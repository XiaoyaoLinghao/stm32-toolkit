"""Fail-closed planning and preview values for CubeMX project regeneration.

The regeneration slice deliberately keeps its public surface small.  This
module owns the immutable request/plan/preview values, the single ownership
inventory used by both planning and apply, and all deterministic hashing.  It
does not invoke CubeMX or mutate a project; orchestration lives in
``regeneration_workflows``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from stm32_toolkit.build.identity import GitEvidence, git_evidence
from stm32_toolkit.creation_environment import (
    CreationEnvironmentError,
    CreationExecutionEnvironment,
    discover_creation_environment,
)
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import (
    GENERATED_TARGETS,
    MANAGED_MANIFEST_PATH,
    canonical_json_bytes,
    casefold_collision,
    parse_managed_manifest,
    portable_path_error,
    portable_sort_key,
    sha256_hex,
)
from stm32_toolkit.project_model import ProjectManifestError, ProjectModel, load_project_model
from stm32_toolkit.tool_support import SupportProfileError, SupportProfileRequest, ToolSupportProfile, discover_tool_support


REGENERATION_SCHEMA_VERSION = 1
MAX_FILES = 200_000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PATH_DEPTH = 32
MAX_RELATIVE_BYTES = 4096
MAX_IOC_BYTES = 1 * 1024 * 1024
MAX_OWNERSHIP_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_DIFF_BYTES = 64 * 1024
MAX_PREVIEW_BYTES = 1 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IOCPROP = re.compile(r"(?im)^\s*ProjectManager\.Language\s*=\s*([^\r\n]+)")

_TOOLKIT_FIXED = frozenset(
    {".stm32-project.json", ".stm32-toolkit/generated-files.json", ".stm32-toolkit/cubemx-ownership.json"}
)
_DERIVED_FIXED = frozenset({".stm32-toolkit/build.lock"})
_USER_ROOTS = ("App", "Tests")


class RegenerationInputError(ValueError):
    """Caller input is not part of the closed regeneration grammar."""

    def __init__(self, code: str, field: str, message: str | None = None) -> None:
        super().__init__(message or f"{code}:{field}")
        self.code = code
        self.field = field
        self.message = message or "regeneration input is invalid"


class RegenerationError(ValueError):
    """Bounded internal/public regeneration failure."""

    def __init__(self, code: str, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _expiry(now: datetime) -> str:
    return (_utc(now) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _portable(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field)
    reason = portable_path_error(value)
    if reason is not None:
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field)
    normalized = value.replace("\\", "/")
    # ``portable_path_error`` accepts backslashes for historical generation
    # paths; requests are normalized to the single public slash spelling.
    if portable_path_error(normalized) is not None:
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field)
    return normalized


def _canonical_root(value: object, field: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field)
    try:
        root = value.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field) from None
    if not root.is_absolute() or root != root.resolve(strict=False):
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", field)
    return root


@dataclass(frozen=True, slots=True)
class RegenerationWorkflowRequest:
    """The only neutral input shared by CLI, MCP, and core workflows."""

    workspace_root: Path
    data_root: Path
    session_id: str
    destination: str

    def __post_init__(self) -> None:
        workspace = _canonical_root(self.workspace_root, "workspaceRoot")
        data = _canonical_root(self.data_root, "dataRoot")
        if not isinstance(self.session_id, str) or _SESSION.fullmatch(self.session_id) is None:
            raise RegenerationInputError("REGENERATION_INPUT_INVALID", "sessionId")
        destination = _portable(self.destination, "destination")
        object.__setattr__(self, "workspace_root", workspace)
        object.__setattr__(self, "data_root", data)
        object.__setattr__(self, "destination", destination)

    @property
    def project_root(self) -> Path:
        return self.workspace_root.joinpath(*self.destination.split("/"))

    @property
    def destination_canonical(self) -> Path:
        try:
            return self.project_root.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            raise RegenerationError("REGENERATION_INPUT_INVALID", "regeneration destination is invalid") from None

    def to_dict(self) -> dict[str, object]:
        # Absolute roots are intentionally not placed in public result data.
        return {"sessionId": self.session_id, "destination": self.destination}

    def canonical_dict(self) -> dict[str, object]:
        return {
            "workspaceRoot": self.workspace_root.as_posix(),
            "dataRoot": self.data_root.as_posix(),
            "sessionId": self.session_id,
            "destination": self.destination,
        }


@dataclass(frozen=True, slots=True)
class RegenerationBlocker:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    path: str
    kind: str  # file|dir
    size: int
    sha256: str | None
    ownership: str  # toolkit|cubemx|user|derived

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "ownership": self.ownership,
        }


@dataclass(frozen=True, slots=True)
class ChangeRecord:
    path: str
    status: str  # added|modified|deleted
    before_sha256: str | None
    after_sha256: str | None
    before_size: int | None
    after_size: int | None
    unified_diff: str | None = None
    ownership_before: str | None = None
    ownership_after: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "beforeSha256": self.before_sha256,
            "afterSha256": self.after_sha256,
            "beforeSize": self.before_size,
            "afterSize": self.after_size,
            "unifiedDiff": self.unified_diff,
        }


@dataclass(frozen=True, slots=True)
class RegenerationPreview:
    preview_digest: str
    changes: tuple[ChangeRecord, ...]
    counts: Mapping[str, int]
    replacement_inventory_digest: str
    ownership_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "previewDigest": self.preview_digest,
            "changes": [item.to_dict() for item in self.changes],
            "counts": dict(self.counts),
            "replacementInventoryDigest": self.replacement_inventory_digest,
            "ownershipDigest": self.ownership_digest,
        }


@dataclass(frozen=True, slots=True)
class RegenerationPlan:
    schema_version: int
    request: RegenerationWorkflowRequest
    logical_project_id: str
    device: str
    ioc_path: str
    current_ioc_sha256: str
    prior_owned_ioc_sha256: str
    git_head: str
    project_state_digest: str
    ownership_manifest_digest: str
    managed_manifest_digest: str
    model_sha256: str
    execution_environment_digest: str
    generator: Mapping[str, object]
    package: Mapping[str, object]
    counts: Mapping[str, int]
    blockers: tuple[RegenerationBlocker, ...]
    expires_at: str
    plan_id: str
    action_digest: str
    mutated: bool = False
    # The following values are internal evidence and are never serialized.
    model: ProjectModel | None = field(default=None, repr=False, compare=False)
    inventory: tuple[InventoryEntry, ...] = field(default=(), repr=False, compare=False)
    git: GitEvidence | None = field(default=None, repr=False, compare=False)
    environment: object | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "request": self.request.to_dict(),
            "logicalProjectId": self.logical_project_id,
            "device": self.device,
            "iocPath": self.ioc_path,
            "currentIocSha256": self.current_ioc_sha256,
            "priorOwnedIocSha256": self.prior_owned_ioc_sha256,
            "gitHead": self.git_head,
            "projectStateDigest": self.project_state_digest,
            "ownershipManifestDigest": self.ownership_manifest_digest,
            "managedManifestDigest": self.managed_manifest_digest,
            "managedManifestModelSha256": self.model_sha256,
            "executionEnvironmentDigest": self.execution_environment_digest,
            "generator": dict(self.generator),
            "package": dict(self.package),
            "counts": dict(self.counts),
            "blockers": [item.to_dict() for item in self.blockers],
            "expiresAt": self.expires_at,
            "planId": self.plan_id,
            "actionDigest": self.action_digest,
            "mutated": self.mutated,
        }


@dataclass(frozen=True, slots=True)
class OwnershipSnapshot:
    model: ProjectModel
    inventory: tuple[InventoryEntry, ...]
    ownership_rows: tuple[dict[str, object], ...]
    ownership_manifest_bytes: bytes
    ownership_manifest_digest: str
    managed_manifest_bytes: bytes
    managed_manifest_digest: str
    model_sha256: str
    prior_ioc_sha256: str
    current_ioc_sha256: str
    blockers: tuple[RegenerationBlocker, ...]
    file_bytes: Mapping[str, bytes] = field(repr=False, compare=False)

    @property
    def ioc_path(self) -> str:
        value = self.model.generation.cube_mx_ioc
        if not isinstance(value, str) or not value:
            raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX IOC path is unavailable")
        return value


def _safe_lstat(path: Path) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path cannot be inspected") from None
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path contains a redirect")
    return info


def _read_file(path: Path, *, limit: int = MAX_FILE_BYTES) -> tuple[bytes, int]:
    before = _safe_lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path contains a special file")
    if before.st_size > limit:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project file exceeds its bound")
    try:
        data = path.read_bytes()
    except OSError:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project file cannot be read") from None
    after = _safe_lstat(path)
    if before.st_size != len(data) or after.st_size != len(data) or before.st_mtime_ns != after.st_mtime_ns:
        raise RegenerationError("REGENERATION_STATE_CHANGED", "project file changed while it was read")
    return data, len(data)


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path escapes its root") from None
    if not relative or portable_path_error(relative) is not None:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path is not portable")
    if len(relative.encode("utf-8")) > MAX_RELATIVE_BYTES or len(Path(relative).parts) > MAX_PATH_DEPTH:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path exceeds its bound")
    return relative


def _assert_destination_lexical_path_safe(request: RegenerationWorkflowRequest) -> None:
    """Reject redirect/reparse components before resolving the destination.

    Resolving first would make a destination symlink look like an ordinary
    project root and would defeat the inventory's no-redirect guarantee.
    Missing components remain a normal project-invalid condition; only an
    existing redirect is rejected here.
    """
    current = request.workspace_root
    for component in request.destination.split("/"):
        current = current / component
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError:
            raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path cannot be inspected") from None
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise RegenerationError("REGENERATION_PATH_UNSAFE", "project path contains a redirect")


def _is_known_ancestor(path: str, known: Iterable[str]) -> bool:
    return any(item.startswith(path + "/") for item in known)


def _inside_user(path: str) -> bool:
    return any(path == root or path.startswith(root + "/") for root in _USER_ROOTS)


def _inside_derived(path: str) -> bool:
    return path in _DERIVED_FIXED or path.startswith("build/") or path == "build" or path.startswith("artifacts/") or path == "artifacts"


def _ownership_for(path: str, toolkit: set[str], cubemx: set[str]) -> str | None:
    # Exact precedence is part of the public contract.
    if path in toolkit or _is_known_ancestor(path, toolkit):
        return "toolkit"
    if path in cubemx or _is_known_ancestor(path, cubemx):
        return "cubemx"
    if _inside_user(path):
        return "user"
    if _inside_derived(path):
        return "derived"
    if path == ".stm32-toolkit" or path == ".stm32-project.json":
        return "toolkit"
    return None


def _scan(root: Path, toolkit: set[str], cubemx: set[str]) -> tuple[tuple[InventoryEntry, ...], dict[str, bytes]]:
    """Inventory every current path without following redirects."""
    root_info = _safe_lstat(root)
    if not stat.S_ISDIR(root_info.st_mode):
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX project root is not a directory")
    paths: list[str] = []
    records: list[InventoryEntry] = []
    bytes_by_path: dict[str, bytes] = {}
    total = 0
    files = 0
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            children = sorted(current.iterdir(), key=lambda value: portable_sort_key(value.name))
        except OSError:
            raise RegenerationError("REGENERATION_PATH_UNSAFE", "project directory cannot be inspected") from None
        for child in children:
            relative = _relative_path(root, child)
            paths.append(relative)
            info = _safe_lstat(child)
            ownership = _ownership_for(relative, toolkit, cubemx)
            if stat.S_ISDIR(info.st_mode):
                if ownership is None:
                    raise RegenerationError("REGENERATION_UNKNOWN_PATH", "project contains an unknown path", {"path": relative})
                records.append(InventoryEntry(relative, "dir", 0, None, ownership))
                pending.append(child)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise RegenerationError("REGENERATION_PATH_UNSAFE", "project contains a special file", {"path": relative})
            files += 1
            if files > MAX_FILES:
                raise RegenerationError("REGENERATION_PATH_UNSAFE", "project file count exceeds its bound")
            data, size = _read_file(child)
            total += size
            if total > MAX_TOTAL_BYTES:
                raise RegenerationError("REGENERATION_PATH_UNSAFE", "project aggregate size exceeds its bound")
            digest = sha256_hex(data)
            if ownership is None:
                raise RegenerationError("REGENERATION_UNKNOWN_PATH", "project contains an unknown path", {"path": relative})
            records.append(InventoryEntry(relative, "file", size, digest, ownership))
            bytes_by_path[relative] = data
    collision = casefold_collision(paths)
    if collision is not None:
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "project contains a case-fold path collision", {"path": collision})
    records.sort(key=lambda item: portable_sort_key(item.path))
    return tuple(records), bytes_by_path


def _parse_json(data: bytes) -> object:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, ValueError, TypeError):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "ownership manifest is invalid") from None


def _validate_ownership_manifest(root: Path) -> tuple[bytes, tuple[dict[str, object], ...]]:
    path = root / ".stm32-toolkit" / "cubemx-ownership.json"
    try:
        data, _ = _read_file(path, limit=MAX_OWNERSHIP_MANIFEST_BYTES)
    except RegenerationError:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership manifest is unavailable") from None
    payload = _parse_json(data)
    if not isinstance(payload, dict):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership manifest is invalid")
    required = {"schemaVersion", "tool", "generator", "source", "planId", "actionDigest", "executionEnvironmentDigest", "files"}
    if set(payload) != required or payload.get("schemaVersion") != 1 or payload.get("tool") != "stm32-toolkit":
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership manifest is invalid")
    generator = payload.get("generator")
    source = payload.get("source")
    if not isinstance(generator, dict) or set(generator) != {"tool", "version", "executableSha256"}:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX generator facts are invalid")
    if generator.get("tool") != "stm32-cubemx" or not isinstance(generator.get("version"), str) or not _digest(generator.get("executableSha256")):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX generator facts are invalid")
    if not isinstance(source, dict) or set(source) != {"packageName", "packageVersion", "packageSha256"} or not all(isinstance(source.get(item), str) for item in source):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX package facts are invalid")
    if not _digest(source.get("packageSha256")):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX package facts are invalid")
    if not _digest(payload.get("planId")) or not _digest(payload.get("actionDigest")) or not _digest(payload.get("executionEnvironmentDigest")):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership binding is invalid")
    values = payload.get("files")
    if not isinstance(values, list):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership file list is invalid")
    rows: list[dict[str, object]] = []
    paths: list[str] = []
    for item in values:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership file list is invalid")
        rel = item.get("path")
        size = item.get("size")
        digest = item.get("sha256")
        if (
            not isinstance(rel, str)
            or unicodedata.normalize("NFC", rel) != rel
            or "\\" in rel
            or portable_path_error(rel) is not None
            or len(rel.encode("utf-8")) > MAX_RELATIVE_BYTES
            or len(Path(rel).parts) > MAX_PATH_DEPTH
            or rel.startswith(".stm32-toolkit/")
            or rel == ".stm32-project.json"
        ):
            raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership path is invalid")
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES or not _digest(digest):
            raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership file facts are invalid")
        paths.append(rel)
        rows.append({"path": rel, "size": size, "sha256": digest})
    if len(set(paths)) != len(paths) or casefold_collision(paths) is not None:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership paths are not canonical")
    rows.sort(key=lambda item: portable_sort_key(str(item["path"])))
    return data, tuple(rows)


def _managed_facts(root: Path, model_sha256: str) -> tuple[bytes, str, tuple[str, ...]]:
    path = root / MANAGED_MANIFEST_PATH
    try:
        data, _ = _read_file(path, limit=MAX_RECORD_BYTES)
    except RegenerationError:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "Toolkit managed manifest is unavailable") from None
    try:
        records = parse_managed_manifest(data)
    except Exception:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "Toolkit managed manifest is invalid") from None
    payload = _parse_json(data)
    if not isinstance(payload, dict) or payload.get("projectManifestSha256") != model_sha256:
        raise RegenerationError("REGENERATION_TOOLKIT_DRIFT", "Toolkit managed model hash does not match the project")
    paths = tuple(record.path for record in records)
    if any(path not in GENERATED_TARGETS for path in paths):
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "Toolkit managed path is outside the closed target set")
    return data, sha256_hex(data), paths


def _model_hash(model: ProjectModel) -> str:
    # Reuse the canonical managed-file model hash implementation without
    # introducing a second ProjectModel serializer.
    from stm32_toolkit.generation.managed_files import model_sha256_for

    return model_sha256_for(model)


def _ioc_language(root: Path, path: str) -> str:
    try:
        data, _ = _read_file(root.joinpath(*path.split("/")), limit=MAX_IOC_BYTES)
        text = data.decode("utf-8")
    except (RegenerationError, UnicodeDecodeError):
        return "c"
    match = _IOCPROP.search(text)
    return "cpp" if match and match.group(1).strip().casefold() in {"c++", "cpp"} else "c"


def _creation_request(model: ProjectModel, root: Path, ioc_path: str, ioc_sha256: str) -> CreationRequest:
    try:
        request = CreationRequest.from_ioc(
            ioc_path,
            root.name,
            framework=model.framework.type,
            language=_ioc_language(root, ioc_path),
        )
    except Exception:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX regeneration inputs are invalid") from None
    source = request.source
    from stm32_toolkit.generation.creation import CreationSource

    return CreationRequest(CreationSource("ioc", source.value, ioc_sha256), request.destination, request.framework, request.language)


def _environment_facts(environment: object | None) -> tuple[str, dict[str, object], dict[str, object]]:
    if environment is None:
        return "", {}, {}
    digest = str(getattr(environment, "digest", ""))
    if not _digest(digest):
        return "", {}, {}
    generator = {
        "tool": "stm32-cubemx",
        "version": str(getattr(environment, "cubemx_version", "")),
        "executableSha256": str(getattr(environment, "cubemx_sha256", "")),
    }
    package = {
        "name": str(getattr(environment, "package_name", "")),
        "version": str(getattr(environment, "package_version", "")),
        "sha256": str(getattr(environment, "package_sha256", "")),
    }
    return digest, generator, package


def _resolve_environment(
    request: RegenerationWorkflowRequest,
    model: ProjectModel,
    ioc_path: str,
    ioc_sha256: str,
    *,
    support_profile: ToolSupportProfile | None,
    repository: Path | None,
    environment: object | None,
) -> tuple[object | None, RegenerationBlocker | None]:
    if environment is not None:
        digest, generator, package = _environment_facts(environment)
        if (
            not _digest(digest)
            or generator.get("tool") != "stm32-cubemx"
            or not isinstance(generator.get("version"), str)
            or not generator.get("version")
            or not _digest(generator.get("executableSha256"))
            or not isinstance(package.get("name"), str)
            or not package.get("name")
            or not isinstance(package.get("version"), str)
            or not package.get("version")
            or not _digest(package.get("sha256"))
        ):
            return environment, RegenerationBlocker("REGENERATION_GENERATOR_DRIFT", "", "CubeMX execution facts are invalid")
        return environment, None
    try:
        support = support_profile or discover_tool_support(SupportProfileRequest(data_root=request.data_root))
        creation = _creation_request(model, request.project_root, ioc_path, ioc_sha256)
        resolved = discover_creation_environment(support, creation, repository=repository, project_root=request.project_root)
        return resolved, None
    except (CreationEnvironmentError, SupportProfileError, OSError, ValueError, RuntimeError):
        return None, RegenerationBlocker("REGENERATION_GENERATOR_DRIFT", "", "CubeMX execution facts are unavailable")


def _classify_snapshot(
    model: ProjectModel,
    inventory: tuple[InventoryEntry, ...],
    bytes_by_path: Mapping[str, bytes],
    ownership_rows: tuple[dict[str, object], ...],
    ownership_bytes: bytes,
    managed_bytes: bytes,
    managed_digest: str,
    model_sha256: str,
) -> OwnershipSnapshot:
    ownership_paths = {str(row["path"]) for row in ownership_rows}
    managed_paths = {path for path in GENERATED_TARGETS if any(entry.path == path for entry in parse_managed_manifest(managed_bytes))}
    toolkit_paths = set(_TOOLKIT_FIXED) | managed_paths
    ioc_path = model.generation.cube_mx_ioc
    if not isinstance(ioc_path, str) or portable_path_error(ioc_path) is not None:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX IOC path is invalid")
    if ioc_path not in ownership_paths:
        raise RegenerationError("REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership manifest does not declare the IOC")
    prior_rows = {str(row["path"]): row for row in ownership_rows}
    prior_ioc = str(prior_rows[ioc_path]["sha256"])
    current_ioc = str(next((entry.sha256 for entry in inventory if entry.path == ioc_path and entry.kind == "file"), ""))
    if not _digest(current_ioc):
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX IOC is unavailable")
    blockers: list[RegenerationBlocker] = []
    actual_by_path = {entry.path: entry for entry in inventory}
    for path, row in sorted(prior_rows.items(), key=lambda item: portable_sort_key(item[0])):
        entry = actual_by_path.get(path)
        if entry is None or entry.kind != "file":
            blockers.append(RegenerationBlocker("REGENERATION_STATE_CHANGED", path, "CubeMX-owned file is missing"))
        elif path != ioc_path and (entry.size != int(row["size"]) or entry.sha256 != row["sha256"]):
            blockers.append(RegenerationBlocker("REGENERATION_STATE_CHANGED", path, "CubeMX-owned file drifted"))
    for path in sorted(managed_paths, key=portable_sort_key):
        entry = actual_by_path.get(path)
        record = next((item for item in parse_managed_manifest(managed_bytes) if item.path == path), None)
        if entry is None or entry.kind != "file" or record is None or entry.sha256 != record.sha256 or entry.size != len(bytes_by_path.get(path, b"")):
            blockers.append(RegenerationBlocker("REGENERATION_TOOLKIT_DRIFT", path, "Toolkit-managed file drifted"))
    # The inventory has already rejected unknown paths.  Check the closed user
    # roots explicitly so a project model that changes the ownership boundary
    # can never silently broaden it.
    if tuple(model.generation.generated_directories) != ("Core", "Drivers"):
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "generated ownership roots are not the closed Core/Drivers set")
    if tuple(model.generation.user_directories) != _USER_ROOTS:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "user ownership roots are not the closed App/Tests set")
    inventory_by_path = {entry.path: entry for entry in inventory}
    for root_name in _USER_ROOTS:
        root_entry = inventory_by_path.get(root_name)
        if root_entry is not None and root_entry.kind != "dir":
            blockers.append(RegenerationBlocker("REGENERATION_PATH_UNSAFE", root_name, "user ownership root is not a directory"))
    return OwnershipSnapshot(
        model=model,
        inventory=inventory,
        ownership_rows=ownership_rows,
        ownership_manifest_bytes=ownership_bytes,
        ownership_manifest_digest=sha256_hex(ownership_bytes),
        managed_manifest_bytes=managed_bytes,
        managed_manifest_digest=managed_digest,
        model_sha256=model_sha256,
        prior_ioc_sha256=prior_ioc,
        current_ioc_sha256=current_ioc,
        blockers=tuple(sorted(blockers, key=lambda item: (item.code, portable_sort_key(item.path)))),
        file_bytes=bytes_by_path,
    )


def _load_snapshot(request: RegenerationWorkflowRequest) -> OwnershipSnapshot:
    _assert_destination_lexical_path_safe(request)
    root = request.destination_canonical
    try:
        raw_manifest = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raw_manifest = None
    try:
        model = load_project_model(root)
    except ProjectManifestError as error:
        if isinstance(raw_manifest, dict) and raw_manifest.get("schemaVersion") == 2:
            raise RegenerationError("REGENERATION_NOT_CUBEMX_PROJECT", "the destination is not a CubeMX project") from None
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "the CubeMX project manifest is invalid") from None
    if model.schema_version != 3 or model.project.origin.casefold() != "cubemx":
        raise RegenerationError("REGENERATION_NOT_CUBEMX_PROJECT", "the destination is not a CubeMX project")
    if model.generation.tool != "stm32-toolkit" or model.generation.managed_manifest != MANAGED_MANIFEST_PATH:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "the CubeMX project generation contract is invalid")
    ownership_bytes, ownership_rows = _validate_ownership_manifest(root)
    model_sha = _model_hash(model)
    managed_bytes, managed_digest, _ = _managed_facts(root, model_sha)
    toolkit_paths = set(_TOOLKIT_FIXED) | {record.path for record in parse_managed_manifest(managed_bytes)}
    cubemx_paths = {str(row["path"]) for row in ownership_rows}
    inventory, bytes_by_path = _scan(root, toolkit_paths, cubemx_paths)
    return _classify_snapshot(model, inventory, bytes_by_path, ownership_rows, ownership_bytes, managed_bytes, managed_digest, model_sha)


def _state_payload(request: RegenerationWorkflowRequest, snapshot: OwnershipSnapshot, git: GitEvidence | None) -> dict[str, object]:
    rows = [entry.to_dict() for entry in snapshot.inventory if entry.ownership != "derived"]
    return {
        "request": request.canonical_dict(),
        "logicalProjectId": str(snapshot.model.logical_project_id),
        "gitHead": git.head if git else "",
        "ownershipManifestSha256": snapshot.ownership_manifest_digest,
        "managedManifestSha256": snapshot.managed_manifest_digest,
        "modelSha256": snapshot.model_sha256,
        "files": rows,
    }


def _counts(inventory: Iterable[InventoryEntry]) -> dict[str, int]:
    result = {"cubeMxOwned": 0, "toolkitOwned": 0, "userOwned": 0, "derived": 0, "files": 0, "directories": 0}
    for entry in inventory:
        owner_key = {
            "cubemx": "cubeMxOwned",
            "toolkit": "toolkitOwned",
            "user": "userOwned",
            "derived": "derived",
        }[entry.ownership]
        result[owner_key] += 1
        if entry.kind == "file":
            result["files"] += 1
        else:
            result["directories"] += 1
    return result


def build_regeneration_plan(
    request: RegenerationWorkflowRequest,
    *,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    environment: object | None = None,
    now: datetime | None = None,
) -> RegenerationPlan:
    if not isinstance(request, RegenerationWorkflowRequest):
        raise RegenerationInputError("REGENERATION_INPUT_INVALID", "request")
    try:
        snapshot = _load_snapshot(request)
    except RegenerationError:
        raise
    env, env_blocker = _resolve_environment(
        request,
        snapshot.model,
        snapshot.ioc_path,
        snapshot.current_ioc_sha256,
        support_profile=support_profile,
        repository=repository,
        environment=environment,
    )
    blockers = list(snapshot.blockers)
    if env_blocker is not None:
        blockers.append(env_blocker)
    env_digest, generator, package = _environment_facts(env)
    recorded_generator = next((row for row in _parse_json(snapshot.ownership_manifest_bytes).get("generator", {}).items()), None) if False else None
    payload = _parse_json(snapshot.ownership_manifest_bytes)
    if isinstance(payload, dict):
        recorded_gen = payload.get("generator")
        recorded_pkg = payload.get("source")
        if env is not None and isinstance(recorded_gen, dict) and isinstance(recorded_pkg, dict):
            if (
                payload.get("executionEnvironmentDigest") != env_digest
                or
                recorded_gen.get("tool") != generator.get("tool")
                or recorded_gen.get("version") != generator.get("version")
                or recorded_gen.get("executableSha256") != generator.get("executableSha256")
                or recorded_pkg.get("packageName") != package.get("name")
                or recorded_pkg.get("packageVersion") != package.get("version")
                or recorded_pkg.get("packageSha256") != package.get("sha256")
            ):
                blockers.append(RegenerationBlocker("REGENERATION_GENERATOR_DRIFT", "", "CubeMX generator or package facts drifted"))
    try:
        git = git_evidence(request.workspace_root)
    except Exception:
        git = None
        blockers.append(RegenerationBlocker("BUILD_GIT_INVALID", "", "Git HEAD evidence is unavailable"))
    state_digest = sha256_hex(canonical_json_bytes(_state_payload(request, snapshot, git)))
    blockers = sorted({(item.code, item.path, item.message): item for item in blockers}.values(), key=lambda item: (item.code, portable_sort_key(item.path), item.message))
    plan_payload = {
        "schemaVersion": REGENERATION_SCHEMA_VERSION,
        "request": request.canonical_dict(),
        "logicalProjectId": str(snapshot.model.logical_project_id),
        "device": snapshot.model.target.device,
        "iocPath": snapshot.ioc_path,
        "currentIocSha256": snapshot.current_ioc_sha256,
        "priorOwnedIocSha256": snapshot.prior_ioc_sha256,
        "gitHead": git.head if git else "",
        "projectStateDigest": state_digest,
        "ownershipManifestDigest": snapshot.ownership_manifest_digest,
        "managedManifestDigest": snapshot.managed_manifest_digest,
        "managedManifestModelSha256": snapshot.model_sha256,
        "executionEnvironmentDigest": env_digest,
        "generator": generator,
        "package": package,
        "counts": _counts(snapshot.inventory),
        "blockers": [item.to_dict() for item in blockers],
    }
    plan_id = sha256_hex(canonical_json_bytes(plan_payload))
    action_payload = {
        "operation": "project-regenerate",
        "planId": plan_id,
        "destination": request.destination_canonical.as_posix(),
        "workspaceRoot": request.workspace_root.as_posix(),
        "executionEnvironmentDigest": env_digest,
        "projectStateDigest": state_digest,
        "destinationState": snapshot.ownership_manifest_digest,
    }
    action_digest = sha256_hex(canonical_json_bytes(action_payload))
    return RegenerationPlan(
        schema_version=REGENERATION_SCHEMA_VERSION,
        request=request,
        logical_project_id=str(snapshot.model.logical_project_id),
        device=snapshot.model.target.device,
        ioc_path=snapshot.ioc_path,
        current_ioc_sha256=snapshot.current_ioc_sha256,
        prior_owned_ioc_sha256=snapshot.prior_ioc_sha256,
        git_head=git.head if git else "",
        project_state_digest=state_digest,
        ownership_manifest_digest=snapshot.ownership_manifest_digest,
        managed_manifest_digest=snapshot.managed_manifest_digest,
        model_sha256=snapshot.model_sha256,
        execution_environment_digest=env_digest,
        generator=generator,
        package=package,
        counts=_counts(snapshot.inventory),
        blockers=tuple(blockers),
        expires_at=_expiry(now or datetime.now(timezone.utc)),
        plan_id=plan_id,
        action_digest=action_digest,
        model=snapshot.model,
        inventory=snapshot.inventory,
        git=git,
        environment=env,
    )


def _file_inventory_payload(inventory: Iterable[InventoryEntry]) -> list[dict[str, object]]:
    return [entry.to_dict() for entry in sorted(inventory, key=lambda item: portable_sort_key(item.path)) if entry.ownership != "derived"]


def _make_diff(path: str, before: bytes | None, after: bytes | None) -> str | None:
    if before is None or after is None:
        return None
    # Text diffs are optional display evidence.  Large or binary generated
    # files remain fully represented by their hashes and sizes, while their
    # optional diff is omitted rather than making a valid replacement
    # impossible to review.
    try:
        old_text = before.decode("utf-8")
        new_text = after.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(before) > MAX_DIFF_BYTES or len(after) > MAX_DIFF_BYTES:
        return None
    old = old_text.splitlines(keepends=True)
    new = new_text.splitlines(keepends=True)
    result = "".join(difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="\n"))
    if len(result.encode("utf-8")) > MAX_DIFF_BYTES:
        return None
    return result


def build_regeneration_preview(
    before: OwnershipSnapshot,
    after: OwnershipSnapshot,
) -> RegenerationPreview:
    before_by_path = {entry.path: entry for entry in before.inventory if entry.ownership != "derived"}
    after_by_path = {entry.path: entry for entry in after.inventory if entry.ownership != "derived"}
    all_paths = sorted(set(before_by_path) | set(after_by_path), key=portable_sort_key)
    changes: list[ChangeRecord] = []
    display_bytes = 0
    replacement_rows: list[dict[str, object]] = []
    for path in all_paths:
        old = before_by_path.get(path)
        new = after_by_path.get(path)
        if new is not None:
            replacement_rows.append(new.to_dict())
        if old is not None and new is not None and old.kind == new.kind and old.size == new.size and old.sha256 == new.sha256 and old.ownership == new.ownership:
            continue
        if old is None:
            status = "added"
        elif new is None:
            status = "deleted"
        else:
            status = "modified"
        before_bytes = before.file_bytes.get(path)
        after_bytes = after.file_bytes.get(path)
        diff = _make_diff(path, before_bytes, after_bytes) if status == "modified" else None
        if diff:
            display_bytes += len(diff.encode("utf-8"))
        if display_bytes > MAX_PREVIEW_BYTES:
            raise RegenerationError("REGENERATION_PREVIEW_TOO_LARGE", "regeneration preview exceeds its display bound")
        changes.append(ChangeRecord(path, status, old.sha256 if old else None, new.sha256 if new else None, old.size if old else None, new.size if new else None, diff, old.ownership if old else None, new.ownership if new else None))
    replacement_digest = sha256_hex(canonical_json_bytes(replacement_rows))
    ownership_payload = {
        "before": _file_inventory_payload(before.inventory),
        "after": _file_inventory_payload(after.inventory),
        "beforeOwnership": before.ownership_manifest_digest,
        "afterOwnership": after.ownership_manifest_digest,
        "beforeManaged": before.managed_manifest_digest,
        "afterManaged": after.managed_manifest_digest,
    }
    ownership_digest = sha256_hex(canonical_json_bytes(ownership_payload))
    digest_payload = {
        "schemaVersion": REGENERATION_SCHEMA_VERSION,
        "replacementInventory": replacement_rows,
        "ownershipTransition": ownership_payload,
        "changes": [
            {
                "path": item.path,
                "status": item.status,
                "beforeSha256": item.before_sha256,
                "afterSha256": item.after_sha256,
                "beforeSize": item.before_size,
                "afterSize": item.after_size,
                "ownershipBefore": item.ownership_before,
                "ownershipAfter": item.ownership_after,
            }
            for item in changes
        ],
    }
    counts = {
        "added": sum(item.status == "added" for item in changes),
        "modified": sum(item.status == "modified" for item in changes),
        "deleted": sum(item.status == "deleted" for item in changes),
        "unchanged": len(all_paths) - len(changes),
        "cubeMxOwned": sum(item.ownership == "cubemx" for item in after.inventory),
        "toolkitOwned": sum(item.ownership == "toolkit" for item in after.inventory),
        "userOwned": sum(item.ownership == "user" for item in after.inventory),
        "derived": sum(item.ownership == "derived" for item in after.inventory),
    }
    return RegenerationPreview(sha256_hex(canonical_json_bytes(digest_payload)), tuple(changes), counts, replacement_digest, ownership_digest)


def plan_regeneration(
    request: RegenerationWorkflowRequest,
    *,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    environment: object | None = None,
) -> object:
    """Neutral read-only plan adapter returning an OperationResult."""
    from stm32_toolkit.result import OperationResult

    operation = "project-regenerate-plan"
    try:
        plan = build_regeneration_plan(request, support_profile=support_profile, repository=repository, environment=environment)
    except RegenerationInputError as error:
        return OperationResult.failure(operation, error.code, error.message, {"field": error.field})
    except RegenerationError as error:
        return OperationResult.failure(operation, error.code, error.message, error.details)
    except Exception:
        return OperationResult.failure(operation, "REGENERATION_PROJECT_INVALID", "the CubeMX project is unavailable", {})
    return OperationResult.success(operation, plan.to_dict())


plan_project_regeneration = build_regeneration_plan
classify_regeneration_project = _load_snapshot


__all__ = [
    "ChangeRecord",
    "InventoryEntry",
    "OwnershipSnapshot",
    "RegenerationBlocker",
    "RegenerationError",
    "RegenerationInputError",
    "RegenerationPlan",
    "RegenerationPreview",
    "RegenerationWorkflowRequest",
    "build_regeneration_plan",
    "build_regeneration_preview",
    "classify_regeneration_project",
    "plan_project_regeneration",
    "plan_regeneration",
    "MAX_DIFF_BYTES",
    "MAX_OWNERSHIP_MANIFEST_BYTES",
    "MAX_PREVIEW_BYTES",
]
