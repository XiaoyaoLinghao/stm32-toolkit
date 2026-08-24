"""Closed immutable models for VS08-B acceptance recovery attempts.

The recovery adapter stores only canonical references to evidence produced by
the existing Project, Build, Test, Diagnostic, and VS08-A authorities.  This
module deliberately contains no execution or persistence behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from types import MappingProxyType
from typing import cast
from unicodedata import normalize
from uuid import UUID

from stm32_toolkit.evidence import canonical_json_bytes

from .model import AcceptanceValidationError, REQUIRED_STAGES, describe_scenario


ATTEMPT_SCHEMA = "stm32-acceptance-attempt/1"
RECOVERY_POLICY_SCHEMA = "stm32-acceptance-recovery-policy/1"
RECOVERY_POLICY_DIGEST = "af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c"
STAGE_OUTPUT_KEYS = (
    "projectModelDigest",
    "beforeBuildId",
    "beforeElfSha256",
    "beforeInputSnapshotSha256",
    "failedBeforeTestRunId",
    "failedBeforeEvidenceId",
    "diagnosticSessionId",
    "diagnosticRevision",
    "diagnosticEventHead",
    "afterBuildId",
    "afterElfSha256",
    "afterInputSnapshotSha256",
    "sourceChangeDeclarationId",
    "acceptanceRecordId",
)
AUTHORIZATION_FIELDS = (
    "action",
    "actionDigest",
    "authorized",
    "authorizedAtUtc",
    "diagnosticSessionId",
    "diagnosticRevision",
    "diagnosticEventHead",
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

_POLICY_TIMEOUTS = {
    "project-materialized": 60,
    "firmware-built-before": 900,
    "target-failure-replayed": 300,
    "diagnosis-completed": 900,
    "firmware-built-after": 900,
    "target-fix-verified": 300,
}
_POLICY_ACTIONS = {
    "source-change": {
        "afterStage": "diagnosis-completed",
        "applicable": True,
        "authorization": "explicit-single-use",
        "beforeStage": "firmware-built-after",
    },
    "flash": {
        "applicable": False,
        "authorization": "existing-probe-action-digest",
        "reason": "software-replay",
    },
}
_POLICY_DOCUMENT = {
    "schema": RECOVERY_POLICY_SCHEMA,
    "attemptSchema": ATTEMPT_SCHEMA,
    "stageTimeoutSeconds": _POLICY_TIMEOUTS,
    "intrusiveActions": _POLICY_ACTIONS,
    "physicalTransportEvidence": False,
}
_ATTEMPT_FIELDS = {
    "schema",
    "attemptId",
    "revision",
    "checkpointId",
    "previousCheckpointId",
    "scenarioId",
    "scenarioVersion",
    "scenarioDigest",
    "recoveryPolicyDigest",
    "workspaceId",
    "logicalProjectId",
    "projectOrigin",
    "executionSource",
    "physicalTransportEvidence",
    "status",
    "completedStages",
    "stageOutputs",
    "sourceChangeAuthorization",
    "openedAtUtc",
    "deadlineAtUtc",
    "updatedAtUtc",
}


class AcceptanceRecoveryValidationError(ValueError):
    """A recovery policy, attempt, or checkpoint failed its closed contract."""

    def __init__(self, message: str, code: str = "ACCEPTANCE_ATTEMPT_INPUT_INVALID") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_tuples(value: object, depth: int = 1) -> None:
    if depth > 32:
        raise AcceptanceRecoveryValidationError("JSON nesting exceeds the recovery limit")
    if isinstance(value, tuple):
        raise AcceptanceRecoveryValidationError("JSON arrays must not be tuples")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key, depth + 1)
            _reject_tuples(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item, depth + 1)


def _string(field: str, value: object, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise AcceptanceRecoveryValidationError(f"{field} must be a string")
    if normalize("NFC", value) != value:
        raise AcceptanceRecoveryValidationError(f"{field} must use NFC")
    if len(value.encode("utf-8")) > 64 * 1024:
        raise AcceptanceRecoveryValidationError(f"{field} exceeds the string limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AcceptanceRecoveryValidationError(f"{field} contains a control character")
    return value


def _hash(field: str, value: object) -> str:
    string = _string(field, value)
    if _HASH.fullmatch(string) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must be a lowercase SHA-256")
    return string


def _uuid(field: str, value: object) -> str:
    string = _string(field, value)
    if _UUID.fullmatch(string) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must be a canonical lowercase UUID")
    try:
        if str(UUID(string)) != string:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise AcceptanceRecoveryValidationError(f"{field} must be a canonical lowercase UUID") from error
    return string


def _utc(field: str, value: object) -> str:
    string = _string(field, value)
    if _UTC.fullmatch(string) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must use UTC microseconds")
    try:
        parsed = datetime.strptime(string, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise AcceptanceRecoveryValidationError(f"{field} is not a valid UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != string:
        raise AcceptanceRecoveryValidationError(f"{field} must use UTC microseconds")
    return string


def _timestamp_value(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")


def _copy_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value


def acceptance_recovery_policy() -> "AcceptanceRecoveryPolicy":
    """Return the code-owned, immutable recovery policy."""
    return AcceptanceRecoveryPolicy(
        schema=RECOVERY_POLICY_SCHEMA,
        attempt_schema=ATTEMPT_SCHEMA,
        stage_timeout_seconds=MappingProxyType(dict(_POLICY_TIMEOUTS)),
        intrusive_actions=MappingProxyType(
            {key: MappingProxyType(dict(value)) for key, value in _POLICY_ACTIONS.items()}
        ),
        physical_transport_evidence=False,
    )


@dataclass(frozen=True)
class AcceptanceRecoveryPolicy:
    schema: str
    attempt_schema: str
    stage_timeout_seconds: Mapping[str, int]
    intrusive_actions: Mapping[str, Mapping[str, object]]
    physical_transport_evidence: bool

    def __post_init__(self) -> None:
        if self.schema != RECOVERY_POLICY_SCHEMA or self.attempt_schema != ATTEMPT_SCHEMA:
            raise AcceptanceRecoveryValidationError("recovery policy schema is unsupported")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            raise AcceptanceRecoveryValidationError("physical transport evidence is forbidden")
        if dict(self.stage_timeout_seconds) != _POLICY_TIMEOUTS:
            raise AcceptanceRecoveryValidationError("recovery timeouts are not frozen")
        if {
            key: dict(value) for key, value in self.intrusive_actions.items()
        } != _POLICY_ACTIONS:
            raise AcceptanceRecoveryValidationError("intrusive action policy is not frozen")
        object.__setattr__(self, "stage_timeout_seconds", MappingProxyType(dict(self.stage_timeout_seconds)))
        object.__setattr__(
            self,
            "intrusive_actions",
            MappingProxyType(
                {key: MappingProxyType(dict(value)) for key, value in self.intrusive_actions.items()}
            ),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "attemptSchema": self.attempt_schema,
            "stageTimeoutSeconds": dict(self.stage_timeout_seconds),
            "intrusiveActions": {
                key: dict(value) for key, value in self.intrusive_actions.items()
            },
            "physicalTransportEvidence": self.physical_transport_evidence,
        }

    @classmethod
    def from_value(cls, value: object) -> "AcceptanceRecoveryPolicy":
        _reject_tuples(value)
        expected = set(_POLICY_DOCUMENT)
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AcceptanceRecoveryValidationError("recovery policy fields are not closed")
        stage_timeouts = value["stageTimeoutSeconds"]
        actions = value["intrusiveActions"]
        if not isinstance(stage_timeouts, Mapping) or not isinstance(actions, Mapping):
            raise AcceptanceRecoveryValidationError("recovery policy objects are invalid")
        return cls(
            schema=cast(str, value["schema"]),
            attempt_schema=cast(str, value["attemptSchema"]),
            stage_timeout_seconds=stage_timeouts,  # type: ignore[arg-type]
            intrusive_actions=actions,  # type: ignore[arg-type]
            physical_transport_evidence=value["physicalTransportEvidence"],  # type: ignore[arg-type]
        )


def _expected_stage_count(revision: int) -> int:
    if revision <= 4:
        return revision
    return revision - 1


def _required_output_keys(revision: int) -> frozenset[str]:
    required: set[str] = set()
    if revision >= 1:
        required.add("projectModelDigest")
    if revision >= 2:
        required.update({"beforeBuildId", "beforeElfSha256", "beforeInputSnapshotSha256"})
    if revision >= 3:
        required.update({"failedBeforeTestRunId", "failedBeforeEvidenceId"})
    if revision >= 4:
        required.update({"diagnosticSessionId", "diagnosticRevision", "diagnosticEventHead"})
    if revision >= 6:
        required.update({"afterBuildId", "afterElfSha256", "afterInputSnapshotSha256", "sourceChangeDeclarationId"})
    if revision >= 7:
        required.add("acceptanceRecordId")
    return frozenset(required)


def _validate_stage_outputs(value: object, revision: int) -> dict[str, object]:
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != set(STAGE_OUTPUT_KEYS):
        raise AcceptanceRecoveryValidationError("stageOutputs fields are not closed")
    outputs = {key: value[key] for key in STAGE_OUTPUT_KEYS}
    required = _required_output_keys(revision)
    for key, item in outputs.items():
        if key in {"diagnosticRevision"}:
            if item is not None and (type(item) is not int or item < 0):
                raise AcceptanceRecoveryValidationError(f"{key} must be a non-negative integer or null")
            continue
        if key in {"failedBeforeTestRunId", "diagnosticSessionId", "acceptanceRecordId"}:
            if item is not None:
                _uuid(key, item)
        elif item is not None:
            _hash(key, item)
        if key in required and item is None:
            raise AcceptanceRecoveryValidationError(f"{key} is required for this revision")
        if key not in required and item is not None:
            raise AcceptanceRecoveryValidationError(f"{key} is unavailable at this revision")
    return outputs


def _validate_authorization(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != set(AUTHORIZATION_FIELDS):
        raise AcceptanceRecoveryValidationError("sourceChangeAuthorization fields are not closed")
    if value["action"] != "source-change":
        raise AcceptanceRecoveryValidationError("source change action is unsupported")
    _hash("actionDigest", value["actionDigest"])
    if type(value["authorized"]) is not bool or value["authorized"] is not True:
        raise AcceptanceRecoveryValidationError("source change authorization must be true")
    authorized_at = _utc("authorizedAtUtc", value["authorizedAtUtc"])
    diagnostic_session_id = _uuid("diagnosticSessionId", value["diagnosticSessionId"])
    revision = value["diagnosticRevision"]
    if type(revision) is not int or revision < 0:
        raise AcceptanceRecoveryValidationError("diagnosticRevision must be a non-negative integer")
    event_head = _hash("diagnosticEventHead", value["diagnosticEventHead"])
    return {
        "action": "source-change",
        "actionDigest": value["actionDigest"],
        "authorized": True,
        "authorizedAtUtc": authorized_at,
        "diagnosticSessionId": diagnostic_session_id,
        "diagnosticRevision": revision,
        "diagnosticEventHead": event_head,
    }


@dataclass(frozen=True)
class AcceptanceAttempt:
    schema: str
    attempt_id: str
    revision: int
    checkpoint_id: str
    previous_checkpoint_id: str | None
    scenario_id: str
    scenario_version: str
    scenario_digest: str
    recovery_policy_digest: str
    workspace_id: str
    logical_project_id: str
    project_origin: str
    execution_source: str
    physical_transport_evidence: bool
    status: str
    completed_stages: tuple[str, ...]
    stage_outputs: Mapping[str, object]
    source_change_authorization: Mapping[str, object] | None
    opened_at_utc: str
    deadline_at_utc: str | None
    updated_at_utc: str

    def __post_init__(self) -> None:
        if self.schema != ATTEMPT_SCHEMA:
            raise AcceptanceRecoveryValidationError("attempt schema is unsupported")
        _uuid("attemptId", self.attempt_id)
        if type(self.revision) is not int or not 0 <= self.revision <= 7:
            raise AcceptanceRecoveryValidationError("revision must be an integer from 0 through 7")
        _hash("checkpointId", self.checkpoint_id)
        if self.revision == 0:
            if self.previous_checkpoint_id is not None:
                raise AcceptanceRecoveryValidationError("revision zero cannot link a previous checkpoint")
        elif self.previous_checkpoint_id is None:
            raise AcceptanceRecoveryValidationError("revision must link its previous checkpoint")
        else:
            _hash("previousCheckpointId", self.previous_checkpoint_id)
        try:
            scenario = describe_scenario(self.scenario_id, self.scenario_version)
        except (AcceptanceValidationError, TypeError, ValueError) as error:
            raise AcceptanceRecoveryValidationError(
                "scenario identity is not an accepted VS08-A definition"
            ) from error
        if self.scenario_digest != scenario.scenario_digest:
            raise AcceptanceRecoveryValidationError("scenario digest does not match VS08-A definition")
        _hash("scenarioDigest", self.scenario_digest)
        if self.recovery_policy_digest != RECOVERY_POLICY_DIGEST:
            raise AcceptanceRecoveryValidationError("recovery policy digest is not frozen")
        _hash("recoveryPolicyDigest", self.recovery_policy_digest)
        _hash("workspaceId", self.workspace_id)
        _uuid("logicalProjectId", self.logical_project_id)
        if self.project_origin != scenario.project_origin:
            raise AcceptanceRecoveryValidationError("project origin does not match scenario")
        if self.execution_source != "replay":
            raise AcceptanceRecoveryValidationError("execution source must be replay")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            raise AcceptanceRecoveryValidationError("physical transport evidence is forbidden")
        if self.status not in {"ACTIVE", "COMPLETED"}:
            raise AcceptanceRecoveryValidationError("attempt status is unsupported")
        if not isinstance(self.completed_stages, tuple):
            raise AcceptanceRecoveryValidationError("completedStages must be a JSON array")
        expected_count = _expected_stage_count(self.revision)
        if self.completed_stages != REQUIRED_STAGES[:expected_count]:
            raise AcceptanceRecoveryValidationError("completed stages are not the exact ordered prefix")
        outputs = _validate_stage_outputs(self.stage_outputs, self.revision)
        authorization = _validate_authorization(self.source_change_authorization)
        if self.revision < 5 and authorization is not None:
            raise AcceptanceRecoveryValidationError("source authorization is only valid at revision five or later")
        if self.revision >= 5 and authorization is None:
            raise AcceptanceRecoveryValidationError("source authorization is required at revision five or later")
        if authorization is not None:
            if (
                authorization["diagnosticSessionId"] != outputs["diagnosticSessionId"]
                or authorization["diagnosticRevision"] != outputs["diagnosticRevision"]
                or authorization["diagnosticEventHead"] != outputs["diagnosticEventHead"]
            ):
                raise AcceptanceRecoveryValidationError(
                    "source authorization must bind the diagnostic checkpoint"
                )
        opened = _utc("openedAtUtc", self.opened_at_utc)
        updated = _utc("updatedAtUtc", self.updated_at_utc)
        if _timestamp_value(updated) < _timestamp_value(opened):
            raise AcceptanceRecoveryValidationError("updatedAtUtc cannot precede openedAtUtc")
        if self.revision == 7:
            if self.status != "COMPLETED" or self.deadline_at_utc is not None:
                raise AcceptanceRecoveryValidationError("completed revision must be COMPLETED with no deadline")
        else:
            if self.status != "ACTIVE" or self.deadline_at_utc is None:
                raise AcceptanceRecoveryValidationError("incomplete revision must be ACTIVE with a deadline")
            deadline = _utc("deadlineAtUtc", self.deadline_at_utc)
            if _timestamp_value(deadline) < _timestamp_value(updated):
                raise AcceptanceRecoveryValidationError("deadlineAtUtc cannot precede updatedAtUtc")
        if authorization is not None and _timestamp_value(authorization["authorizedAtUtc"]) > _timestamp_value(updated):
            raise AcceptanceRecoveryValidationError("authorization cannot follow the revision update")
        object.__setattr__(self, "stage_outputs", MappingProxyType(dict(outputs)))
        if authorization is not None:
            object.__setattr__(self, "source_change_authorization", MappingProxyType(dict(authorization)))

        expected = self._without_checkpoint()
        calculated = hashlib.sha256(canonical_json_bytes(expected)).hexdigest()
        if calculated != self.checkpoint_id:
            raise AcceptanceRecoveryValidationError("checkpointId does not match canonical snapshot")

    def _without_checkpoint(self) -> dict[str, object]:
        payload = self.to_dict()
        payload.pop("checkpointId")
        return payload

    @property
    def next_stage(self) -> str | None:
        if self.revision >= 7:
            return None
        return REQUIRED_STAGES[_expected_stage_count(self.revision)]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "attemptId": self.attempt_id,
            "revision": self.revision,
            "checkpointId": self.checkpoint_id,
            "previousCheckpointId": self.previous_checkpoint_id,
            "scenarioId": self.scenario_id,
            "scenarioVersion": self.scenario_version,
            "scenarioDigest": self.scenario_digest,
            "recoveryPolicyDigest": self.recovery_policy_digest,
            "workspaceId": self.workspace_id,
            "logicalProjectId": self.logical_project_id,
            "projectOrigin": self.project_origin,
            "executionSource": self.execution_source,
            "physicalTransportEvidence": self.physical_transport_evidence,
            "status": self.status,
            "completedStages": list(self.completed_stages),
            "stageOutputs": _copy_json(self.stage_outputs),
            "sourceChangeAuthorization": _copy_json(self.source_change_authorization),
            "openedAtUtc": self.opened_at_utc,
            "deadlineAtUtc": self.deadline_at_utc,
            "updatedAtUtc": self.updated_at_utc,
        }

    @classmethod
    def from_value(cls, value: object) -> "AcceptanceAttempt":
        _reject_tuples(value)
        if not isinstance(value, Mapping) or set(value) != _ATTEMPT_FIELDS:
            raise AcceptanceRecoveryValidationError("attempt fields are not closed")
        stages = value["completedStages"]
        if not isinstance(stages, list) or any(type(item) is not str for item in stages):
            raise AcceptanceRecoveryValidationError("completedStages must be a JSON array of strings")
        outputs = value["stageOutputs"]
        authorization = value["sourceChangeAuthorization"]
        return cls(
            schema=cast(str, value["schema"]),
            attempt_id=cast(str, value["attemptId"]),
            revision=value["revision"],  # type: ignore[arg-type]
            checkpoint_id=cast(str, value["checkpointId"]),
            previous_checkpoint_id=value["previousCheckpointId"],  # type: ignore[arg-type]
            scenario_id=cast(str, value["scenarioId"]),
            scenario_version=cast(str, value["scenarioVersion"]),
            scenario_digest=cast(str, value["scenarioDigest"]),
            recovery_policy_digest=cast(str, value["recoveryPolicyDigest"]),
            workspace_id=cast(str, value["workspaceId"]),
            logical_project_id=cast(str, value["logicalProjectId"]),
            project_origin=cast(str, value["projectOrigin"]),
            execution_source=cast(str, value["executionSource"]),
            physical_transport_evidence=value["physicalTransportEvidence"],  # type: ignore[arg-type]
            status=cast(str, value["status"]),
            completed_stages=tuple(stages),
            stage_outputs=outputs,  # type: ignore[arg-type]
            source_change_authorization=authorization,  # type: ignore[arg-type]
            opened_at_utc=cast(str, value["openedAtUtc"]),
            deadline_at_utc=value["deadlineAtUtc"],  # type: ignore[arg-type]
            updated_at_utc=cast(str, value["updatedAtUtc"]),
        )


__all__ = [
    "ATTEMPT_SCHEMA",
    "AUTHORIZATION_FIELDS",
    "AcceptanceAttempt",
    "AcceptanceRecoveryPolicy",
    "AcceptanceRecoveryValidationError",
    "RECOVERY_POLICY_DIGEST",
    "RECOVERY_POLICY_SCHEMA",
    "STAGE_OUTPUT_KEYS",
    "acceptance_recovery_policy",
]
