"""SESSION-TRACE: one-shot constructor diagnostic with an explicit child grant.

Run-specific, non-packaged helper.  It is evidence preparation only: the
default invocation refuses, and a prepared ``run`` performs a real USB
metadata exchange through the Toolkit's default PyOCD driver, so executing it
against hardware needs a separate, explicit authorization that this file does
not grant.

Protocol
--------
The parent creates one run directory exclusively and writes a small closed
``request.json``.  It then starts exactly one direct child process with the
same interpreter, ``-B`` and this same saved source file (``child <dir>``).
The child reserves its output with an exclusive ``claim.json`` before any
backend work, starts a real 127.0.0.1-only health endpoint, takes the existing
exact-probe OBSERVE lease through ``ProbeLeaseManager`` in the explicit shared
data root, and publishes ``ready.json`` bound to its actual PID, source digest,
request digest and lease.  It performs no enumeration or USB access before a
matching parent ``go.json``.  After that grant it performs exactly one lazy
default-driver acquisition, one exact-selector enumeration/selection and one
Session construction with the accepted options, then closes that Session once
through its existing close path.

The parent only writes ``go.json`` once its own child handle exists and the
READY identity matches exactly before the single absolute deadline.  A failed
or unknown startup, a bad READY, an identity mismatch or a cancellation never
grants.  A child that survives its one cooperative termination request is
reported as UNKNOWN and keeps its own live lease; the parent never releases a
lease it does not own.

Fixed run-owned files: ``request.json``, ``claim.json``, ``ready.json``,
``go.json``, ``result.json``, ``events.json``, ``terminate.request``,
``native-traceback.txt``, ``child-stderr.txt`` and ``attempt.json``.  Every
run file is created exclusively (one shot); every JSON record except the
one-shot terminate request has a closed key set.  No command, import or code
string is ever taken from these files.  The private native traceback contains
only file/function/line frames and is never a public field of the result.

Physical target state is always UNKNOWN.  A returned constructor is narrow
evidence about this helper's own operations, not proof of attachment,
programming, clock rate, application execution or a repaired physical fault.

Private test seam: the child understands a small closed set of
``SESSION_TRACE_PRIVATE_*`` environment variables (fixed fake mode, bounded
seconds, fake probe id, unique release path, receipt path) used only by the
offline tests to select an inert fixed backend.  They are never CLI arguments
and can never name a module, interpreter, command or import; an unknown mode
fails closed before any construction.
"""

from __future__ import annotations

import faulthandler
import hashlib
import http.server
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
WORKSPACE_ID = "session-trace"
DEFAULT_DEADLINE_SECONDS = 20.0
MAX_DEADLINE_SECONDS = 30.0
MIN_DEADLINE_SECONDS = 0.5
OWNED_TERMINATION_JOIN_SECONDS = 2.0
FAULTHANDLER_DELAY_SECONDS = 1.0
POLL_SECONDS = 0.02
MAX_RUN_FILE_BYTES = 8192
MAX_EVENTS = 32
MAX_SOURCE_BYTES = 4 * 1024 * 1024

REQUEST_FILE = "request.json"
CLAIM_FILE = "claim.json"
READY_FILE = "ready.json"
GO_FILE = "go.json"
RESULT_FILE = "result.json"
EVENTS_FILE = "events.json"
TERMINATE_FILE = "terminate.request"
TRACEBACK_FILE = "native-traceback.txt"
STDERR_FILE = "child-stderr.txt"
ATTEMPT_FILE = "attempt.json"

RUN_FILE_NAMES = frozenset(
    {
        REQUEST_FILE,
        CLAIM_FILE,
        READY_FILE,
        GO_FILE,
        RESULT_FILE,
        EVENTS_FILE,
        TERMINATE_FILE,
        TRACEBACK_FILE,
        STDERR_FILE,
        ATTEMPT_FILE,
    }
)

_PRIVATE_ENV = "SESSION_TRACE_PRIVATE_"
FAKE_MODE_ENV = _PRIVATE_ENV + "FAKE_MODE"
FAKE_SECONDS_ENV = _PRIVATE_ENV + "FAKE_SECONDS"
FAKE_PROBE_ENV = _PRIVATE_ENV + "FAKE_PROBE"
FAKE_RELEASE_ENV = _PRIVATE_ENV + "FAKE_RELEASE"
FAKE_RECEIPT_ENV = _PRIVATE_ENV + "FAKE_RECEIPT"

_PORTABLE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

_EXIT_REFUSED = 2
_EXIT_UNKNOWN = 3
_EXIT_TIMEOUT = 4
_EXIT_CANCELLED = 5
_EXIT_CHILD_FAILED = 6
_EXIT_LIFECYCLE = 7

FAKE_MODES = frozenset(
    {
        "construct-ok",
        "construct-block-exit",
        "construct-block-stubborn",
        "construct-error",
        "close-error",
        "no-ready",
        "bad-ready",
    }
)

RESULT_OUTCOMES = frozenset(
    {
        "ok",
        "busy",
        "lease-error",
        "ready-write-failed",
        "startup-aborted",
        "go-timeout",
        "cancelled-before-go",
        "go-identity-mismatch",
        "driver-error",
        "selection-error",
        "construct-error",
        "cancelled-after-go",
        "internal-error",
    }
)

CHILD_ERROR_KEYS = (
    "lease",
    "ready",
    "go",
    "construction",
    "sessionClose",
    "tracebackArm",
    "tracebackCancel",
    "tracebackClose",
    "leaseRelease",
    "health",
    "events",
    "result",
    "internal",
)

EVENT_STAGES = frozenset(
    {
        "claim-reserved",
        "lease-acquired",
        "ready-published",
        "go-accepted",
        "cancelled",
        "driver-acquired",
        "probe-enumerated",
        "probe-selected",
        "faulthandler-armed",
        "faulthandler-arm-failed",
        "session-constructed",
        "session-construct-failed",
        "session-closed",
        "session-close-failed",
        "traceback-cancelled",
        "traceback-cancel-failed",
        "lease-released",
        "lease-release-failed",
    }
)

CLAIM_KEYS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "requestDigest",
        "pid",
        "sourceDigest",
        "interpreter",
        "claimedAtUnix",
    }
)
READY_KEYS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "requestDigest",
        "pid",
        "sourceDigest",
        "interpreter",
        "leaseId",
        "readyAtUnix",
    }
)
GO_KEYS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "requestDigest",
        "pid",
        "sourceDigest",
        "interpreter",
        "leaseId",
        "issuedAtUnix",
    }
)
RESULT_KEYS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "requestDigest",
        "pid",
        "sourceDigest",
        "interpreter",
        "leaseId",
        "outcome",
        "ok",
        "physicalTargetState",
        "facts",
        "sessionOptions",
        "traceback",
        "errors",
    }
)
FACTS_KEYS = frozenset(
    {
        "driverAcquired",
        "enumerations",
        "selections",
        "sessionConstructed",
        "sessionOpened",
        "sessionClosed",
        "forbiddenCalls",
        "probeFingerprint",
    }
)
TRACEBACK_KEYS = frozenset({"armed", "bytes", "cancelled"})
REQUEST_KEYS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "sessionId",
        "workspaceId",
        "probeSelector",
        "target",
        "projectDir",
        "dataRoot",
        "deadlineUnix",
        "faulthandlerDelaySeconds",
        "requestDigest",
    }
)
EVENTS_KEYS = frozenset(
    {"schemaVersion", "attemptId", "requestDigest", "pid", "events"}
)


