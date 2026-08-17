"""Persistent closed authorization records for Probe CONTROL operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Callable, Mapping

from stm32_toolkit.evidence import EvidenceValidationError, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore


_HASH = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS = {
    "target.halt",
    "target.resume",
    "target.step",
    "target.breakpoint.set",
    "target.breakpoint.clear",
}
_BINDING_KEYS = {
    "workspace_id",
    "project_id",
    "session_id",
    "revision",
    "target",
    "firmware",
    "operation",
    "arguments",
    "identity_snapshot",
    "state_snapshot",
}
_RECORD_KEYS = _BINDING_KEYS | {"nonce", "prepared_at_utc", "expires_at_utc"}
_MAX_RECORD_BYTES = 64 * 1024
_AUTHORITY_VERSION = "stm32-toolkit-control-authority/1"


class ControlAuthorizationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreparedControlAuthorization:
    action_digest: str
    nonce: str
    expires_at_utc: datetime
    binding: Mapping[str, object]


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", f"{field} must be UTC aware")
    return value.astimezone(timezone.utc)


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization record is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization record is invalid") from error
    return _utc(parsed, "authorization time")


def _closed_binding(binding: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid")
    value = dict(binding)
    if value["operation"] not in _OPERATIONS or not isinstance(value["arguments"], Mapping):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid")
    for field in ("workspace_id", "project_id", "session_id", "revision"):
        if not isinstance(value[field], str) or not value[field]:
            raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid")
    for field in ("target", "firmware", "identity_snapshot", "state_snapshot"):
        if not isinstance(value[field], Mapping):
            raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid")
        value[field] = dict(value[field])
    value["arguments"] = dict(value["arguments"])
    target = value["target"]
    identity = value["identity_snapshot"]
    if (
        set(target) != {"board_id", "mcu", "target_id", "probe_serial_hash"}
        or set(identity) != set(target)
        or target != identity
        or any(not isinstance(member, str) or not member for member in target.values())
        or _HASH.fullmatch(str(target["probe_serial_hash"])) is None
    ):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization identity is invalid")
    firmware = value["firmware"]
    if (
        set(firmware) != {"build_id", "elf_sha256"}
        or any(_HASH.fullmatch(str(firmware[field])) is None for field in firmware)
    ):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization firmware is invalid")
    state = value["state_snapshot"]
    if (
        set(state) != {"state", "reason"}
        or state["state"] not in {"running", "halted", "reset", "faulted"}
        or state["reason"] not in {"requested", "breakpoint", "watchpoint", "fault", "exception", "reset"}
    ):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization state is invalid")
    arguments = value["arguments"]
    operation = value["operation"]
    if operation in {"target.halt", "target.resume", "target.step"} and arguments:
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization arguments are invalid")
    if operation == "target.breakpoint.set" and (
        set(arguments) != {"address", "kind", "size"}
        or type(arguments.get("address")) is not int
        or not 0 <= arguments["address"] <= 0xFFFF_FFFF
        or arguments.get("kind") != "temporary"
        or arguments.get("size") not in (1, 2, 4)
    ):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization arguments are invalid")
    if operation == "target.breakpoint.clear" and (
        set(arguments) != {"breakpoint_id"}
        or not isinstance(arguments.get("breakpoint_id"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", arguments["breakpoint_id"]) is None
    ):
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization arguments are invalid")
    try:
        canonical_json_bytes(value)
    except (TypeError, ValueError) as error:
        raise ControlAuthorizationError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid") from error
    return value


class ControlAuthorizationStore:
    """One persistent create-new ledger shared by client preparation and service consumption."""

    def __init__(
        self, root: Path, *, monotonic_clock: Callable[[], float] = time.monotonic
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root.parent == root:
            raise TypeError("Control authorization root must be an absolute bounded path")
        if not callable(monotonic_clock):
            raise TypeError("Control authorization monotonic clock must be callable")
        self.root = root
        self._monotonic_clock = monotonic_clock
        self._live_deadlines: dict[str, float] = {}
        self._live_lock = threading.Lock()
        self._storage: EvidenceStore | None = None
        self._authority_storage: EvidenceStore | None = None
        self._storage_lock = threading.Lock()

    def _evidence_store(self) -> EvidenceStore:
        storage = self._storage
        if storage is None:
            with self._storage_lock:
                storage = self._storage
                if storage is None:
                    storage = EvidenceStore(self.root)
                    self._storage = storage
        return storage

    def _directory(self) -> Path:
        return self._evidence_store()._managed_directory("records")

    def _parent_store(self) -> EvidenceStore:
        storage = self._authority_storage
        if storage is None:
            with self._storage_lock:
                storage = self._authority_storage
                if storage is None:
                    storage = EvidenceStore(self.root.parent)
                    self._authority_storage = storage
        return storage

    def _authority_path(self) -> Path:
        name_digest = sha256(self.root.name.encode("utf-8")).hexdigest()
        return self.root.parent / f".{name_digest}.control-authority.json"

    @staticmethod
    def _identity(info: os.stat_result) -> dict[str, str]:
        # Windows file indices may exceed the canonical JSON safe-integer range.
        return {"device": str(int(info.st_dev)), "inode": str(int(info.st_ino))}

    def _read_authority(self) -> dict[str, object]:
        path = self._authority_path()
        parent_store = self._parent_store()
        try:
            before = parent_store._validate_existing_path(path, regular=True, single_link=True)
            descriptor = parent_store._open_readonly(path)
            try:
                opened = os.fstat(descriptor)
                raw = os.read(descriptor, 4097)
                if os.read(descriptor, 1) or len(raw) > 4096:
                    raise ValueError
            finally:
                os.close(descriptor)
            after = parent_store._validate_existing_path(path, regular=True, single_link=True)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise ValueError
            value = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(value, dict)
                or set(value) != {"version", "root_name_sha256", "parent", "root"}
                or value["version"] != _AUTHORITY_VERSION
                or value["root_name_sha256"] != sha256(self.root.name.encode("utf-8")).hexdigest()
                or set(value["parent"]) != {"device", "inode"}
                or set(value["root"]) != {"device", "inode"}
                or any(
                    not isinstance(member, str)
                    or re.fullmatch(r"[0-9]{1,32}", member) is None
                    for member in (*value["parent"].values(), *value["root"].values())
                )
                or canonical_json_bytes(value) != raw
            ):
                raise ValueError
            return value
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, EvidenceValidationError) as error:
            raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization authority is invalid") from error

    @contextmanager
    def _authority_lock(self, *, create: bool):
        """Hold parent authority, the root object, and its mutation lock as one unit."""
        parent_store = self._parent_store()
        try:
            with parent_store._mutation_lock(create=create):
                storage = self._evidence_store()
                if create:
                    storage._ensure_root()
                with self._pinned_root_directory() as pinned_root:
                    authority_path = self._authority_path()
                    if create and not authority_path.exists():
                        parent_info = parent_store._validate_existing_path(self.root.parent)
                        root_info = storage._validate_existing_path(self.root)
                        if not stat.S_ISDIR(parent_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
                            raise EvidenceValidationError("authorization authority is not a directory")
                        payload = canonical_json_bytes({
                            "version": _AUTHORITY_VERSION,
                            "root_name_sha256": sha256(self.root.name.encode("utf-8")).hexdigest(),
                            "parent": self._identity(parent_info),
                            "root": self._identity(root_info),
                        })
                        if not parent_store._atomic_create_new(
                            authority_path, payload, phase="control-authority-pin"
                        ):
                            raise EvidenceValidationError("authorization authority already changed")
                    authority = self._read_authority()
                    parent_info = parent_store._validate_existing_path(self.root.parent)
                    root_info = storage._validate_existing_path(self.root)
                    if (
                        not stat.S_ISDIR(parent_info.st_mode)
                        or not stat.S_ISDIR(root_info.st_mode)
                        or authority["parent"] != self._identity(parent_info)
                        or authority["root"] != self._identity(root_info)
                        or self._identity(root_info) != pinned_root
                    ):
                        raise EvidenceValidationError("authorization authority identity changed")
                    with storage._mutation_lock(create=create):
                        locked_root = storage._validate_existing_path(self.root)
                        if self._identity(locked_root) != pinned_root:
                            raise EvidenceValidationError("authorization root changed before lock")
                        yield storage
                        final_root = storage._validate_existing_path(self.root)
                        final_authority = self._read_authority()
                        if (
                            self._identity(final_root) != pinned_root
                            or final_authority != authority
                        ):
                            raise EvidenceValidationError("authorization authority changed while locked")
        except (OSError, EvidenceValidationError) as error:
            raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization authority is invalid") from error

    @contextmanager
    def _pinned_root_directory(self):
        """Hold the original root object against replacement before its lock is opened."""
        storage = self._evidence_store()
        handle: object | None = None
        descriptor: int | None = None
        try:
            before = storage._validate_existing_path(self.root)
            if not stat.S_ISDIR(before.st_mode):
                raise EvidenceValidationError("authorization root is not a directory")
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
                create_file.argtypes = (
                    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
                )
                create_file.restype = wintypes.HANDLE
                raw_handle = create_file(
                    str(self.root), 0x00000001, 0x00000001 | 0x00000002, None, 3,
                    0x02000000 | 0x00200000, None,
                )
                if raw_handle == wintypes.HANDLE(-1).value:
                    raise OSError(ctypes.get_last_error(), "authorization root pin failed")
                handle = raw_handle
            else:
                descriptor = os.open(
                    self.root,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                )
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise EvidenceValidationError("authorization root identity changed")
            named = storage._validate_existing_path(self.root)
            if (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino):
                raise EvidenceValidationError("authorization root identity changed")
            yield self._identity(before)
            after = storage._validate_existing_path(self.root)
            if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                raise EvidenceValidationError("authorization root identity changed")
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if handle is not None:
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)

    def _path(self, digest: str, state: str) -> Path:
        if _HASH.fullmatch(digest) is None or state not in {"prepared", "consumed"}:
            raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization is invalid")
        return self._directory() / f"{digest}.{state}.json"

    @contextmanager
    def _pinned_records_directory(self):
        """Hold the validated records object against replacement through publication."""
        storage = self._evidence_store()
        directory = self._directory()
        handle: object | None = None
        descriptor: int | None = None
        try:
            before = storage._validate_existing_path(directory)
            if not stat.S_ISDIR(before.st_mode):
                raise EvidenceValidationError("authorization records path is not a directory")
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
                create_file.argtypes = (
                    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
                )
                create_file.restype = wintypes.HANDLE
                raw_handle = create_file(
                    str(directory), 0x00000001, 0x00000001 | 0x00000002, None, 3,
                    0x02000000 | 0x00200000, None,
                )
                if raw_handle == wintypes.HANDLE(-1).value:
                    raise OSError(ctypes.get_last_error(), "authorization directory pin failed")
                handle = raw_handle
            else:
                descriptor = os.open(
                    directory,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                )
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise EvidenceValidationError("authorization records identity changed")
            opened_path = storage._validate_existing_path(directory)
            if (opened_path.st_dev, opened_path.st_ino) != (before.st_dev, before.st_ino):
                raise EvidenceValidationError("authorization records identity changed")
            yield directory
            after = storage._validate_existing_path(directory)
            if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                raise EvidenceValidationError("authorization records identity changed")
        except (OSError, EvidenceValidationError) as error:
            raise ControlAuthorizationError(
                "PROBE_AUTHORIZATION_INVALID", "Authorization directory is invalid"
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if handle is not None:
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)

    def _read_prepared(self, digest: str) -> dict[str, object]:
        path = self._path(digest, "prepared")
        storage = self._evidence_store()
        try:
            storage._validate_existing_path(path, regular=True, single_link=True)
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                raw = os.read(descriptor, _MAX_RECORD_BYTES + 1)
                if os.read(descriptor, 1) or len(raw) > _MAX_RECORD_BYTES:
                    raise ValueError
            finally:
                os.close(descriptor)
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
                raise ValueError
            if canonical_json_bytes(value) != raw or sha256(raw).hexdigest() != digest:
                raise ValueError
            if _HASH.fullmatch(str(value["nonce"])) is None:
                raise ValueError
            _closed_binding({key: value[key] for key in _BINDING_KEYS})
            prepared = _parse_utc(value["prepared_at_utc"])
            expires = _parse_utc(value["expires_at_utc"])
            if expires <= prepared or expires - prepared > timedelta(minutes=5):
                raise ValueError
            return value
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, ControlAuthorizationError) as error:
            raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization is unknown or corrupt") from error

    def prepare(
        self, binding: Mapping[str, object], *, now: datetime | None = None
    ) -> PreparedControlAuthorization:
        import secrets

        instant = _utc(now or datetime.now(timezone.utc), "authorization time")
        started = self._monotonic_clock()
        if type(started) not in {int, float} or not math.isfinite(started):
            raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization clock is invalid")
        value = _closed_binding(binding)
        nonce = secrets.token_hex(32)
        expires = instant + timedelta(minutes=5)
        record = {
            **value,
            "nonce": nonce,
            "prepared_at_utc": instant.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "expires_at_utc": expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        payload = canonical_json_bytes(record)
        digest = sha256(payload).hexdigest()
        storage = self._evidence_store()
        with self._authority_lock(create=True):
            with self._pinned_records_directory():
                created = storage._atomic_create_new(
                    self._path(digest, "prepared"), payload, phase="control-authorization-prepare"
                )
                if not created:
                    raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization already exists")
        with self._live_lock:
            self._live_deadlines[digest] = float(started) + 300.0
        return PreparedControlAuthorization(digest, nonce, expires, record)

    def consume(
        self,
        digest: str,
        *,
        operation: str,
        arguments: Mapping[str, object],
        workspace_id: str,
        session_id: str,
        identity: Mapping[str, object] | None,
        state: Mapping[str, object] | None,
        now: datetime | None = None,
    ) -> Mapping[str, object]:
        instant = _utc(now or datetime.now(timezone.utc), "authorization time")
        storage = self._evidence_store()
        with self._authority_lock(create=False):
            with self._pinned_records_directory():
                record = self._read_prepared(digest)
                consumed_payload = canonical_json_bytes(
                    {"action_digest": digest, "consumed_at_utc": instant.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
                )
                if not storage._atomic_create_new(
                    self._path(digest, "consumed"),
                    consumed_payload,
                    phase="control-authorization-consume",
                ):
                    raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization is already consumed")
                with self._live_lock:
                    live_deadline = self._live_deadlines.pop(digest, None)
                live_now = self._monotonic_clock() if live_deadline is not None else None
                prepared_at = _parse_utc(record["prepared_at_utc"])
                expires_at = _parse_utc(record["expires_at_utc"])
                if (
                    (live_deadline is not None and (
                        type(live_now) not in {int, float}
                        or not math.isfinite(live_now)
                        or live_now >= live_deadline
                    ))
                    or
                    instant < prepared_at
                    or instant >= expires_at
                    or operation != record["operation"]
                    or dict(arguments) != record["arguments"]
                    or workspace_id != record["workspace_id"]
                    or session_id != record["session_id"]
                    or (identity is not None and dict(identity) != record["identity_snapshot"])
                    or (state is not None and dict(state) != record["state_snapshot"])
                ):
                    raise ControlAuthorizationError("PROBE_AUTHORIZATION_INVALID", "Authorization binding is invalid")
                return record


__all__ = [
    "ControlAuthorizationError",
    "ControlAuthorizationStore",
    "PreparedControlAuthorization",
]
