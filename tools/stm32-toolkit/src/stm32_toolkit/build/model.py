"""Frozen public model types for the bounded build pipeline (STM32TK-0305).

All public containers are frozen dataclasses; tuples replace lists.
``to_dict()`` returns a fresh JSON-safe mapping with portable ``/`` paths and
never includes absolute paths, raw bytes, or host exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Accepted build timeout range in seconds (mirrors the process layer).
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 3600.0

# Stable failure codes.
BUILD_REQUEST_INVALID = "BUILD_REQUEST_INVALID"
BUILD_MODEL_INVALID = "BUILD_MODEL_INVALID"
BUILD_BUSY = "BUILD_BUSY"
BUILD_ENVIRONMENT_ERROR = "BUILD_ENVIRONMENT_ERROR"
BUILD_TIMEOUT = "BUILD_TIMEOUT"
BUILD_FAILED = "BUILD_FAILED"
BUILD_EVIDENCE_INVALID = "BUILD_EVIDENCE_INVALID"
BUILD_IDENTITY_INVALID = "BUILD_IDENTITY_INVALID"
BUILD_PUBLICATION_FAILED = "BUILD_PUBLICATION_FAILED"


class BuildError(Exception):
    """A deterministic build failure with a stable code and bounded details."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


@dataclass(frozen=True)
class BuildRequest:
    """One bounded configure+build invocation for a declared preset."""

    project_root: Path
    preset: str
    clean_first: bool = False
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class MemoryUsage:
    """Per-region interval-union usage from the linker MAP."""

    region: str
    origin: int
    length: int
    used: int
    percent: float

    def to_dict(self) -> dict[str, object]:
        return {
            "region": self.region,
            "origin": self.origin,
            "length": self.length,
            "used": self.used,
            "percent": self.percent,
        }


@dataclass(frozen=True)
class InputSnapshotFile:
    """One project input with its SHA-256 digest."""

    path: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class InputSnapshot:
    """Canonical sorted input list plus one aggregate SHA-256."""

    sha256: str
    files: tuple[InputSnapshotFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {"sha256": self.sha256, "files": [entry.to_dict() for entry in self.files]}


@dataclass(frozen=True)
class FirmwareIdentity:
    """Schema-1 firmware identity evidence for one successful build."""

    schema_version: int
    build_id: str
    built_at_utc: str
    status: str
    preset: str
    clean_first: bool
    git_head: str | None
    git_branch: str | None
    git_target: str | None
    input_snapshot: InputSnapshot
    elf_path: str
    elf_sha256: str
    elf_size: int
    map_path: str
    map_sha256: str
    map_size: int
    entry_point: str
    isr_vector_present: bool
    reset_handler_present: bool
    entry_point_consistent: bool
    undefined_symbols: tuple[str, ...]
    memory_usage: tuple[MemoryUsage, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "buildId": self.build_id,
            "builtAtUtc": self.built_at_utc,
            "status": self.status,
            "preset": self.preset,
            "cleanFirst": self.clean_first,
            "gitHead": self.git_head,
            "gitBranch": self.git_branch,
            "gitTarget": self.git_target,
            "inputSnapshot": self.input_snapshot.to_dict(),
            "elf": {
                "path": self.elf_path,
                "sha256": self.elf_sha256,
                "size": self.elf_size,
            },
            "map": {
                "path": self.map_path,
                "sha256": self.map_sha256,
                "size": self.map_size,
            },
            "entryPoint": self.entry_point,
            "isrVectorPresent": self.isr_vector_present,
            "resetHandlerPresent": self.reset_handler_present,
            "entryPointConsistent": self.entry_point_consistent,
            "undefinedSymbols": list(self.undefined_symbols),
            "memoryUsage": [usage.to_dict() for usage in self.memory_usage],
        }


@dataclass(frozen=True)
class BuildReport:
    """The published outcome of one successful build."""

    preset: str
    clean_first: bool
    success: bool
    returncode: int | None
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    log_path: str | None
    identity_path: str | None
    result_path: str | None
    elf_path: str | None
    map_path: str | None
    identity: FirmwareIdentity | None
    memory_usage: tuple[MemoryUsage, ...]
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Compact JSON-safe record; the build-result.json commit point."""
        identity = self.identity
        return {
            "schemaVersion": 1,
            "status": "success" if self.success else "failed",
            "preset": self.preset,
            "cleanFirst": self.clean_first,
            "buildId": identity.build_id if identity is not None else None,
            "builtAtUtc": identity.built_at_utc if identity is not None else None,
            "returncode": self.returncode,
            "timedOut": self.timed_out,
            "durationSeconds": self.duration_seconds,
            "elf": (
                {
                    "path": self.elf_path,
                    "sha256": identity.elf_sha256,
                    "size": identity.elf_size,
                }
                if identity is not None and self.elf_path is not None
                else None
            ),
            "map": (
                {
                    "path": self.map_path,
                    "sha256": identity.map_sha256,
                    "size": identity.map_size,
                }
                if identity is not None and self.map_path is not None
                else None
            ),
            "logPath": self.log_path,
            "identityPath": self.identity_path,
            "resultPath": self.result_path,
        }
