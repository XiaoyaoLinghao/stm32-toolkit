"""Bounded public assembly scenarios for the v1 and v2 test protocols."""

from __future__ import annotations

from hashlib import sha256

import pytest
import stm32_toolkit.testing.target as target_mod
from stm32_toolkit.testing.model import TestProtocolError as ProtocolError
from stm32_toolkit.testing.model import TestRunManifest as RunManifest
from stm32_toolkit.testing.protocol import assemble_target_v2_run, assemble_test_run
from test_target_protocol_v2 import (
    UTC_0 as V2_UTC_0,
)
from test_target_protocol_v2 import (
    _identity as _v2_identity,
)
from test_target_protocol_v2 import (
    _raw_artifact,
    _v2_payloads,
)
from test_testing_model import (
    HASH,
    UTC_0,
    UTC_1,
    UTC_2,
    _artifact,
    _inventory,
)

_V1_CASE_STATES = ("passed", "failed", "skipped", "error", "timeout")
_V1_CASE_IDS = ("zeta", "éclair")


def _v1_counts(**values: int) -> dict[str, int]:
    return {state: values.get(state, 0) for state in _V1_CASE_STATES}


def _v1_run_start(
    inventory, *, case_ids: list[str] | None = None, inventory_digest: str | None = None
) -> dict[str, object]:
    return {
        "run_id": "run-authority",
        "started_at_utc": UTC_0,
        "case_ids": list(_V1_CASE_IDS) if case_ids is None else case_ids,
        "inventory_digest": inventory.inventory_digest
        if inventory_digest is None
        else inventory_digest,
    }


def _v1_run_end(
    inventory, *, counts: dict[str, int], state: str = "passed"
) -> dict[str, object]:
    return {
        "state": state,
        "ended_at_utc": UTC_2,
        "duration_ms": 2_000,
        "inventory_digest": inventory.inventory_digest,
        "build_id": inventory.identity.build_id,
        "elf_sha256": inventory.identity.elf_sha256,
        "target_device": inventory.identity.target_device,
        "counts": counts,
        "event_stream_digest": HASH["raw-events"],
    }


def _v1_events(name: str, inventory):
    start = (0, "run_start", _v1_run_start(inventory, case_ids=["zeta"]))
    if name == "invalid-record":
        return (start, (1, "case_start"))
    if name == "duplicate-run-start":
        return (start, (1, "run_start", _v1_run_start(inventory, case_ids=["zeta"])))
    if name == "undiscovered-case":
        return ((0, "run_start", _v1_run_start(inventory, case_ids=["missing-case"])),)
    if name == "changed-start-inventory":
        return (
            (
                0,
                "run_start",
                _v1_run_start(
                    inventory, case_ids=["zeta"], inventory_digest=HASH["raw-events"]
                ),
            ),
        )
    if name == "duplicate-case-start":
        case_start = (1, "case_start", {"case_id": "zeta", "started_at_utc": UTC_0})
        return (start, case_start, (2, "case_start", {**case_start[2]}))
    if name == "premature-run-end":
        return (
            start,
            (
                1,
                "run_end",
                _v1_run_end(inventory, counts=_v1_counts(error=1), state="error"),
            ),
        )
    if name == "valid-log":
        return (
            (0, "run_start", _v1_run_start(inventory)),
            (1, "case_start", {"case_id": "zeta", "started_at_utc": UTC_0}),
            (
                2,
                "case_result",
                {
                    "case_id": "zeta",
                    "state": "passed",
                    "ended_at_utc": UTC_1,
                    "duration_ms": 1_000,
                    "message": None,
                    "stdout": _artifact("stdout"),
                    "stderr": None,
                },
            ),
            (3, "case_start", {"case_id": "éclair", "started_at_utc": UTC_1}),
            (
                4,
                "case_result",
                {
                    "case_id": "éclair",
                    "state": "passed",
                    "ended_at_utc": UTC_2,
                    "duration_ms": 1_000,
                    "message": None,
                    "stdout": None,
                    "stderr": _artifact("stderr"),
                },
            ),
            (5, "log", {"timestamp_utc": UTC_1, "stream": "stdout", "message": "line"}),
            (6, "run_end", _v1_run_end(inventory, counts=_v1_counts(passed=2))),
        )
    if name == "terminal-count-mismatch":
        return (
            start,
            (1, "case_start", {"case_id": "zeta", "started_at_utc": UTC_0}),
            (
                2,
                "case_result",
                {
                    "case_id": "zeta",
                    "state": "passed",
                    "ended_at_utc": UTC_1,
                    "duration_ms": 1_000,
                    "message": None,
                    "stdout": None,
                    "stderr": None,
                },
            ),
            (3, "run_end", _v1_run_end(inventory, counts=_v1_counts(error=1))),
        )
    raise AssertionError(f"unknown v1 scenario: {name}")


