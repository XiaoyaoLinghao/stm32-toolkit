from __future__ import annotations

from hashlib import sha256
import json
import struct
import zlib

import pytest

import stm32_toolkit.testing as testing_api
from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity
import stm32_toolkit.testing.protocol as protocol_mod
import stm32_toolkit.testing.target as target_mod
from stm32_toolkit.testing.model import (
    TestProtocolError as ProtocolError,
    TestRunManifest as RunManifest,
)


H0 = "0" * 64
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
UTC_0 = "2026-08-25T00:00:00.000000Z"
V2_CASE_DIGEST = "966a489bdde16562885cc4ac3c3e2b9b9bde0b477f9c06aae25f4916be52c2b5"
CASE_ID = "d4-heartbeat"


def _identity() -> EvidenceIdentity:
    return EvidenceIdentity(
        workspace_id=H0,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="vs10a-v2",
        build_id=H1,
        elf_sha256=H2,
        target_device="stm32:F429ZGT6",
        input_snapshot_sha256=H3,
        git_commit="a" * 40,
        git_dirty=False,
    )


def _v2_payloads() -> dict[int, dict[str, object]]:
    return {
        1: {
            "mode": "target",
            "case_ids": [CASE_ID],
            "case_inventory_digest": V2_CASE_DIGEST,
            "monotonic_ms": 0,
        },
        2: {
            "case_ids": [CASE_ID],
            "case_inventory_digest": V2_CASE_DIGEST,
            "monotonic_ms": 10,
        },
        3: {"case_id": CASE_ID, "monotonic_ms": 20},
        4: {
            "case_id": CASE_ID,
            "state": "passed",
            "monotonic_ms": 2220,
            "message": None,
        },
        5: {
            "state": "passed",
            "case_inventory_digest": V2_CASE_DIGEST,
            "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
            "event_stream_digest": H3,
            "monotonic_ms": 2230,
        },
        6: {"stream": "stdout", "message": "heartbeat", "monotonic_ms": 2221},
    }


def _manual_frame(kind: int, sequence: int, payload: dict[str, object], *, version: int = 2, flags: int = 0) -> bytes:
    body = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    header = struct.pack("<4sBBHII", b"ST32", version, kind, flags, sequence, len(body))
    return header + body + struct.pack("<I", zlib.crc32(header + body) & 0xFFFFFFFF)


def _assert_code(code: str, operation) -> None:
    with pytest.raises(ProtocolError) as caught:
        operation()
    assert caught.value.code == code


def _v2_stream(
    *,
    mutate: dict[int, dict[str, object]] | None = None,
    version: int = 2,
) -> tuple[tuple[target_mod.TargetFrame, ...], bytes]:
    payloads = _v2_payloads()
    for kind, changes in (mutate or {}).items():
        payloads[kind].update(changes)
    nonterminal = [1, 2, 3, 4, 6]
    raw_frames = [
        target_mod.encode_frame(
            kind, sequence, payloads[kind], version=version
        )
        for sequence, kind in enumerate(nonterminal)
    ]
    if not (mutate and 5 in mutate and "event_stream_digest" in mutate[5]):
        payloads[5]["event_stream_digest"] = sha256(b"".join(raw_frames)).hexdigest()
    raw_frames.append(target_mod.encode_frame(5, len(raw_frames), payloads[5], version=version))
    stream = b"".join(raw_frames)
    decoder = target_mod.TargetFrameDecoder(expected_version=version)
    frames = decoder.feed(stream)
    decoder.finish()
    return frames, stream


def _raw_artifact(stream: bytes, *, digest: str | None = None) -> ArtifactRef:
    value = sha256(stream).hexdigest() if digest is None else digest
    return ArtifactRef(
        sha256=value,
        size_bytes=len(stream),
        relative_path="objects/v2/target-stream.bin",
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )


def _assemble_v2(
    *,
    frames: tuple[target_mod.TargetFrame, ...],
    stream: bytes,
    timeout_ms: int = 3_000,
    identity: EvidenceIdentity | None = None,
    raw_events: ArtifactRef | None = None,
):
    assemble = getattr(protocol_mod, "assemble_target_v2_run", None)
    assert callable(assemble)
    return assemble(
        identity=_identity() if identity is None else identity,
        run_id="run-v2",
        started_at_utc=UTC_0,
        frames=frames,
        raw_events=_raw_artifact(stream) if raw_events is None else raw_events,
        transport="memory-mailbox",
        timeout_ms=timeout_ms,
    )


@pytest.mark.parametrize("kind", range(1, 7))
def test_v2_encoder_matches_manual_little_endian_bytes_for_every_kind(kind: int):
    payload = _v2_payloads()[kind]

    encoded = target_mod.encode_frame(kind, 7, payload, version=2)

    assert encoded == _manual_frame(kind, 7, payload)


