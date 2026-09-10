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

# Task 10 deliberately has a separate immutable attempt model.  The VS08
# replay model above is a published compatibility contract and must not be
# widened to carry physical evidence or native Target run identifiers.
PHYSICAL_ATTEMPT_SCHEMA = "stm32-acceptance-attempt/2"
PHYSICAL_RECOVERY_POLICY_SCHEMA = "stm32-acceptance-recovery-policy/2"
PHYSICAL_SCENARIO_ID = "legacy-keil-physical-repair"
PHYSICAL_SCENARIO_VERSION = "1"
PHYSICAL_TRANSPORT = "mailbox"
PHYSICAL_STAGES = (
    "project-materialized",
    "firmware-built-before",
    "target-failure-observed",
    "diagnosis-completed",
    "firmware-built-after",
    "target-fix-verified",
)
PHYSICAL_STAGE_OUTPUT_KEYS = (
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
    "fixedAfterTestRunId",
    "fixedAfterEvidenceId",
    "fixVerificationId",
)
PHYSICAL_POLICY_TIMEOUTS = {
    "project-materialized": 60,
    "firmware-built-before": 900,
    "target-failure-observed": 300,
    "diagnosis-completed": 900,
    "firmware-built-after": 900,
    "target-fix-verified": 300,
}
PHYSICAL_POLICY_ACTIONS = {
    "source-change": {
        "afterStage": "diagnosis-completed",
        "applicable": True,
        "authorization": "explicit-single-use",
        "beforeStage": "firmware-built-after",
    },
    "flash": {
        "applicable": False,
        "authorization": "existing-probe-action-digest",
        "reason": "recovery-adapter-no-hardware",
    },
}
_PHYSICAL_SCENARIO_DOCUMENT = {
    "scenarioId": PHYSICAL_SCENARIO_ID,
    "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
    "projectOrigin": "keil",
    "executionSource": "physical",
    "transport": PHYSICAL_TRANSPORT,
    "physicalTransportEvidence": True,
    "stages": PHYSICAL_STAGES,
}
PHYSICAL_SCENARIO_DIGEST = hashlib.sha256(
    canonical_json_bytes(_PHYSICAL_SCENARIO_DOCUMENT)
).hexdigest()
_PHYSICAL_POLICY_DOCUMENT = {
    "schema": PHYSICAL_RECOVERY_POLICY_SCHEMA,
    "attemptSchema": PHYSICAL_ATTEMPT_SCHEMA,
    "scenarioId": PHYSICAL_SCENARIO_ID,
    "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
    "scenarioDigest": PHYSICAL_SCENARIO_DIGEST,
    "stageTimeoutSeconds": PHYSICAL_POLICY_TIMEOUTS,
    "intrusiveActions": PHYSICAL_POLICY_ACTIONS,
    "physicalTransportEvidence": True,
}
PHYSICAL_RECOVERY_POLICY_DIGEST = hashlib.sha256(
    canonical_json_bytes(_PHYSICAL_POLICY_DOCUMENT)
).hexdigest()
_PHYSICAL_ATTEMPT_FIELDS = _ATTEMPT_FIELDS | {"sourceChangeIntent"}
_PHYSICAL_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PHYSICAL_DIAGNOSTIC_ID = re.compile(r"^[0-9a-f]{32}$")
SOURCE_CHANGE_INTENT_SCHEMA = "stm32-source-change-intent/1"
_SOURCE_CHANGE_INTENT_INPUT_FIELDS = {"schema", "changes"}
_SOURCE_CHANGE_INTENT_FIELDS = {
    "schema",
    "changes",
    "beforeInputSnapshotSha256",
    "expectedAfterInputSnapshotSha256",
    "intentDigest",
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


def _physical_run_id(field: str, value: object) -> str:
    string = _string(field, value)
    if _PHYSICAL_RUN_ID.fullmatch(string) is None:
        raise AcceptanceRecoveryValidationError(
            f"{field} must be a native Target run identifier"
        )
    return string


def _physical_diagnostic_id(field: str, value: object) -> str:
    string = _string(field, value)
    if _PHYSICAL_DIAGNOSTIC_ID.fullmatch(string) is None:
        raise AcceptanceRecoveryValidationError(
            f"{field} must be a 32-hex Diagnostic session identifier"
        )
    return string


def _source_path(value: object) -> str:
    path = _string("path", value)
    if (
        "\\" in path
        or ":" in path
        or path.startswith("/")
        or any(component in {"", ".", ".."} for component in path.split("/"))
    ):
        raise AcceptanceRecoveryValidationError("path must be a portable project-relative source path")
    return path


def _source_change(value: object) -> dict[str, object]:
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != {
        "path", "beforeSha256", "afterSha256", "afterSize"
    }:
        raise AcceptanceRecoveryValidationError("source change fields are not closed")
    after_size = value["afterSize"]
    if type(after_size) is not int or not 0 <= after_size <= 8 * 1024 * 1024:
        raise AcceptanceRecoveryValidationError("afterSize is outside the source file limit")
    before_sha256 = _hash("beforeSha256", value["beforeSha256"])
    after_sha256 = _hash("afterSha256", value["afterSha256"])
    if before_sha256 == after_sha256:
        raise AcceptanceRecoveryValidationError("source change must change the file hash")
    return {
        "path": _source_path(value["path"]),
        "beforeSha256": before_sha256,
        "afterSha256": after_sha256,
        "afterSize": after_size,
    }


@dataclass(frozen=True)
class SourceChangeIntent:
    """Closed source replacement intent carried by a physical recovery attempt.

    The two snapshot digests and ``intent_digest`` are absent on caller input
    and are required on the immutable revision-4 snapshot onward.  Keeping the
    derived fields inside this object means retries and authorization compare
    the exact expanded intent rather than reconstructing it from a scalar hash.
    """

    schema: str
    changes: tuple[Mapping[str, object], ...]
    before_input_snapshot_sha256: str | None = None
    expected_after_input_snapshot_sha256: str | None = None
    intent_digest: str | None = None

    def __post_init__(self) -> None:
        if self.schema != SOURCE_CHANGE_INTENT_SCHEMA:
            raise AcceptanceRecoveryValidationError("source change intent schema is unsupported")
        if type(self.changes) is not tuple or not 1 <= len(self.changes) <= 32:
            raise AcceptanceRecoveryValidationError("source change intent changes are invalid")
        changes = tuple(_source_change(item) for item in self.changes)
        paths = tuple(cast(str, item["path"]) for item in changes)
        if len(set(paths)) != len(paths) or paths != tuple(sorted(paths, key=lambda item: item.encode("utf-8"))):
            raise AcceptanceRecoveryValidationError("source change paths must be unique and lexical")
        before = self.before_input_snapshot_sha256
        expected = self.expected_after_input_snapshot_sha256
        digest = self.intent_digest
        if (before is None) != (expected is None) or (before is None) != (digest is None):
            raise AcceptanceRecoveryValidationError("expanded source change intent fields are incomplete")
        if before is not None:
            before = _hash("beforeInputSnapshotSha256", before)
            expected = _hash("expectedAfterInputSnapshotSha256", expected)
            digest = _hash("intentDigest", digest)
            payload = {
                "schema": SOURCE_CHANGE_INTENT_SCHEMA,
                "changes": [dict(item) for item in changes],
                "beforeInputSnapshotSha256": before,
                "expectedAfterInputSnapshotSha256": expected,
            }
            calculated = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
            if calculated != digest:
                raise AcceptanceRecoveryValidationError("intentDigest does not match source change intent")
        object.__setattr__(self, "changes", tuple(MappingProxyType(dict(item)) for item in changes))
        object.__setattr__(self, "before_input_snapshot_sha256", before)
        object.__setattr__(self, "expected_after_input_snapshot_sha256", expected)
        object.__setattr__(self, "intent_digest", digest)

    @classmethod
    def new(cls, *, changes: object) -> "SourceChangeIntent":
        _reject_tuples(changes)
        if not isinstance(changes, list):
            raise AcceptanceRecoveryValidationError("changes must be a JSON array")
        return cls(SOURCE_CHANGE_INTENT_SCHEMA, tuple(_source_change(item) for item in changes))

    @classmethod
    def expanded(
        cls,
        *,
        changes: object,
        before_input_snapshot_sha256: str,
        expected_after_input_snapshot_sha256: str,
    ) -> "SourceChangeIntent":
        candidate = cls.new(changes=changes)
        before = _hash("beforeInputSnapshotSha256", before_input_snapshot_sha256)
        expected = _hash("expectedAfterInputSnapshotSha256", expected_after_input_snapshot_sha256)
        payload = {
            "schema": SOURCE_CHANGE_INTENT_SCHEMA,
            "changes": [dict(item) for item in candidate.changes],
            "beforeInputSnapshotSha256": before,
            "expectedAfterInputSnapshotSha256": expected,
        }
        digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        return cls(
            SOURCE_CHANGE_INTENT_SCHEMA,
            candidate.changes,
            before,
            expected,
            digest,
        )

    @classmethod
    def from_value(cls, value: object) -> "SourceChangeIntent":
        _reject_tuples(value)
        if not isinstance(value, Mapping):
            raise AcceptanceRecoveryValidationError("source change intent must be an object")
        keys = set(value)
        if value.get("schema") != SOURCE_CHANGE_INTENT_SCHEMA:
            raise AcceptanceRecoveryValidationError("source change intent schema is unsupported")
        if keys == _SOURCE_CHANGE_INTENT_INPUT_FIELDS:
            return cls.new(changes=value["changes"])
        if keys != _SOURCE_CHANGE_INTENT_FIELDS:
            raise AcceptanceRecoveryValidationError("source change intent fields are not closed")
        changes = value["changes"]
        if not isinstance(changes, list):
            raise AcceptanceRecoveryValidationError("changes must be a JSON array")
        return cls(
            cast(str, value["schema"]),
            tuple(changes),
            cast(str, value["beforeInputSnapshotSha256"]),
            cast(str, value["expectedAfterInputSnapshotSha256"]),
            cast(str, value["intentDigest"]),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": self.schema,
            "changes": [dict(item) for item in self.changes],
        }
        if self.intent_digest is not None:
            result.update(
                {
                    "beforeInputSnapshotSha256": self.before_input_snapshot_sha256,
                    "expectedAfterInputSnapshotSha256": self.expected_after_input_snapshot_sha256,
                    "intentDigest": self.intent_digest,
                }
            )
        return result


def physical_acceptance_scenario() -> Mapping[str, object]:
    """Return the immutable Task 10 physical scenario definition."""
    return MappingProxyType(dict(_PHYSICAL_SCENARIO_DOCUMENT))


def physical_acceptance_recovery_policy() -> "PhysicalAcceptanceRecoveryPolicy":
    return PhysicalAcceptanceRecoveryPolicy(
        schema=PHYSICAL_RECOVERY_POLICY_SCHEMA,
        attempt_schema=PHYSICAL_ATTEMPT_SCHEMA,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        scenario_digest=PHYSICAL_SCENARIO_DIGEST,
        stage_timeout_seconds=MappingProxyType(dict(PHYSICAL_POLICY_TIMEOUTS)),
        intrusive_actions=MappingProxyType(
            {key: MappingProxyType(dict(value)) for key, value in PHYSICAL_POLICY_ACTIONS.items()}
        ),
        physical_transport_evidence=True,
    )


@dataclass(frozen=True)
class PhysicalAcceptanceRecoveryPolicy:
    schema: str
    attempt_schema: str
    scenario_id: str
    scenario_version: str
    scenario_digest: str
    stage_timeout_seconds: Mapping[str, int]
    intrusive_actions: Mapping[str, Mapping[str, object]]
    physical_transport_evidence: bool

    def __post_init__(self) -> None:
        if (
            self.schema != PHYSICAL_RECOVERY_POLICY_SCHEMA
            or self.attempt_schema != PHYSICAL_ATTEMPT_SCHEMA
            or self.scenario_id != PHYSICAL_SCENARIO_ID
            or self.scenario_version != PHYSICAL_SCENARIO_VERSION
            or self.scenario_digest != PHYSICAL_SCENARIO_DIGEST
            or self.physical_transport_evidence is not True
            or dict(self.stage_timeout_seconds) != PHYSICAL_POLICY_TIMEOUTS
            or {key: dict(value) for key, value in self.intrusive_actions.items()}
            != PHYSICAL_POLICY_ACTIONS
        ):
            raise AcceptanceRecoveryValidationError("physical recovery policy is not frozen")
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
            "scenarioId": self.scenario_id,
            "scenarioVersion": self.scenario_version,
            "scenarioDigest": self.scenario_digest,
            "stageTimeoutSeconds": dict(self.stage_timeout_seconds),
            "intrusiveActions": {key: dict(value) for key, value in self.intrusive_actions.items()},
            "physicalTransportEvidence": self.physical_transport_evidence,
        }

    @classmethod
    def from_value(cls, value: object) -> "PhysicalAcceptanceRecoveryPolicy":
        _reject_tuples(value)
        expected = set(_PHYSICAL_POLICY_DOCUMENT)
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AcceptanceRecoveryValidationError("physical recovery policy fields are not closed")
        timeouts = value["stageTimeoutSeconds"]
        actions = value["intrusiveActions"]
        if not isinstance(timeouts, Mapping) or not isinstance(actions, Mapping):
            raise AcceptanceRecoveryValidationError("physical recovery policy objects are invalid")
        return cls(
            schema=cast(str, value["schema"]),
            attempt_schema=cast(str, value["attemptSchema"]),
            scenario_id=cast(str, value["scenarioId"]),
            scenario_version=cast(str, value["scenarioVersion"]),
            scenario_digest=cast(str, value["scenarioDigest"]),
            stage_timeout_seconds=timeouts,  # type: ignore[arg-type]
            intrusive_actions=actions,  # type: ignore[arg-type]
            physical_transport_evidence=value["physicalTransportEvidence"],  # type: ignore[arg-type]
        )