class SessionTraceError(Exception):
    """A closed diagnostic failure with a stable code and safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AttemptConfig:
    output_dir: Path
    data_root: Path
    probe_selector: str
    target: str
    project_dir: Path
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS


@dataclass(frozen=True)
class AttemptOutcome:
    attempt_id: str
    outcome: str
    ok: bool
    exit_code: int
    report: Mapping[str, object]


def _safe_code(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(value))[:80]
    return text if _SAFE_CODE.fullmatch(text) else "UNKNOWN"


def _normalized_path(value: object) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        total = 0
        while True:
            chunk = handle.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                raise SessionTraceError("SOURCE_TOO_LARGE", "Helper source is too large")
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest_mapping(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    data = _canonical_bytes(payload)
    if len(data) > MAX_RUN_FILE_BYTES:
        raise SessionTraceError("RUN_FILE_TOO_LARGE", "Run record exceeds its bound")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        written = 0
        while written < len(data):
            written += os.write(descriptor, data[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json_once(path: Path) -> tuple[str, object]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_RUN_FILE_BYTES + 1)
    except FileNotFoundError:
        return "missing", None
    except PermissionError:
        # A single exclusive writer may still hold the file open; retry.
        return "incomplete", None
    except OSError:
        return "unreadable", None
    if len(raw) > MAX_RUN_FILE_BYTES:
        return "oversized", None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # A single exclusive write can still be observed mid-write.
        return "incomplete", None
    if not isinstance(payload, dict):
        return "invalid", None
    return "ok", payload


def _read_json_until(
    path: Path, deadline: float, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, object]:
    while True:
        status, payload = _read_json_once(path)
        if status == "ok":
            return payload  # type: ignore[return-value]
        if status not in ("missing", "incomplete"):
            raise SessionTraceError("RUN_FILE_INVALID", "Run record is invalid")
        if time.time() >= deadline:
            raise SessionTraceError("RUN_FILE_TIMEOUT", "Run record is unavailable")
        sleep(POLL_SECONDS)


def _peek_json(path: Path) -> tuple[str, object]:
    return _read_json_once(path)


def _require_exact_keys(
    payload: Mapping[str, object], keys: frozenset[str], name: str
) -> None:
    if set(payload) != keys:
        raise SessionTraceError("RUN_FILE_SCHEMA", f"{name} record has the wrong shape")


def _require_identifier(value: object, field_name: str, code: str) -> str:
    if not isinstance(value, str) or _PORTABLE_IDENTIFIER.fullmatch(value) is None:
        raise SessionTraceError(code, f"{field_name} is not a portable identifier")
    return value


def _require_number(value: object, field_name: str, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SessionTraceError(code, f"{field_name} is not a number")
    return float(value)


def _require_schema(payload: Mapping[str, object], code: str) -> None:
    if type(payload.get("schemaVersion")) is not int:
        raise SessionTraceError(code, "Run record schema is invalid")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise SessionTraceError(code, "Run record schema is unsupported")


def _event(
    events: list[dict[str, object]], stage: str, started: float
) -> None:
    if stage not in EVENT_STAGES or len(events) >= MAX_EVENTS:
        return
    elapsed = max(0, int((time.monotonic() - started) * 1000))
    events.append({"stage": stage, "elapsedMs": elapsed})


def _new_facts() -> dict[str, object]:
    return {
        "driverAcquired": 0,
        "enumerations": 0,
        "selections": 0,
        "sessionConstructed": False,
        "sessionOpened": False,
        "sessionClosed": 0,
        "forbiddenCalls": [],
        "probeFingerprint": None,
    }


def _session_options(request: Mapping[str, object]) -> dict[str, object]:
    return {
        "auto_unlock": False,
        "connect_mode": "halt",
        "dap_protocol": "swd",
        "frequency": 100_000,
        "no_config": True,
        "pack.debug_sequences.enable": True,
        "primary_core": 0,
        "project_dir": request["projectDir"],
        "resume_on_disconnect": False,
        "target_override": request["target"],
        "user_script": os.devnull,
    }


def _build_request(
    config: AttemptConfig,
    *,
    attempt_id: str,
    session_id: str,
    deadline_wall: float,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "sessionId": session_id,
        "workspaceId": WORKSPACE_ID,
        "probeSelector": config.probe_selector,
        "target": config.target,
        "projectDir": str(config.project_dir),
        "dataRoot": str(config.data_root),
        "deadlineUnix": float(deadline_wall),
        "faulthandlerDelaySeconds": FAULTHANDLER_DELAY_SECONDS,
    }
    body["requestDigest"] = _digest_mapping(body)
    return body


def _validate_request(payload: Mapping[str, object]) -> dict[str, object]:
    _require_exact_keys(payload, REQUEST_KEYS, "request")
    _require_schema(payload, "REQUEST_INVALID")
    for field_name in ("attemptId", "sessionId", "workspaceId", "probeSelector"):
        _require_identifier(payload[field_name], field_name, "REQUEST_INVALID")
    _require_identifier(payload["target"], "target", "REQUEST_INVALID")
    for field_name in ("projectDir", "dataRoot"):
        value = payload[field_name]
        if not isinstance(value, str) or not os.path.isabs(value):
            raise SessionTraceError("REQUEST_INVALID", f"{field_name} is not absolute")
    if not os.path.isdir(str(payload["projectDir"])):
        raise SessionTraceError("REQUEST_INVALID", "projectDir is not a directory")
    _require_number(payload["deadlineUnix"], "deadlineUnix", "REQUEST_INVALID")
    delay = _require_number(
        payload["faulthandlerDelaySeconds"], "faulthandlerDelaySeconds", "REQUEST_INVALID"
    )
    if not 0.1 <= delay <= 5.0:
        raise SessionTraceError("REQUEST_INVALID", "faulthandler delay is out of range")
    digest = payload["requestDigest"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise SessionTraceError("REQUEST_INVALID", "requestDigest is invalid")
    body = {key: value for key, value in payload.items() if key != "requestDigest"}
    if not secrets.compare_digest(digest, _digest_mapping(body)):
        raise SessionTraceError("REQUEST_INVALID", "requestDigest does not match")
    return dict(payload)


def _require_identity(
    payload: Mapping[str, object],
    *,
    attempt_id: str,
    request_digest: str,
    pid: int,
    source_digest: str,
    interpreter: str,
    code: str,
) -> None:
    checks = (
        (payload["attemptId"] == attempt_id, "attempt"),
        (payload["requestDigest"] == request_digest, "request"),
        (type(payload["pid"]) is int and payload["pid"] == pid, "pid"),
        (payload["sourceDigest"] == source_digest, "source"),
        (
            isinstance(payload["interpreter"], str)
            and _normalized_path(payload["interpreter"]) == _normalized_path(interpreter),
            "interpreter",
        ),
    )
    if not all(passed for passed, _name in checks):
        raise SessionTraceError(code, "Run record identity does not match")


def _validate_claim(
    payload: Mapping[str, object],
    *,
    attempt_id: str,
    request_digest: str,
    pid: int,
    source_digest: str,
    interpreter: str,
) -> None:
    _require_exact_keys(payload, CLAIM_KEYS, "claim")
    _require_schema(payload, "CLAIM_MISMATCH")
    _require_identity(
        payload,
        attempt_id=attempt_id,
        request_digest=request_digest,
        pid=pid,
        source_digest=source_digest,
        interpreter=interpreter,
        code="CLAIM_MISMATCH",
    )
    _require_number(payload["claimedAtUnix"], "claimedAtUnix", "CLAIM_MISMATCH")


def _validate_ready(
    payload: Mapping[str, object],
    *,
    attempt_id: str,
    request_digest: str,
    pid: int,
    source_digest: str,
    interpreter: str,
) -> None:
    _require_exact_keys(payload, READY_KEYS, "ready")
    _require_schema(payload, "readiness-mismatch")
    _require_identity(
        payload,
        attempt_id=attempt_id,
        request_digest=request_digest,
        pid=pid,
        source_digest=source_digest,
        interpreter=interpreter,
        code="readiness-mismatch",
    )
    _require_identifier(payload["leaseId"], "leaseId", "readiness-mismatch")
    _require_number(payload["readyAtUnix"], "readyAtUnix", "readiness-mismatch")


def _validate_go(
    payload: Mapping[str, object],
    *,
    request: Mapping[str, object],
    pid: int,
    source_digest: str,
    interpreter: str,
) -> None:
    _require_exact_keys(payload, GO_KEYS, "go")
    _require_schema(payload, "go-identity-mismatch")
    _require_identity(
        payload,
        attempt_id=str(request["attemptId"]),
        request_digest=str(request["requestDigest"]),
        pid=pid,
        source_digest=source_digest,
        interpreter=interpreter,
        code="go-identity-mismatch",
    )
    _require_identifier(payload["leaseId"], "leaseId", "go-identity-mismatch")
    _require_number(payload["issuedAtUnix"], "issuedAtUnix", "go-identity-mismatch")


def _validate_session_options(
    options: object, request: Mapping[str, object]
) -> None:
    expected = _session_options(request)
    if not isinstance(options, Mapping) or set(options) != set(expected):
        raise SessionTraceError("result-mismatch", "Session options are invalid")
    for key, value in expected.items():
        actual = options[key]
        if type(actual) is not type(value) or actual != value:
            raise SessionTraceError("result-mismatch", "Session options are invalid")


def _validate_result(
    payload: Mapping[str, object],
    *,
    attempt_id: str,
    request_digest: str,
    pid: int,
    source_digest: str,
    lease_id: str | None,
    request: Mapping[str, object],
    interpreter: str,
) -> None:
    _require_exact_keys(payload, RESULT_KEYS, "result")
    _require_schema(payload, "result-mismatch")
    _require_identity(
        payload,
        attempt_id=attempt_id,
        request_digest=request_digest,
        pid=pid,
        source_digest=source_digest,
        interpreter=interpreter,
        code="result-mismatch",
    )
    result_lease = payload["leaseId"]
    if lease_id is None:
        if result_lease is not None:
            _require_identifier(result_lease, "leaseId", "result-mismatch")
    elif result_lease != lease_id:
        raise SessionTraceError("result-mismatch", "Result lease does not match")
    result_outcome = payload["outcome"]
    if not isinstance(result_outcome, str) or result_outcome not in RESULT_OUTCOMES:
        raise SessionTraceError("result-mismatch", "Result outcome is invalid")
    if type(payload["ok"]) is not bool:
        raise SessionTraceError("result-mismatch", "Result flag is invalid")
    if payload["physicalTargetState"] != "UNKNOWN":
        raise SessionTraceError("result-mismatch", "Physical state must stay UNKNOWN")
    facts = payload["facts"]
    if not isinstance(facts, Mapping):
        raise SessionTraceError("result-mismatch", "Result facts are invalid")
    if set(facts) != FACTS_KEYS:
        raise SessionTraceError("result-mismatch", "Result facts are invalid")
    for name in ("driverAcquired", "enumerations", "selections", "sessionClosed"):
        value = facts[name]
        if type(value) is not int or not 0 <= value <= 8:
            raise SessionTraceError("result-mismatch", "Result facts are invalid")
    for name in ("sessionConstructed", "sessionOpened"):
        if type(facts[name]) is not bool:
            raise SessionTraceError("result-mismatch", "Result facts are invalid")
    if facts["sessionOpened"] is not False:
        raise SessionTraceError("result-mismatch", "Session.open must never run")
    forbidden = facts["forbiddenCalls"]
    if (
        not isinstance(forbidden, list)
        or len(forbidden) > MAX_EVENTS
        or any(not isinstance(name, str) or _SAFE_CODE.fullmatch(name) is None for name in forbidden)
    ):
        raise SessionTraceError("result-mismatch", "Result facts are invalid")
    fingerprint = facts["probeFingerprint"]
    if fingerprint is not None and (
        not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
    ):
        raise SessionTraceError("result-mismatch", "Result facts are invalid")
    if payload["sessionOptions"] is not None:
        _validate_session_options(payload["sessionOptions"], request)
    traceback_meta = payload["traceback"]
    if not isinstance(traceback_meta, Mapping) or set(traceback_meta) != TRACEBACK_KEYS:
        raise SessionTraceError("result-mismatch", "Result trace metadata is invalid")
    if type(traceback_meta["armed"]) is not bool or type(traceback_meta["cancelled"]) is not bool:
        raise SessionTraceError("result-mismatch", "Result trace metadata is invalid")
    if type(traceback_meta["bytes"]) is not int or traceback_meta["bytes"] < 0:
        raise SessionTraceError("result-mismatch", "Result trace metadata is invalid")
    errors = payload["errors"]
    if not isinstance(errors, Mapping) or set(errors) != set(CHILD_ERROR_KEYS):
        raise SessionTraceError("result-mismatch", "Result errors are invalid")
    for value in errors.values():
        if value is not None and (
            not isinstance(value, str) or _SAFE_CODE.fullmatch(value) is None
        ):
            raise SessionTraceError("result-mismatch", "Result errors are invalid")


def _result_is_ok(payload: Mapping[str, object]) -> bool:
    facts = payload["facts"]
    errors = payload["errors"]
    assert isinstance(facts, Mapping) and isinstance(errors, Mapping)
    return bool(
        payload["ok"] is True
        and payload["outcome"] == "ok"
        and facts["driverAcquired"] == 1
        and facts["enumerations"] == 1
        and facts["selections"] == 1
        and facts["sessionConstructed"] is True
        and facts["sessionOpened"] is False
        and facts["sessionClosed"] == 1
        and facts["forbiddenCalls"] == []
        and all(value is None for value in errors.values())
    )


def _validate_events(
    payload: Mapping[str, object], *, attempt_id: str, request_digest: str, pid: int
) -> None:
    _require_exact_keys(payload, EVENTS_KEYS, "events")
    _require_schema(payload, "EVENTS_INVALID")
    if (
        payload["attemptId"] != attempt_id
        or payload["requestDigest"] != request_digest
        or type(payload["pid"]) is not int
        or payload["pid"] != pid
    ):
        raise SessionTraceError("EVENTS_INVALID", "Event identity does not match")
    events = payload["events"]
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise SessionTraceError("EVENTS_INVALID", "Event list is invalid")
    for entry in events:
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"stage", "elapsedMs"}
            or entry["stage"] not in EVENT_STAGES
            or type(entry["elapsedMs"]) is not int
            or entry["elapsedMs"] < 0
        ):
            raise SessionTraceError("EVENTS_INVALID", "Event list is invalid")


def _release_terminal_process_handles(process: object) -> list[str]:
    """Release real process handles only after a proven terminal exit."""

    errors: list[str] = []
    try:
        returncode = process.poll()  # type: ignore[attr-defined]
    except BaseException:
        return ["process-poll-failed"]
    if returncode is None:
        return ["process-not-terminal"]
    try:
        process.wait(timeout=1.0)  # type: ignore[attr-defined]
    except BaseException:
        errors.append("process-wait-failed")
    try:
        still_running = process.poll()  # type: ignore[attr-defined]
    except BaseException:
        still_running = None
        errors.append("process-poll-failed")
    if still_running is None:
        errors.append("process-still-live")
    handle = getattr(process, "_handle", None)
    if handle is not None and not bool(getattr(handle, "closed", False)):
        try:
            handle.Close()
        except BaseException:
            errors.append("process-handle-close-failed")
        else:
            try:
                setattr(process, "_handle", None)
            except BaseException:
                errors.append("process-handle-clear-failed")
    return errors


def _request_termination(
    output_dir: Path,
    attempt_id: str,
    process: object,
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, object]:
    """Ask the known-live child to stop exactly once, then join boundedly."""

    requested = False
    errors: list[str] = []
    try:
        _write_json_exclusive(
            output_dir / TERMINATE_FILE,
            {
                "schemaVersion": SCHEMA_VERSION,
                "attemptId": attempt_id,
                "requestedAtUnix": time.time(),
            },
        )
        requested = True
    except FileExistsError:
        requested = True
    except BaseException:
        errors.append("terminate-request-failed")
    join_deadline = clock() + OWNED_TERMINATION_JOIN_SECONDS
    while clock() < join_deadline:
        try:
            if process.poll() is not None:  # type: ignore[attr-defined]
                break
        except BaseException:
            errors.append("process-poll-failed")
            break
        sleep(POLL_SECONDS)
    try:
        returncode = process.poll()  # type: ignore[attr-defined]
    except BaseException:
        returncode = None
        errors.append("process-poll-failed")
    return {
        "terminateRequested": requested,
        "joined": returncode is not None,
        "returncode": returncode,
        "alive": returncode is None,
        "errors": errors,
    }


def _await_identity_file(
    path: Path,
    *,
    deadline_mono: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    cancel_event: threading.Event | None,
    process: object | None,
    validator: Callable[[Mapping[str, object]], None],
) -> tuple[str | None, dict[str, object] | None]:
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled", None
        status, payload = _read_json_once(path)
        if status == "ok":
            assert isinstance(payload, dict)
            try:
                validator(payload)
            except SessionTraceError as error:
                return error.code, payload
            return None, payload
        if status not in ("missing", "incomplete"):
            return "run-file-invalid", None
        if clock() >= deadline_mono:
            return "deadline", None
        if process is not None:
            try:
                terminal = process.poll() is not None  # type: ignore[attr-defined]
            except BaseException:
                terminal = False
            if terminal:
                status, payload = _read_json_once(path)
                if status == "ok":
                    assert isinstance(payload, dict)
                    try:
                        validator(payload)
                    except SessionTraceError as error:
                        return error.code, payload
                    return None, payload
                return "child-exited", None
        sleep(POLL_SECONDS)


def _launch_child(
    *,
    source_path: Path,
    interpreter: str,
    output_dir: Path,
    project_dir: Path,
    stderr: object,
    launcher: Callable[[Sequence[str], str], object] | None,
) -> object:
    argv = [str(interpreter), "-B", str(source_path), "child", str(output_dir)]
    if launcher is not None:
        return launcher(argv, str(project_dir))
    kwargs: dict[str, object] = {
        "cwd": str(project_dir),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": stderr,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(argv, **kwargs)


def _unexpected_entries(output_dir: Path) -> list[str]:
    try:
        names = os.listdir(output_dir)
    except OSError:
        return ["run-directory-unreadable"]
    extra = sorted(name for name in names if name not in RUN_FILE_NAMES)
    return extra


def _validate_config(config: AttemptConfig) -> None:
    if not isinstance(config.deadline_seconds, (int, float)) or isinstance(
        config.deadline_seconds, bool
    ):
        raise SessionTraceError("INVALID_DEADLINE", "Deadline is not a number")
    if not MIN_DEADLINE_SECONDS <= float(config.deadline_seconds) <= MAX_DEADLINE_SECONDS:
        raise SessionTraceError("INVALID_DEADLINE", "Deadline is out of range")
    _require_identifier(config.probe_selector, "probeSelector", "INVALID_CONFIGURATION")
    _require_identifier(config.target, "target", "INVALID_CONFIGURATION")
    for name, value in (
        ("output_dir", config.output_dir),
        ("data_root", config.data_root),
        ("project_dir", config.project_dir),
    ):
        if not isinstance(value, Path) or not value.is_absolute():
            raise SessionTraceError("INVALID_CONFIGURATION", f"{name} is not absolute")
    if not config.project_dir.is_dir():
        raise SessionTraceError("INVALID_CONFIGURATION", "project_dir is not a directory")


def _exit_code(outcome: str, ok: bool, errors: Sequence[str]) -> int:
    if ok:
        return 0
    if outcome == "cancelled":
        return _EXIT_CANCELLED
    if errors or outcome == "ok":
        return _EXIT_LIFECYCLE
    if outcome in ("readiness-timeout", "work-timeout", "exit-timeout"):
        return _EXIT_TIMEOUT
    if outcome in (
        "child-exited",
        "child-nonzero-exit",
        "result-mismatch",
        "result-invalid",
    ):
        return _EXIT_CHILD_FAILED
    return _EXIT_UNKNOWN


def run_attempt(
    config: AttemptConfig,
    *,
    launcher: Callable[[Sequence[str], str], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    cancel_event: threading.Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AttemptOutcome:
    """Run one bounded attempt and always leave a closed attempt record."""

    started = clock()
    _validate_config(config)
    output_dir = Path(config.output_dir)
    try:
        os.mkdir(output_dir)
    except FileExistsError as error:
        raise SessionTraceError(
            "OUTPUT_EXISTS", "Run directory already exists"
        ) from error
    except OSError as error:
        raise SessionTraceError(
            "OUTPUT_UNAVAILABLE", "Run directory is unavailable"
        ) from error

    source_path = Path(__file__).resolve()
    source_digest = _file_digest(source_path)
    interpreter = os.path.abspath(sys.executable)
    attempt_id = f"attempt-{secrets.token_hex(16)}"
    session_id = f"session-{secrets.token_hex(16)}"
    deadline_wall = wall_clock() + float(config.deadline_seconds)
    deadline_mono = started + float(config.deadline_seconds)
    request = _build_request(
        config,
        attempt_id=attempt_id,
        session_id=session_id,
        deadline_wall=deadline_wall,
    )
    request_digest = str(request["requestDigest"])
    _write_json_exclusive(output_dir / REQUEST_FILE, request)

    process: object | None = None
    errors: list[str] = []
    go_written = False
    ready_matched = False
    ready_payload: dict[str, object] | None = None
    result_payload: dict[str, object] | None = None
    result_valid = False
    outcome: str | None = None
    termination: dict[str, object] = {
        "terminateRequested": False,
        "joined": None,
        "returncode": None,
        "alive": None,
        "errors": [],
    }
    handle_errors: list[str] = []

    def _ready_validator(payload: Mapping[str, object]) -> None:
        _validate_ready(
            payload,
            attempt_id=attempt_id,
            request_digest=request_digest,
            pid=int(getattr(process, "pid")),
            source_digest=source_digest,
            interpreter=interpreter,
        )

    def _result_validator(payload: Mapping[str, object]) -> None:
        lease_id = None if ready_payload is None else str(ready_payload["leaseId"])
        _validate_result(
            payload,
            attempt_id=attempt_id,
            request_digest=request_digest,
            pid=int(getattr(process, "pid")),
            source_digest=source_digest,
            lease_id=lease_id,
            request=request,
            interpreter=interpreter,
        )

    try:
        if cancel_event is not None and cancel_event.is_set():
            outcome = "cancelled"
        else:
            stderr_handle = None
            try:
                stderr_fd = os.open(
                    output_dir / STDERR_FILE,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                stderr_handle = os.fdopen(stderr_fd, "wb")
            except OSError:
                errors.append("stderr-open-failed")
                outcome = "startup-failed"
            if outcome is None:
                try:
                    process = _launch_child(
                        source_path=source_path,
                        interpreter=interpreter,
                        output_dir=output_dir,
                        project_dir=Path(config.project_dir),
                        stderr=stderr_handle,
                        launcher=launcher,
                    )
                except BaseException:
                    errors.append("launch-failed")
                    outcome = "startup-failed"
                    process = None
                finally:
                    if stderr_handle is not None:
                        try:
                            stderr_handle.close()
                        except BaseException:
                            errors.append("stderr-close-failed")
            if outcome is None:
                child_pid = getattr(process, "pid", None)
                if type(child_pid) is not int or child_pid <= 0:
                    errors.append("startup-handle-invalid")
                    outcome = "startup-failed"
                    process = None
        if outcome is None and process is not None:
            ready_code, ready_seen = _await_identity_file(
                output_dir / READY_FILE,
                deadline_mono=deadline_mono,
                clock=clock,
                sleep=sleep,
                cancel_event=cancel_event,
                process=process,
                validator=_ready_validator,
            )
            ready_payload = ready_seen
            if ready_code is None:
                ready_matched = True
            else:
                outcome = {
                    "cancelled": "cancelled",
                    "deadline": "readiness-timeout",
                    "child-exited": "startup-exited",
                    "run-file-invalid": "readiness-invalid",
                }.get(ready_code, "readiness-mismatch")
            if outcome is None:
                claim_status, claim_payload = _peek_json(output_dir / CLAIM_FILE)
                if claim_status in ("oversized", "unreadable", "invalid"):
                    errors.append("claim-record-invalid")
                    outcome = "readiness-mismatch"
                elif claim_status == "ok" and isinstance(claim_payload, dict):
                    try:
                        _validate_claim(
                            claim_payload,
                            attempt_id=attempt_id,
                            request_digest=request_digest,
                            pid=int(getattr(process, "pid")),
                            source_digest=source_digest,
                            interpreter=interpreter,
                        )
                    except SessionTraceError:
                        errors.append("claim-identity-mismatch")
                        outcome = "readiness-mismatch"
            if outcome is None and clock() >= deadline_mono:
                outcome = "readiness-timeout"
            if outcome is None:
                assert ready_payload is not None
                go_payload: dict[str, object] = {
                    "schemaVersion": SCHEMA_VERSION,
                    "attemptId": attempt_id,
                    "requestDigest": request_digest,
                    "pid": int(getattr(process, "pid")),
                    "sourceDigest": source_digest,
                    "interpreter": ready_payload["interpreter"],
                    "leaseId": ready_payload["leaseId"],
                    "issuedAtUnix": wall_clock(),
                }
                try:
                    _write_json_exclusive(output_dir / GO_FILE, go_payload)
                except BaseException:
                    errors.append("grant-write-failed")
                    outcome = "grant-failed"
                else:
                    go_written = True
        if outcome is None and go_written and process is not None:
            result_code, result_seen = _await_identity_file(
                output_dir / RESULT_FILE,
                deadline_mono=deadline_mono,
                clock=clock,
                sleep=sleep,
                cancel_event=cancel_event,
                process=process,
                validator=_result_validator,
            )
            result_payload = result_seen
            if result_code is None:
                result_valid = True
            else:
                outcome = {
                    "cancelled": "cancelled",
                    "deadline": "work-timeout",
                    "child-exited": "child-exited",
                    "run-file-invalid": "result-invalid",
                }.get(result_code, "result-mismatch")
            if result_valid:
                while clock() < deadline_mono:
                    if process.poll() is not None:  # type: ignore[attr-defined]
                        break
                    sleep(POLL_SECONDS)
                returncode = process.poll()  # type: ignore[attr-defined]
                if returncode is None:
                    outcome = "exit-timeout"
                elif returncode != 0:
                    outcome = "child-nonzero-exit"
                else:
                    outcome = "ok"
        if outcome is None:
            outcome = "no-grant"
    except KeyboardInterrupt:
        outcome = "cancelled"
    except SessionTraceError as error:
        errors.append(_safe_code(error.code))
        outcome = "failure"
    finally:
        if process is not None:
            try:
                returncode = process.poll()  # type: ignore[attr-defined]
            except BaseException:
                returncode = None
                errors.append("process-poll-failed")
            termination["returncode"] = returncode
            termination["alive"] = None if returncode is None else False
            if returncode is None:
                requested = _request_termination(
                    output_dir, attempt_id, process, clock=clock, sleep=sleep
                )
                termination = requested
                returncode = requested["returncode"]
            if returncode is not None:
                handle_errors.extend(_release_terminal_process_handles(process))

    if result_payload is None and process is not None:
        status, payload = _read_json_once(output_dir / RESULT_FILE)
        if status == "ok" and isinstance(payload, dict):
            try:
                _result_validator(payload)
            except SessionTraceError:
                errors.append("result-identity-mismatch")
            else:
                result_payload = payload
                result_valid = True

    extra_entries = _unexpected_entries(output_dir)
    if extra_entries:
        errors.append("unexpected-entries")

    if result_valid and process is not None:
        events_status, events_payload = _read_json_once(output_dir / EVENTS_FILE)
        try:
            if events_status != "ok" or not isinstance(events_payload, dict):
                raise SessionTraceError("EVENTS_INVALID", "Event record is unavailable")
            _validate_events(
                events_payload,
                attempt_id=attempt_id,
                request_digest=request_digest,
                pid=int(getattr(process, "pid")),
            )
        except SessionTraceError:
            errors.append("events-invalid")

    try:
        traceback_bytes = (output_dir / TRACEBACK_FILE).stat().st_size
    except OSError:
        traceback_bytes = 0

    termination_errors = list(termination.get("errors") or [])  # type: ignore[arg-type]
    all_errors = errors + handle_errors + termination_errors
    child_alive = termination.get("alive") if process is not None else None
    child_returncode = termination.get("returncode") if process is not None else None
    result_ok = bool(
        result_valid and result_payload is not None and _result_is_ok(result_payload)
    )
    ok = bool(
        outcome == "ok"
        and ready_matched
        and go_written
        and child_returncode == 0
        and child_alive is False
        and result_ok
        and not all_errors
    )
    exit_code = _exit_code(str(outcome), ok, all_errors)
    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "requestDigest": request_digest,
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "outcome": str(outcome),
        "ok": ok,
        "exitCode": exit_code,
        "physicalTargetState": "UNKNOWN",
        "child": {
            "pid": None if process is None else getattr(process, "pid", None),
            "returncode": child_returncode,
            "alive": child_alive,
            "handleReleased": bool(
                process is not None
                and child_returncode is not None
                and not handle_errors
            ),
        },
        "grant": {"readyMatched": ready_matched, "goWritten": go_written},
        "result": {
            "present": result_payload is not None,
            "outcome": (
                result_payload.get("outcome") if result_payload is not None else None
            ),
            "ok": result_ok,
            "leaseReleased": bool(
                result_valid
                and result_payload is not None
                and isinstance(result_payload.get("errors"), Mapping)
                and result_payload["errors"].get("leaseRelease") is None  # type: ignore[union-attr]
                and result_payload.get("leaseId") is not None
            ),
        },
        "traceback": {"present": traceback_bytes > 0, "bytes": traceback_bytes},
        "termination": {
            "terminateRequested": bool(termination.get("terminateRequested")),
            "joined": termination.get("joined"),
            "alive": termination.get("alive"),
        },
        "errors": sorted(set(all_errors)),
        "unexpectedEntries": extra_entries,
        "durationMs": int((clock() - started) * 1000),
    }
    report_error: str | None = None
    try:
        _write_json_exclusive(output_dir / ATTEMPT_FILE, report)
    except BaseException as error:
        report_error = _safe_code(error)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    if report_error is not None:
        exit_code = _EXIT_LIFECYCLE
        print("session-trace: attempt report write failed", file=sys.stderr)
    return AttemptOutcome(
        attempt_id=attempt_id,
        outcome=str(outcome),
        ok=ok,
        exit_code=exit_code,
        report=report,
    )


def _error_name(error: BaseException) -> str:
    return _safe_code(type(error).__name__)


class _LeaseSlot:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lease_id: str | None = None

    def set(self, lease_id: str) -> None:
        with self._lock:
            self._lease_id = lease_id

    def get(self) -> str | None:
        with self._lock:
            return self._lease_id


def _make_health_handler(
    slot: _LeaseSlot, protocol: str, toolkit_version: str
) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            lease_id = slot.get()
            token = self.headers.get("X-Probe-Lease")
            if self.path != "/health" or lease_id is None or token != lease_id:
                self.send_error(404 if self.path != "/health" else 503)
                return
            body = json.dumps(
                {
                    "ok": True,
                    "protocol": protocol,
                    "toolkitVersion": toolkit_version,
                    "leaseId": lease_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    return Handler


class _HealthServer:
    """Real loopback-only lease health bound to the child's actual lease."""

    def __init__(self) -> None:
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._slot = _LeaseSlot()

    def start(self) -> str:
        from stm32_toolkit import __version__
        from stm32_toolkit.probe.model import PROBE_PROTOCOL_VERSION

        handler = _make_health_handler(self._slot, PROBE_PROTOCOL_VERSION, __version__)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="session-trace-health",
        )
        self._server = server
        self._thread = thread
        thread.start()
        self._started = True
        port = int(server.server_address[1])
        return f"http://127.0.0.1:{port}/health"

    def set_lease(self, lease_id: str) -> None:
        self._slot.set(lease_id)

    def stop(self) -> str | None:
        server = self._server
        started = self._started
        self._server = None
        self._started = False
        error: str | None = None
        if server is not None:
            if started:
                # shutdown() joins the serve_forever loop; it must never be
                # called for a server whose loop was not started.
                try:
                    server.shutdown()
                except BaseException:
                    error = "health-shutdown-failed"
            try:
                server.server_close()
            except BaseException:
                if error is None:
                    error = "health-close-failed"
        return error


