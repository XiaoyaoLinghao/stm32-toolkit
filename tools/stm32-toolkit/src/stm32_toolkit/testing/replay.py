"""Closed, non-physical Target replay descriptors and bounded fixtures.

This module owns only the replay input boundary.  It decodes a canonical
descriptor and a reviewable hexadecimal stream, validates their immutable
byte contract, and checks the existing Target framing/state machine.  It
does not open a transport, acquire authorization, execute a run, or publish
Evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal, cast

from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.model import (
    EVIDENCE_LIMIT_EXCEEDED,
    EVIDENCE_PATH_UNSAFE,
)

from .model import MAX_RUN_STREAM_BYTES, TestProtocolError
from stm32_toolkit.evidence.store import EvidenceStore


TARGET_REPLAY_SCHEMA = "stm32tk-target-replay/1"
TARGET_REPLAY_SOURCE = "toolkit-generated-protocol-replay"
TARGET_REPLAY_TRANSPORT = "replay"
TARGET_REPLAY_STREAM_FORMAT = "stm32-target-frame/1"
TARGET_REPLAY_STREAM_KIND = "target-replay-stream"

MAX_REPLAY_DESCRIPTOR_BYTES = 256 * 1024
MAX_REPLAY_HEX_BYTES = MAX_RUN_STREAM_BYTES * 3 + 2

_HASH = re.compile(r"^[0-9a-f]{64}$")
_ROLES = frozenset(("failed-before", "fixed-after"))
_TERMINAL_STATES = frozenset(("failed", "passed"))
_DESCRIPTOR_FIELDS = frozenset(
    {
        "schema",
        "replay_id",
        "scenario_role",
        "source",
        "physical_transport_evidence",
        "identity",
        "inventory_digest",
        "stream",
        "stream_format",
        "expected_terminal_state",
    }
)
_HEX_DIGITS = frozenset("0123456789abcdef")
_ASCII_WHITESPACE = frozenset(" \t\r\n")


class TargetReplayError(TestProtocolError):
    """Stable validation failure for a replay descriptor or fixture."""


def _replay_error(code: str, message: str, cause: BaseException | None = None) -> TargetReplayError:
    error = TargetReplayError(code, message)
    if cause is not None:
        raise error from cause
    raise error


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _replay_error("TEST_REPLAY_INVALID", f"{field} must be a lowercase SHA-256")
    return cast(str, value)


def _reject_tuples(value: object) -> None:
    if isinstance(value, tuple):
        _replay_error("TEST_REPLAY_INVALID", "replay JSON input must not contain tuple containers")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key)
            _reject_tuples(item)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item)


@dataclass(frozen=True)
class TargetReplayDescriptor:
    """The complete closed descriptor for one Target replay input."""

    schema: str
    replay_id: str
    scenario_role: Literal["failed-before", "fixed-after"]
    source: str
    physical_transport_evidence: bool
    identity: EvidenceIdentity
    inventory_digest: str
    stream: ArtifactRef
    stream_format: str
    expected_terminal_state: Literal["failed", "passed"]

    def __post_init__(self) -> None:
        if self.schema != TARGET_REPLAY_SCHEMA:
            _replay_error("TEST_REPLAY_INVALID", "schema must be stm32tk-target-replay/1")
        _hash(self.replay_id, "replay_id")
        if self.scenario_role not in _ROLES:
            _replay_error("TEST_REPLAY_INVALID", "scenario_role is invalid")
        if self.source != TARGET_REPLAY_SOURCE:
            _replay_error("TEST_REPLAY_INVALID", "source must be toolkit-generated-protocol-replay")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence is not False:
            _replay_error("TEST_REPLAY_INVALID", "physical_transport_evidence must be exactly false")
        if not isinstance(self.identity, EvidenceIdentity):
            _replay_error("TEST_REPLAY_INVALID", "identity must be an EvidenceIdentity")
        _hash(self.inventory_digest, "inventory_digest")
        if (
            not isinstance(self.stream, ArtifactRef)
            or self.stream.kind != TARGET_REPLAY_STREAM_KIND
            or self.stream.media_type != "application/octet-stream"
            or not self.stream.relative_path.endswith(".bin")
        ):
            _replay_error(
                "TEST_REPLAY_INVALID",
                "stream must be a target-replay-stream binary ArtifactRef",
            )
        if self.stream_format != TARGET_REPLAY_STREAM_FORMAT:
            _replay_error("TEST_REPLAY_INVALID", "stream_format must be stm32-target-frame/1")
        if self.expected_terminal_state not in _TERMINAL_STATES:
            _replay_error("TEST_REPLAY_INVALID", "expected_terminal_state is invalid")
        expected_for_role = {
            "failed-before": "failed",
            "fixed-after": "passed",
        }[self.scenario_role]
        if self.expected_terminal_state != expected_for_role:
            _replay_error("TEST_REPLAY_INVALID", "scenario_role and expected_terminal_state contradict each other")
        if self.replay_id != calculate_replay_id(self):
            _replay_error("TEST_REPLAY_INVALID", "replay_id does not match canonical descriptor intent")

    @classmethod
    def from_value(cls, value: object) -> "TargetReplayDescriptor":
        """Parse one JSON-shaped closed descriptor without accepting extra fields."""

        if type(value) is cls:
            return value
        _reject_tuples(value)
        if not isinstance(value, Mapping) or set(value) != _DESCRIPTOR_FIELDS:
            _replay_error("TEST_REPLAY_INVALID", "TargetReplayDescriptor fields are not closed")
        data = dict(value)
        try:
            identity = EvidenceIdentity.from_dict(data["identity"])
            stream = ArtifactRef.from_dict(data["stream"])
            descriptor = cls(
                schema=cast(str, data["schema"]),
                replay_id=cast(str, data["replay_id"]),
                scenario_role=cast(Literal["failed-before", "fixed-after"], data["scenario_role"]),
                source=cast(str, data["source"]),
                physical_transport_evidence=cast(bool, data["physical_transport_evidence"]),
                identity=identity,
                inventory_digest=cast(str, data["inventory_digest"]),
                stream=stream,
                stream_format=cast(str, data["stream_format"]),
                expected_terminal_state=cast(Literal["failed", "passed"], data["expected_terminal_state"]),
            )
        except TargetReplayError:
            raise
        except (EvidenceValidationError, TypeError, ValueError) as error:
            _replay_error("TEST_REPLAY_INVALID", "TargetReplayDescriptor is invalid", error)
        return descriptor

    def to_dict(self) -> dict[str, object]:
        """Return fresh JSON containers for this descriptor."""

        return {
            "schema": self.schema,
            "replay_id": self.replay_id,
            "scenario_role": self.scenario_role,
            "source": self.source,
            "physical_transport_evidence": self.physical_transport_evidence,
            "identity": self.identity.to_dict(),
            "inventory_digest": self.inventory_digest,
            "stream": self.stream.to_dict(),
            "stream_format": self.stream_format,
            "expected_terminal_state": self.expected_terminal_state,
        }


def canonical_replay_json_bytes(value: object) -> bytes:
    """Return the canonical UTF-8 JSON bytes for a replay value."""

    if isinstance(value, TargetReplayDescriptor):
        value = value.to_dict()
    _reject_tuples(value)
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError, EvidenceValidationError) as error:
        _replay_error("TEST_REPLAY_INVALID", "replay value is not canonical JSON", error)


def calculate_replay_id(value: TargetReplayDescriptor | Mapping[str, object]) -> str:
    """Calculate the SHA-256 of canonical descriptor intent without ``replay_id``."""

    if isinstance(value, TargetReplayDescriptor):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        _reject_tuples(value)
        if set(value) != _DESCRIPTOR_FIELDS:
            _replay_error("TEST_REPLAY_INVALID", "TargetReplayDescriptor fields are not closed")
        payload = dict(value)
    else:
        _replay_error("TEST_REPLAY_INVALID", "replay ID input must be a TargetReplayDescriptor or mapping")
    payload.pop("replay_id", None)
    return hashlib.sha256(canonical_replay_json_bytes(payload)).hexdigest()


def _decode_json(data: bytes) -> object:
    if data.startswith(b"\xef\xbb\xbf"):
        _replay_error("TEST_REPLAY_INVALID", "descriptor JSON must not include a BOM")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                _replay_error("TEST_REPLAY_INVALID", "descriptor JSON has duplicate keys")
            result[key] = item
        return result

    def reject_constant(value: str) -> object:
        _replay_error("TEST_REPLAY_INVALID", f"descriptor JSON has a non-finite constant: {value}")

    try:
        decoded = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except TargetReplayError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _replay_error("TEST_REPLAY_INVALID", "descriptor is not UTF-8 JSON", error)
    canonical = canonical_replay_json_bytes(decoded)
    if data not in {canonical, canonical + b"\n"}:
        _replay_error("TEST_REPLAY_INVALID", "descriptor JSON is not canonical")
    return decoded


def _read_fixture_file(path_value: Path | str, *, maximum_bytes: int, label: str) -> bytes:
    try:
        path = Path(path_value)
    except TypeError as error:
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", f"{label} path is invalid", error)
    try:
        return EvidenceStore._read_file_bytes(path, maximum_bytes=maximum_bytes)
    except EvidenceValidationError as error:
        if error.code in {EVIDENCE_PATH_UNSAFE, EVIDENCE_LIMIT_EXCEEDED}:
            _replay_error("TEST_REPLAY_FIXTURE_UNSAFE", f"{label} is not a bounded singular regular file", error)
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", f"{label} could not be read", error)
    except (FileNotFoundError, OSError) as error:
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", f"{label} could not be read", error)


def _decode_hex_stream(data: bytes, *, maximum_bytes: int) -> bytes:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream is not ASCII", error)
    if text.startswith("\ufeff"):
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream must not include a BOM")
    if any(character not in _HEX_DIGITS and character not in _ASCII_WHITESPACE for character in text):
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream contains a non-hex character")
    compact = "".join(character for character in text if character not in _ASCII_WHITESPACE)
    if not compact or len(compact) % 2 or compact != compact.lower():
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream must be non-empty normalized lowercase hex")
    if len(compact) // 2 > maximum_bytes:
        _replay_error("TEST_REPLAY_FIXTURE_LIMIT", "decoded hex stream exceeds the replay bound")
    try:
        return bytes.fromhex(compact)
    except ValueError as error:
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream is not valid hexadecimal", error)


@dataclass(frozen=True)
class TargetReplayFixture:
    """An immutable descriptor and its verified exact Target frame bytes."""

    descriptor: TargetReplayDescriptor
    stream_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, TargetReplayDescriptor) or not isinstance(self.stream_bytes, bytes):
            _replay_error("TEST_REPLAY_INVALID", "TargetReplayFixture values are invalid")

    @property
    def stream(self) -> bytes:
        """Compatibility spelling for callers that treat the fixture as a byte stream."""

        return self.stream_bytes


def load_target_replay_fixture(
    descriptor_file: Path | str,
    stream_file: Path | str,
    *,
    max_stream_bytes: int = MAX_RUN_STREAM_BYTES,
) -> TargetReplayFixture:
    """Load one bounded canonical descriptor and its auditable hex stream.

    Both paths are read through the evidence store's singular regular-file
    guard.  The stream is decoded from lowercase hexadecimal text, checked
    against the descriptor's exact size and SHA-256, and then passed through
    the existing Target frame decoder/state validator.
    """

    if type(max_stream_bytes) is not int or not 1 <= max_stream_bytes <= MAX_RUN_STREAM_BYTES:
        _replay_error("TEST_REPLAY_FIXTURE_LIMIT", "max_stream_bytes is outside the replay bound")
    descriptor_bytes = _read_fixture_file(
        descriptor_file,
        maximum_bytes=MAX_REPLAY_DESCRIPTOR_BYTES,
        label="descriptor",
    )
    descriptor = TargetReplayDescriptor.from_value(_decode_json(descriptor_bytes))
    try:
        stream_path = Path(stream_file)
    except TypeError as error:
        _replay_error("TEST_REPLAY_FIXTURE_INVALID", "hex stream path is invalid", error)
    if stream_path.suffix != ".hex" or stream_path.name == descriptor.stream.relative_path:
        _replay_error(
            "TEST_REPLAY_FIXTURE_INVALID",
            "hex stream input must be a distinct .hex source, not the binary artifact",
        )
    stream_text_bytes = _read_fixture_file(
        stream_path,
        maximum_bytes=min(MAX_REPLAY_HEX_BYTES, max_stream_bytes * 3 + 2),
        label="hex stream",
    )
    stream_bytes = _decode_hex_stream(stream_text_bytes, maximum_bytes=max_stream_bytes)
    artifact = descriptor.stream
    if artifact.size_bytes != len(stream_bytes):
        _replay_error("TEST_REPLAY_INTEGRITY", "stream byte count contradicts its descriptor")
    if artifact.sha256 != hashlib.sha256(stream_bytes).hexdigest():
        _replay_error("TEST_REPLAY_INTEGRITY", "stream SHA-256 contradicts its descriptor")

    # ``target.py`` imports Probe interfaces, while Probe service imports the
    # testing package.  Keep this dependency at the validation call site so
    # importing the replay descriptor domain never creates that cycle.
    from .target import TargetFrameDecoder, TargetRunBinding, TargetRunValidator

    decoder = TargetFrameDecoder(max_stream_bytes=max_stream_bytes)
    validator = TargetRunValidator(
        TargetRunBinding(
            descriptor.inventory_digest,
            descriptor.identity.build_id,
            descriptor.identity.elf_sha256,
            descriptor.identity.target_device,
        )
    )
    try:
        frames = decoder.feed(stream_bytes)
        for frame in frames:
            validator.accept(frame)
        decoder.finish()
        validator.finish()
    except TestProtocolError:
        raise
    if not frames or frames[-1].kind != 5 or frames[-1].payload.get("state") != descriptor.expected_terminal_state:
        _replay_error("TEST_REPLAY_INTEGRITY", "stream terminal state contradicts its descriptor")
    return TargetReplayFixture(descriptor, stream_bytes)


__all__ = [
    "MAX_REPLAY_DESCRIPTOR_BYTES",
    "MAX_REPLAY_HEX_BYTES",
    "TARGET_REPLAY_SCHEMA",
    "TARGET_REPLAY_SOURCE",
    "TARGET_REPLAY_TRANSPORT",
    "TARGET_REPLAY_STREAM_FORMAT",
    "TARGET_REPLAY_STREAM_KIND",
    "TargetReplayDescriptor",
    "TargetReplayError",
    "TargetReplayFixture",
    "calculate_replay_id",
    "canonical_replay_json_bytes",
    "load_target_replay_fixture",
]
