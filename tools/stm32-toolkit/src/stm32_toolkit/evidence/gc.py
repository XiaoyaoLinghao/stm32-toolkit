"""Conservative, reachability-based collection for immutable evidence objects."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
from types import MappingProxyType
from typing import Mapping
from unicodedata import normalize
import weakref

from .model import (
    EVIDENCE_CORRUPT,
    EVIDENCE_INVALID,
    EVIDENCE_LIMIT_EXCEEDED,
    EVIDENCE_PATH_UNSAFE,
    EvidenceEnvelope,
    EvidenceValidationError,
    MAX_ENVELOPE_BYTES,
    canonical_json_bytes,
)
from .store import EvidenceStore


GC_PLAN_SCHEMA = "stm32-evidence-gc-plan/1"
GC_RESULT_SCHEMA = "stm32-evidence-gc-result/1"
REGISTERED_ROOT_TYPES = frozenset(
    {
        "test-run",
        "diagnostic-session",
        "bundle",
        "annotation",
        "monitor-run",
        "monitor-analysis",
        "diagnostic-marker",
    }
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PREFIX = re.compile(r"^[0-9a-f]{2}$")
_ROOT_FIELDS = {"root_type", "root_id", "manifest_id", "metadata"}
_AUTHORIZATION_LEDGER_PRIMARY = ".stm32-evidence-gc-ledger"
_AUTHORIZATION_LEDGER_SECONDARY = ".stm32-evidence-gc-ledger-alt"


GC_STORE_CHANGED_MESSAGE = "evidence store changed during GC"


class GcStoreChangedError(Exception):
    """The object selected by the plan no longer has the captured identity."""

    code = "GC_STORE_CHANGED"

    def __init__(self) -> None:
        Exception.__init__(self, GC_STORE_CHANGED_MESSAGE)


@dataclass(frozen=True)
class _DeleteOutcome:
    size: int
    committed: bool
    error: str | None = None


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _ordered(values) -> tuple[str, ...]:
    return tuple(sorted(values, key=lambda value: value.encode("utf-8")))


def _json_copy(value: object) -> object:
    return json.loads(canonical_json_bytes(value))


def _canonical_root_bytes(value: Mapping[str, object]) -> bytes:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_ENVELOPE_BYTES:
        raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "root bytes exceed the evidence limit")
    return payload


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _validate_root_key(root_type: object, root_id: object) -> tuple[str, str]:
    if not isinstance(root_type, str) or root_type not in REGISTERED_ROOT_TYPES:
        raise EvidenceValidationError(EVIDENCE_INVALID, "root_type is not registered")
    if (
        not isinstance(root_id, str)
        or not root_id
        or normalize("NFC", root_id) != root_id
        or len(root_id.encode("utf-8")) > 64 * 1024
        or any(ord(character) < 32 or ord(character) == 127 for character in root_id)
        or any(character in root_id for character in "/\\:")
        or root_id in {".", ".."}
    ):
        raise EvidenceValidationError(EVIDENCE_INVALID, "root_id is not a canonical path-safe bounded string")
    return root_type, root_id


def _windows_file_information(handle: int) -> dict[str, int]:
    """Return stable Win32 identity/shape fields for an already-open handle."""
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("access_time", wintypes.FILETIME),
            ("write_time", wintypes.FILETIME),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(ByHandleFileInformation)]
    get_information.restype = wintypes.BOOL
    information = ByHandleFileInformation()
    if not get_information(handle, ctypes.byref(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "attributes": information.attributes,
        "links": information.links,
        "size": (information.size_high << 32) | information.size_low,
        "volume_serial": information.volume_serial,
        "file_index": (information.file_index_high << 32) | information.file_index_low,
    }


def _open_windows_file(path: Path, *, delete: bool = False) -> int:
    """Open exactly one path without traversing a final reparse point."""
    import ctypes
    from ctypes import wintypes

    generic_read = 0x80000000
    delete_access = 0x00010000
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    file_share_delete = 0x00000004
    open_existing = 3
    open_reparse_point = 0x00200000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    access = generic_read | file_read_attributes | (delete_access if delete else 0)
    sharing = file_share_read
    if not delete:
        sharing |= file_share_write | file_share_delete
    handle = create_file(
        str(path), access, sharing, None, open_existing, open_reparse_point, None
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def _close_windows_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    if not close_handle(handle):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def _stable_parent_guard(parent: Path, expected: os.stat_result):
    """Pin the existing ledger parent identity while its fixed sibling is accessed."""
    if os.name != "nt":  # pragma: no cover - unsupported destructive platform
        raise EvidenceValidationError(EVIDENCE_INVALID,
            "stable authorization ledger parent locking is unavailable"
        )
    import ctypes
    from ctypes import wintypes

    generic_read = 0x80000000
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    open_reparse_point = 0x00200000
    backup_semantics = 0x02000000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(parent),
        generic_read | file_read_attributes,
        file_share_read | file_share_write,
        None,
        open_existing,
        open_reparse_point | backup_semantics,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = int(handle)
    try:
        opened = _windows_file_information(handle)
        current = EvidenceStore._validate_existing_path(parent)
        if (
            not stat.S_ISDIR(expected.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or opened["attributes"] & 0x00000400
            or not opened["attributes"] & 0x00000010
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
            or current.st_ino != opened["file_index"]
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                "authorization ledger parent identity changed"
            )
        yield
    finally:
        _close_windows_handle(handle)


def _file_identity_fields(path: Path, info: os.stat_result) -> dict[str, object]:
    fields: dict[str, object] = {
        "device": str(info.st_dev),
        "inode": str(info.st_ino),
    }
    if os.name != "nt":  # pragma: no cover - Linux acceptance is intentionally fail closed
        return fields  # pragma: no cover
    handle = _open_windows_file(path)
    try:
        opened = _windows_file_information(handle)
        if (
            opened["links"] != info.st_nlink
            or opened["size"] != info.st_size
            or opened["attributes"] & 0x00000400
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "file identity changed while it was captured")
        fields.update(
            {
                "volume_serial": str(opened["volume_serial"]),
                "file_index": str(opened["file_index"]),
            }
        )
        return fields
    finally:
        _close_windows_handle(handle)


@dataclass(frozen=True)
class RootRecord:
    """One closed typed root record."""

    root_type: str
    root_id: str
    manifest_id: str
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        _validate_root_key(self.root_type, self.root_id)
        if not isinstance(self.manifest_id, str) or _HASH.fullmatch(self.manifest_id) is None:
            raise EvidenceValidationError(EVIDENCE_INVALID, "manifest_id must be a lowercase SHA-256")
        if not isinstance(self.metadata, Mapping):
            raise EvidenceValidationError(EVIDENCE_INVALID, "root metadata must be a JSON object")
        copied = _json_copy(self.metadata)
        if not isinstance(copied, dict):
            raise EvidenceValidationError(EVIDENCE_INVALID, "root metadata must be a JSON object")
        object.__setattr__(self, "metadata", _freeze_json(copied))
        _canonical_root_bytes(self.to_dict())

    @classmethod
    def from_value(cls, value: object) -> "RootRecord":
        if not isinstance(value, Mapping) or set(value) != _ROOT_FIELDS:
            raise EvidenceValidationError(EVIDENCE_INVALID, "root record fields are not closed")
        return cls(
            root_type=value["root_type"],  # type: ignore[arg-type]
            root_id=value["root_id"],  # type: ignore[arg-type]
            manifest_id=value["manifest_id"],  # type: ignore[arg-type]
            metadata=value["metadata"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_type": self.root_type,
            "root_id": self.root_id,
            "manifest_id": self.manifest_id,
            "metadata": _json_copy(self.metadata),
        }


@dataclass(frozen=True, eq=False)
class GcPlan:
    """Immutable canonical dry-run document; prepare authority is held out-of-object."""

    store_root: str
    store_id: str
    roots: tuple[RootRecord, ...]
    manifest_ids: tuple[str, ...]
    reachable_manifests: tuple[str, ...]
    unreachable_manifests: tuple[str, ...]
    reachable_objects: tuple[str, ...]
    unreachable_objects: tuple[str, ...]
    unknown_entries: tuple[str, ...]
    corrupt_entries: tuple[str, ...]
    bytes_reclaimable: int
    manifest_snapshot_digest: str
    store_snapshot_digest: str
    plan_digest: str
    action_digest: str
    schema: str = field(default=GC_PLAN_SCHEMA, init=False)

    def _document_without_digest(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "store_root": self.store_root,
            "store_id": self.store_id,
            "roots": [root.to_dict() for root in self.roots],
            "manifest_ids": list(self.manifest_ids),
            "reachable_manifests": list(self.reachable_manifests),
            "unreachable_manifests": list(self.unreachable_manifests),
            "reachable_objects": list(self.reachable_objects),
            "unreachable_objects": list(self.unreachable_objects),
            "unknown_entries": list(self.unknown_entries),
            "corrupt_entries": list(self.corrupt_entries),
            "bytes_reclaimable": self.bytes_reclaimable,
            "manifest_snapshot_digest": self.manifest_snapshot_digest,
            "store_snapshot_digest": self.store_snapshot_digest,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._document_without_digest(), "plan_digest": self.plan_digest}

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class GcResult:
    """Exact terminal outcome; partial progress can never compare equal to success."""

    success: bool
    code: str
    plan_digest: str
    action_digest: str
    deleted_manifests: tuple[str, ...]
    retained_manifests: tuple[str, ...]
    deleted_objects: tuple[str, ...]
    retained_objects: tuple[str, ...]
    bytes_reclaimed: int
    errors: tuple[str, ...]
    schema: str = field(default=GC_RESULT_SCHEMA, init=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "success": self.success,
            "code": self.code,
            "plan_digest": self.plan_digest,
            "action_digest": self.action_digest,
            "deleted_manifests": list(self.deleted_manifests),
            "retained_manifests": list(self.retained_manifests),
            "deleted_objects": list(self.deleted_objects),
            "retained_objects": list(self.retained_objects),
            "bytes_reclaimed": self.bytes_reclaimed,
            "errors": list(self.errors),
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass
class _PreparedGcPlan:
    store: EvidenceStore
    store_root: str
    store_id: str
    plan_digest: str
    action_digest: str
    manifest_snapshot_digest: str
    store_snapshot_digest: str
    bytes_reclaimable: int
    unreachable_manifests: tuple[str, ...]
    unreachable_objects: tuple[str, ...]
    target_sizes: Mapping[str, int]
    snapshot_entries: tuple[dict[str, object], ...]
    canonical_plan: bytes
    consumed: bool = False
    consume_lock: threading.Lock = field(default_factory=threading.Lock)


_PREPARED_REGISTRY_LOCK = threading.Lock()
_PREPARED_BY_PLAN: weakref.WeakKeyDictionary[GcPlan, _PreparedGcPlan] = (
    weakref.WeakKeyDictionary()
)


def _relative(store: EvidenceStore, path: Path) -> str:
    return path.relative_to(store.root).as_posix()


def _snapshot_entries(
    store: EvidenceStore,
    *,
    phase: str | None = None,
    excluded: set[str] | frozenset[str] = frozenset(),
) -> tuple[dict[str, object], ...]:
    """Snapshot every roots/manifests/objects entry without following links."""
    entries: list[dict[str, object]] = []
    top_states: dict[str, os.stat_result | None] = {}
    directory_states: dict[Path, os.stat_result] = {}
    for top_name in ("roots", "manifests", "objects"):
        try:
            top_states[top_name] = (store.root / top_name).lstat()
        except FileNotFoundError:
            top_states[top_name] = None
    for top_name in ("roots", "manifests", "objects"):
        top = store.root / top_name
        top_info = top_states[top_name]
        if top_info is None:
            if phase is not None:
                store._fault(f"{phase}.after-top.{top_name}")
            continue
        top_is_link = stat.S_ISLNK(top_info.st_mode) or store._is_reparse(top_info)
        if top_is_link or not stat.S_ISDIR(top_info.st_mode):
            entries.append(
                {
                    "path": top_name,
                    "kind": "link" if top_is_link else "special",
                    "mode": stat.S_IFMT(top_info.st_mode),
                    "links": top_info.st_nlink,
                    "size": top_info.st_size,
                    "mtime_ns": top_info.st_mtime_ns,
                }
            )
            if phase is not None:
                store._fault(f"{phase}.after-top.{top_name}")
            continue
        directory_states[top] = top_info
        pending = [top]
        while pending:
            parent = pending.pop()
            for path in sorted(parent.iterdir(), key=lambda item: item.name.encode("utf-8")):
                info = path.lstat()
                relative = _relative(store, path)
                if relative in excluded:
                    continue
                kind = (
                    "link"
                    if stat.S_ISLNK(info.st_mode) or store._is_reparse(info)
                    else "directory"
                    if stat.S_ISDIR(info.st_mode)
                    else "file"
                    if stat.S_ISREG(info.st_mode)
                    else "special"
                )
                if kind == "directory":
                    directory_states[path] = info
                    entries.append(
                        {
                            "path": relative,
                            "kind": kind,
                            "mode": stat.S_IFMT(info.st_mode),
                            "links": info.st_nlink,
                        }
                    )
                    pending.append(path)
                    continue
                entry: dict[str, object] = {
                    "path": relative,
                    "kind": kind,
                    "mode": stat.S_IFMT(info.st_mode),
                    "links": info.st_nlink,
                    "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns,
                }
                if kind == "file" and info.st_nlink == 1:
                    try:
                        entry.update(_file_identity_fields(path, info))
                        _size, content_digest = store._hash_file(path, single_link=True)
                        entry["content_sha256"] = content_digest
                    except (OSError, EvidenceValidationError) as exc:
                        entry["read_error"] = type(exc).__name__
                entries.append(entry)
        after_top = top.lstat()
        if (
            stat.S_ISLNK(after_top.st_mode)
            or store._is_reparse(after_top)
            or not stat.S_ISDIR(after_top.st_mode)
            or (after_top.st_dev, after_top.st_ino)
            != (top_info.st_dev, top_info.st_ino)
            or after_top.st_mtime_ns != top_info.st_mtime_ns
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                f"managed directory changed while it was scanned: {top}"
            )
        if phase is not None:
            store._fault(f"{phase}.after-top.{top_name}")
    for top_name, before in top_states.items():
        top = store.root / top_name
        try:
            after = top.lstat()
        except FileNotFoundError:
            after = None
        if before is None:
            if after is not None:
                raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                    f"managed directory appeared while the store was scanned: {top}"
                )
            continue
        if after is None or (
            (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or after.st_mode != before.st_mode
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                f"managed directory changed while the store was scanned: {top}"
            )
    for directory, before in directory_states.items():
        try:
            after = directory.lstat()
        except FileNotFoundError as exc:
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                f"managed directory disappeared while the store was scanned: {directory}"
            ) from exc
        if (
            stat.S_ISLNK(after.st_mode)
            or store._is_reparse(after)
            or not stat.S_ISDIR(after.st_mode)
            or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                f"managed directory changed while the store was scanned: {directory}"
            )
    return tuple(sorted(entries, key=lambda item: str(item["path"]).encode("utf-8")))


def _filtered_snapshot_digest(
    entries: tuple[dict[str, object], ...], excluded: set[str] | frozenset[str] = frozenset()
) -> str:
    return _digest([entry for entry in entries if entry["path"] not in excluded])


def _scan_roots(
    store: EvidenceStore, entries: tuple[dict[str, object], ...]
) -> tuple[list[RootRecord], list[str], list[str], bool]:
    roots: list[RootRecord] = []
    unknown: list[str] = []
    corrupt: list[str] = []
    conservative = False
    root_entries = [
        entry
        for entry in entries
        if str(entry["path"]) == "roots" or str(entry["path"]).startswith("roots/")
    ]
    for entry in root_entries:
        relative = str(entry["path"])
        document: object = None
        if entry["kind"] == "directory":
            continue
        if (
            entry["kind"] != "file"
            or entry["links"] != 1
            or "read_error" in entry
            or not relative.endswith(".json")
        ):
            corrupt.append(relative)
            conservative = True
            continue
        path = store.root.joinpath(*relative.split("/"))
        try:
            payload = path.read_bytes()
            if (
                len(payload) != entry["size"]
                or hashlib.sha256(payload).hexdigest() != entry.get("content_sha256")
            ):
                raise EvidenceValidationError(EVIDENCE_CORRUPT, "root bytes differ from the captured snapshot")
            document = json.loads(payload)
            if canonical_json_bytes(document) != payload:
                raise EvidenceValidationError(EVIDENCE_CORRUPT, "root is not canonical JSON")
            root = RootRecord.from_value(document)
        except (OSError, UnicodeError, json.JSONDecodeError, EvidenceValidationError, TypeError, ValueError):
            candidate_type = document.get("root_type") if isinstance(document, Mapping) else None
            if isinstance(candidate_type, str) and candidate_type not in REGISTERED_ROOT_TYPES:
                unknown.append(relative)
            else:
                corrupt.append(relative)
            conservative = True
            continue
        roots.append(root)
    roots.sort(
        key=lambda root: canonical_json_bytes(root.to_dict())
    )
    return roots, unknown, corrupt, conservative


def _scan_manifests(
    store: EvidenceStore,
    entries: tuple[dict[str, object], ...],
    objects: Mapping[str, int],
) -> tuple[dict[str, EvidenceEnvelope], list[str], list[str]]:
    manifests: dict[str, EvidenceEnvelope] = {}
    unknown: list[str] = []
    corrupt: list[str] = []
    object_snapshot = {
        relative: (size, Path(relative).name) for relative, size in objects.items()
    }
    for entry in entries:
        relative = str(entry["path"])
        if relative != "manifests" and not relative.startswith("manifests/"):
            continue
        name = relative.removeprefix("manifests/")
        if entry["kind"] in {"link", "special"} or entry["links"] != 1:
            corrupt.append(relative)
            continue
        if "/" in name or not name.endswith(".json") or _HASH.fullmatch(name[:-5]) is None:
            unknown.append(relative)
            continue
        if entry["kind"] != "file" or entry["links"] != 1 or "read_error" in entry:
            corrupt.append(relative)
            continue
        try:
            payload = store.root.joinpath(*relative.split("/")).read_bytes()
            if (
                len(payload) != entry["size"]
                or hashlib.sha256(payload).hexdigest() != entry.get("content_sha256")
            ):
                raise EvidenceValidationError(EVIDENCE_CORRUPT, "manifest bytes differ from the captured snapshot")
            envelope = EvidenceEnvelope.from_json_bytes(payload)
            manifest_id = name[:-5]
            if str(envelope.evidence_id) != manifest_id:
                raise EvidenceValidationError(EVIDENCE_CORRUPT, "manifest filename does not match its evidence_id")
            manifests[manifest_id] = store._verify_envelope_snapshot(
                envelope, object_snapshot
            )
        except (OSError, EvidenceValidationError):
            corrupt.append(relative)
    return manifests, unknown, corrupt


def _scan_objects(
    store: EvidenceStore, entries: tuple[dict[str, object], ...]
) -> tuple[dict[str, int], list[str], list[str]]:
    objects: dict[str, int] = {}
    unknown: list[str] = []
    corrupt: list[str] = []
    for entry in entries:
        relative = str(entry["path"])
        if relative != "objects" and not relative.startswith("objects/"):
            continue
        parts = relative.split("/")
        if entry["kind"] in {"link", "special"} or entry["links"] != 1:
            corrupt.append(relative)
            continue
        if entry["kind"] == "directory":
            valid_container = (
                parts == ["objects", "sha256"]
                or (len(parts) == 3 and parts[:2] == ["objects", "sha256"] and _PREFIX.fullmatch(parts[2]) is not None)
            )
            valid_object_slot = (
                len(parts) == 4
                and parts[:2] == ["objects", "sha256"]
                and _PREFIX.fullmatch(parts[2]) is not None
                and _HASH.fullmatch(parts[3]) is not None
                and parts[3].startswith(parts[2])
            )
            if valid_container:
                continue
            (corrupt if valid_object_slot else unknown).append(relative)
            continue
        valid_name = (
            len(parts) == 4
            and parts[1] == "sha256"
            and _PREFIX.fullmatch(parts[2]) is not None
            and _HASH.fullmatch(parts[3]) is not None
            and parts[3].startswith(parts[2])
        )
        if not valid_name:
            unknown.append(relative)
            continue
        if entry["kind"] != "file" or entry["links"] != 1 or "read_error" in entry:
            corrupt.append(relative)
            continue
        if entry.get("content_sha256") != parts[3]:
            corrupt.append(relative)
            continue
        objects[relative] = int(entry["size"])
    return objects, unknown, corrupt


def _existing_store_identity(store: EvidenceStore) -> tuple[str, str]:
    """Read an existing canonical store identity without creating any path."""
    info = store._validate_existing_path(store.root)
    if not stat.S_ISDIR(info.st_mode):
        raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "evidence root is not a directory")
    canonical_root = os.path.normcase(str(store.root.absolute()))
    store_id = _digest(
        {
            "canonical_root": canonical_root,
            "device": str(info.st_dev),
            "inode": str(info.st_ino),
        }
    )
    return canonical_root, store_id


def _store_identity(store: EvidenceStore) -> tuple[str, str]:
    store._ensure_root()
    return _existing_store_identity(store)


def put_root(store: EvidenceStore | Path | str, root: RootRecord | Mapping[str, object]) -> Path:
    """Verify and atomically publish one known root under the shared mutation lock."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    value = root.to_dict() if isinstance(root, RootRecord) else root
    record = RootRecord.from_value(value)
    payload = _canonical_root_bytes(record.to_dict())
    name = f"{_digest({'root_type': record.root_type, 'root_id': record.root_id})}.json"
    with evidence_store._mutation_lock():
        evidence_store.get_envelope(record.manifest_id)
        directory = evidence_store._managed_directory("roots", record.root_type)
        target = directory / name
        try:
            evidence_store._validate_existing_path(target, regular=True, single_link=True)
        except FileNotFoundError:
            if evidence_store._atomic_create_new(target, payload, phase="gc-root"):
                return target
        if target.read_bytes() != payload:
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "root identity already has different canonical bytes")
        return target