class _NativeTraceback:
    """Exactly one real one-shot faulthandler dump into a run-owned file."""

    def __init__(self, path: Path, delay: float = FAULTHANDLER_DELAY_SECONDS) -> None:
        self.path = path
        self.delay = delay
        self.armed = False
        self.cancelled = False
        self.bytes = 0
        self.left_open = False
        self._file: object | None = None

    def arm(self) -> str | None:
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except OSError:
            return "traceback-open-failed"
        try:
            handle = os.fdopen(descriptor, "wb")
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            return "traceback-open-failed"
        self._file = handle
        try:
            faulthandler.dump_traceback_later(
                self.delay, repeat=False, exit=False, file=handle
            )
        except BaseException:
            try:
                handle.close()
            except BaseException:
                pass
            self._file = None
            return "faulthandler-arm-failed"
        self.armed = True
        return None

    def disarm(self) -> str | None:
        if not self.armed:
            return None
        try:
            faulthandler.cancel_dump_traceback_later()
        except BaseException:
            # Never close a possibly active writer to imply a clean stop.
            self.left_open = True
            return "faulthandler-cancel-failed"
        self.cancelled = True
        handle = self._file
        self._file = None
        if handle is None:
            return None
        try:
            handle.flush()  # type: ignore[attr-defined]
            handle.close()  # type: ignore[attr-defined]
        except BaseException:
            return "traceback-close-failed"
        try:
            self.bytes = self.path.stat().st_size
        except OSError:
            self.bytes = 0
        return None

    def summary(self) -> dict[str, object]:
        return {
            "armed": self.armed,
            "bytes": int(self.bytes),
            "cancelled": self.cancelled,
        }