def test_v2_case_inventory_digest_uses_the_frozen_one_case_preimage():
    calculate = getattr(protocol_mod, "calculate_case_inventory_digest", None)
    assert callable(calculate)

    assert calculate([CASE_ID]) == V2_CASE_DIGEST


def test_v2_case_inventory_digest_canonicalizes_utf8_order_and_bounds_input():
    calculate = protocol_mod.calculate_case_inventory_digest

    assert calculate(["z-case", "a-case"]) == calculate(["a-case", "z-case"])
    with pytest.raises(ProtocolError):
        calculate([f"case-{index}" for index in range(100_001)])


def test_v2_protocol_helpers_are_available_from_testing_public_api():
    assert testing_api.TARGET_FRAME_V1 == "stm32-target-frame/1"
    assert testing_api.TARGET_FRAME_V2 == "stm32-target-frame/2"
    assert testing_api.calculate_case_inventory_digest([CASE_ID]) == V2_CASE_DIGEST
    assert callable(testing_api.assemble_target_v2_run)


@pytest.mark.parametrize("kind", range(1, 7))
def test_v2_payload_validator_accepts_only_the_frozen_shape(kind: int):
    validate = protocol_mod.validate_event_payload

    value = validate(
        {1: "inventory", 2: "run_start", 3: "case_start", 4: "case_result", 5: "run_end", 6: "log"}[kind],
        _v2_payloads()[kind],
        frame_version=2,
    )

    assert value == _v2_payloads()[kind]


def test_v2_decoder_preserves_version_and_supports_byte_fragmentation():
    _, stream = _v2_stream()
    decoder = target_mod.TargetFrameDecoder(expected_version=2)
    frames = []
    for byte in stream:
        frames.extend(decoder.feed(bytes((byte,))))
    decoder.finish()

    assert [frame.version for frame in frames] == [2] * 6
    assert b"".join(frame.raw_bytes for frame in frames) == stream


def test_v2_decoder_rejects_crc_oversize_invalid_utf8_and_duplicate_keys():
    corrupt = bytearray(target_mod.encode_frame(1, 0, _v2_payloads()[1], version=2))
    corrupt[-1] ^= 0x80
    decoder = target_mod.TargetFrameDecoder(expected_version=2)
    decoder.feed(bytes(corrupt))
    _assert_code("TEST_FRAME_CRC_INVALID", decoder.finish)

    oversized_header = struct.pack("<4sBBHII", b"ST32", 2, 1, 0, 0, 16 * 1024 + 1)
    _assert_code("TEST_FRAME_TOO_LARGE", lambda: target_mod.TargetFrameDecoder(expected_version=2).feed(oversized_header))

    def raw(body: bytes) -> bytes:
        header = struct.pack("<4sBBHII", b"ST32", 2, 1, 0, 0, len(body))
        return header + body + struct.pack("<I", zlib.crc32(header + body) & 0xFFFFFFFF)

    for body in (b"\xff", b'{"mode":"target","mode":"target"}'):
        _assert_code("TEST_PROTOCOL_INVALID", lambda body=body: target_mod.TargetFrameDecoder(expected_version=2).feed(raw(body)))


def test_v2_decoder_rejects_mixed_versions_nonzero_flags_and_sequence_gaps():
    v2 = target_mod.encode_frame(1, 0, _v2_payloads()[1], version=2)
    v1_log = {
        "timestamp_utc": UTC_0,
        "stream": "stdout",
        "message": "legacy",
    }
    v1 = target_mod.encode_frame(6, 1, v1_log)
    decoder = target_mod.TargetFrameDecoder(expected_version=2)
    decoder.feed(v2 + v1)
    _assert_code("TEST_FRAME_VERSION_INVALID", decoder.finish)

    flagged = _manual_frame(1, 0, _v2_payloads()[1], flags=1)
    _assert_code("TEST_PROTOCOL_INVALID", lambda: target_mod.TargetFrameDecoder(expected_version=2).feed(flagged))

    gap = target_mod.encode_frame(1, 1, _v2_payloads()[1], version=2)
    _assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: target_mod.TargetFrameDecoder(expected_version=2).feed(gap))


