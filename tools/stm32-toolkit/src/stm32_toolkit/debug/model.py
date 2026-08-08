"""Immutable, JSON-safe contracts shared by typed debug operations."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, cast

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
_RAW_HEX = re.compile(r"^0x[0-9a-f]+$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_FLOAT_SYMBOLS = {"nan", "positiveInfinity", "negativeInfinity"}
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_REGISTER_ACCESS = {"read-only", "read-write", "readOnce", "read-writeOnce"}
_REGISTER_SIDE_EFFECTS = {None, "none", "read-clear", "read-set", "modify", "unknown"}
_MAX_REPORT_ITEMS = 256
_MAX_SAMPLES = 10_000
_MAX_JSON_NODES = 200_000
_MAX_JSON_STRING_CHARS = 4_000_000


def _integer(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is out of range")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} must be a portable identifier")
    return value


def _portable_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("path must be a portable project-relative path")
    path = Path(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("path must be a portable project-relative path")
    return value


def _freeze_json(
    value: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    budget = [0, 0] if _budget is None else _budget
    if _depth > 64:
        raise ValueError("JSON value exceeds the nesting budget")
    budget[0] += 1
    if budget[0] > _MAX_JSON_NODES:
        raise ValueError("JSON value exceeds the node budget")
    if isinstance(value, str):
        budget[1] += len(value)
        if budget[1] > _MAX_JSON_STRING_CHARS:
            raise ValueError("JSON value exceeds the string budget")
    if value is None or isinstance(value, (bool, str)):
        return value
    if type(value) is int:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats require symbolic evidence")
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON mappings require string keys")
            budget[1] += len(key)
            if budget[1] > _MAX_JSON_STRING_CHARS:
                raise ValueError("JSON value exceeds the string budget")
            frozen[key] = _freeze_json(item, _depth=_depth + 1, _budget=budget)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, _depth=_depth + 1, _budget=budget) for item in value
        )
    raise TypeError("value must be JSON-safe")


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _text(name: str, value: object, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _timestamp(name: str, value: object) -> str:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")
    return value


def _raw_hex_width(value: object, bit_width: int) -> str:
    if not isinstance(value, str) or _RAW_HEX.fullmatch(value) is None:
        raise ValueError("raw_hex is invalid")
    if len(value) != 2 + (bit_width + 3) // 4 or int(value[2:], 16) >= 1 << bit_width:
        raise ValueError("raw_hex width does not match bit_width")
    return value


def _json_budget(value: object) -> None:
    nodes = 0
    characters = 0
    pending = [value]
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise ValueError("JSON output exceeds the node budget")
        if isinstance(item, str):
            characters += len(item)
            if characters > _MAX_JSON_STRING_CHARS:
                raise ValueError("JSON output exceeds the string budget")
        elif isinstance(item, MappingABC):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, tuple):
            pending.extend(item)


@dataclass(frozen=True)
class DebugBindingRequest:
    project_root: Path = field(repr=False)
    probe_id: str
    target: str
    workspace_id: str
    observation_session_id: str
    lease_id: str
    expected_build_id: str
    expected_elf_sha256: str


@dataclass(frozen=True)
class MemoryRegionBinding:
    name: str
    origin: int
    length: int
    attributes: str

    def __post_init__(self) -> None:
        _identifier("name", self.name)
        _integer("origin", self.origin, 0, 0xFFFF_FFFF)
        _integer("length", self.length, 1, 0x1_0000_0000)
        if self.origin + self.length > 0x1_0000_0000:
            raise ValueError("memory region exceeds the address space")
        if not isinstance(self.attributes, str) or not self.attributes or any(
            character not in "rwx-" for character in self.attributes
        ):
            raise ValueError("memory attributes are invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "length": self.length,
            "attributes": self.attributes,
        }


@dataclass(frozen=True)
class DebugFirmwareBinding:
    logical_project_id: str
    workspace_id: str
    observation_session_id: str
    flash_session_id: str
    lease_id: str
    probe_id: str
    target_device: str
    debug_target: str
    build_id: str
    elf_sha256: str
    elf_size: int
    elf_path: str
    input_snapshot_sha256: str
    git_head: str
    git_dirty: bool
    confirmed_at_utc: str
    memory_regions: tuple[MemoryRegionBinding, ...]
    project_root: Path = field(repr=False, compare=True)

    def __post_init__(self) -> None:
        for name in (
            "logical_project_id",
            "workspace_id",
            "observation_session_id",
            "flash_session_id",
            "lease_id",
            "probe_id",
            "target_device",
            "debug_target",
        ):
            _identifier(name, getattr(self, name))
        for name in ("build_id", "elf_sha256", "input_snapshot_sha256"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a SHA-256 digest")
        if not isinstance(self.git_head, str) or not self.git_head:
            raise ValueError("git_head is invalid")
        if type(self.git_dirty) is not bool:
            raise TypeError("git_dirty must be a boolean")
        _integer("elf_size", self.elf_size, 1, 64 * 1024 * 1024)
        _portable_path(self.elf_path)
        _timestamp("confirmed_at_utc", self.confirmed_at_utc)
        if type(self.memory_regions) is not tuple or not self.memory_regions or not all(
            isinstance(region, MemoryRegionBinding) for region in self.memory_regions
        ):
            raise TypeError("memory_regions must be a non-empty tuple")
        if not isinstance(self.project_root, Path):
            raise TypeError("project_root must be a Path")
        try:
            canonical = self.project_root.resolve(strict=True)
        except (OSError, RuntimeError):
            raise ValueError("project_root must exist") from None
        if (
            not self.project_root.is_absolute()
            or canonical != self.project_root
            or not canonical.is_dir()
        ):
            raise ValueError("project_root must be a canonical absolute directory")

    def to_dict(self) -> dict[str, object]:
        return {
            "logicalProjectId": self.logical_project_id,
            "workspaceId": self.workspace_id,
            "observationSessionId": self.observation_session_id,
            "flashSessionId": self.flash_session_id,
            "leaseId": self.lease_id,
            "probeId": self.probe_id,
            "targetDevice": self.target_device,
            "debugTarget": self.debug_target,
            "buildId": self.build_id,
            "elfSha256": self.elf_sha256,
            "elfSize": self.elf_size,
            "elfPath": self.elf_path,
            "inputSnapshotSha256": self.input_snapshot_sha256,
            "gitHead": self.git_head,
            "gitDirty": self.git_dirty,
            "confirmedAtUtc": self.confirmed_at_utc,
            "memoryRegions": [region.to_dict() for region in self.memory_regions],
        }


@dataclass(frozen=True)
class IntegerEvidence:
    decimal: str
    raw_hex: str
    bit_width: int
    signed: bool

    def __post_init__(self) -> None:
        width = _integer("bit_width", self.bit_width, 1, 64)
        if type(self.signed) is not bool:
            raise TypeError("signed must be a boolean")
        if not isinstance(self.decimal, str) or _DECIMAL.fullmatch(self.decimal) is None:
            raise ValueError("decimal must be a canonical integer string")
        if not isinstance(self.raw_hex, str) or _RAW_HEX.fullmatch(self.raw_hex) is None:
            raise ValueError("raw_hex must be canonical lowercase hexadecimal")
        if len(self.raw_hex) != 2 + (width + 3) // 4:
            raise ValueError("raw_hex width does not match bit_width")
        raw = int(self.raw_hex[2:], 16)
        if raw >= 1 << width:
            raise ValueError("raw_hex exceeds bit_width")
        value = int(self.decimal)
        lower = -(1 << (width - 1)) if self.signed else 0
        upper = (1 << (width - 1)) - 1 if self.signed else (1 << width) - 1
        if not lower <= value <= upper:
            raise ValueError("decimal exceeds bit_width")
        decoded = raw - (1 << width) if self.signed and raw & (1 << (width - 1)) else raw
        if decoded != value:
            raise ValueError("decimal and raw_hex disagree")

    def to_dict(self) -> dict[str, object]:
        return {
            "decimal": self.decimal,
            "rawHex": self.raw_hex,
            "bitWidth": self.bit_width,
            "signed": self.signed,
        }


@dataclass(frozen=True)
class FloatEvidence:
    value: float | str
    raw_hex: str
    bit_width: int

    def __post_init__(self) -> None:
        width = _integer("bit_width", self.bit_width, 32, 64)
        if width not in (32, 64):
            raise ValueError("floating bit_width must be 32 or 64")
        if isinstance(self.value, str):
            if self.value not in _FLOAT_SYMBOLS:
                raise ValueError("floating symbol is invalid")
        elif not isinstance(self.value, float) or not math.isfinite(self.value):
            raise ValueError("non-finite floats require symbolic evidence")
        _raw_hex_width(self.raw_hex, width)

    @classmethod
    def symbolic(cls, value: str, *, raw_hex: str, bit_width: int) -> "FloatEvidence":
        return cls(value, raw_hex, bit_width)

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "rawHex": self.raw_hex, "bitWidth": self.bit_width}


@dataclass(frozen=True)
class TypedLocation:
    expression: str
    address: int
    size: int
    type_name: str
    kind: str
    bit_width: int
    signed: bool | None
    memory_region: str

    def __post_init__(self) -> None:
        if not isinstance(self.expression, str) or not self.expression or len(self.expression) > 512:
            raise ValueError("expression is invalid")
        _integer("address", self.address, 0, 0xFFFF_FFFF)
        _integer("size", self.size, 1, 1024 * 1024)
        _integer("bit_width", self.bit_width, 1, 8 * 1024 * 1024)
        if self.size * 8 != self.bit_width:
            raise ValueError("size and bit_width disagree")
        if self.signed is not None and type(self.signed) is not bool:
            raise TypeError("signed must be boolean or null")
        for name in ("type_name", "kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"{name} is invalid")
        _identifier("memory_region", self.memory_region)

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "address": self.address,
            "size": self.size,
            "typeName": self.type_name,
            "kind": self.kind,
            "bitWidth": self.bit_width,
            "signed": self.signed,
            "memoryRegion": self.memory_region,
        }


@dataclass(frozen=True)
class TypedValue:
    expression: str
    type_name: str
    value: object
    raw_hex: str
    bit_width: int

    def __post_init__(self) -> None:
        if not isinstance(self.expression, str) or not self.expression or len(self.expression) > 512:
            raise ValueError("expression is invalid")
        if not isinstance(self.type_name, str) or not self.type_name or len(self.type_name) > 256:
            raise ValueError("type_name is invalid")
        frozen = _freeze_json(self.value)
        _json_budget(frozen)
        object.__setattr__(self, "value", frozen)
        width = _integer("bit_width", self.bit_width, 1, 8 * 1024 * 1024)
        _raw_hex_width(self.raw_hex, width)

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "typeName": self.type_name,
            "value": _thaw_json(self.value),
            "rawHex": self.raw_hex,
            "bitWidth": self.bit_width,
        }


@dataclass(frozen=True)
class DebugReadItem:
    expression: str
    status: str
    value: TypedValue | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        _text("expression", self.expression, 512)
        if self.status not in {"ok", "error"}:
            raise ValueError("status is invalid")
        if self.status == "ok":
            if not isinstance(self.value, TypedValue) or self.code is not None:
                raise ValueError("successful read items require only a value")
            if self.value.expression != self.expression:
                raise ValueError("read item expression and value disagree")
        elif self.value is not None or not isinstance(self.code, str) or _CODE.fullmatch(self.code) is None:
            raise ValueError("failed read items require only a stable code")

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "status": self.status,
            "value": self.value.to_dict() if self.value is not None else None,
            "code": self.code,
        }


@dataclass(frozen=True)
class DebugReadReport:
    binding: DebugFirmwareBinding
    items: tuple[DebugReadItem, ...]
    confirmed_at_utc: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, DebugFirmwareBinding):
            raise TypeError("binding is invalid")
        if (
            type(self.items) is not tuple
            or not 1 <= len(self.items) <= _MAX_REPORT_ITEMS
            or not all(isinstance(item, DebugReadItem) for item in self.items)
        ):
            raise TypeError("items must be a bounded tuple")
        _timestamp("confirmed_at_utc", self.confirmed_at_utc)

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "confirmedAtUtc": self.confirmed_at_utc,
        }


@dataclass(frozen=True)
class SvdSelectionEvidence:
    target_device: str
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _identifier("target_device", self.target_device)
        _portable_path(self.path)
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("sha256 is invalid")

    def to_dict(self) -> dict[str, object]:
        return {"targetDevice": self.target_device, "path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class RegisterEvidence:
    path: str
    address: int
    size: int
    access: str
    side_effect: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path or len(self.path) > 512:
            raise ValueError("register path is invalid")
        _integer("address", self.address, 0, 0xFFFF_FFFF)
        _integer("size", self.size, 1, 8)
        if self.access not in _REGISTER_ACCESS:
            raise ValueError("register access is invalid")
        if self.side_effect not in _REGISTER_SIDE_EFFECTS:
            raise ValueError("register side effect is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "address": self.address,
            "size": self.size,
            "access": self.access,
            "sideEffect": self.side_effect,
        }


@dataclass(frozen=True)
class SampleReport:
    binding: DebugFirmwareBinding
    requested_interval_ms: int
    applied_interval_ms: int
    samples: tuple[Mapping[str, object], ...]
    actual_rate_hz: float
    deadline_misses: int
    dropped_samples: int

    def __post_init__(self) -> None:
        if not isinstance(self.binding, DebugFirmwareBinding):
            raise TypeError("binding is invalid")
        if type(self.samples) is not tuple or len(self.samples) > _MAX_SAMPLES:
            raise TypeError("samples must be a bounded tuple")
        if not all(isinstance(item, MappingABC) for item in self.samples):
            raise TypeError("sample entries must be mappings")
        _integer("requested_interval_ms", self.requested_interval_ms, 1, 3_600_000)
        _integer("applied_interval_ms", self.applied_interval_ms, 100, 10_000)
        _integer("deadline_misses", self.deadline_misses, 0, 1_000_000)
        _integer("dropped_samples", self.dropped_samples, 0, 1_000_000)
        if not isinstance(self.actual_rate_hz, float) or not math.isfinite(self.actual_rate_hz) or self.actual_rate_hz < 0:
            raise ValueError("actual_rate_hz is invalid")
        frozen = tuple(_freeze_json(item) for item in self.samples)
        _json_budget(frozen)
        object.__setattr__(self, "samples", cast(tuple[Mapping[str, object], ...], frozen))

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "requestedIntervalMs": self.requested_interval_ms,
            "appliedIntervalMs": self.applied_interval_ms,
            "samples": _thaw_json(self.samples),
            "actualRateHz": self.actual_rate_hz,
            "deadlineMisses": self.deadline_misses,
            "droppedSamples": self.dropped_samples,
        }


@dataclass(frozen=True)
class FaultReport:
    binding: DebugFirmwareBinding
    target_state: str
    registers: Mapping[str, object]
    fault_status: Mapping[str, object]
    stack_frame: Mapping[str, object] | None
    symbols: Mapping[str, object]
    confirmed_at_utc: str
    audit_operation: str = "fault.analyze"

    def __post_init__(self) -> None:
        if not isinstance(self.binding, DebugFirmwareBinding):
            raise TypeError("binding is invalid")
        if self.target_state != "halted" or self.audit_operation != "fault.analyze":
            raise ValueError("Fault report state or audit operation is invalid")
        _timestamp("confirmed_at_utc", self.confirmed_at_utc)
        for name in ("registers", "fault_status", "stack_frame", "symbols"):
            value = getattr(self, name)
            if value is None and name == "stack_frame":
                continue
            if not isinstance(value, MappingABC):
                raise TypeError(f"{name} must be a mapping")
            frozen = _freeze_json(value)
            _json_budget(frozen)
            object.__setattr__(self, name, frozen)

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "targetState": self.target_state,
            "registers": _thaw_json(self.registers),
            "faultStatus": _thaw_json(self.fault_status),
            "stackFrame": _thaw_json(self.stack_frame),
            "symbols": _thaw_json(self.symbols),
            "confirmedAtUtc": self.confirmed_at_utc,
            "auditOperation": self.audit_operation,
        }


__all__ = [
    "DebugBindingRequest",
    "DebugFirmwareBinding",
    "DebugReadItem",
    "DebugReadReport",
    "FaultReport",
    "FloatEvidence",
    "IntegerEvidence",
    "MemoryRegionBinding",
    "RegisterEvidence",
    "SampleReport",
    "SvdSelectionEvidence",
    "TypedLocation",
    "TypedValue",
]
