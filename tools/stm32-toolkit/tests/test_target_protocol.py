from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import random
import struct
from types import MappingProxyType
import zlib

import pytest

from stm32_toolkit.testing.model import (
    EVENT_KINDS,
    MAX_FRAME_PAYLOAD_BYTES,
    MAX_RUN_STREAM_BYTES,
    TestProtocolError as ProtocolError,
)
from stm32_toolkit.testing.target import (
    FRAME_MAGIC,
    FRAME_VERSION,
    TargetFrame,
    TargetFrameDecoder,
    TargetRunBinding,
    TargetRunValidator,
    encode_frame,
)


FIXTURES = Path(__file__).parent / "fixtures" / "target-streams"
ATTRIBUTES = Path(__file__).parents[3] / ".gitattributes"
H0 = "0" * 64
H1 = "1" * 64
H2 = "2" * 64
TARGET = "stm32:fixture"
UTC_0 = "2026-08-16T00:00:00.000000Z"
UTC_1 = "2026-08-16T00:00:01.000000Z"


def frozen_schema_payloads() -> dict[int, dict[str, object]]:
    identity = {
        "workspace_id": H0,
        "project_id": "123e4567-e89b-42d3-a456-426614174000",
        "session_id": "session-0601-t08",
        "build_id": H1,
        "elf_sha256": H2,
        "target_device": TARGET,
        "input_snapshot_sha256": "3" * 64,
        "git_commit": "a" * 40,
        "git_dirty": False,
    }
    return {
        1: {"mode": "target", "identity": identity, "case_ids": ["case.a"], "inventory_digest": H0, "discovered_at_utc": UTC_0},
        2: {"run_id": "run-1", "started_at_utc": UTC_0, "case_ids": ["case.a"], "inventory_digest": H0},
        3: {"case_id": "case.a", "started_at_utc": UTC_0},
        4: {"case_id": "case.a", "state": "passed", "ended_at_utc": UTC_1, "duration_ms": 1000, "message": None, "stdout": None, "stderr": None},
        5: {"state": "passed", "ended_at_utc": UTC_1, "duration_ms": 1000, "inventory_digest": H0, "build_id": H1, "elf_sha256": H2, "target_device": TARGET, "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0}, "event_stream_digest": "4" * 64},
        6: {"timestamp_utc": UTC_0, "stream": "stdout", "message": "line"},
    }


def payloads() -> list[tuple[int, dict[str, object]]]:
    frozen = frozen_schema_payloads()
    return [(kind, frozen[kind]) for kind in (1, 2, 3, 4, 6)]


def valid_run_bytes() -> bytes:
    frames = [encode_frame(kind, sequence, body) for sequence, (kind, body) in enumerate(payloads())]
    terminal = frozen_schema_payloads()[5]
    terminal["event_stream_digest"] = sha256(b"".join(frames)).hexdigest()
    frames.append(encode_frame(5, len(frames), terminal))
    return b"".join(frames)


def assert_code(code: str, function) -> None:
    with pytest.raises(ProtocolError) as caught:
        function()
    assert caught.value.code == code


def test_exact_golden_little_endian_header_crc_and_all_kinds() -> None:
    payload = frozen_schema_payloads()[6]
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = b"ST32" + bytes((1, 6)) + b"\x00\x00" + struct.pack("<II", 0x78563412, len(body))
    expected = header + body + struct.pack("<I", zlib.crc32(header + body) & 0xFFFFFFFF)
    assert encode_frame(6, 0x78563412, payload) == expected
    assert EVENT_KINDS == {1: "inventory", 2: "run_start", 3: "case_start", 4: "case_result", 5: "run_end", 6: "log"}
    assert FRAME_MAGIC == b"ST32" and FRAME_VERSION == 1


def test_byte_at_a_time_fragmentation_and_concatenation() -> None:
    stream = valid_run_bytes()
    decoder = TargetFrameDecoder()
    frames = []
    for byte in stream:
        frames.extend(decoder.feed(bytes((byte,))))
    decoder.finish()
    assert [frame.kind for frame in frames] == [1, 2, 3, 4, 6, 5]
    decoder = TargetFrameDecoder()
    assert len(decoder.feed(stream)) == 6
    decoder.finish()


@pytest.mark.parametrize("seed", range(16))
def test_deterministic_property_fragmentation(seed: int) -> None:
    rng = random.Random(seed)
    stream = valid_run_bytes()
    decoder = TargetFrameDecoder()
    frames = []
    cursor = 0
    while cursor < len(stream):
        size = rng.randint(1, 31)
        frames.extend(decoder.feed(stream[cursor : cursor + size]))
        cursor += size
    decoder.finish()
    assert b"".join(frame.raw_bytes for frame in frames) == stream


def test_strict_sequence_kind_flags_and_payload_limits() -> None:
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetFrameDecoder().feed(encode_frame(1, 1, frozen_schema_payloads()[1])))
    for kind in (0, 7, 255):
        assert_code("TEST_PROTOCOL_INVALID", lambda kind=kind: encode_frame(kind, 0, {}))
    assert_code("TEST_PROTOCOL_INVALID", lambda: encode_frame(1, 0, frozen_schema_payloads()[1], flags=1))
    oversized = frozen_schema_payloads()[6]
    oversized["message"] = "x" * MAX_FRAME_PAYLOAD_BYTES
    assert_code("TEST_FRAME_TOO_LARGE", lambda: encode_frame(6, 0, oversized))


