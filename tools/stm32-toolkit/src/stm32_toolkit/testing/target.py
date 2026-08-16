"""Closed target-test framing and terminal run validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import struct
from typing import Mapping
import zlib

from stm32_toolkit.evidence import canonical_json_bytes
from stm32_toolkit.testing.model import (
    EVENT_KINDS,
    MAX_FRAME_PAYLOAD_BYTES,
    MAX_RUN_STREAM_BYTES,
    TestProtocolError,
    protocol_error,
)


FRAME_MAGIC = b"ST32"
FRAME_VERSION = 1
FRAME_HEADER_BYTES = 16
FRAME_CRC_BYTES = 4
_HEADER = struct.Struct("<4sBBHII")
_CRC = struct.Struct("<I")
_COUNT_STATES = ("passed", "failed", "skipped", "error", "timeout")


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


@dataclass(frozen=True)
class TargetFrame:
    kind: int
    sequence: int
    payload: Mapping[str, object]
    raw_bytes: bytes

    @property
    def kind_name(self) -> str:
        return EVENT_KINDS[self.kind]


@dataclass(frozen=True)
class TargetRunBinding:
    inventory_digest: str
    build_id: str
    elf_sha256: str
    target_id: str

    def __post_init__(self) -> None:
        for name in ("inventory_digest", "build_id", "elf_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise protocol_error("TEST_PROTOCOL_INVALID", f"{name} must be a lowercase SHA-256")
        if not isinstance(self.target_id, str) or not self.target_id:
            raise protocol_error("TEST_PROTOCOL_INVALID", "target_id must be a non-empty string")


@dataclass(frozen=True)
class TargetRunSummary:
    counts: Mapping[str, int]
    event_stream_digest: str


def encode_frame(kind: int, sequence: int, payload: Mapping[str, object], *, flags: int = 0) -> bytes:
    """Encode one canonical version-1 frame."""
    if type(kind) is not int or kind not in EVENT_KINDS or type(sequence) is not int or not 0 <= sequence <= 0xFFFFFFFF:
        raise protocol_error("TEST_PROTOCOL_INVALID", "frame kind or sequence is invalid")
    if type(flags) is not int or flags != 0:
        raise protocol_error("TEST_PROTOCOL_INVALID", "version 1 frame flags must be zero")
    if not isinstance(payload, Mapping):
        raise protocol_error("TEST_PROTOCOL_INVALID", "frame payload must be a JSON object")
    try:
        body = canonical_json_bytes(dict(payload))
    except (TypeError, ValueError) as exc:
        raise protocol_error("TEST_PROTOCOL_INVALID", "frame payload is not canonical JSON") from exc
    if len(body) > MAX_FRAME_PAYLOAD_BYTES:
        raise protocol_error("TEST_FRAME_TOO_LARGE", "frame payload exceeds 16 KiB")
    header = _HEADER.pack(FRAME_MAGIC, FRAME_VERSION, kind, flags, sequence, len(body))
    framed = header + body
    return framed + _CRC.pack(zlib.crc32(framed) & 0xFFFFFFFF)


class TargetFrameDecoder:
    """Incrementally decode a bounded stream and recover only at verified frame boundaries."""

    def __init__(
        self,
        *,
        max_stream_bytes: int = MAX_RUN_STREAM_BYTES,
        max_discarded_bytes: int = MAX_FRAME_PAYLOAD_BYTES + FRAME_HEADER_BYTES + FRAME_CRC_BYTES,
    ) -> None:
        if type(max_stream_bytes) is not int or not 1 <= max_stream_bytes <= MAX_RUN_STREAM_BYTES:
            raise protocol_error("TEST_PROTOCOL_INVALID", "stream limit is invalid")
        if type(max_discarded_bytes) is not int or max_discarded_bytes < 0:
            raise protocol_error("TEST_PROTOCOL_INVALID", "recovery limit is invalid")
        self._max_stream_bytes = max_stream_bytes
        self._max_discarded_bytes = max_discarded_bytes
        self._buffer = bytearray()
        self._stream_bytes = 0
        self._discarded_bytes = 0
        self._expected_sequence = 0
        self._pending_recovery_error: TestProtocolError | None = None
        self._finished = False
        self._frames: list[TargetFrame] = []

    @property
    def discarded_bytes(self) -> int:
        return self._discarded_bytes

    @property
    def stream_bytes(self) -> int:
        return self._stream_bytes

    @property
    def frames(self) -> tuple[TargetFrame, ...]:
        return tuple(self._frames)

    def _discard(self, count: int) -> None:
        if count <= 0:
            return
        del self._buffer[:count]
        self._discarded_bytes += count
        if self._discarded_bytes > self._max_discarded_bytes:
            raise protocol_error("TEST_FRAME_RECOVERY_LIMIT", "discarded frame data exceeds the recovery bound")

    def feed(self, data: bytes) -> tuple[TargetFrame, ...]:
        if self._finished or not isinstance(data, bytes):
            raise protocol_error("TEST_PROTOCOL_INVALID", "decoder is finished or input is not bytes")
        if self._stream_bytes + len(data) > self._max_stream_bytes:
            raise protocol_error("TEST_STREAM_TOO_LARGE", "target event stream exceeds 64 MiB")
        self._stream_bytes += len(data)
        self._buffer.extend(data)
        decoded: list[TargetFrame] = []
        while True:
            if len(self._buffer) < len(FRAME_MAGIC):
                break
            marker = self._buffer.find(FRAME_MAGIC)
            if marker < 0:
                self._discard(len(self._buffer) - len(FRAME_MAGIC) + 1)
                break
            self._discard(marker)
            if len(self._buffer) < FRAME_HEADER_BYTES:
                break
            magic, version, kind, flags, sequence, payload_length = _HEADER.unpack_from(self._buffer)
            assert magic == FRAME_MAGIC
            if payload_length > MAX_FRAME_PAYLOAD_BYTES:
                raise protocol_error("TEST_FRAME_TOO_LARGE", "frame payload exceeds 16 KiB")
            if version != FRAME_VERSION:
                self._pending_recovery_error = protocol_error("TEST_FRAME_VERSION_INVALID", "target frame version is not 1")
                self._discard(1)
                continue
            frame_length = FRAME_HEADER_BYTES + payload_length + FRAME_CRC_BYTES
            if len(self._buffer) < frame_length:
                break
            candidate = bytes(self._buffer[:frame_length])
            expected_crc = _CRC.unpack_from(candidate, frame_length - FRAME_CRC_BYTES)[0]
            actual_crc = zlib.crc32(candidate[:-FRAME_CRC_BYTES]) & 0xFFFFFFFF
            if expected_crc != actual_crc:
                self._pending_recovery_error = protocol_error("TEST_FRAME_CRC_INVALID", "target frame CRC is invalid")
                self._discard(1)
                continue
            if kind not in EVENT_KINDS or flags != 0:
                raise protocol_error("TEST_PROTOCOL_INVALID", "target frame kind or flags are invalid")
            if sequence != self._expected_sequence:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target frame sequence is not strictly increasing from zero")
            payload_bytes = candidate[FRAME_HEADER_BYTES:-FRAME_CRC_BYTES]
            try:
                payload = json.loads(
                    payload_bytes.decode("utf-8"),
                    object_pairs_hook=_closed_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise protocol_error("TEST_PROTOCOL_INVALID", "target frame payload is not UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise protocol_error("TEST_PROTOCOL_INVALID", "target frame payload must be a JSON object")
            frame = TargetFrame(kind, sequence, payload, candidate)
            del self._buffer[:frame_length]
            self._expected_sequence += 1
            self._pending_recovery_error = None
            self._frames.append(frame)
            decoded.append(frame)
        return tuple(decoded)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        if self._pending_recovery_error is not None:
            raise self._pending_recovery_error
        if self._buffer:
            raise protocol_error("TEST_STREAM_INCOMPLETE", "target event stream ends inside a frame")


class TargetRunValidator:
    """Validate run state and the identity-bound terminal frame."""

    def __init__(self, binding: TargetRunBinding) -> None:
        if not isinstance(binding, TargetRunBinding):
            raise protocol_error("TEST_PROTOCOL_INVALID", "target run binding is invalid")
        self._binding = binding
        self._stage = "inventory"
        self._active_case: str | None = None
        self._case_ids: set[str] = set()
        self._counts = {state: 0 for state in _COUNT_STATES}
        self._digest = sha256()
        self._terminal: Mapping[str, object] | None = None

    @staticmethod
    def _string(payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise protocol_error("TEST_PROTOCOL_INVALID", f"{key} must be a non-empty string")
        return value

    def accept(self, frame: TargetFrame) -> None:
        if not isinstance(frame, TargetFrame) or self._terminal is not None:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target event occurs after run_end")
        payload = frame.payload
        if self._stage == "inventory":
            if frame.kind != 1:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "inventory must be first")
            if payload.get("inventory_digest") != self._binding.inventory_digest:
                raise protocol_error("TEST_IDENTITY_MISMATCH", "inventory digest does not match the run binding")
            self._stage = "run_start"
        elif self._stage == "run_start":
            if frame.kind != 2:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_start must follow inventory")
            self._check_run_identity(payload)
            self._stage = "running"
        elif frame.kind == 3:
            if self._active_case is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case_start occurs while another case is active")
            case_id = self._string(payload, "case_id")
            if case_id in self._case_ids:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case is duplicated")
            self._active_case = case_id
        elif frame.kind == 4:
            case_id = self._string(payload, "case_id")
            state = payload.get("state")
            if case_id != self._active_case or state not in _COUNT_STATES:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case_result contradicts the active case")
            self._case_ids.add(case_id)
            self._active_case = None
            self._counts[str(state)] += 1
        elif frame.kind == 6:
            self._string(payload, "text")
        elif frame.kind == 5:
            if self._active_case is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end occurs while a case is active")
            self._terminal = payload
            return
        else:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target event kind is invalid in the current state")
        self._digest.update(frame.raw_bytes)

    def _check_run_identity(self, payload: Mapping[str, object]) -> None:
        expected = {
            "build_id": self._binding.build_id,
            "elf_sha256": self._binding.elf_sha256,
            "target_id": self._binding.target_id,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise protocol_error("TEST_IDENTITY_MISMATCH", "run_start identity does not match the run binding")

    def finish(self) -> TargetRunSummary:
        if self._terminal is None:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target run has no terminal run_end")
        terminal = self._terminal
        expected_identity = {
            "inventory_digest": self._binding.inventory_digest,
            "build_id": self._binding.build_id,
            "elf_sha256": self._binding.elf_sha256,
            "target_id": self._binding.target_id,
        }
        if any(terminal.get(key) != value for key, value in expected_identity.items()):
            raise protocol_error("TEST_IDENTITY_MISMATCH", "run_end identity does not match the run binding")
        if terminal.get("event_stream_digest") != self._digest.hexdigest():
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end event stream digest is invalid")
        raw_counts = terminal.get("counts")
        if not isinstance(raw_counts, dict) or set(raw_counts) != set(_COUNT_STATES) or raw_counts != self._counts:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end counts contradict case results")
        return TargetRunSummary(dict(self._counts), self._digest.hexdigest())
