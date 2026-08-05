"""Frozen public models and stable errors for Keil inspection and baseline.

This module performs no I/O and owns no logic beyond immutable containers,
JSON-safe serialization, and stable error construction.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType


def _freeze(value: object) -> object:
    """Recursively snapshot JSON-style values into immutable containers."""
    if isinstance(value, MappingABC):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


class KeilInspectionError(Exception):
    """Stable error carrying a machine-readable code and frozen details."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details if details is not None else {})


def _json_safe(value: object) -> object:
    """Convert dataclasses, paths, and containers into JSON-safe values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, MappingABC):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value of type {type(value).__name__} is not JSON-safe")


class _JsonModel:
    """Base class providing fresh JSON-safe serialization for frozen models."""

    def to_dict(self) -> dict[str, object]:
        result = _json_safe(self)
        assert isinstance(result, dict)
        return result


@dataclass(frozen=True)
class KeilInputDigest(_JsonModel):
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class KeilMemoryRegion(_JsonModel):
    name: str  # IROM1, IROM2, IRAM1, IRAM2
    origin: int
    length: int
    attributes: str  # r-x for IROM, rwx for IRAM


@dataclass(frozen=True)
class KeilScopedOptions(_JsonModel):
    scope: str  # target, group, or file
    owner: str  # target/group name or source path
    include_in_build: bool
    defines: tuple[str, ...]
    include_paths: tuple[str, ...]
    misc_controls: tuple[str, ...]


@dataclass(frozen=True)
class KeilSource(_JsonModel):
    path: str
    group: str
    language: str  # c, cxx, asm, header, library, or other
    included: bool


@dataclass(frozen=True)
class KeilOutputSpec(_JsonModel):
    object_directory: str | None
    listing_directory: str | None
    output_name: str | None
    axf: str | None
    map_file: str | None
    scatter_file: str | None


@dataclass(frozen=True)
class KeilEvidence(_JsonModel):
    category: str  # define, include, or path
    value: str
    framework: str  # spl, hal, or ll


@dataclass(frozen=True)
class KeilFinding(_JsonModel):
    rule_id: str
    severity: str  # info, warning, or blocker
    path: str
    line: int
    column: int
    evidence: str  # trimmed to at most 200 Unicode code points
    message: str


@dataclass(frozen=True)
class KeilWarning(_JsonModel):
    code: str
    message: str
    details: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        frozen_details = _freeze(self.details)
        object.__setattr__(self, "details", frozen_details)


@dataclass(frozen=True)
class KeilInspection(_JsonModel):
    project_root: Path
    project_file: str
    project_sha256: str
    target_name: str
    device: str
    device_pack: str | None
    cpu: str
    fpu: str | None
    float_abi: str | None
    compiler: str  # armcc, armclang, or unknown
    compiler_version: str | None
    defines: tuple[str, ...]
    include_paths: tuple[str, ...]
    sources: tuple[KeilSource, ...]
    scoped_options: tuple[KeilScopedOptions, ...]
    linker_inputs: tuple[str, ...]
    memory_regions: tuple[KeilMemoryRegion, ...]
    output: KeilOutputSpec
    framework: str | None
    framework_candidates: tuple[str, ...]
    framework_evidence: tuple[KeilEvidence, ...]
    findings: tuple[KeilFinding, ...]
    warnings: tuple[KeilWarning, ...]
    inputs: tuple[KeilInputDigest, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a portable JSON-safe mapping; the host path is omitted."""
        data = _json_safe(self)
        assert isinstance(data, dict)
        data.pop("project_root", None)
        return data


@dataclass(frozen=True)
class KeilArtifactEvidence(_JsonModel):
    path: str | None
    available: bool
    sha256: str | None
    size: int | None


@dataclass(frozen=True)
class KeilSectionEvidence(_JsonModel):
    name: str
    address: int
    size: int
    flags: int


@dataclass(frozen=True)
class KeilSymbolEvidence(_JsonModel):
    name: str
    address: int
    size: int | None
    section: str | None


@dataclass(frozen=True)
class KeilProgramSize(_JsonModel):
    code: int
    ro_data: int
    rw_data: int
    zi_data: int
    flash: int  # code + ro_data + rw_data
    ram: int  # rw_data + zi_data


@dataclass(frozen=True)
class KeilBaseline(_JsonModel):
    available: bool
    axf: KeilArtifactEvidence
    map_file: KeilArtifactEvidence
    entry_point: int | None
    sections: tuple[KeilSectionEvidence, ...]
    symbols: tuple[KeilSymbolEvidence, ...]
    program_size: KeilProgramSize | None
    warnings: tuple[KeilWarning, ...]