def test_invalid_version_and_oversize_rejected_before_payload_allocation() -> None:
    version = b"ST32" + bytes((2, 1)) + b"\0\0" + struct.pack("<II", 0, 0)
    version += struct.pack("<I", zlib.crc32(version) & 0xFFFFFFFF)
    decoder = TargetFrameDecoder()
    decoder.feed(version)
    assert_code("TEST_FRAME_VERSION_INVALID", decoder.finish)

    header = b"ST32" + bytes((1, 1)) + b"\0\0" + struct.pack("<II", 0, MAX_FRAME_PAYLOAD_BYTES + 1)
    assert_code("TEST_FRAME_TOO_LARGE", lambda: TargetFrameDecoder().feed(header))


def test_crc_corruption_recovers_only_at_a_complete_valid_boundary() -> None:
    corrupt = bytearray(encode_frame(1, 0, frozen_schema_payloads()[1]))
    corrupt[-1] ^= 0x80
    valid_payload = frozen_schema_payloads()[1]
    valid_payload["discovered_at_utc"] = UTC_1
    valid = encode_frame(1, 0, valid_payload)
    decoder = TargetFrameDecoder()
    frames = decoder.feed(bytes(corrupt) + valid)
    decoder.finish()
    assert frames[0].payload["discovered_at_utc"] == UTC_1
    assert decoder.discarded_bytes == len(corrupt)

    decoder = TargetFrameDecoder()
    decoder.feed(bytes(corrupt))
    assert_code("TEST_FRAME_CRC_INVALID", decoder.finish)


def test_magic_recovery_is_bounded_and_records_discarded_bytes() -> None:
    decoder = TargetFrameDecoder(max_discarded_bytes=8)
    assert decoder.feed(b"junk" + encode_frame(1, 0, frozen_schema_payloads()[1]))[0].payload["mode"] == "target"
    assert decoder.discarded_bytes == 4
    assert_code("TEST_FRAME_RECOVERY_LIMIT", lambda: TargetFrameDecoder(max_discarded_bytes=3).feed(b"junkjunk"))


def test_utf8_json_object_and_incomplete_stream_errors() -> None:
    def raw(payload: bytes) -> bytes:
        header = b"ST32" + bytes((1, 1)) + b"\0\0" + struct.pack("<II", 0, len(payload))
        return header + payload + struct.pack("<I", zlib.crc32(header + payload) & 0xFFFFFFFF)

    for data in (b"\xff", b"{", b"[]", b'{"x":NaN}', b'{"x":1,"x":2}'):
        decoder = TargetFrameDecoder()
        assert_code("TEST_PROTOCOL_INVALID", lambda data=data, decoder=decoder: decoder.feed(raw(data)))
    decoder = TargetFrameDecoder()
    decoder.feed(encode_frame(1, 0, frozen_schema_payloads()[1])[:-1])
    assert_code("TEST_STREAM_INCOMPLETE", decoder.finish)


def test_run_stream_hard_limit() -> None:
    decoder = TargetFrameDecoder(max_stream_bytes=32)
    decoder.feed(b"x" * 32)
    assert_code("TEST_STREAM_TOO_LARGE", lambda: decoder.feed(b"x"))
    assert MAX_RUN_STREAM_BYTES == 64 * 1024 * 1024


def test_terminal_digest_counts_and_identity_binding() -> None:
    decoder = TargetFrameDecoder()
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    for frame in decoder.feed(valid_run_bytes()):
        validator.accept(frame)
    decoder.finish()
    summary = validator.finish()
    assert summary.counts["passed"] == 1
    assert summary.event_stream_digest == sha256(b"".join(frame.raw_bytes for frame in decoder.frames[:-1])).hexdigest()