def test_v2_decoder_rejects_monotonic_counter_rollback():
    first_payload = _v2_payloads()[1]
    first_payload["monotonic_ms"] = 10
    first = target_mod.encode_frame(1, 0, first_payload, version=2)
    second_payload = _v2_payloads()[2]
    second_payload["monotonic_ms"] = 0
    second = target_mod.encode_frame(2, 1, second_payload, version=2)
    decoder = target_mod.TargetFrameDecoder(expected_version=2)
    decoder.feed(first)
    _assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: decoder.feed(second))


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        (1, "identity", {}),
        (1, "discovered_at_utc", UTC_0),
        (2, "run_id", "target-supplied"),
        (2, "started_at_utc", UTC_0),
        (3, "started_at_utc", UTC_0),
        (4, "ended_at_utc", UTC_0),
        (4, "stdout", None),
        (5, "target_device", "target-supplied"),
        (6, "timestamp_utc", UTC_0),
    ],
)
def test_v2_payloads_reject_v1_host_authority_and_artifact_fields(
    kind: int, field: str, value: object
):
    payload = _v2_payloads()[kind]
    payload[field] = value
    validate = protocol_mod.validate_event_payload
    kind_name = {1: "inventory", 2: "run_start", 3: "case_start", 4: "case_result", 5: "run_end", 6: "log"}[kind]

    _assert_code("TEST_EVENT_PAYLOAD_INVALID", lambda: validate(kind_name, payload, frame_version=2))


def test_v2_host_bound_assembly_returns_existing_manifest_and_case_models():
    frames, stream = _v2_stream()

    manifest = _assemble_v2(frames=frames, stream=stream)

    assert isinstance(manifest, RunManifest)
    assert manifest.schema == "stm32-test/1"
    assert manifest.run_id == "run-v2"
    assert manifest.identity == _identity()
    assert manifest.started_at_utc == UTC_0
    assert manifest.ended_at_utc == "2026-08-25T00:00:02.220000Z"
    assert manifest.duration_ms == 2_220
    assert manifest.state == "passed"
    assert len(manifest.cases) == 1
    assert manifest.cases[0].case_id == CASE_ID
    assert manifest.cases[0].started_at_utc == "2026-08-25T00:00:00.010000Z"
    assert manifest.cases[0].ended_at_utc == "2026-08-25T00:00:02.210000Z"
    assert manifest.cases[0].duration_ms == 2_200
    assert manifest.stdout is None and manifest.stderr is None


def test_v2_assembly_rejects_timeout_inventory_count_state_and_raw_digest_contradictions():
    frames, stream = _v2_stream()
    _assert_code(
        "TEST_TIMEOUT",
        lambda: _assemble_v2(frames=frames, stream=stream, timeout_ms=1_000),
    )

    changed_frames, changed_stream = _v2_stream(
        mutate={
            2: {
                "case_ids": ["other-case"],
                "case_inventory_digest": protocol_mod.calculate_case_inventory_digest(["other-case"]),
            }
        }
    )
    _assert_code(
        "TEST_INVENTORY_CHANGED",
        lambda: _assemble_v2(frames=changed_frames, stream=changed_stream),
    )

    bad_counts, bad_count_stream = _v2_stream(
        mutate={5: {"counts": {"passed": 0, "failed": 1, "skipped": 0, "error": 0, "timeout": 0}}}
    )
    _assert_code(
        "TEST_EVENT_SEQUENCE_INVALID",
        lambda: _assemble_v2(frames=bad_counts, stream=bad_count_stream),
    )

    bad_state, bad_state_stream = _v2_stream(mutate={5: {"state": "failed"}})
    _assert_code(
        "TEST_EVENT_SEQUENCE_INVALID",
        lambda: _assemble_v2(frames=bad_state, stream=bad_state_stream),
    )

    bad_raw = _raw_artifact(stream, digest=H0)
    _assert_code(
        "TEST_PROTOCOL_INVALID",
        lambda: _assemble_v2(frames=frames, stream=stream, raw_events=bad_raw),
    )


def test_v2_assembly_rejects_terminal_event_stream_digest_and_host_identity_injection():
    frames, stream = _v2_stream()
    terminal = frames[-1].payload
    assert terminal["event_stream_digest"] == sha256(
        b"".join(frame.raw_bytes for frame in frames[:-1])
    ).hexdigest()

    bad_terminal, bad_stream = _v2_stream(mutate={5: {"event_stream_digest": H0}})
    _assert_code(
        "TEST_EVENT_SEQUENCE_INVALID",
        lambda: _assemble_v2(frames=bad_terminal, stream=bad_stream),
    )

    injected = _v2_payloads()[1]
    injected["host_identity"] = _identity().to_dict()
    _assert_code(
        "TEST_EVENT_PAYLOAD_INVALID",
        lambda: protocol_mod.validate_event_payload("inventory", injected, frame_version=2),
    )


def test_v1_encoder_and_decoder_defaults_remain_legacy_version_one():
    payload = {
        "timestamp_utc": UTC_0,
        "stream": "stdout",
        "message": "legacy",
    }
    expected = _manual_frame(6, 0, payload, version=1)

    encoded = target_mod.encode_frame(6, 0, payload)
    frame = target_mod.TargetFrameDecoder().feed(encoded)[0]

    assert encoded == expected
    assert frame.version == 1
