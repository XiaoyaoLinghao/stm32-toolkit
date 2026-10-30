"""Input snapshots, Git evidence, ELF validation, identity, and atomic evidence.

``snapshot_project_inputs`` hashes exact bytes for the manifest, declared
sources, assembly sources, all owned generated files, and recursively
bounded include directories (lexically sorted portable paths, regular files
only, escaping redirects/loops/special files/unreadable entries and
duplicate/casefold collisions rejected).  Git evidence comes only from the
fixed bounded ``git rev-parse --verify HEAD`` and
``git status --porcelain=v1 -z --untracked-files=all`` argv; build outputs
and ``artifacts/migration`` never contribute to the dirty interpretation.
ELF validation is fail-closed with pyelftools over an already bounded byte
buffer.  Identity documents are validated against the packaged schema and
published atomically (temp + flush + fsync + replace + directory fsync).
"""

from __future__ import annotations

import importlib.resources
import io
import json
import os
import re
import stat
import struct
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from jsonschema import Draft202012Validator

from stm32_toolkit import __version__
from stm32_toolkit.build.abi_evidence import validate_float_abi_evidence
from stm32_toolkit.build.map_file import (
    ElfSectionEvidence,
    MapError,
    map_error,
    parse_map,
)
from stm32_toolkit.build.memory_margin import MemorySummary, MemorySummaryError
from stm32_toolkit.build.model import (
    BUILD_ARTIFACT_INVALID,
    BUILD_EVIDENCE_FAILED,
    BUILD_GIT_INVALID,
    BUILD_INPUT_INVALID,
    BUILD_MAP_INVALID,
    BUILD_PROJECT_INVALID,
    BUILD_REQUEST_INVALID,
    GIT_DIAGNOSTIC_UNAVAILABLE,
    IDENTITY_SCHEMA_VERSION,
    SNAPSHOT_IDENTITY_SCHEMA_VERSION,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
    SUPPORTED_PRESETS,
    BuildError,
    build_error,
)
from stm32_toolkit.generation.managed_files import (
    _reject_duplicate_json_keys,
    canonical_json_bytes,
    parse_managed_manifest,
    portable_path_error,
    portable_sort_key,
    sha256_hex,
)
from stm32_toolkit.process import ProcessError, ProcessRequest, run_process
from stm32_toolkit.project_model import MemoryRegion, ProjectModel

_FILE_LIMIT_BYTES = 8 * 1024 * 1024
_AGGREGATE_LIMIT_BYTES = 256 * 1024 * 1024
_FILE_LIMIT_COUNT = 10000
_ELF_LIMIT_BYTES = 64 * 1024 * 1024
_MAP_LIMIT_BYTES = 32 * 1024 * 1024
_EVIDENCE_LIMIT_BYTES = 8 * 1024 * 1024
_MAX_WALK_DEPTH = 64
#: Deterministic bound for fragment-project overlap evidence; the ELF byte
#: limit alone would otherwise permit quadratic interval work.
_FRAGMENT_ALLOCATED_SECTION_LIMIT = 100_000
LEGACY_INPUT_DISCOVERY_POLICY = "legacy"
SOURCE_LOCAL_HEADERS_POLICY = "source-local-headers-v1"

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_DIAGNOSTIC_RULES = frozenset({"head", "status"})
#: Required public artifact inventory of a current schema-2 success record.
SNAPSHOT_BUILD_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "status",
        "stage",
        "code",
        "buildId",
        "sourceBaseline",
        "gitHead",
        "gitDirty",
        "gitEvidence",
        "inputSnapshotSha256",
        "targetDevice",
        "preset",
        "startedAtUtc",
        "finishedAtUtc",
        "durationMs",
        "artifacts",
        "memory",
        "warnings",
    }
)
#: The only fields a current receipt may add on top of the required set.
#: Every other extra stays rejected; absence keeps legacy records readable.
BUILD_RESULT_OPTIONAL_FIELDS = frozenset({"toolkitVersion", "floatAbi"})

_FIXED_SECTION_RE = re.compile(r"^\.stm32tk\.abs\.([0-9A-Fa-f]{8})$")
_ARM_MACHINE = "EM_ARM"
_SHF_ALLOC = 0x2
_SHN_UNDEF = "SHN_UNDEF"
_STB_WEAK = "STB_WEAK"

def _default_sync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return  # directory fsync is unavailable on some platforms (e.g. Windows)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


#: Module seams (tests inject failures; Windows never touches missing APIs).
_lstat = os.lstat
_listdir = os.listdir
_scandir = os.scandir
_fsync_file = os.fsync
_replace = os.replace
_sync_directory = _default_sync_directory


def _read_limited(path: Path, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes through the injectable open seam."""
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def read_bounded(path: Path, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes; callers enforce the bound."""
    return _read_limited(path, limit)


def utc_now_rfc3339() -> str:
    """RFC 3339 UTC with exactly six fractional digits and ``Z``."""
    now = datetime.now(timezone.utc)
    return f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond:06d}Z"


# ---------------------------------------------------------------------------
# model artifact mapping
# ---------------------------------------------------------------------------