def _physical_expected_stage_count(revision: int) -> int:
    return revision if revision <= 4 else revision - 1


def _physical_required_output_keys(revision: int) -> frozenset[str]:
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
        required.update({"fixedAfterTestRunId", "fixedAfterEvidenceId", "fixVerificationId"})
    return frozenset(required)


def _validate_physical_stage_outputs(value: object, revision: int) -> dict[str, object]:
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != set(PHYSICAL_STAGE_OUTPUT_KEYS):
        raise AcceptanceRecoveryValidationError("stageOutputs fields are not closed")
    outputs = {key: value[key] for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    required = _physical_required_output_keys(revision)
    for key, item in outputs.items():
        if key == "diagnosticRevision":
            if item is not None and (type(item) is not int or item < 0):
                raise AcceptanceRecoveryValidationError("diagnosticRevision must be a non-negative integer or null")
        elif key in {"failedBeforeTestRunId", "fixedAfterTestRunId"}:
            if item is not None:
                _physical_run_id(key, item)
        elif key == "diagnosticSessionId":
            if item is not None:
                _physical_diagnostic_id(key, item)
        elif item is not None:
            _hash(key, item)
        if key in required and item is None:
            raise AcceptanceRecoveryValidationError(f"{key} is required for this revision")
        if key not in required and item is not None:
            raise AcceptanceRecoveryValidationError(f"{key} is unavailable at this revision")
    return outputs


def _validate_physical_authorization(value: object) -> dict[str, object] | None:
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
    revision = value["diagnosticRevision"]
    if type(revision) is not int or revision < 0:
        raise AcceptanceRecoveryValidationError("diagnosticRevision must be a non-negative integer")
    return {
        "action": "source-change",
        "actionDigest": value["actionDigest"],
        "authorized": True,
        "authorizedAtUtc": _utc("authorizedAtUtc", value["authorizedAtUtc"]),
        "diagnosticSessionId": _physical_diagnostic_id("diagnosticSessionId", value["diagnosticSessionId"]),
        "diagnosticRevision": revision,
        "diagnosticEventHead": _hash("diagnosticEventHead", value["diagnosticEventHead"]),
    }


@dataclass(frozen=True)
class PhysicalAcceptanceAttempt:
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
    source_change_intent: SourceChangeIntent | None
    opened_at_utc: str
    deadline_at_utc: str | None
    updated_at_utc: str

    def __post_init__(self) -> None:
        if self.schema != PHYSICAL_ATTEMPT_SCHEMA:
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
        if (
            self.scenario_id != PHYSICAL_SCENARIO_ID
            or self.scenario_version != PHYSICAL_SCENARIO_VERSION
            or self.scenario_digest != PHYSICAL_SCENARIO_DIGEST
            or self.recovery_policy_digest != PHYSICAL_RECOVERY_POLICY_DIGEST
        ):
            raise AcceptanceRecoveryValidationError("physical scenario or policy identity is not frozen")
        _hash("scenarioDigest", self.scenario_digest)
        _hash("recoveryPolicyDigest", self.recovery_policy_digest)
        _hash("workspaceId", self.workspace_id)
        _uuid("logicalProjectId", self.logical_project_id)
        if self.project_origin != "keil":
            raise AcceptanceRecoveryValidationError("physical recovery requires a Keil project")
        if self.execution_source != "physical":
            raise AcceptanceRecoveryValidationError("physical recovery execution source is frozen")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence != (self.revision >= 3):
            raise AcceptanceRecoveryValidationError("physical transport evidence has an invalid revision profile")
        if self.status not in {"ACTIVE", "COMPLETED"}:
            raise AcceptanceRecoveryValidationError("attempt status is unsupported")
        if type(self.completed_stages) is not tuple or self.completed_stages != PHYSICAL_STAGES[: _physical_expected_stage_count(self.revision)]:
            raise AcceptanceRecoveryValidationError("completed stages are not the exact ordered prefix")
        outputs = _validate_physical_stage_outputs(self.stage_outputs, self.revision)
        authorization = _validate_physical_authorization(self.source_change_authorization)
        intent = self.source_change_intent
        if self.revision < 4 and intent is not None:
            raise AcceptanceRecoveryValidationError("source change intent is only valid at revision four or later")
        if self.revision >= 4 and type(intent) is not SourceChangeIntent:
            raise AcceptanceRecoveryValidationError("source change intent is required at revision four or later")
        if self.revision >= 4 and (
            intent is None
            or intent.before_input_snapshot_sha256 is None
            or intent.expected_after_input_snapshot_sha256 is None
            or intent.intent_digest is None
            or intent.before_input_snapshot_sha256 != outputs["beforeInputSnapshotSha256"]
        ):
            raise AcceptanceRecoveryValidationError(
                "source change intent must be expanded and bound to the before snapshot"
            )
        if self.revision >= 6 and (
            intent is None
            or intent.expected_after_input_snapshot_sha256 != outputs["afterInputSnapshotSha256"]
        ):
            raise AcceptanceRecoveryValidationError(
                "source change intent must be bound to the after snapshot"
            )
        if self.revision < 5 and authorization is not None:
            raise AcceptanceRecoveryValidationError("source authorization is only valid at revision five or later")
        if self.revision >= 5 and authorization is None:
            raise AcceptanceRecoveryValidationError("source authorization is required at revision five or later")
        if authorization is not None and (
            authorization["diagnosticSessionId"] != outputs["diagnosticSessionId"]
            or authorization["diagnosticRevision"] != outputs["diagnosticRevision"]
            or authorization["diagnosticEventHead"] != outputs["diagnosticEventHead"]
        ):
            raise AcceptanceRecoveryValidationError("source authorization must bind the diagnostic checkpoint")
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
        object.__setattr__(self, "source_change_intent", intent)
        expected = self._without_checkpoint()
        if hashlib.sha256(canonical_json_bytes(expected)).hexdigest() != self.checkpoint_id:
            raise AcceptanceRecoveryValidationError("checkpointId does not match canonical snapshot")

    def _without_checkpoint(self) -> dict[str, object]:
        payload = self.to_dict()
        payload.pop("checkpointId")
        return payload

    @property
    def next_stage(self) -> str | None:
        if self.revision >= 7:
            return None
        return PHYSICAL_STAGES[_physical_expected_stage_count(self.revision)]

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
            "sourceChangeIntent": _copy_json(self.source_change_intent.to_dict() if self.source_change_intent is not None else None),
            "openedAtUtc": self.opened_at_utc,
            "deadlineAtUtc": self.deadline_at_utc,
            "updatedAtUtc": self.updated_at_utc,
        }

    @classmethod
    def from_value(cls, value: object) -> "PhysicalAcceptanceAttempt":
        _reject_tuples(value)
        if not isinstance(value, Mapping) or set(value) != _PHYSICAL_ATTEMPT_FIELDS:
            raise AcceptanceRecoveryValidationError("physical attempt fields are not closed")
        stages = value["completedStages"]
        if not isinstance(stages, list) or any(type(item) is not str for item in stages):
            raise AcceptanceRecoveryValidationError("completedStages must be a JSON array of strings")
        raw_intent = value["sourceChangeIntent"]
        intent = None if raw_intent is None else SourceChangeIntent.from_value(raw_intent)
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
            stage_outputs=value["stageOutputs"],  # type: ignore[arg-type]
            source_change_authorization=value["sourceChangeAuthorization"],  # type: ignore[arg-type]
            source_change_intent=intent,
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
    "PHYSICAL_ATTEMPT_SCHEMA",
    "PHYSICAL_RECOVERY_POLICY_DIGEST",
    "PHYSICAL_RECOVERY_POLICY_SCHEMA",
    "PHYSICAL_SCENARIO_DIGEST",
    "PHYSICAL_SCENARIO_ID",
    "PHYSICAL_SCENARIO_VERSION",
    "PHYSICAL_TRANSPORT",
    "PHYSICAL_STAGE_OUTPUT_KEYS",
    "PHYSICAL_STAGES",
    "PhysicalAcceptanceAttempt",
    "PhysicalAcceptanceRecoveryPolicy",
    "RECOVERY_POLICY_DIGEST",
    "RECOVERY_POLICY_SCHEMA",
    "SOURCE_CHANGE_INTENT_SCHEMA",
    "SourceChangeIntent",
    "STAGE_OUTPUT_KEYS",
    "acceptance_recovery_policy",
    "physical_acceptance_recovery_policy",
    "physical_acceptance_scenario",
]
