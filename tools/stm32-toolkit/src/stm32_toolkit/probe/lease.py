"""Portable exclusive probe leases backed by OS locks and owner evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Callable
from uuid import uuid4

from stm32_toolkit import __version__

from .model import OperationLevel, ProbeOwnerEvidence
from .protocol import PROBE_PROTOCOL_VERSION

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


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


def _read_record_path(path: Path) -> dict[str, object] | None:
    try:
        raw = path.read_bytes().strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry record is unavailable"
        ) from error
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


def _write_record_path(path: Path, record: dict[str, object]) -> None:
    payload = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except OSError:
            pass
        raise ProbeLeaseError(
            "PROBE_REGISTRY_UNAVAILABLE", "Probe registry is unavailable"
        ) from error


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


class ProbeLease:
    def __init__(
        self,
        *,
        handle: BinaryIO,
        record_path: Path,
        record: dict[str, object],
        owner_identity: ProcessIdentity,
    ) -> None:
        self._handle = handle
        self.record_path = record_path
        self._record = dict(record)
        self._owner_identity = owner_identity
        self._released = False

    @property
    def lease_id(self) -> str:
        return str(self._record["leaseId"])

    @property
    def owner(self) -> ProbeOwnerEvidence:
        return _owner_from_record(self._record)

    def _close_locked_handle(self) -> None:
        if not self._handle.closed:
            try:
                _unlock_handle(self._handle)
            finally:
                self._handle.close()

    def _require_current_record(self) -> dict[str, object]:
        current = _read_record_path(self.record_path)
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

    def heartbeat(self, *, utc_now: Callable[[], datetime] = _utc_now) -> None:
        if self._released:
            raise ProbeLeaseError("PROBE_LEASE_LOST", "Probe lease is not active")
        current = self._require_current_record()
        current["heartbeatAtUtc"] = _format_utc(utc_now())
        _write_record_path(self.record_path, current)
        self._record = current

    def release(self) -> None:
        if self._released:
            return
        self._require_current_record()
        _write_record_path(
            self.record_path,
            {
                "schemaVersion": 1,
                "state": "released",
                "leaseId": self.lease_id,
            },
        )
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

    def _ensure_registry(self) -> None:
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

    def _open_guard(self, path: Path) -> BinaryIO:
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
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

        self._ensure_registry()
        record_path = self.record_path(probe_id)
        guard_path = record_path.with_suffix(".guard")
        handle = self._open_guard(guard_path)
        try:
            try:
                _lock_handle(handle)
            except (OSError, BlockingIOError):
                record = _read_record_path(record_path)
                if record is None or record.get("state", "active") != "active":
                    raise ProbeLeaseError(
                        "PROBE_REGISTRY_UNAVAILABLE", "Probe owner record is unavailable"
                    )
                _validate_record_version(record)
                raise ProbeBusyError(_owner_from_record(record))

            existing = _read_record_path(record_path)
            if (
                existing is not None
                and existing.get("state", "active") == "active"
            ):
                _validate_record_version(existing)
                if self._is_record_owner_live(existing):
                    owner = _owner_from_record(existing)
                    _unlock_handle(handle)
                    handle.close()
                    raise ProbeBusyError(owner)

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
            _write_record_path(record_path, record)
            return ProbeLease(
                handle=handle,
                record_path=record_path,
                record=record,
                owner_identity=identity,
            )
        except Exception:
            if not handle.closed:
                try:
                    _unlock_handle(handle)
                except OSError:
                    pass
                handle.close()
            raise