def model_artifact_paths(model: ProjectModel, preset: str) -> tuple[str, str]:
    """Central validated mapping from the model ELF to preset-specific paths.

    Debug uses ``build/arm-debug/<basename>.elf``; release uses the same
    basename under ``build/arm-release``.  The MAP shares the directory and
    basename with a ``.map`` extension.
    """
    if preset not in SUPPORTED_PRESETS:
        raise build_error(
            BUILD_REQUEST_INVALID, "build request is invalid", {"field": "preset", "rule": "value"}
        )
    elf_rel = model.build.elf
    if elf_rel is None or not elf_rel.startswith("build/arm-debug/"):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "build.elf", "rule": "value"},
        )
    base = elf_rel[len("build/arm-debug/") :]
    if (
        not base
        or "/" in base
        or "\\" in base
        or not base.endswith(".elf")
        or len(base) <= len(".elf")
    ):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "build.elf", "rule": "value"},
        )
    stem = base[: -len(".elf")]
    elf = elf_rel if preset == "arm-debug" else "build/arm-release/" + base
    return elf, f"build/{preset}/{stem}.map"


def _relative_to_root(path: Path, root: Path) -> str:
    return "/".join(path.resolve(strict=False).relative_to(root).parts)


# ---------------------------------------------------------------------------
# input snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEntry:
    path: str
    size: int
    sha256: str
    mtime_ns: int


@dataclass(frozen=True)
class InputSnapshot:
    entries: tuple[SnapshotEntry, ...]
    sha256: str
    newest_mtime_ns: int
    policy: str = LEGACY_INPUT_DISCOVERY_POLICY


def _input_invalid(path: str, rule: str) -> BuildError:
    return build_error(
        BUILD_INPUT_INVALID, "build input is invalid", {"path": path, "rule": rule}
    )


def _input_invalid_rule(rule: str) -> BuildError:
    return build_error(BUILD_INPUT_INVALID, "build input is invalid", {"rule": rule})


