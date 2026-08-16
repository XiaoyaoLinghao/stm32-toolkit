"""Closed event payload validation and run assembly."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence, cast

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity

from .model import (
    CASE_STATES,
    MAX_CASES,
    MAX_DURATION_MS,
    TEST_SCHEMA,
    TestCaseResult,
    TestInventory,
    TestProtocolError,
    TestRunManifest,
    protocol_error,
)


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


def validate_event_payload(kind: str, payload: object) -> dict[str, object]:
    """Validate one decoded JSON payload against its exact event-kind shape."""
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
