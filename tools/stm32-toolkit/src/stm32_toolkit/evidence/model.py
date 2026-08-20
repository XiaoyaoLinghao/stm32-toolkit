"""Closed, immutable, canonical evidence envelope records.

The common envelope deliberately has no operation registry.  A producer owns
the closed schema for its own ``operation`` and ``metadata`` fields; callers
may supply that producer validation through the explicit ``metadata_validator``
hook when decoding an envelope.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from types import MappingProxyType
from typing import TypeVar, cast
from unicodedata import normalize
from uuid import UUID


EVIDENCE_SCHEMA = "stm32-evidence/1"
MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_STRING_BYTES = 64 * 1024
MAX_PARENTS = 64
MAX_ARTIFACTS = 4_096
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
MAX_JSON_INTEGER = 2**63 - 1
MIN_JSON_INTEGER = -(2**63)

EVIDENCE_INVALID = "EVIDENCE_INVALID"
EVIDENCE_CORRUPT = "EVIDENCE_CORRUPT"
EVIDENCE_PATH_UNSAFE = "EVIDENCE_PATH_UNSAFE"
EVIDENCE_LIMIT_EXCEEDED = "EVIDENCE_LIMIT_EXCEEDED"

_EVIDENCE_VALIDATION_CODES = frozenset(
    {
        EVIDENCE_INVALID,
        EVIDENCE_CORRUPT,
        EVIDENCE_PATH_UNSAFE,
        EVIDENCE_LIMIT_EXCEEDED,
    }
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SESSION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

_T = TypeVar("_T")
MetadataValidator = Callable[[str, dict[str, object]], None]
_UNSET_EVIDENCE_ID = object()


class EvidenceValidationError(ValueError):
    """An evidence record or canonical JSON value failed closed validation."""

    def __init__(self, code: str, message: str) -> None:
        if type(code) is not str or code not in _EVIDENCE_VALIDATION_CODES:
            raise ValueError("unknown evidence validation error code")
        if type(message) is not str:
            raise TypeError("evidence validation error message must be a string")
        ValueError.__init__(self, message)
        self._code = code
        self._message = message

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message


@dataclass
class _JsonState:
    nodes: int = 0

    def visit(self, depth: int) -> None:
        if depth > MAX_JSON_DEPTH:
            raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "JSON nesting exceeds the evidence limit")
        self.nodes += 1
        if self.nodes > MAX_JSON_NODES:
            raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "JSON node count exceeds the evidence limit")


def _require_bounded_string(
    field: str,
    value: object,
    *,
    nonempty: bool = True,
    allow_controls: bool = False,
) -> str:
    if not isinstance(value, str):
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} must be a string")
    if nonempty and not value:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} must not be empty")
    if normalize("NFC", value) != value:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} must use NFC")
    if len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, f"{field} exceeds the string limit")
    if not allow_controls and any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} contains a control character")
    return value


def _require_hash(field: str, value: object) -> str:
    string = _require_bounded_string(field, value)
    if _HASH.fullmatch(string) is None:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} must be a lowercase SHA-256")
    return string


def _require_integer(field: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{field} must be an integer in range")
    return cast(int, value)


def _require_keys(value: object, expected: set[str], record: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"{record} fields are not closed")
    return value


def _validate_session_id(value: object) -> str:
    session_id = _require_bounded_string("session_id", value)
    if _SESSION_ID.fullmatch(session_id) is None:
        raise EvidenceValidationError(EVIDENCE_INVALID, "session_id must be lowercase ASCII")
    return session_id


def _validate_project_id(value: object) -> str:
    project_id = _require_bounded_string("project_id", value)
    try:
        parsed = UUID(project_id)
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(EVIDENCE_INVALID, "project_id must be a canonical UUID") from exc
    if str(parsed) != project_id:
        raise EvidenceValidationError(EVIDENCE_INVALID, "project_id must be a lowercase canonical UUID")
    return project_id


def _validate_utc(value: object) -> str:
    timestamp = _require_bounded_string("produced_at_utc", value)
    if _UTC.fullmatch(timestamp) is None:
        raise EvidenceValidationError(EVIDENCE_INVALID, "produced_at_utc must use UTC microseconds")
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise EvidenceValidationError(EVIDENCE_INVALID, "produced_at_utc is not a valid UTC timestamp") from exc
    return timestamp


def _validate_relative_path(value: object) -> str:
    path = _require_bounded_string("relative_path", value)
    if len(path.encode("utf-8")) > 512:
        raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "relative_path exceeds 512 UTF-8 bytes")
    if path.startswith(("/", "\\")) or "\\" in path or ":" in path:
        raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "relative_path is not POSIX-relative")
    parts = path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "relative_path contains an unsafe segment")
    for part in parts:
        if part.endswith((".", " ")):
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "relative_path has an ambiguous trailing character")
        base = part.split(".", 1)[0].upper()
        if base in _WINDOWS_RESERVED:
            raise EvidenceValidationError(EVIDENCE_PATH_UNSAFE, "relative_path uses a reserved Windows name")
    return path


def _copy_json(value: object, state: _JsonState, depth: int = 1) -> object:
    state.visit(depth)
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not MIN_JSON_INTEGER <= value <= MAX_JSON_INTEGER:
            raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "JSON integer is out of range")
        return value
    if isinstance(value, str):
        return _require_bounded_string("JSON string", value, nonempty=False, allow_controls=True)
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            key = _require_bounded_string("JSON object key", key, nonempty=False, allow_controls=True)
            if key in copied:
                raise EvidenceValidationError(EVIDENCE_INVALID, "duplicate JSON object key")
            copied[key] = _copy_json(item, state, depth + 1)
        return copied
    if isinstance(value, (list, tuple)):
        return [_copy_json(item, state, depth + 1) for item in value]
    raise EvidenceValidationError(EVIDENCE_INVALID, "JSON value has an unsupported type")


def _canonical_json_value(value: object) -> object:
    return _copy_json(value, _JsonState())


def _reject_tuple_containers(value: object, depth: int = 1) -> None:
    """Keep Python-only tuples out of dictionary and JSON decoding boundaries."""
    if depth > MAX_JSON_DEPTH:
        raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "JSON nesting exceeds the evidence limit")
    if isinstance(value, tuple):
        raise EvidenceValidationError(EVIDENCE_INVALID, "JSON input must not contain tuple containers")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuple_containers(key, depth + 1)
            _reject_tuple_containers(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_tuple_containers(item, depth + 1)


def canonical_json_bytes(value: object) -> bytes:
    """Return the strict, compact NFC UTF-8 encoding of a JSON-safe value."""
    copied = _canonical_json_value(value)
    return json.dumps(copied, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _decode_authoritative_json(data: bytes) -> object:
    if not isinstance(data, bytes) or len(data) > MAX_ENVELOPE_BYTES:
        raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "envelope bytes exceed the evidence limit")
    if data.startswith(b"\xef\xbb\xbf"):
        raise EvidenceValidationError(EVIDENCE_INVALID, "authoritative JSON must not include a BOM")

    def pairs(pairs_value: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs_value:
            if key in result:
                raise EvidenceValidationError(EVIDENCE_INVALID, "authoritative JSON has duplicate keys")
            result[key] = value
        return result

    def reject_number(text: str) -> object:
        raise EvidenceValidationError(EVIDENCE_INVALID, f"non-integer JSON number is forbidden: {text}")

    try:
        decoded = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(EVIDENCE_INVALID, "authoritative JSON is invalid UTF-8 JSON") from exc
    if canonical_json_bytes(decoded) != data:
        raise EvidenceValidationError(EVIDENCE_INVALID, "authoritative JSON is not canonical")
    return decoded


def _validate_identity_shared_fields(
    *,
    workspace_id: object,
    project_id: object,
    session_id: object,
    target_device: object,
    input_snapshot_sha256: object,
    git_commit: object,
    git_dirty: object,
) -> None:
    """Validate the caller-owned fields shared by complete identities and contexts."""
    _require_hash("workspace_id", workspace_id)
    _validate_project_id(project_id)
    _validate_session_id(session_id)
    _require_bounded_string("target_device", target_device)
    _require_hash("input_snapshot_sha256", input_snapshot_sha256)
    if _GIT_COMMIT.fullmatch(_require_bounded_string("git_commit", git_commit)) is None:
        raise EvidenceValidationError(EVIDENCE_INVALID, "git_commit must be a lowercase Git SHA-1")
    if type(git_dirty) is not bool:
        raise EvidenceValidationError(EVIDENCE_INVALID, "git_dirty must be a JSON boolean")


@dataclass(frozen=True)
class EvidenceIdentity:
    workspace_id: str
    project_id: str
    session_id: str
    build_id: str
    elf_sha256: str
    target_device: str
    input_snapshot_sha256: str
    git_commit: str
    git_dirty: bool

    def __post_init__(self) -> None:
        _validate_identity_shared_fields(
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            session_id=self.session_id,
            target_device=self.target_device,
            input_snapshot_sha256=self.input_snapshot_sha256,
            git_commit=self.git_commit,
            git_dirty=self.git_dirty,
        )
        _require_hash("build_id", self.build_id)
        _require_hash("elf_sha256", self.elf_sha256)

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceIdentity":
        data = _require_keys(
            value,
            {
                "workspace_id", "project_id", "session_id", "build_id", "elf_sha256",
                "target_device", "input_snapshot_sha256", "git_commit", "git_dirty",
            },
            "EvidenceIdentity",
        )
        return cls(**cast(dict[str, object], dict(data)))

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "build_id": self.build_id,
            "elf_sha256": self.elf_sha256,
            "target_device": self.target_device,
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
        }


@dataclass(frozen=True)
class EvidenceIdentityContext:
    """Caller-owned identity fields that Host discovery completes with its digests."""

    workspace_id: str
    project_id: str
    session_id: str
    target_device: str
    input_snapshot_sha256: str
    git_commit: str
    git_dirty: bool

    def __post_init__(self) -> None:
        _validate_identity_shared_fields(
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            session_id=self.session_id,
            target_device=self.target_device,
            input_snapshot_sha256=self.input_snapshot_sha256,
            git_commit=self.git_commit,
            git_dirty=self.git_dirty,
        )

    def bind(self, *, build_id: str, elf_sha256: str) -> EvidenceIdentity:
        return EvidenceIdentity(
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            session_id=self.session_id,
            build_id=build_id,
            elf_sha256=elf_sha256,
            target_device=self.target_device,
            input_snapshot_sha256=self.input_snapshot_sha256,
            git_dirty=self.git_dirty,
            git_commit=self.git_commit,
        )


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    size_bytes: int
    relative_path: str
    kind: str
    media_type: str

    def __post_init__(self) -> None:
        _require_hash("sha256", self.sha256)
        _require_integer("size_bytes", self.size_bytes, 0, MAX_ARTIFACT_BYTES)
        _validate_relative_path(self.relative_path)
        _require_bounded_string("kind", self.kind)
        _require_bounded_string("media_type", self.media_type)

    @classmethod
    def from_dict(cls, value: object) -> "ArtifactRef":
        data = _require_keys(value, {"sha256", "size_bytes", "relative_path", "kind", "media_type"}, "ArtifactRef")
        return cls(**cast(dict[str, object], dict(data)))

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "relative_path": self.relative_path,
            "kind": self.kind,
            "media_type": self.media_type,
        }


@dataclass(frozen=True)
class EvidenceEnvelope:
    identity: EvidenceIdentity
    operation: str
    produced_at_utc: str
    parents: tuple[str, ...]
    artifacts: tuple[ArtifactRef, ...]
    metadata: Mapping[str, object]
    schema: str = EVIDENCE_SCHEMA
    evidence_id: object = _UNSET_EVIDENCE_ID

    def __post_init__(self) -> None:
        if self.schema != EVIDENCE_SCHEMA:
            raise EvidenceValidationError(EVIDENCE_INVALID, "schema must be stm32-evidence/1")
        if not isinstance(self.identity, EvidenceIdentity):
            raise EvidenceValidationError(EVIDENCE_INVALID, "identity must be an EvidenceIdentity")
        _require_bounded_string("operation", self.operation)
        _validate_utc(self.produced_at_utc)
        if not isinstance(self.parents, tuple) or not isinstance(self.artifacts, tuple):
            raise EvidenceValidationError(EVIDENCE_INVALID, "parents and artifacts must be tuples")
        parents = self.parents
        artifacts = self.artifacts
        if len(parents) > MAX_PARENTS or len(artifacts) > MAX_ARTIFACTS:
            raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "envelope collection exceeds the evidence limit")
        for parent in parents:
            _require_hash("parent evidence_id", parent)
        if not all(isinstance(artifact, ArtifactRef) for artifact in artifacts):
            raise EvidenceValidationError(EVIDENCE_INVALID, "artifacts must be ArtifactRef values")
        metadata = _canonical_json_value(self.metadata)
        if not isinstance(metadata, dict):
            raise EvidenceValidationError(EVIDENCE_INVALID, "metadata must be a canonical JSON object")
        object.__setattr__(self, "parents", parents)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "metadata", cast(Mapping[str, object], _freeze_json(metadata)))
        calculated = calculate_evidence_id(self)
        if self.evidence_id is not _UNSET_EVIDENCE_ID:
            _require_hash("evidence_id", self.evidence_id)
            if self.evidence_id != calculated:
                raise EvidenceValidationError(EVIDENCE_INVALID, "evidence_id does not match canonical envelope content")
        object.__setattr__(self, "evidence_id", calculated)
        if len(self.to_json_bytes()) > MAX_ENVELOPE_BYTES:
            raise EvidenceValidationError(EVIDENCE_LIMIT_EXCEEDED, "envelope JSON exceeds 1 MiB")

    @classmethod
    def from_dict(
        cls,
        value: object,
        *,
        metadata_validator: MetadataValidator | None = None,
    ) -> "EvidenceEnvelope":
        _reject_tuple_containers(value)
        copied = _canonical_json_value(value)
        data = _require_keys(
            copied,
            {"schema", "evidence_id", "identity", "operation", "produced_at_utc", "parents", "artifacts", "metadata"},
            "EvidenceEnvelope",
        )
        parents = data["parents"]
        artifacts = data["artifacts"]
        if not isinstance(parents, list) or not isinstance(artifacts, list):
            raise EvidenceValidationError(EVIDENCE_INVALID, "parents and artifacts must be JSON arrays")
        envelope = cls(
            schema=cast(str, data["schema"]),
            evidence_id=data["evidence_id"],
            identity=EvidenceIdentity.from_dict(data["identity"]),
            operation=cast(str, data["operation"]),
            produced_at_utc=cast(str, data["produced_at_utc"]),
            parents=tuple(cast(list[object], parents)),
            artifacts=tuple(ArtifactRef.from_dict(item) for item in artifacts),
            metadata=cast(Mapping[str, object], data["metadata"]),
        )
        if metadata_validator is not None:
            metadata_validator(envelope.operation, cast(dict[str, object], _thaw_json(envelope.metadata)))
        return envelope

    @classmethod
    def from_json_bytes(
        cls,
        data: bytes,
        *,
        metadata_validator: MetadataValidator | None = None,
    ) -> "EvidenceEnvelope":
        return cls.from_dict(_decode_authoritative_json(data), metadata_validator=metadata_validator)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "evidence_id": self.evidence_id,
            "identity": self.identity.to_dict(),
            "operation": self.operation,
            "produced_at_utc": self.produced_at_utc,
            "parents": list(self.parents),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "metadata": cast(dict[str, object], _thaw_json(self.metadata)),
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


def calculate_evidence_id(value: EvidenceEnvelope | Mapping[str, object]) -> str:
    """Calculate the SHA-256 of canonical envelope JSON with ``evidence_id`` omitted."""
    if isinstance(value, EvidenceEnvelope):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = cast(dict[str, object], _canonical_json_value(value))
    else:
        raise EvidenceValidationError(EVIDENCE_INVALID, "evidence digest input must be an envelope object")
    payload.pop("evidence_id", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
