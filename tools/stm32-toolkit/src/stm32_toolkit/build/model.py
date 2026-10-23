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
#: A snapshot identity is emitted only when Git provenance is unavailable.
SNAPSHOT_IDENTITY_SCHEMA_VERSION = 2
SOURCE_BASELINE_INPUT_SNAPSHOT = "input-snapshot-v1"
GIT_DIAGNOSTIC_UNAVAILABLE = "unavailable"

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
    git_head: str | None
    git_dirty: bool | None
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
    input_discovery_policy: str = "legacy"
    source_baseline: str | None = None
    git_evidence: dict[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        result = {
            "schemaVersion": self.schema_version,
            "buildId": self.build_id,
            "logicalProjectId": self.logical_project_id,
            "toolkitVersion": self.toolkit_version,
        }
        if self.source_baseline is not None:
            result["sourceBaseline"] = self.source_baseline
        result["gitHead"] = self.git_head
        result["gitDirty"] = self.git_dirty
        if self.git_evidence is not None:
            result["gitEvidence"] = dict(self.git_evidence)
        result.update(
            {
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
        )
        if self.input_discovery_policy == "source-local-headers-v1":
            result["inputDiscoveryPolicy"] = self.input_discovery_policy
        return result

    @classmethod
    def from_document(cls, document: dict[str, object]) -> "FirmwareIdentity":
        """Build the typed identity from a schema-validated document.

        Optional fields are preserved exactly so ``to_dict()`` round-trips a
        schema-1 Git identity or a schema-2 input-snapshot identity.
        """
        schema_version = document["schemaVersion"]
        if type(schema_version) is not int:
            raise TypeError("schemaVersion must be an integer")
        git_head = document["gitHead"]
        git_dirty = document["gitDirty"]
        if git_head is not None and not isinstance(git_head, str):
            raise TypeError("gitHead must be a string or null")
        if git_dirty is not None and type(git_dirty) is not bool:
            raise TypeError("gitDirty must be a boolean or null")
        source_baseline = document.get("sourceBaseline")
        if source_baseline is not None and not isinstance(source_baseline, str):
            raise TypeError("sourceBaseline must be a string")
        raw_evidence = document.get("gitEvidence")
        git_evidence: dict[str, str] | None = None
        if raw_evidence is not None:
            if not isinstance(raw_evidence, dict):
                raise TypeError("gitEvidence must be an object")
            git_evidence = {str(key): str(value) for key, value in raw_evidence.items()}
        policy = document.get("inputDiscoveryPolicy")
        return cls(
            schema_version=schema_version,
            build_id=str(document["buildId"]),
            logical_project_id=str(document["logicalProjectId"]),
            toolkit_version=str(document["toolkitVersion"]),
            git_head=None if git_head is None else str(git_head),
            git_dirty=git_dirty,
            input_snapshot_sha256=str(document["inputSnapshotSha256"]),
            newest_input_mtime_ns=int(document["newestInputMtimeNs"]),
            target_device=str(document["targetDevice"]),
            preset=str(document["preset"]),
            elf_path=str(document["elfPath"]),
            elf_sha256=str(document["elfSha256"]),
            elf_size=int(document["elfSize"]),
            map_path=str(document["mapPath"]),
            map_sha256=str(document["mapSha256"]),
            entry_point=int(document["entryPoint"]),
            vector_address=int(document["vectorAddress"]),
            reset_handler_address=int(document["resetHandlerAddress"]),
            built_at_utc=str(document["builtAtUtc"]),
            input_discovery_policy=str(policy) if policy is not None else "legacy",
            source_baseline=None if source_baseline is None else str(source_baseline),
            git_evidence=git_evidence,
        )


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
