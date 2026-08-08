from __future__ import annotations

import re
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, cast
from uuid import UUID, uuid4

from stm32_toolkit.paths import require_safe_session_id


MAX_SELECTOR_CHARS = 512
MAX_GROUP_NAME_CHARS = 128
MAX_DESCRIPTION_CHARS = 1024
MIN_INTERVAL_MS = 100
MAX_INTERVAL_MS = 5_000
MAX_SAMPLE_VALUES = 256
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 10_000
MAX_JSON_STRING_CHARS = 1024 * 1024
MIN_SIGNED_INT64 = -(1 << 63)
MAX_SIGNED_INT64 = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WORKSPACE_ID = re.compile(r"[0-9a-f]{24}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


_MAPPING_PROXY = type(MappingProxyType({}))


def _freeze_json(value: object) -> object:
    nodes = 0
    string_chars = 0
    active: set[int] = set()

    def freeze(current: object, depth: int) -> object:
        nonlocal nodes, string_chars
        if depth > MAX_JSON_DEPTH:
            raise ValueError("JSON value exceeds its depth limit")
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError("JSON value exceeds its node limit")
        if current is None or type(current) is bool:
            return current
        if type(current) is int:
            if not MIN_SIGNED_INT64 <= current <= MAX_SIGNED_INT64:
                raise ValueError("JSON integer exceeds the signed 64-bit limit")
            return current
        if type(current) is float:
            if not math.isfinite(current):
                raise ValueError("JSON number must be finite")
            return current
        if type(current) is str:
            string_chars += len(current)
            if string_chars > MAX_JSON_STRING_CHARS:
                raise ValueError("JSON value exceeds its string limit")
            return current
        if type(current) in (list, tuple):
            identity = id(current)
            if identity in active:
                raise ValueError("JSON value contains a cycle")
            active.add(identity)
            try:
                return tuple(freeze(item, depth + 1) for item in current)
            finally:
                active.remove(identity)
        if type(current) in (dict, _MAPPING_PROXY):
            identity = id(current)
            if identity in active:
                raise ValueError("JSON value contains a cycle")
            active.add(identity)
            result: dict[str, object] = {}
            try:
                for key, item in current.items():
                    if type(key) is not str:
                        raise TypeError("JSON object keys must be strings")
                    normalized = unicodedata.normalize("NFC", key)
                    string_chars += len(normalized)
                    if string_chars > MAX_JSON_STRING_CHARS:
                        raise ValueError("JSON value exceeds its string limit")
                    if normalized in result:
                        raise ValueError("JSON object keys must be unique after normalization")
                    result[normalized] = freeze(item, depth + 1)
            finally:
                active.remove(identity)
            return MappingProxyType(result)
        if type(current) in (set, frozenset):
            raise TypeError("sets are not JSON values")
        raise TypeError("value is not an exact JSON value")

    return freeze(value, 0)


def _thaw_json(value: object) -> object:
    if type(value) is _MAPPING_PROXY:
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise TypeError("value is not a frozen JSON value")


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include UTC timezone")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def unix_ns_to_utc(value: int) -> str:
    if type(value) is not int or not 0 <= value <= MAX_SIGNED_INT64:
        raise ValueError("Unix nanoseconds must be a non-negative signed 64-bit integer")
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    try:
        timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
            microsecond=nanoseconds // 1_000
        )
    except (OSError, OverflowError, ValueError):
        raise ValueError("Unix nanoseconds are outside the serializable range") from None
    return _utc_text(timestamp)


def _require_text(value: str, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} is invalid")
    normalized = unicodedata.normalize("NFC", value.strip())
    if (not normalized and not allow_empty) or len(normalized) > maximum:
        raise ValueError(f"{label} is invalid")
    return normalized


def _require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value.lower()) is None:
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value.lower()