_FORBIDDEN_NAMES = frozenset(
    {
        "open",
        "connect",
        "halt",
        "resume",
        "reset",
        "step",
        "reset_and_halt",
        "program",
        "program_file",
        "read_memory",
        "read_memory_block8",
        "read_core_registers",
        "read_core_registers_raw",
        "get_state",
        "flash",
        "recover",
        "unlock",
        "close",
    }
)


class _ForbiddenCall(RuntimeError):
    pass


class _FakeReceipt:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, object] = {
            "listProbes": 0,
            "createSession": 0,
            "options": None,
            "selectedIsProbe": None,
            "sessionOpenCalls": 0,
            "sessionCloseCalls": 0,
            "forbiddenCalls": [],
            "blockResult": None,
        }

    def forbid(self, name: str) -> None:
        calls = self.data["forbiddenCalls"]
        assert isinstance(calls, list)
        calls.append(name)
        raise _ForbiddenCall(name)

    def flush(self) -> None:
        if self.path is None:
            return
        try:
            self.path.write_text(
                json.dumps(self.data, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError:
            pass


class _FakeProbe:
    def __init__(self, unique_id: str, receipt: _FakeReceipt) -> None:
        self.unique_id = unique_id
        self._receipt = receipt

    def __getattr__(self, name: str) -> object:
        if name in _FORBIDDEN_NAMES:
            return lambda *_args, **_kwargs: self._receipt.forbid(name)
        raise AttributeError(name)


class _FakeSession:
    def __init__(self, probe: _FakeProbe, receipt: _FakeReceipt) -> None:
        self.probe = probe
        self.closed = False
        self._receipt = receipt

    def open(self) -> None:
        self._receipt.data["sessionOpenCalls"] = int(
            self._receipt.data["sessionOpenCalls"]
        ) + 1
        self._receipt.forbid("open")

    def close(self) -> None:
        self._receipt.data["sessionCloseCalls"] = int(
            self._receipt.data["sessionCloseCalls"]
        ) + 1
        self.closed = True
        if self._receipt.data.get("mode") == "close-error":
            raise RuntimeError("fake close failure")

    def __getattr__(self, name: str) -> object:
        if name in _FORBIDDEN_NAMES and name != "close":
            return lambda *_args, **_kwargs: self._receipt.forbid(name)
        raise AttributeError(name)


class _FakeDriver:
    def __init__(
        self,
        config: "_FakeConfig",
        receipt: _FakeReceipt,
        *,
        terminate_path: Path,
    ) -> None:
        self._config = config
        self._receipt = receipt
        self._terminate_path = terminate_path
        self._probe = _FakeProbe(config.probe_id, receipt)
        receipt.data["mode"] = config.mode

    def list_probes(self) -> tuple[object, ...]:
        self._receipt.data["listProbes"] = int(self._receipt.data["listProbes"]) + 1
        return (self._probe,)

    def _block(self, stubborn: bool) -> str:
        end = time.monotonic() + self._config.seconds
        release = self._config.release_path
        while time.monotonic() < end:
            if release is not None and release.exists():
                return "released"
            if not stubborn and self._terminate_path.exists():
                return "terminated"
            time.sleep(POLL_SECONDS)
        return "elapsed"

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> object:
        self._receipt.data["createSession"] = (
            int(self._receipt.data["createSession"]) + 1
        )
        self._receipt.data["options"] = dict(options)
        self._receipt.data["selectedIsProbe"] = probe is self._probe
        try:
            if self._config.mode == "construct-error":
                raise RuntimeError("fake constructor failure")
            if self._config.mode in ("construct-block-exit", "construct-block-stubborn"):
                self._receipt.data["blockResult"] = self._block(
                    self._config.mode == "construct-block-stubborn"
                )
            return _FakeSession(self._probe, self._receipt)
        finally:
            self._receipt.flush()


@dataclass(frozen=True)
class _FakeConfig:
    mode: str
    seconds: float = 0.0
    probe_id: str = "fake-probe-1"
    release_path: Path | None = None
    receipt_path: Path | None = None


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value or not os.path.isabs(value):
        return None
    return Path(value)


def _fake_config() -> _FakeConfig:
    mode = os.environ.get(FAKE_MODE_ENV, "").strip() or "none"
    seconds = 0.0
    try:
        seconds = float(os.environ.get(FAKE_SECONDS_ENV, "0") or "0")
    except ValueError:
        seconds = 0.0
    seconds = min(max(seconds, 0.0), 60.0)
    probe_id = os.environ.get(FAKE_PROBE_ENV, "").strip() or "fake-probe-1"
    if (
        not probe_id.isprintable()
        or len(probe_id.encode("utf-8", errors="replace")) > 512
    ):
        probe_id = "fake-probe-1"
    return _FakeConfig(
        mode=mode,
        seconds=seconds,
        probe_id=probe_id,
        release_path=_env_path(FAKE_RELEASE_ENV),
        receipt_path=_env_path(FAKE_RECEIPT_ENV),
    )


def _acquire_driver(
    fake: _FakeConfig, output_dir: Path
) -> tuple[object | None, str | None, _FakeReceipt | None]:
    if fake.mode == "none":
        try:
            from stm32_toolkit.probe.pyocd_backend import _DefaultPyOCDDriver

            return _DefaultPyOCDDriver(), None, None
        except BaseException:
            return None, "driver-acquire-failed", None
    if fake.mode not in FAKE_MODES:
        return None, "fake-mode-invalid", None
    receipt = _FakeReceipt(fake.receipt_path)
    driver = _FakeDriver(fake, receipt, terminate_path=output_dir / TERMINATE_FILE)
    return driver, None, receipt


def _select_exactly_one(
    probes: Iterable[object], selector: str
) -> object:
    from stm32_toolkit.probe.selector import (
        public_probe_selector,
        valid_hardware_probe_id,
    )

    matches: list[object] = []
    for probe in probes:
        try:
            raw = getattr(probe, "unique_id", None)
        except Exception:
            raise SessionTraceError("SELECTION_ERROR", "Probe descriptor is invalid")
        if not valid_hardware_probe_id(raw):
            raise SessionTraceError("SELECTION_ERROR", "Probe descriptor is invalid")
        if public_probe_selector(raw) == selector:
            matches.append(probe)
    if not matches:
        raise SessionTraceError("SELECTION_NOT_FOUND", "Selected probe is unavailable")
    if len(matches) != 1:
        raise SessionTraceError("SELECTION_AMBIGUOUS", "Selected probe is ambiguous")
    return matches[0]


def _fingerprint_probe(probe: object) -> str:
    from stm32_toolkit.probe.selector import probe_fingerprint

    return probe_fingerprint(getattr(probe, "unique_id"))


def _release_lease(lease: object) -> str | None:
    try:
        lease.release()  # type: ignore[attr-defined]
    except BaseException as error:
        return _error_name(error)
    return None


def _construct_and_close(
    facts: dict[str, object],
    errors: dict[str, str | None],
    trace_meta: dict[str, object],
    *,
    driver: object,
    probe: object,
    options: Mapping[str, object],
    traceback_path: Path,
    events: list[dict[str, object]],
    started: float,
) -> None:
    trace = _NativeTraceback(traceback_path, FAULTHANDLER_DELAY_SECONDS)
    arm_error = trace.arm()
    trace_meta.update(trace.summary())
    if arm_error is not None:
        errors["tracebackArm"] = arm_error
        _event(events, "faulthandler-arm-failed", started)
        return
    _event(events, "faulthandler-armed", started)
    session: object | None = None
    try:
        try:
            session = driver.create_session(probe, options=options)  # type: ignore[attr-defined]
        except Exception as error:
            errors["construction"] = _error_name(error)
            _event(events, "session-construct-failed", started)
        else:
            facts["sessionConstructed"] = True
            _event(events, "session-constructed", started)
    finally:
        disarm_error = trace.disarm()
        trace_meta.update(trace.summary())
        if disarm_error is not None:
            errors[
                "tracebackCancel"
                if disarm_error == "faulthandler-cancel-failed"
                else "tracebackClose"
            ] = disarm_error
            _event(events, "traceback-cancel-failed", started)
        else:
            _event(events, "traceback-cancelled", started)
    if session is None:
        return
    try:
        getattr(session, "close")()
    except Exception as error:
        errors["sessionClose"] = _error_name(error)
        _event(events, "session-close-failed", started)
    else:
        facts["sessionClosed"] = 1
        _event(events, "session-closed", started)


def _child_ok(
    outcome: str, facts: Mapping[str, object], errors: Mapping[str, str | None]
) -> bool:
    return bool(
        outcome == "ok"
        and facts["driverAcquired"] == 1
        and facts["enumerations"] == 1
        and facts["selections"] == 1
        and facts["sessionConstructed"] is True
        and facts["sessionOpened"] is False
        and facts["sessionClosed"] == 1
        and facts["forbiddenCalls"] == []
        and all(value is None for value in errors.values())
    )


def _load_request(output_dir: Path) -> dict[str, object] | None:
    try:
        payload = _read_json_until(output_dir / REQUEST_FILE, time.time() + 5.0)
    except SessionTraceError:
        return None
    try:
        return _validate_request(payload)
    except SessionTraceError:
        return None


def _acquire_lease(
    request: Mapping[str, object], health_url: str
) -> tuple[object | None, str | None, bool]:
    try:
        from stm32_toolkit.probe.lease import (
            ProbeBusyError,
            ProbeLeaseError,
            ProbeLeaseManager,
        )
        from stm32_toolkit.probe.model import OperationLevel
    except BaseException:
        return None, "lease-import-failed", False
    try:
        manager = ProbeLeaseManager(Path(str(request["dataRoot"])))
        lease = manager.acquire(
            probe_id=str(request["probeSelector"]),
            workspace_id=WORKSPACE_ID,
            session_id=str(request["sessionId"]),
            operation_level=OperationLevel.OBSERVE,
            health_url=health_url,
        )
    except ProbeBusyError:
        return None, "PROBE_BUSY", True
    except ProbeLeaseError as error:
        return None, _safe_code(error.code), False
    except BaseException:
        return None, "lease-acquire-failed", False
    return lease, None, False


def _await_go(
    output_dir: Path,
    request: Mapping[str, object],
    source_digest: str,
    interpreter: str,
) -> str:
    deadline = float(request["deadlineUnix"])
    while True:
        if (output_dir / TERMINATE_FILE).exists():
            return "cancelled-before-go"
        status, payload = _read_json_once(output_dir / GO_FILE)
        if status == "ok":
            assert isinstance(payload, dict)
            try:
                _validate_go(
                    payload,
                    request=request,
                    pid=os.getpid(),
                    source_digest=source_digest,
                    interpreter=interpreter,
                )
            except SessionTraceError:
                return "go-identity-mismatch"
            return "accepted"
        if status not in ("missing", "incomplete"):
            return "go-identity-mismatch"
        if time.time() >= deadline:
            return "go-timeout"
        time.sleep(POLL_SECONDS)


def child_main(output_dir: Path | str) -> int:
    """Child entrypoint: reserve, lease, READY, wait for GO, construct once."""

    output_dir = Path(output_dir)
    request = _load_request(output_dir)
    if request is None:
        return _EXIT_UNKNOWN
    attempt_id = str(request["attemptId"])
    request_digest = str(request["requestDigest"])
    source_digest = _file_digest(Path(__file__).resolve())
    interpreter = os.path.abspath(sys.executable)
    started = time.monotonic()
    events: list[dict[str, object]] = []
    errors: dict[str, str | None] = {key: None for key in CHILD_ERROR_KEYS}
    facts = _new_facts()
    options: dict[str, object] | None = None
    trace_meta: dict[str, object] = {"armed": False, "bytes": 0, "cancelled": False}
    outcome = "internal-error"
    lease: object | None = None
    receipt: _FakeReceipt | None = None
    server = _HealthServer()
    fake = _fake_config()

    claim_payload: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "requestDigest": request_digest,
        "pid": os.getpid(),
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "claimedAtUnix": time.time(),
    }
    try:
        _write_json_exclusive(output_dir / CLAIM_FILE, claim_payload)
    except (FileExistsError, OSError):
        # One-shot output: never overwrite an existing claim or result.
        return _EXIT_REFUSED
    _event(events, "claim-reserved", started)

    try:
        health_url: str | None = None
        try:
            health_url = server.start()
        except BaseException:
            errors["health"] = "health-start-failed"
        if health_url is None:
            outcome = "lease-error"
            errors["lease"] = "HEALTH_UNAVAILABLE"
        else:
            lease, lease_error, busy = _acquire_lease(request, health_url)
            if busy:
                outcome = "busy"
                errors["lease"] = "PROBE_BUSY"
            elif lease is None:
                outcome = "lease-error"
                errors["lease"] = lease_error or "lease-acquire-failed"
            else:
                server.set_lease(str(getattr(lease, "lease_id")))
                _event(events, "lease-acquired", started)
                if fake.mode == "no-ready":
                    # A deliberately partial start: claim and lease exist but
                    # no READY is ever published.
                    outcome = "startup-aborted"
                else:
                    ready_pid = (
                        os.getpid() + 1 if fake.mode == "bad-ready" else os.getpid()
                    )
                    ready_payload: dict[str, object] = {
                        "schemaVersion": SCHEMA_VERSION,
                        "attemptId": attempt_id,
                        "requestDigest": request_digest,
                        "pid": ready_pid,
                        "sourceDigest": source_digest,
                        "interpreter": interpreter,
                        "leaseId": str(getattr(lease, "lease_id")),
                        "readyAtUnix": time.time(),
                    }
                    try:
                        _write_json_exclusive(output_dir / READY_FILE, ready_payload)
                    except BaseException:
                        errors["ready"] = "ready-write-failed"
                        outcome = "ready-write-failed"
                    else:
                        _event(events, "ready-published", started)
                        grant = _await_go(
                            output_dir, request, source_digest, interpreter
                        )
                        if grant == "accepted":
                            _event(events, "go-accepted", started)
                            driver, driver_error, receipt = _acquire_driver(
                                fake, output_dir
                            )
                            if driver is None:
                                errors["construction"] = driver_error
                                outcome = "driver-error"
                            else:
                                facts["driverAcquired"] = 1
                                _event(events, "driver-acquired", started)
                                try:
                                    probes = tuple(driver.list_probes())  # type: ignore[attr-defined]
                                except BaseException:
                                    errors["construction"] = "enumeration-failed"
                                    outcome = "driver-error"
                                else:
                                    facts["enumerations"] = 1
                                    _event(events, "probe-enumerated", started)
                                    try:
                                        probe = _select_exactly_one(
                                            probes, str(request["probeSelector"])
                                        )
                                    except SessionTraceError:
                                        errors["construction"] = "selection-failed"
                                        outcome = "selection-error"
                                    else:
                                        facts["selections"] = 1
                                        facts["probeFingerprint"] = _fingerprint_probe(
                                            probe
                                        )
                                        _event(events, "probe-selected", started)
                                        options = _session_options(request)
                                        _construct_and_close(
                                            facts,
                                            errors,
                                            trace_meta,
                                            driver=driver,
                                            probe=probe,
                                            options=options,
                                            traceback_path=output_dir / TRACEBACK_FILE,
                                            events=events,
                                            started=started,
                                        )
                                        outcome = (
                                            "ok"
                                            if facts["sessionConstructed"]
                                            else "construct-error"
                                        )
                                        if (output_dir / TERMINATE_FILE).exists():
                                            outcome = "cancelled-after-go"
                                            _event(events, "cancelled", started)
                        elif grant == "cancelled-before-go":
                            outcome = "cancelled-before-go"
                        elif grant == "go-identity-mismatch":
                            outcome = "go-identity-mismatch"
                            errors["go"] = "go-identity-mismatch"
                        else:
                            outcome = "go-timeout"
                            errors["go"] = "go-timeout"
    except SessionTraceError as error:
        errors["internal"] = _safe_code(error.code)
        outcome = "internal-error"
    except Exception as error:
        errors["internal"] = _error_name(error)
        outcome = "internal-error"
    finally:
        if lease is not None:
            release_error = _release_lease(lease)
            errors["leaseRelease"] = release_error
            _event(
                events,
                "lease-released" if release_error is None else "lease-release-failed",
                started,
            )
        health_error = server.stop()
        if health_error is not None and errors["health"] is None:
            errors["health"] = health_error
        if receipt is not None:
            receipt.flush()

    lease_id = None if lease is None else str(getattr(lease, "lease_id"))
    events_payload: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "requestDigest": request_digest,
        "pid": os.getpid(),
        "events": events,
    }
    try:
        _write_json_exclusive(output_dir / EVENTS_FILE, events_payload)
    except BaseException:
        errors["events"] = "events-write-failed"
    ok = _child_ok(outcome, facts, errors)
    if outcome == "ok" and not ok:
        # Cleanup/handle failures keep narrow constructor facts but are never
        # reported as an overall success.
        outcome = "internal-error"
    result_payload: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "requestDigest": request_digest,
        "pid": os.getpid(),
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "leaseId": lease_id,
        "outcome": outcome,
        "ok": ok,
        "physicalTargetState": "UNKNOWN",
        "facts": facts,
        "sessionOptions": options,
        "traceback": trace_meta,
        "errors": errors,
    }
    try:
        _write_json_exclusive(output_dir / RESULT_FILE, result_payload)
    except BaseException:
        print("session-trace: child result write failed", file=sys.stderr)
        return _EXIT_CHILD_FAILED
    return 0 if ok else _EXIT_CHILD_FAILED


