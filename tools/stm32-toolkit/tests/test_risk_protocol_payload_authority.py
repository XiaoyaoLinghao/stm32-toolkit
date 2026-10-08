from __future__ import annotations

from hashlib import sha256

import pytest
from test_target_protocol_v2 import (
    CASE_ID,
    H0,
    _assemble_v2,
    _identity,
    _raw_artifact,
    _v2_payloads,
    _v2_stream,
)

import stm32_toolkit.testing.protocol as protocol_mod
import stm32_toolkit.testing.target as target_mod
from stm32_toolkit.testing.model import (
    TestProtocolError as ProtocolError,
)
from stm32_toolkit.testing.model import (
    TestRunManifest as RunManifest,
)


@pytest.mark.parametrize(
    (
        "variant",
        "kind",
        "sequence",
        "changes",
        "expected_code",
        "expected_message",
    ),
    (
        pytest.param(
            "case-ids-empty",
            1,
            0,
            {"case_ids": []},
            "TEST_EVENT_PAYLOAD_INVALID",
            "case_ids are invalid",
            id="case-ids-empty",
        ),
        pytest.param(
            "case-ids-duplicate",
            1,
            0,
            {"case_ids": [CASE_ID, CASE_ID]},
            "TEST_EVENT_PAYLOAD_INVALID",
            "case_ids are duplicated",
            id="case-ids-duplicate",
        ),
        pytest.param(
            "case-ids-unsorted",
            1,
            0,
            {"case_ids": ["z-case", "a-case"]},
            "TEST_EVENT_PAYLOAD_INVALID",
            "case_ids are not in UTF-8 byte order",
            id="case-ids-unsorted",
        ),
        pytest.param(
            "inventory-mode-host",
            1,
            0,
            {"mode": "host"},
            "TEST_EVENT_PAYLOAD_INVALID",
            "inventory mode is invalid",
            id="inventory-mode-host",
        ),
        pytest.param(
            "inventory-digest-wrong",
            1,
            0,
            {"case_inventory_digest": H0},
            "TEST_INVENTORY_CHANGED",
            "case inventory digest contradicts case IDs",
            id="inventory-digest-wrong",
        ),
        pytest.param(
            "run-start-digest-wrong",
            2,
            1,
            {"case_inventory_digest": H0},
            "TEST_INVENTORY_CHANGED",
            "case inventory digest contradicts case IDs",
            id="run-start-digest-wrong",
        ),
        pytest.param(
            "case-result-state-invalid",
            4,
            3,
            {"state": "bogus"},
            "TEST_EVENT_PAYLOAD_INVALID",
            "case state is invalid",
            id="case-result-state-invalid",
        ),
        pytest.param(
            "terminal-state-invalid",
            5,
            5,
            {"state": "running"},
            "TEST_EVENT_PAYLOAD_INVALID",
            "terminal run state is invalid",
            id="terminal-state-invalid",
        ),
        pytest.param(
            "terminal-counts-keys-invalid",
            5,
            5,
            {"counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0}},
            "TEST_EVENT_PAYLOAD_INVALID",
            "run counts are invalid",
            id="terminal-counts-keys-invalid",
        ),
        pytest.param(
            "log-stream-invalid",
            6,
            4,
            {"stream": "serial"},
            "TEST_EVENT_PAYLOAD_INVALID",
            "log stream is invalid",
            id="log-stream-invalid",
        ),
        pytest.param(
            "case-result-message-success",
            None,
            None,
            {"message": "heartbeat passed"},
            None,
            None,
            id="case-result-message-success",
        ),
    ),
)
def test_v2_public_encode_frame_enforces_payload_authority(
    variant: str,
    kind: int | None,
    sequence: int | None,
    changes: dict[str, object],
    expected_code: str | None,
    expected_message: str | None,
) -> None:
    if kind is None:
        frames, stream = _v2_stream(mutate={4: changes})
        manifest = _assemble_v2(frames=frames, stream=stream)

        assert isinstance(manifest, RunManifest)
        assert manifest.identity == _identity()
        assert manifest.state == "passed"
        assert len(manifest.cases) == 1
        assert manifest.cases[0].case_id == CASE_ID
        assert manifest.cases[0].state == "passed"
        assert manifest.cases[0].message == "heartbeat passed"
        assert manifest.raw_events == _raw_artifact(stream)
        assert manifest.raw_events.sha256 == sha256(stream).hexdigest()
        terminal = next(frame for frame in frames if frame.kind == 5)
        nonterminal_bytes = b"".join(
            frame.raw_bytes for frame in frames if frame.kind != terminal.kind
        )
        assert (
            terminal.payload["event_stream_digest"]
            == sha256(nonterminal_bytes).hexdigest()
        )
        assert variant == "case-result-message-success"
        return

    payload = _v2_payloads()[kind]
    payload.update(changes)

    with pytest.raises(ProtocolError) as caught:
        target_mod.encode_frame(kind, sequence, payload, version=2)

    assert caught.value.code == expected_code
    assert caught.value.message == expected_message


@pytest.mark.parametrize(
    ("variant", "case_ids", "expected_code", "expected_message"),
    (
        pytest.param(
            "string",
            "not-a-sequence",
            "TEST_PROTOCOL_INVALID",
            "case_ids must be a sequence",
            id="string",
        ),
        pytest.param(
            "empty",
            [],
            "TEST_NO_CASES",
            "test inventory is empty",
            id="empty",
        ),
        pytest.param(
            "duplicate",
            [CASE_ID, CASE_ID],
            "TEST_DUPLICATE_CASE",
            "case IDs must be unique",
            id="duplicate",
        ),
    ),
)
def test_public_case_inventory_digest_rejects_invalid_declarations(
    variant: str,
    case_ids: object,
    expected_code: str,
    expected_message: str,
) -> None:
    with pytest.raises(ProtocolError) as caught:
        protocol_mod.calculate_case_inventory_digest(case_ids)

    assert caught.value.code == expected_code
    assert caught.value.message == expected_message
    assert variant in {"string", "empty", "duplicate"}
