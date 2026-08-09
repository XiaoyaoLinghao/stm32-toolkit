"""Portable exclusive probe leases backed by OS locks and owner evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import threading
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Callable, Protocol
from uuid import uuid4

from stm32_toolkit import __version__

from .model import OperationLevel, ProbeOwnerEvidence
from .protocol import PROBE_PROTOCOL_VERSION

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HANDOFF_TICKET = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_REGISTRY_RECORD_LIMIT = 16_384


class _RuntimeRootAuthority(Protocol):
    def directory_descriptor(self, path: Path) -> int | None: ...


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    process_start_id: str
    boot_id: str


class ProbeLeaseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProbeBusyError(ProbeLeaseError):
    def __init__(self, owner: ProbeOwnerEvidence) -> None:
        super().__init__("PROBE_BUSY", "The selected probe is owned by another session")
        self.owner = owner


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("UTC clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _default_process_identity(pid: int) -> ProcessIdentity | None:
    if pid < 1:
        return None
    if sys.platform.startswith("linux"):
        try:
            stat_fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
            start_id = stat_fields[21]
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
                encoding="ascii"
            ).strip()
            return ProcessIdentity(pid, start_id, boot_id)
        except (FileNotFoundError, PermissionError, IndexError, OSError):
            return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            query = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(query, False, pid)
            if not handle:
                return None
            try:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                if not ctypes.windll.kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    return None
                created = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
                return ProcessIdentity(pid, f"filetime-{created}", "windows-current-boot")
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError, ValueError):
            return None
    try:
        os.kill(pid, 0)
    except (OSError, PermissionError):
        return None
    return ProcessIdentity(pid, f"pid-{pid}", "unknown-boot")


def _default_current_identity() -> ProcessIdentity:
    identity = _default_process_identity(os.getpid())
    if identity is None:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Current process identity is unavailable"
        )
    return identity


def _parse_health_endpoint(endpoint: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(endpoint)
    port = parsed.port
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or port < 1
        or parsed.path != "/health"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Probe health endpoint must be exact IPv4 loopback")
    return parsed


def _default_health_check(endpoint: str, lease_id: str) -> bool:
    try:
        _parse_health_endpoint(endpoint)
        request = urllib.request.Request(
            endpoint,
            headers={"X-Probe-Lease": lease_id},
            method="GET",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=0.5) as response:
            if getattr(response, "status", None) != 200:
                return False
            raw = response.read(1025)
        if len(raw) > 1024:
            return False
        payload = json.loads(raw.decode("utf-8"))
        return bool(
            isinstance(payload, dict)
            and set(payload) == {"ok", "protocol", "toolkitVersion", "leaseId"}
            and payload["ok"] is True
            and payload["protocol"] == PROBE_PROTOCOL_VERSION
            and payload["toolkitVersion"] == __version__
            and payload["leaseId"] == lease_id
        )
    except Exception:
        return False


def _is_redirect(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _is_redirect_metadata(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _lock_handle(handle: BinaryIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b" ")
        handle.flush()
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(handle: BinaryIO) -> None:
    if handle.closed:
        return
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_record_path(
    path: Path, *, directory_descriptor: int | None = None
) -> dict[str, object] | None:
    descriptor = -1
    try:
        parent = (
            os.lstat(path.parent)
            if directory_descriptor is None
            else os.fstat(directory_descriptor)
        )
        if (
            (directory_descriptor is None and _is_redirect(path.parent, parent))
            or _is_redirect_metadata(parent)
            or not stat.S_ISDIR(parent.st_mode)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry record is unsafe"
            )
        metadata = (
            os.lstat(path)
            if directory_descriptor is None
            else os.stat(
                path.name, dir_fd=directory_descriptor, follow_symlinks=False
            )
        )
    except FileNotFoundError:
        return None
    except ProbeLeaseError:
        raise
    except OSError as error:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is unavailable"
        ) from error
    if (
        (directory_descriptor is None and _is_redirect(path, metadata))
        or _is_redirect_metadata(metadata)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNSAFE", "Probe registry record is unsafe"
        )
    try:
        if directory_descriptor is None:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        else:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_BINARY", 0),
                dir_fd=directory_descriptor,
            )
        opened = os.fstat(descriptor)
        named = (
            os.lstat(path)
            if directory_descriptor is None
            else os.stat(
                path.name, dir_fd=directory_descriptor, follow_symlinks=False
            )
        )
        if (
            (directory_descriptor is None and _is_redirect(path, named))
            or _is_redirect_metadata(named)
            or not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry record changed during read"
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(_REGISTRY_RECORD_LIMIT + 1).strip()
        named_after = (
            os.lstat(path)
            if directory_descriptor is None
            else os.stat(
                path.name, dir_fd=directory_descriptor, follow_symlinks=False
            )
        )
        parent_after = (
            os.lstat(path.parent)
            if directory_descriptor is None
            else os.fstat(directory_descriptor)
        )
        if (
            (directory_descriptor is None and _is_redirect(path, named_after))
            or (directory_descriptor is None and _is_redirect(path.parent, parent_after))
            or _is_redirect_metadata(named_after)
            or _is_redirect_metadata(parent_after)
            or (opened.st_dev, opened.st_ino)
            != (named_after.st_dev, named_after.st_ino)
            or (parent.st_dev, parent.st_ino)
            != (parent_after.st_dev, parent_after.st_ino)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry record changed during read"
            )
    except ProbeLeaseError:
        raise
    except OSError as error:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is unavailable"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _REGISTRY_RECORD_LIMIT:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is invalid"
        )
    if not raw:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is invalid"
        ) from error
    if not isinstance(value, dict):
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is invalid"
        )
    return value


def _write_record_path(
    path: Path,
    record: dict[str, object],
    *,
    directory_descriptor: int | None = None,
) -> None:
    payload = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        parent = (
            os.lstat(path.parent)
            if directory_descriptor is None
            else os.fstat(directory_descriptor)
        )
        if (
            (directory_descriptor is None and _is_redirect(path.parent, parent))
            or _is_redirect_metadata(parent)
            or not stat.S_ISDIR(parent.st_mode)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry record is unsafe"
            )
        try:
            destination = (
                os.lstat(path)
                if directory_descriptor is None
                else os.stat(
                    path.name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            )
        except FileNotFoundError:
            destination = None
        if destination is not None and (
            (directory_descriptor is None and _is_redirect(path, destination))
            or _is_redirect_metadata(destination)
            or not stat.S_ISREG(destination.st_mode)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry record is unsafe"
            )
        if directory_descriptor is None:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        else:
            descriptor = os.open(
                temporary.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_descriptor,
            )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        parent_after = (
            os.lstat(path.parent)
            if directory_descriptor is None
            else os.fstat(directory_descriptor)
        )
        if (
            (directory_descriptor is None and _is_redirect(path.parent, parent_after))
            or _is_redirect_metadata(parent_after)
            or (parent.st_dev, parent.st_ino)
            != (parent_after.st_dev, parent_after.st_ino)
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry changed during write"
            )
        try:
            destination_after = (
                os.lstat(path)
                if directory_descriptor is None
                else os.stat(
                    path.name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            )
        except FileNotFoundError:
            destination_after = None
        if (
            (destination is None) != (destination_after is None)
            or (
                destination is not None
                and destination_after is not None
                and (
                    (
                        directory_descriptor is None
                        and _is_redirect(path, destination_after)
                    )
                    or _is_redirect_metadata(destination_after)
                    or (destination.st_dev, destination.st_ino)
                    != (destination_after.st_dev, destination_after.st_ino)
                )
            )
        ):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry changed during write"
            )
        if directory_descriptor is None:
            os.replace(temporary, path)
        else:
            os.replace(
                temporary.name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
    except ProbeLeaseError:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if directory_descriptor is None:
                temporary.unlink()
            else:
                os.unlink(temporary.name, dir_fd=directory_descriptor)
        except OSError:
            pass
        raise
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if directory_descriptor is None:
                temporary.unlink()
            else:
                os.unlink(temporary.name, dir_fd=directory_descriptor)
        except OSError:
            pass
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry is unavailable"
        ) from error


def _read_authorized_record(
    path: Path, directory_descriptor: int | None
) -> dict[str, object] | None:
    if directory_descriptor is None:
        return _read_record_path(path)
    return _read_record_path(path, directory_descriptor=directory_descriptor)


def _write_authorized_record(
    path: Path,
    record: dict[str, object],
    directory_descriptor: int | None,
) -> None:
    if directory_descriptor is None:
        _write_record_path(path, record)
    else:
        _write_record_path(
            path, record, directory_descriptor=directory_descriptor
        )


def _owner_from_record(record: dict[str, object]) -> ProbeOwnerEvidence:
    try:
        return ProbeOwnerEvidence(
            probe_id=str(record["probeId"]),
            workspace_id=str(record["workspaceId"]),
            session_id=str(record["sessionId"]),
            lease_id=str(record["leaseId"]),
            pid=int(record["pid"]),
            operation_level=OperationLevel(str(record["operationLevel"])),
            created_at_utc=str(record["createdAtUtc"]),
            heartbeat_at_utc=str(record["heartbeatAtUtc"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is invalid"
        ) from error


def _validate_record_version(record: dict[str, object]) -> None:
    if (
        record.get("schemaVersion") != 1
        or record.get("protocol") != PROBE_PROTOCOL_VERSION
        or record.get("toolkitVersion") != __version__
    ):
        raise ProbeLeaseError(
            "PROBE_REGISTRY_INCOMPATIBLE",
            "Probe registry record uses an incompatible version",
        )


def _consumed_handoff_tombstone(
    record: dict[str, object],
) -> dict[str, object]:
    digest = record.get("consumedTicketSha256")
    if digest is None:
        return {}
    probe_id = record.get("consumedProbeId", record.get("probeId"))
    workspace_id = record.get("consumedWorkspaceId", record.get("workspaceId"))
    session_id = record.get("consumedSessionId", record.get("sessionId"))
    if (
        not isinstance(digest, str)
        or _HANDOFF_TICKET.fullmatch(digest) is None
        or not isinstance(probe_id, str)
        or _IDENTIFIER.fullmatch(probe_id) is None
        or not isinstance(workspace_id, str)
        or _IDENTIFIER.fullmatch(workspace_id) is None
        or not isinstance(session_id, str)
        or _IDENTIFIER.fullmatch(session_id) is None
    ):
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE",
            "Consumed probe handoff recovery evidence is invalid",
        )
    return {
        "consumedTicketSha256": digest,
        "consumedProbeId": probe_id,
        "consumedWorkspaceId": workspace_id,
        "consumedSessionId": session_id,
    }


class ProbeLease:
    def __init__(
        self,
        *,
        handle: BinaryIO,
        record_path: Path,
        record: dict[str, object],
        owner_identity: ProcessIdentity,
        external_record: dict[str, object] | None = None,
        registry_descriptor: int | None = None,
    ) -> None:
        self._handle = handle
        self.record_path = record_path
        self._record = dict(record)
        self._owner_identity = owner_identity
        self._external_record = (
            None if external_record is None else dict(external_record)
        )
        self._record_lock = threading.RLock()
        self._external_consumed = False
        self._released = False
        self._registry_descriptor = registry_descriptor

    @property
    def lease_id(self) -> str:
        return str(self._record["leaseId"])

    @property
    def owner(self) -> ProbeOwnerEvidence:
        return _owner_from_record(self._record)

    def _close_locked_handle(self) -> None:
        error: BaseException | None = None
        if not self._handle.closed:
            try:
                _unlock_handle(self._handle)
            except BaseException as caught:
                error = caught
            try:
                self._handle.close()
            except BaseException as caught:
                if error is None:
                    error = caught
        if self._registry_descriptor is not None:
            descriptor = self._registry_descriptor
            self._registry_descriptor = None
            try:
                os.close(descriptor)
            except BaseException as caught:
                if error is None:
                    error = caught
        if error is not None:
            raise error

    def _require_current_record(self) -> dict[str, object]:
        current = self._read_record()
        if current is None or current.get("leaseId") != self.lease_id:
            self._close_locked_handle()
            self._released = True
            raise ProbeLeaseError(
                "PROBE_LEASE_LOST", "Probe lease ownership no longer matches"
            )
        identity_fields = (
            current.get("pid"),
            current.get("processStartId"),
            current.get("bootId"),
        )
        expected = (
            self._owner_identity.pid,
            self._owner_identity.process_start_id,
            self._owner_identity.boot_id,
        )
        if identity_fields != expected:
            self._close_locked_handle()
            self._released = True
            raise ProbeLeaseError(
                "PROBE_LEASE_LOST", "Probe lease ownership no longer matches"
            )
        return current

    def _read_record(self) -> dict[str, object] | None:
        if self._registry_descriptor is None:
            return _read_record_path(self.record_path)
        return _read_record_path(
            self.record_path, directory_descriptor=self._registry_descriptor
        )

    def _write_record(self, record: dict[str, object]) -> None:
        if self._registry_descriptor is None:
            _write_record_path(self.record_path, record)
            return
        _write_record_path(
            self.record_path,
            record,
            directory_descriptor=self._registry_descriptor,
        )

    def heartbeat(self, *, utc_now: Callable[[], datetime] = _utc_now) -> None:
        with self._record_lock:
            if self._released:
                raise ProbeLeaseError("PROBE_LEASE_LOST", "Probe lease is not active")
            current = self._require_current_record()
            current["heartbeatAtUtc"] = _format_utc(utc_now())
            self._write_record(current)
            self._record = current

    def reserve_external_handoff(self, ticket: str) -> None:
        if not isinstance(ticket, str) or _HANDOFF_TICKET.fullmatch(ticket) is None:
            raise ProbeLeaseError(
                "PROBE_LEASE_INVALID", "External handoff ticket is invalid"
            )
        with self._record_lock:
            if self._released:
                raise ProbeLeaseError(
                    "PROBE_LEASE_LOST", "Probe lease is not available for handoff"
                )
            current = self._require_current_record()
            digest = hashlib.sha256(ticket.encode("ascii")).hexdigest()
            if self._external_record is not None:
                expected = str(current.get("ticketSha256", ""))
                if secrets.compare_digest(digest, expected):
                    return
                raise ProbeLeaseError(
                    "PROBE_LEASE_LOST", "Probe lease is not available for handoff"
                )
            external = dict(current)
            external["state"] = "externally-owned"
            external["ticketSha256"] = digest
            self._write_record(external)
            self._record = external
            self._external_record = external

    def consume_external_handoff(self, ticket: str) -> None:
        if not isinstance(ticket, str) or _HANDOFF_TICKET.fullmatch(ticket) is None:
            raise ProbeLeaseError(
                "PROBE_LEASE_INVALID", "External handoff ticket is invalid"
            )
        with self._record_lock:
            if self._released or self._external_record is None:
                raise ProbeLeaseError(
                    "PROBE_LEASE_LOST", "External handoff claim is not active"
                )
            current = self._require_current_record()
            expected = str(current.get("ticketSha256", ""))
            actual = hashlib.sha256(ticket.encode("ascii")).hexdigest()
            if not secrets.compare_digest(actual, expected):
                raise ProbeLeaseError(
                    "PROBE_LEASE_LOST", "External handoff claim does not match"
                )
            self._external_consumed = True

    def release(self) -> None:
        with self._record_lock:
            if self._released:
                return
            self._require_current_record()
            if self._external_record is not None and self._external_consumed:
                consumed = dict(self._external_record)
                consumed["state"] = "handoff-consumed"
                consumed["leaseId"] = self.lease_id
                self._write_record(consumed)
            elif self._external_record is not None:
                self._write_record(self._external_record)
            else:
                released: dict[str, object] = {
                    "schemaVersion": 1,
                    "state": "released",
                    "leaseId": self.lease_id,
                }
                released.update(_consumed_handoff_tombstone(self._record))
                self._write_record(released)
            self._close_locked_handle()
            self._released = True

    def __enter__(self) -> "ProbeLease":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


class ProbeLeaseManager:
    def __init__(
        self,
        data_root: Path,
        *,
        current_identity: Callable[[], ProcessIdentity] = _default_current_identity,
        inspect_process: Callable[[int], ProcessIdentity | None] = _default_process_identity,
        health_check: Callable[[str, str], bool] = _default_health_check,
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.data_root = data_root.expanduser().absolute()
        self.registry_root = self.data_root / "probe-registry"
        self._current_identity = current_identity
        self._inspect_process = inspect_process
        self._health_check = health_check
        self.utc_now = utc_now

    def record_path(self, probe_id: str) -> Path:
        digest = hashlib.sha256(probe_id.encode("utf-8")).hexdigest()
        return self.registry_root / f"{digest}.lock"

    def _validate_registry_component(self, path: Path) -> None:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return
        except OSError as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe registry cannot be inspected"
            ) from error
        if _is_redirect(path, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNSAFE", "Probe registry contains an unsafe redirect"
            )

    def _validate_data_root_chain(self) -> None:
        for component in reversed((self.data_root, *self.data_root.parents)):
            self._validate_registry_component(component)

    def _ensure_registry(
        self, runtime_root_authority: _RuntimeRootAuthority | None = None
    ) -> int | None:
        root_descriptor = (
            None
            if runtime_root_authority is None
            else runtime_root_authority.directory_descriptor(self.data_root)
        )
        if root_descriptor is not None:
            descriptor = -1
            try:
                try:
                    os.mkdir(self.registry_root.name, dir_fd=root_descriptor)
                except FileExistsError:
                    pass
                descriptor = os.open(
                    self.registry_root.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_descriptor,
                )
                metadata = os.fstat(descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    raise ProbeLeaseError(
                        "PROBE_REGISTRY_UNSAFE",
                        "Probe registry contains an unsafe redirect",
                    )
                return descriptor
            except ProbeLeaseError:
                if descriptor >= 0:
                    os.close(descriptor)
                raise
            except OSError as error:
                if descriptor >= 0:
                    os.close(descriptor)
                raise ProbeLeaseError(
                    "PROBE_REGISTRY_UNAVAILABLE", "Probe registry is unavailable"
                ) from error
        try:
            self._validate_data_root_chain()
            self.data_root.mkdir(parents=True, exist_ok=True)
            self._validate_data_root_chain()
            self._validate_registry_component(self.registry_root)
            self.registry_root.mkdir(exist_ok=True)
            self._validate_registry_component(self.registry_root)
            resolved_registry = self.registry_root.resolve(strict=True)
            resolved_registry.relative_to(self.data_root.resolve(strict=True))
        except ProbeLeaseError:
            raise
        except (OSError, ValueError) as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe registry is unavailable"
            ) from error
        return None

    def _open_guard(
        self, path: Path, *, directory_descriptor: int | None = None
    ) -> BinaryIO:
        try:
            if directory_descriptor is None:
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            else:
                descriptor = os.open(
                    path.name,
                    os.O_RDWR | os.O_CREAT,
                    0o600,
                    dir_fd=directory_descriptor,
                )
            return os.fdopen(descriptor, "r+b", buffering=0)
        except OSError as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe registry is unavailable"
            ) from error

    def _is_record_owner_live(self, record: dict[str, object]) -> bool:
        owner = _owner_from_record(record)
        try:
            process = self._inspect_process(owner.pid)
        except Exception as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe owner cannot be inspected"
            ) from error
        same_process = bool(
            process is not None
            and process.process_start_id == record.get("processStartId")
            and process.boot_id == record.get("bootId")
        )
        health_url = str(record.get("healthUrl", ""))
        try:
            _parse_health_endpoint(health_url)
        except ValueError as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe owner health is invalid"
            ) from error
        try:
            health_live = self._health_check(
                health_url, str(record["leaseId"])
            )
        except Exception as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE", "Probe owner health cannot be verified"
            ) from error
        return same_process or health_live

    def acquire(
        self,
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        operation_level: OperationLevel,
        health_url: str,
        handoff_ticket: str | None = None,
        _runtime_root_authority: _RuntimeRootAuthority | None = None,
    ) -> ProbeLease:
        for field_name, value in (
            ("probe_id", probe_id),
            ("workspace_id", workspace_id),
            ("session_id", session_id),
        ):
            if not _IDENTIFIER.fullmatch(value):
                raise ProbeLeaseError(
                    "PROBE_LEASE_INVALID", f"{field_name} is not a portable identifier"
                )
        try:
            _parse_health_endpoint(health_url)
        except ValueError as error:
            raise ProbeLeaseError(
                "PROBE_LEASE_INVALID", "Probe health endpoint must be loopback-only"
            ) from error
        if handoff_ticket is not None and (
            not isinstance(handoff_ticket, str)
            or _HANDOFF_TICKET.fullmatch(handoff_ticket) is None
        ):
            raise ProbeLeaseError(
                "PROBE_LEASE_INVALID", "External handoff ticket is invalid"
            )

        registry_descriptor = self._ensure_registry(_runtime_root_authority)
        record_path = self.record_path(probe_id)
        guard_path = record_path.with_suffix(".guard")
        try:
            handle = self._open_guard(
                guard_path, directory_descriptor=registry_descriptor
            )
        except BaseException:
            if registry_descriptor is not None:
                os.close(registry_descriptor)
            raise
        try:
            try:
                _lock_handle(handle)
            except (OSError, BlockingIOError):
                record = _read_authorized_record(record_path, registry_descriptor)
                if record is None or record.get("state", "active") not in (
                    "active",
                    "externally-owned",
                    "handoff-consumed",
                    "handoff-finalized",
                ):
                    raise ProbeLeaseError(
                        "PROBE_REGISTRY_UNAVAILABLE", "Probe owner record is unavailable"
                    )
                _validate_record_version(record)
                raise ProbeBusyError(_owner_from_record(record))

            existing = _read_authorized_record(record_path, registry_descriptor)
            consumed_tombstone = (
                {} if existing is None else _consumed_handoff_tombstone(existing)
            )
            external_record: dict[str, object] | None = None
            if existing is not None and existing.get("state") in (
                "handoff-consumed",
                "handoff-finalized",
            ):
                _validate_record_version(existing)
                owner = _owner_from_record(existing)
                _unlock_handle(handle)
                handle.close()
                raise ProbeBusyError(owner)
            if existing is not None and existing.get("state") == "externally-owned":
                _validate_record_version(existing)
                if not self._matches_external_handoff(
                    existing,
                    probe_id=probe_id,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    operation_level=operation_level,
                    ticket=handoff_ticket,
                ):
                    owner = _owner_from_record(existing)
                    _unlock_handle(handle)
                    handle.close()
                    raise ProbeBusyError(owner)
                external_record = dict(existing)
            elif (
                existing is not None
                and existing.get("state", "active") == "active"
            ):
                _validate_record_version(existing)
                if "ticketSha256" in existing:
                    if not self._matches_external_handoff(
                        existing,
                        probe_id=probe_id,
                        workspace_id=workspace_id,
                        session_id=session_id,
                        operation_level=operation_level,
                        ticket=handoff_ticket,
                    ):
                        owner = _owner_from_record(existing)
                        _unlock_handle(handle)
                        handle.close()
                        raise ProbeBusyError(owner)
                    external_record = dict(existing)
                    external_record["state"] = "externally-owned"
                    external_record["leaseId"] = str(
                        existing.get("reservationLeaseId", existing["leaseId"])
                    )
                    external_record.pop("reservationLeaseId", None)
                elif handoff_ticket is not None:
                    owner = _owner_from_record(existing)
                    _unlock_handle(handle)
                    handle.close()
                    raise ProbeBusyError(owner)
                if self._is_record_owner_live(existing):
                    owner = _owner_from_record(existing)
                    _unlock_handle(handle)
                    handle.close()
                    raise ProbeBusyError(owner)

            if handoff_ticket is not None and external_record is None:
                raise ProbeLeaseError(
                    "PROBE_HANDOFF_INVALID",
                    "External handoff reservation does not match",
                )

            identity = self._current_identity()
            timestamp = _format_utc(self.utc_now())
            record: dict[str, object] = {
                "schemaVersion": 1,
                "protocol": PROBE_PROTOCOL_VERSION,
                "toolkitVersion": __version__,
                "probeId": probe_id,
                "workspaceId": workspace_id,
                "sessionId": session_id,
                "leaseId": f"lease-{uuid4().hex}",
                "pid": identity.pid,
                "processStartId": identity.process_start_id,
                "bootId": identity.boot_id,
                "healthUrl": health_url,
                "operationLevel": operation_level.value,
                "createdAtUtc": timestamp,
                "heartbeatAtUtc": timestamp,
                "state": "active",
            }
            record.update(consumed_tombstone)
            if external_record is not None:
                record["ticketSha256"] = external_record["ticketSha256"]
                record["reservationLeaseId"] = external_record["leaseId"]
            _write_authorized_record(record_path, record, registry_descriptor)
            lease = ProbeLease(
                handle=handle,
                record_path=record_path,
                record=record,
                owner_identity=identity,
                external_record=external_record,
                registry_descriptor=registry_descriptor,
            )
            registry_descriptor = None
            return lease
        except Exception:
            if not handle.closed:
                try:
                    _unlock_handle(handle)
                except OSError:
                    pass
                handle.close()
            if registry_descriptor is not None:
                os.close(registry_descriptor)
            raise

    @staticmethod
    def _matches_external_handoff(
        record: dict[str, object],
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        operation_level: OperationLevel,
        ticket: str | None,
    ) -> bool:
        return bool(
            record.get("operationLevel") == operation_level.value
            and ProbeLeaseManager._matches_handoff_identity(
                record,
                probe_id=probe_id,
                workspace_id=workspace_id,
                session_id=session_id,
                ticket=ticket,
            )
        )

    @staticmethod
    def _matches_handoff_identity(
        record: dict[str, object],
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        ticket: str | None,
    ) -> bool:
        if ticket is None:
            return False
        digest = hashlib.sha256(ticket.encode("ascii")).hexdigest()
        expected = record.get("ticketSha256")
        return bool(
            isinstance(expected, str)
            and secrets.compare_digest(digest, expected)
            and record.get("probeId") == probe_id
            and record.get("workspaceId") == workspace_id
            and record.get("sessionId") == session_id
        )

    def finalize_consumed_handoff(
        self,
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        ticket: str,
        _runtime_root_authority: _RuntimeRootAuthority | None = None,
    ) -> bool:
        return self._transition_consumed_handoff(
            probe_id=probe_id,
            workspace_id=workspace_id,
            session_id=session_id,
            ticket=ticket,
            acknowledge=False,
            runtime_root_authority=_runtime_root_authority,
        )

    def acknowledge_consumed_handoff(
        self,
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        ticket: str,
        _runtime_root_authority: _RuntimeRootAuthority | None = None,
    ) -> bool:
        return self._transition_consumed_handoff(
            probe_id=probe_id,
            workspace_id=workspace_id,
            session_id=session_id,
            ticket=ticket,
            acknowledge=True,
            runtime_root_authority=_runtime_root_authority,
        )

    def _transition_consumed_handoff(
        self,
        *,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        ticket: str,
        acknowledge: bool,
        runtime_root_authority: _RuntimeRootAuthority | None,
    ) -> bool:
        if (
            not all(
                _IDENTIFIER.fullmatch(value)
                for value in (probe_id, workspace_id, session_id)
            )
            or _HANDOFF_TICKET.fullmatch(ticket) is None
        ):
            raise ProbeLeaseError(
                "PROBE_LEASE_INVALID", "External handoff identity is invalid"
            )
        registry_descriptor = self._ensure_registry(runtime_root_authority)
        record_path = self.record_path(probe_id)
        try:
            handle = self._open_guard(
                record_path.with_suffix(".guard"),
                directory_descriptor=registry_descriptor,
            )
        except BaseException:
            if registry_descriptor is not None:
                os.close(registry_descriptor)
            raise
        try:
            _lock_handle(handle)
            record = _read_authorized_record(record_path, registry_descriptor)
            if record is None:
                return False
            state = record.get("state")
            digest = hashlib.sha256(ticket.encode("ascii")).hexdigest()
            if state == "released":
                tombstone = _consumed_handoff_tombstone(record)
                return bool(
                    acknowledge
                    and tombstone.get("consumedProbeId") == probe_id
                    and tombstone.get("consumedWorkspaceId") == workspace_id
                    and tombstone.get("consumedSessionId") == session_id
                    and isinstance(tombstone.get("consumedTicketSha256"), str)
                    and secrets.compare_digest(
                        digest, str(tombstone["consumedTicketSha256"])
                    )
                )
            if state not in ("handoff-consumed", "handoff-finalized"):
                return False
            _validate_record_version(record)
            if not self._matches_handoff_identity(
                record,
                probe_id=probe_id,
                workspace_id=workspace_id,
                session_id=session_id,
                ticket=ticket,
            ):
                return False
            if acknowledge:
                if state != "handoff-finalized":
                    return False
                _write_authorized_record(
                    record_path,
                    {
                        "schemaVersion": 1,
                        "state": "released",
                        "leaseId": str(record["leaseId"]),
                        "consumedTicketSha256": digest,
                        "consumedProbeId": probe_id,
                        "consumedWorkspaceId": workspace_id,
                        "consumedSessionId": session_id,
                    },
                    registry_descriptor,
                )
            elif state == "handoff-consumed":
                finalized = dict(record)
                finalized["state"] = "handoff-finalized"
                _write_authorized_record(
                    record_path, finalized, registry_descriptor
                )
            return True
        except (OSError, BlockingIOError) as error:
            raise ProbeLeaseError(
                "PROBE_REGISTRY_UNAVAILABLE",
                "Probe handoff record cannot be transitioned",
            ) from error
        finally:
            if not handle.closed:
                try:
                    _unlock_handle(handle)
                except OSError:
                    pass
                handle.close()
            if registry_descriptor is not None:
                os.close(registry_descriptor)
