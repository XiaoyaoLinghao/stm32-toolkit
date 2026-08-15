"""Conservative, reachability-based collection for immutable evidence objects."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Mapping
from unicodedata import normalize

from .model import EvidenceEnvelope, EvidenceValidationError, canonical_json_bytes
from .store import EvidenceStore


GC_PLAN_SCHEMA = "stm32-evidence-gc-plan/1"
GC_RESULT_SCHEMA = "stm32-evidence-gc-result/1"
REGISTERED_ROOT_TYPES = frozenset(
    {"test-run", "diagnostic-session", "bundle", "annotation"}
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PREFIX = re.compile(r"^[0-9a-f]{2}$")
_ROOT_FIELDS = {"root_type", "root_id", "manifest_id", "metadata"}


class _GcStoreChanged(EvidenceValidationError):
    """The object selected by the plan no longer has the captured identity."""


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _ordered(values) -> tuple[str, ...]:
    return tuple(sorted(values, key=lambda value: value.encode("utf-8")))


def _json_copy(value: object) -> object:
    return json.loads(canonical_json_bytes(value))


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
    sharing = file_share_read | file_share_write
    if not delete:
        sharing |= file_share_delete
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
            raise EvidenceValidationError("file identity changed while it was captured")
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

    @classmethod
    def from_value(cls, value: object) -> "RootRecord":
        if not isinstance(value, Mapping) or set(value) != _ROOT_FIELDS:
            raise EvidenceValidationError("root record fields are not closed")
        root_type = value["root_type"]
        root_id = value["root_id"]
        manifest_id = value["manifest_id"]
        metadata = value["metadata"]
        if not isinstance(root_type, str):
            raise EvidenceValidationError("root_type must be a string")
        if root_type not in REGISTERED_ROOT_TYPES:
            raise EvidenceValidationError("root_type is not registered")
        for field_name, item in (("root_type", root_type), ("root_id", root_id)):
            if (
                not isinstance(item, str)
                or not item
                or normalize("NFC", item) != item
                or len(item.encode("utf-8")) > 64 * 1024
                or any(ord(character) < 32 or ord(character) == 127 for character in item)
            ):
                raise EvidenceValidationError(f"{field_name} is not a canonical bounded string")
        if not isinstance(manifest_id, str) or _HASH.fullmatch(manifest_id) is None:
            raise EvidenceValidationError("manifest_id must be a lowercase SHA-256")
        if not isinstance(metadata, Mapping):
            raise EvidenceValidationError("root metadata must be a JSON object")
        copied = _json_copy(metadata)
        assert isinstance(copied, dict)
        return cls(root_type, root_id, manifest_id, MappingProxyType(copied))

    def to_dict(self) -> dict[str, object]:
        return {
            "root_type": self.root_type,
            "root_id": self.root_id,
            "manifest_id": self.manifest_id,
            "metadata": _json_copy(self.metadata),
        }


@dataclass
class GcPlan:
    """Canonical read-only plan plus one in-memory, single-use MODIFY token."""

    store_root: str
    store_id: str
    roots: tuple[RootRecord, ...]
    manifest_ids: tuple[str, ...]
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
    _store: EvidenceStore = field(repr=False, compare=False, default=None)  # type: ignore[assignment]
    _object_sizes: Mapping[str, int] = field(repr=False, compare=False, default_factory=dict)
    _snapshot_entries: tuple[dict[str, object], ...] = field(
        repr=False, compare=False, default_factory=tuple
    )
    _prepared_plan_digest: str = field(repr=False, compare=False, default="")
    _prepared_action_digest: str = field(repr=False, compare=False, default="")
    _prepared_store_id: str = field(repr=False, compare=False, default="")
    _prepared_store: EvidenceStore | None = field(repr=False, compare=False, default=None)
    _prepared_unreachable_objects: tuple[str, ...] = field(
        repr=False, compare=False, default_factory=tuple
    )
    _consumed: bool = field(repr=False, compare=False, default=False)

    def _document_without_digest(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "store_root": self.store_root,
            "store_id": self.store_id,
            "roots": [root.to_dict() for root in self.roots],
            "manifest_ids": list(self.manifest_ids),
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
            "deleted_objects": list(self.deleted_objects),
            "retained_objects": list(self.retained_objects),
            "bytes_reclaimed": self.bytes_reclaimed,
            "errors": list(self.errors),
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


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
            raise EvidenceValidationError(
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
                raise EvidenceValidationError(
                    f"managed directory appeared while the store was scanned: {top}"
                )
            continue
        if after is None or (
            (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or after.st_mode != before.st_mode
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise EvidenceValidationError(
                f"managed directory changed while the store was scanned: {top}"
            )
    for directory, before in directory_states.items():
        try:
            after = directory.lstat()
        except FileNotFoundError as exc:
            raise EvidenceValidationError(
                f"managed directory disappeared while the store was scanned: {directory}"
            ) from exc
        if (
            stat.S_ISLNK(after.st_mode)
            or store._is_reparse(after)
            or not stat.S_ISDIR(after.st_mode)
            or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise EvidenceValidationError(
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
                raise EvidenceValidationError("root bytes differ from the captured snapshot")
            document = json.loads(payload)
            if canonical_json_bytes(document) != payload:
                raise EvidenceValidationError("root is not canonical JSON")
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
    store: EvidenceStore, entries: tuple[dict[str, object], ...]
) -> tuple[dict[str, EvidenceEnvelope], list[str], list[str]]:
    manifests: dict[str, EvidenceEnvelope] = {}
    unknown: list[str] = []
    corrupt: list[str] = []
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
                raise EvidenceValidationError("manifest bytes differ from the captured snapshot")
            envelope = EvidenceEnvelope.from_json_bytes(payload)
            manifest_id = name[:-5]
            if str(envelope.evidence_id) != manifest_id:
                raise EvidenceValidationError("manifest filename does not match its evidence_id")
            manifests[manifest_id] = envelope
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


def _store_identity(store: EvidenceStore) -> tuple[str, str]:
    store._ensure_root()
    info = store._validate_existing_path(store.root)
    canonical_root = os.path.normcase(str(store.root.absolute()))
    store_id = _digest(
        {
            "canonical_root": canonical_root,
            "device": str(info.st_dev),
            "inode": str(info.st_ino),
        }
    )
    return canonical_root, store_id


def put_root(store: EvidenceStore | Path | str, root: RootRecord | Mapping[str, object]) -> Path:
    """Verify and atomically publish one known root under the shared mutation lock."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    record = root if isinstance(root, RootRecord) else RootRecord.from_value(root)
    payload = canonical_json_bytes(record.to_dict())
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
            raise EvidenceValidationError("root identity already has different canonical bytes")
        return target


