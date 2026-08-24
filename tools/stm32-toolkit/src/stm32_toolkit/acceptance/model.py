"""Closed, immutable models for the VS08-A software acceptance scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from typing import cast
from unicodedata import normalize
from uuid import UUID

from stm32_toolkit.evidence import canonical_json_bytes


SCENARIO_SCHEMA = "stm32-acceptance-scenario/1"
RECORD_SCHEMA = "stm32-acceptance-record/1"
REQUIRED_STAGES = (
    "project-materialized",
    "firmware-built-before",
    "target-failure-replayed",
    "diagnosis-completed",
    "firmware-built-after",
    "target-fix-verified",
)

_SCENARIO_FIELDS = {
    "schema",
    "scenarioId",
    "scenarioVersion",
    "scenarioDigest",
    "projectOrigin",
    "executionProfile",
    "requiredStages",
    "physicalTransportEvidence",
}
_RECORD_FIELDS = {
    "schema",
    "recordId",
    "scenarioId",
    "scenarioVersion",
    "scenarioDigest",
    "workspaceId",
    "logicalProjectId",
    "projectOrigin",
    "executionSource",
    "physicalTransportEvidence",
    "completedStages",
    "failedBeforeTestRunId",
    "fixedAfterTestRunId",
    "diagnosticSessionId",
    "fixVerificationId",
    "failedBeforeEvidenceId",
    "fixedAfterEvidenceId",
    "beforeBuildId",
    "afterBuildId",
    "beforeElfSha256",
    "afterElfSha256",
    "verdict",
    "producedAtUtc",
}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_SCENARIO_IDS = frozenset({"legacy-keil-migration", "new-cubemx-project"})
_SCENARIO_VERSIONS = frozenset({"1"})
_SCENARIO_DEFINITIONS = {
    ("legacy-keil-migration", "1"): "keil",
    ("new-cubemx-project", "1"): "cubemx",
}


class AcceptanceValidationError(ValueError):
    """A public acceptance model failed its closed canonical contract."""

    def __init__(self, message: str, code: str = "ACCEPTANCE_INPUT_INVALID") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_tuple_containers(value: object, depth: int = 1) -> None:
    if depth > 32:
        raise AcceptanceValidationError("JSON nesting exceeds the acceptance limit")
    if isinstance(value, tuple):
        raise AcceptanceValidationError("JSON arrays must not be tuples")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuple_containers(key, depth + 1)
            _reject_tuple_containers(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_tuple_containers(item, depth + 1)


def _string(field: str, value: object, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise AcceptanceValidationError(f"{field} must be a string")
    if normalize("NFC", value) != value:
        raise AcceptanceValidationError(f"{field} must use NFC")
    if len(value.encode("utf-8")) > 64 * 1024:
        raise AcceptanceValidationError(f"{field} exceeds the string limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AcceptanceValidationError(f"{field} contains a control character")
    return value


def _hash(field: str, value: object) -> str:
    value = _string(field, value)
    if _HASH.fullmatch(value) is None:
        raise AcceptanceValidationError(f"{field} must be a lowercase SHA-256")
    return value


def _uuid(field: str, value: object) -> str:
    value = _string(field, value)
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as error:
        raise AcceptanceValidationError(f"{field} must be a canonical lowercase UUID") from error
    if str(parsed) != value:
        raise AcceptanceValidationError(f"{field} must be a canonical lowercase UUID")
    return value


def _utc(field: str, value: object) -> str:
    value = _string(field, value)
    if _UTC.fullmatch(value) is None:
        raise AcceptanceValidationError(f"{field} must use UTC microseconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise AcceptanceValidationError(f"{field} is not a valid UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise AcceptanceValidationError(f"{field} must use UTC microseconds")
    return value


def _definition_key(scenario_id: object, scenario_version: object) -> tuple[str, str]:
    scenario_id = _string("scenarioId", scenario_id)
    scenario_version = _string("scenarioVersion", scenario_version)
    if scenario_id not in _SCENARIO_IDS:
        raise AcceptanceValidationError(
            "scenario ID is not supported", "ACCEPTANCE_SCENARIO_UNKNOWN"
        )
    if scenario_version not in _SCENARIO_VERSIONS:
        raise AcceptanceValidationError(
            "scenario version is not supported", "ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED"
        )
    if (scenario_id, scenario_version) not in _SCENARIO_DEFINITIONS:
        raise AcceptanceValidationError(
            "scenario definition is not supported", "ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED"
        )
    return scenario_id, scenario_version


def _scenario_without_digest(
    scenario_id: str, scenario_version: str, project_origin: str
) -> dict[str, object]:
    return {
        "schema": SCENARIO_SCHEMA,
        "scenarioId": scenario_id,
        "scenarioVersion": scenario_version,
        "projectOrigin": project_origin,
        "executionProfile": "software-replay",
        "requiredStages": list(REQUIRED_STAGES),
        "physicalTransportEvidence": False,
    }


def _scenario_digest(scenario_id: str, scenario_version: str, project_origin: str) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_scenario_without_digest(scenario_id, scenario_version, project_origin))
    ).hexdigest()


@dataclass(frozen=True)
class AcceptanceScenario:
    schema: str
    scenario_id: str
    scenario_version: str
    scenario_digest: str
    project_origin: str
    execution_profile: str
    required_stages: tuple[str, ...]
    physical_transport_evidence: bool

    def __post_init__(self) -> None:
        if self.schema != SCENARIO_SCHEMA:
            raise AcceptanceValidationError("schema is unsupported")
        scenario_id, scenario_version = _definition_key(
            self.scenario_id, self.scenario_version
        )
        expected_origin = _SCENARIO_DEFINITIONS[(scenario_id, scenario_version)]
        if self.project_origin != expected_origin:
            raise AcceptanceValidationError("project origin is not bound to the scenario")
        if self.execution_profile != "software-replay":
            raise AcceptanceValidationError("execution profile is unsupported")
        if not isinstance(self.required_stages, tuple) or self.required_stages != REQUIRED_STAGES:
            raise AcceptanceValidationError("required stages are not the closed ordered definition")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            raise AcceptanceValidationError("physical transport evidence is forbidden")
        expected_digest = _scenario_digest(scenario_id, scenario_version, expected_origin)
        if self.scenario_digest != expected_digest:
            raise AcceptanceValidationError("scenario digest does not match the definition")
        _hash("scenarioDigest", self.scenario_digest)

    @classmethod
    def from_value(cls, value: object) -> "AcceptanceScenario":
        _reject_tuple_containers(value)
        if not isinstance(value, Mapping) or set(value) != _SCENARIO_FIELDS:
            raise AcceptanceValidationError("scenario fields are not closed")
        stages = value["requiredStages"]
        if not isinstance(stages, list):
            raise AcceptanceValidationError("requiredStages must be a JSON array")
        if any(type(item) is not str for item in stages):
            raise AcceptanceValidationError("requiredStages must contain strings")
        return cls(
            schema=cast(str, value["schema"]),
            scenario_id=cast(str, value["scenarioId"]),
            scenario_version=cast(str, value["scenarioVersion"]),
            scenario_digest=cast(str, value["scenarioDigest"]),
            project_origin=cast(str, value["projectOrigin"]),
            execution_profile=cast(str, value["executionProfile"]),
            required_stages=tuple(stages),
            physical_transport_evidence=value["physicalTransportEvidence"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "scenarioId": self.scenario_id,
            "scenarioVersion": self.scenario_version,
            "scenarioDigest": self.scenario_digest,
            "projectOrigin": self.project_origin,
            "executionProfile": self.execution_profile,
            "requiredStages": list(self.required_stages),
            "physicalTransportEvidence": self.physical_transport_evidence,
        }


def describe_scenario(scenario_id: str, scenario_version: str) -> AcceptanceScenario:
    """Return the immutable code-owned definition for one supported scenario."""
    scenario_id, scenario_version = _definition_key(scenario_id, scenario_version)
    origin = _SCENARIO_DEFINITIONS[(scenario_id, scenario_version)]
    return AcceptanceScenario(
        schema=SCENARIO_SCHEMA,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        scenario_digest=_scenario_digest(scenario_id, scenario_version, origin),
        project_origin=origin,
        execution_profile="software-replay",
        required_stages=REQUIRED_STAGES,
        physical_transport_evidence=False,
    )


@dataclass(frozen=True)
class AcceptanceRecord:
    schema: str
    record_id: str
    scenario_id: str
    scenario_version: str
    scenario_digest: str
    workspace_id: str
    logical_project_id: str
    project_origin: str
    execution_source: str
    physical_transport_evidence: bool
    completed_stages: tuple[str, ...]
    failed_before_test_run_id: str
    fixed_after_test_run_id: str
    diagnostic_session_id: str
    fix_verification_id: str
    failed_before_evidence_id: str
    fixed_after_evidence_id: str
    before_build_id: str
    after_build_id: str
    before_elf_sha256: str
    after_elf_sha256: str
    verdict: str
    produced_at_utc: str

    def __post_init__(self) -> None:
        if self.schema != RECORD_SCHEMA:
            raise AcceptanceValidationError("record schema is unsupported")
        _uuid("recordId", self.record_id)
        scenario = describe_scenario(self.scenario_id, self.scenario_version)
        if self.scenario_digest != scenario.scenario_digest:
            raise AcceptanceValidationError("record scenario digest does not match definition")
        _hash("scenarioDigest", self.scenario_digest)
        _hash("workspaceId", self.workspace_id)
        _uuid("logicalProjectId", self.logical_project_id)
        if self.project_origin != scenario.project_origin:
            raise AcceptanceValidationError("record project origin does not match definition")
        if self.execution_source != "replay":
            raise AcceptanceValidationError("execution source must be replay")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            raise AcceptanceValidationError("physical transport evidence is forbidden")
        if not isinstance(self.completed_stages, tuple) or self.completed_stages != scenario.required_stages:
            raise AcceptanceValidationError("completed stages are not the exact ordered definition")
        _uuid("failedBeforeTestRunId", self.failed_before_test_run_id)
        _uuid("fixedAfterTestRunId", self.fixed_after_test_run_id)
        _uuid("diagnosticSessionId", self.diagnostic_session_id)
        for field, value in (
            ("fixVerificationId", self.fix_verification_id),
            ("failedBeforeEvidenceId", self.failed_before_evidence_id),
            ("fixedAfterEvidenceId", self.fixed_after_evidence_id),
            ("beforeBuildId", self.before_build_id),
            ("afterBuildId", self.after_build_id),
            ("beforeElfSha256", self.before_elf_sha256),
            ("afterElfSha256", self.after_elf_sha256),
        ):
            _hash(field, value)
        if self.verdict != "SOFTWARE_PASSED":
            raise AcceptanceValidationError("record verdict must be SOFTWARE_PASSED")
        _utc("producedAtUtc", self.produced_at_utc)

    @classmethod
    def from_value(cls, value: object) -> "AcceptanceRecord":
        _reject_tuple_containers(value)
        if not isinstance(value, Mapping) or set(value) != _RECORD_FIELDS:
            raise AcceptanceValidationError("record fields are not closed")
        stages = value["completedStages"]
        if not isinstance(stages, list):
            raise AcceptanceValidationError("completedStages must be a JSON array")
        if any(type(item) is not str for item in stages):
            raise AcceptanceValidationError("completedStages must contain strings")
        return cls(
            schema=cast(str, value["schema"]),
            record_id=cast(str, value["recordId"]),
            scenario_id=cast(str, value["scenarioId"]),
            scenario_version=cast(str, value["scenarioVersion"]),
            scenario_digest=cast(str, value["scenarioDigest"]),
            workspace_id=cast(str, value["workspaceId"]),
            logical_project_id=cast(str, value["logicalProjectId"]),
            project_origin=cast(str, value["projectOrigin"]),
            execution_source=cast(str, value["executionSource"]),
            physical_transport_evidence=value["physicalTransportEvidence"],  # type: ignore[arg-type]
            completed_stages=tuple(stages),
            failed_before_test_run_id=cast(str, value["failedBeforeTestRunId"]),
            fixed_after_test_run_id=cast(str, value["fixedAfterTestRunId"]),
            diagnostic_session_id=cast(str, value["diagnosticSessionId"]),
            fix_verification_id=cast(str, value["fixVerificationId"]),
            failed_before_evidence_id=cast(str, value["failedBeforeEvidenceId"]),
            fixed_after_evidence_id=cast(str, value["fixedAfterEvidenceId"]),
            before_build_id=cast(str, value["beforeBuildId"]),
            after_build_id=cast(str, value["afterBuildId"]),
            before_elf_sha256=cast(str, value["beforeElfSha256"]),
            after_elf_sha256=cast(str, value["afterElfSha256"]),
            verdict=cast(str, value["verdict"]),
            produced_at_utc=cast(str, value["producedAtUtc"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "recordId": self.record_id,
            "scenarioId": self.scenario_id,
            "scenarioVersion": self.scenario_version,
            "scenarioDigest": self.scenario_digest,
            "workspaceId": self.workspace_id,
            "logicalProjectId": self.logical_project_id,
            "projectOrigin": self.project_origin,
            "executionSource": self.execution_source,
            "physicalTransportEvidence": self.physical_transport_evidence,
            "completedStages": list(self.completed_stages),
            "failedBeforeTestRunId": self.failed_before_test_run_id,
            "fixedAfterTestRunId": self.fixed_after_test_run_id,
            "diagnosticSessionId": self.diagnostic_session_id,
            "fixVerificationId": self.fix_verification_id,
            "failedBeforeEvidenceId": self.failed_before_evidence_id,
            "fixedAfterEvidenceId": self.fixed_after_evidence_id,
            "beforeBuildId": self.before_build_id,
            "afterBuildId": self.after_build_id,
            "beforeElfSha256": self.before_elf_sha256,
            "afterElfSha256": self.after_elf_sha256,
            "verdict": self.verdict,
            "producedAtUtc": self.produced_at_utc,
        }


__all__ = [
    "AcceptanceRecord",
    "AcceptanceScenario",
    "AcceptanceValidationError",
    "RECORD_SCHEMA",
    "REQUIRED_STAGES",
    "SCENARIO_SCHEMA",
    "describe_scenario",
]
