"""Fixed, owned process boundary for blocking Probe backend execution."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
import json
import multiprocessing
from multiprocessing.connection import Connection
import os
import threading
import time
from typing import Any

from .backend import (
    FlashBackendReport,
    ProbeAttachmentEvidence,
    ProbeBackendError,
    ProbeDescriptor,
)


_VERSION = "stm32-toolkit-probe-worker/1"
# 64 MiB is the frozen PyOCD flash-image bound; canonical base64 expansion plus
# the closed envelope remains below this fixed IPC ceiling.
_MAX_MESSAGE_BYTES = 96 * 1024 * 1024
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_GRACE_SECONDS = 1.0
_METHODS = {
    "preflight_target_capabilities", "list_probes", "open_attach", "read_memory",
    "read_core_registers", "halt", "resume", "step", "reset", "flash_elf", "close",
    "target_identity", "target_state", "set_temporary_breakpoint",
    "clear_temporary_breakpoint", "capture_fault", "capture_logs",
    "open_target_transport", "read_target_transport", "close_target_transport",
}
_BACKEND_ERROR_CODES = {
    "PROBE_ATTACH_FAILED", "PROBE_BACKEND_ERROR", "PROBE_BACKEND_UNAVAILABLE",
    "PROBE_BACKPRESSURE", "PROBE_CLOSE_FAILED", "PROBE_CONTROL_FAILED",
    "PROBE_DESCRIPTOR_INVALID", "PROBE_ENUMERATION_FAILED", "PROBE_IDENTITY_MISMATCH",
    "PROBE_LIMIT_EXCEEDED", "PROBE_NOT_ATTACHED", "PROBE_NOT_FOUND",
    "PROBE_OPERATION_LEVEL_DENIED", "PROBE_OPERATION_UNAVAILABLE", "PROBE_PARTIAL_READ",
    "PROBE_PROGRAM_FAILED", "PROBE_PROGRAM_INVALID", "PROBE_PROTOCOL_INVALID",
    "PROBE_READ_INVALID", "PROBE_READ_UNAVAILABLE", "PROBE_REGISTER_INVALID",
    "PROBE_REGISTER_UNAVAILABLE", "PROBE_SELECTION_AMBIGUOUS", "PROBE_SELECTION_REQUIRED",
    "PROBE_TARGET_AMBIGUOUS", "PROBE_TARGET_IDENTITY_UNAVAILABLE", "PROBE_TARGET_INVALID",
    "PROBE_TARGET_UNAVAILABLE", "PROBE_TIMEOUT",
}


class ProbeWorkerError(ProbeBackendError):
    """A closed failure emitted by the owned worker boundary."""


@dataclass(frozen=True, init=False)
class ProbeWorkerConfig:
    """Closed serializable production construction contract for one PyOCD child."""

    frequency_hz: int
    target_profile_json: str
    transport_provider: str

    def __init__(
        self,
        *,
        frequency_hz: int = 1_000_000,
        target_profile: Mapping[str, object] | None = None,
        transport_provider: str = "task8",
    ) -> None:
        profile_input: object = {} if target_profile is None else target_profile
        if (
            type(frequency_hz) is not int
            or not 100_000 <= frequency_hz <= 50_000_000
            or transport_provider != "task8"
            or not isinstance(profile_input, Mapping)
        ):
            raise TypeError("Probe worker configuration is invalid")
        try:
            profile_json = _canonical_bytes(dict(profile_input)).decode("utf-8")
            profile = json.loads(profile_json)
        except (ProbeWorkerError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise TypeError("Probe worker configuration is invalid") from error
        if not isinstance(profile, dict):
            raise TypeError("Probe worker configuration is invalid")
        object.__setattr__(self, "frequency_hz", frequency_hz)
        object.__setattr__(self, "target_profile_json", profile_json)
        object.__setattr__(self, "transport_provider", transport_provider)

    def target_profile(self) -> dict[str, object]:
        value = json.loads(self.target_profile_json)
        if not isinstance(value, dict):
            raise ProbeWorkerError("PROBE_PROTOCOL_INVALID", "Probe worker configuration is invalid")
        return value


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProbeWorkerError("PROBE_PROTOCOL_INVALID", "Probe worker message is invalid") from error


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError("worker object contains a duplicate member")
        value[key] = member
    return value


def _decode_message(raw: bytes) -> dict[str, object]:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_closed_object)
    if not isinstance(value, dict) or _canonical_bytes(value) != raw:
        raise ValueError("worker message is not canonical")
    return value


def _json_value(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("worker mapping keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    raise TypeError("worker result type is not supported")


def _from_json(value: object) -> object:
    if isinstance(value, dict):
        if set(value) == {"$bytes"}:
            encoded = value["$bytes"]
            if not isinstance(encoded, str):
                raise ValueError("worker bytes are invalid")
            raw = base64.b64decode(encoded, validate=True)
            if base64.b64encode(raw).decode("ascii") != encoded:
                raise ValueError("worker bytes are not canonical")
            return raw
        return {key: _from_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_json(item) for item in value]
    return value


def _send(connection: Connection, value: Mapping[str, object]) -> None:
    payload = _canonical_bytes(value)
    if len(payload) > _MAX_OUTPUT_BYTES:
        payload = _canonical_bytes({
            "version": _VERSION,
            "ok": False,
            "error": {"code": "PROBE_LIMIT_EXCEEDED", "message": "Probe worker output exceeds its limit"},
        })
    connection.send_bytes(payload)


def _worker_main(
    connection: Connection,
    config: ProbeWorkerConfig | None,
    backend_factory: Callable[[], object] | None,
) -> None:
    backend: object | None = None
    explicit_close_started = False
    try:
        if backend_factory is not None:
            # The callable is an explicit private test seam passed through Windows spawn;
            # production construction never accepts a module or import string.
            backend = backend_factory()
        elif type(config) is ProbeWorkerConfig:
            from .pyocd_backend import PyOCDBackend, admitted_target_transport_factory
            backend = PyOCDBackend(
                frequency_hz=config.frequency_hz,
                target_profile=config.target_profile(),
                target_transport_factory=admitted_target_transport_factory,
            )
        else:
            raise TypeError("Probe worker configuration is invalid")
        _send(connection, {"version": _VERSION, "ok": True, "pid": os.getpid()})
        while True:
            raw = connection.recv_bytes(_MAX_MESSAGE_BYTES)
            request = _decode_message(raw)
            if (
                not isinstance(request, dict)
                or set(request) != {"version", "id", "method", "args", "kwargs"}
                or request["version"] != _VERSION
                or type(request["id"]) is not int
                or request["method"] not in _METHODS
                or not isinstance(request["args"], list)
                or not isinstance(request["kwargs"], dict)
            ):
                raise ValueError("worker request is invalid")
            method = request["method"]
            args = [_from_json(item) for item in request["args"]]
            if method == "preflight_target_capabilities" and len(args) == 2:
                from .model import OperationLevel
                args[1] = OperationLevel(args[1])
            explicit_close_started = method == "close"
            result = getattr(backend, method)(
                *args,
                **{key: _from_json(item) for key, item in request["kwargs"].items()},
            )
            _send(connection, {
                "version": _VERSION, "ok": True, "id": request["id"],
                "result": _json_value(result),
            })
            if method == "close":
                return
    except EOFError:
        return
    except BaseException as error:
        code = error.code if isinstance(error, ProbeBackendError) else "PROBE_BACKEND_ERROR"
        if code not in _BACKEND_ERROR_CODES:
            code = "PROBE_BACKEND_ERROR"
        try:
            _send(connection, {
                "version": _VERSION, "ok": False,
                "error": {"code": code, "message": "Probe worker operation failed"},
            })
        except BaseException:
            pass
    finally:
        if backend is not None and not explicit_close_started:
            try:
                getattr(backend, "close")()
            except BaseException:
                pass
        connection.close()


class ProbeBackendWorker:
    """Synchronous ProbeBackend proxy owning exactly one spawned child process."""

    def __init__(
        self,
        *,
        config: ProbeWorkerConfig | None = None,
        _test_backend_factory: Callable[[], object] | None = None,
    ) -> None:
        if (config is None) == (_test_backend_factory is None):
            raise TypeError("Exactly one production config or private test backend is required")
        if config is not None and type(config) is not ProbeWorkerConfig:
            raise TypeError("Probe worker configuration is invalid")
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(
            target=_worker_main,
            args=(child, config, _test_backend_factory),
            name="stm32-toolkit-probe-backend",
            daemon=True,
        )
        process.start()
        child.close()
        self._connection = parent
        self._process = process
        self._call_lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        try:
            ready = self._receive(time.monotonic() + 10.0)
        except BaseException:
            self.abort_owned_execution()
            raise
        if set(ready) != {"version", "ok", "pid"} or ready != {
            "version": _VERSION, "ok": True, "pid": process.pid,
        }:
            self.abort_owned_execution()
            raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker failed to start")

    @property
    def owned_pid(self) -> int:
        pid = self._process.pid
        if pid is None:
            raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker has no process identity")
        return pid

    @property
    def is_alive(self) -> bool:
        return self._process.is_alive()

    def _receive(self, deadline: float) -> dict[str, object]:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._connection.poll(remaining):
            raise ProbeWorkerError("PROBE_TIMEOUT", "Probe worker operation timed out")
        try:
            raw = self._connection.recv_bytes(_MAX_OUTPUT_BYTES)
            value = _decode_message(raw)
        except (EOFError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid") from error
        if not isinstance(value, dict) or value.get("version") != _VERSION:
            raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
        return value

    def call(self, method: str, *args: object, timeout_seconds: float = 30.0, **kwargs: object) -> object:
        if method not in _METHODS or not 0 < timeout_seconds <= 301:
            raise ProbeWorkerError("PROBE_PROTOCOL_INVALID", "Probe worker request is invalid")
        with self._call_lock:
            if self._closed or not self._process.is_alive():
                raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker is unavailable")
            self._sequence += 1
            request_id = self._sequence
            payload = _canonical_bytes({
                "version": _VERSION, "id": request_id, "method": method,
                "args": _json_value(args), "kwargs": _json_value(kwargs),
            })
            if len(payload) > _MAX_MESSAGE_BYTES:
                raise ProbeWorkerError("PROBE_LIMIT_EXCEEDED", "Probe worker request exceeds its limit")
            try:
                self._connection.send_bytes(payload)
                response = self._receive(time.monotonic() + timeout_seconds)
            except ProbeWorkerError:
                self.abort_owned_execution()
                raise
            if response.get("ok") is False:
                failure = response.get("error")
                if (
                    not isinstance(failure, dict)
                    or set(failure) != {"code", "message"}
                    or failure.get("code") not in _BACKEND_ERROR_CODES
                    or not isinstance(failure.get("message"), str)
                ):
                    self.abort_owned_execution()
                    raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
                code, message = failure["code"], failure["message"]
                self.abort_owned_execution()
                raise ProbeWorkerError(code, message)
            if set(response) != {"version", "ok", "id", "result"} or response["id"] != request_id:
                self.abort_owned_execution()
                raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
            return _from_json(response["result"])

    def abort_owned_execution(self) -> None:
        """Terminate only the exact child owned by this proxy and bound the join."""
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process.is_alive():
            process.terminate()
            process.join(_GRACE_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(_GRACE_SECONDS)
        self._connection.close()
        if process.is_alive():
            raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker could not be terminated")

    def preflight_target_capabilities(self, probe_id: str, operation_level: object) -> None:
        self.call("preflight_target_capabilities", probe_id, operation_level.value)

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        result = self.call("list_probes")
        return tuple(ProbeDescriptor(**item) for item in result)

    def open_attach(self, probe_id: str, target: str, *, halt_on_connect: bool = False) -> ProbeAttachmentEvidence:
        return ProbeAttachmentEvidence(**self.call("open_attach", probe_id, target, halt_on_connect=halt_on_connect))

    def read_memory(self, address: int, length: int) -> bytes:
        return self.call("read_memory", address, length)

    def read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]:
        return self.call("read_core_registers", names)

    def halt(self) -> None: self.call("halt")
    def resume(self) -> None: self.call("resume")
    def step(self) -> None: self.call("step", timeout_seconds=5.0)
    def reset(self) -> None: self.call("reset")
    def flash_elf(self, image: bytes) -> FlashBackendReport:
        return FlashBackendReport(**self.call("flash_elf", image, timeout_seconds=300.0))
    def target_identity(self) -> Mapping[str, object]: return self.call("target_identity")
    def target_state(self) -> Mapping[str, object]: return self.call("target_state")
    def set_temporary_breakpoint(self, address: int, size: int) -> Mapping[str, object]: return self.call("set_temporary_breakpoint", address, size)
    def clear_temporary_breakpoint(self, breakpoint_id: str) -> Mapping[str, object]: return self.call("clear_temporary_breakpoint", breakpoint_id)
    def capture_fault(self, max_stack_bytes: int) -> Mapping[str, object]: return self.call("capture_fault", max_stack_bytes)
    def capture_logs(self, channel: str, max_bytes: int, duration_ms: int) -> Mapping[str, object]: return self.call("capture_logs", channel, max_bytes, duration_ms, timeout_seconds=(duration_ms / 1000) + 1)
    def open_target_transport(self, transport: str, config: Mapping[str, object], deadline_ms: int) -> Mapping[str, object]: return self.call("open_target_transport", transport, config, deadline_ms, timeout_seconds=(deadline_ms / 1000) + 1)
    def read_target_transport(self, transport_id: str, max_bytes: int, deadline_ms: int) -> Mapping[str, object]: return self.call("read_target_transport", transport_id, max_bytes, deadline_ms, timeout_seconds=(deadline_ms / 1000) + 1)
    def close_target_transport(self, transport_id: str) -> Mapping[str, object]: return self.call("close_target_transport", transport_id)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.call("close", timeout_seconds=5.0)
        finally:
            self.abort_owned_execution()


__all__ = ["ProbeBackendWorker", "ProbeWorkerConfig", "ProbeWorkerError"]
