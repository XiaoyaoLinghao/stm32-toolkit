"""Closed event payload validation and run assembly."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence, cast

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity, canonical_json_bytes

from .model import (
    CASE_STATES,
    MAX_CASES,
    MAX_DURATION_MS,
    TEST_SCHEMA,
    TestCaseResult,
    TestInventory,
    TestProtocolError,
    TestRunManifest,
    calculate_inventory_digest,
    protocol_error,
)


TARGET_FRAME_V1 = "stm32-target-frame/1"
TARGET_FRAME_V2 = "stm32-target-frame/2"


_PAYLOAD_FIELDS = {
    "inventory": {"mode", "identity", "case_ids", "inventory_digest", "discovered_at_utc"},
    "run_start": {"run_id", "started_at_utc", "case_ids", "inventory_digest"},
    "case_start": {"case_id", "started_at_utc"},
    "case_result": {
        "case_id", "state", "ended_at_utc", "duration_ms", "message", "stdout", "stderr"
    },
    "run_end": {
        "state", "ended_at_utc", "duration_ms", "inventory_digest", "build_id",
        "elf_sha256", "target_device", "counts", "event_stream_digest",
    },
    "log": {"timestamp_utc", "stream", "message"},
}

_V2_PAYLOAD_FIELDS = {
    "inventory": {"mode", "case_ids", "case_inventory_digest", "monotonic_ms"},
    "run_start": {"case_ids", "case_inventory_digest", "monotonic_ms"},
    "case_start": {"case_id", "monotonic_ms"},
    "case_result": {"case_id", "state", "monotonic_ms", "message"},
    "run_end": {"state", "case_inventory_digest", "counts", "event_stream_digest", "monotonic_ms"},
    "log": {"stream", "message", "monotonic_ms"},
}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 64 * 1024:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid")
    return value


def _utc(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != text:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid")
    return text


def _integer(value: object, field: str, maximum: int = MAX_DURATION_MS) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid")
    return value


def _v2_monotonic(value: object) -> int:
    return _integer(value, "monotonic_ms", MAX_DURATION_MS)


def _artifact(value: object, field: str) -> ArtifactRef | None:
    if value is None:
        return None
    if isinstance(value, ArtifactRef):
        return value
    if isinstance(value, dict):
        try:
            return ArtifactRef.from_dict(value)
        except ValueError as exc:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid") from exc
    raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid")


def _validate_event_payload_v1(kind: str, payload: object) -> dict[str, object]:
    """Validate one legacy version-1 decoded JSON payload."""
    if not isinstance(kind, str):
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "event kind is invalid")
    fields = _PAYLOAD_FIELDS.get(kind)
    if fields is None or not isinstance(payload, dict) or set(payload) != fields:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "event payload fields are invalid")
    value = dict(payload)
    if kind == "inventory":
        if value["mode"] not in {"host", "target"}:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "inventory mode is invalid")
        try:
            EvidenceIdentity.from_dict(value["identity"])
        except ValueError as exc:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "inventory identity is invalid") from exc
        _case_ids(value["case_ids"])
        _hashes(value, "inventory_digest")
        _utc(value["discovered_at_utc"], "discovered_at_utc")
    elif kind == "run_start":
        _text(value["run_id"], "run_id")
        _utc(value["started_at_utc"], "started_at_utc")
        _case_ids(value["case_ids"])
        _hashes(value, "inventory_digest")
    elif kind == "case_start":
        _text(value["case_id"], "case_id")
        _utc(value["started_at_utc"], "started_at_utc")
    elif kind == "case_result":
        _text(value["case_id"], "case_id")
        if value["state"] not in CASE_STATES:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case state is invalid")
        _utc(value["ended_at_utc"], "ended_at_utc")
        _integer(value["duration_ms"], "duration_ms")
        if value["message"] is not None:
            _text(value["message"], "message")
        _artifact(value["stdout"], "stdout")
        _artifact(value["stderr"], "stderr")
    elif kind == "run_end":
        if value["state"] not in {"passed", "failed", "error", "cancelled"}:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "terminal run state is invalid")
        _utc(value["ended_at_utc"], "ended_at_utc")
        _integer(value["duration_ms"], "duration_ms")
        for field in ("inventory_digest", "build_id", "elf_sha256", "event_stream_digest"):
            _hashes(value, field)
        _text(value["target_device"], "target_device")
        counts = value["counts"]
        if not isinstance(counts, dict) or set(counts) != set(CASE_STATES):
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "run counts are invalid")
        for state in CASE_STATES:
            _integer(counts[state], f"counts.{state}", MAX_CASES)
    else:
        _utc(value["timestamp_utc"], "timestamp_utc")
        if value["stream"] not in {"stdout", "stderr"}:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "log stream is invalid")
        _text(value["message"], "message")
    return value


def calculate_case_inventory_digest(case_ids: Sequence[str]) -> str:
    """Hash the canonical, target-owned v2 case inventory declaration."""
    if not isinstance(case_ids, Sequence) or isinstance(case_ids, (str, bytes)):
        raise protocol_error("TEST_PROTOCOL_INVALID", "case_ids must be a sequence")
    if not case_ids:
        raise protocol_error("TEST_NO_CASES", "test inventory is empty")
    if len(case_ids) > MAX_CASES:
        raise protocol_error("TEST_PROTOCOL_INVALID", "test inventory is too large")
    normalized = tuple(_text(item, "case_id") for item in case_ids)
    if len(set(normalized)) != len(normalized):
        raise protocol_error("TEST_DUPLICATE_CASE", "case IDs must be unique")
    ordered = tuple(sorted(normalized, key=lambda item: item.encode("utf-8")))
    return sha256(
        canonical_json_bytes(
            {"case_ids": list(ordered), "mode": "target", "protocol": TARGET_FRAME_V2}
        )
    ).hexdigest()


def _validate_v2_case_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_CASES:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case_ids are invalid")
    normalized = tuple(_text(item, "case_id") for item in value)
    if len(set(normalized)) != len(normalized):
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case_ids are duplicated")
    if normalized != tuple(sorted(normalized, key=lambda item: item.encode("utf-8"))):
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case_ids are not in UTF-8 byte order")
    return normalized


def _validate_event_payload_v2(kind: str, payload: object) -> dict[str, object]:
    """Validate one closed target-frame version-2 payload."""
    fields = _V2_PAYLOAD_FIELDS.get(kind)
    if fields is None or not isinstance(payload, dict) or set(payload) != fields:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "event payload fields are invalid")
    value = dict(payload)
    if kind == "inventory":
        if value["mode"] != "target":
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "inventory mode is invalid")
        case_ids = _validate_v2_case_ids(value["case_ids"])
        _hashes(value, "case_inventory_digest")
        if value["case_inventory_digest"] != calculate_case_inventory_digest(case_ids):
            raise protocol_error("TEST_INVENTORY_CHANGED", "case inventory digest contradicts case IDs")
        _v2_monotonic(value["monotonic_ms"])
    elif kind == "run_start":
        case_ids = _validate_v2_case_ids(value["case_ids"])
        _hashes(value, "case_inventory_digest")
        if value["case_inventory_digest"] != calculate_case_inventory_digest(case_ids):
            raise protocol_error("TEST_INVENTORY_CHANGED", "case inventory digest contradicts case IDs")
        _v2_monotonic(value["monotonic_ms"])
    elif kind == "case_start":
        _text(value["case_id"], "case_id")
        _v2_monotonic(value["monotonic_ms"])
    elif kind == "case_result":
        _text(value["case_id"], "case_id")
        if value["state"] not in CASE_STATES:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case state is invalid")
        _v2_monotonic(value["monotonic_ms"])
        if value["message"] is not None:
            _text(value["message"], "message")
    elif kind == "run_end":
        if value["state"] not in {"passed", "failed", "error", "cancelled"}:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "terminal run state is invalid")
        _hashes(value, "case_inventory_digest")
        _hashes(value, "event_stream_digest")
        counts = value["counts"]
        if not isinstance(counts, dict) or set(counts) != set(CASE_STATES):
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "run counts are invalid")
        for state in CASE_STATES:
            _integer(counts[state], f"counts.{state}", MAX_CASES)
        _v2_monotonic(value["monotonic_ms"])
    else:
        if value["stream"] not in {"stdout", "stderr"}:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "log stream is invalid")
        _text(value["message"], "message")
        _v2_monotonic(value["monotonic_ms"])
    return value


def validate_event_payload(
    kind: str, payload: object, *, frame_version: int = 1
) -> dict[str, object]:
    """Validate one decoded JSON payload for an explicit frame version."""
    if type(frame_version) is not int or frame_version not in {1, 2}:
        raise protocol_error("TEST_FRAME_VERSION_INVALID", "target frame version is unsupported")
    if frame_version == 1:
        return _validate_event_payload_v1(kind, payload)
    return _validate_event_payload_v2(kind, payload)


def _hashes(value: Mapping[str, object], field: str) -> None:
    import re

    member = value[field]
    if not isinstance(member, str) or re.fullmatch(r"[0-9a-f]{64}", member) is None:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", f"{field} is invalid")


def _case_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_CASES:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case_ids are invalid")
    result = tuple(_text(item, "case_id") for item in value)
    if len(set(result)) != len(result):
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "case_ids are duplicated")
    return result


def _elapsed_ms(started: str, ended: str) -> int:
    start = datetime.strptime(started, "%Y-%m-%dT%H:%M:%S.%fZ")
    end = datetime.strptime(ended, "%Y-%m-%dT%H:%M:%S.%fZ")
    return max(0, int((end - start).total_seconds() * 1000))


def _expected_state(cases: Sequence[TestCaseResult]) -> str:
    states = {case.state for case in cases}
    if states & {"error", "timeout"}:
        return "error"
    if "failed" in states:
        return "failed"
    return "passed"


def assemble_test_run(
    inventory: TestInventory,
    events: Sequence[tuple[int, str, Mapping[str, object]]],
    *,
    exit_code: int | None,
    raw_events: ArtifactRef,
    transport: str | None,
    stdout: ArtifactRef | None = None,
    stderr: ArtifactRef | None = None,
) -> TestRunManifest:
    """Apply a complete, sequence-numbered event stream to a frozen inventory."""
    if (
        not isinstance(inventory, TestInventory)
        or not isinstance(events, Sequence)
        or isinstance(events, (str, bytes))
        or not events
    ):
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "event stream is empty or unbound")
    if not isinstance(raw_events, ArtifactRef):
        raise protocol_error("TEST_PROTOCOL_INVALID", "raw_events must be an ArtifactRef")
    if exit_code is not None and (type(exit_code) is not int):
        raise protocol_error("TEST_EXIT_MISMATCH", "process exit code is invalid")
    started_cases: dict[str, str] = {}
    results: dict[str, TestCaseResult] = {}
    run_start: dict[str, object] | None = None
    run_end: dict[str, object] | None = None
    terminal_seen = False
    for expected_sequence, event in enumerate(events):
        if not isinstance(event, tuple) or len(event) != 3:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "event record is invalid")
        sequence, kind, payload = event
        if (
            type(sequence) is not int
            or not 0 <= sequence <= 0xFFFFFFFF
            or sequence != expected_sequence
            or terminal_seen
        ):
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "event sequence is invalid")
        value = validate_event_payload(kind, payload)
        if kind == "run_start":
            if expected_sequence != 0 or run_start is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_start is duplicated or misplaced")
            selected = _case_ids(value["case_ids"])
            if any(case_id not in inventory.case_ids for case_id in selected):
                raise protocol_error("TEST_CASE_NOT_FOUND", "run_start names an undiscovered case")
            if value["inventory_digest"] != inventory.inventory_digest:
                raise protocol_error("TEST_INVENTORY_CHANGED", "run_start inventory digest changed")
            run_start = value
        elif kind == "case_start":
            if run_start is None or value["case_id"] not in cast(list[str], run_start["case_ids"]):
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case_start is not selected")
            case_id = cast(str, value["case_id"])
            if case_id in started_cases or case_id in results:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case_start is duplicated")
            started_cases[case_id] = cast(str, value["started_at_utc"])
        elif kind == "case_result":
            case_id = cast(str, value["case_id"])
            if case_id not in started_cases or case_id in results:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case terminal event is illegal")
            results[case_id] = TestCaseResult(
                case_id=case_id,
                state=cast(str, value["state"]),
                started_at_utc=started_cases[case_id],
                ended_at_utc=cast(str, value["ended_at_utc"]),
                duration_ms=cast(int, value["duration_ms"]),
                message=cast(str | None, value["message"]),
                stdout=_artifact(value["stdout"], "stdout"),
                stderr=_artifact(value["stderr"], "stderr"),
            )
        elif kind == "run_end":
            if run_start is None or run_end is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end is duplicated or premature")
            run_end = value
            terminal_seen = True
        elif kind in {"inventory", "log"}:
            if run_start is None or kind == "inventory":
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "event kind is invalid in a run stream")
    if run_start is None or run_end is None:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run stream lacks one terminal event")
    selected = cast(list[str], run_start["case_ids"])
    for case_id in selected:
        if case_id not in results:
            started = started_cases.get(case_id, cast(str, run_start["started_at_utc"]))
            results[case_id] = TestCaseResult(
                case_id, "error", started, cast(str, run_end["ended_at_utc"]),
                _elapsed_ms(started, cast(str, run_end["ended_at_utc"])),
                "case ended without a terminal result" if case_id in started_cases else "case did not start",
                None, None,
            )
    ordered = tuple(results[case_id] for case_id in inventory.case_ids if case_id in selected)
    expected_counts = {state: sum(case.state == state for case in ordered) for state in CASE_STATES}
    if run_end["counts"] != expected_counts:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end counts contradict cases")
    if (
        run_end["inventory_digest"] != inventory.inventory_digest
        or run_end["build_id"] != inventory.identity.build_id
        or run_end["elf_sha256"] != inventory.identity.elf_sha256
        or run_end["target_device"] != inventory.identity.target_device
        or run_end["event_stream_digest"] != raw_events.sha256
    ):
        raise protocol_error("TEST_IDENTITY_MISMATCH", "run_end identity binding is invalid")
    expected_state = _expected_state(ordered)
    if run_end["state"] != "cancelled" and run_end["state"] != expected_state:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end state contradicts cases")
    native_failure = run_end["state"] != "passed"
    if exit_code is not None and ((exit_code == 0) == native_failure):
        raise protocol_error("TEST_EXIT_MISMATCH", "process exit contradicts terminal events")
    return TestRunManifest(
        TEST_SCHEMA, cast(str, run_start["run_id"]), inventory.mode,
        cast(str, run_end["state"]), inventory.identity, transport, ordered,
        cast(str, run_start["started_at_utc"]), cast(str, run_end["ended_at_utc"]),
        cast(int, run_end["duration_ms"]), stdout, stderr, raw_events,
    )


def _v2_host_utc(anchor: str, monotonic_delta_ms: int) -> str:
    _utc(anchor, "started_at_utc")
    parsed = datetime.strptime(anchor, "%Y-%m-%dT%H:%M:%S.%fZ")
    return (parsed + timedelta(milliseconds=monotonic_delta_ms)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def assemble_target_v2_run(
    *,
    identity: EvidenceIdentity,
    run_id: str,
    started_at_utc: str,
    frames: Sequence[object],
    raw_events: ArtifactRef,
    transport: str | None,
    timeout_ms: int,
) -> TestRunManifest:
    """Bind target-owned v2 monotonic events to host-owned run facts.

    Target frames contain only case facts.  The host supplies identity, run ID,
    UTC anchor, transport, and the exact retained raw artifact before the
    existing TestRun model is constructed.
    """
    if (
        not isinstance(identity, EvidenceIdentity)
        or not isinstance(frames, Sequence)
        or isinstance(frames, (str, bytes))
        or not frames
        or not isinstance(raw_events, ArtifactRef)
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= 300_000
    ):
        raise protocol_error("TEST_PROTOCOL_INVALID", "v2 host assembly binding is invalid")
    _text(run_id, "run_id")
    _utc(started_at_utc, "started_at_utc")

    try:
        from .target import TargetFrame, TargetFrameDecoder

        target_frames = tuple(frames)
        if not all(isinstance(frame, TargetFrame) and frame.version == 2 for frame in target_frames):
            raise ValueError("target frames must be version 2")
        stream = b"".join(frame.raw_bytes for frame in target_frames)
        decoder = TargetFrameDecoder(expected_version=2)
        decoded = decoder.feed(stream)
        decoder.finish()
        if len(decoded) != len(target_frames) or any(
            left.raw_bytes != right.raw_bytes for left, right in zip(decoded, target_frames)
        ):
            raise ValueError("target frame stream does not match exact frame bytes")
    except TestProtocolError:
        raise
    except Exception as error:
        raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "v2 target frames are invalid") from error

    if raw_events.sha256 != sha256(stream).hexdigest() or raw_events.size_bytes != len(stream):
        raise protocol_error("TEST_PROTOCOL_INVALID", "raw v2 target artifact does not match frame bytes")

    if target_frames[0].kind != 1:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 inventory must be first")
    if target_frames[-1].kind != 5:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 run_end must be terminal")
    if len(target_frames) < 3 or target_frames[1].kind != 2:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 run_start must follow inventory")

    inventory_payload = target_frames[0].payload
    run_start_payload = target_frames[1].payload
    case_ids = tuple(cast(Sequence[str], inventory_payload["case_ids"]))
    inventory_case_digest = cast(str, inventory_payload["case_inventory_digest"])
    if (
        run_start_payload["case_inventory_digest"] != inventory_case_digest
        or tuple(cast(Sequence[str], run_start_payload["case_ids"])) != case_ids
    ):
        raise protocol_error("TEST_INVENTORY_CHANGED", "v2 run_start inventory changed")

    inventory = TestInventory(
        mode="target",
        identity=identity,
        case_ids=case_ids,
        inventory_digest=calculate_inventory_digest("target", identity, case_ids),
        discovered_at_utc=started_at_utc,
    )

    anchor_ms = cast(int, run_start_payload["monotonic_ms"])
    terminal_payload = target_frames[-1].payload
    terminal_ms = cast(int, terminal_payload["monotonic_ms"])
    if terminal_ms - anchor_ms > timeout_ms:
        raise protocol_error("TEST_TIMEOUT", "v2 target monotonic delta exceeds timeout")
    expected_stream_digest = sha256(
        b"".join(frame.raw_bytes for frame in target_frames[:-1])
    ).hexdigest()
    if terminal_payload["event_stream_digest"] != expected_stream_digest:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 event stream digest is invalid")
    if terminal_payload["case_inventory_digest"] != inventory_case_digest:
        raise protocol_error("TEST_INVENTORY_CHANGED", "v2 run_end inventory changed")

    selected = set(inventory.case_ids)
    active_case: str | None = None
    started_cases: dict[str, int] = {}
    results: dict[str, TestCaseResult] = {}
    for frame in target_frames[2:-1]:
        payload = frame.payload
        if frame.kind == 3:
            case_id = cast(str, payload["case_id"])
            if active_case is not None or case_id not in selected or case_id in started_cases:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 case_start contradicts selected cases")
            active_case = case_id
            started_cases[case_id] = cast(int, payload["monotonic_ms"])
        elif frame.kind == 4:
            case_id = cast(str, payload["case_id"])
            state = cast(str, payload["state"])
            result_ms = cast(int, payload["monotonic_ms"])
            if active_case != case_id or case_id in results:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 case_result contradicts active case")
            case_start_ms = started_cases[case_id]
            if result_ms < case_start_ms:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 case duration is negative")
            results[case_id] = TestCaseResult(
                case_id=case_id,
                state=state,
                started_at_utc=_v2_host_utc(started_at_utc, case_start_ms - anchor_ms),
                ended_at_utc=_v2_host_utc(started_at_utc, result_ms - anchor_ms),
                duration_ms=result_ms - case_start_ms,
                message=cast(str | None, payload["message"]),
                stdout=None,
                stderr=None,
            )
            active_case = None
        elif frame.kind == 6:
            continue
        else:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 event kind is invalid in the run")
    if active_case is not None or set(results) != selected:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 run did not complete every case")

    ordered = tuple(results[case_id] for case_id in inventory.case_ids)
    expected_counts = {state: sum(case.state == state for case in ordered) for state in CASE_STATES}
    counts = terminal_payload["counts"]
    if not isinstance(counts, Mapping) or dict(counts) != expected_counts:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 run counts contradict case results")
    expected_state = _expected_state(ordered)
    terminal_state = cast(str, terminal_payload["state"])
    if terminal_state != "cancelled" and terminal_state != expected_state:
        raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "v2 run state contradicts case results")

    return TestRunManifest(
        TEST_SCHEMA,
        run_id,
        "target",
        terminal_state,
        identity,
        transport,
        ordered,
        started_at_utc,
        _v2_host_utc(started_at_utc, terminal_ms - anchor_ms),
        terminal_ms - anchor_ms,
        None,
        None,
        raw_events,
    )


assemble_v2_target_run = assemble_target_v2_run