@pytest.mark.parametrize("field", ["inventory_digest", "build_id", "elf_sha256", "target_device", "event_stream_digest", "counts"])
def test_terminal_binding_rejects_each_contradiction(field: str) -> None:
    decoder = TargetFrameDecoder()
    frames = list(decoder.feed(valid_run_bytes()))
    terminal = frozen_schema_payloads()[5]
    terminal["event_stream_digest"] = frames[-1].payload["event_stream_digest"]
    terminal[field] = ({"passed": 99, "failed": 0, "skipped": 0, "error": 0, "timeout": 0} if field == "counts" else ("wrong" if field == "target_device" else "f" * 64))
    frames[-1] = TargetFrameDecoder().feed(encode_frame(5, 0, terminal))[0]
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    for frame in frames:
        validator.accept(frame)
    assert_code("TEST_IDENTITY_MISMATCH" if field not in ("counts", "event_stream_digest") else "TEST_EVENT_SEQUENCE_INVALID", validator.finish)


def test_state_machine_rejects_duplicate_case_and_events_after_terminal() -> None:
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    frames = TargetFrameDecoder().feed(valid_run_bytes())
    for frame in frames:
        validator.accept(frame)
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: validator.accept(frames[4]))


def test_recorded_replay_manifest_binds_exact_binary_fixtures() -> None:
    manifest = json.loads((FIXTURES / "replay-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "stm32tk-target-replay/1"
    assert manifest["physical_transport_evidence"] is False
    assert manifest["source"] == "toolkit-generated-protocol-replay"
    for name, record in manifest["files"].items():
        data = (FIXTURES / name).read_bytes()
        assert len(data) == record["bytes"]
        assert sha256(data).hexdigest() == record["sha256"]
    for record in manifest["embedded_streams"].values():
        data = bytes.fromhex(record["value"])
        assert record["encoding"] == "hex" and len(data) == record["bytes"]
        assert sha256(data).hexdigest() == record["sha256"]
    assert (FIXTURES / "valid-run.bin").read_bytes() == valid_run_bytes()


def test_replay_fixture_line_endings_are_explicit_and_binary_is_not_text() -> None:
    attributes = ATTRIBUTES.read_text(encoding="utf-8").splitlines()
    assert "/tools/stm32-toolkit/tests/fixtures/target-streams/*.json text eol=lf" in attributes
    assert "/tools/stm32-toolkit/tests/fixtures/target-streams/*.bin -text" in attributes


def test_recorded_corruption_classes() -> None:
    decoder = TargetFrameDecoder()
    decoder.feed((FIXTURES / "corrupt-crc.bin").read_bytes())
    assert_code("TEST_FRAME_CRC_INVALID", decoder.finish)
    decoder = TargetFrameDecoder()
    decoder.feed((FIXTURES / "truncated-frame.bin").read_bytes())
    assert_code("TEST_STREAM_INCOMPLETE", decoder.finish)
    assert_code("TEST_FRAME_TOO_LARGE", lambda: TargetFrameDecoder().feed((FIXTURES / "oversize-header.bin").read_bytes()))


def test_closed_constructor_encoder_and_decoder_error_paths() -> None:
    for args in (("x", H1, H2, TARGET), (H0, H1, H2, "")):
        assert_code("TEST_PROTOCOL_INVALID", lambda args=args: TargetRunBinding(*args))
    assert_code("TEST_PROTOCOL_INVALID", lambda: encode_frame(1, 0, []))
    assert_code("TEST_EVENT_PAYLOAD_INVALID", lambda: encode_frame(1, 0, {"bad": object()}))
    for kwargs in ({"max_stream_bytes": 0}, {"max_stream_bytes": MAX_RUN_STREAM_BYTES + 1}, {"max_discarded_bytes": -1}):
        assert_code("TEST_PROTOCOL_INVALID", lambda kwargs=kwargs: TargetFrameDecoder(**kwargs))
    decoder = TargetFrameDecoder()
    assert decoder.stream_bytes == 0
    decoder.finish()
    decoder.finish()
    assert_code("TEST_PROTOCOL_INVALID", lambda: decoder.feed(b""))
    assert_code("TEST_PROTOCOL_INVALID", lambda: TargetFrameDecoder().feed(bytearray()))


def test_decoder_rejects_crc_valid_unknown_kind_and_flags() -> None:
    def raw(kind: int, flags: int) -> bytes:
        body = b"{}"
        header = struct.pack("<4sBBHII", b"ST32", 1, kind, flags, 0, len(body))
        return header + body + struct.pack("<I", zlib.crc32(header + body) & 0xFFFFFFFF)

    for kind, flags in ((7, 0), (1, 1)):
        assert_code("TEST_PROTOCOL_INVALID", lambda kind=kind, flags=flags: TargetFrameDecoder().feed(raw(kind, flags)))


def isolated_frame(kind: int, payload: dict[str, object]) -> TargetFrame:
    return TargetFrameDecoder().feed(encode_frame(kind, 0, payload))[0]


def validator_after_start() -> TargetRunValidator:
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    validator.accept(isolated_frame(1, frozen_schema_payloads()[1]))
    validator.accept(isolated_frame(2, frozen_schema_payloads()[2]))
    return validator


def test_validator_closed_state_machine_error_paths() -> None:
    assert_code("TEST_PROTOCOL_INVALID", lambda: TargetRunValidator(object()))
    binding = TargetRunBinding(H0, H1, H2, TARGET)
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetRunValidator(binding).finish())
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetRunValidator(binding).accept(isolated_frame(2, frozen_schema_payloads()[2])))
    bad_inventory = frozen_schema_payloads()[1]
    bad_inventory["inventory_digest"] = H1
    assert_code("TEST_IDENTITY_MISMATCH", lambda: TargetRunValidator(binding).accept(isolated_frame(1, bad_inventory)))
    first = TargetRunValidator(binding)
    first.accept(isolated_frame(1, frozen_schema_payloads()[1]))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: first.accept(isolated_frame(3, frozen_schema_payloads()[3])))
    bad_start = frozen_schema_payloads()[2]
    bad_start["inventory_digest"] = H1
    assert_code("TEST_IDENTITY_MISMATCH", lambda: first.accept(isolated_frame(2, bad_start)))
    undiscovered = frozen_schema_payloads()[2]
    undiscovered["case_ids"] = ["case.b"]
    inventory_bound = TargetRunValidator(binding)
    inventory_bound.accept(isolated_frame(1, frozen_schema_payloads()[1]))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: inventory_bound.accept(isolated_frame(2, undiscovered)))

    active = validator_after_start()
    active.accept(isolated_frame(3, frozen_schema_payloads()[3]))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(3, frozen_schema_payloads()[3])))
    wrong_result = frozen_schema_payloads()[4]
    wrong_result["case_id"] = "case.b"
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(4, wrong_result)))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(5, frozen_schema_payloads()[5])))

    invalid_kind = validator_after_start()
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: invalid_kind.accept(isolated_frame(1, frozen_schema_payloads()[1])))

    duplicate = validator_after_start()
    duplicate.accept(isolated_frame(3, frozen_schema_payloads()[3]))
    duplicate.accept(isolated_frame(4, frozen_schema_payloads()[4]))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: duplicate.accept(isolated_frame(3, frozen_schema_payloads()[3])))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: duplicate.accept("not-a-frame"))


