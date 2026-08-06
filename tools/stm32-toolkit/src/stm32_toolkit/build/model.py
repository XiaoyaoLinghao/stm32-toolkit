"""Frozen build request, report, identity, and memory types (STM32TK-0305).

Every value is immutable; container fields are tuples; every ``to_dict()``
returns a fresh JSON-safe mapping with portable project-relative paths and
never exposes absolute roots, raw bytes, or process output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_PRESETS = ("arm-debug", "arm-release")
IDENTITY_SCHEMA_VERSION = 1

#: Stable failure codes (work order section 12).
BUILD_REQUEST_INVALID = "BUILD_REQUEST_INVALID"
BUILD_PROJECT_INVALID = "BUILD_PROJECT_INVALID"
BUILD_INPUT_INVALID = "BUILD_INPUT_INVALID"
BUILD_INPUT_CHANGED = "BUILD_INPUT_CHANGED"
BUILD_GIT_INVALID = "BUILD_GIT_INVALID"
BUILD_BUSY = "BUILD_BUSY"
BUILD_CONFIGURE_FAILED = "BUILD_CONFIGURE_FAILED"
BUILD_FAILED = "BUILD_FAILED"
BUILD_TIMEOUT = "BUILD_TIMEOUT"
BUILD_OUTPUT_STALE = "BUILD_OUTPUT_STALE"
BUILD_MAP_INVALID = "BUILD_MAP_INVALID"
BUILD_ARTIFACT_INVALID = "BUILD_ARTIFACT_INVALID"
FLASH_OVERFLOW = "FLASH_OVERFLOW"
RAM_OVERFLOW = "RAM_OVERFLOW"
MEMORY_OVERFLOW = "MEMORY_OVERFLOW"
BUILD_EVIDENCE_FAILED = "BUILD_EVIDENCE_FAILED"


class BuildError(Exception):
    """A stable build failure carrying a code and bounded details."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


def build_error(code: str, message: str, details: dict[str, object]) -> BuildError:
    return BuildError(code, message, details)


@dataclass(frozen=True)
class BuildRequest:
    project_root: Path
    preset: str
    clean: bool = False
    timeout_seconds: int = 300


@dataclass(frozen=True)
class MemoryUsage:
    name: str
    origin: int
    length: int
    used: int
    free: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "length": self.length,
            "used": self.used,
            "free": self.free,
        }


@dataclass(frozen=True)
class FirmwareIdentity:
    schema_version: int
    build_id: str
    logical_project_id: str
    toolkit_version: str
    git_head: str
    git_dirty: bool
    input_snapshot_sha256: str
    newest_input_mtime_ns: int
    target_device: str
    preset: str
    elf_path: str
    elf_sha256: str
    elf_size: int
    map_path: str
    map_sha256: str
    entry_point: int
    vector_address: int
    reset_handler_address: int
    built_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "buildId": self.build_id,
            "logicalProjectId": self.logical_project_id,
            "toolkitVersion": self.toolkit_version,
            "gitHead": self.git_head,
            "gitDirty": self.git_dirty,
            "inputSnapshotSha256": self.input_snapshot_sha256,
            "newestInputMtimeNs": self.newest_input_mtime_ns,
            "targetDevice": self.target_device,
            "preset": self.preset,
            "elfPath": self.elf_path,
            "elfSha256": self.elf_sha256,
            "elfSize": self.elf_size,
            "mapPath": self.map_path,
            "mapSha256": self.map_sha256,
            "entryPoint": self.entry_point,
            "vectorAddress": self.vector_address,
            "resetHandlerAddress": self.reset_handler_address,
            "builtAtUtc": self.built_at_utc,
        }


@dataclass(frozen=True)
class BuildReport:
    identity: FirmwareIdentity
    memory: tuple[MemoryUsage, ...]
    warnings: tuple[str, ...]
    build_log_path: str
    build_result_path: str
    identity_path: str
    configure_duration_ms: int
    build_duration_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "memory": [item.to_dict() for item in self.memory],
            "warnings": list(self.warnings),
            "buildLogPath": self.build_log_path,
            "buildResultPath": self.build_result_path,
            "identityPath": self.identity_path,
            "configureDurationMs": self.configure_duration_ms,
            "buildDurationMs": self.build_duration_ms,
        }
