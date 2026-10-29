"""Fixed, owned process boundary for blocking Probe backend execution."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
import json
import math
import multiprocessing
from multiprocessing.connection import Connection
import os
import threading
import time
from typing import Any

from .backend import (
    DebugHandoffMetadata,
    FlashBackendReport,
    extract_program_diagnostic,
    ProbeAttachmentEvidence,
    ProbeBackendError,
    ProbeDescriptor,
)
from .attach_diagnostics import (
    LEGACY_ATTACH_STAGES,
    append_cleanup,
    legacy_stage_matches_attach_diagnostic,
    make_cleanup_entry,
    promote_legacy_details,
    SOURCE_CODES,
    validate_attach_diagnostic,
)
from .attach_progress import (
    HALT_STAGE,
    PROGRESS_CLOCK,
    PROGRESS_STAGES,
    PROGRESS_VERSION,
    RESUME_STAGES,
    validate_attach_progress,
)


_VERSION = "stm32-toolkit-probe-worker/1"
NORMAL_CONNECTION_POLICY = "normal"
UNDER_RESET_RECOVERY_CONNECTION_POLICY = "under-reset-recovery"
OBSERVE_PRESERVE_CONNECTION_POLICY = "observe-preserve"
# 64 MiB is the frozen PyOCD flash-image bound; canonical base64 expansion plus
# the closed envelope remains below this fixed IPC ceiling.
_MAX_MESSAGE_BYTES = 96 * 1024 * 1024
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_GRACE_SECONDS = 1.0
_METHODS = {
    "preflight_target_capabilities", "list_probes", "open_attach", "read_memory",
    "read_core_registers", "halt", "resume", "step", "reset", "flash_elf",
    "flash_imported_elf", "close",
    "target_identity", "target_state", "target_observation_policy", "target_read_memory",
    "target_read_core_registers", "set_temporary_breakpoint",
    "clear_temporary_breakpoint", "capture_fault", "capture_logs",
    "open_target_transport", "read_target_transport", "close_target_transport",
    "debug_handoff_metadata",
}
_BACKEND_ERROR_CODES = frozenset(SOURCE_CODES - {"UNTYPED", "CALLER_CANCELLED"})
_REGISTER_ERROR_STATES = frozenset({
    "halted", "running", "reset", "sleeping", "lockedup", "programming", "unknown",
})
_ATTACH_ERROR_STAGES = LEGACY_ATTACH_STAGES


class ProbeWorkerError(ProbeBackendError):
    """A closed failure emitted by the owned worker boundary."""


@dataclass(frozen=True, init=False)
class ProbeWorkerConfig:
    """Closed serializable production construction contract for one PyOCD child."""

    frequency_hz: int
    target_profile_json: str
    transport_provider: str
    connection_policy: str

    def __init__(
        self,
        *,
        frequency_hz: int = 1_000_000,
        target_profile: Mapping[str, object] | None = None,
        transport_provider: str = "task8",
        connection_policy: str = NORMAL_CONNECTION_POLICY,
    ) -> None:
        profile_input: object = {} if target_profile is None else target_profile
        if (
            type(frequency_hz) is not int
            or not 100_000 <= frequency_hz <= 50_000_000
            or transport_provider != "task8"
            or not isinstance(profile_input, Mapping)
            or type(connection_policy) is not str
            or connection_policy
            not in {NORMAL_CONNECTION_POLICY, UNDER_RESET_RECOVERY_CONNECTION_POLICY,
                    OBSERVE_PRESERVE_CONNECTION_POLICY}
            or (
                connection_policy in {UNDER_RESET_RECOVERY_CONNECTION_POLICY,
                                      OBSERVE_PRESERVE_CONNECTION_POLICY}
                and frequency_hz != 100_000
            )
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
        object.__setattr__(self, "connection_policy", connection_policy)

    def target_profile(self) -> dict[str, object]:
        value = json.loads(self.target_profile_json)
        if not isinstance(value, dict):
            raise ProbeWorkerError("PROBE_PROTOCOL_INVALID", "Probe worker configuration is invalid")
        return value

    def for_observation(self, *, preserve_target_state: bool = False) -> "ProbeWorkerConfig":
        if type(preserve_target_state) is not bool:
            raise TypeError("Probe worker observation policy is invalid")
        return ProbeWorkerConfig(
            frequency_hz=100_000,
            target_profile=self.target_profile(),
            transport_provider=self.transport_provider,
            connection_policy=(OBSERVE_PRESERVE_CONNECTION_POLICY if preserve_target_state
                               else NORMAL_CONNECTION_POLICY),
        )

    def for_under_reset_recovery(self) -> "ProbeWorkerConfig":
        return ProbeWorkerConfig(
            frequency_hz=100_000,
            target_profile=self.target_profile(),
            transport_provider=self.transport_provider,
            connection_policy=UNDER_RESET_RECOVERY_CONNECTION_POLICY,
        )


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


def _safe_register_error_details(code: object, details: object) -> dict[str, str] | None:
    if code != "PROBE_REGISTER_UNAVAILABLE" or type(details) is not dict:
        return None
    if set(details) != {"state"} or type(details["state"]) is not str:
        return None
    state = details["state"]
    if state not in _REGISTER_ERROR_STATES:
        return None
    return {"state": state}


def _safe_program_error_details(
    code: object, details: object
) -> dict[str, object] | None:
    if code != "PROBE_PROGRAM_FAILED" or type(details) is not dict:
        return None
    if set(details) != {"programDiagnostic"}:
        return None
    diagnostic = extract_program_diagnostic(details)
    return None if diagnostic is None else {"programDiagnostic": diagnostic}


def _safe_attach_error_details(code: object, details: object) -> dict[str, object] | None:
    if type(details) is not dict:
        return None
    if set(details) not in (
        {"stage"},
        {"attachDiagnostic"},
        {"stage", "attachDiagnostic"},
    ):
        return None
    result: dict[str, object] = {}
    if "stage" in details:
        stage = details["stage"]
        if (
            code != "PROBE_ATTACH_FAILED"
            or type(stage) is not str
            or stage not in _ATTACH_ERROR_STAGES
        ):
            return None
        result["stage"] = stage
    if "attachDiagnostic" in details:
        diagnostic = validate_attach_diagnostic(details["attachDiagnostic"], worker=True)
        if diagnostic is None:
            return None
        if type(code) is not str or code not in _BACKEND_ERROR_CODES:
            return None
        result["attachDiagnostic"] = diagnostic
    if (
        "stage" in result
        and "attachDiagnostic" in result
        and not legacy_stage_matches_attach_diagnostic(
            result["stage"], result["attachDiagnostic"], worker=True
        )
    ):
        return None
    return result


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
    method: str | None = None
    stage_request: dict[str, int | None] = {"id": None}

    def attach_stage_callback(stage: object) -> None:
        identifier = stage_request["id"]
        if identifier is None:
            return
        try:
            _send(connection, {
                "version": _VERSION, "progress": stage, "id": identifier,
            })
        except BaseException:
            # A stage frame is diagnostic-only; its transport failure must not
            # alter or replace the backend's own attach behavior or error.
            pass

    try:
        if backend_factory is not None:
            # The callable is an explicit private test seam passed through Windows spawn;
            # production construction never accepts a module or import string.
            backend = backend_factory()
            register_stage_callback = getattr(
                backend, "_set_attach_stage_callback", None
            )
            if callable(register_stage_callback):
                try:
                    register_stage_callback(attach_stage_callback)
                except BaseException:
                    pass
        elif type(config) is ProbeWorkerConfig:
            from .pyocd_backend import PyOCDBackend, admitted_target_transport_factory
            backend = PyOCDBackend(
                frequency_hz=config.frequency_hz,
                target_profile=config.target_profile(),
                target_transport_factory=admitted_target_transport_factory,
                connection_policy=config.connection_policy,
                stage_callback=attach_stage_callback,
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
            if (
                method in {"read_core_registers", "target_read_core_registers"}
                and len(args) == 1
                and isinstance(args[0], list)
            ):
                args[0] = tuple(args[0])
            explicit_close_started = method == "close"
            if method == "open_attach":
                stage_request["id"] = request["id"]
            try:
                result = getattr(backend, method)(
                    *args,
                    **{key: _from_json(item) for key, item in request["kwargs"].items()},
                )
            finally:
                if method == "open_attach":
                    stage_request["id"] = None
            if method == "debug_handoff_metadata":
                result = DebugHandoffMetadata.from_value(result).to_dict()
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
        if type(code) is not str or code not in _BACKEND_ERROR_CODES:
            code = "PROBE_BACKEND_ERROR"
        try:
            error_payload: dict[str, object] = {
                "code": code, "message": "Probe worker operation failed",
            }
            safe_details = (
                _safe_attach_error_details(code, getattr(error, "details", None))
                if method == "open_attach"
                else _safe_program_error_details(code, getattr(error, "details", None))
                if method in {"flash_elf", "flash_imported_elf"}
                else _safe_register_error_details(code, getattr(error, "details", None))
            )
            if safe_details is not None:
                error_payload["details"] = safe_details
            _send(connection, {
                "version": _VERSION, "ok": False,
                "error": error_payload,
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
        try:
            if os.name == "nt":
                from .worker_windows import WorkerWindowsSpawnProcess

                process = WorkerWindowsSpawnProcess(
                    target=_worker_main,
                    args=(child, config, _test_backend_factory),
                    name="stm32-toolkit-probe-backend",
                    daemon=True,
                )
            else:
                process = context.Process(
                    target=_worker_main,
                    args=(child, config, _test_backend_factory),
                    name="stm32-toolkit-probe-backend",
                    daemon=True,
                )
            process.start()
        except BaseException:
            for endpoint in (child, parent):
                try:
                    endpoint.close()
                except BaseException:
                    pass
            raise
        child.close()
        self._connection = parent
        self._process = process
        self._call_lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        # Small local-only metadata snapshot for the current attach attempt.
        # It is never shared with the child and never holds the call lock.
        self._attach_progress_lock = threading.Lock()
        self._attach_progress_token: str | None = None
        self._attach_progress_origin: float | None = None
        self._attach_progress_events: list[tuple[str, int]] = []
        self._attach_progress_last_index = -1
        self._attach_progress_frozen_ms: int | None = None
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

    @property
    def is_terminal(self) -> bool:
        """Whether this proxy can no longer service an owned backend call."""
        return self._closed or not self._process.is_alive()

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

    def _reset_attach_progress(self, token: str | None) -> None:
        with self._attach_progress_lock:
            self._attach_progress_token = token
            self._attach_progress_origin = None
            self._attach_progress_events = []
            self._attach_progress_last_index = -1
            self._attach_progress_frozen_ms = None

    def _mark_attach_dispatch(self) -> None:
        """Record the parent-created origin only after a successful send."""

        with self._attach_progress_lock:
            self._attach_progress_origin = time.monotonic()
            self._attach_progress_events = [("worker-dispatch", 0)]
            self._attach_progress_last_index = 0
            self._attach_progress_frozen_ms = None

    def _freeze_attach_progress(self) -> None:
        with self._attach_progress_lock:
            origin = self._attach_progress_origin
            if origin is not None and self._attach_progress_frozen_ms is None:
                self._attach_progress_frozen_ms = max(
                    0, int((time.monotonic() - origin) * 1000)
                )

    def _record_attach_progress_frame(
        self, frame: dict[str, object], request_id: int
    ) -> None:
        """Admit one ordered child stage frame or fail the worker protocol closed."""

        if (
            set(frame) != {"version", "progress", "id"}
            or type(frame.get("id")) is not int
            or frame["id"] != request_id
            or type(frame.get("progress")) is not str
            or frame["progress"] not in PROGRESS_STAGES
        ):
            raise ProbeWorkerError(
                "PROBE_BACKEND_ERROR", "Probe worker response is invalid"
            )
        stage = frame["progress"]
        assert type(stage) is str
        index = PROGRESS_STAGES.index(stage)
        with self._attach_progress_lock:
            if self._attach_progress_frozen_ms is not None:
                return
            origin = self._attach_progress_origin
            if origin is None or index <= self._attach_progress_last_index:
                raise ProbeWorkerError(
                    "PROBE_BACKEND_ERROR", "Probe worker response is invalid"
                )
            stages = {item[0] for item in self._attach_progress_events}
            if (
                (stage == HALT_STAGE and RESUME_STAGES[0] in stages)
                or (stage == RESUME_STAGES[0] and HALT_STAGE in stages)
                or (stage == RESUME_STAGES[1] and RESUME_STAGES[0] not in stages)
            ):
                raise ProbeWorkerError(
                    "PROBE_BACKEND_ERROR", "Probe worker response is invalid"
                )
            elapsed_ms = max(0, int((time.monotonic() - origin) * 1000))
            self._attach_progress_events.append((stage, elapsed_ms))
            self._attach_progress_last_index = index

    def _receive_attach_response(
        self, deadline: float, request_id: int
    ) -> dict[str, object]:
        """Receive stage frames and the terminal result under one absolute deadline."""

        while True:
            value = self._receive(deadline)
            if "progress" not in value:
                return value
            self._record_attach_progress_frame(value, request_id)

    def attach_progress_snapshot(self, request_token: str) -> dict[str, object] | None:
        """Return the detached local snapshot for exactly this private token.

        This never acquires the blocking call lock and never performs IPC or
        hardware access, so it remains usable after an owned abort.
        """

        if type(request_token) is not str or not 1 <= len(request_token) <= 128:
            return None
        with self._attach_progress_lock:
            if (
                self._attach_progress_token != request_token
                or self._attach_progress_origin is None
            ):
                return None
            elapsed_ms = self._attach_progress_frozen_ms
            if elapsed_ms is None:
                elapsed_ms = max(
                    0,
                    int((time.monotonic() - self._attach_progress_origin) * 1000),
                )
            events = tuple(self._attach_progress_events)
        value = {
            "version": PROGRESS_VERSION,
            "clock": PROGRESS_CLOCK,
            "elapsedMs": elapsed_ms,
            "events": [
                {"stage": stage, "elapsedMs": milliseconds}
                for stage, milliseconds in events
            ],
        }
        return validate_attach_progress(value)

    def call(
        self,
        method: str,
        *args: object,
        timeout_seconds: float = 30.0,
        deadline: float | None = None,
        _progress_token: str | None = None,
        **kwargs: object,
    ) -> object:
        if (
            method not in _METHODS
            or not 0 < timeout_seconds <= 301
            or (deadline is not None and (type(deadline) is not float or not math.isfinite(deadline)))
            or (
                _progress_token is not None
                and (
                    method != "open_attach"
                    or type(_progress_token) is not str
                    or not 1 <= len(_progress_token) <= 128
                )
            )
        ):
            raise ProbeWorkerError("PROBE_PROTOCOL_INVALID", "Probe worker request is invalid")
        if deadline is None:
            self._call_lock.acquire()
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeWorkerError("PROBE_TIMEOUT", "Probe worker operation timed out")
            if not self._call_lock.acquire(timeout=remaining):
                raise ProbeWorkerError("PROBE_TIMEOUT", "Probe worker operation timed out")
        dispatched = False
        try:
            if self._closed or not self._process.is_alive():
                raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker is unavailable")
            request_deadline = (
                deadline if deadline is not None else time.monotonic() + timeout_seconds
            )
            if request_deadline <= time.monotonic():
                raise ProbeWorkerError("PROBE_TIMEOUT", "Probe worker operation timed out")
            self._sequence += 1
            request_id = self._sequence
            if method == "open_attach":
                self._reset_attach_progress(_progress_token)
            payload = _canonical_bytes({
                "version": _VERSION, "id": request_id, "method": method,
                "args": _json_value(args), "kwargs": _json_value(kwargs),
            })
            if len(payload) > _MAX_MESSAGE_BYTES:
                raise ProbeWorkerError("PROBE_LIMIT_EXCEEDED", "Probe worker request exceeds its limit")
            try:
                self._connection.send_bytes(payload)
                dispatched = True
                if method == "open_attach":
                    self._mark_attach_dispatch()
                    response = self._receive_attach_response(
                        request_deadline, request_id
                    )
                    self._freeze_attach_progress()
                else:
                    response = self._receive(request_deadline)
            except ProbeWorkerError:
                if dispatched:
                    self.abort_owned_execution()
                raise
            if response.get("ok") is False:
                failure = response.get("error")
                if (
                    not isinstance(failure, dict)
                    or set(failure) not in ({"code", "message"}, {"code", "message", "details"})
                    or type(failure.get("code")) is not str
                    or failure.get("code") not in _BACKEND_ERROR_CODES
                    or not isinstance(failure.get("message"), str)
                ):
                    self.abort_owned_execution()
                    raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
                code, message = failure["code"], failure["message"]
                details: dict[str, object] = {}
                if set(failure) == {"code", "message", "details"}:
                    safe_details = (
                        _safe_attach_error_details(code, failure["details"])
                        if method == "open_attach"
                        else _safe_program_error_details(code, failure["details"])
                        if method in {"flash_elf", "flash_imported_elf"}
                        else _safe_register_error_details(code, failure["details"])
                    )
                    if safe_details is None:
                        self.abort_owned_execution()
                        raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
                    details = dict(safe_details)
                if method == "open_attach" and details.get("attachDiagnostic") is None:
                    promoted = promote_legacy_details(details)
                    if promoted is not None:
                        details = {**details, "attachDiagnostic": promoted}
                diagnostic = details.get("attachDiagnostic")
                try:
                    self.abort_owned_execution()
                except BaseException as abort_error:
                    if diagnostic is None:
                        raise
                    abort_code = (
                        abort_error.code
                        if isinstance(abort_error, ProbeBackendError)
                        and type(abort_error.code) is str
                        and abort_error.code in _BACKEND_ERROR_CODES
                        else "PROBE_BACKEND_ERROR"
                    )
                    abort_details = append_cleanup(
                        diagnostic,
                        (
                            make_cleanup_entry(
                                "worker-parent-abort",
                                "failed",
                                reason="backend-code",
                                source_code=abort_code,
                            ),
                        ),
                    ) or diagnostic
                    merged = dict(details)
                    merged["attachDiagnostic"] = abort_details
                    raise ProbeWorkerError(
                        "PROBE_BACKEND_ERROR",
                        "Probe worker could not be terminated",
                        merged,
                    ) from None
                if diagnostic is not None:
                    details = dict(details)
                    details["attachDiagnostic"] = append_cleanup(
                        diagnostic,
                        (make_cleanup_entry("worker-parent-abort", "succeeded"),),
                    ) or diagnostic
                raise ProbeWorkerError(code, message, details)
            if set(response) != {"version", "ok", "id", "result"} or response["id"] != request_id:
                self.abort_owned_execution()
                raise ProbeWorkerError("PROBE_BACKEND_ERROR", "Probe worker response is invalid")
            return _from_json(response["result"])
        finally:
            self._call_lock.release()

    def abort_owned_execution(self) -> None:
        """Terminate only the exact child owned by this proxy and bound the join."""
        self._freeze_attach_progress()
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

    def open_attach_with_progress(
        self,
        probe_id: str,
        target: str,
        *,
        halt_on_connect: bool = False,
        request_token: str,
    ) -> ProbeAttachmentEvidence:
        """Attach while retaining a snapshot scoped to one private service token."""

        if type(request_token) is not str or not 1 <= len(request_token) <= 128:
            raise ProbeWorkerError(
                "PROBE_PROTOCOL_INVALID", "Probe worker request is invalid"
            )
        return ProbeAttachmentEvidence(**self.call(
            "open_attach",
            probe_id,
            target,
            halt_on_connect=halt_on_connect,
            _progress_token=request_token,
        ))

    def debug_handoff_metadata(self, *, deadline: float | None = None) -> DebugHandoffMetadata:
        try:
            if deadline is None:
                deadline = time.monotonic() + 5.0
            return DebugHandoffMetadata.from_value(
                self.call("debug_handoff_metadata", deadline=deadline)
            )
        except (TypeError, ValueError) as error:
            self.abort_owned_execution()
            raise ProbeWorkerError(
                "PROBE_BACKEND_ERROR", "Probe worker response is invalid"
            ) from error

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
    def flash_imported_elf(self, image: bytes) -> FlashBackendReport:
        return FlashBackendReport(**self.call("flash_imported_elf", image, timeout_seconds=300.0))
    def target_identity(self) -> Mapping[str, object]: return self.call("target_identity")
    def target_state(self) -> Mapping[str, object]: return self.call("target_state")
    def target_observation_policy(self) -> Mapping[str, object]: return self.call("target_observation_policy")
    def target_read_memory(self, address: int, length: int) -> bytes: return self.call("target_read_memory", address, length)
    def target_read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]: return self.call("target_read_core_registers", names)
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