@dataclass(frozen=True)
class MonitorConfig:
    project_root: Path
    data_root: Path
    session_id: str

    def __post_init__(self) -> None:
        try:
            project = Path(self.project_root).expanduser().resolve(strict=True)
        except OSError as error:
            raise ValueError("project root must be a directory") from error
        if not project.is_dir():
            raise ValueError("project root must be a directory")
        data = Path(self.data_root).expanduser().resolve(strict=False)
        try:
            data.relative_to(project)
        except ValueError:
            pass
        else:
            raise ValueError("data root must remain outside project root")
        object.__setattr__(self, "project_root", project)
        object.__setattr__(self, "data_root", data)
        object.__setattr__(self, "session_id", require_safe_session_id(self.session_id))


@dataclass(frozen=True)
class ProbeConnectRequest:
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", _require_text(self.probe_id, "probe ID", 256))
        object.__setattr__(self, "expected_build_id", _require_sha256(self.expected_build_id, "build ID"))
        object.__setattr__(self, "expected_elf_sha256", _require_sha256(self.expected_elf_sha256, "ELF digest"))

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "expectedBuildId": self.expected_build_id,
            "expectedElfSha256": self.expected_elf_sha256,
        }


@dataclass(frozen=True)
class WatchItem:
    kind: str
    selector: str

    def __post_init__(self) -> None:
        if self.kind not in {"variable", "register"}:
            raise ValueError("watch kind is invalid")
        object.__setattr__(self, "selector", _require_text(self.selector, "watch selector", MAX_SELECTOR_CHARS))

    @classmethod
    def variable(cls, expression: str) -> "WatchItem":
        return cls("variable", expression)

    @classmethod
    def register(cls, register_path: str) -> "WatchItem":
        return cls("register", register_path)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "WatchItem":
        if set(value) == {"kind", "expression"} and value.get("kind") == "variable":
            return cls.variable(cast(str, value["expression"]))
        if set(value) == {"kind", "registerPath"} and value.get("kind") == "register":
            return cls.register(cast(str, value["registerPath"]))
        raise ValueError("watch item is invalid")

    def to_dict(self) -> dict[str, object]:
        field_name = "expression" if self.kind == "variable" else "registerPath"
        return {"kind": self.kind, field_name: self.selector}


@dataclass(frozen=True)
class WatchGroup:
    group_id: UUID
    name: str
    description: str
    interval_ms: int
    items: tuple[WatchItem, ...]
    revision: int
    created_at_utc: datetime
    updated_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, UUID):
            raise ValueError("group ID must be a UUID")
        object.__setattr__(self, "name", _require_text(self.name, "group name", MAX_GROUP_NAME_CHARS))
        object.__setattr__(self, "description", _require_text(self.description, "description", MAX_DESCRIPTION_CHARS, allow_empty=True))
        if not isinstance(self.interval_ms, int) or isinstance(self.interval_ms, bool) or not MIN_INTERVAL_MS <= self.interval_ms <= MAX_INTERVAL_MS:
            raise ValueError("interval must be between 100 and 5000 milliseconds")
        items = tuple(self.items)
        if not all(isinstance(item, WatchItem) for item in items):
            raise ValueError("group items are invalid")
        if len(set(items)) != len(items):
            raise ValueError("group items must be unique")
        object.__setattr__(self, "items", items)
        if type(self.revision) is not int or not 1 <= self.revision <= MAX_SIGNED_INT64:
            raise ValueError("revision must be positive")
        _utc_text(self.created_at_utc)
        _utc_text(self.updated_at_utc)

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        interval_ms: int,
        items: Sequence[WatchItem],
        *,
        group_id: UUID | None = None,
        now: datetime | None = None,
    ) -> "WatchGroup":
        timestamp = now if now is not None else datetime.now(timezone.utc)
        return cls(group_id or uuid4(), name, description, interval_ms, tuple(items), 1, timestamp, timestamp)

    def to_dict(self) -> dict[str, object]:
        return {
            "groupId": str(self.group_id),
            "name": self.name,
            "description": self.description,
            "intervalMs": self.interval_ms,
            "items": [item.to_dict() for item in self.items],
            "revision": self.revision,
            "createdAtUtc": _utc_text(self.created_at_utc),
            "updatedAtUtc": _utc_text(self.updated_at_utc),
        }