def snapshot_project_inputs(
    model: ProjectModel, *, policy: str = SOURCE_LOCAL_HEADERS_POLICY
) -> InputSnapshot:
    """Hash declared inputs and the selected policy's discovered inputs.

    A regular file reached by both an explicit source declaration and
    include-directory traversal is counted exactly once (STM32TK-0306
    revision 1): the traversal skips any path that is already declared or
    that resolves to an already-declared canonical file.  Duplicate
    declarations of the same canonical file, Unicode casefold conflicts,
    and redirect/reparse escapes fail closed; include-only overlaps (for
    example two case-variant names for one file) remain distinct so the
    casefold collision check still fails closed. The new policy also scans
    immediate header siblings of declared sources under the same input limits.
    """
    if policy not in (LEGACY_INPUT_DISCOVERY_POLICY, SOURCE_LOCAL_HEADERS_POLICY):
        raise _input_invalid_rule("discoveryPolicy")
    root = model.project_root
    paths: list[str] = []
    declared_identities: dict[tuple[int, int], str] = {}
    declared = [".stm32-project.json", *model.build.sources, *model.build.assembly_sources]
    native_linker = model.generation.native_linker_script
    fragment = model.generation.linker_fragment
    fragment_path = fragment.path if fragment is not None else None
    if native_linker is not None:
        declared.append(native_linker)
    if fragment_path is not None:
        declared.append(fragment_path)
    for rel in declared:
        _require_input_path(
            root,
            rel,
            paths,
            declared_identities,
            reject_redirect=rel == native_linker or rel == fragment_path,
        )
    manifest_rel = model.generation.managed_manifest
    manifest_abs = root.joinpath(*manifest_rel.split("/"))
    try:
        manifest_data = _read_limited(manifest_abs, _FILE_LIMIT_BYTES)
    except FileNotFoundError:
        raise _input_invalid(manifest_rel, "missing") from None
    except OSError:
        raise _input_invalid(manifest_rel, "unreadable") from None
    if len(manifest_data) > _FILE_LIMIT_BYTES:
        raise _input_invalid(manifest_rel, "size")
    try:
        records = parse_managed_manifest(manifest_data)
    except Exception as error:
        details = getattr(error, "details", None)
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            dict(details) if isinstance(details, dict) else {"path": manifest_rel, "rule": "manifest"},
        ) from None
    for record in records:
        _require_input_path(root, record.path, paths, declared_identities)
    if policy == SOURCE_LOCAL_HEADERS_POLICY:
        _add_source_local_headers(model, paths, declared_identities)
    walked: set[str] = set()
    explicitly_walked: set[str] = set()
    for include in model.build.include_paths:
        _walk_include(
            root,
            include,
            paths,
            declared_identities,
            walked,
            explicit_walked=explicitly_walked,
        )
    if len(paths) > _FILE_LIMIT_COUNT:
        raise _input_invalid_rule("fileCount")
    collision = casefold_collision(paths)
    if collision is not None:
        raise _input_invalid(collision, "collision")
    entries: list[SnapshotEntry] = []
    aggregate = 0
    for rel in paths:
        absolute = root.joinpath(*rel.split("/"))
        try:
            lst = _lstat(absolute)
        except FileNotFoundError:
            raise _input_invalid(rel, "missing") from None
        except OSError:
            raise _input_invalid(rel, "inspection") from None
        read_path = absolute
        if stat.S_ISLNK(lst.st_mode):
            try:
                resolved = absolute.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                raise _input_invalid(rel, "escape") from None
            read_path = resolved
            try:
                lst = _lstat(resolved)
            except OSError:
                raise _input_invalid(rel, "inspection") from None
        if not stat.S_ISREG(lst.st_mode):
            raise _input_invalid(rel, "regularFile")
        try:
            data = _read_limited(read_path, _FILE_LIMIT_BYTES)
        except OSError:
            raise _input_invalid(rel, "unreadable") from None
        if len(data) > _FILE_LIMIT_BYTES:
            raise _input_invalid(rel, "size")
        if (
            fragment is not None
            and rel == fragment_path
            and sha256_hex(data) != fragment.sha256
        ):
            # The model parsed one frozen byte image.  The snapshot must not
            # silently accept a different fragment that appeared between the
            # model load and input discovery; this also covers a change during
            # the build itself on the post-build snapshot.
            raise _input_invalid(rel, "fragmentChanged")
        aggregate += len(data)
        if aggregate > _AGGREGATE_LIMIT_BYTES:
            raise _input_invalid_rule("aggregate")
        entries.append(
            SnapshotEntry(
                path=rel,
                size=len(data),
                sha256=sha256_hex(data),
                mtime_ns=lst.st_mtime_ns,
            )
        )
    entries.sort(key=lambda entry: portable_sort_key(entry.path))
    payload = [
        {"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in entries
    ]
    digest = sha256_hex(canonical_json_bytes(payload))
    newest = max((entry.mtime_ns for entry in entries), default=0)
    return InputSnapshot(entries=tuple(entries), sha256=digest, newest_mtime_ns=newest,
                         policy=policy)


def _add_source_local_headers(
    model: ProjectModel, paths: list[str], declared_identities: dict[tuple[int, int], str]
) -> None:
    """Inspect only immediate siblings of declared source and assembly files."""
    root = model.project_root
    parents = sorted({str(Path(source).parent).replace("\\", "/")
                      for source in (*model.build.sources, *model.build.assembly_sources)},
                     key=portable_sort_key)
    inspected = 0
    declared_at_start = set(declared_identities)
    by_casefold = {path.casefold(): path for path in paths}
    for parent in parents:
        if parent != "." and portable_path_error(parent) is not None:
            raise _input_invalid(parent, "portable")
        directory = root if parent == "." else root.joinpath(*parent.split("/"))
        try:
            resolved = directory.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_dir():
                raise ValueError
            names = []
            with _scandir(directory) as entries:
                for entry in entries:
                    inspected += 1
                    if inspected > _FILE_LIMIT_COUNT:
                        raise _input_invalid_rule("siblingCount")
                    names.append(entry.name)
            names.sort(key=portable_sort_key)
        except (OSError, RuntimeError, ValueError):
            raise _input_invalid(parent, "inspection") from None
        for name in names:
            if not name.lower().endswith(".h"):
                continue
            rel = name if parent == "." else f"{parent}/{name}"
            if rel in paths:
                continue
            prior = by_casefold.get(rel.casefold())
            if prior is not None and prior != rel:
                raise _input_invalid(rel, "collision")
            if portable_path_error(rel) is not None:
                raise _input_invalid(rel, "portable")
            absolute = directory / name
            try:
                lst = _lstat(absolute)
            except OSError:
                raise _input_invalid(rel, "inspection") from None
            if not stat.S_ISREG(lst.st_mode):
                raise _input_invalid(rel, "regularFile")
            identity = _canonical_identity(absolute, lst, root, rel)
            if identity is not None and identity in declared_at_start:
                continue
            _require_input_path(root, rel, paths, declared_identities)
            by_casefold[rel.casefold()] = rel


def identity_discovery_policy(document: dict[str, object]) -> str:
    """Read the policy from an already validated firmware identity document."""
    marker = document.get("inputDiscoveryPolicy")
    if marker is None and "inputDiscoveryPolicy" not in document:
        return LEGACY_INPUT_DISCOVERY_POLICY
    if marker != SOURCE_LOCAL_HEADERS_POLICY:
        raise build_error(BUILD_EVIDENCE_FAILED, "identity evidence is invalid",
                          {"phase": "identity"})
    return SOURCE_LOCAL_HEADERS_POLICY


def _require_input_path(
    root: Path,
    rel: str,
    paths: list[str],
    declared_identities: dict[tuple[int, int], str],
    *,
    reject_redirect: bool = False,
) -> None:
    if portable_path_error(rel) is not None:
        raise _input_invalid(rel, "portable")
    if rel.startswith("build/") or rel.startswith("artifacts/migration"):
        raise _input_invalid(rel, "reserved")
    if rel in paths:
        raise _input_invalid_rule("duplicate")
    absolute = root.joinpath(*rel.split("/"))
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel, "escape") from None
    try:
        lst = _lstat(absolute)
    except FileNotFoundError:
        raise _input_invalid(rel, "missing") from None
    except OSError:
        raise _input_invalid(rel, "inspection") from None
    if reject_redirect and (
        stat.S_ISLNK(lst.st_mode)
        or bool(getattr(lst, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    ):
        raise _input_invalid(rel, "redirect")
    if not stat.S_ISREG(lst.st_mode):
        raise _input_invalid(rel, "regularFile")
    identity = _canonical_identity(absolute, lst, root, rel)
    if identity is not None and identity in declared_identities:
        raise _input_invalid_rule("duplicate")
    if identity is not None:
        declared_identities[identity] = rel
    paths.append(rel)


def _canonical_identity(
    absolute: Path, lst: os.stat_result, root: Path, rel: str
) -> tuple[int, int] | None:
    """Return the canonical ``(st_dev, st_ino)`` the path resolves to.

    Symlink declarations resolve to their target; redirect/reparse escapes
    and non-regular targets fail closed with the established rules.
    """
    if not stat.S_ISLNK(lst.st_mode):
        return (lst.st_dev, lst.st_ino)
    try:
        resolved = absolute.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel, "escape") from None
    try:
        target_lst = _lstat(resolved)
    except OSError:
        raise _input_invalid(rel, "inspection") from None
    if not stat.S_ISREG(target_lst.st_mode):
        raise _input_invalid(rel, "regularFile")
    return (target_lst.st_dev, target_lst.st_ino)


def _walk_include(
    root: Path,
    rel_dir: str,
    paths: list[str],
    declared_identities: dict[tuple[int, int], str],
    walked: set[str],
    depth: int = 0,
    explicit_walked: set[str] | None = None,
    explicit: bool = True,
) -> None:
    if explicit_walked is None:
        explicit_walked = set()
    if depth > _MAX_WALK_DEPTH:
        raise _input_invalid(rel_dir, "escape")
    if portable_path_error(rel_dir) is not None:
        raise _input_invalid(rel_dir, "portable")
    if rel_dir.startswith("build/") or rel_dir.startswith("artifacts/migration"):
        raise _input_invalid(rel_dir, "reserved")
    if rel_dir in walked:
        if explicit and rel_dir not in explicit_walked:
            return
        if not explicit and rel_dir in explicit_walked:
            return
        raise _input_invalid_rule("duplicate")
    walked.add(rel_dir)
    if explicit:
        explicit_walked.add(rel_dir)
    absolute = root.joinpath(*rel_dir.split("/"))
    try:
        lst = _lstat(absolute)
    except OSError:
        raise _input_invalid(rel_dir, "inspection") from None
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel_dir, "escape") from None
    if stat.S_ISLNK(lst.st_mode):
        # follow a redirecting include directory; the target must be a directory
        try:
            lst = _lstat(resolved)
        except OSError:
            raise _input_invalid(rel_dir, "inspection") from None
    if not stat.S_ISDIR(lst.st_mode):
        raise _input_invalid(rel_dir, "directory")
    try:
        names = sorted(_listdir(absolute))
    except OSError:
        raise _input_invalid(rel_dir, "inspection") from None
    for name in names:
        rel = f"{rel_dir}/{name}"
        child = absolute / name
        try:
            child_lst = _lstat(child)
        except OSError:
            raise _input_invalid(rel, "inspection") from None
        if stat.S_ISLNK(child_lst.st_mode):
            try:
                resolved_child = child.resolve(strict=False)
                resolved_child.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                raise _input_invalid(rel, "escape") from None
            try:
                target_lst = _lstat(resolved_child)
            except OSError:
                raise _input_invalid(rel, "inspection") from None
            if stat.S_ISDIR(target_lst.st_mode):
                _walk_include(
                    root,
                    rel,
                    paths,
                    declared_identities,
                    walked,
                    depth + 1,
                    explicit_walked,
                    explicit=False,
                )
            elif stat.S_ISREG(target_lst.st_mode):
                identity = (target_lst.st_dev, target_lst.st_ino)
                if rel in paths or identity in declared_identities:
                    continue
                paths.append(rel)
            else:
                raise _input_invalid(rel, "regularFile")
        elif stat.S_ISDIR(child_lst.st_mode):
            _walk_include(
                root,
                rel,
                paths,
                declared_identities,
                walked,
                depth + 1,
                explicit_walked,
                explicit=False,
            )
        elif stat.S_ISREG(child_lst.st_mode):
            identity = (child_lst.st_dev, child_lst.st_ino)
            if rel in paths or identity in declared_identities:
                continue
            paths.append(rel)
        else:
            raise _input_invalid(rel, "regularFile")