REFUSAL_TEXT = (
    "session-trace: refusing to run.\n"
    "The default invocation performs no filesystem, registry or process "
    "activity.  The 'run' command performs a real one-shot USB metadata "
    "exchange through the Toolkit default driver and requires a separate, "
    "explicit hardware authorization plus a filled execution card; this "
    "helper does not grant that authorization."
)

_RUN_FLAGS = {
    "--output-dir": "output_dir",
    "--data-root": "data_root",
    "--probe": "probe",
    "--target": "target",
    "--project-dir": "project_dir",
    "--deadline-seconds": "deadline",
}


def _parse_arguments(
    argv: list[str],
) -> tuple[str, object] | None:
    if not argv:
        return None
    command = argv[0]
    if command == "child":
        if len(argv) != 2:
            return None
        return ("child", Path(argv[1]))
    if command != "run":
        return None
    values: dict[str, str] = {}
    index = 1
    while index < len(argv):
        token = argv[index]
        if token not in _RUN_FLAGS or index + 1 >= len(argv):
            raise SessionTraceError(
                "INVALID_ARGUMENT", "Unrecognized or incomplete argument"
            )
        values[_RUN_FLAGS[token]] = argv[index + 1]
        index += 2
    for name in ("output_dir", "data_root", "probe", "target", "project_dir"):
        if name not in values:
            raise SessionTraceError("INVALID_ARGUMENT", "A required argument is missing")
    deadline = DEFAULT_DEADLINE_SECONDS
    if "deadline" in values:
        try:
            deadline = float(values["deadline"])
        except ValueError as error:
            raise SessionTraceError(
                "INVALID_DEADLINE", "Deadline is invalid"
            ) from error
    config = AttemptConfig(
        output_dir=Path(values["output_dir"]),
        data_root=Path(values["data_root"]),
        probe_selector=values["probe"],
        target=values["target"],
        project_dir=Path(values["project_dir"]),
        deadline_seconds=deadline,
    )
    _validate_config(config)
    return ("run", config)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = _parse_arguments(arguments)
    except SessionTraceError as error:
        print(f"session-trace: {error.code}: {error.message}", file=sys.stderr)
        return _EXIT_REFUSED
    if parsed is None:
        print(REFUSAL_TEXT, file=sys.stderr)
        return _EXIT_REFUSED
    kind, value = parsed
    if kind == "child":
        return child_main(value)  # type: ignore[arg-type]
    cancel_event = threading.Event()
    previous: object | None = None
    installed = False
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        try:
            previous = signal.signal(
                signal.SIGBREAK, lambda _signum, _frame: cancel_event.set()
            )
            installed = True
        except (OSError, ValueError):
            previous = None
    try:
        outcome = run_attempt(value, cancel_event=cancel_event)  # type: ignore[arg-type]
        return outcome.exit_code
    except SessionTraceError as error:
        print(f"session-trace: {error.code}: {error.message}", file=sys.stderr)
        return _EXIT_REFUSED
    except KeyboardInterrupt:
        return _EXIT_CANCELLED
    finally:
        if installed and previous is not None:
            try:
                signal.signal(signal.SIGBREAK, previous)
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