@dataclass(frozen=True)
class ObservationBinding:
    workspace_id: str
    logical_project_id: str
    session_id: str
    probe_id: str
    target_device: str
    physical_target: str
    build_id: str
    elf_sha256: str
    input_snapshot_sha256: str
    git_head: str
    git_dirty: bool
    flash_session_id: str
    lease_id: str
    dwarf_sha256: str
    svd_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or _WORKSPACE_ID.fullmatch(self.workspace_id.lower()) is None:
            raise ValueError("workspace ID is invalid")
        object.__setattr__(self, "workspace_id", self.workspace_id.lower())
        UUID(self.logical_project_id)
        object.__setattr__(self, "session_id", require_safe_session_id(self.session_id))
        for field_name in ("probe_id", "target_device", "physical_target", "flash_session_id", "lease_id"):
            object.__setattr__(self, field_name, _require_text(getattr(self, field_name), field_name, 256))
        for field_name in ("build_id", "elf_sha256", "input_snapshot_sha256", "dwarf_sha256"):
            object.__setattr__(self, field_name, _require_sha256(getattr(self, field_name), field_name))
        if self.svd_sha256 is not None:
            object.__setattr__(self, "svd_sha256", _require_sha256(self.svd_sha256, "SVD digest"))
        if not isinstance(self.git_head, str) or _GIT_SHA.fullmatch(self.git_head.lower()) is None:
            raise ValueError("Git HEAD is invalid")
        if type(self.git_dirty) is not bool:
            raise ValueError("Git dirty state is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ObservationBinding":
        expected = {
            "workspaceId", "logicalProjectId", "sessionId", "probeId", "targetDevice",
            "physicalTarget", "buildId", "elfSha256", "inputSnapshotSha256", "gitHead",
            "gitDirty", "flashSessionId", "leaseId", "dwarfSha256", "svdSha256",
        }
        if set(value) != expected:
            raise ValueError("observation binding is invalid")
        return cls(
            workspace_id=cast(str, value["workspaceId"]),
            logical_project_id=cast(str, value["logicalProjectId"]),
            session_id=cast(str, value["sessionId"]),
            probe_id=cast(str, value["probeId"]),
            target_device=cast(str, value["targetDevice"]),
            physical_target=cast(str, value["physicalTarget"]),
            build_id=cast(str, value["buildId"]),
            elf_sha256=cast(str, value["elfSha256"]),
            input_snapshot_sha256=cast(str, value["inputSnapshotSha256"]),
            git_head=cast(str, value["gitHead"]),
            git_dirty=cast(bool, value["gitDirty"]),
            flash_session_id=cast(str, value["flashSessionId"]),
            lease_id=cast(str, value["leaseId"]),
            dwarf_sha256=cast(str, value["dwarfSha256"]),
            svd_sha256=cast(str | None, value["svdSha256"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "workspaceId": self.workspace_id,
            "logicalProjectId": self.logical_project_id,
            "sessionId": self.session_id,
            "probeId": self.probe_id,
            "targetDevice": self.target_device,
            "physicalTarget": self.physical_target,
            "buildId": self.build_id,
            "elfSha256": self.elf_sha256,
            "inputSnapshotSha256": self.input_snapshot_sha256,
            "gitHead": self.git_head,
            "gitDirty": self.git_dirty,
            "flashSessionId": self.flash_session_id,
            "leaseId": self.lease_id,
            "dwarfSha256": self.dwarf_sha256,
            "svdSha256": self.svd_sha256,
        }


@dataclass(frozen=True)
class SampleValue:
    watch: WatchItem
    status: str
    typed_value: object | None = None
    code: str | None = None
    definition: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.watch, WatchItem):
            raise ValueError("sample watch is invalid")
        if self.status not in {"OK", "ERROR"}:
            raise ValueError("sample status is invalid")
        if self.status == "OK":
            if self.typed_value is None:
                raise ValueError("successful sample requires a typed value")
            if self.code is not None:
                raise ValueError("successful sample cannot include an error code")
        else:
            if self.typed_value is not None:
                raise ValueError("failed sample cannot include a typed value")
            object.__setattr__(self, "code", _require_text(self.code, "sample code", 128))
        object.__setattr__(self, "typed_value", _freeze_json(self.typed_value))
        if self.definition is not None:
            definition = _freeze_json(self.definition)
            if type(definition) is not _MAPPING_PROXY:
                raise TypeError("sample definition must be a JSON object")
            object.__setattr__(self, "definition", cast(Mapping[str, object], definition))

    def to_dict(self) -> dict[str, object]:
        return {
            "watch": self.watch.to_dict(),
            "status": self.status,
            "typedValue": _thaw_json(self.typed_value),
            "code": self.code,
            "definition": None if self.definition is None else _thaw_json(self.definition),
        }


@dataclass(frozen=True)
class SampleBatch:
    binding: ObservationBinding
    group_id: UUID
    group_revision: int
    run_id: UUID
    sequence: int
    scheduled_unix_ns: int
    captured_unix_ns: int
    latency_ns: int
    actual_rate_hz: float
    subscriber_drops: int
    history_drops: int
    deadline_drops: int
    values: tuple[SampleValue, ...]

    def __post_init__(self) -> None:
        if type(self.binding) is not ObservationBinding:
            raise ValueError("batch binding is invalid")
        if not isinstance(self.group_id, UUID) or not isinstance(self.run_id, UUID):
            raise ValueError("batch identifiers must be UUIDs")
        for name in ("group_revision", "sequence", "scheduled_unix_ns", "captured_unix_ns", "latency_ns", "subscriber_drops", "history_drops", "deadline_drops"):
            value = getattr(self, name)
            minimum = 1 if name == "group_revision" else 0
            if type(value) is not int or not minimum <= value <= MAX_SIGNED_INT64:
                raise ValueError(f"{name} is invalid")
        if self.captured_unix_ns < self.scheduled_unix_ns:
            raise ValueError("captured time precedes scheduled time")
        if type(self.actual_rate_hz) not in (int, float) or not math.isfinite(
            float(self.actual_rate_hz)
        ) or self.actual_rate_hz < 0:
            raise ValueError("actual rate is invalid")
        values = tuple(self.values)
        if not all(isinstance(value, SampleValue) for value in values):
            raise ValueError("sample values are invalid")
        if len(values) > MAX_SAMPLE_VALUES:
            raise ValueError("sample values exceed the batch limit")
        unix_ns_to_utc(self.scheduled_unix_ns)
        unix_ns_to_utc(self.captured_unix_ns)
        object.__setattr__(self, "values", values)

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "groupId": str(self.group_id),
            "groupRevision": self.group_revision,
            "runId": str(self.run_id),
            "sequence": self.sequence,
            "scheduledUnixNs": self.scheduled_unix_ns,
            "scheduledAtUtc": unix_ns_to_utc(self.scheduled_unix_ns),
            "capturedUnixNs": self.captured_unix_ns,
            "capturedAtUtc": unix_ns_to_utc(self.captured_unix_ns),
            "latencyNs": self.latency_ns,
            "actualRateHz": float(self.actual_rate_hz),
            "subscriberDrops": self.subscriber_drops,
            "historyDrops": self.history_drops,
            "deadlineDrops": self.deadline_drops,
            "values": [value.to_dict() for value in self.values],
        }
