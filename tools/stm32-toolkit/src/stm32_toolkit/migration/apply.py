"""Guarded staging, atomic apply, and rollback for an accepted conversion plan.

Apply revalidates the plan's every field and digest, the canonical root, the
Git HEAD, patch-target containment and state, a clean porcelain status, a
freshly re-run inspection and plan, and the absence of blockers before its
first write.  All writes then happen through a private staging directory with
exclusive creation, fsync, sibling temporary files, ``os.replace``, and a
byte-exact rollback on failure.  ``.uvprojx``, Git state, unrelated files, and
out-of-root targets are never touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.result import OperationResult

from stm32_toolkit.migration import git_guard
from stm32_toolkit.migration.model import (
    FilePatch,
    FixedSectionRequirement,
    GitBaseline,
    MigrationBlocker,
    MigrationInput,
    MigrationPlan,
    MigrationPlanError,
    full_sha_error,
    inspection_sha256_for,
    plan_id_for,
    portable_path_error,
    sha256_error,
)
from stm32_toolkit.migration.planner import (
    _MANIFEST_NAME,
    _canonical_root,
    _read_limited,
    plan_keil_conversion,
)

_REPORT_LIMIT_BYTES = 64 * 1024 * 1024
_PATCH_PATH = "artifacts/migration/conversion.patch"
_REPORT_PATH = "artifacts/migration/conversion-report.json"
_ARTIFACT_PATHS = (_PATCH_PATH, _REPORT_PATH)
_STAGING_ROOT = ".stm32-toolkit/migration-staging"
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class _ApplyFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _fail(code: str, message: str, details: dict[str, object]) -> _ApplyFailure:
    return _ApplyFailure(code, message, details)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plan_invalid(rule: str) -> _ApplyFailure:
    return _fail("MIGRATION_PLAN_INVALID", "plan validation failed", {"rule": rule})


# ---------------------------------------------------------------------------
# step 1: forged-plan defense
# ---------------------------------------------------------------------------


def _reserved_patch_path_error(path: str) -> str | None:
    if path == _MANIFEST_NAME:
        return None
    if path.endswith(".uvprojx"):
        return "reserved"
    if path == ".git" or path.startswith(".git/"):
        return "reserved"
    if path.startswith(".stm32-toolkit/"):
        return "reserved"
    if path.startswith("artifacts/migration/"):
        return "reserved"
    return None


def _validate_plan(plan: object) -> None:
    """Full structural and digest validation of the supplied plan."""
    if type(plan) is not MigrationPlan:
        raise _plan_invalid("type")
    if not isinstance(plan.plan_version, int) or plan.plan_version != 1:
        raise _plan_invalid("planVersion")
    if not isinstance(plan.project_root, Path):
        raise _plan_invalid("type")
    if type(plan.inspection) is not KeilInspection:
        raise _plan_invalid("type")
    if type(plan.git) is not GitBaseline:
        raise _plan_invalid("type")
    if full_sha_error(plan.git.head) is not None or plan.git.root_marker != ".":
        raise _plan_invalid("type")
    if not isinstance(plan.inputs, tuple) or not all(
        isinstance(entry, MigrationInput) for entry in plan.inputs
    ):
        raise _plan_invalid("type")
    if not isinstance(plan.patches, tuple) or not all(
        isinstance(patch, FilePatch) for patch in plan.patches
    ):
        raise _plan_invalid("type")
    if not isinstance(plan.fixed_sections, tuple) or not all(
        isinstance(section, FixedSectionRequirement) for section in plan.fixed_sections
    ):
        raise _plan_invalid("type")
    if not isinstance(plan.blockers, tuple) or not all(
        isinstance(blocker, MigrationBlocker) for blocker in plan.blockers
    ):
        raise _plan_invalid("type")

    for entry in plan.inputs:
        if portable_path_error(entry.path) is not None:
            raise _plan_invalid("portablePath")
        if (
            sha256_error(entry.sha256) is not None
            or not isinstance(entry.size, int)
            or entry.size < 0
        ):
            raise _plan_invalid("digestFormat")
    for patch in plan.patches:
        if portable_path_error(patch.path) is not None:
            raise _plan_invalid("portablePath")
        if _reserved_patch_path_error(patch.path) is not None:
            raise _plan_invalid("portablePath")
        if not isinstance(patch.rule_ids, tuple) or not all(
            isinstance(rule, str) for rule in patch.rule_ids
        ):
            raise _plan_invalid("type")
        if not isinstance(patch.unified_diff, str):
            raise _plan_invalid("type")
        if not isinstance(patch.after_bytes, bytes) or not isinstance(
            patch.before_bytes, (bytes, type(None))
        ):
            raise _plan_invalid("type")
    for section in plan.fixed_sections:
        if (
            not isinstance(section.section, str)
            or not isinstance(section.address, int)
            or portable_path_error(section.source_path) is not None
            or not isinstance(section.line, int)
            or not isinstance(section.symbol, str)
        ):
            raise _plan_invalid("type")
    for blocker in plan.blockers:
        if (
            not isinstance(blocker.code, str)
            or not isinstance(blocker.rule_id, str)
            or portable_path_error(blocker.path) is not None
            or not isinstance(blocker.line, int)
            or not isinstance(blocker.column, int)
            or not isinstance(blocker.evidence, str)
            or not isinstance(blocker.message, str)
        ):
            raise _plan_invalid("type")

    input_paths = [entry.path for entry in plan.inputs]
    patch_paths = [patch.path for patch in plan.patches]
    if len(set(input_paths)) != len(input_paths):
        raise _plan_invalid("uniquePath")
    if len(set(patch_paths)) != len(patch_paths):
        raise _plan_invalid("uniquePath")
    all_paths = input_paths + patch_paths
    for index, first in enumerate(all_paths):
        for second in all_paths[index + 1 :]:
            if first != second and first.casefold() == second.casefold():
                raise _plan_invalid("casefoldCollision")

    if input_paths != sorted(input_paths):
        raise _plan_invalid("sortedOrder")
    if patch_paths != sorted(patch_paths):
        raise _plan_invalid("sortedOrder")
    fixed_key = lambda s: (s.address, s.section, s.source_path, s.line, s.symbol)
    if list(plan.fixed_sections) != sorted(plan.fixed_sections, key=fixed_key):
        raise _plan_invalid("sortedOrder")
    blocker_key = lambda b: (b.path, b.line, b.column, b.code, b.rule_id)
    if list(plan.blockers) != sorted(plan.blockers, key=blocker_key):
        raise _plan_invalid("sortedOrder")

    for patch in plan.patches:
        created = patch.before_bytes is None
        if created:
            if patch.before_sha256 is not None or patch.before_size is not None:
                raise _plan_invalid("patchDigest")
        else:
            if (
                sha256_error(patch.before_sha256) is not None
                or not isinstance(patch.before_size, int)
                or patch.before_size < 0
                or _sha256(patch.before_bytes) != patch.before_sha256
                or len(patch.before_bytes) != patch.before_size
            ):
                raise _plan_invalid("patchDigest")
        if (
            sha256_error(patch.after_sha256) is not None
            or not isinstance(patch.after_size, int)
            or patch.after_size < 0
            or _sha256(patch.after_bytes) != patch.after_sha256
            or len(patch.after_bytes) != patch.after_size
        ):
            raise _plan_invalid("patchDigest")

    if inspection_sha256_for(plan.inspection) != plan.inspection_sha256:
        raise _plan_invalid("inspectionSha256")
    if plan_id_for(plan) != plan.plan_id:
        raise _plan_invalid("planId")


# ---------------------------------------------------------------------------
# steps 2-4: root, Git, inputs, targets
# ---------------------------------------------------------------------------


def _resolve_patch_target(root: Path, path: str) -> Path:
    try:
        resolved = root.joinpath(*path.split("/")).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "MIGRATION_PATH_INVALID",
            "patch target resolution failed",
            {"path": path, "rule": "withinProjectRoot"},
        )
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _fail(
            "MIGRATION_PATH_INVALID",
            "patch target escapes the project root",
            {"path": path, "rule": "withinProjectRoot"},
        )
    return resolved


def _revalidate_apply_inputs(root: Path, plan: MigrationPlan) -> None:
    for entry in plan.inputs:
        path = entry.path
        try:
            absolute = _resolve_patch_target(root, path)
        except _ApplyFailure:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input is no longer inside the project root",
                {"path": path},
            )
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise _fail("MIGRATION_INPUT_CHANGED", "recorded input is missing", {"path": path})
        except NotADirectoryError:
            raise _fail("MIGRATION_INPUT_CHANGED", "recorded input is missing", {"path": path})
        except OSError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input inspection failed",
                {"path": path},
            )
        if not stat.S_ISREG(lst.st_mode):
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input is not a regular file",
                {"path": path},
            )
        try:
            data = _read_limited(absolute, entry.size)
        except FileNotFoundError:
            raise _fail("MIGRATION_INPUT_CHANGED", "recorded input is missing", {"path": path})
        except OSError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input is unreadable",
                {"path": path},
            )
        if len(data) > entry.size or len(data) != entry.size or _sha256(data) != entry.sha256:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input bytes changed",
                {"path": path},
            )


def _validate_patch_targets(root: Path, plan: MigrationPlan) -> None:
    destinations = [patch.path for patch in plan.patches] + list(_ARTIFACT_PATHS)
    for path in destinations:
        _resolve_patch_target(root, path)
    for patch in plan.patches:
        if patch.before_bytes is None:
            continue
        target = _resolve_patch_target(root, patch.path)
        try:
            lst = os.lstat(target)
        except FileNotFoundError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED", "patch target is missing", {"path": patch.path}
            )
        except NotADirectoryError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED", "patch target is missing", {"path": patch.path}
            )
        except OSError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "patch target inspection failed",
                {"path": patch.path},
            )
        if not stat.S_ISREG(lst.st_mode):
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "patch target is not a regular file",
                {"path": patch.path},
            )
        try:
            data = _read_limited(target, patch.before_size)
        except FileNotFoundError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED", "patch target is missing", {"path": patch.path}
            )
        except OSError:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "patch target is unreadable",
                {"path": patch.path},
            )
        if len(data) != patch.before_size or _sha256(data) != patch.before_sha256:
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "patch target bytes changed",
                {"path": patch.path},
            )
    for path in destinations:
        if any(patch.path == path and patch.before_bytes is not None for patch in plan.patches):
            continue
        try:
            os.lstat(root.joinpath(*path.split("/")))
        except FileNotFoundError:
            continue
        except NotADirectoryError:
            continue
        except OSError:
            raise _fail(
                "MIGRATION_PATH_INVALID",
                "creation target state cannot be verified",
                {"path": path, "rule": "withinProjectRoot"},
            )
        raise _fail("MIGRATION_TARGET_EXISTS", "creation target already exists", {"path": path})


# ---------------------------------------------------------------------------
# step 5: fresh re-inspection and re-planning
# ---------------------------------------------------------------------------


def _fresh_plan(root: Path, plan: MigrationPlan) -> MigrationPlan:
    try:
        return plan_keil_conversion(root, plan.inspection)
    except MigrationPlanError as error:
        if error.code == "MIGRATION_INSPECTION_CHANGED":
            raise _fail(
                "MIGRATION_INPUT_CHANGED",
                "recorded input bytes changed",
                {"path": error.details.get("path", "")},
            )
        if error.code == "MIGRATION_INSPECTION_INVALID":
            raise _plan_invalid("freshInspection")
        raise _plan_invalid("freshPlan")


def _fresh_plan_matches(fresh: MigrationPlan, plan: MigrationPlan) -> bool:
    if fresh.to_dict() != plan.to_dict():
        return False
    fresh_by_path = {patch.path: patch for patch in fresh.patches}
    for patch in plan.patches:
        other = fresh_by_path.get(patch.path)
        if other is None:
            return False
        if other.before_bytes != patch.before_bytes or other.after_bytes != patch.after_bytes:
            return False
    return True


# ---------------------------------------------------------------------------
# artifact bytes
# ---------------------------------------------------------------------------


def _build_report(plan: MigrationPlan, patch_bytes: bytes) -> bytes:
    inspection = plan.inspection
    payload = {
        "schemaVersion": 1,
        "toolkitVersion": __version__,
        "planId": plan.plan_id,
        "gitHead": plan.git.head,
        "inspectionSha256": plan.inspection_sha256,
        "inputs": [
            {"path": entry.path, "sha256": entry.sha256, "size": entry.size}
            for entry in plan.inputs
        ],
        "patches": [
            {
                "path": patch.path,
                "beforeSha256": patch.before_sha256,
                "afterSha256": patch.after_sha256,
                "beforeSize": patch.before_size,
                "afterSize": patch.after_size,
                "ruleIds": list(patch.rule_ids),
            }
            for patch in plan.patches
        ],
        "fixedSections": [
            {
                "section": section.section,
                "address": section.address,
                "sourcePath": section.source_path,
                "line": section.line,
                "symbol": section.symbol,
            }
            for section in plan.fixed_sections
        ],
        "ignoredCompatible": [
            {
                "ruleId": observation.rule_id,
                "path": observation.path,
                "line": observation.line,
                "column": observation.column,
                "evidence": observation.evidence,
            }
            for observation in sorted(
                getattr(plan, "_ignored", ()),
                key=lambda o: (o.path, o.line, o.column, o.rule_id),
            )
        ],
        "omittedSources": [
            {"path": source.path, "language": source.language}
            for source in sorted(
                (
                    source
                    for source in inspection.sources
                    if source.language in ("header", "library", "other")
                ),
                key=lambda s: s.path,
            )
        ],
        "includedAssembly": sorted(
            source.path
            for source in inspection.sources
            if source.included and source.language == "asm"
        ),
        "blockers": [
            {
                "code": blocker.code,
                "ruleId": blocker.rule_id,
                "path": blocker.path,
                "line": blocker.line,
                "column": blocker.column,
                "evidence": blocker.evidence,
                "message": blocker.message,
            }
            for blocker in plan.blockers
        ],
        "artifacts": {
            "patch": _PATCH_PATH,
            "patchSha256": _sha256(patch_bytes),
            "report": _REPORT_PATH,
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def plan_patch_bytes(plan: MigrationPlan) -> bytes:
    return b"".join(patch.unified_diff.encode("utf-8") for patch in plan.patches)


# ---------------------------------------------------------------------------
# staging, replace, rollback
# ---------------------------------------------------------------------------


def _within_root_prefix(root_resolved: str, candidate: Path) -> bool:
    """String-prefix containment: equal to the root or directly under it."""
    candidate_str = os.path.normcase(str(candidate))
    return candidate_str == root_resolved or candidate_str.startswith(
        root_resolved + os.sep
    )


def _validate_staging_containment(root: Path, staging: Path) -> None:
    """Reject any staging path component that escapes the project root.

    The staging directory lives at ``.stm32-toolkit/migration-staging/<id>``.
    On a healthy tree those are regular project directories, but either
    intermediate component may be an attacker-influenced redirect (symlink,
    junction, or reparse point) whose canonical target lies outside the root.
    Every component is resolved with ``Path.resolve()`` and string-prefix
    compared against the resolved project root before the first staging write
    (and before any ``lstat`` of the staging path), so an escape returns the
    stable ``MIGRATION_PATH_INVALID`` / ``withinProjectRoot`` failure without
    changing any external directory.
    """
    portable = f"{_STAGING_ROOT}/{staging.name}"
    try:
        root_resolved = os.path.normcase(str(root.resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "MIGRATION_PATH_INVALID",
            "project root resolution failed",
            {"path": portable, "rule": "withinProjectRoot"},
        )
    current = root
    for component in _STAGING_ROOT.split("/") + [staging.name]:
        current = current.joinpath(component)
        try:
            resolved = current.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            raise _fail(
                "MIGRATION_PATH_INVALID",
                "staging path resolution failed",
                {"path": portable, "rule": "withinProjectRoot"},
            )
        if not _within_root_prefix(root_resolved, resolved):
            raise _fail(
                "MIGRATION_PATH_INVALID",
                "staging path escapes the project root",
                {"path": portable, "rule": "withinProjectRoot"},
            )


class _FsyncError(OSError):
    pass


def _fsync(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as error:
        raise _FsyncError(error.errno, error.strerror) from error


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return  # directory fsync not supported here
    try:
        _fsync(fd)
    finally:
        os.close(fd)


def _stage_write(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            _fsync(handle.fileno())
        os.chmod(path, mode)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _temp_write(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            _fsync(handle.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _remove_staging(staging: Path) -> None:
    shutil.rmtree(staging)
    try:
        os.rmdir(staging.parent)
    except OSError:
        pass


def _remove_created_dirs(created_dirs: list[Path], skip: set[Path]) -> None:
    for directory in reversed(created_dirs):
        if directory in skip:
            continue
        try:
            os.rmdir(directory)
        except OSError:
            pass


def _apply(plan: MigrationPlan) -> dict[str, object]:
    _validate_plan(plan)

    canonical = _canonical_root(plan.project_root)
    try:
        inspection_root = plan.inspection.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _plan_invalid("projectRoot")
    if canonical != inspection_root:
        raise _plan_invalid("projectRoot")
    try:
        toplevel = git_guard.git_toplevel(canonical)
    except MigrationPlanError as error:
        raise _fail(error.code, error.message, error.details)
    if toplevel != canonical:
        raise _plan_invalid("projectRoot")
    try:
        head = git_guard.git_head(canonical)
    except MigrationPlanError as error:
        raise _fail(error.code, error.message, error.details)
    if head != plan.git.head:
        raise _fail(
            "MIGRATION_GIT_HEAD_CHANGED",
            "Git HEAD changed since planning",
            {"expected": plan.git.head, "actual": head},
        )

    _revalidate_apply_inputs(canonical, plan)
    _validate_patch_targets(canonical, plan)

    staging = canonical.joinpath(*_STAGING_ROOT.split("/"), plan.plan_id)
    # A staging escape must be rejected before any other preflight step can
    # short-circuit with a less specific failure: the canonical staging path
    # (including the .stm32-toolkit and migration-staging intermediates) must
    # stay inside the project root before the first write.
    _validate_staging_containment(canonical, staging)

    try:
        status = git_guard.porcelain_status(canonical)
    except MigrationPlanError as error:
        raise _fail(error.code, error.message, error.details)
    if status:
        raise _fail(
            "MIGRATION_GIT_DIRTY",
            "Git working tree is not clean",
            {"rule": "cleanWorktree"},
        )

    fresh = _fresh_plan(canonical, plan)
    if not _fresh_plan_matches(fresh, plan):
        raise _plan_invalid("freshPlan")
    if plan.blockers:
        raise _fail(
            "MIGRATION_BLOCKED",
            "conversion is blocked",
            {"blockerCodes": sorted({blocker.code for blocker in plan.blockers})},
        )

    patch_bytes = plan_patch_bytes(plan)
    report_bytes = _build_report(plan, patch_bytes)
    if len(report_bytes) > _REPORT_LIMIT_BYTES:
        raise _plan_invalid("reportLimit")

    destinations: list[tuple[str, bytes, int]] = []
    for patch in plan.patches:
        destinations.append((patch.path, patch.after_bytes, 1 if patch.before_bytes is not None else 0))
    destinations.append((_PATCH_PATH, patch_bytes, 0))
    destinations.append((_REPORT_PATH, report_bytes, 0))
    destinations.sort(key=lambda item: item[0])

    staging = canonical.joinpath(*_STAGING_ROOT.split("/"), plan.plan_id)
    # Repeat the containment check immediately before any staging state is
    # inspected or created, closing the gap left by the earlier preflight run.
    _validate_staging_containment(canonical, staging)
    try:
        os.lstat(staging)
    except FileNotFoundError:
        pass
    except NotADirectoryError:
        raise _fail(
            "MIGRATION_TARGET_EXISTS",
            "staging path already exists",
            {"path": f"{_STAGING_ROOT}/{plan.plan_id}"},
        )
    except OSError:
        raise _fail(
            "MIGRATION_PATH_INVALID",
            "staging state cannot be verified",
            {"path": f"{_STAGING_ROOT}/{plan.plan_id}", "rule": "withinProjectRoot"},
        )
    else:
        raise _fail(
            "MIGRATION_TARGET_EXISTS",
            "staging path already exists",
            {"path": f"{_STAGING_ROOT}/{plan.plan_id}"},
        )

    created_dirs: list[Path] = []
    replaced: list[tuple[str, Path, Path]] = []  # (portable path, target, backup)
    created_files: list[tuple[str, Path]] = []
    temp_files: list[tuple[str, Path]] = []
    success = False

    def ensure_dir(path: Path) -> None:
        """Create ``path`` and record every missing ancestor (shallowest first)."""
        if path.is_dir():
            return
        missing: list[Path] = []
        current = path
        while not current.is_dir():
            missing.append(current)
            if current.parent == current:
                break
            current = current.parent
        os.makedirs(path, exist_ok=True)
        created_dirs.extend(reversed(missing))

    try:
        # --- stage phase ----------------------------------------------------
        stage_root = staging / "new"
        backup_root = staging / "backup"
        ensure_dir(staging)
        ensure_dir(stage_root)
        ensure_dir(backup_root)
        for path, data, existed in destinations:
            staged = stage_root.joinpath(*path.split("/"))
            ensure_dir(staged.parent)
            if existed:
                target = canonical.joinpath(*path.split("/"))
                lst = os.lstat(target)
                original_mode = stat.S_IMODE(lst.st_mode)
                backup = backup_root.joinpath(*path.split("/"))
                ensure_dir(backup.parent)
                with target.open("rb") as handle:
                    original = handle.read()
                _stage_write(backup, original, original_mode)
                _stage_write(staged, data, original_mode)
            else:
                _stage_write(staged, data, 0o644)

        # --- replace phase --------------------------------------------------
        for path, data, existed in destinations:
            target = canonical.joinpath(*path.split("/"))
            _resolve_patch_target(canonical, path)
            ensure_dir(target.parent)
            mode = 0o644 if not existed else stat.S_IMODE(os.lstat(target).st_mode)
            temp = target.parent / f".{plan.plan_id[:12]}.{target.name}.stm32tk-tmp"
            _temp_write(temp, data, mode)
            temp_files.append((path, temp))
            os.replace(temp, target)
            temp_files.remove((path, temp))
            if existed:
                replaced.append((path, target, backup_root.joinpath(*path.split("/"))))
            else:
                created_files.append((path, target))
            try:
                _fsync_dir(target.parent)
            except OSError as error:
                raise _FsyncError(error.errno, error.strerror) from error
        success = True
        _remove_staging(staging)
    except _ApplyFailure:
        raise
    except OSError as error:
        if isinstance(error, _FsyncError):
            phase = "fsync"
        elif success:
            phase = "stage"
        else:
            phase = "replace" if replaced or created_files or temp_files else "stage"
        try:
            if replaced or created_files or temp_files:
                _rollback(staging, replaced, created_files, created_dirs, temp_files)
            else:
                try:
                    _remove_staging(staging)
                except OSError:
                    pass
                _remove_created_dirs(created_dirs, {staging, staging.parent})
        except _ApplyFailure:
            raise
        raise _fail("MIGRATION_APPLY_FAILED", "apply failed", {"phase": phase})

    return {
        "planId": plan.plan_id,
        "gitHead": plan.git.head,
        "changedPaths": [patch.path for patch in plan.patches if patch.before_bytes is not None],
        "createdPaths": sorted(
            [patch.path for patch in plan.patches if patch.before_bytes is None]
            + [_PATCH_PATH, _REPORT_PATH]
        ),
        "fixedSections": [
            {
                "section": section.section,
                "address": section.address,
                "sourcePath": section.source_path,
                "line": section.line,
                "symbol": section.symbol,
            }
            for section in plan.fixed_sections
        ],
        "patchPath": _PATCH_PATH,
        "patchSha256": _sha256(patch_bytes),
        "reportPath": _REPORT_PATH,
        "reportSha256": _sha256(report_bytes),
    }


def _rollback(
    staging: Path,
    replaced: list[tuple[str, Path, Path]],
    created_files: list[tuple[str, Path]],
    created_dirs: list[Path],
    temp_files: list[tuple[str, Path]],
) -> None:
    """Restore every pre-apply byte and mode; failures retain recoverable staging."""
    failed: list[str] = []
    for path, temp in temp_files:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(path)
    for path, target, backup in reversed(replaced):
        try:
            os.replace(backup, target)
        except OSError:
            failed.append(path)
    for path, target in reversed(created_files):
        try:
            os.unlink(target)
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(path)
    if failed:
        raise _fail(
            "MIGRATION_ROLLBACK_FAILED",
            "rollback could not restore every path",
            {"paths": sorted(set(failed))},
        )
    try:
        _remove_staging(staging)
    except OSError:
        pass  # staging retention is recoverable
    _remove_created_dirs(created_dirs, {staging, staging.parent})


def apply_keil_conversion(plan: MigrationPlan) -> OperationResult[dict[str, object]]:
    """Apply the accepted plan atomically, or fail without partial writes."""
    try:
        data = _apply(plan)
    except _ApplyFailure as failure:
        return OperationResult.failure(
            "keil-conversion-apply",
            failure.code,
            failure.message,
            failure.details,
        )
    except MigrationPlanError as error:
        return OperationResult.failure(
            "keil-conversion-apply",
            error.code,
            error.message,
            error.details,
        )
    return OperationResult.success("keil-conversion-apply", data)
