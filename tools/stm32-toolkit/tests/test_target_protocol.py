from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import random
import struct
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


def payloads() -> list[tuple[int, dict[str, object]]]:
    return [
        (1, {"case_ids": ["case.a"], "inventory_digest": H0}),
        (2, {"build_id": H1, "elf_sha256": H2, "target_id": TARGET}),
        (3, {"case_id": "case.a"}),
        (4, {"case_id": "case.a", "state": "passed"}),
        (6, {"text": "ok"}),
    ]


def valid_run_bytes() -> bytes:
    frames = [encode_frame(kind, sequence, body) for sequence, (kind, body) in enumerate(payloads())]
    terminal = {
        "build_id": H1,
        "counts": {"error": 0, "failed": 0, "passed": 1, "skipped": 0, "timeout": 0},
        "elf_sha256": H2,
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
        "inventory_digest": H0,
        "target_id": TARGET,
    }
    frames.append(encode_frame(5, len(frames), terminal))
    return b"".join(frames)


def assert_code(code: str, function) -> None:
    with pytest.raises(ProtocolError) as caught:
        function()
    assert caught.value.code == code


def test_exact_golden_little_endian_header_crc_and_all_kinds() -> None:
    body = b'{"n":1}'
    header = b"ST32" + bytes((1, 6)) + b"\x00\x00" + struct.pack("<II", 0x78563412, len(body))
    expected = header + body + struct.pack("<I", zlib.crc32(header + body) & 0xFFFFFFFF)
    assert encode_frame(6, 0x78563412, {"n": 1}) == expected
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
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetFrameDecoder().feed(encode_frame(1, 1, {"x": 1})))
    for kind in (0, 7, 255):
        assert_code("TEST_PROTOCOL_INVALID", lambda kind=kind: encode_frame(kind, 0, {}))
    assert_code("TEST_PROTOCOL_INVALID", lambda: encode_frame(1, 0, {}, flags=1))
    assert_code("TEST_FRAME_TOO_LARGE", lambda: encode_frame(1, 0, {"x": "x" * MAX_FRAME_PAYLOAD_BYTES}))


def test_invalid_version_and_oversize_rejected_before_payload_allocation() -> None:
    version = b"ST32" + bytes((2, 1)) + b"\0\0" + struct.pack("<II", 0, 0)
    version += struct.pack("<I", zlib.crc32(version) & 0xFFFFFFFF)
    decoder = TargetFrameDecoder()
    decoder.feed(version)
    assert_code("TEST_FRAME_VERSION_INVALID", decoder.finish)

    header = b"ST32" + bytes((1, 1)) + b"\0\0" + struct.pack("<II", 0, MAX_FRAME_PAYLOAD_BYTES + 1)
    assert_code("TEST_FRAME_TOO_LARGE", lambda: TargetFrameDecoder().feed(header))


def test_crc_corruption_recovers_only_at_a_complete_valid_boundary() -> None:
    corrupt = bytearray(encode_frame(1, 0, {"x": 1}))
    corrupt[-1] ^= 0x80
    valid = encode_frame(1, 0, {"x": 2})
    decoder = TargetFrameDecoder()
    frames = decoder.feed(bytes(corrupt) + valid)
    decoder.finish()
    assert [frame.payload for frame in frames] == [{"x": 2}]
    assert decoder.discarded_bytes == len(corrupt)

    decoder = TargetFrameDecoder()
    decoder.feed(bytes(corrupt))
    assert_code("TEST_FRAME_CRC_INVALID", decoder.finish)


def test_magic_recovery_is_bounded_and_records_discarded_bytes() -> None:
    decoder = TargetFrameDecoder(max_discarded_bytes=8)
    assert decoder.feed(b"junk" + encode_frame(1, 0, {"x": 1}))[0].payload == {"x": 1}
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
    decoder.feed(encode_frame(1, 0, {})[:-1])
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


@pytest.mark.parametrize("field", ["inventory_digest", "build_id", "elf_sha256", "target_id", "event_stream_digest", "counts"])
def test_terminal_binding_rejects_each_contradiction(field: str) -> None:
    decoder = TargetFrameDecoder()
    frames = list(decoder.feed(valid_run_bytes()))
    terminal = dict(frames[-1].payload)
    terminal[field] = ({"passed": 99} if field == "counts" else ("wrong" if field == "target_id" else "f" * 64))
    frames[-1] = TargetFrameDecoder().feed(encode_frame(5, 0, terminal))[0]
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    for frame in frames:
        validator.accept(frame)
    assert_code("TEST_IDENTITY_MISMATCH" if field != "counts" and field != "event_stream_digest" else "TEST_EVENT_SEQUENCE_INVALID", validator.finish)


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
    assert_code("TEST_PROTOCOL_INVALID", lambda: encode_frame(1, 0, {"bad": object()}))
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
    return TargetFrame(kind, 0, payload, encode_frame(kind, 0, payload))


def validator_after_start() -> TargetRunValidator:
    validator = TargetRunValidator(TargetRunBinding(H0, H1, H2, TARGET))
    validator.accept(isolated_frame(1, {"inventory_digest": H0}))
    validator.accept(isolated_frame(2, {"build_id": H1, "elf_sha256": H2, "target_id": TARGET}))
    return validator


def test_validator_closed_state_machine_error_paths() -> None:
    assert_code("TEST_PROTOCOL_INVALID", lambda: TargetRunValidator(object()))
    binding = TargetRunBinding(H0, H1, H2, TARGET)
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetRunValidator(binding).finish())
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: TargetRunValidator(binding).accept(isolated_frame(2, {})))
    assert_code("TEST_IDENTITY_MISMATCH", lambda: TargetRunValidator(binding).accept(isolated_frame(1, {"inventory_digest": H1})))
    first = TargetRunValidator(binding)
    first.accept(isolated_frame(1, {"inventory_digest": H0}))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: first.accept(isolated_frame(3, {"case_id": "x"})))
    assert_code("TEST_IDENTITY_MISMATCH", lambda: first.accept(isolated_frame(2, {"build_id": H0, "elf_sha256": H2, "target_id": TARGET})))

    active = validator_after_start()
    active.accept(isolated_frame(3, {"case_id": "a"}))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(3, {"case_id": "b"})))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(4, {"case_id": "b", "state": "passed"})))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: active.accept(isolated_frame(5, {})))

    invalid_text = validator_after_start()
    assert_code("TEST_PROTOCOL_INVALID", lambda: invalid_text.accept(isolated_frame(6, {"text": ""})))
    invalid_kind = validator_after_start()
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: invalid_kind.accept(isolated_frame(1, {})))

    duplicate = validator_after_start()
    duplicate.accept(isolated_frame(3, {"case_id": "a"}))
    duplicate.accept(isolated_frame(4, {"case_id": "a", "state": "passed"}))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: duplicate.accept(isolated_frame(3, {"case_id": "a"})))
    assert_code("TEST_EVENT_SEQUENCE_INVALID", lambda: duplicate.accept("not-a-frame"))