def get_root(store: EvidenceStore | Path | str, root_type: str, root_id: str) -> RootRecord:
    """Load one exact canonical root without creating store state."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    root_type, root_id = _validate_root_key(root_type, root_id)
    name = f"{_digest({'root_type': root_type, 'root_id': root_id})}.json"
    try:
        path = evidence_store._existing_managed_path(
            "roots", root_type, name, regular=True, single_link=True,
        )
        payload = evidence_store._read_file_bytes(path, maximum_bytes=MAX_ENVELOPE_BYTES)
    except FileNotFoundError as exc:
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "evidence root is absent") from exc
    try:
        document = json.loads(payload.decode("utf-8"))
        if canonical_json_bytes(document) != payload:
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "root is not canonical JSON")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "root is not canonical JSON") from exc
    except EvidenceValidationError as exc:
        if exc.code == EVIDENCE_CORRUPT:
            raise
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "root stored bytes are corrupt") from exc
    try:
        record = RootRecord.from_value(document)
    except EvidenceValidationError as exc:
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "root stored record is corrupt") from exc
    if record.root_type != root_type or record.root_id != root_id:
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "root payload does not match its exact key")
    return record


def _plan_gc_locked(evidence_store: EvidenceStore) -> GcPlan:
    """Build the plan while the caller holds the verified store mutation lock."""
    store_root, store_id = _store_identity(evidence_store)
    snapshot = _snapshot_entries(evidence_store)
    evidence_store._fault("gc.plan.after_snapshot")
    roots, root_unknown, root_corrupt, conservative = _scan_roots(evidence_store, snapshot)
    objects, object_unknown, object_corrupt = _scan_objects(evidence_store, snapshot)
    manifests, manifest_unknown, manifest_corrupt = _scan_manifests(
        evidence_store, snapshot, objects
    )
    if manifest_corrupt:
        conservative = True
    evidence_store._fault("gc.plan.after_scan")
    if _filtered_snapshot_digest(_snapshot_entries(evidence_store)) != _filtered_snapshot_digest(
        snapshot
    ):
        raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "evidence store changed while GC planning")

    reachable: set[str] = set()
    pending_manifests = [root.manifest_id for root in roots]
    visited_manifests: set[str] = set()
    while pending_manifests:
        manifest_id = pending_manifests.pop()
        if manifest_id in visited_manifests:
            continue
        visited_manifests.add(manifest_id)
        envelope = manifests.get(manifest_id)
        if envelope is None:
            root_corrupt.append(f"manifest:{manifest_id}")
            conservative = True
            continue
        reachable.update(artifact.relative_path for artifact in envelope.artifacts)
        pending_manifests.extend(envelope.parents)
    if conservative:
        reachable.update(objects)

    reachable_manifest_ids = (
        set(manifests) if conservative else set(manifests).intersection(visited_manifests)
    )
    reachable_manifests = _ordered(
        f"manifests/{manifest_id}.json" for manifest_id in reachable_manifest_ids
    )
    unreachable_manifests = _ordered(
        f"manifests/{manifest_id}.json"
        for manifest_id in manifests
        if manifest_id not in reachable_manifest_ids
    )

    unknown = _ordered({*root_unknown, *manifest_unknown, *object_unknown})
    corrupt = _ordered({*root_corrupt, *manifest_corrupt, *object_corrupt})
    reachable_known = _ordered(path for path in objects if path in reachable)
    unreachable = _ordered(
        path for path in objects if path not in reachable and path not in corrupt
    )
    manifest_sizes = {
        str(entry["path"]): int(entry["size"])
        for entry in snapshot
        if str(entry["path"]).startswith("manifests/") and entry.get("kind") == "file"
    }
    reclaimable = sum(objects[path] for path in unreachable) + sum(
        manifest_sizes[path] for path in unreachable_manifests
    )
    manifest_entries = tuple(
        entry for entry in snapshot if str(entry["path"]).startswith("manifests/")
    )
    values: dict[str, object] = {
        "schema": GC_PLAN_SCHEMA,
        "store_root": store_root,
        "store_id": store_id,
        "roots": [root.to_dict() for root in roots],
        "manifest_ids": list(_ordered(manifests)),
        "reachable_manifests": list(reachable_manifests),
        "unreachable_manifests": list(unreachable_manifests),
        "reachable_objects": list(reachable_known),
        "unreachable_objects": list(unreachable),
        "unknown_entries": list(unknown),
        "corrupt_entries": list(corrupt),
        "bytes_reclaimable": reclaimable,
        "manifest_snapshot_digest": _filtered_snapshot_digest(manifest_entries),
        "store_snapshot_digest": _filtered_snapshot_digest(snapshot),
    }
    plan_digest = _digest(values)
    action_digest = _digest(
        {
            "operation": "evidence.gc.apply",
            "store_id": store_id,
            "plan_digest": plan_digest,
            "manifest_snapshot_digest": values["manifest_snapshot_digest"],
            "bytes_reclaimable": reclaimable,
        }
    )
    plan = GcPlan(
        store_root=store_root,
        store_id=store_id,
        roots=tuple(roots),
        manifest_ids=_ordered(manifests),
        reachable_manifests=reachable_manifests,
        unreachable_manifests=unreachable_manifests,
        reachable_objects=reachable_known,
        unreachable_objects=unreachable,
        unknown_entries=unknown,
        corrupt_entries=corrupt,
        bytes_reclaimable=reclaimable,
        manifest_snapshot_digest=str(values["manifest_snapshot_digest"]),
        store_snapshot_digest=str(values["store_snapshot_digest"]),
        plan_digest=plan_digest,
        action_digest=action_digest,
    )
    prepared = _PreparedGcPlan(
        store=evidence_store,
        store_root=store_root,
        store_id=store_id,
        plan_digest=plan_digest,
        action_digest=action_digest,
        manifest_snapshot_digest=str(values["manifest_snapshot_digest"]),
        store_snapshot_digest=str(values["store_snapshot_digest"]),
        bytes_reclaimable=reclaimable,
        unreachable_manifests=unreachable_manifests,
        unreachable_objects=unreachable,
        target_sizes=MappingProxyType(
            {
                **{path: manifest_sizes[path] for path in unreachable_manifests},
                **{path: objects[path] for path in unreachable},
            }
        ),
        snapshot_entries=snapshot,
        canonical_plan=plan.to_json_bytes(),
    )
    with _PREPARED_REGISTRY_LOCK:
        _PREPARED_BY_PLAN[plan] = prepared
    return plan


def plan_gc(store: EvidenceStore | Path | str) -> GcPlan:
    """Build a deterministic dry-run plan after initializing coordination metadata."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    with evidence_store._mutation_lock():
        return _plan_gc_locked(evidence_store)