@pytest.mark.parametrize("kind", range(1, 7))
@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong-type"])
def test_frame_encoder_reuses_frozen_closed_payload_contract(kind: int, mutation: str) -> None:
    payload = frozen_schema_payloads()[kind]
    if mutation == "missing":
        payload.pop(next(iter(payload)))
    elif mutation == "extra":
        payload["extra"] = True
    else:
        payload[next(iter(payload))] = None
    assert_code("TEST_EVENT_PAYLOAD_INVALID", lambda: encode_frame(kind, 0, payload))


def test_decoded_payload_is_deeply_immutable_and_bound_to_raw_bytes() -> None:
    payload = frozen_schema_payloads()[1]
    frame = TargetFrameDecoder().feed(encode_frame(1, 0, payload))[0]
    assert isinstance(frame.payload, MappingProxyType)
    with pytest.raises(TypeError):
        frame.payload["mode"] = "host"  # type: ignore[index]
    with pytest.raises((AttributeError, TypeError)):
        frame.payload["case_ids"].append("mutated")  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        frame.payload["identity"]["target_device"] = "mutated"  # type: ignore[index]

    forged_payload = dict(frame.payload)
    forged_payload["mode"] = "host"
    forged = TargetFrame(frame.kind, frame.sequence, MappingProxyType(forged_payload), frame.raw_bytes)
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    assert_code("TEST_EVENT_PAYLOAD_INVALID", lambda: validator.accept(forged))

    unknown = bytearray(frame.raw_bytes)
    unknown[5] = 7
    unknown[-4:] = struct.pack("<I", zlib.crc32(unknown[:-4]) & 0xFFFFFFFF)
    unknown_frame = TargetFrame(7, frame.sequence, frame.payload, bytes(unknown))
    assert_code("TEST_EVENT_PAYLOAD_INVALID", lambda: validator.accept(unknown_frame))


def test_golden_decoder_uses_all_six_frozen_payload_shapes() -> None:
    frames = []
    decoder = TargetFrameDecoder()
    for sequence, (kind, payload) in enumerate(frozen_schema_payloads().items()):
        frames.extend(decoder.feed(encode_frame(kind, sequence, payload)))
    decoder.finish()
    assert [set(frame.payload) for frame in frames] == [set(value) for value in frozen_schema_payloads().values()]