def casefold_collision(paths: list[str]) -> str | None:
    """Return the first duplicate or Unicode-casefold-colliding path, if any."""
    seen: dict[str, str] = {}
    for path in paths:
        folded = path.casefold()
        prior = seen.get(folded)
        if prior is not None and prior != path:
            return path
        seen[folded] = path
    return None


# ---------------------------------------------------------------------------
# git evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitEvidence:
    head: str
    dirty: bool


@dataclass(frozen=True)
class GitUnavailableEvidence:
    """Bounded, stable Git-unavailability diagnostics for a snapshot build.

    Only fixed public codes and rules are retained; no command output,
    exception text, or host path can reach the identity document.
    """

    rule: str
    status: str = GIT_DIAGNOSTIC_UNAVAILABLE
    code: str = BUILD_GIT_INVALID

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "code": self.code, "rule": self.rule}


def _git_invalid(rule: str) -> BuildError:
    return build_error(BUILD_GIT_INVALID, "git evidence is unavailable", {"rule": rule})


def _porcelain_dirty(stdout: str) -> bool:
    """Dirty iff a porcelain entry outside ``build/``/``artifacts/migration`` exists."""
    for chunk in stdout.split("\x00"):
        if not chunk:
            continue
        path = chunk[3:] if len(chunk) >= 4 and chunk[2] == " " else chunk
        if path.startswith("build/") or path.startswith("artifacts/migration"):
            continue
        return True
    return False