def _result(
    prepared: _PreparedGcPlan,
    success: bool,
    code: str,
    *,
    deleted: tuple[str, ...] = (),
    deleted_manifests: tuple[str, ...] = (),
    bytes_reclaimed: int = 0,
    errors: tuple[str, ...] = (),
) -> GcResult:
    return GcResult(
        success=success,
        code=code,
        plan_digest=prepared.plan_digest,
        action_digest=prepared.action_digest,
        deleted_manifests=deleted_manifests,
        retained_manifests=tuple(
            path
            for path in prepared.unreachable_manifests
            if path not in deleted_manifests
        ),
        deleted_objects=deleted,
        retained_objects=tuple(
            path for path in prepared.unreachable_objects if path not in deleted
        ),
        bytes_reclaimed=bytes_reclaimed,
        errors=errors,
    )


def _unprepared_result(plan: GcPlan) -> GcResult:
    plan_digest = plan.plan_digest if isinstance(plan.plan_digest, str) else ""
    action_digest = plan.action_digest if isinstance(plan.action_digest, str) else ""
    retained = (
        plan.unreachable_objects
        if isinstance(plan.unreachable_objects, tuple)
        and all(isinstance(path, str) for path in plan.unreachable_objects)
        else ()
    )
    retained_manifests = (
        plan.unreachable_manifests
        if isinstance(plan.unreachable_manifests, tuple)
        and all(isinstance(path, str) for path in plan.unreachable_manifests)
        else ()
    )
    return GcResult(
        success=False,
        code="GC_PLAN_INVALID",
        plan_digest=plan_digest,
        action_digest=action_digest,
        deleted_manifests=(),
        retained_manifests=retained_manifests,
        deleted_objects=(),
        retained_objects=retained,
        bytes_reclaimed=0,
        errors=(),
    )


