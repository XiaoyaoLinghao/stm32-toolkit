"""Closed target-test framing and terminal run validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import inspect
import secrets
import time
import struct
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4
import zlib

from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from stm32_toolkit.probe.client import ProbeClient
from stm32_toolkit.probe.service import ProbeEndpoint
from stm32_toolkit.testing.model import (
    EVENT_KINDS,
    MAX_FRAME_PAYLOAD_BYTES,
    MAX_RUN_STREAM_BYTES,
    TestProtocolError,
    TestCaseResult,
    TestRunManifest,
    TEST_SCHEMA,
    protocol_error,
)
from stm32_toolkit.testing.protocol import validate_event_payload


FRAME_MAGIC = b"ST32"
FRAME_VERSION = 1
FRAME_HEADER_BYTES = 16
FRAME_CRC_BYTES = 4
_HEADER = struct.Struct("<4sBBHII")
_CRC = struct.Struct("<I")
_COUNT_STATES = ("passed", "failed", "skipped", "error", "timeout")
_TRANSPORT_KINDS = {
    "mailbox": "memory-mailbox", "rtt": "rtt", "uart": "uart", "semihosting": "semihosting",
}
_TRANSPORT_IDENTITY_FIELDS = {
    "mailbox": {"probe_id", "target_id", "transport", "config_digest", "address", "ring_size", "ram_bounds"},
    "rtt": {"probe_id", "target_id", "transport", "config_digest", "channel", "control_block_address", "ram_bounds"},
    "uart": {"probe_id", "target_id", "transport", "config_digest", "port", "baud", "data_bits", "parity", "stop_bits", "flow_control"},
    "semihosting": {"probe_id", "target_id", "transport", "config_digest", "elf_path", "elf_sha256", "host_file_policy"},
}


def _closed_project_transport_config(
    transport: object, config: object
) -> dict[str, object]:
    """Validate exactly the Project v3 target transport union."""
    if transport not in _TRANSPORT_KINDS or not isinstance(config, Mapping) or set(config) != {"kind", "options"}:
        raise ValueError("Target transport configuration is invalid")
    if config.get("kind") != _TRANSPORT_KINDS[transport] or not isinstance(config.get("options"), Mapping):
        raise ValueError("Target transport configuration is invalid")
    options = dict(config["options"])
    if transport == "mailbox":
        if (
            set(options) != {"address", "size"}
            or type(options["address"]) is not int
            or type(options["size"]) is not int
            or not 0 <= options["address"] <= 0xFFFF_FFFF
            or not 1 <= options["size"] <= 65_536
            or options["address"] + options["size"] > 1 << 32
        ):
            raise ValueError("Target mailbox configuration is invalid")
    elif transport == "rtt":
        if set(options) not in ({"channel"}, {"channel", "controlBlockAddress"}):
            raise ValueError("Target RTT configuration is invalid")
        if type(options["channel"]) is not int or not 0 <= options["channel"] <= 15:
            raise ValueError("Target RTT configuration is invalid")
        if "controlBlockAddress" in options and (
            type(options["controlBlockAddress"]) is not int
            or not 0 <= options["controlBlockAddress"] <= 0xFFFF_FFFF
        ):
            raise ValueError("Target RTT configuration is invalid")
    elif transport == "uart":
        port = options.get("port")
        if (
            set(options) != {"port", "baud"}
            or not isinstance(port, str)
            or not 1 <= len(port.encode("utf-8")) <= 256
            or any(ord(character) < 32 or ord(character) == 127 for character in port)
            or type(options["baud"]) is not int
            or options["baud"] not in {9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600}
        ):
            raise ValueError("Target UART configuration is invalid")
    elif options:
        raise ValueError("Target semihosting configuration is invalid")
    return {"kind": config["kind"], "options": options}


def _closed_transport_identity(value: object, binding: Mapping[str, object]) -> dict[str, str]:
    transport = binding.get("transport")
    fields = _TRANSPORT_IDENTITY_FIELDS.get(transport)
    if not isinstance(value, Mapping) or fields is None or set(value) != fields:
        raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target transport identity is invalid")
    result = dict(value)
    if any(not isinstance(member, str) or not member for member in result.values()):
        raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target transport identity is invalid")
    if (
        result["target_id"] != dict(binding["target"])["target_id"]
        or result["transport"] != binding["transport"]
        or len(result["config_digest"]) != 64
        or any(character not in "0123456789abcdef" for character in result["config_digest"])
    ):
        raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target transport identity changed")
    return result


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def _deep_freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(member) for key, member in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(member) for member in value)
    return value


def _deep_thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(member) for key, member in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(member) for member in value]
    return value


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
    value = validate_event_payload(EVENT_KINDS[kind], dict(payload))
    try:
        body = canonical_json_bytes(value)
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
            value = validate_event_payload(EVENT_KINDS[kind], payload)
            frame = TargetFrame(kind, sequence, _deep_freeze(value), candidate)
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
        self._inventory_cases: set[str] = set()
        self._case_ids: set[str] = set()
        self._selected_cases: set[str] = set()
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
        self._validate_raw_binding(frame)
        payload = frame.payload
        if self._stage == "inventory":
            if frame.kind != 1:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "inventory must be first")
            if payload.get("inventory_digest") != self._binding.inventory_digest:
                raise protocol_error("TEST_IDENTITY_MISMATCH", "inventory digest does not match the run binding")
            identity = payload.get("identity")
            if not isinstance(identity, Mapping) or any(
                identity.get(key) != value for key, value in {
                    "build_id": self._binding.build_id,
                    "elf_sha256": self._binding.elf_sha256,
                    "target_device": self._binding.target_id,
                }.items()
            ):
                raise protocol_error("TEST_IDENTITY_MISMATCH", "inventory identity does not match the run binding")
            inventory_cases = payload.get("case_ids")
            assert isinstance(inventory_cases, tuple)
            self._inventory_cases = set(inventory_cases)
            self._stage = "run_start"
        elif self._stage == "run_start":
            if frame.kind != 2:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_start must follow inventory")
            if payload.get("inventory_digest") != self._binding.inventory_digest:
                raise protocol_error("TEST_IDENTITY_MISMATCH", "run_start inventory does not match the run binding")
            selected = payload.get("case_ids")
            assert isinstance(selected, tuple)
            if any(case_id not in self._inventory_cases for case_id in selected):
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_start names an undiscovered case")
            self._selected_cases = set(selected)
            self._stage = "running"
        elif frame.kind == 3:
            if self._active_case is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "case_start occurs while another case is active")
            case_id = self._string(payload, "case_id")
            if case_id not in self._selected_cases or case_id in self._case_ids:
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
            self._string(payload, "message")
        elif frame.kind == 5:
            if self._active_case is not None:
                raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end occurs while a case is active")
            self._terminal = payload
            return
        else:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target event kind is invalid in the current state")
        self._digest.update(frame.raw_bytes)

    @staticmethod
    def _validate_raw_binding(frame: TargetFrame) -> None:
        raw = frame.raw_bytes
        if not isinstance(raw, bytes) or len(raw) < FRAME_HEADER_BYTES + FRAME_CRC_BYTES:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "frame raw bytes are invalid")
        magic, version, kind, flags, sequence, payload_length = _HEADER.unpack_from(raw)
        if (
            magic != FRAME_MAGIC or version != FRAME_VERSION or kind not in EVENT_KINDS or kind != frame.kind
            or flags != 0 or sequence != frame.sequence
            or len(raw) != FRAME_HEADER_BYTES + payload_length + FRAME_CRC_BYTES
            or (_CRC.unpack_from(raw, len(raw) - FRAME_CRC_BYTES)[0] != zlib.crc32(raw[:-FRAME_CRC_BYTES]) & 0xFFFFFFFF)
        ):
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "frame metadata contradicts raw bytes")
        try:
            decoded = json.loads(
                raw[FRAME_HEADER_BYTES:-FRAME_CRC_BYTES].decode("utf-8"),
                object_pairs_hook=_closed_json_object,
                parse_constant=_reject_json_constant,
            )
            validated = validate_event_payload(EVENT_KINDS[kind], decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TestProtocolError) as exc:
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "frame payload contradicts raw bytes") from exc
        if validated != _deep_thaw(frame.payload):
            raise protocol_error("TEST_EVENT_PAYLOAD_INVALID", "frame payload contradicts raw bytes")

    def finish(self) -> TargetRunSummary:
        if self._terminal is None:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target run has no terminal run_end")
        if self._active_case is not None or self._case_ids != self._selected_cases:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "target run did not complete every selected case")
        terminal = self._terminal
        expected_identity = {
            "inventory_digest": self._binding.inventory_digest,
            "build_id": self._binding.build_id,
            "elf_sha256": self._binding.elf_sha256,
            "target_device": self._binding.target_id,
        }
        if any(terminal.get(key) != value for key, value in expected_identity.items()):
            raise protocol_error("TEST_IDENTITY_MISMATCH", "run_end identity does not match the run binding")
        if terminal.get("event_stream_digest") != self._digest.hexdigest():
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end event stream digest is invalid")
        raw_counts = terminal.get("counts")
        if not isinstance(raw_counts, Mapping) or set(raw_counts) != set(_COUNT_STATES) or dict(raw_counts) != self._counts:
            raise protocol_error("TEST_EVENT_SEQUENCE_INVALID", "run_end counts contradict case results")
        return TargetRunSummary(dict(self._counts), self._digest.hexdigest())


class TargetRunError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreparedTargetRun:
    action_digest: str
    nonce: str
    expires_at_utc: datetime
    binding: Mapping[str, object]


class GuardedTargetFlashAdapter:
    """Bind Target runs to the existing one-shot guarded flash workflow."""

    def __init__(
        self,
        *,
        project_root: Path,
        data_root: Path,
        session_id: str,
        probe_id: str,
        workflow: object,
    ) -> None:
        if (
            not isinstance(project_root, Path)
            or not project_root.is_absolute()
            or not isinstance(data_root, Path)
            or not data_root.is_absolute()
            or not isinstance(session_id, str)
            or not session_id
            or not isinstance(probe_id, str)
            or not probe_id
            or not callable(workflow)
        ):
            raise TypeError("Guarded Target flash adapter configuration is invalid")
        self._project_root = project_root
        self._data_root = data_root
        self._session_id = session_id
        self._probe_id = probe_id
        self._workflow = workflow

    async def run(self, binding: Mapping[str, object]) -> None:
        from stm32_toolkit.hardware_workflows import FlashWorkflowRequest

        if binding.get("session_id") != self._session_id:
            raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target flash session changed")
        result = await self._workflow(
            FlashWorkflowRequest(
                self._project_root,
                self._data_root,
                self._session_id,
                self._probe_id,
                str(binding["build_id"]),
                str(binding["elf_sha256"]),
                True,
            )
        )
        if not isinstance(result, OperationResult) or not result.ok:
            raise TargetRunError("TEST_FLASH_FAILED", "Guarded Target flash failed")


class TargetTestRunner:
    """Identity-bound Target test orchestration over guarded flash and closed transports."""

    def __init__(
        self,
        evidence_root: Path,
        probe: object,
        flash_workflow: object,
        transport_factory: object,
        *,
        artifact_collector: TestArtifactCollector | None = None,
    ) -> None:
        if (
            not isinstance(evidence_root, Path)
            or not evidence_root.is_absolute()
            or evidence_root.parent == evidence_root
            or not callable(transport_factory)
        ):
            raise TypeError("Target runner dependencies are invalid")
        self._root = evidence_root
        self._storage = EvidenceStore(evidence_root)
        self._probe = probe
        self._flash = flash_workflow
        self._transport_factory = transport_factory
        self._collector = artifact_collector

    async def prepare(self, *, now: datetime | None = None, **binding: object) -> PreparedTargetRun:
        required = {
            "workspace_id", "project_id", "session_id", "revision", "target", "probe_serial_hash",
            "elf_path", "elf_sha256", "build_id", "inventory_digest", "transport",
            "transport_config", "cases", "timeout_ms",
        }
        if set(binding) != required:
            raise TargetRunError("TEST_PROTOCOL_INVALID", "Target run binding is not closed")
        for digest in ("probe_serial_hash", "elf_sha256", "build_id", "inventory_digest"):
            value = binding[digest]
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise TargetRunError("TEST_PROTOCOL_INVALID", f"{digest} is invalid")
        if type(binding["timeout_ms"]) is not int or not 1 <= binding["timeout_ms"] <= 300_000:
            raise TargetRunError("TEST_PROTOCOL_INVALID", "Target timeout is invalid")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise TargetRunError("TEST_PROTOCOL_INVALID", "Target run time must be UTC aware")
        nonce = secrets.token_hex(32)
        expires = instant.astimezone(timezone.utc) + timedelta(minutes=5)
        full = {
            **binding,
            "cases": list(binding["cases"]),
            "nonce": nonce,
            "prepared_at_utc": instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "expires_at_utc": expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        try:
            self._validate_prepared_record(full)
        except ValueError as error:
            raise TargetRunError("TEST_PROTOCOL_INVALID", "Target run binding is invalid") from error
        digest = sha256(canonical_json_bytes(full)).hexdigest()
        with self._storage._mutation_lock():
            created = self._storage._atomic_create_new(
                self._root / f"{digest}.prepared.json",
                canonical_json_bytes(full),
                phase="target-run-prepare",
            )
            if not created:
                raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization already exists")
        return PreparedTargetRun(digest, nonce, expires, full)

    def _consume_prepared(
        self, digest: str, *, now: datetime
    ) -> Mapping[str, object]:
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization is invalid")
        with self._storage._mutation_lock():
            path = self._root / f"{digest}.prepared.json"
            try:
                self._storage._validate_existing_path(path, regular=True, single_link=True)
                descriptor = os.open(
                    path,
                    os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    payload = os.read(descriptor, 65_537)
                    if len(payload) > 65_536 or os.read(descriptor, 1):
                        raise ValueError
                finally:
                    os.close(descriptor)
                record = json.loads(payload.decode("utf-8"))
                if (
                    not isinstance(record, dict)
                    or canonical_json_bytes(record) != payload
                    or sha256(payload).hexdigest() != digest
                ):
                    raise ValueError
                self._validate_prepared_record(record)
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
                raise TargetRunError(
                    "TEST_AUTHORIZATION_INVALID", "Target authorization is unknown or corrupt"
                ) from error
            consumed = canonical_json_bytes(
                {
                    "action_digest": digest,
                    "consumed_at_utc": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                }
            )
            if not self._storage._atomic_create_new(
                self._root / f"{digest}.consumed.json",
                consumed,
                phase="target-run-consume",
            ):
                raise TargetRunError(
                    "TEST_AUTHORIZATION_INVALID", "Target authorization is already consumed"
                )
            return record

    @staticmethod
    def _validate_prepared_record(record: Mapping[str, object]) -> None:
        required = {
            "workspace_id", "project_id", "session_id", "revision", "target",
            "probe_serial_hash", "elf_path", "elf_sha256", "build_id", "inventory_digest",
            "transport", "transport_config", "cases", "timeout_ms", "nonce",
            "prepared_at_utc", "expires_at_utc",
        }
        try:
            if set(record) != required:
                raise ValueError
            for field in ("workspace_id", "project_id", "session_id", "revision", "elf_path"):
                if not isinstance(record[field], str) or not record[field]:
                    raise ValueError
            for field in ("probe_serial_hash", "elf_sha256", "build_id", "inventory_digest", "nonce"):
                value = record[field]
                if not isinstance(value, str) or len(value) != 64 or any(
                    character not in "0123456789abcdef" for character in value
                ):
                    raise ValueError
            target = record["target"]
            if (
                not isinstance(target, Mapping)
                or set(target) != {"board_id", "mcu", "target_id", "probe_serial_hash"}
                or any(not isinstance(value, str) or not value for value in target.values())
                or target["probe_serial_hash"] != record["probe_serial_hash"]
            ):
                raise ValueError
            if record["transport"] not in {"mailbox", "rtt", "uart", "semihosting"}:
                raise ValueError
            _closed_project_transport_config(record["transport"], record["transport_config"])
            cases = record["cases"]
            if (
                not isinstance(cases, list)
                or not cases
                or len(cases) > 4096
                or any(not isinstance(case, str) or not case for case in cases)
                or len(set(cases)) != len(cases)
            ):
                raise ValueError
            if type(record["timeout_ms"]) is not int or not 1 <= record["timeout_ms"] <= 300_000:
                raise ValueError
            prepared = datetime.fromisoformat(str(record["prepared_at_utc"])[:-1] + "+00:00")
            expires = datetime.fromisoformat(str(record["expires_at_utc"])[:-1] + "+00:00")
            if (
                not str(record["prepared_at_utc"]).endswith("Z")
                or not str(record["expires_at_utc"]).endswith("Z")
                or prepared.tzinfo is None
                or expires <= prepared
                or expires - prepared > timedelta(minutes=5)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid prepared Target run record") from error

    async def run(
        self, prepared: PreparedTargetRun, authorized_digest: str, *,
        current_revision: str, current_inventory_digest: str, now: datetime | None = None,
    ) -> Mapping[str, object]:
        transport = None
        try:
            instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            if not isinstance(prepared, PreparedTargetRun):
                raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization value is invalid")
            binding = self._consume_prepared(prepared.action_digest, now=instant)
            try:
                expires_at = datetime.fromisoformat(
                    str(binding["expires_at_utc"])[:-1] + "+00:00"
                )
            except (KeyError, ValueError, TypeError) as error:
                raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization record is invalid") from error
            if authorized_digest != prepared.action_digest or instant > expires_at:
                raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Exact unexpired Target authorization is required")
            if current_revision != binding["revision"] or current_inventory_digest != binding["inventory_digest"]:
                raise TargetRunError("TEST_INVENTORY_CHANGED", "Project revision or inventory changed")
            identity = await self._probe.target_identity()
            if identity != binding["target"]:
                raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target identity changed")
            if not isinstance(self._flash, GuardedTargetFlashAdapter):
                raise TargetRunError(
                    "TEST_AUTHORIZATION_INVALID",
                    "Target run requires the production guarded flash adapter",
                )
            try:
                transport = self._transport_factory(str(binding["transport"]))
                if (
                    not callable(getattr(transport, "open", None))
                    or not callable(getattr(transport, "identity", None))
                    or not (
                        callable(getattr(transport, "read_async", None))
                        or callable(getattr(transport, "read", None))
                    )
                    or not (
                        callable(getattr(transport, "close_async", None))
                        or callable(getattr(transport, "close", None))
                    )
                ):
                    raise TypeError
            except Exception as error:
                raise TargetRunError(
                    "TEST_TRANSPORT_UNAVAILABLE", "Configured Target transport is unavailable"
                ) from error
            await self._flash.run(binding)
            if await self._probe.target_identity() != binding["target"]:
                raise TargetRunError("TEST_IDENTITY_MISMATCH", "Target identity changed after flash")
            deadline = time.monotonic() + float(binding["timeout_ms"]) / 1000
            opened = transport.open(dict(binding["transport_config"]), deadline)
            if inspect.isawaitable(opened):
                await opened
            transport_identity = _closed_transport_identity(transport.identity(), binding)
            raw = bytearray()
            while len(raw) <= MAX_RUN_STREAM_BYTES:
                reader = getattr(transport, "read_async", transport.read)
                chunk = reader(min(65_536, MAX_RUN_STREAM_BYTES + 1 - len(raw)), deadline)
                if inspect.isawaitable(chunk):
                    chunk = await chunk
                if not chunk:
                    break
                raw.extend(chunk)
            if len(raw) > MAX_RUN_STREAM_BYTES:
                raise TargetRunError("TEST_STREAM_TOO_LARGE", "Target output exceeds the run limit")
            try:
                decoder = TargetFrameDecoder()
                frames = decoder.feed(bytes(raw))
                decoder.finish()
                validator = TargetRunValidator(
                    TargetRunBinding(
                        str(binding["inventory_digest"]),
                        str(binding["build_id"]),
                        str(binding["elf_sha256"]),
                        str(dict(binding["target"])["target_id"]),
                    )
                )
                for frame in frames:
                    validator.accept(frame)
                validator.finish()
                expected_cases = tuple(binding["cases"])
                if (
                    tuple(frames[0].payload["case_ids"]) != expected_cases
                    or tuple(frames[1].payload["case_ids"]) != expected_cases
                    or tuple(
                        str(frame.payload["case_id"]) for frame in frames if frame.kind == 4
                    ) != expected_cases
                    or _closed_transport_identity(transport.identity(), binding) != transport_identity
                ):
                    raise TargetRunError(
                        "TEST_IDENTITY_MISMATCH", "Target inventory, cases, or transport changed"
                    )
            except TestProtocolError as error:
                raise TargetRunError(error.code, error.message) from error
            collector = self._collector
            if not isinstance(collector, TestArtifactCollector):
                raise TargetRunError("TEST_EVIDENCE_FAILED", "Target Evidence collector is required")
            directory = collector.new_directory("target-run")
            raw_artifact = collector.write_and_ingest(
                directory,
                "target-stream.bin",
                bytes(raw),
                kind="test-events",
                media_type="application/vnd.stm32.target-events",
            )
            inventory = frames[0].payload
            run_start = frames[1].payload
            terminal = frames[-1].payload
            identity = EvidenceIdentity.from_dict(inventory["identity"])
            if (
                identity.workspace_id != binding["workspace_id"]
                or identity.project_id != binding["project_id"]
                or identity.session_id != binding["session_id"]
                or identity.build_id != binding["build_id"]
                or identity.elf_sha256 != binding["elf_sha256"]
                or identity.target_device != dict(binding["target"])["target_id"]
                or identity.input_snapshot_sha256 != binding["inventory_digest"]
                or identity.git_commit != binding["revision"]
            ):
                raise TargetRunError(
                    "TEST_IDENTITY_MISMATCH", "Target Test and Evidence identities do not match"
                )
            case_starts = {
                str(frame.payload["case_id"]): frame.payload
                for frame in frames if frame.kind == 3
            }
            cases = tuple(
                TestCaseResult(
                    str(frame.payload["case_id"]),
                    str(frame.payload["state"]),
                    str(case_starts[str(frame.payload["case_id"])]["started_at_utc"]),
                    str(frame.payload["ended_at_utc"]),
                    int(frame.payload["duration_ms"]),
                    frame.payload["message"],
                    None,
                    None,
                )
                for frame in frames if frame.kind == 4
            )
            manifest = TestRunManifest(
                TEST_SCHEMA,
                uuid4().hex,
                "target",
                str(terminal["state"]),
                identity,
                str(binding["transport"]),
                cases,
                str(run_start["started_at_utc"]),
                str(terminal["ended_at_utc"]),
                int(terminal["duration_ms"]),
                None,
                None,
                raw_artifact,
            )
            manifest_artifact = collector.write_and_ingest(
                directory,
                "test-manifest.json",
                canonical_json_bytes(manifest.to_dict()),
                kind="test-manifest",
                media_type="application/json",
            )
            envelope = EvidenceEnvelope(
                identity=identity,
                operation="target-test-run",
                produced_at_utc=str(terminal["ended_at_utc"]),
                parents=(),
                artifacts=(raw_artifact, manifest_artifact),
                metadata={
                    "action_digest": prepared.action_digest,
                    "test_run_id": manifest.run_id,
                    "test_manifest_sha256": manifest_artifact.sha256,
                },
            )
            collector.evidence_store.put_envelope(envelope)
            return {"test_manifest": manifest, "evidence": envelope}
        finally:
            if transport is not None:
                try:
                    closer = getattr(transport, "close_async", transport.close)
                    closed = closer()
                    if inspect.isawaitable(closed):
                        await closed
                except Exception:
                    pass
            await self._probe.close()

    async def discover(
        self, *, transport: str, config: Mapping[str, object], deadline: float,
        expected_identity: Mapping[str, object],
    ) -> Mapping[str, object]:
        active = self._transport_factory(transport)
        try:
            identity = await self._probe.target_identity()
            if identity != dict(expected_identity):
                raise TargetRunError("TEST_TRANSPORT_UNAVAILABLE", "Configured target identity is unavailable")
            opened = active.open(config, deadline)
            if inspect.isawaitable(opened):
                await opened
            reader = getattr(active, "read_async", active.read)
            raw = reader(65_536, deadline)
            if inspect.isawaitable(raw):
                raw = await raw
            if not isinstance(raw, bytes):
                raise TargetRunError("TEST_TRANSPORT_UNAVAILABLE", "Target discovery output is invalid")
            transport_identity = active.identity()
            if transport_identity.get("target_id") != expected_identity.get("target_id"):
                raise TargetRunError("TEST_TRANSPORT_UNAVAILABLE", "Target transport identity is unavailable")
            return {"identity": transport_identity, "raw": raw}
        finally:
            try:
                closer = getattr(active, "close_async", active.close)
                closed = closer()
                if inspect.isawaitable(closed):
                    await closed
            finally:
                await self._probe.close()


class ProbeV2MemoryReader:
    """Async bounded mailbox port backed only by a public Probe v2 endpoint."""

    def __init__(self, endpoint: ProbeEndpoint, expected_identity: Mapping[str, object]) -> None:
        if not isinstance(endpoint, ProbeEndpoint) or endpoint.protocol != "stm32-toolkit-probe/2":
            raise TypeError("Mailbox production binding requires a Probe v2 endpoint")
        if set(expected_identity) != {"board_id", "mcu", "target_id", "probe_serial_hash"}:
            raise TypeError("Mailbox target identity is invalid")
        self._endpoint = endpoint
        self._identity = dict(expected_identity)
        self._closed = False

    async def read_memory(self, address: int, size: int, deadline: float) -> bytes:
        if self._closed or type(address) is not int or type(size) is not int or not 1 <= size <= 4096:
            raise RuntimeError("Mailbox reader is closed or request is invalid")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Mailbox read deadline elapsed")
        timeout_ms = max(1, min(300_000, int(remaining * 1000)))

        client = ProbeClient(self._endpoint)
        try:
            if await client.target_identity() != self._identity:
                raise RuntimeError("Mailbox target identity changed")
            return await client.target_memory(address, size, timeout_ms=timeout_ms)
        finally:
            await client.close()

    async def close(self) -> None:
        self._closed = True