def plan_gc(store: EvidenceStore | Path | str) -> GcPlan:
    """Build a deterministic dry-run plan without modifying the evidence store."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    store_root, store_id = _store_identity(evidence_store)
    snapshot = _snapshot_entries(evidence_store)
    evidence_store._fault("gc.plan.after_snapshot")
    roots, root_unknown, root_corrupt, conservative = _scan_roots(evidence_store, snapshot)
    manifests, manifest_unknown, manifest_corrupt = _scan_manifests(evidence_store, snapshot)
    objects, object_unknown, object_corrupt = _scan_objects(evidence_store, snapshot)
    evidence_store._fault("gc.plan.after_scan")
    if _filtered_snapshot_digest(_snapshot_entries(evidence_store)) != _filtered_snapshot_digest(
        snapshot
    ):
        raise EvidenceValidationError("evidence store changed while GC planning")

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

    unknown = _ordered({*root_unknown, *manifest_unknown, *object_unknown})
    corrupt = _ordered({*root_corrupt, *manifest_corrupt, *object_corrupt})
    reachable_known = _ordered(path for path in objects if path in reachable)
    unreachable = _ordered(
        path for path in objects if path not in reachable and path not in corrupt
    )
    reclaimable = sum(objects[path] for path in unreachable)
    manifest_entries = tuple(
        entry for entry in snapshot if str(entry["path"]).startswith("manifests/")
    )
    values: dict[str, object] = {
        "schema": GC_PLAN_SCHEMA,
        "store_root": store_root,
        "store_id": store_id,
        "roots": [root.to_dict() for root in roots],
        "manifest_ids": list(_ordered(manifests)),
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
    return GcPlan(
        store_root=store_root,
        store_id=store_id,
        roots=tuple(roots),
        manifest_ids=_ordered(manifests),
        reachable_objects=reachable_known,
        unreachable_objects=unreachable,
        unknown_entries=unknown,
        corrupt_entries=corrupt,
        bytes_reclaimable=reclaimable,
        manifest_snapshot_digest=str(values["manifest_snapshot_digest"]),
        store_snapshot_digest=str(values["store_snapshot_digest"]),
        plan_digest=plan_digest,
        action_digest=action_digest,
        _store=evidence_store,
        _object_sizes=MappingProxyType({path: objects[path] for path in unreachable}),
        _snapshot_entries=snapshot,
        _prepared_plan_digest=plan_digest,
        _prepared_action_digest=action_digest,
        _prepared_store_id=store_id,
        _prepared_store=evidence_store,
        _prepared_unreachable_objects=unreachable,
    )


def _result(
    plan: GcPlan,
    success: bool,
    code: str,
    *,
    deleted: tuple[str, ...] = (),
    bytes_reclaimed: int = 0,
    errors: tuple[str, ...] = (),
) -> GcResult:
    return GcResult(
        success=success,
        code=code,
        plan_digest=plan._prepared_plan_digest or plan.plan_digest,
        action_digest=plan._prepared_action_digest or plan.action_digest,
        deleted_objects=deleted,
        retained_objects=tuple(
            path for path in plan._prepared_unreachable_objects if path not in deleted
        ),
        bytes_reclaimed=bytes_reclaimed,
        errors=errors,
    )


def _consume_authorization(plan: GcPlan) -> bool:
    """Atomically redeem an action digest once for this store, across plan instances/processes."""
    if plan._prepared_store is None:
        raise EvidenceValidationError("prepared authorization store is unavailable")
    directory = plan._prepared_store._managed_directory("gc-authorizations")
    target = directory / f"{plan._prepared_action_digest}.json"
    payload = canonical_json_bytes(
        {
            "action_digest": plan._prepared_action_digest,
            "plan_digest": plan._prepared_plan_digest,
            "state": "consumed",
            "store_id": plan._prepared_store_id,
        }
    )
    try:
        plan._store._validate_existing_path(target, regular=True, single_link=True)
    except FileNotFoundError:
        return plan._prepared_store._atomic_create_new(
            target, payload, phase="gc-authorization"
        )
    except (OSError, EvidenceValidationError):
        return False
    return False


def _delete_identity_bound(
    plan: GcPlan,
    relative: str,
    final_snapshot: tuple[dict[str, object], ...],
) -> int:
    """Delete the verified Windows file identity without a pathname unlink race."""
    if os.name != "nt":  # pragma: no cover - Linux acceptance must retain safely
        raise _GcStoreChanged(  # pragma: no cover
            "identity-bound evidence deletion is unavailable on this platform"
        )
    expected = next(
        (entry for entry in final_snapshot if entry.get("path") == relative), None
    )
    if expected is None:
        raise _GcStoreChanged("planned object disappeared before identity-bound deletion")
    path = plan._store.root.joinpath(*relative.split("/"))
    try:
        handle = _open_windows_file(path, delete=True)
    except OSError as exc:
        raise _GcStoreChanged("planned object could not be opened by identity") from exc
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
            or opened["size"] != plan._object_sizes[relative]
        ):
            raise _GcStoreChanged("planned object identity changed before deletion")

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
            or digest.hexdigest() != Path(relative).name
        ):
            raise _GcStoreChanged("planned object changed while its handle was verified")

        excluded = frozenset(
            {*plan.unreachable_objects[: plan.unreachable_objects.index(relative)], relative}
        )
        handle_snapshot = _snapshot_entries(
            plan._store,
            phase="gc.handle-snapshot",
            excluded=excluded,
        )
        if _filtered_snapshot_digest(
            handle_snapshot, excluded
        ) != _filtered_snapshot_digest(plan._snapshot_entries, excluded):
            raise _GcStoreChanged("evidence store changed while delete handle was held")

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
    if close_error is not None:
        raise close_error
    if not disposition_set:
        raise OSError("identity-bound deletion was not committed")
    plan._store._flush_directory(path.parent)
    return size


def _apply_gc_locked(plan: GcPlan) -> GcResult:
    plan._store._fault("gc.locked.before_validate")
    try:
        current_root, current_store_id = _store_identity(plan._store)
        current_snapshot = _snapshot_entries(plan._store)
    except (OSError, EvidenceValidationError) as exc:
        return _result(plan, False, "GC_STORE_CHANGED", errors=(str(exc),))
    if (
        current_root != plan.store_root
        or current_store_id != plan.store_id
        or _filtered_snapshot_digest(current_snapshot) != plan.store_snapshot_digest
    ):
        return _result(plan, False, "GC_STORE_CHANGED")

    deleted: list[str] = []
    reclaimed = 0
    for relative in plan.unreachable_objects:
        try:
            plan._store._fault("gc.before_delete")
            current_snapshot = _snapshot_entries(plan._store)
            excluded = set(deleted)
            if _filtered_snapshot_digest(current_snapshot, excluded) != _filtered_snapshot_digest(
                plan._snapshot_entries, excluded
            ):
                return _result(
                    plan,
                    False,
                    "GC_STORE_CHANGED" if not deleted else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    bytes_reclaimed=reclaimed,
                )
            plan._store._fault("gc.before_unlink")
            try:
                final_snapshot = _snapshot_entries(
                    plan._store, phase="gc.final-snapshot"
                )
            except EvidenceValidationError as exc:
                return _result(
                    plan,
                    False,
                    "GC_STORE_CHANGED" if not deleted else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    bytes_reclaimed=reclaimed,
                    errors=(str(exc),),
                )
            if _filtered_snapshot_digest(final_snapshot, excluded) != _filtered_snapshot_digest(
                plan._snapshot_entries, excluded
            ):
                return _result(
                    plan,
                    False,
                    "GC_STORE_CHANGED" if not deleted else "GC_PARTIAL_DELETE",
                    deleted=tuple(deleted),
                    bytes_reclaimed=reclaimed,
                )
            size = _delete_identity_bound(plan, relative, final_snapshot)
            deleted.append(relative)
            reclaimed += size
            plan._store._fault("gc.after_delete")
        except _GcStoreChanged as exc:
            return _result(
                plan,
                False,
                "GC_STORE_CHANGED" if not deleted else "GC_PARTIAL_DELETE",
                deleted=tuple(deleted),
                bytes_reclaimed=reclaimed,
                errors=(str(exc),),
            )
        except (OSError, EvidenceValidationError) as exc:
            return _result(
                plan,
                False,
                "GC_PARTIAL_DELETE" if deleted else "GC_DELETE_FAILED",
                deleted=tuple(deleted),
                bytes_reclaimed=reclaimed,
                errors=(str(exc),),
            )
    return _result(
        plan,
        True,
        "GC_APPLIED",
        deleted=tuple(deleted),
        bytes_reclaimed=reclaimed,
    )


def apply_gc(plan: GcPlan, authorized: object, expected_plan_digest: object) -> GcResult:
    """Consume one exact MODIFY token and delete only still-unreachable verified objects."""
    if not isinstance(plan, GcPlan):
        raise EvidenceValidationError("plan must be a GcPlan")
    if plan._consumed:
        return _result(plan, False, "GC_AUTHORIZATION_CONSUMED")
    if (
        not isinstance(plan._prepared_action_digest, str)
        or _HASH.fullmatch(plan._prepared_action_digest) is None
    ):
        return _result(plan, False, "GC_PLAN_INVALID")
    try:
        consumed_now = _consume_authorization(plan)
    except (OSError, EvidenceValidationError) as exc:
        plan._consumed = True
        return _result(plan, False, "GC_AUTHORIZATION_INVALID", errors=(str(exc),))
    plan._consumed = True
    if not consumed_now:
        return _result(plan, False, "GC_AUTHORIZATION_CONSUMED")
    try:
        current_plan_digest = _digest(plan._document_without_digest())
        current_action_digest = _digest(
            {
                "operation": "evidence.gc.apply",
                "store_id": plan.store_id,
                "plan_digest": plan.plan_digest,
                "manifest_snapshot_digest": plan.manifest_snapshot_digest,
                "bytes_reclaimable": plan.bytes_reclaimable,
            }
        )
    except (
        AttributeError,
        EvidenceValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        return _result(plan, False, "GC_PLAN_INVALID")
    if current_plan_digest != plan.plan_digest or current_action_digest != plan.action_digest:
        return _result(plan, False, "GC_PLAN_INVALID")
    if plan._store is not plan._prepared_store:
        return _result(plan, False, "GC_PLAN_INVALID")
    if not isinstance(authorized, str) or authorized != plan.action_digest:
        return _result(plan, False, "GC_AUTHORIZATION_INVALID")
    if not isinstance(expected_plan_digest, str) or expected_plan_digest != plan.plan_digest:
        return _result(plan, False, "GC_PLAN_DIGEST_MISMATCH")
    try:
        with plan._store._mutation_lock():
            return _apply_gc_locked(plan)
    except (OSError, EvidenceValidationError) as exc:
        return _result(plan, False, "GC_STORE_CHANGED", errors=(str(exc),))


__all__ = [
    "GC_PLAN_SCHEMA",
    "GC_RESULT_SCHEMA",
    "REGISTERED_ROOT_TYPES",
    "GcPlan",
    "GcResult",
    "RootRecord",
    "apply_gc",
    "plan_gc",
    "put_root",
]
