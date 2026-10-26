"""Independent, Git-free Keil-to-GCC delivery into a new output directory.

The source is an existing canonical directory that is never modified.  The
destination is an explicit absolute directory outside it whose parent exists;
it must be absent or verified empty.  Planning inventories the complete
bounded regular-file source tree (excluding only ``.git``), overlays the
reviewed conversion patches and the generated Keil-to-GCC configuration in
memory, and binds the source snapshot, destination state, options and every
final output digest into a deterministic plan ID.  Planning writes nothing.

Apply requires explicit authorization and the exact freshly recomputed plan
ID, revalidates the source snapshot, destination state and options, stages
only in a newly created owned sibling of the destination, and publishes one
complete directory.  The original source is never touched and a nonempty
destination is never overwritten.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.generation.configure import render_new_project_configuration
from stm32_toolkit.generation.managed_files import (
    MANAGED_MANIFEST_PATH,
    GenerationError,
    portable_sort_key,
)
from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.migration.model import (
    FilePatch,
    IncludeMerge,
    MigrationPlanError,
    StartupOptions,
    canonical_json_bytes,
    inspection_sha256_for,
    portable_path_error,
    sha256_error,
)
from stm32_toolkit.migration.planner import (
    ConversionAnalysis,
    _validate_extra_region_option,
    _validate_memory_layout,
    _validate_startup_options,
    analyze_keil_conversion,
)
from stm32_toolkit.project_model import ProjectManifestError, load_project_model_candidate
from stm32_toolkit.result import OperationResult

_PLAN_VERSION = 1
_MANIFEST_NAME = ".stm32-project.json"
_CONVERSION_REPORT_PATH = "artifacts/migration/conversion-report.json"

#: Bounds for the complete source inventory.  A tree beyond any bound is a
#: stable refusal, never a silently partial copy.
_MAX_DEPTH = 64
_MAX_FILES = 20000
_MAX_DIRECTORIES = 5000
_FILE_LIMIT_BYTES = 8 * 1024 * 1024
_AGGREGATE_LIMIT_BYTES = 64 * 1024 * 1024
_PLAN_LIMIT_BYTES = 64 * 1024 * 1024

_EXCLUDED_ENTRY = ".git"
_REPARSE_POINT_ATTRIBUTE = 0x400
_STAGING_SUFFIX = ".stm32tk-staging-"

_SOURCE_SNAPSHOT_FORMAT = "stm32tk-source-snapshot/1"
_OUTPUT_SNAPSHOT_FORMAT = "stm32tk-output-snapshot/1"
_ANALYSIS_FORMAT = "stm32tk-delivery-analysis/1"
_CONTENT_FORMAT = "stm32tk-delivery-content/1"

_FOLLOW_UP = (
    "Bind the new output root and use the normal GCC configure/build route."
    " Configuration output is not a successful build or flash."
)


def _raise(code: str, message: str, details: dict[str, object]) -> MigrationPlanError:
    return MigrationPlanError(code, message, details)


def _is_redirect(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# immutable inventory and output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SourceFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class _Inventory:
    root: Path
    files: tuple[_SourceFile, ...]
    directories: tuple[str, ...]
    data: dict[str, bytes] = field(repr=False)
    total_bytes: int = 0
    excluded: int = 0

    @property
    def snapshot_sha256(self) -> str:
        return _snapshot_sha256(
            _SOURCE_SNAPSHOT_FORMAT,
            self.files,
            self.directories,
        )


@dataclass(frozen=True)
class _PlannedOutput:
    path: str
    kind: str  # copied, replaced, or generated
    data: bytes = field(repr=False)
    before_data: bytes | None = field(default=None, repr=False)
    collision: bool = False

    @property
    def sha256(self) -> str:
        return _sha256(self.data)

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class DeliveryOutput:
    """One final output, described by digest/size rather than raw content."""

    path: str
    kind: str
    sha256: str
    size: int
    before_sha256: str | None
    before_size: int | None
    collision: bool
    binary: bool = False
    unified_diff: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "sha256": self.sha256,
            "size": self.size,
            "beforeSha256": self.before_sha256,
            "beforeSize": self.before_size,
            "collision": self.collision,
            "binary": self.binary,
            "unifiedDiff": self.unified_diff,
        }


@dataclass(frozen=True)
class DeliveryPlan:
    """Deterministic, read-only plan for one independent output directory."""

    source_root: Path
    destination_root: Path
    inspection: KeilInspection
    plan_version: int
    plan_id: str
    content_id: str
    destination_state: str  # absent or empty
    source_snapshot_sha256: str
    output_snapshot_sha256: str
    outputs: tuple[DeliveryOutput, ...]
    output_directories: tuple[str, ...]
    source_patches: tuple[FilePatch, ...]
    source_file_count: int
    source_directory_count: int
    source_total_bytes: int
    excluded_git_entries: int
    report_path: str
    report_sha256: str
    managed_manifest_path: str
    managed_manifest_sha256: str
    startup_options: StartupOptions | None
    memory_layout: MemoryLayout | None
    extra_regions: tuple[ExtraRegion, ...]
    include_merges: tuple[IncludeMerge, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "planVersion": self.plan_version,
            "planId": self.plan_id,
            "contentId": self.content_id,
            "sourceRoot": str(self.source_root),
            "destination": str(self.destination_root),
            "destinationState": self.destination_state,
            "sourceSnapshotSha256": self.source_snapshot_sha256,
            "outputSnapshotSha256": self.output_snapshot_sha256,
            "inspection": {
                "projectFile": self.inspection.project_file,
                "targetName": self.inspection.target_name,
                "device": self.inspection.device,
                "compiler": self.inspection.compiler,
            },
            "options": {
                "startupOptions": (
                    self.startup_options.to_dict()
                    if self.startup_options is not None
                    else None
                ),
                "memoryLayout": (
                    self.memory_layout.to_dict()
                    if self.memory_layout is not None
                    else None
                ),
                "extraRegions": [region.to_dict() for region in self.extra_regions],
            },
            "inventory": {
                "files": self.source_file_count,
                "directories": self.source_directory_count,
                "bytes": self.source_total_bytes,
                "excludedGitEntries": self.excluded_git_entries,
                "limits": {
                    "depth": _MAX_DEPTH,
                    "files": _MAX_FILES,
                    "directories": _MAX_DIRECTORIES,
                    "fileBytes": _FILE_LIMIT_BYTES,
                    "aggregateBytes": _AGGREGATE_LIMIT_BYTES,
                },
            },
            "outputs": [output.to_dict() for output in self.outputs],
            "outputDirectories": list(self.output_directories),
            "counts": {
                "copied": sum(1 for output in self.outputs if output.kind == "copied"),
                "replaced": sum(1 for output in self.outputs if output.kind == "replaced"),
                "generated": sum(1 for output in self.outputs if output.kind == "generated"),
            },
            "sourcePatches": [patch.to_dict() for patch in self.source_patches],
            "reportPath": self.report_path,
            "reportSha256": self.report_sha256,
            "managedManifestPath": self.managed_manifest_path,
            "managedManifestSha256": self.managed_manifest_sha256,
            "warnings": list(self.warnings),
            # Planning never builds or flashes, and generated configuration is
            # not build evidence.
            "configured": False,
            "built": False,
            "flashed": False,
            "followUp": _FOLLOW_UP,
        }
        if self.include_merges:
            payload["includeMerges"] = [
                merge.to_report_dict() for merge in self.include_merges
            ]
        return payload


# ---------------------------------------------------------------------------
# canonical digests
# ---------------------------------------------------------------------------


def _snapshot_sha256(
    format_name: str,
    files: tuple[_SourceFile, ...],
    directories: tuple[str, ...],
) -> str:
    return _sha256(
        canonical_json_bytes(
            {
                "format": format_name,
                "directories": list(directories),
                "files": [
                    {
                        "path": entry.path,
                        "sha256": entry.sha256,
                        "size": entry.size,
                    }
                    for entry in files
                ],
            }
        )
    )


def _output_snapshot_sha256(
    outputs: tuple[tuple[str, str, int], ...], directories: tuple[str, ...]
) -> str:
    files = tuple(
        _SourceFile(path=path, sha256=digest, size=size)
        for path, digest, size in outputs
    )
    return _snapshot_sha256(_OUTPUT_SNAPSHOT_FORMAT, files, directories)


def _analysis_id(
    destination: str,
    destination_state: str,
    source_snapshot_sha256: str,
    inspection_sha256: str,
    analysis: ConversionAnalysis,
    options: dict[str, object],
    patches: tuple[FilePatch, ...],
) -> str:
    return _sha256(
        canonical_json_bytes(
            {
                "format": _ANALYSIS_FORMAT,
                "toolkitVersion": __version__,
                "destination": destination,
                "destinationState": destination_state,
                "sourceSnapshotSha256": source_snapshot_sha256,
                "inspectionSha256": inspection_sha256,
                "target": {
                    "projectFile": analysis.inspection.project_file,
                    "targetName": analysis.inspection.target_name,
                    "device": analysis.inspection.device,
                },
                "options": options,
                "patches": [
                    {
                        "path": patch.path,
                        "before_sha256": patch.before_sha256,
                        "after_sha256": patch.after_sha256,
                        "rule_ids": list(patch.rule_ids),
                    }
                    for patch in patches
                ],
            }
        )
    )


def _normalized_destination(destination: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(destination)))


# ---------------------------------------------------------------------------
# bounded source inventory
# ---------------------------------------------------------------------------


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def _scan_tree(root: Path, *, exclude_git: bool = True) -> _Inventory:
    """Read the complete bounded regular-file tree below ``root``.

    Only ``.git`` entries are excluded when ``exclude_git`` is true (source
    inventory).  Output/staging verification passes ``exclude_git=False`` so a
    Git directory can never be silently omitted from the verified snapshot.
    Links/reparse points, special files, casefold collisions, and every
    exceeded bound are stable refusals.
    """
    files: list[_SourceFile] = []
    directories: list[str] = []
    data: dict[str, bytes] = {}
    total = 0
    excluded = 0

    def walk(directory: Path, relative: str, depth: int) -> None:
        nonlocal total, excluded
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(list(iterator), key=lambda entry: entry.name)
        except OSError:
            raise _raise(
                "DELIVERY_SOURCE_INVALID",
                "source directory is unreadable",
                {"path": relative or ".", "rule": "unreadable"},
            ) from None
        for entry in entries:
            name = entry.name
            if exclude_git and name == _EXCLUDED_ENTRY:
                excluded += 1
                continue
            child = name if not relative else f"{relative}/{name}"
            if portable_path_error(child) is not None:
                raise _raise(
                    "DELIVERY_SOURCE_INVALID",
                    "source path is not portable",
                    {"path": child, "rule": "portablePath"},
                )
            absolute = Path(entry.path)
            try:
                st = os.lstat(absolute)
            except OSError:
                raise _raise(
                    "DELIVERY_SOURCE_INVALID",
                    "source entry is unreadable",
                    {"path": child, "rule": "unreadable"},
                ) from None
            if _is_redirect(st):
                raise _raise(
                    "DELIVERY_LINK_UNSUPPORTED",
                    "source links and reparse points are not supported",
                    {"path": child, "rule": "link"},
                )
            if stat.S_ISDIR(st.st_mode):
                if depth + 1 > _MAX_DEPTH:
                    raise _raise(
                        "DELIVERY_LIMIT_EXCEEDED",
                        "source tree exceeds the depth limit",
                        {"scope": "depth", "limit": _MAX_DEPTH},
                    )
                if len(directories) >= _MAX_DIRECTORIES:
                    raise _raise(
                        "DELIVERY_LIMIT_EXCEEDED",
                        "source tree exceeds the directory limit",
                        {"scope": "directories", "limit": _MAX_DIRECTORIES},
                    )
                directories.append(child)
                walk(absolute, child, depth + 1)
                continue
            if not stat.S_ISREG(st.st_mode):
                raise _raise(
                    "DELIVERY_UNSUPPORTED_ENTRY",
                    "source entry is not a regular file or directory",
                    {"path": child, "rule": "regularFile"},
                )
            if len(files) >= _MAX_FILES:
                raise _raise(
                    "DELIVERY_LIMIT_EXCEEDED",
                    "source tree exceeds the file-count limit",
                    {"scope": "files", "limit": _MAX_FILES},
                )
            if st.st_size > _FILE_LIMIT_BYTES:
                raise _raise(
                    "DELIVERY_LIMIT_EXCEEDED",
                    "source file exceeds the per-file limit",
                    {"scope": "file", "limitBytes": _FILE_LIMIT_BYTES, "path": child},
                )
            if total + st.st_size > _AGGREGATE_LIMIT_BYTES:
                raise _raise(
                    "DELIVERY_LIMIT_EXCEEDED",
                    "source tree exceeds the aggregate byte limit",
                    {
                        "scope": "aggregate",
                        "limitBytes": _AGGREGATE_LIMIT_BYTES,
                        "path": child,
                    },
                )
            try:
                content = _read_limited(absolute, _FILE_LIMIT_BYTES)
            except OSError:
                raise _raise(
                    "DELIVERY_SOURCE_INVALID",
                    "source file is unreadable",
                    {"path": child, "rule": "unreadable"},
                ) from None
            if len(content) > _FILE_LIMIT_BYTES:
                raise _raise(
                    "DELIVERY_LIMIT_EXCEEDED",
                    "source file exceeds the per-file limit",
                    {"scope": "file", "limitBytes": _FILE_LIMIT_BYTES, "path": child},
                )
            total += len(content)
            if total > _AGGREGATE_LIMIT_BYTES:
                raise _raise(
                    "DELIVERY_LIMIT_EXCEEDED",
                    "source tree exceeds the aggregate byte limit",
                    {"scope": "aggregate", "limitBytes": _AGGREGATE_LIMIT_BYTES},
                )
            digest = _sha256(content)
            if child in data:
                raise _raise(
                    "DELIVERY_CASEFOLD_COLLISION",
                    "source paths collide after case folding",
                    {"path": child, "rule": "casefoldCollision"},
                )
            data[child] = content
            files.append(_SourceFile(path=child, sha256=digest, size=len(content)))

    walk(root, "", 0)

    ordered_files = tuple(sorted(files, key=lambda entry: portable_sort_key(entry.path)))
    ordered_directories = tuple(
        sorted(directories, key=portable_sort_key)
    )
    _reject_casefold([entry.path for entry in ordered_files], "source")
    _reject_casefold(list(ordered_directories), "source")
    combined = [entry.path for entry in ordered_files] + list(ordered_directories)
    _reject_casefold(combined, "source", skip_equal=True)
    return _Inventory(
        root=root,
        files=ordered_files,
        directories=ordered_directories,
        data=data,
        total_bytes=total,
        excluded=excluded,
    )


def _reject_casefold(
    paths: list[str], scope: str, *, skip_equal: bool = False
) -> None:
    seen: dict[str, str] = {}
    for path in paths:
        folded = path.casefold()
        prior = seen.get(folded)
        if prior is not None and not (skip_equal and prior == path):
            raise _raise(
                "DELIVERY_CASEFOLD_COLLISION",
                "paths collide after case folding",
                {"path": path, "collision": prior, "scope": scope},
            )
        seen[folded] = path


# ---------------------------------------------------------------------------
# source and destination roots
# ---------------------------------------------------------------------------


def _canonical_source(source: object) -> Path:
    if not isinstance(source, Path) or "\x00" in os.fspath(source):
        raise _raise(
            "DELIVERY_ROOT_INVALID",
            "source root must be an existing directory",
            {"field": "sourceRoot", "rule": "directory"},
        )
    try:
        canonical = source.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "DELIVERY_ROOT_INVALID",
            "source root is unavailable",
            {"field": "sourceRoot", "rule": "directory"},
        ) from None
    if not canonical.is_dir():
        raise _raise(
            "DELIVERY_ROOT_INVALID",
            "source root must be an existing directory",
            {"field": "sourceRoot", "rule": "directory"},
        )
    return canonical


def _absolute_destination(destination: object) -> Path:
    if not isinstance(destination, Path) or not destination.is_absolute():
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination must be an explicit absolute directory",
            {"field": "destination", "rule": "absolute"},
        )
    if "\x00" in os.fspath(destination):
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination is invalid",
            {"field": "destination", "rule": "directory"},
        )
    return Path(os.path.abspath(os.path.expanduser(os.fspath(destination))))


def _reject_disjoint(source: Path, destination: Path) -> None:
    source_text = os.path.normcase(str(source))
    destination_text = os.path.normcase(str(destination))
    if (
        destination_text == source_text
        or destination_text.startswith(source_text + os.sep)
        or source_text.startswith(destination_text + os.sep)
    ):
        raise _raise(
            "DELIVERY_SOURCE_DESTINATION_OVERLAP",
            "source and destination must be disjoint directories",
            {"field": "destination", "rule": "disjoint"},
        )


def _validate_existing_components(path: Path) -> None:
    """Reject links/reparse points and non-directories in existing components."""
    anchor = Path(path.anchor)
    parts = path.parts[1:] if path.anchor else path.parts
    current = anchor
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return
        except OSError:
            raise _raise(
                "DELIVERY_DESTINATION_INVALID",
                "destination path is unavailable",
                {"field": "destination", "rule": "directory"},
            ) from None
        if _is_redirect(st):
            raise _raise(
                "DELIVERY_DESTINATION_INVALID",
                "destination must not redirect",
                {"field": "destination", "rule": "link"},
            )
        terminal = index == len(parts) - 1
        if not terminal and not stat.S_ISDIR(st.st_mode):
            raise _raise(
                "DELIVERY_DESTINATION_INVALID",
                "destination parent is not a directory",
                {"field": "destination", "rule": "directory"},
            )


def _inspect_destination(destination: Path) -> str:
    try:
        st = os.lstat(destination)
    except FileNotFoundError:
        return "absent"
    except NotADirectoryError:
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination parent is not a directory",
            {"field": "destination", "rule": "directory"},
        ) from None
    except OSError:
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination state cannot be verified",
            {"field": "destination", "rule": "directory"},
        ) from None
    if _is_redirect(st):
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination must not redirect",
            {"field": "destination", "rule": "link"},
        )
    if not stat.S_ISDIR(st.st_mode):
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination must be a directory",
            {"field": "destination", "rule": "directory"},
        )
    try:
        with os.scandir(destination) as iterator:
            entries = list(iterator)
    except OSError:
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination state cannot be verified",
            {"field": "destination", "rule": "directory"},
        ) from None
    if entries:
        raise _raise(
            "DELIVERY_DESTINATION_EXISTS",
            "destination already contains files",
            {"field": "destination", "rule": "empty"},
        )
    return "empty"


def _planning_destination(destination: Path) -> str:
    if not destination.parent.is_dir():
        raise _raise(
            "DELIVERY_DESTINATION_INVALID",
            "destination parent must be an existing directory",
            {"field": "destination", "rule": "parent"},
        )
    _validate_existing_components(destination.parent)
    return _inspect_destination(destination)


# ---------------------------------------------------------------------------
# in-memory overlay
# ---------------------------------------------------------------------------


def _overlay_patches(
    inventory: _Inventory, patches: tuple[FilePatch, ...]
) -> dict[str, _PlannedOutput]:
    outputs: dict[str, _PlannedOutput] = {
        entry.path: _PlannedOutput(path=entry.path, kind="copied", data=inventory.data[entry.path])
        for entry in inventory.files
    }
    for patch in patches:
        existing = outputs.get(patch.path)
        if patch.before_bytes is None:
            if existing is None:
                outputs[patch.path] = _PlannedOutput(
                    path=patch.path, kind="generated", data=patch.after_bytes
                )
                continue
            # A proposed new file at an existing source path is an explicit
            # replacement, never a silent overwrite.
            before = existing.data
        else:
            if existing is None or existing.data != patch.before_bytes:
                raise _raise(
                    "DELIVERY_SOURCE_CHANGED",
                    "conversion patch no longer matches the source inventory",
                    {"path": patch.path},
                )
            before = existing.data
        outputs[patch.path] = _PlannedOutput(
            path=patch.path,
            kind="replaced",
            data=patch.after_bytes,
            before_data=before,
            collision=existing.collision if existing is not None else False,
        )
    return outputs


def _add_generated(
    outputs: dict[str, _PlannedOutput], path: str, data: bytes
) -> None:
    existing = outputs.get(path)
    if existing is None:
        outputs[path] = _PlannedOutput(path=path, kind="generated", data=data)
        return
    if existing.data == data:
        outputs[path] = _PlannedOutput(
            path=path,
            kind=existing.kind,
            data=data,
            before_data=existing.before_data,
            collision=True,
        )
        return
    outputs[path] = _PlannedOutput(
        path=path,
        kind="replaced",
        data=data,
        before_data=existing.data,
        collision=True,
    )


def _output_directories(
    inventory: _Inventory, outputs: dict[str, _PlannedOutput]
) -> tuple[str, ...]:
    directories = set(inventory.directories)
    for path in outputs:
        parts = path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("/".join(parts[:index]))
    return tuple(sorted(directories, key=portable_sort_key))


def _validate_output_bounds(
    outputs: tuple[_PlannedOutput, ...], directories: tuple[str, ...]
) -> None:
    """Refuse at planning time any output the published verifier would refuse.

    The same module bounds apply to the staged/published scan, so a source
    tree near a limit cannot plan an output that validation later rejects
    after staging.
    """
    if len(outputs) > _MAX_FILES:
        raise _raise(
            "DELIVERY_LIMIT_EXCEEDED",
            "final output exceeds the file-count limit",
            {"scope": "output-files", "limit": _MAX_FILES},
        )
    total = 0
    for output in outputs:
        if output.size > _FILE_LIMIT_BYTES:
            raise _raise(
                "DELIVERY_LIMIT_EXCEEDED",
                "final output file exceeds the per-file limit",
                {
                    "scope": "output-file",
                    "limitBytes": _FILE_LIMIT_BYTES,
                    "path": output.path,
                },
            )
        total += output.size
        if total > _AGGREGATE_LIMIT_BYTES:
            raise _raise(
                "DELIVERY_LIMIT_EXCEEDED",
                "final output exceeds the aggregate byte limit",
                {
                    "scope": "output-aggregate",
                    "limitBytes": _AGGREGATE_LIMIT_BYTES,
                    "path": output.path,
                },
            )
    if len(directories) > _MAX_DIRECTORIES:
        raise _raise(
            "DELIVERY_LIMIT_EXCEEDED",
            "final output exceeds the directory limit",
            {"scope": "output-directories", "limit": _MAX_DIRECTORIES},
        )
    for path in [output.path for output in outputs] + list(directories):
        if len(path.split("/")) > _MAX_DEPTH:
            raise _raise(
                "DELIVERY_LIMIT_EXCEEDED",
                "final output exceeds the depth limit",
                {"scope": "output-depth", "limit": _MAX_DEPTH, "path": path},
            )


def _reject_output_conflicts(
    outputs: tuple[_PlannedOutput, ...], directories: tuple[str, ...]
) -> None:
    """A path cannot be both a file and a directory in the final output."""
    files = {output.path for output in outputs}
    directories_set = set(directories)
    for output in outputs:
        if output.path in directories_set:
            raise _raise(
                "DELIVERY_OUTPUT_INVALID",
                "output path is both a file and a directory",
                {"path": output.path, "rule": "conflict"},
            )
        parts = output.path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            parent = "/".join(parts[:index])
            if parent in files:
                raise _raise(
                    "DELIVERY_OUTPUT_INVALID",
                    "output file path collides with a directory path",
                    {"path": output.path, "collision": parent, "rule": "conflict"},
                )
    for directory in directories:
        if directory in files:
            raise _raise(
                "DELIVERY_OUTPUT_INVALID",
                "output directory path collides with a file path",
                {"path": directory, "rule": "conflict"},
            )


def _unified_diff(path: str, before: bytes, after: bytes) -> tuple[bool, str]:
    try:
        before_text = before.decode("utf-8")
        after_text = after.decode("utf-8")
    except UnicodeDecodeError:
        return True, ""
    return False, "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
            n=3,
        )
    )


def _delivery_output(output: _PlannedOutput) -> DeliveryOutput:
    binary = False
    diff = ""
    if output.kind == "replaced" and output.before_data is not None:
        binary, diff = _unified_diff(output.path, output.before_data, output.data)
    return DeliveryOutput(
        path=output.path,
        kind=output.kind,
        sha256=output.sha256,
        size=output.size,
        before_sha256=(
            None if output.before_data is None else _sha256(output.before_data)
        ),
        before_size=(
            None if output.before_data is None else len(output.before_data)
        ),
        collision=output.collision,
        binary=binary,
        unified_diff=diff,
    )


# ---------------------------------------------------------------------------
# conversion report (schema 2)
# ---------------------------------------------------------------------------


def _report_bytes(
    analysis: ConversionAnalysis,
    *,
    content_id: str,
    source_snapshot_sha256: str,
    inventory: _Inventory,
    destination_state: str,
    extra_regions: tuple[ExtraRegion, ...],
) -> bytes:
    inspection = analysis.inspection
    payload: dict[str, object] = {
        "schemaVersion": 2,
        "toolkitVersion": __version__,
        # The final delivery plan hashes every published byte, including this
        # report, so the report carries the pre-report content identity rather
        # than claiming to be the final plan ID.
        "contentId": content_id,
        "sourceSnapshotSha256": source_snapshot_sha256,
        "destinationState": destination_state,
        "sourceFileCount": len(inventory.files),
        "inspectionSha256": inspection_sha256_for(inspection),
        "floatAbi": analysis.float_abi,
        "inputs": [
            {"path": entry.path, "sha256": entry.sha256, "size": entry.size}
            for entry in analysis.inputs
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
            for patch in analysis.patches
        ],
        "fixedSections": [
            {
                "section": section.section,
                "address": section.address,
                "sourcePath": section.source_path,
                "line": section.line,
                "symbol": section.symbol,
            }
            for section in analysis.fixed_sections
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
                analysis.ignored,
                key=lambda item: (item.path, item.line, item.column, item.rule_id),
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
                key=lambda source: source.path,
            )
        ],
        "includedAssembly": sorted(
            source.path
            for source in inspection.sources
            if source.included and source.language == "asm"
        ),
        "blockers": [],
    }
    if extra_regions:
        payload["extraRegions"] = [region.to_dict() for region in extra_regions]
    if analysis.include_merges:
        payload["includeMerges"] = [
            merge.to_report_dict() for merge in analysis.include_merges
        ]
    if analysis.startup is not None:
        payload["startup"] = analysis.startup.to_dict()
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------


def _blocked(analysis: ConversionAnalysis) -> MigrationPlanError:
    blockers = analysis.blockers
    return _raise(
        "DELIVERY_BLOCKED",
        "conversion is blocked; resolve the reported decisions before delivery",
        {
            "blockerCount": len(blockers),
            "blockerCodes": sorted({blocker.code for blocker in blockers}),
            "blockers": [blocker.to_dict() for blocker in blockers[:32]],
        },
    )


def _build_delivery(
    source: Path,
    destination: Path,
    inspection: KeilInspection,
    *,
    startup_options: StartupOptions | None,
    memory_layout: MemoryLayout | None,
    extra_regions: tuple[ExtraRegion, ...] | None,
    expected_source_snapshot: str | None = None,
) -> tuple[DeliveryPlan, tuple[tuple[str, bytes], ...], tuple[str, ...]]:
    canonical_source = _canonical_source(source)
    absolute_destination = _absolute_destination(destination)
    if type(inspection) is not KeilInspection:
        raise _raise(
            "DELIVERY_INSPECTION_INVALID",
            "inspection must be a KeilInspection",
            {"field": "inspection", "rule": "type"},
        )
    _reject_disjoint(canonical_source, absolute_destination)
    destination_state = _planning_destination(absolute_destination)

    options = _validate_startup_options(startup_options)
    layout_option = _validate_memory_layout(memory_layout)
    extras = _validate_extra_region_option(extra_regions)

    # Revalidate the complete source snapshot before any conversion analysis.
    # A changed/unreadable/removed source is a delivery-source change with
    # replan guidance, not an incidental low-level input error.
    inventory = _scan_tree(canonical_source)
    if (
        expected_source_snapshot is not None
        and inventory.snapshot_sha256 != expected_source_snapshot
    ):
        raise _raise(
            "DELIVERY_SOURCE_CHANGED",
            "source content changed since planning; replan before applying",
            {
                "rule": "sourceSnapshot",
                "expected": expected_source_snapshot,
                "actual": inventory.snapshot_sha256,
            },
        )

    try:
        analysis = analyze_keil_conversion(
            canonical_source,
            inspection,
            startup_options=options,
            memory_layout=layout_option,
            extra_regions=extras,
        )
    except MigrationPlanError as error:
        # A conversion-analysis failure is relabelled as a source change only
        # when the complete source snapshot demonstrably differs from the one
        # just read; otherwise the genuine diagnostic is returned unchanged.
        rescanned: _Inventory | None = None
        try:
            rescanned = _scan_tree(canonical_source)
        except MigrationPlanError:
            rescanned = None
        if (
            rescanned is not None
            and rescanned.snapshot_sha256 != inventory.snapshot_sha256
        ):
            details = {
                "rule": "sourceSnapshot",
                "cause": error.code,
                "path": _first_inventory_difference(inventory, rescanned),
            }
            raise _raise(
                "DELIVERY_SOURCE_CHANGED",
                "source content changed while planning; replan",
                details,
            ) from None
        if error.code in ("MIGRATION_INSPECTION_CHANGED", "MIGRATION_INSPECTION_INVALID"):
            details = {"rule": "inspection", "cause": error.code}
            if isinstance(error.details.get("path"), str):
                details["path"] = error.details["path"]
            raise _raise(
                "DELIVERY_SOURCE_CHANGED",
                "source no longer matches the supplied inspection; replan before applying",
                details,
            ) from None
        raise
    if analysis.blockers:
        raise _blocked(analysis)

    # Analysis re-inspects the source; refuse a source change between the
    # complete snapshot above and that analysis rather than planning from
    # mixed evidence.
    after_analysis = _scan_tree(canonical_source)
    if after_analysis.snapshot_sha256 != inventory.snapshot_sha256:
        raise _raise(
            "DELIVERY_SOURCE_CHANGED",
            "source content changed while planning; replan",
            {
                "rule": "sourceSnapshot",
                "path": _first_inventory_difference(inventory, after_analysis),
            },
        )
    outputs = _overlay_patches(inventory, analysis.patches)
    manifest_output = outputs.get(_MANIFEST_NAME)
    if manifest_output is None:
        raise _raise(
            "DELIVERY_MANIFEST_INVALID",
            "conversion analysis did not produce a project manifest",
            {"field": "manifest", "rule": "missing"},
        )
    try:
        load_project_model_candidate(canonical_source, manifest_output.data)
    except ProjectManifestError as error:
        raise _raise(
            "DELIVERY_MANIFEST_INVALID",
            "proposed project manifest is not a valid model",
            {
                "field": str(error.details.get("path", "$")),
                "rule": str(error.details.get("reason", "invalid")),
            },
        ) from None

    normalized_destination = _normalized_destination(absolute_destination)
    inspection_sha256 = inspection_sha256_for(analysis.inspection)
    option_payload = {
        "startupOptions": options.to_dict() if options is not None else None,
        "memoryLayout": layout_option.to_dict() if layout_option is not None else None,
        "extraRegions": [region.to_dict() for region in extras],
    }
    analysis_id = _analysis_id(
        normalized_destination,
        destination_state,
        inventory.snapshot_sha256,
        inspection_sha256,
        analysis,
        option_payload,
        analysis.patches,
    )
    # The seed report carries validated fixed-section evidence into the shared
    # renderer; only its content identity changes once the final content
    # identity exists.
    seed_report = _report_bytes(
        analysis,
        content_id=analysis_id,
        source_snapshot_sha256=inventory.snapshot_sha256,
        inventory=inventory,
        destination_state=destination_state,
        extra_regions=extras,
    )
    try:
        rendered = render_new_project_configuration(
            canonical_source,
            manifest_output.data,
            conversion_report_bytes=seed_report,
        )
    except GenerationError as error:
        raise _raise(error.code, error.message, dict(error.details)) from None

    for entry in rendered.files:
        _add_generated(outputs, entry.path, entry.after_bytes)
    _add_generated(outputs, rendered.managed_manifest_path, rendered.managed_manifest_bytes)

    directories = _output_directories(inventory, outputs)
    content_id = _sha256(
        canonical_json_bytes(
            {
                "format": _CONTENT_FORMAT,
                "toolkitVersion": __version__,
                "analysisId": analysis_id,
                "outputDirectories": list(directories),
                "outputs": [
                    {
                        "path": output.path,
                        "kind": output.kind,
                        "sha256": output.sha256,
                        "size": output.size,
                    }
                    for output in sorted(
                        outputs.values(), key=lambda item: portable_sort_key(item.path)
                    )
                ],
            }
        )
    )
    report = _report_bytes(
        analysis,
        content_id=content_id,
        source_snapshot_sha256=inventory.snapshot_sha256,
        inventory=inventory,
        destination_state=destination_state,
        extra_regions=extras,
    )
    _add_generated(outputs, _CONVERSION_REPORT_PATH, report)
    directories = _output_directories(inventory, outputs)

    final = tuple(
        sorted(outputs.values(), key=lambda item: portable_sort_key(item.path))
    )
    _reject_casefold([output.path for output in final], "output")
    _reject_casefold(
        [output.path for output in final] + list(directories),
        "output",
        skip_equal=True,
    )
    _reject_output_conflicts(final, directories)
    _validate_output_bounds(final, directories)
    for output in final:
        if output.path == _EXCLUDED_ENTRY or output.path.startswith(
            _EXCLUDED_ENTRY + "/"
        ):
            raise _raise(
                "DELIVERY_SOURCE_INVALID",
                "output must not contain a Git directory",
                {"path": output.path, "rule": "reserved"},
            )

    output_snapshot_sha256 = _output_snapshot_sha256(
        tuple((output.path, output.sha256, output.size) for output in final),
        directories,
    )
    report_output = outputs[_CONVERSION_REPORT_PATH]
    plan_id = _sha256(
        canonical_json_bytes(
            {
                "format": "stm32tk-delivery-plan/1",
                "planVersion": _PLAN_VERSION,
                "contentId": content_id,
                "outputSnapshotSha256": output_snapshot_sha256,
                "outputs": [
                    {
                        "path": output.path,
                        "kind": output.kind,
                        "sha256": output.sha256,
                        "size": output.size,
                        "beforeSha256": (
                            None
                            if output.before_data is None
                            else _sha256(output.before_data)
                        ),
                    }
                    for output in final
                ],
            }
        )
    )

    plan = DeliveryPlan(
        source_root=canonical_source,
        destination_root=absolute_destination,
        inspection=analysis.inspection,
        plan_version=_PLAN_VERSION,
        plan_id=plan_id,
        content_id=content_id,
        destination_state=destination_state,
        source_snapshot_sha256=inventory.snapshot_sha256,
        output_snapshot_sha256=output_snapshot_sha256,
        outputs=tuple(
            _delivery_output(output)
            for output in final
        ),
        output_directories=directories,
        source_patches=analysis.patches,
        source_file_count=len(inventory.files),
        source_directory_count=len(inventory.directories),
        source_total_bytes=inventory.total_bytes,
        excluded_git_entries=inventory.excluded,
        report_path=_CONVERSION_REPORT_PATH,
        report_sha256=report_output.sha256,
        managed_manifest_path=rendered.managed_manifest_path,
        managed_manifest_sha256=_sha256(rendered.managed_manifest_bytes),
        startup_options=options,
        memory_layout=layout_option,
        extra_regions=extras,
        include_merges=analysis.include_merges,
        warnings=(
            "Inputs outside the source tree are never guessed; unresolved"
            " dependencies remain conversion diagnostics.",
        ),
    )
    # Private, non-identity inventory evidence for change diagnostics only.
    object.__setattr__(plan, "_source_files", inventory.files)
    object.__setattr__(plan, "_source_directories", inventory.directories)
    try:
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        raise _raise(
            "DELIVERY_PLAN_INVALID",
            "plan serialization failed",
            {"rule": "serialize"},
        ) from None
    if len(serialized) > _PLAN_LIMIT_BYTES:
        raise _raise(
            "DELIVERY_LIMIT_EXCEEDED",
            "serialized delivery plan exceeds the limit",
            {"scope": "plan", "limitBytes": _PLAN_LIMIT_BYTES},
        )
    return (
        plan,
        tuple((output.path, output.data) for output in final),
        directories,
    )


def plan_keil_delivery(
    source_root: Path,
    destination_root: Path,
    inspection: KeilInspection,
    *,
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
    extra_regions: tuple[ExtraRegion, ...] | None = None,
) -> DeliveryPlan:
    """Plan one independent output directory without writing anything."""
    plan, _outputs, _directories = _build_delivery(
        source_root,
        destination_root,
        inspection,
        startup_options=startup_options,
        memory_layout=memory_layout,
        extra_regions=extra_regions,
    )
    return plan


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class _DeliveryFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _fail(code: str, message: str, details: dict[str, object]) -> _DeliveryFailure:
    return _DeliveryFailure(code, message, details)


def _plan_invalid(rule: str) -> _DeliveryFailure:
    return _fail(
        "DELIVERY_PLAN_INVALID", "delivery plan validation failed", {"rule": rule}
    )


def _validate_plan_object(plan: object) -> None:
    if type(plan) is not DeliveryPlan:
        raise _plan_invalid("type")
    if type(plan.plan_version) is not int or plan.plan_version != _PLAN_VERSION:
        raise _plan_invalid("planVersion")
    if not isinstance(plan.source_root, Path) or not isinstance(
        plan.destination_root, Path
    ):
        raise _plan_invalid("type")
    if not plan.destination_root.is_absolute():
        raise _plan_invalid("destination")
    if type(plan.inspection) is not KeilInspection:
        raise _plan_invalid("type")
    for value in (
        plan.plan_id,
        plan.content_id,
        plan.source_snapshot_sha256,
        plan.output_snapshot_sha256,
        plan.report_sha256,
        plan.managed_manifest_sha256,
    ):
        if sha256_error(value) is not None:
            raise _plan_invalid("digest")
    if plan.destination_state not in ("absent", "empty"):
        raise _plan_invalid("destinationState")
    if plan.report_path != _CONVERSION_REPORT_PATH:
        raise _plan_invalid("reportPath")
    if plan.managed_manifest_path != MANAGED_MANIFEST_PATH:
        raise _plan_invalid("manifestPath")
    if not isinstance(plan.outputs, tuple) or not all(
        isinstance(output, DeliveryOutput) for output in plan.outputs
    ):
        raise _plan_invalid("outputs")
    paths = [output.path for output in plan.outputs]
    if len(set(paths)) != len(paths):
        raise _plan_invalid("uniquePath")
    if paths != sorted(paths, key=portable_sort_key):
        raise _plan_invalid("sortedOrder")
    for path in paths:
        if portable_path_error(path) is not None:
            raise _plan_invalid("portablePath")
    for output in plan.outputs:
        if output.kind not in ("copied", "replaced", "generated"):
            raise _plan_invalid("kind")
        if sha256_error(output.sha256) is not None:
            raise _plan_invalid("digest")
        if type(output.size) is not int or output.size < 0:
            raise _plan_invalid("digest")
        if (output.before_sha256 is None) != (output.before_size is None):
            raise _plan_invalid("digest")
        if output.before_size is not None and (
            type(output.before_size) is not int or output.before_size < 0
        ):
            raise _plan_invalid("digest")
        if output.before_sha256 is not None and sha256_error(
            output.before_sha256
        ) is not None:
            raise _plan_invalid("digest")
    if not isinstance(plan.output_directories, tuple) or not all(
        isinstance(directory, str) for directory in plan.output_directories
    ):
        raise _plan_invalid("directories")
    for directory in plan.output_directories:
        if portable_path_error(directory) is not None:
            raise _plan_invalid("portablePath")
    if plan.startup_options is not None and type(plan.startup_options) is not StartupOptions:
        raise _plan_invalid("startupOptions")
    if plan.memory_layout is not None and type(plan.memory_layout) is not MemoryLayout:
        raise _plan_invalid("memoryLayout")
    if not isinstance(plan.extra_regions, tuple) or not all(
        isinstance(region, ExtraRegion) for region in plan.extra_regions
    ):
        raise _plan_invalid("extraRegions")
    if not isinstance(plan.source_patches, tuple) or not all(
        isinstance(patch, FilePatch) for patch in plan.source_patches
    ):
        raise _plan_invalid("patches")
    for count in (
        plan.source_file_count,
        plan.source_directory_count,
        plan.source_total_bytes,
        plan.excluded_git_entries,
    ):
        if type(count) is not int or count < 0:
            raise _plan_invalid("counts")


def _plan_preview_mismatch(fresh: DeliveryPlan, plan: DeliveryPlan) -> str | None:
    """Return the first preview field that differs from a fresh recomputation.

    Comparing only ``plan_id`` and selected digest attributes would accept a
    ``dataclasses.replace``-mutated plan whose displayed outputs, directories,
    patches, options or counts no longer describe what apply would publish.
    """
    if fresh.plan_version != plan.plan_version:
        return "planVersion"
    if fresh.source_root != plan.source_root:
        return "sourceRoot"
    if fresh.destination_root != plan.destination_root:
        return "destination"
    if fresh.inspection != plan.inspection:
        return "inspection"
    if fresh.destination_state != plan.destination_state:
        return "destinationState"
    if fresh.source_snapshot_sha256 != plan.source_snapshot_sha256:
        return "sourceSnapshot"
    if fresh.content_id != plan.content_id:
        return "contentId"
    if fresh.output_snapshot_sha256 != plan.output_snapshot_sha256:
        return "outputSnapshot"
    if fresh.outputs != plan.outputs:
        return "outputs"
    if fresh.output_directories != plan.output_directories:
        return "directories"
    if fresh.source_patches != plan.source_patches:
        return "patches"
    if fresh.source_file_count != plan.source_file_count:
        return "sourceFileCount"
    if fresh.source_directory_count != plan.source_directory_count:
        return "sourceDirectoryCount"
    if fresh.source_total_bytes != plan.source_total_bytes:
        return "sourceTotalBytes"
    if fresh.excluded_git_entries != plan.excluded_git_entries:
        return "excludedGitEntries"
    if fresh.report_path != plan.report_path:
        return "reportPath"
    if fresh.report_sha256 != plan.report_sha256:
        return "reportSha256"
    if fresh.managed_manifest_path != plan.managed_manifest_path:
        return "managedManifestPath"
    if fresh.managed_manifest_sha256 != plan.managed_manifest_sha256:
        return "managedManifestSha256"
    if fresh.startup_options != plan.startup_options:
        return "startupOptions"
    if fresh.memory_layout != plan.memory_layout:
        return "memoryLayout"
    if fresh.extra_regions != plan.extra_regions:
        return "extraRegions"
    if fresh.include_merges != plan.include_merges:
        return "includeMerges"
    if fresh.warnings != plan.warnings:
        return "warnings"
    return None


def _source_changed(
    *, path: str = "", cause: str = "", scope: str = ""
) -> _DeliveryFailure:
    details: dict[str, object] = {"rule": "sourceSnapshot"}
    if cause:
        details["cause"] = cause
    if path:
        details["path"] = path
    if scope:
        details["scope"] = scope
    return _fail(
        "DELIVERY_SOURCE_CHANGED",
        "source content changed since planning; replan before applying",
        details,
    )


def _first_inventory_difference(planned: _Inventory, current: _Inventory) -> str:
    """Return the first source path whose content or presence differs."""
    planned_files = {entry.path: entry.sha256 for entry in planned.files}
    actual_files = {entry.path: entry.sha256 for entry in current.files}
    for path in sorted(
        set(planned_files) | set(actual_files), key=portable_sort_key
    ):
        if planned_files.get(path) != actual_files.get(path):
            return path
    planned_dirs = set(planned.directories)
    actual_dirs = set(current.directories)
    for path in sorted(planned_dirs | actual_dirs, key=portable_sort_key):
        if (path in planned_dirs) != (path in actual_dirs):
            return path
    return ""


def _first_source_difference(plan: DeliveryPlan, current: _Inventory) -> str:
    """Difference against the planning-time inventory carried privately.

    That inventory is diagnostic only and never participates in identity or
    preview fields.
    """
    return _first_inventory_difference(
        _Inventory(
            root=plan.source_root,
            files=tuple(getattr(plan, "_source_files", ())),
            directories=tuple(getattr(plan, "_source_directories", ())),
            data={},
        ),
        current,
    )


def _source_changed_from(error: MigrationPlanError) -> _DeliveryFailure:
    """Map a source-tree refusal to a source change without dropping detail."""
    path = error.details.get("path")
    scope = error.details.get("scope")
    failure = _source_changed(
        path=path if isinstance(path, str) else "",
        cause=error.code,
        scope=scope if isinstance(scope, str) else "",
    )
    for key in ("expected", "actual"):
        value = error.details.get(key)
        if isinstance(value, str):
            failure.details[key] = value
    return failure


def _destination_changed() -> _DeliveryFailure:
    return _fail(
        "DELIVERY_DESTINATION_CHANGED",
        "destination state changed since planning; replan before applying",
        {"rule": "destinationState"},
    )


@dataclass(frozen=True)
class _StagingIdentity:
    """Identity of the one staging directory this apply created."""

    dev: int
    ino: int
    parent_dev: int
    parent_ino: int


def _capture_staging_identity(staging: Path) -> _StagingIdentity:
    st = os.lstat(staging)
    parent = os.lstat(staging.parent)
    return _StagingIdentity(
        dev=st.st_dev,
        ino=st.st_ino,
        parent_dev=parent.st_dev,
        parent_ino=parent.st_ino,
    )


def _staging_still_owned(staging: Path, identity: _StagingIdentity) -> bool:
    """True only when the staging root and its parent are the same regular dirs.

    A replaced root, a replaced/redirected parent, or a missing path is never
    treated as ours; callers must not delete or publish through it.
    """
    try:
        st = os.lstat(staging)
        parent = os.lstat(staging.parent)
    except OSError:
        return False
    if _is_redirect(st) or not stat.S_ISDIR(st.st_mode):
        return False
    if _is_redirect(parent) or not stat.S_ISDIR(parent.st_mode):
        return False
    return (st.st_dev, st.st_ino) == (identity.dev, identity.ino) and (
        parent.st_dev,
        parent.st_ino,
    ) == (identity.parent_dev, identity.parent_ino)


def _cleanup_staging(
    staging: Path, identity: _StagingIdentity | None
) -> tuple[bool, str]:
    """Remove only the verified owned staging root.

    Returns ``(removed, status)`` where status is ``removed``, ``absent``,
    ``skipped-replaced`` (identity changed; nothing was deleted), ``failed``
    (owned but removal failed), or ``unverified`` (no recorded identity).
    """
    if identity is None:
        return False, "unverified"
    if not _staging_still_owned(staging, identity):
        return False, "skipped-replaced"
    try:
        shutil.rmtree(staging)
        return True, "removed"
    except FileNotFoundError:
        return True, "absent"
    except OSError:
        return False, "failed"


def _write_new_file(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o644)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _stage_outputs(
    staging: Path,
    outputs: tuple[tuple[str, bytes], ...],
    directories: tuple[str, ...],
) -> None:
    for directory in directories:
        os.makedirs(staging.joinpath(*directory.split("/")), exist_ok=True)
    for path, data in outputs:
        target = staging.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_new_file(target, data)


def _verify_staging(staging: Path, expected_snapshot: str) -> None:
    """Verify the complete staged tree, not only the files we intended.

    The same bounded scanner used for publication runs here, so unexpected
    files, links/reparse points, directories, missing bytes, or a tree beyond
    a limit are refused before the destination is touched.
    """
    try:
        scanned = _scan_tree(staging, exclude_git=False)
    except MigrationPlanError as error:
        details: dict[str, object] = {"phase": "stage", "cause": error.code}
        path = error.details.get("path")
        if isinstance(path, str):
            details["path"] = path
        raise _fail(
            "DELIVERY_APPLY_FAILED",
            "staged output is not a supported complete tree",
            details,
        ) from None
    snapshot = _output_snapshot_sha256(
        tuple((entry.path, entry.sha256, entry.size) for entry in scanned.files),
        scanned.directories,
    )
    if snapshot != expected_snapshot:
        raise _fail(
            "DELIVERY_APPLY_FAILED",
            "staged output does not match the planned snapshot",
            {"phase": "stage", "rule": "outputSnapshot"},
        )


def _apply(plan: DeliveryPlan) -> dict[str, object]:
    _validate_plan_object(plan)
    try:
        fresh, outputs, directories = _build_delivery(
            plan.source_root,
            plan.destination_root,
            plan.inspection,
            startup_options=plan.startup_options,
            memory_layout=plan.memory_layout,
            extra_regions=plan.extra_regions,
            expected_source_snapshot=plan.source_snapshot_sha256,
        )
    except MigrationPlanError as error:
        if error.code in ("DELIVERY_DESTINATION_EXISTS", "DELIVERY_DESTINATION_INVALID"):
            raise _destination_changed() from None
        if error.code in (
            "DELIVERY_SOURCE_CHANGED",
            "DELIVERY_ROOT_INVALID",
            "DELIVERY_SOURCE_INVALID",
            "DELIVERY_LINK_UNSUPPORTED",
            "DELIVERY_UNSUPPORTED_ENTRY",
            "DELIVERY_LIMIT_EXCEEDED",
            "DELIVERY_CASEFOLD_COLLISION",
            "MIGRATION_INSPECTION_CHANGED",
            "MIGRATION_INSPECTION_INVALID",
        ):
            raise _source_changed_from(error) from None
        # Every other refusal (invalid inspection/model/options/manifest,
        # conversion blockers, generation errors) is a genuine diagnostic and
        # is returned unchanged rather than relabelled as a source change.
        raise
    if fresh.destination_state != plan.destination_state:
        raise _destination_changed()
    if fresh.source_snapshot_sha256 != plan.source_snapshot_sha256:
        raise _source_changed(cause="sourceSnapshot")
    if fresh.plan_id != plan.plan_id:
        raise _fail(
            "DELIVERY_PLAN_CHANGED",
            "recomputed delivery plan does not match the supplied plan",
            {"rule": "planId"},
        )
    # The supplied plan is a preview object: every displayed field and digest
    # must match the fresh recomputation before the first staging write.
    mismatch = _plan_preview_mismatch(fresh, plan)
    if mismatch is not None:
        raise _fail(
            "DELIVERY_PLAN_CHANGED",
            "recomputed delivery plan does not match the supplied plan",
            {"rule": mismatch},
        )

    destination = plan.destination_root
    staging = destination.parent / f".{destination.name}{_STAGING_SUFFIX}{fresh.plan_id[:12]}"
    if staging.parent != destination.parent:
        raise _fail(
            "DELIVERY_PLAN_INVALID",
            "staging is not a sibling of the destination",
            {"rule": "staging"},
        )
    try:
        os.mkdir(staging)
    except FileExistsError:
        raise _fail(
            "DELIVERY_TARGET_EXISTS",
            "an owned staging directory already exists",
            {"path": staging.name},
        ) from None
    except OSError:
        raise _fail(
            "DELIVERY_APPLY_FAILED",
            "staging could not be created",
            {"phase": "stage"},
        ) from None

    identity: _StagingIdentity | None
    try:
        identity = _capture_staging_identity(staging)
    except OSError:
        # The directory was created but cannot be proven to be ours; never
        # delete an unverified path.
        raise _fail(
            "DELIVERY_APPLY_FAILED",
            "owned staging identity could not be recorded",
            {"phase": "stage", "stagingRemoved": False, "cleanup": "unverified"},
        ) from None

    emptied = False
    try:
        _stage_outputs(staging, outputs, directories)
        if not _staging_still_owned(staging, identity):
            raise _fail(
                "DELIVERY_STAGING_CHANGED",
                "owned staging was replaced; nothing was published",
                {"phase": "stage", "reason": "replaced"},
            )
        _verify_staging(staging, fresh.output_snapshot_sha256)

        # A concurrent source change invalidates the plan before publication.
        try:
            current = _scan_tree(plan.source_root)
        except MigrationPlanError as error:
            raise _source_changed_from(error) from None
        if (
            current.snapshot_sha256 != fresh.source_snapshot_sha256
            or current.snapshot_sha256 != plan.source_snapshot_sha256
        ):
            raise _source_changed(
                cause="sourceSnapshot",
                path=_first_source_difference(fresh, current),
            )
        try:
            state = _inspect_destination(destination)
        except MigrationPlanError:
            raise _destination_changed() from None
        if state != fresh.destination_state:
            raise _destination_changed()

        if state == "empty":
            try:
                os.rmdir(destination)
            except OSError:
                raise _destination_changed() from None
            emptied = True
        # The destination must still be absent immediately before the single
        # publication rename; an unrelated file or directory that appeared is
        # never replaced or deleted.
        try:
            os.lstat(destination)
        except FileNotFoundError:
            pass
        except OSError:
            raise _destination_changed() from None
        else:
            raise _destination_changed()
        # Publication uses only the verified owned staging root.
        if not _staging_still_owned(staging, identity):
            raise _fail(
                "DELIVERY_STAGING_CHANGED",
                "owned staging was replaced; nothing was published",
                {"phase": "publish", "reason": "replaced"},
            )
        try:
            os.replace(staging, destination)
        except FileExistsError:
            if emptied:
                try:
                    os.mkdir(destination)
                except OSError:
                    pass
                emptied = False
            raise _destination_changed() from None
        except OSError:
            raise _fail(
                "DELIVERY_APPLY_FAILED",
                "publishing the complete output failed",
                {"phase": "publish"},
            ) from None
    except _DeliveryFailure as failure:
        removed, cleanup_status = _cleanup_staging(staging, identity)
        details = dict(failure.details)
        details["stagingRemoved"] = removed
        details["cleanup"] = cleanup_status
        if not removed:
            details["staging"] = staging.name
        if emptied and not destination.exists():
            try:
                os.mkdir(destination)
            except OSError:
                pass
        raise _DeliveryFailure(failure.code, failure.message, details) from None
    except OSError:
        removed, cleanup_status = _cleanup_staging(staging, identity)
        details: dict[str, object] = {
            "phase": "stage",
            "stagingRemoved": removed,
            "cleanup": cleanup_status,
        }
        if not removed:
            details["staging"] = staging.name
        raise _fail(
            "DELIVERY_APPLY_FAILED", "delivery apply failed", details
        ) from None

    # Honest published-state verification: the complete directory must match
    # the output snapshot the plan bound.
    try:
        published = _scan_tree(destination, exclude_git=False)
        published_snapshot = _output_snapshot_sha256(
            tuple(
                (entry.path, entry.sha256, entry.size) for entry in published.files
            ),
            published.directories,
        )
    except MigrationPlanError:
        published_snapshot = None
    if (
        published_snapshot != fresh.output_snapshot_sha256
        or published_snapshot != plan.output_snapshot_sha256
    ):
        raise _fail(
            "DELIVERY_PUBLISH_INVALID",
            "published output does not match the planned snapshot",
            {"rule": "outputSnapshot"},
        )

    return {
        "planId": fresh.plan_id,
        "contentId": fresh.content_id,
        "outputRoot": str(destination),
        "sourceSnapshotSha256": fresh.source_snapshot_sha256,
        "outputSnapshotSha256": fresh.output_snapshot_sha256,
        "reportPath": fresh.report_path,
        "reportSha256": fresh.report_sha256,
        "managedManifestPath": fresh.managed_manifest_path,
        "managedManifestSha256": fresh.managed_manifest_sha256,
        "copiedFiles": sum(1 for output in fresh.outputs if output.kind == "copied"),
        "replacedFiles": sum(
            1 for output in fresh.outputs if output.kind == "replaced"
        ),
        "generatedFiles": sum(
            1 for output in fresh.outputs if output.kind == "generated"
        ),
        "directories": len(directories),
        "destinationStateAtPlan": fresh.destination_state,
        # Configuration was generated; no build or flash occurred.
        "configured": True,
        "built": False,
        "flashed": False,
        "followUp": _FOLLOW_UP,
        "warnings": list(fresh.warnings),
    }


def apply_keil_delivery(
    plan: DeliveryPlan,
    *,
    authorized: object = False,
    plan_id: object = None,
) -> OperationResult[dict[str, object]]:
    """Publish the planned complete output after explicit authorization."""
    if authorized is not True:
        return OperationResult.failure(
            "keil-delivery-apply",
            "DELIVERY_NOT_AUTHORIZED",
            "explicit authorization is required",
            {"field": "authorized", "rule": "confirmation"},
        )
    if not isinstance(plan, DeliveryPlan):
        return OperationResult.failure(
            "keil-delivery-apply",
            "DELIVERY_PLAN_INVALID",
            "delivery plan validation failed",
            {"rule": "type"},
        )
    if not isinstance(plan_id, str) or plan_id != plan.plan_id:
        return OperationResult.failure(
            "keil-delivery-apply",
            "DELIVERY_PLAN_ID_MISMATCH",
            "the exact freshly recomputed plan ID is required",
            {"field": "planId", "rule": "confirmation"},
        )
    try:
        data = _apply(plan)
    except _DeliveryFailure as failure:
        return OperationResult.failure(
            "keil-delivery-apply",
            failure.code,
            failure.message,
            failure.details,
        )
    except MigrationPlanError as error:
        return OperationResult.failure(
            "keil-delivery-apply", error.code, error.message, error.details
        )
    except OSError:
        return OperationResult.failure(
            "keil-delivery-apply",
            "DELIVERY_APPLY_FAILED",
            "delivery apply failed",
            {"phase": "unknown"},
        )
    return OperationResult.success("keil-delivery-apply", data)