@pytest.mark.parametrize(
    ("name", "expected_code", "expected_message"),
    [
        pytest.param(
            "invalid-record",
            "TEST_EVENT_SEQUENCE_INVALID",
            "event record is invalid",
            id="record-shape",
        ),
        pytest.param(
            "duplicate-run-start",
            "TEST_EVENT_SEQUENCE_INVALID",
            "run_start is duplicated or misplaced",
            id="duplicate-run-start",
        ),
        pytest.param(
            "undiscovered-case",
            "TEST_CASE_NOT_FOUND",
            "run_start names an undiscovered case",
            id="unknown-case",
        ),
        pytest.param(
            "changed-start-inventory",
            "TEST_INVENTORY_CHANGED",
            "run_start inventory digest changed",
            id="changed-start-inventory",
        ),
        pytest.param(
            "duplicate-case-start",
            "TEST_EVENT_SEQUENCE_INVALID",
            "case_start is duplicated",
            id="duplicate-case-start",
        ),
        pytest.param(
            "premature-run-end",
            "TEST_EVENT_SEQUENCE_INVALID",
            "run_end is duplicated or premature",
            id="premature-run-end",
        ),
        pytest.param("valid-log", None, None, id="complete-log-success"),
        pytest.param(
            "terminal-count-mismatch",
            "TEST_EVENT_SEQUENCE_INVALID",
            "run_end counts contradict cases",
            id="terminal-count-mismatch",
        ),
    ],
)
def test_v1_public_assembly_authority(
    name: str, expected_code: str | None, expected_message: str | None
):
    """A frozen v1 inventory reaches each selected public assembly guard."""
    inventory = _inventory()
    events = _v1_events(name, inventory)

    if name == "valid-log":
        manifest = assemble_test_run(
            inventory,
            events,
            exit_code=0,
            raw_events=_artifact(),
            transport="rtt",
            stdout=_artifact("stdout"),
            stderr=_artifact("stderr"),
        )
        assert isinstance(manifest, RunManifest)
        assert manifest.schema == "stm32-test/1"
        assert manifest.run_id == "run-authority"
        assert manifest.mode == "host"
        assert manifest.state == "passed"
        assert manifest.identity == inventory.identity
        assert manifest.transport == "rtt"
        assert manifest.started_at_utc == UTC_0
        assert manifest.ended_at_utc == UTC_2
        assert manifest.duration_ms == 2_000
        assert [(case.case_id, case.state) for case in manifest.cases] == [
            ("zeta", "passed"),
            ("éclair", "passed"),
        ]
        assert manifest.cases[0].stdout == _artifact("stdout")
        assert manifest.cases[1].stderr == _artifact("stderr")
        assert manifest.stdout == _artifact("stdout")
        assert manifest.stderr == _artifact("stderr")
        assert manifest.raw_events == _artifact()
        return

    with pytest.raises(ProtocolError) as caught:
        assemble_test_run(
            inventory,
            events,
            exit_code=None,
            raw_events=_artifact(),
            transport="rtt",
        )
    assert caught.value.code == expected_code
    assert caught.value.message == expected_message