def _registered_prepared(plan: GcPlan) -> _PreparedGcPlan | None:
    with _PREPARED_REGISTRY_LOCK:
        return _PREPARED_BY_PLAN.get(plan)


def _consume_authorization(prepared: _PreparedGcPlan) -> bool:
    """Redeem through the stable parent-scoped ledger, independent of root replacement."""
    parent = prepared.store.root.parent
    parent_info = EvidenceStore._validate_existing_path(parent)
    if not stat.S_ISDIR(parent_info.st_mode):
        raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "evidence store parent is not a directory")
    payload = canonical_json_bytes(
        {
            "action_digest": prepared.action_digest,
            "plan_digest": prepared.plan_digest,
            "state": "consumed",
            "store_id": prepared.store_id,
        }
    )
    with _stable_parent_guard(parent, parent_info):
        root_name = os.path.normcase(prepared.store.root.name)
        ledger_name = (
            _AUTHORIZATION_LEDGER_SECONDARY
            if root_name == os.path.normcase(_AUTHORIZATION_LEDGER_PRIMARY)
            else _AUTHORIZATION_LEDGER_PRIMARY
        )
        ledger_root = parent / ledger_name
        if os.path.normcase(str(ledger_root.absolute())) == os.path.normcase(
            str(prepared.store.root.absolute())
        ):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE,
                "authorization ledger aliases the evidence store root"
            )
        ledger = EvidenceStore(ledger_root)
        with ledger._mutation_lock():
            directory = ledger._managed_directory("actions", prepared.store_id)
            target = directory / f"{prepared.action_digest}.json"
            try:
                ledger._validate_existing_path(target, regular=True, single_link=True)
            except FileNotFoundError:
                return ledger._atomic_create_new(
                    target, payload, phase="gc-authorization"
                )
            except (OSError, EvidenceValidationError):
                return False
            return False