def git_evidence(project_root: Path, timeout_seconds: int = 30) -> GitEvidence:
    """Collect bounded fixed-argv Git evidence; failure is always stable."""
    try:
        head_result = run_process(
            ProcessRequest(
                argv=("git", "rev-parse", "--verify", "HEAD"),
                cwd=project_root,
                timeout_seconds=timeout_seconds,
            )
        )
    except ProcessError:
        raise _git_invalid("head") from None
    if head_result.timed_out or head_result.returncode != 0:
        raise _git_invalid("head")
    head = head_result.stdout.strip()
    if _FULL_SHA_RE.fullmatch(head) is None:
        raise _git_invalid("head")
    try:
        status_result = run_process(
            ProcessRequest(
                argv=("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
                cwd=project_root,
                timeout_seconds=timeout_seconds,
            )
        )
    except ProcessError:
        raise _git_invalid("status") from None
    if status_result.timed_out or status_result.returncode != 0:
        raise _git_invalid("status")
    return GitEvidence(head=head, dirty=_porcelain_dirty(status_result.stdout))


def collect_build_git_evidence(
    project_root: Path, timeout_seconds: int = 30
) -> GitEvidence | GitUnavailableEvidence:
    """Collect Git evidence for a build, tolerating availability failure only.

    The strict :func:`git_evidence` API is unchanged for existing consumers.
    This build-specific collector maps only its stable availability error to
    bounded diagnostics; any unexpected exception still propagates.
    """
    try:
        return git_evidence(project_root, timeout_seconds)
    except BuildError as error:
        if error.code != BUILD_GIT_INVALID:
            raise
        details = getattr(error, "details", None)
        rule = details.get("rule") if isinstance(details, dict) else None
        if not isinstance(rule, str) or rule not in _GIT_DIAGNOSTIC_RULES:
            # The fixed collector only reports these two phases.  Anything
            # else (including an unhashable JSON object) is treated as the
            # first unavailable phase so an arbitrary or unsafe detail can
            # never enter the identity document.
            rule = "head"
        return GitUnavailableEvidence(rule=rule)


def _valid_toolkit_version(value: object) -> bool:
    """A bounded, non-empty toolkit version string (never null or a boolean)."""
    return isinstance(value, str) and 1 <= len(value) <= 64


def validate_optional_provenance(record: object, identity: object) -> bool:
    """Check bounded agreement of the optional receipt/identity fields.

    A receipt ``toolkitVersion``, when present, must equal the identity's
    ``toolkitVersion``.  ``floatAbi`` must be absent from both or present in
    both with an identical, closed, non-blocked evidence object.  Absence in
    both remains fully supported for legacy records; a forged null, wrong
    type, arbitrary extra or one-sided evidence never agrees.
    """
    if not isinstance(record, dict) or not isinstance(identity, dict):
        return False
    if "toolkitVersion" in record:
        version = record["toolkitVersion"]
        if not _valid_toolkit_version(version) or version != identity.get(
            "toolkitVersion"
        ):
            return False
    if ("floatAbi" in record) != ("floatAbi" in identity):
        return False
    if "floatAbi" in record:
        try:
            record_evidence = validate_float_abi_evidence(record["floatAbi"])
            identity_evidence = validate_float_abi_evidence(identity["floatAbi"])
        except (TypeError, ValueError):
            return False
        if record_evidence != identity_evidence:
            return False
    return True


def validate_snapshot_build_result(
    record: object,
    *,
    preset: str,
    expected_artifact_paths: frozenset[str],
) -> bool:
    """Strictly validate one current schema-2 successful build record.

    Missing, extra, mistyped, forged-null, cross-schema, or malformed
    artifact fields fail closed.  ``dict.get`` alone is insufficient because
    a removed nullable field would compare equal to JSON null.  Only
    ``toolkitVersion`` and ``floatAbi`` may extend the required set, and each
    is validated strictly when present.
    """
    if not isinstance(record, dict):
        return False
    keys = set(record)
    if not SNAPSHOT_BUILD_RESULT_FIELDS <= keys:
        return False
    if keys - SNAPSHOT_BUILD_RESULT_FIELDS - BUILD_RESULT_OPTIONAL_FIELDS:
        return False
    if type(record["schemaVersion"]) is not int or record["schemaVersion"] != (
        SNAPSHOT_IDENTITY_SCHEMA_VERSION
    ):
        return False
    if record["status"] != "success" or record["stage"] != "" or record["code"] != "OK":
        return False
    if record["sourceBaseline"] != SOURCE_BASELINE_INPUT_SNAPSHOT:
        return False
    if record["gitHead"] is not None or record["gitDirty"] is not None:
        return False
    evidence = record["gitEvidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"status", "code", "rule"}:
        return False
    if (
        evidence.get("status") != GIT_DIAGNOSTIC_UNAVAILABLE
        or evidence.get("code") != BUILD_GIT_INVALID
    ):
        return False
    rule = evidence.get("rule")
    if not isinstance(rule, str) or rule not in _GIT_DIAGNOSTIC_RULES:
        # The guard precedes membership: JSON arrays/objects are unhashable
        # and must produce a stable invalid-record result, never TypeError.
        return False
    if not isinstance(record["buildId"], str) or _SHA256_RE.fullmatch(
        record["buildId"]
    ) is None:
        return False
    if not isinstance(record["inputSnapshotSha256"], str) or _SHA256_RE.fullmatch(
        record["inputSnapshotSha256"]
    ) is None:
        return False
    target = record["targetDevice"]
    if not isinstance(target, str) or not 1 <= len(target) <= 128:
        return False
    if record["preset"] != preset or preset not in SUPPORTED_PRESETS:
        return False
    for field in ("startedAtUtc", "finishedAtUtc"):
        if not isinstance(record[field], str) or not record[field]:
            return False
    if type(record["durationMs"]) is not int or record["durationMs"] < 0:
        return False
    artifacts = record["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 5:
        return False
    paths: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path"}:
            return False
        path = item["path"]
        if not isinstance(path, str) or not path:
            return False
        paths.append(path)
    if len(set(paths)) != len(paths) or set(paths) != set(expected_artifact_paths):
        return False
    if not isinstance(record["memory"], list) or not isinstance(record["warnings"], list):
        return False
    if "toolkitVersion" in record and not _valid_toolkit_version(
        record["toolkitVersion"]
    ):
        return False
    if "floatAbi" in record:
        try:
            validate_float_abi_evidence(record["floatAbi"])
        except (TypeError, ValueError):
            return False
    return True


# ---------------------------------------------------------------------------
# MAP reading
# ---------------------------------------------------------------------------


def read_map_text(path: Path, rel: str) -> str:
    """Read the MAP bounded to 32 MiB and decode strict UTF-8/ASCII text."""
    try:
        data = _read_limited(path, _MAP_LIMIT_BYTES)
    except FileNotFoundError:
        raise map_error("missing", rel) from None
    except OSError:
        raise map_error("unreadable", rel) from None
    if len(data) > _MAP_LIMIT_BYTES:
        raise map_error("size", rel)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise map_error("encoding", rel) from None


# ---------------------------------------------------------------------------
# ELF validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ElfEvidence:
    entry_point: int
    vector_address: int
    reset_handler_address: int
    sha256: str
    size: int
    sections: tuple[ElfSectionEvidence, ...]


def _artifact_invalid(rel: str, rule: str) -> BuildError:
    return build_error(
        BUILD_ARTIFACT_INVALID, "build artifact is invalid", {"path": rel, "rule": rule}
    )


def _in_region(addr: int, size: int, region: MemoryRegion) -> bool:
    return region.origin <= addr and addr + size <= region.origin + region.length


def _in_any_region(addr: int, size: int, model: ProjectModel) -> bool:
    return any(_in_region(addr, size, region) for region in model.memory.regions)


def _in_executable_region(addr: int, size: int, model: ProjectModel) -> bool:
    return any(
        "x" in region.attributes and _in_region(addr, size, region)
        for region in model.memory.regions
    )


def validate_elf(path: Path, model: ProjectModel) -> ElfEvidence:
    """Fail-closed ELF32 LE ARM validation over an already bounded buffer."""
    root = model.project_root
    rel = _relative_to_root(path, root)
    try:
        lst = _lstat(path)
    except FileNotFoundError:
        raise _artifact_invalid(rel, "missing") from None
    except OSError:
        raise _artifact_invalid(rel, "unreadable") from None
    if not stat.S_ISREG(lst.st_mode):
        raise _artifact_invalid(rel, "regularFile")
    try:
        data = _read_limited(path, _ELF_LIMIT_BYTES)
    except OSError:
        raise _artifact_invalid(rel, "unreadable") from None
    if len(data) > _ELF_LIMIT_BYTES:
        raise _artifact_invalid(rel, "size")
    if not data:
        raise _artifact_invalid(rel, "empty")
    try:
        elffile = ELFFile(io.BytesIO(data))
        return _inspect_elf(elffile, rel, model, data)
    except BuildError:
        raise
    except (ELFError, ValueError, KeyError, IndexError, struct.error) as error:
        raise _artifact_invalid(rel, "format") from error


def _inspect_elf(elffile: ELFFile, rel: str, model: ProjectModel, data: bytes) -> ElfEvidence:
    ident = elffile.header["e_ident"]
    if ident.get("EI_CLASS") != "ELFCLASS32":
        raise _artifact_invalid(rel, "class")
    if ident.get("EI_DATA") != "ELFDATA2LSB":
        raise _artifact_invalid(rel, "endian")
    if elffile.header.get("e_machine") != _ARM_MACHINE:
        raise _artifact_invalid(rel, "machine")

    vector = elffile.get_section_by_name(".isr_vector")
    if vector is None:
        raise _artifact_invalid(rel, "vector")
    vector_size = vector["sh_size"]
    if vector_size < 8:
        raise _artifact_invalid(rel, "vectorSize")
    if not vector["sh_flags"] & _SHF_ALLOC:
        raise _artifact_invalid(rel, "vectorAlloc")
    vector_addr = vector["sh_addr"]
    if not _in_executable_region(vector_addr, vector_size, model):
        raise _artifact_invalid(rel, "vectorRegion")
    vector_bytes = vector.data()[:8]
    vector_word = int.from_bytes(vector_bytes[4:8], "little")

    symtab = elffile.get_section_by_name(".symtab")
    if symtab is None:
        raise _artifact_invalid(rel, "symbols")
    reset_handler_addr: int | None = None
    for symbol in symtab.iter_symbols():
        if symbol.name == "Reset_Handler":
            if symbol["st_shndx"] == _SHN_UNDEF:
                raise _artifact_invalid(rel, "resetHandlerUndefined")
            reset_handler_addr = symbol["st_value"]
    if reset_handler_addr is None:
        raise _artifact_invalid(rel, "resetHandler")

    entry = elffile.header["e_entry"]
    if entry & 1 == 0:
        raise _artifact_invalid(rel, "entryThumb")
    if entry & ~1 != reset_handler_addr & ~1:
        raise _artifact_invalid(rel, "entry")
    if vector_word & ~1 != reset_handler_addr & ~1:
        raise _artifact_invalid(rel, "vectorReset")

    for symbol in symtab.iter_symbols():
        if symbol["st_shndx"] != _SHN_UNDEF:
            continue
        if not symbol.name:
            continue
        if symbol["st_info"]["bind"] != _STB_WEAK:
            raise _artifact_invalid(rel, "undefinedSymbols")

    section_evidence: list[ElfSectionEvidence] = []
    for section in elffile.iter_sections():
        size = section["sh_size"]
        if size == 0:
            continue
        alloc = bool(section["sh_flags"] & _SHF_ALLOC)
        nobits = section["sh_type"] == "SHT_NOBITS"
        addr = section["sh_addr"]
        if not alloc:
            section_evidence.append(
                ElfSectionEvidence(name=section.name, address=addr, size=size, alloc=False, nobits=nobits)
            )
            continue
        if not _in_any_region(addr, size, model):
            raise _artifact_invalid(rel, "sectionOutOfRange")
        fixed = _FIXED_SECTION_RE.fullmatch(section.name)
        if fixed is not None and addr != int(fixed.group(1), 16):
            raise _artifact_invalid(rel, "fixedSectionAddress")
        section_evidence.append(
            ElfSectionEvidence(name=section.name, address=addr, size=size, alloc=True, nobits=nobits)
        )

    _validate_fragment_elf(rel, model, section_evidence)

    return ElfEvidence(
        entry_point=entry,
        vector_address=vector_addr,
        reset_handler_address=reset_handler_addr,
        sha256=sha256_hex(data),
        size=len(data),
        sections=tuple(section_evidence),
    )


def _validate_fragment_elf(
    rel: str, model: ProjectModel, sections: list[ElfSectionEvidence]
) -> None:
    """Validate materialized fragment sections and allocated-section overlap.

    A selector that matches no input may legitimately leave no output
    section, so only nonempty materialized sections are required to exist.
    Every nonempty section carrying a declared name must be allocated; a
    non-allocated materialization is refused rather than silently skipped.
    Each allocated one must be an ``SHT_NOBITS`` section placed in its
    declared writable region (and exactly at an explicit address).  Because
    the GNU MAP accounts interval unions, it cannot prove non-overlap; for a
    fragment project every nonempty allocated ELF section must therefore have
    a disjoint VMA interval from every other nonempty allocated section.
    """
    fragment = model.generation.linker_fragment
    if fragment is None:
        return
    regions = {region.name: region for region in model.memory.regions}
    declared = {section.name: section for section in fragment.sections}
    allocated = [
        section
        for section in sections
        if section.alloc and section.size > 0
    ]
    # Inspect every nonempty section, not only the allocated evidence: a
    # declared custom section whose SHF_ALLOC bit was cleared must fail the
    # contract instead of disappearing from the allocated subset.
    for evidence in sections:
        if evidence.size <= 0:
            continue
        expected = declared.get(evidence.name)
        if expected is None:
            continue
        if not evidence.alloc:
            raise _artifact_invalid(rel, "fragmentNotAllocated")
        if not evidence.nobits:
            raise _artifact_invalid(rel, "fragmentLoadable")
        region = regions.get(expected.region)
        if region is None or "w" not in region.attributes:
            raise _artifact_invalid(rel, "fragmentRegion")
        end = evidence.address + evidence.size
        if (
            evidence.address < region.origin
            or end > region.origin + region.length
        ):
            raise _artifact_invalid(rel, "fragmentOutOfRange")
        if expected.address is not None and evidence.address != expected.address:
            raise _artifact_invalid(rel, "fragmentAddress")
    if len(allocated) > _FRAGMENT_ALLOCATED_SECTION_LIMIT:
        raise _artifact_invalid(rel, "fragmentSectionCount")
    previous_end: int | None = None
    for evidence in sorted(
        allocated, key=lambda item: (item.address, item.size, item.name)
    ):
        if previous_end is not None and evidence.address < previous_end:
            raise _artifact_invalid(rel, "fragmentOverlap")
        end = evidence.address + evidence.size
        previous_end = end if previous_end is None else max(previous_end, end)


# ---------------------------------------------------------------------------
# identity construction and schema validation
# ---------------------------------------------------------------------------


def compute_build_id(document: dict) -> str:
    """Hash every identity field except ``schemaVersion``/``buildId``/``builtAtUtc``."""
    fields = {
        key: value
        for key, value in document.items()
        if key not in ("schemaVersion", "buildId", "builtAtUtc")
    }
    return sha256_hex(canonical_json_bytes(fields))


def build_identity_document(
    *,
    model: ProjectModel,
    preset: str,
    snapshot: InputSnapshot,
    elf: ElfEvidence,
    elf_size: int,
    elf_sha256: str,
    map_size: int,
    map_sha256: str,
    built_at_utc: str,
    git: GitEvidence | None = None,
    git_unavailable: GitUnavailableEvidence | None = None,
    memory_summary: MemorySummary | None = None,
    float_abi: dict[str, object] | None = None,
) -> dict:
    """Construct a schema-1 Git or schema-2 input-snapshot identity.

    Exactly one provenance source must be supplied.  A Git-backed build keeps
    the exact schema-1 key order and field bytes; an unavailable Git result
    emits schema 2 with ``sourceBaseline`` and explicit null Git fields plus
    bounded diagnostics.  A synthetic commit hash is never produced.
    """
    if (git is None) == (git_unavailable is None):
        raise ValueError("exactly one Git provenance source is required")
    elf_rel, map_rel = model_artifact_paths(model, preset)
    if git is not None:
        document = {
            "schemaVersion": IDENTITY_SCHEMA_VERSION,
            "buildId": "",
            "logicalProjectId": str(model.logical_project_id),
            "toolkitVersion": __version__,
            "gitHead": git.head,
            "gitDirty": git.dirty,
            "inputSnapshotSha256": snapshot.sha256,
            "newestInputMtimeNs": snapshot.newest_mtime_ns,
            "targetDevice": model.target.device,
            "preset": preset,
            "elfPath": elf_rel,
            "elfSha256": elf_sha256,
            "elfSize": elf_size,
            "mapPath": map_rel,
            "mapSha256": map_sha256,
            "entryPoint": elf.entry_point,
            "vectorAddress": elf.vector_address,
            "resetHandlerAddress": elf.reset_handler_address,
            "builtAtUtc": built_at_utc,
        }
    else:
        assert git_unavailable is not None
        document = {
            "schemaVersion": SNAPSHOT_IDENTITY_SCHEMA_VERSION,
            "buildId": "",
            "logicalProjectId": str(model.logical_project_id),
            "toolkitVersion": __version__,
            "sourceBaseline": SOURCE_BASELINE_INPUT_SNAPSHOT,
            "gitHead": None,
            "gitDirty": None,
            "gitEvidence": git_unavailable.to_dict(),
            "inputSnapshotSha256": snapshot.sha256,
            "newestInputMtimeNs": snapshot.newest_mtime_ns,
            "targetDevice": model.target.device,
            "preset": preset,
            "elfPath": elf_rel,
            "elfSha256": elf_sha256,
            "elfSize": elf_size,
            "mapPath": map_rel,
            "mapSha256": map_sha256,
            "entryPoint": elf.entry_point,
            "vectorAddress": elf.vector_address,
            "resetHandlerAddress": elf.reset_handler_address,
            "builtAtUtc": built_at_utc,
        }
    if snapshot.policy == SOURCE_LOCAL_HEADERS_POLICY:
        document["inputDiscoveryPolicy"] = SOURCE_LOCAL_HEADERS_POLICY
    if memory_summary is not None:
        document["memorySummary"] = memory_summary.to_dict()
    if float_abi is not None:
        # Present evidence participates in the identity hash exactly like any
        # other identity field; absent evidence keeps the historical hash.
        document["floatAbi"] = dict(float_abi)
    document["buildId"] = compute_build_id(document)
    return document


def load_packaged_schema_bytes() -> bytes:
    resource = importlib.resources.files("stm32_toolkit").joinpath(
        "schemas", "firmware-identity.schema.json"
    )
    return resource.read_bytes()


def load_packaged_schema() -> dict:
    return json.loads(load_packaged_schema_bytes().decode("utf-8"))


_IDENTITY_VALIDATOR: Draft202012Validator | None = None


def _identity_validator() -> Draft202012Validator:
    global _IDENTITY_VALIDATOR
    if _IDENTITY_VALIDATOR is None:
        schema = load_packaged_schema()
        Draft202012Validator.check_schema(schema)
        _IDENTITY_VALIDATOR = Draft202012Validator(schema)
    return _IDENTITY_VALIDATOR


def validate_identity_document(document: dict) -> None:
    """Validate the identity against the packaged schema; fail closed.

    Optional ``memorySummary`` and ``floatAbi`` evidence is additionally
    validated for semantics, not just schema shape.
    """
    try:
        validator = _identity_validator()
        errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    except Exception:
        raise build_error(
            BUILD_EVIDENCE_FAILED,
            "identity evidence is invalid",
            {"phase": "identity"},
        ) from None
    if errors:
        raise build_error(
            BUILD_EVIDENCE_FAILED,
            "identity evidence is invalid",
            {"phase": "identity"},
        )
    if "memorySummary" in document:
        try:
            MemorySummary.from_document(document["memorySummary"])
        except (MemorySummaryError, TypeError, ValueError, KeyError):
            raise build_error(
                BUILD_EVIDENCE_FAILED,
                "identity evidence is invalid",
                {"phase": "identity"},
            ) from None
    if "floatAbi" in document:
        # Schema shape is not enough: the evidence validator also reconstructs
        # the deterministic resolver decision from the recorded raw fields, so
        # a relabelled or hand-edited ABI record fails closed here.
        try:
            validate_float_abi_evidence(document["floatAbi"])
        except (TypeError, ValueError):
            raise build_error(
                BUILD_EVIDENCE_FAILED,
                "identity evidence is invalid",
                {"phase": "identity"},
            ) from None


# ---------------------------------------------------------------------------
# atomic evidence publication
# ---------------------------------------------------------------------------


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via unique sibling temp + flush + fsync + replace + dir fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".build-", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            _fsync_file(handle.fileno())
        _replace(tmp_path, str(path))
        tmp_path = None
        _sync_directory(path.parent)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def atomic_write_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


def read_evidence_json(path: Path, rel: str, limit: int) -> dict | None:
    """Read and strictly parse an evidence JSON file; ``None`` when invalid."""
    try:
        data = _read_limited(path, limit)
    except OSError:
        return None
    if len(data) > limit:
        return None
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def hash_artifact(path: Path, rel: str, limit: int, code: str) -> tuple[int, str]:
    """Hash exact artifact bytes after validation; reject oversized evidence."""
    data = read_bounded(path, limit)
    if len(data) > limit:
        raise build_error(code, "build artifact is invalid", {"path": rel, "rule": "size"})
    return len(data), sha256_hex(data)
