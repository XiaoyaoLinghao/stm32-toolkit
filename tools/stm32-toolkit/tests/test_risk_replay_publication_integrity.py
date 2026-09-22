"""Public replay-input and durable-publication integrity journeys.

The cases in this file keep the public loader, publisher, and repository guards
live.  Invalid bytes are prepared as ordinary files, while recovery uses the
same public fixture and publication entry points as a caller would use.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import test_target_replay_publication as target_replay_tests
from stm32_toolkit.testing import (
    TargetReplayError,
    calculate_replay_id,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)

FIXTURES = target_replay_tests.FIXTURES


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _descriptor_bytes(base: dict[str, object], **updates: object) -> bytes:
    candidate = dict(base)
    candidate.update(updates)
    candidate["replay_id"] = calculate_replay_id(candidate)
    return canonical_replay_json_bytes(candidate)


def _replay_input_cases(
    descriptor: dict[str, object],
    canonical_descriptor: bytes,
    stream_text: bytes,
    stream_bytes: bytes,
) -> tuple[tuple[str, bytes, bytes, dict[str, int], str, str], ...]:
    """Return ordinary file inputs and their exact public refusal contract."""

    invalid_descriptor = (
        (
            "schema-invalid",
            _descriptor_bytes(descriptor, schema="stm32tk-target-replay/0"),
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "schema must be stm32tk-target-replay/1",
        ),
        (
            "role-invalid",
            _descriptor_bytes(descriptor, scenario_role="not-a-role"),
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "scenario_role is invalid",
        ),
        (
            "source-invalid",
            _descriptor_bytes(descriptor, source="untrusted-source"),
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "source must be toolkit-generated-protocol-replay",
        ),
        (
            "stream-format-invalid",
            _descriptor_bytes(descriptor, stream_format="not-a-target-frame"),
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "stream_format must be stm32-target-frame/1",
        ),
        (
            "terminal-type-invalid",
            _descriptor_bytes(descriptor, expected_terminal_state="aborted"),
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "expected_terminal_state is invalid",
        ),
        (
            "descriptor-bom",
            b"\xef\xbb\xbf" + canonical_descriptor,
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "descriptor JSON must not include a BOM",
        ),
        (
            "descriptor-duplicate-key",
            b'{"schema":"stm32tk-target-replay/1","schema":"stm32tk-target-replay/1"}',
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "descriptor JSON has duplicate keys",
        ),
        (
            "descriptor-noncanonical",
            canonical_descriptor + b" ",
            stream_text,
            {},
            "TEST_REPLAY_INVALID",
            "descriptor JSON is not canonical",
        ),
        (
            "hex-nonhex",
            canonical_descriptor,
            b"00g0",
            {},
            "TEST_REPLAY_FIXTURE_INVALID",
            "hex stream contains a non-hex character",
        ),
        (
            "hex-empty",
            canonical_descriptor,
            b"",
            {},
            "TEST_REPLAY_FIXTURE_INVALID",
            "hex stream must be non-empty normalized lowercase hex",
        ),
        (
            "hex-size-limit",
            canonical_descriptor,
            b"0000",
            {"max_stream_bytes": 1},
            "TEST_REPLAY_FIXTURE_LIMIT",
            "decoded hex stream exceeds the replay bound",
        ),
    )

    changed = bytearray(stream_bytes)
    changed[0] ^= 0x01
    integrity = (
        "stream-digest-mismatch",
        canonical_descriptor,
        bytes(changed).hex().encode("ascii"),
        {},
        "TEST_REPLAY_INTEGRITY",
        "stream SHA-256 contradicts its descriptor",
    )
    terminal_mismatch = (
        "terminal-state-mismatch",
        _descriptor_bytes(
            descriptor,
            scenario_role="fixed-after",
            expected_terminal_state="passed",
        ),
        stream_text,
        {},
        "TEST_REPLAY_INTEGRITY",
        "stream terminal state contradicts its descriptor",
    )
    return invalid_descriptor + (integrity, terminal_mismatch)


def test_public_replay_inputs_refuse_and_restore(tmp_path: Path):
    """Malformed public replay inputs fail closed and restore the valid loader contract."""

    fixture = load_target_replay_fixture(
        FIXTURES / "failed-before.json", FIXTURES / "failed-before.hex"
    )
    descriptor = fixture.descriptor.to_dict()
    canonical_descriptor = canonical_replay_json_bytes(descriptor)
    stream_text = (FIXTURES / "failed-before.hex").read_bytes()

    for label, descriptor_payload, stream_payload, kwargs, code, message in _replay_input_cases(
        descriptor, canonical_descriptor, stream_text, fixture.stream_bytes
    ):
        case_root = tmp_path / "replay-inputs" / label
        case_root.mkdir(parents=True)
        descriptor_path = case_root / f"{label}.json"
        stream_path = case_root / f"{label}.hex"
        descriptor_path.write_bytes(descriptor_payload)
        stream_path.write_bytes(stream_payload)
        before = _tree_bytes(case_root)

        with pytest.raises(TargetReplayError) as failure:
            load_target_replay_fixture(descriptor_path, stream_path, **kwargs)
        assert failure.value.code == code
        assert failure.value.message == message
        assert _tree_bytes(case_root) == before

        descriptor_path.write_bytes(canonical_descriptor)
        stream_path.write_bytes(stream_text)
        restored = load_target_replay_fixture(descriptor_path, stream_path)
        assert restored == fixture
        assert _tree_bytes(case_root) == {
            descriptor_path.name: canonical_descriptor,
            stream_path.name: stream_text,
        }