def _delete_identity_bound(
    prepared: _PreparedGcPlan,
    relative: str,
    final_snapshot: tuple[dict[str, object], ...],
    excluded_before: set[str],
) -> _DeleteOutcome:
    """Delete the verified Windows file identity without a pathname unlink race."""
    if os.name != "nt":  # pragma: no cover - Linux acceptance must retain safely
        raise GcStoreChangedError()  # pragma: no cover
    expected = next(
        (entry for entry in final_snapshot if entry.get("path") == relative), None
    )
    if expected is None:
        raise GcStoreChangedError()
    path = prepared.store.root.joinpath(*relative.split("/"))
    try:
        handle = _open_windows_file(path, delete=True)
    except OSError as exc:
        raise GcStoreChangedError() from exc
    disposition_set = False
    close_error: OSError | None = None
    try:
        opened = _windows_file_information(handle)
        identity = {
            "volume_serial": str(opened["volume_serial"]),
            "file_index": str(opened["file_index"]),
        }
        if (
            expected.get("kind") != "file"
            or expected.get("links") != 1
            or opened["links"] != 1
            or opened["attributes"] & (0x00000010 | 0x00000400)
            or any(expected.get(name) != value for name, value in identity.items())
            or opened["size"] != expected.get("size")
            or opened["size"] != prepared.target_sizes[relative]
        ):
            raise GcStoreChangedError()

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        read_file = kernel32.ReadFile
        read_file.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        read_file.restype = wintypes.BOOL
        digest = hashlib.sha256()
        size = 0
        buffer = ctypes.create_string_buffer(1024 * 1024)
        count = wintypes.DWORD()
        while True:
            if not read_file(handle, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if count.value == 0:
                break
            size += count.value
            digest.update(buffer.raw[: count.value])
        after = _windows_file_information(handle)
        if (
            after["volume_serial"] != opened["volume_serial"]
            or after["file_index"] != opened["file_index"]
            or after["links"] != 1
            or after["size"] != opened["size"]
            or after["attributes"] & (0x00000010 | 0x00000400)
            or size != opened["size"]
            or digest.hexdigest() != expected.get("content_sha256")
        ):
            raise GcStoreChangedError()

        excluded = frozenset({*excluded_before, relative})
        handle_snapshot = _snapshot_entries(
            prepared.store,
            phase="gc.handle-snapshot",
            excluded=excluded,
        )
        if _filtered_snapshot_digest(
            handle_snapshot, excluded
        ) != _filtered_snapshot_digest(prepared.snapshot_entries, excluded):
            raise GcStoreChangedError()

        set_pointer = kernel32.SetFilePointerEx
        set_pointer.argtypes = [
            wintypes.HANDLE,
            ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_longlong),
            wintypes.DWORD,
        ]
        set_pointer.restype = wintypes.BOOL
        position = ctypes.c_longlong()
        if not set_pointer(handle, 0, ctypes.byref(position), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        final_digest = hashlib.sha256()
        final_size = 0
        while True:
            if not read_file(handle, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if count.value == 0:
                break
            final_size += count.value
            final_digest.update(buffer.raw[: count.value])
        final_info = _windows_file_information(handle)
        if (
            final_info != after
            or final_size != size
            or final_digest.hexdigest() != expected.get("content_sha256")
        ):
            raise GcStoreChangedError()

        class FileDispositionInformation(ctypes.Structure):
            _fields_ = [("delete_file", wintypes.BOOL)]

        set_information = kernel32.SetFileInformationByHandle
        set_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        set_information.restype = wintypes.BOOL
        disposition = FileDispositionInformation(True)
        if not set_information(
            handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        disposition_set = True
    finally:
        try:
            _close_windows_handle(handle)
        except OSError as exc:
            close_error = exc
    if not disposition_set:
        if close_error is not None:
            raise close_error
        raise OSError("identity-bound deletion was not committed")
    error = str(close_error) if close_error is not None else None
    try:
        prepared.store._flush_directory(path.parent)
    except OSError as exc:
        error = str(exc) if error is None else f"{error}; {exc}"
    return _DeleteOutcome(size=size, committed=True, error=error)


def _apply_gc_locked(prepared: _PreparedGcPlan) -> GcResult:
    prepared.store._fault("gc.locked.before_validate")
    try:
        current_root, current_store_id = _store_identity(prepared.store)
        current_snapshot = _snapshot_entries(prepared.store)
    except (OSError, EvidenceValidationError) as exc:
        return _result(prepared, False, "GC_STORE_CHANGED", errors=(str(exc),))
    if (
        current_root != prepared.store_root
        or current_store_id != prepared.store_id
        or _filtered_snapshot_digest(current_snapshot) != prepared.store_snapshot_digest
    ):
        return _result(prepared, False, "GC_STORE_CHANGED")

    deleted: list[str] = []
    deleted_manifests: list[str] = []
    reclaimed = 0
    targets = (*prepared.unreachable_manifests, *prepared.unreachable_objects)
    for relative in targets:
        try:
            prepared.store._fault("gc.before_delete")
            current_snapshot = _snapshot_entries(prepared.store)
            excluded = {*deleted_manifests, *deleted}
            if _filtered_snapshot_digest(current_snapshot, excluded) != _filtered_snapshot_digest(
                prepared.snapshot_entries, excluded
            ):
                return _result(
                    prepared,
                    False,
                    "GC_STORE_CHANGED" if not (deleted or deleted_manifests) else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    deleted_manifests=tuple(deleted_manifests),
                    bytes_reclaimed=reclaimed,
                )
            prepared.store._fault("gc.before_unlink")
            try:
                final_snapshot = _snapshot_entries(
                    prepared.store, phase="gc.final-snapshot"
                )
            except EvidenceValidationError as exc:
                return _result(
                    prepared,
                    False,
                    "GC_STORE_CHANGED" if not (deleted or deleted_manifests) else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    deleted_manifests=tuple(deleted_manifests),
                    bytes_reclaimed=reclaimed,
                    errors=(str(exc),),
                )
            if _filtered_snapshot_digest(final_snapshot, excluded) != _filtered_snapshot_digest(
                prepared.snapshot_entries, excluded
            ):
                return _result(
                    prepared,
                    False,
                    "GC_STORE_CHANGED" if not (deleted or deleted_manifests) else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    deleted_manifests=tuple(deleted_manifests),
                    bytes_reclaimed=reclaimed,
                )
            outcome = _delete_identity_bound(prepared, relative, final_snapshot, excluded)
            if outcome.committed:
                if relative.startswith("manifests/"):
                    deleted_manifests.append(relative)
                else:
                    deleted.append(relative)
                reclaimed += outcome.size
            if outcome.error is not None:
                return _result(
                    prepared,
                    False,
                    "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    deleted_manifests=tuple(deleted_manifests),
                    bytes_reclaimed=reclaimed,
                    errors=(outcome.error,),
                )
            prepared.store._fault("gc.after_delete")
        except GcStoreChangedError as exc:
            return _result(
                prepared,
                False,
                "GC_STORE_CHANGED" if not (deleted or deleted_manifests) else "GC_PARTIAL_DELETE",
                deleted=tuple(deleted),
                deleted_manifests=tuple(deleted_manifests),
                bytes_reclaimed=reclaimed,
                errors=(str(exc),),
            )
        except (OSError, EvidenceValidationError) as exc:
            return _result(
                prepared,
                False,
                "GC_PARTIAL_DELETE" if (deleted or deleted_manifests) else "GC_DELETE_FAILED",
                deleted=tuple(deleted),
                deleted_manifests=tuple(deleted_manifests),
                bytes_reclaimed=reclaimed,
                errors=(str(exc),),
            )
    return _result(
        prepared,
        True,
        "GC_APPLIED",
        deleted=tuple(deleted),
        deleted_manifests=tuple(deleted_manifests),
        bytes_reclaimed=reclaimed,
    )


def _apply_registered(
    plan: GcPlan,
    prepared: _PreparedGcPlan,
    authorized: object,
    expected_plan_digest: object,
) -> GcResult:
    """Apply an original registered plan under one store mutation lock."""
    with prepared.consume_lock:
        if prepared.consumed:
            return _result(prepared, False, "GC_AUTHORIZATION_CONSUMED")
        try:
            consumed_now = _consume_authorization(prepared)
            prepared.consumed = True
            if not consumed_now:
                return _result(prepared, False, "GC_AUTHORIZATION_CONSUMED")
            store_root, store_id = _existing_store_identity(prepared.store)
            if store_root != prepared.store_root or store_id != prepared.store_id:
                raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "prepared evidence store identity changed")
            with prepared.store._mutation_lock(create=False):
                store_root, store_id = _existing_store_identity(prepared.store)
                if store_root != prepared.store_root or store_id != prepared.store_id:
                    raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "prepared evidence store identity changed")
                try:
                    current_plan = plan.to_json_bytes()
                except (
                    AttributeError,
                    EvidenceValidationError,
                    KeyError,
                    OverflowError,
                    TypeError,
                    ValueError,
                ):
                    return _result(prepared, False, "GC_PLAN_INVALID")
                if (
                    current_plan != prepared.canonical_plan
                    or plan.plan_digest != prepared.plan_digest
                    or plan.action_digest != prepared.action_digest
                ):
                    return _result(prepared, False, "GC_PLAN_INVALID")
                if not isinstance(authorized, str) or authorized != prepared.action_digest:
                    return _result(prepared, False, "GC_AUTHORIZATION_INVALID")
                if (
                    not isinstance(expected_plan_digest, str)
                    or expected_plan_digest != prepared.plan_digest
                ):
                    return _result(prepared, False, "GC_PLAN_DIGEST_MISMATCH")
                try:
                    return _apply_gc_locked(prepared)
                except (OSError, EvidenceValidationError) as exc:
                    return _result(
                        prepared,
                        False,
                        "GC_STORE_CHANGED",
                        errors=(str(exc),),
                    )
        except (OSError, EvidenceValidationError) as exc:
            prepared.consumed = True
            return _result(
                prepared,
                False,
                "GC_AUTHORIZATION_INVALID",
                errors=(str(exc),),
            )


def _apply_reconstructed(plan: GcPlan) -> GcResult:
    """Recognize and reject an exact copy without trusting its public prepared fields."""
    if (
        not isinstance(plan.store_root, str)
        or not isinstance(plan.store_id, str)
        or not isinstance(plan.plan_digest, str)
        or not isinstance(plan.action_digest, str)
    ):
        return _unprepared_result(plan)
    try:
        store = EvidenceStore(Path(plan.store_root))
        store_root, store_id = _existing_store_identity(store)
        if store_root != plan.store_root or store_id != plan.store_id:
            return _unprepared_result(plan)
        with store._mutation_lock(create=False):
            store_root, store_id = _existing_store_identity(store)
            if store_root != plan.store_root or store_id != plan.store_id:
                return _unprepared_result(plan)
            regenerated = _plan_gc_locked(store)
            prepared = _registered_prepared(regenerated)
            if prepared is None:
                return _unprepared_result(plan)
            try:
                current_plan = plan.to_json_bytes()
            except (
                AttributeError,
                EvidenceValidationError,
                KeyError,
                OverflowError,
                TypeError,
                ValueError,
            ):
                return _unprepared_result(plan)
            if (
                current_plan != prepared.canonical_plan
                or plan.action_digest != prepared.action_digest
            ):
                return _unprepared_result(plan)
            with prepared.consume_lock:
                if prepared.consumed:
                    return _result(prepared, False, "GC_AUTHORIZATION_CONSUMED")
                consumed_now = _consume_authorization(prepared)
                prepared.consumed = True
                if not consumed_now:
                    return _result(prepared, False, "GC_AUTHORIZATION_CONSUMED")
                return _result(prepared, False, "GC_PLAN_INVALID")
    except (EvidenceValidationError, FileNotFoundError, OSError, TypeError, ValueError):
        return _unprepared_result(plan)


def apply_gc(plan: GcPlan, authorized: object, expected_plan_digest: object) -> GcResult:
    """Consume one exact MODIFY token and delete only still-unreachable verified objects."""
    if not isinstance(plan, GcPlan):
        raise EvidenceValidationError(EVIDENCE_INVALID, "plan must be a GcPlan")
    prepared = _registered_prepared(plan)
    if prepared is None:
        return _apply_reconstructed(plan)
    return _apply_registered(plan, prepared, authorized, expected_plan_digest)


__all__ = [
    "GC_PLAN_SCHEMA",
    "GC_RESULT_SCHEMA",
    "REGISTERED_ROOT_TYPES",
    "GcStoreChangedError",
    "GcPlan",
    "GcResult",
    "RootRecord",
    "apply_gc",
    "get_root",
    "plan_gc",
    "put_root",
]
