"""Crash-safe, one-time ownership handoff to an external Cortex-Debug session."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Mapping

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.result import OperationResult

from .flash import _load_fresh_firmware, _verify_segments
from .model import OperationLevel

_BEGIN_OPERATION = "stm32_debug_handoff_begin"
_END_OPERATION = "stm32_debug_handoff_end"
_STATE_NAME = "debug-handoff.json"
_GUARD_NAME = ".debug-handoff.guard"
_STATE_LIMIT = 65_536
_LEASE_RECORD_LIMIT = 16_384
_FLASH_RESULT_LIMIT = 8 * 1024 * 1024
_REPARSE_POINT = 0x400
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_TARGET_CANONICAL = re.compile(r"[^a-z0-9]")
_FLASH_RESULT_REL = "artifacts/migration/flash-result.json"
_FLASH_FIELDS = {
    "schemaVersion",
    "status",
    "code",
    "toolkitVersion",
    "buildId",
    "elfSha256",
    "elfSize",
    "targetDevice",
    "debugTarget",
    "probeId",
    "workspaceId",
    "sessionId",
    "verifiedBytes",
    "backendBytesProgrammed",
    "backendSectorsProgrammed",
    "startedAtUtc",
    "finishedAtUtc",
    "flashResultPath",
    "elfPath",
    "gitHead",
    "gitDirty",
    "inputSnapshotSha256",
    "operationLevel",
    "authorized",
}
_STATE_FIELDS = {
    "schemaVersion",
    "toolkitVersion",
    "state",
    "ticketId",
    "workspaceId",
    "sessionId",
    "probeId",
    "leaseId",
    "target",
    "buildId",
    "elfSha256",
    "previousWatchSelection",
    "issuedAtUtc",
}
_async_locks: dict[Path, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}


@dataclass(frozen=True)
class DebugHandoffRequest:
    project_root: Path
    expected_build_id: str
    expected_elf_sha256: str
    authorized: bool
    previous_watch_selection: tuple[str, ...] = ()


@dataclass(frozen=True)
class CortexDebugAttachContract:
    target: str
    executable: str
    serial_number: str
    servertype: str = "pyocd"
    request: str = "attach"

    def __post_init__(self) -> None:
        if self.servertype != "pyocd" or self.request != "attach":
            raise ValueError("Cortex-Debug contract must use PyOCD attach mode")
        if _IDENTIFIER.fullmatch(self.target) is None:
            raise ValueError("Cortex-Debug target is invalid")
        if _IDENTIFIER.fullmatch(self.serial_number) is None:
            raise ValueError("Cortex-Debug probe selector is invalid")
        _validate_relative_path(self.executable)

    def to_dict(self) -> dict[str, str]:
        return {
            "servertype": "pyocd",
            "request": "attach",
            "target": self.target,
            "serialNumber": self.serial_number,
            "executable": f"${{workspaceFolder}}/{self.executable}",
        }


@dataclass(frozen=True)
class HandoffTicket:
    ticket_id: str = field(repr=False)
    cortex_debug: CortexDebugAttachContract

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket": self.ticket_id,
            "cortexDebug": self.cortex_debug.to_dict(),
        }


@dataclass(frozen=True)
class HandoffRestore:
    previous_watch_selection: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"previousWatchSelection": list(self.previous_watch_selection)}


class _HandoffFailure(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _fail(code: str, message: str, **details: object) -> _HandoffFailure:
    return _HandoffFailure(code, message, details)


def _failure(operation: str, error: BaseException) -> OperationResult[None]:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    details = getattr(error, "details", None)
    if isinstance(code, str) and isinstance(message, str):
        return OperationResult.failure(
            operation, code, message, details if isinstance(details, Mapping) else {}
        )
    return OperationResult.failure(
        operation, "HANDOFF_INTERNAL_ERROR", "Debug ownership handoff failed", {}
    )


def _validate_relative_path(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("Cortex-Debug executable path is invalid")
    path = Path(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("Cortex-Debug executable path is invalid")


def _request_root(request: DebugHandoffRequest) -> Path:
    if not isinstance(request.project_root, Path):
        raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field="projectRoot")
    try:
        root = request.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field="projectRoot") from None
    if not root.is_dir():
        raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field="projectRoot")
    return root


def _valid_selection(value: object, container_type: type[tuple] | type[list]) -> bool:
    return (
        type(value) is container_type
        and len(value) <= 128
        and all(
            isinstance(item, str)
            and item
            and len(item) <= 512
            and "\x00" not in item
            and all(ord(character) >= 32 for character in item)
            for item in value
        )
        and sum(len(item) for item in value) <= 16_384
    )


def _validate_request(request: object) -> tuple[DebugHandoffRequest, Path]:
    if not isinstance(request, DebugHandoffRequest):
        raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field="request")
    if type(request.authorized) is not bool or request.authorized is not True:
        raise _fail("AUTHORIZATION_REQUIRED", "Debug ownership handoff requires explicit authorization")
    root = _request_root(request)
    for field, value in (
        ("expectedBuildId", request.expected_build_id),
        ("expectedElfSha256", request.expected_elf_sha256),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field=field)
    selection = request.previous_watch_selection
    if not _valid_selection(selection, tuple):
        raise _fail("HANDOFF_REQUEST_INVALID", "Debug handoff request is invalid", field="previousWatchSelection")
    return request, root


def _is_redirect(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        int(getattr(info, "st_file_attributes", 0)) & _REPARSE_POINT
    )


def _safe_session_root(supervisor: object) -> tuple[object, Path]:
    config = getattr(supervisor, "_config", None)
    session_root = getattr(config, "session_root", None)
    if not isinstance(session_root, Path):
        raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe supervisor configuration is invalid")
    root = session_root.expanduser().absolute()
    manager = getattr(supervisor, "_lease_manager", None)
    data_root = getattr(manager, "data_root", None)
    if isinstance(data_root, Path):
        data_root = data_root.expanduser().absolute()
        try:
            relative = root.relative_to(data_root)
        except ValueError:
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="sessionRoot") from None
        components = (data_root, *(data_root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)))
    else:
        components = (root,)
    for component in components:
        try:
            info = os.lstat(component)
        except OSError:
            raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
        if _is_redirect(info) or not stat.S_ISDIR(info.st_mode):
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="sessionRoot")
    for name in (_STATE_NAME, _GUARD_NAME):
        path = root / name
        try:
            child = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError:
            raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
        if _is_redirect(child) or not stat.S_ISREG(child.st_mode):
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="statePath")
    return config, root


def _async_lock(path: Path) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    current = _async_locks.get(path)
    if current is None or (current[0] is not loop and not current[1].locked()):
        current = (loop, asyncio.Lock())
        _async_locks[path] = current
    return current[1]


@contextmanager
def _process_guard(path: Path) -> Iterator[None]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        opened = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            _is_redirect(named)
            or not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            os.close(descriptor)
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="guardRace")
    except _HandoffFailure:
        raise
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _directory_identity_chain(root: Path, parent: Path) -> tuple[tuple[int, int], ...]:
    lexical_root = root.expanduser().absolute()
    lexical_parent = parent.expanduser().absolute()
    try:
        relative = lexical_parent.relative_to(lexical_root)
    except ValueError:
        raise _fail(
            "HANDOFF_STATE_INVALID",
            "Debug handoff state is invalid",
            rule="parentContainment",
        ) from None
    components = (
        lexical_root,
        *(
            lexical_root.joinpath(*relative.parts[:index])
            for index in range(1, len(relative.parts) + 1)
        ),
    )
    identities: list[tuple[int, int]] = []
    try:
        for component in components:
            metadata = os.lstat(component)
            if _is_redirect(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise _fail(
                    "HANDOFF_STATE_INVALID",
                    "Debug handoff state is invalid",
                    rule="parentChain",
                )
            identities.append((metadata.st_dev, metadata.st_ino))
    except _HandoffFailure:
        raise
    except OSError:
        raise _fail(
            "HANDOFF_STATE_UNAVAILABLE",
            "Debug handoff state is unavailable",
        ) from None
    return tuple(identities)


def _read_json_file(
    path: Path,
    limit: int,
    *,
    missing: bool = False,
    containment_root: Path | None = None,
) -> dict[str, object] | None:
    descriptor = -1
    root = path.parent if containment_root is None else containment_root
    parent_identity = _directory_identity_chain(root, path.parent)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        if missing:
            return None
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="missing") from None
    except OSError:
        raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
    if _is_redirect(info) or not stat.S_ISREG(info.st_mode):
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="regularFile")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            _is_redirect(named)
            or not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _fail(
                "HANDOFF_STATE_INVALID",
                "Debug handoff state is invalid",
                rule="fileRace",
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(limit + 1)
            named_after = os.lstat(path)
            parent_after = _directory_identity_chain(root, path.parent)
            if (
                _is_redirect(named_after)
                or not stat.S_ISREG(named_after.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (named_after.st_dev, named_after.st_ino)
                or parent_after != parent_identity
            ):
                raise _fail(
                    "HANDOFF_STATE_INVALID",
                    "Debug handoff state is invalid",
                    rule="fileRace",
                )
    except _HandoffFailure:
        raise
    except OSError:
        raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > limit:
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="size")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="json") from None
    if not isinstance(value, dict):
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="type")
    return value


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _validate_state(value: dict[str, object]) -> dict[str, object]:
    if set(value) != _STATE_FIELDS or value.get("schemaVersion") != 1 or value.get("toolkitVersion") != __version__:
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="fields")
    state = value.get("state")
    ticket = value.get("ticketId")
    selection = value.get("previousWatchSelection")
    if state not in ("paused-for-debug", "externally-owned", "reacquiring", "observing"):
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="state")
    if state == "observing":
        if ticket is not None or selection != []:
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="consumed")
    elif not isinstance(ticket, str) or _SHA256.fullmatch(ticket) is None:
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="ticket")
    for field in ("workspaceId", "sessionId", "probeId", "leaseId", "target"):
        if not isinstance(value.get(field), str) or _IDENTIFIER.fullmatch(str(value[field])) is None:
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule=field)
    for field in ("buildId", "elfSha256"):
        if not isinstance(value.get(field), str) or _SHA256.fullmatch(str(value[field])) is None:
            raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule=field)
    if not isinstance(value.get("issuedAtUtc"), str) or _TIMESTAMP.fullmatch(str(value["issuedAtUtc"])) is None:
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="issuedAtUtc")
    if not _valid_selection(selection, list):
        raise _fail("HANDOFF_STATE_INVALID", "Debug handoff state is invalid", rule="selection")
    return value


def _read_state(session_root: Path) -> dict[str, object] | None:
    value = _read_json_file(
        session_root / _STATE_NAME,
        _STATE_LIMIT,
        missing=True,
        containment_root=session_root,
    )
    return None if value is None else _validate_state(value)


def _write_state(session_root: Path, state: dict[str, object]) -> None:
    _validate_state(state)
    path = session_root / _STATE_NAME
    data = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    descriptor = -1
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".debug-handoff-", suffix=".tmp", dir=session_root)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        if os.name != "nt":
            os.chmod(path, 0o600)
        try:
            directory = os.open(session_root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    except OSError:
        raise _fail("HANDOFF_STATE_UNAVAILABLE", "Debug handoff state is unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _configuration(config: object, root: Path) -> tuple[str, str, str]:
    probe = getattr(config, "probe_id", None)
    workspace = getattr(config, "workspace_id", None)
    session = getattr(config, "session_id", None)
    configured_root = getattr(config, "project_root", None)
    level = getattr(config, "operation_level", None)
    level_value = getattr(level, "value", level)
    try:
        root_matches = (
            isinstance(configured_root, Path)
            and configured_root.expanduser().resolve(strict=True) == root
        )
    except (OSError, RuntimeError):
        root_matches = False
    if (
        any(not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None for value in (probe, workspace, session))
        or not root_matches
        or level_value != OperationLevel.MODIFY.value
    ):
        raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe supervisor configuration is invalid")
    return probe, workspace, session


def _endpoint(endpoint: object, probe: str, workspace: str, session: str) -> str:
    lease_id = getattr(endpoint, "lease_id", None)
    level = getattr(endpoint, "operation_level", None)
    if (
        getattr(endpoint, "probe_id", None) != probe
        or getattr(endpoint, "workspace_id", None) != workspace
        or getattr(endpoint, "session_id", None) != session
        or not isinstance(lease_id, str)
        or _IDENTIFIER.fullmatch(lease_id) is None
        or getattr(level, "value", level) != OperationLevel.MODIFY.value
    ):
        raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe supervisor endpoint is invalid")
    return lease_id


def _validate_client_endpoint(client: object, endpoint: object) -> None:
    actual = getattr(client, "endpoint", None)
    expected_token = getattr(endpoint, "token", None)
    actual_token = getattr(actual, "token", None)
    fields = (
        "protocol",
        "toolkit_version",
        "host",
        "port",
        "workspace_id",
        "session_id",
        "lease_id",
        "probe_id",
    )
    if (
        actual is None
        or any(getattr(actual, field, None) != getattr(endpoint, field, None) for field in fields)
        or getattr(getattr(actual, "operation_level", None), "value", None)
        != getattr(getattr(endpoint, "operation_level", None), "value", None)
        or not isinstance(expected_token, str)
        or not isinstance(actual_token, str)
        or not secrets.compare_digest(actual_token, expected_token)
    ):
        raise _fail(
            "HANDOFF_CLIENT_MISMATCH",
            "Probe client does not match the owning service endpoint",
        )


def _load_flash_result(root: Path) -> dict[str, object]:
    path = root
    for component in _FLASH_RESULT_REL.split("/"):
        path /= component
        try:
            info = os.lstat(path)
        except OSError:
            raise _fail("HANDOFF_FLASH_REQUIRED", "A current successful flash result is required") from None
        if _is_redirect(info):
            raise _fail("HANDOFF_FLASH_REQUIRED", "A current successful flash result is required")
    try:
        value = _read_json_file(
            path, _FLASH_RESULT_LIMIT, containment_root=root
        )
    except _HandoffFailure:
        raise _fail("HANDOFF_FLASH_REQUIRED", "A current successful flash result is required") from None
    assert value is not None
    if set(value) != _FLASH_FIELDS or value.get("schemaVersion") != 1 or value.get("status") != "success" or value.get("code") != "OK":
        raise _fail("HANDOFF_FLASH_REQUIRED", "A current successful flash result is required")
    return value


def _validate_flash(
    result: Mapping[str, object],
    firmware: object,
    *,
    probe: str,
    workspace: str,
    session: str,
    target: str,
) -> None:
    identity = getattr(firmware, "identity")
    model = getattr(firmware, "model")
    segments = getattr(firmware, "segments")
    verified_bytes = sum(len(segment.data) for segment in segments)
    telemetry = (
        result.get("backendBytesProgrammed"),
        result.get("backendSectorsProgrammed"),
    )
    if (
        result.get("toolkitVersion") != __version__
        or result.get("authorized") is not True
        or result.get("operationLevel") != "modify"
        or result.get("flashResultPath") != _FLASH_RESULT_REL
        or result.get("buildId") != identity.get("buildId")
        or result.get("elfSha256") != identity.get("elfSha256")
        or result.get("elfSize") != len(getattr(firmware, "elf_data"))
        or result.get("verifiedBytes") != verified_bytes
        or result.get("elfPath") != getattr(firmware, "elf_path")
        or result.get("targetDevice") != model.target.device
        or result.get("debugTarget") != target
        or result.get("probeId") != probe
        or result.get("workspaceId") != workspace
        or result.get("sessionId") != session
        or result.get("gitHead") != identity.get("gitHead")
        or result.get("gitDirty") != identity.get("gitDirty")
        or result.get("inputSnapshotSha256") != identity.get("inputSnapshotSha256")
        or not isinstance(result.get("startedAtUtc"), str)
        or _TIMESTAMP.fullmatch(str(result["startedAtUtc"])) is None
        or not isinstance(result.get("finishedAtUtc"), str)
        or _TIMESTAMP.fullmatch(str(result["finishedAtUtc"])) is None
        or any(
            value is not None
            and (type(value) is not int or value < 0 or value > 0x7FFF_FFFF)
            for value in telemetry
        )
    ):
        raise _fail("HANDOFF_FLASH_MISMATCH", "Flash result does not match the debug handoff")


def _canonical_target(value: str) -> str:
    return _TARGET_CANONICAL.sub("", value.casefold())


def _validate_attachment(attachment: object, probe: str, target: str) -> None:
    resolved = getattr(attachment, "resolved_part_number", None)
    if (
        getattr(attachment, "probe_id", None) != probe
        or getattr(attachment, "requested_target", None) != target
        or not isinstance(resolved, str)
        or _canonical_target(resolved) != _canonical_target(target)
        or getattr(attachment, "core_count", None) != 1
    ):
        raise _fail("HANDOFF_TARGET_MISMATCH", "Connected target does not match the debug handoff")


def _state_matches(
    state: Mapping[str, object],
    *,
    probe: str,
    workspace: str,
    session: str,
    target: str,
    build_id: str,
    elf_sha: str,
    selection: tuple[str, ...] | None = None,
) -> bool:
    return (
        state.get("probeId") == probe
        and state.get("workspaceId") == workspace
        and state.get("sessionId") == session
        and state.get("target") == target
        and state.get("buildId") == build_id
        and state.get("elfSha256") == elf_sha
        and (selection is None or state.get("previousWatchSelection") == list(selection))
    )


def _ticket(state: Mapping[str, object], executable: str) -> HandoffTicket:
    return HandoffTicket(
        str(state["ticketId"]),
        CortexDebugAttachContract(
            str(state["target"]), executable, str(state["probeId"])
        ),
    )


def _prove_released(supervisor: object, probe: str, lease_id: str, endpoint_path: Path | None) -> None:
    if getattr(supervisor, "endpoint", None) is not None:
        raise _fail("HANDOFF_STOP_FAILED", "Probe Service did not stop cleanly")
    if endpoint_path is not None and endpoint_path.exists():
        raise _fail("HANDOFF_STOP_FAILED", "Probe Service endpoint remained active")
    manager = getattr(supervisor, "_lease_manager", None)
    try:
        record_path = manager.record_path(probe)
        data_root = getattr(manager, "data_root", None)
        containment_root = data_root if isinstance(data_root, Path) else record_path.parent
        record = _read_json_file(
            record_path,
            _LEASE_RECORD_LIMIT,
            containment_root=containment_root,
        )
    except Exception:
        raise _fail("HANDOFF_STOP_FAILED", "Probe lease release could not be proven") from None
    if record != {"schemaVersion": 1, "state": "released", "leaseId": lease_id}:
        raise _fail("HANDOFF_STOP_FAILED", "Probe lease release could not be proven")


async def begin_debug_handoff(
    request: object, supervisor: object, client: object
) -> OperationResult[HandoffTicket]:
    """Release one Toolkit-owned probe for an explicitly authorized debugger."""

    try:
        typed, root = _validate_request(request)
        config, session_root = _safe_session_root(supervisor)
        probe, workspace, session = _configuration(config, root)
        lock = _async_lock(session_root)
        async with lock:
            with _process_guard(session_root / _GUARD_NAME):
                firmware = _load_fresh_firmware(root)
                target = firmware.model.debug.target
                if (
                    not isinstance(target, str)
                    or typed.expected_build_id != firmware.identity.get("buildId")
                    or typed.expected_elf_sha256 != firmware.identity.get("elfSha256")
                ):
                    raise _fail("HANDOFF_IDENTITY_MISMATCH", "Firmware identity does not match the debug handoff")
                flash_result = _load_flash_result(root)
                _validate_flash(
                    flash_result,
                    firmware,
                    probe=probe,
                    workspace=workspace,
                    session=session,
                    target=target,
                )
                state = _read_state(session_root)
                if state is not None and state["state"] == "observing":
                    state = None
                if state is not None:
                    if not _state_matches(
                        state,
                        probe=probe,
                        workspace=workspace,
                        session=session,
                        target=target,
                        build_id=typed.expected_build_id,
                        elf_sha=typed.expected_elf_sha256,
                        selection=typed.previous_watch_selection,
                    ):
                        raise _fail("HANDOFF_STATE_CONFLICT", "Another debug handoff is active")
                    if state["state"] == "externally-owned":
                        _prove_released(
                            supervisor,
                            probe,
                            str(state["leaseId"]),
                            session_root / "probe-endpoint.json",
                        )
                        return OperationResult.success(
                            _BEGIN_OPERATION, _ticket(state, firmware.elf_path)
                        )
                    if state["state"] == "reacquiring":
                        raise _fail("HANDOFF_STATE_CONFLICT", "Debug handoff is already reacquiring")
                endpoint = getattr(supervisor, "endpoint", None)
                if endpoint is None and state is None:
                    raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe Service is not active")
                if endpoint is None:
                    raise _fail(
                        "HANDOFF_REACQUIRE_REQUIRED",
                        "Probe Service must be reacquired before debug handoff can resume",
                    )
                if endpoint is not None:
                    lease_id = _endpoint(endpoint, probe, workspace, session)
                    _validate_client_endpoint(client, endpoint)
                    try:
                        await supervisor.drain_modifications()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        raise _fail(
                            "HANDOFF_DRAIN_FAILED",
                            "Probe Service modification operations could not be drained",
                        ) from None

                    firmware = _load_fresh_firmware(root)
                    target = firmware.model.debug.target
                    if (
                        not isinstance(target, str)
                        or typed.expected_build_id != firmware.identity.get("buildId")
                        or typed.expected_elf_sha256 != firmware.identity.get("elfSha256")
                    ):
                        raise _fail(
                            "HANDOFF_IDENTITY_MISMATCH",
                            "Firmware identity does not match the debug handoff",
                        )
                    flash_result = _load_flash_result(root)
                    _validate_flash(
                        flash_result,
                        firmware,
                        probe=probe,
                        workspace=workspace,
                        session=session,
                        target=target,
                    )
                    attachment = await client.attach(probe, target)
                    _validate_attachment(attachment, probe, target)
                    await _verify_segments(client, firmware.segments)

                    current_firmware = _load_fresh_firmware(root)
                    if (
                        current_firmware.identity.get("buildId")
                        != typed.expected_build_id
                        or current_firmware.identity.get("elfSha256")
                        != typed.expected_elf_sha256
                        or current_firmware.model.debug.target != target
                    ):
                        raise _fail(
                            "HANDOFF_IDENTITY_MISMATCH",
                            "Firmware identity changed during debug handoff",
                        )
                    current_flash = _load_flash_result(root)
                    _validate_flash(
                        current_flash,
                        current_firmware,
                        probe=probe,
                        workspace=workspace,
                        session=session,
                        target=target,
                    )
                    firmware = current_firmware

                if state is None:
                    state = {
                        "schemaVersion": 1,
                        "toolkitVersion": __version__,
                        "state": "paused-for-debug",
                        "ticketId": secrets.token_hex(32),
                        "workspaceId": workspace,
                        "sessionId": session,
                        "probeId": probe,
                        "leaseId": lease_id,
                        "target": target,
                        "buildId": typed.expected_build_id,
                        "elfSha256": typed.expected_elf_sha256,
                        "previousWatchSelection": list(typed.previous_watch_selection),
                        "issuedAtUtc": utc_now_rfc3339(),
                    }
                    _write_state(session_root, state)
                else:
                    state["leaseId"] = lease_id
                    _write_state(session_root, state)

                endpoint_path = getattr(endpoint, "record_path", None)
                if endpoint_path is not None and not isinstance(endpoint_path, Path):
                    raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe supervisor endpoint is invalid")
                stop_cancellation: asyncio.CancelledError | None = None
                if endpoint is not None:
                    try:
                        await supervisor.stop()
                    except asyncio.CancelledError as error:
                        stop_cancellation = error
                    except Exception:
                        raise _fail("HANDOFF_STOP_FAILED", "Probe Service could not be stopped") from None
                try:
                    _prove_released(supervisor, probe, str(state["leaseId"]), endpoint_path)
                    state["state"] = "externally-owned"
                    _write_state(session_root, state)
                finally:
                    if stop_cancellation is not None:
                        raise stop_cancellation
                return OperationResult.success(
                    _BEGIN_OPERATION, _ticket(state, firmware.elf_path)
                )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return _failure(_BEGIN_OPERATION, error)


async def end_debug_handoff(
    ticket: object,
    supervisor: object,
    client_factory: Callable[[object], object],
) -> OperationResult[HandoffRestore]:
    """Reacquire the exact originating probe and consume one active ticket."""

    try:
        if not isinstance(ticket, str) or _SHA256.fullmatch(ticket) is None:
            raise _fail("HANDOFF_TICKET_INVALID", "Debug handoff ticket is invalid")
        config, session_root = _safe_session_root(supervisor)
        configured_root = getattr(config, "project_root", None)
        if not isinstance(configured_root, Path):
            raise _fail("HANDOFF_SUPERVISOR_INVALID", "Probe supervisor configuration is invalid")
        try:
            root = configured_root.expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            raise _fail(
                "HANDOFF_SUPERVISOR_INVALID",
                "Probe supervisor configuration is invalid",
            ) from None
        probe, workspace, session = _configuration(config, root)
        lock = _async_lock(session_root)
        async with lock:
            with _process_guard(session_root / _GUARD_NAME):
                state = _read_state(session_root)
                if (
                    state is None
                    or state.get("state") not in ("externally-owned", "reacquiring")
                    or not secrets.compare_digest(str(state.get("ticketId", "")), ticket)
                    or not _state_matches(
                        state,
                        probe=probe,
                        workspace=workspace,
                        session=session,
                        target=str(state.get("target", "")),
                        build_id=str(state.get("buildId", "")),
                        elf_sha=str(state.get("elfSha256", "")),
                    )
                ):
                    raise _fail("HANDOFF_TICKET_INVALID", "Debug handoff ticket is invalid")
                if state["state"] == "externally-owned":
                    state["state"] = "reacquiring"
                    _write_state(session_root, state)
                firmware_before = _load_fresh_firmware(root)
                if not _state_matches(
                    state,
                    probe=probe,
                    workspace=workspace,
                    session=session,
                    target=str(firmware_before.model.debug.target),
                    build_id=str(firmware_before.identity.get("buildId", "")),
                    elf_sha=str(firmware_before.identity.get("elfSha256", "")),
                ):
                    raise _fail("HANDOFF_TICKET_INVALID", "Debug handoff ticket is invalid")
                flash_before = _load_flash_result(root)
                _validate_flash(
                    flash_before,
                    firmware_before,
                    probe=probe,
                    workspace=workspace,
                    session=session,
                    target=str(state["target"]),
                )
                try:
                    endpoint = await supervisor.start()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise _fail("HANDOFF_REACQUIRE_FAILED", "Probe Service could not be reacquired") from None
                _endpoint(endpoint, probe, workspace, session)
                try:
                    client = client_factory(endpoint)
                except Exception:
                    raise _fail("HANDOFF_REACQUIRE_FAILED", "Probe client could not be created") from None
                _validate_client_endpoint(client, endpoint)
                attachment = await client.attach(probe, str(state["target"]))
                _validate_attachment(attachment, probe, str(state["target"]))
                firmware = _load_fresh_firmware(root)
                if not _state_matches(
                    state,
                    probe=probe,
                    workspace=workspace,
                    session=session,
                    target=str(firmware.model.debug.target),
                    build_id=str(firmware.identity.get("buildId", "")),
                    elf_sha=str(firmware.identity.get("elfSha256", "")),
                ):
                    raise _fail("HANDOFF_IDENTITY_MISMATCH", "Firmware identity changed during debug handoff")
                flash_result = _load_flash_result(root)
                _validate_flash(
                    flash_result,
                    firmware,
                    probe=probe,
                    workspace=workspace,
                    session=session,
                    target=str(state["target"]),
                )
                await _verify_segments(client, firmware.segments)
                selection = tuple(str(item) for item in state["previousWatchSelection"])
                state["state"] = "observing"
                state["ticketId"] = None
                state["previousWatchSelection"] = []
                _write_state(session_root, state)
                return OperationResult.success(
                    _END_OPERATION, HandoffRestore(selection)
                )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return _failure(_END_OPERATION, error)


__all__ = [
    "CortexDebugAttachContract",
    "DebugHandoffRequest",
    "HandoffRestore",
    "HandoffTicket",
    "begin_debug_handoff",
    "end_debug_handoff",
]