def _encoded_v2_stream(
    order: tuple[int, ...], *, terminal_changes: dict[str, object] | None = None
) -> tuple[tuple[target_mod.TargetFrame, ...], bytes]:
    """Encode and decode a fresh v2 stream while keeping its raw bytes authoritative."""
    assert order[-1] == 5
    payloads = _v2_payloads()
    if terminal_changes:
        payloads[5].update(terminal_changes)
    raw_frames = []
    for sequence, kind in enumerate(order[:-1]):
        payload = dict(payloads[kind])
        payload["monotonic_ms"] = sequence * 10
        raw_frames.append(target_mod.encode_frame(kind, sequence, payload, version=2))
    terminal = dict(payloads[5])
    terminal["monotonic_ms"] = len(raw_frames) * 10
    terminal["event_stream_digest"] = sha256(b"".join(raw_frames)).hexdigest()
    raw_frames.append(target_mod.encode_frame(5, len(raw_frames), terminal, version=2))
    stream = b"".join(raw_frames)
    decoder = target_mod.TargetFrameDecoder(expected_version=2)
    frames = decoder.feed(stream)
    decoder.finish()
    assert b"".join(frame.raw_bytes for frame in frames) == stream
    return frames, stream


def _assemble_v2_public(
    frames: tuple[target_mod.TargetFrame, ...], stream: bytes, *, timeout_ms: int
):
    return assemble_target_v2_run(
        identity=_v2_identity(),
        run_id="run-v2",
        started_at_utc=V2_UTC_0,
        frames=frames,
        raw_events=_raw_artifact(stream),
        transport="memory-mailbox",
        timeout_ms=timeout_ms,
    )


@pytest.mark.parametrize(
    (
        "name",
        "order",
        "timeout_ms",
        "terminal_changes",
        "expected_code",
        "expected_message",
    ),
    [
        pytest.param(
            "invalid-host-timeout",
            (1, 2, 3, 4, 6, 5),
            0,
            None,
            "TEST_PROTOCOL_INVALID",
            "v2 host assembly binding is invalid",
            id="invalid-host-timeout",
        ),
        pytest.param(
            "inventory-not-first",
            (2, 1, 3, 4, 6, 5),
            3_000,
            None,
            "TEST_EVENT_SEQUENCE_INVALID",
            "v2 inventory must be first",
            id="inventory-not-first",
        ),
        pytest.param(
            "run-start-not-second",
            (1, 3, 2, 4, 6, 5),
            3_000,
            None,
            "TEST_EVENT_SEQUENCE_INVALID",
            "v2 run_start must follow inventory",
            id="run-start-not-second",
        ),
        pytest.param(
            "terminal-inventory-mismatch",
            (1, 2, 3, 4, 6, 5),
            3_000,
            {"case_inventory_digest": "0" * 64},
            "TEST_INVENTORY_CHANGED",
            "v2 run_end inventory changed",
            id="terminal-inventory-mismatch",
        ),
        pytest.param(
            "consecutive-case-starts",
            (1, 2, 3, 3, 4, 6, 5),
            3_000,
            None,
            "TEST_EVENT_SEQUENCE_INVALID",
            "v2 case_start contradicts selected cases",
            id="consecutive-case-starts",
        ),
        pytest.param(
            "result-without-active-case",
            (1, 2, 4, 3, 6, 5),
            3_000,
            None,
            "TEST_EVENT_SEQUENCE_INVALID",
            "v2 case_result contradicts active case",
            id="result-without-active-case",
        ),
        pytest.param(
            "invalid-middle-kind",
            (1, 2, 1, 3, 4, 6, 5),
            3_000,
            None,
            "TEST_EVENT_SEQUENCE_INVALID",
            "v2 event kind is invalid in the run",
            id="invalid-middle-kind",
        ),
    ],
)
def test_v2_public_assembly_authority(
    name: str,
    order: tuple[int, ...],
    timeout_ms: int,
    terminal_changes: dict[str, object] | None,
    expected_code: str,
    expected_message: str,
):
    """Fresh decoder-derived v2 bytes reach each selected public assembly guard."""
    del name
    frames, stream = _encoded_v2_stream(order, terminal_changes=terminal_changes)
    assert len(frames) == len(order)

    with pytest.raises(ProtocolError) as caught:
        _assemble_v2_public(frames, stream, timeout_ms=timeout_ms)
    assert caught.value.code == expected_code
    assert caught.value.message == expected_message
