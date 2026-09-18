"""Closed models for the VS10-B offline evidence finalization profile.

This module is deliberately independent of Diagnostic and workflow code.  It
owns only the JSON contracts for the /2 continuation request and proof and the
two immutable /5 attempt snapshots.  The upper-level recovery adapter owns
all persisted graph authentication and publication.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import cast

from stm32_toolkit.evidence import canonical_json_bytes

from .recovery import AcceptanceRecoveryValidationError, SourceChangeIntent


FINALIZATION_SCHEMA = "stm32-physical-continuation/2"
FINALIZATION_REQUEST_SCHEMA = "stm32-physical-continuation-request/2"
FINALIZATION_ROOT_TYPE = "physical-continuation"
FINALIZATION_OPERATION = "physical-continuation"
FINALIZATION_ATTEMPT_SCHEMA = "stm32-acceptance-attempt/5"
FINALIZATION_POLICY_SCHEMA = "stm32-physical-continuation-policy/2"
FINALIZATION_SCENARIO_ID = "new-cubemx-physical-repair"
FINALIZATION_SCENARIO_VERSION = "1"
FINALIZATION_PROJECT_ORIGIN = "cubemx"
FINALIZATION_EXECUTION_SOURCE = "physical"
FINALIZATION_TRANSPORT = "mailbox"
FINALIZATION_WINDOW_SECONDS = 900
FINALIZATION_STAGES = ("verification-pending", "target-fix-verified")

_HASH = re.compile(r"^[0-9a-f]{64}$\Z")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_RUN = re.compile(r"^[a-z0-9][a-z0-9._-]*\Z")
_DIAGNOSTIC = re.compile(r"^[0-9a-f]{32}\Z")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")


class FinalizationValidationError(ValueError):
    """Raised when a finalization value is not in its closed JSON domain."""


class FinalizationEnvironmentError(FinalizationValidationError):
    """The finalization provider could not be read reliably."""


class FinalizationIdentityError(FinalizationValidationError):
    """A valid proof does not belong to the requested caller context."""


# Descriptive aliases keep the profile easy to discover for callers that use
# the continuation terminology from the public command.
ContinuationFinalizationValidationError = FinalizationValidationError
ContinuationFinalizationIdentityError = FinalizationIdentityError


def _reject_tuples(value: object) -> None:
    if isinstance(value, (tuple, frozenset)):
        raise FinalizationValidationError("tuples are not accepted on the JSON boundary")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key)
            _reject_tuples(item)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item)


def _mapping(value: object, fields: frozenset[str]) -> dict[str, object]:
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FinalizationValidationError("finalization object fields are not closed")
    return dict(cast(Mapping[str, object], value))


def _text(field: str, value: object, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 64 * 1024:
        raise FinalizationValidationError(f"{field} is invalid")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise FinalizationValidationError(f"{field} is invalid")
    return value


def _hash(field: str, value: object) -> str:
    return _text(field, value, pattern=_HASH)


def _uuid(field: str, value: object) -> str:
    return _text(field, value, pattern=_UUID)


def _run_id(field: str, value: object) -> str:
    return _text(field, value, pattern=_RUN)


def _diagnostic_id(field: str, value: object) -> str:
    return _text(field, value, pattern=_DIAGNOSTIC)


def _utc(field: str, value: object) -> str:
    result = _text(field, value, pattern=_UTC)
    try:
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise FinalizationValidationError(f"{field} is invalid") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != result:
        raise FinalizationValidationError(f"{field} is invalid")
    return result


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _hash_payload(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _intent(value: object) -> SourceChangeIntent:
    try:
        intent = SourceChangeIntent.from_value(value)
    except (AcceptanceRecoveryValidationError, TypeError, ValueError) as error:
        raise FinalizationValidationError("sourceChangeIntent is invalid") from error
    if (
        intent.before_input_snapshot_sha256 is None
        or intent.expected_after_input_snapshot_sha256 is None
        or intent.intent_digest is None
    ):
        raise FinalizationValidationError("finalization intent must be expanded")
    return intent


_PROOF_FIELDS = frozenset(
    {
        "schema", "predecessorAttemptId", "predecessorCheckpointId",
        "predecessorEvidenceId", "diagnosticSessionId", "diagnosticRevision",
        "diagnosticEventHead", "diagnosticEvidenceId", "sourceChangeDeclarationId",
        "sourceChangeIntent", "failedBeforeTestRunId", "failedBeforeEvidenceId",
        "fixedAfterTestRunId", "fixedAfterEvidenceId", "fixVerificationId",
    }
)


@dataclass(frozen=True)
class PhysicalFinalizationProof:
    """The exact immutable /2 association for the already completed B graph."""

    schema: str
    predecessor_attempt_id: str
    predecessor_checkpoint_id: str
    predecessor_evidence_id: str
    diagnostic_session_id: str
    diagnostic_revision: int
    diagnostic_event_head: str
    diagnostic_evidence_id: str
    source_change_declaration_id: str
    source_change_intent: SourceChangeIntent
    failed_before_test_run_id: str
    failed_before_evidence_id: str
    fixed_after_test_run_id: str
    fixed_after_evidence_id: str
    fix_verification_id: str

    def __post_init__(self) -> None:
        if self.schema != FINALIZATION_SCHEMA:
            raise FinalizationValidationError("finalization proof schema is unsupported")
        _uuid("predecessorAttemptId", self.predecessor_attempt_id)
        _hash("predecessorCheckpointId", self.predecessor_checkpoint_id)
        _hash("predecessorEvidenceId", self.predecessor_evidence_id)
        _diagnostic_id("diagnosticSessionId", self.diagnostic_session_id)
        if type(self.diagnostic_revision) is not int or self.diagnostic_revision < 0:
            raise FinalizationValidationError("diagnosticRevision is invalid")
        _hash("diagnosticEventHead", self.diagnostic_event_head)
        _hash("diagnosticEvidenceId", self.diagnostic_evidence_id)
        _hash("sourceChangeDeclarationId", self.source_change_declaration_id)
        if type(self.source_change_intent) is not SourceChangeIntent:
            raise FinalizationValidationError("sourceChangeIntent is invalid")
        if (
            self.source_change_intent.before_input_snapshot_sha256 is None
            or self.source_change_intent.expected_after_input_snapshot_sha256 is None
            or self.source_change_intent.intent_digest is None
        ):
            raise FinalizationValidationError("sourceChangeIntent is not expanded")
        _run_id("failedBeforeTestRunId", self.failed_before_test_run_id)
        _hash("failedBeforeEvidenceId", self.failed_before_evidence_id)
        _run_id("fixedAfterTestRunId", self.fixed_after_test_run_id)
        _hash("fixedAfterEvidenceId", self.fixed_after_evidence_id)
        _hash("fixVerificationId", self.fix_verification_id)
        if self.failed_before_test_run_id == self.fixed_after_test_run_id:
            raise FinalizationValidationError("before and after TestRuns must differ")
        if self.failed_before_evidence_id == self.fixed_after_evidence_id:
            raise FinalizationValidationError("before and after evidence must differ")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "predecessorAttemptId": self.predecessor_attempt_id,
            "predecessorCheckpointId": self.predecessor_checkpoint_id,
            "predecessorEvidenceId": self.predecessor_evidence_id,
            "diagnosticSessionId": self.diagnostic_session_id,
            "diagnosticRevision": self.diagnostic_revision,
            "diagnosticEventHead": self.diagnostic_event_head,
            "diagnosticEvidenceId": self.diagnostic_evidence_id,
            "sourceChangeDeclarationId": self.source_change_declaration_id,
            "sourceChangeIntent": self.source_change_intent.to_dict(),
            "failedBeforeTestRunId": self.failed_before_test_run_id,
            "failedBeforeEvidenceId": self.failed_before_evidence_id,
            "fixedAfterTestRunId": self.fixed_after_test_run_id,
            "fixedAfterEvidenceId": self.fixed_after_evidence_id,
            "fixVerificationId": self.fix_verification_id,
        }

    @property
    def continuation_id(self) -> str:
        return _hash_payload(self.to_dict())

    @classmethod
    def from_value(cls, value: object) -> "PhysicalFinalizationProof":
        data = _mapping(value, _PROOF_FIELDS)
        revision = data["diagnosticRevision"]
        if type(revision) is not int or revision < 0:
            raise FinalizationValidationError("diagnosticRevision is invalid")
        return cls(
            schema=_text("schema", data["schema"]),
            predecessor_attempt_id=_uuid("predecessorAttemptId", data["predecessorAttemptId"]),
            predecessor_checkpoint_id=_hash("predecessorCheckpointId", data["predecessorCheckpointId"]),
            predecessor_evidence_id=_hash("predecessorEvidenceId", data["predecessorEvidenceId"]),
            diagnostic_session_id=_diagnostic_id("diagnosticSessionId", data["diagnosticSessionId"]),
            diagnostic_revision=revision,
            diagnostic_event_head=_hash("diagnosticEventHead", data["diagnosticEventHead"]),
            diagnostic_evidence_id=_hash("diagnosticEvidenceId", data["diagnosticEvidenceId"]),
            source_change_declaration_id=_hash("sourceChangeDeclarationId", data["sourceChangeDeclarationId"]),
            source_change_intent=_intent(data["sourceChangeIntent"]),
            failed_before_test_run_id=_run_id("failedBeforeTestRunId", data["failedBeforeTestRunId"]),
            failed_before_evidence_id=_hash("failedBeforeEvidenceId", data["failedBeforeEvidenceId"]),
            fixed_after_test_run_id=_run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
            fixed_after_evidence_id=_hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
            fix_verification_id=_hash("fixVerificationId", data["fixVerificationId"]),
        )


_BIND_FIELDS = frozenset(
    {
        "schema", "kind", "predecessorAttemptId", "predecessorCheckpointId",
        "predecessorEvidenceId", "fixedAfterTestRunId", "fixedAfterEvidenceId",
        "diagnosticRevision", "diagnosticEventHead", "fixVerificationId",
    }
)
_REUSE_FIELDS = frozenset({"schema", "kind", "continuationEvidenceId"})


@dataclass(frozen=True)
class FinalizationRequest:
    schema: str
    kind: str
    predecessor_attempt_id: str | None = None
    predecessor_checkpoint_id: str | None = None
    predecessor_evidence_id: str | None = None
    fixed_after_test_run_id: str | None = None
    fixed_after_evidence_id: str | None = None
    diagnostic_revision: int | None = None
    diagnostic_event_head: str | None = None
    fix_verification_id: str | None = None
    continuation_evidence_id: str | None = None

    @classmethod
    def from_value(cls, value: object) -> "FinalizationRequest":
        _reject_tuples(value)
        if not isinstance(value, Mapping):
            raise FinalizationValidationError("finalization request must be an object")
        keys = set(value)
        if keys == _BIND_FIELDS:
            data = dict(value)
            if data.get("schema") != FINALIZATION_REQUEST_SCHEMA or data.get("kind") != "bind":
                raise FinalizationValidationError("bind request schema or kind is invalid")
            revision = data["diagnosticRevision"]
            if type(revision) is not int or revision < 0:
                raise FinalizationValidationError("diagnosticRevision is invalid")
            return cls(
                FINALIZATION_REQUEST_SCHEMA,
                "bind",
                _uuid("predecessorAttemptId", data["predecessorAttemptId"]),
                _hash("predecessorCheckpointId", data["predecessorCheckpointId"]),
                _hash("predecessorEvidenceId", data["predecessorEvidenceId"]),
                _run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
                _hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
                revision,
                _hash("diagnosticEventHead", data["diagnosticEventHead"]),
                _hash("fixVerificationId", data["fixVerificationId"]),
                None,
            )
        if keys == _REUSE_FIELDS:
            data = dict(value)
            if data.get("schema") != FINALIZATION_REQUEST_SCHEMA or data.get("kind") != "reuse":
                raise FinalizationValidationError("reuse request schema or kind is invalid")
            return cls(
                FINALIZATION_REQUEST_SCHEMA,
                "reuse",
                continuation_evidence_id=_hash("continuationEvidenceId", data["continuationEvidenceId"]),
            )
        raise FinalizationValidationError("finalization request fields are not closed")


_SCENARIO_DOCUMENT = {
    "schema": FINALIZATION_ATTEMPT_SCHEMA,
    "scenarioId": FINALIZATION_SCENARIO_ID,
    "scenarioVersion": FINALIZATION_SCENARIO_VERSION,
    "projectOrigin": FINALIZATION_PROJECT_ORIGIN,
    "executionSource": FINALIZATION_EXECUTION_SOURCE,
    "physicalTransport": FINALIZATION_TRANSPORT,
    "physicalTransportEvidence": True,
    "stages": list(FINALIZATION_STAGES),
}
FINALIZATION_SCENARIO_DIGEST = hashlib.sha256(canonical_json_bytes(_SCENARIO_DOCUMENT)).hexdigest()


def finalization_policy_document() -> dict[str, object]:
    return {
        "schema": FINALIZATION_POLICY_SCHEMA,
        "attemptSchema": FINALIZATION_ATTEMPT_SCHEMA,
        "scenarioDigest": FINALIZATION_SCENARIO_DIGEST,
        "completionWindowSeconds": FINALIZATION_WINDOW_SECONDS,
        "intrusiveActions": {},
    }


FINALIZATION_POLICY_DIGEST = _hash_payload(finalization_policy_document())


_ATTEMPT_FIELDS = frozenset(
    {
        "schema", "attemptId", "revision", "checkpointId", "previousCheckpointId",
        "scenarioId", "scenarioVersion", "scenarioDigest", "recoveryPolicyDigest",
        "workspaceId", "logicalProjectId", "sessionId", "projectOrigin",
        "executionSource", "physicalTransportEvidence", "status", "stage",
        "continuationEvidenceId", "fixedAfterTestRunId", "fixedAfterEvidenceId",
        "fixVerificationId", "openedAtUtc", "updatedAtUtc", "deadlineAtUtc",
    }
)


def _attempt_payload(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("checkpointId", None)
    return payload


@dataclass(frozen=True)
class PhysicalFinalizationAttempt:
    """One immutable revision in the offline /5 finalization chain."""

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
    session_id: str
    project_origin: str
    execution_source: str
    physical_transport_evidence: bool
    status: str
    stage: str
    continuation_evidence_id: str
    fixed_after_test_run_id: str
    fixed_after_evidence_id: str
    fix_verification_id: str | None
    opened_at_utc: str
    updated_at_utc: str
    deadline_at_utc: str

    def __post_init__(self) -> None:
        if self.schema != FINALIZATION_ATTEMPT_SCHEMA:
            raise FinalizationValidationError("attempt schema is unsupported")
        _uuid("attemptId", self.attempt_id)
        if type(self.revision) is not int or self.revision not in (0, 1):
            raise FinalizationValidationError("attempt revision is invalid")
        if self.revision == 0 and self.previous_checkpoint_id is not None:
            raise FinalizationValidationError("rev0 cannot have a predecessor")
        if self.revision == 1 and self.previous_checkpoint_id is None:
            raise FinalizationValidationError("rev1 needs a predecessor")
        if self.previous_checkpoint_id is not None:
            _hash("previousCheckpointId", self.previous_checkpoint_id)
        if (
            self.scenario_id != FINALIZATION_SCENARIO_ID
            or self.scenario_version != FINALIZATION_SCENARIO_VERSION
            or self.scenario_digest != FINALIZATION_SCENARIO_DIGEST
            or self.recovery_policy_digest != FINALIZATION_POLICY_DIGEST
        ):
            raise FinalizationValidationError("finalization scenario or policy identity is not frozen")
        _hash("scenarioDigest", self.scenario_digest)
        _hash("recoveryPolicyDigest", self.recovery_policy_digest)
        _hash("workspaceId", self.workspace_id)
        _uuid("logicalProjectId", self.logical_project_id)
        _text("sessionId", self.session_id)
        if (
            self.project_origin != FINALIZATION_PROJECT_ORIGIN
            or self.execution_source != FINALIZATION_EXECUTION_SOURCE
            or self.physical_transport_evidence is not True
        ):
            raise FinalizationValidationError("finalization provenance is invalid")
        if self.status != ("IN_PROGRESS" if self.revision == 0 else "COMPLETED"):
            raise FinalizationValidationError("finalization status is invalid")
        if self.stage != FINALIZATION_STAGES[self.revision]:
            raise FinalizationValidationError("finalization stage is invalid")
        _hash("continuationEvidenceId", self.continuation_evidence_id)
        _run_id("fixedAfterTestRunId", self.fixed_after_test_run_id)
        _hash("fixedAfterEvidenceId", self.fixed_after_evidence_id)
        if self.revision == 0:
            if self.fix_verification_id is not None:
                raise FinalizationValidationError("rev0 cannot carry fixVerificationId")
        else:
            _hash("fixVerificationId", self.fix_verification_id)
        opened = _utc("openedAtUtc", self.opened_at_utc)
        updated = _utc("updatedAtUtc", self.updated_at_utc)
        deadline = _utc("deadlineAtUtc", self.deadline_at_utc)
        if _time(updated) < _time(opened) or _time(updated) > _time(deadline):
            raise FinalizationValidationError("attempt update is outside its offline window")
        expected_deadline = (_time(opened) + timedelta(seconds=FINALIZATION_WINDOW_SECONDS)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        if deadline != expected_deadline:
            raise FinalizationValidationError("attempt deadline differs from rev0 publication window")
        if self.revision == 0 and updated != opened:
            raise FinalizationValidationError("rev0 opened and updated times differ")
        if _hash_payload(_attempt_payload(self.to_dict())) != self.checkpoint_id:
            raise FinalizationValidationError("checkpointId does not match the snapshot")

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
            "sessionId": self.session_id,
            "projectOrigin": self.project_origin,
            "executionSource": self.execution_source,
            "physicalTransportEvidence": self.physical_transport_evidence,
            "status": self.status,
            "stage": self.stage,
            "continuationEvidenceId": self.continuation_evidence_id,
            "fixedAfterTestRunId": self.fixed_after_test_run_id,
            "fixedAfterEvidenceId": self.fixed_after_evidence_id,
            "fixVerificationId": self.fix_verification_id,
            "openedAtUtc": self.opened_at_utc,
            "updatedAtUtc": self.updated_at_utc,
            "deadlineAtUtc": self.deadline_at_utc,
        }

    @property
    def next_stage(self) -> str | None:
        return None if self.revision == 1 else FINALIZATION_STAGES[1]

    @classmethod
    def from_value(cls, value: object) -> "PhysicalFinalizationAttempt":
        data = _mapping(value, _ATTEMPT_FIELDS)
        return cls(
            schema=_text("schema", data["schema"]),
            attempt_id=_uuid("attemptId", data["attemptId"]),
            revision=data["revision"],  # type: ignore[arg-type]
            checkpoint_id=_hash("checkpointId", data["checkpointId"]),
            previous_checkpoint_id=None if data["previousCheckpointId"] is None else _hash("previousCheckpointId", data["previousCheckpointId"]),
            scenario_id=_text("scenarioId", data["scenarioId"]),
            scenario_version=_text("scenarioVersion", data["scenarioVersion"]),
            scenario_digest=_hash("scenarioDigest", data["scenarioDigest"]),
            recovery_policy_digest=_hash("recoveryPolicyDigest", data["recoveryPolicyDigest"]),
            workspace_id=_hash("workspaceId", data["workspaceId"]),
            logical_project_id=_uuid("logicalProjectId", data["logicalProjectId"]),
            session_id=_text("sessionId", data["sessionId"]),
            project_origin=_text("projectOrigin", data["projectOrigin"]),
            execution_source=_text("executionSource", data["executionSource"]),
            physical_transport_evidence=data["physicalTransportEvidence"],  # type: ignore[arg-type]
            status=_text("status", data["status"]),
            stage=_text("stage", data["stage"]),
            continuation_evidence_id=_hash("continuationEvidenceId", data["continuationEvidenceId"]),
            fixed_after_test_run_id=_run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
            fixed_after_evidence_id=_hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
            fix_verification_id=None if data["fixVerificationId"] is None else _hash("fixVerificationId", data["fixVerificationId"]),
            opened_at_utc=_utc("openedAtUtc", data["openedAtUtc"]),
            updated_at_utc=_utc("updatedAtUtc", data["updatedAtUtc"]),
            deadline_at_utc=_utc("deadlineAtUtc", data["deadlineAtUtc"]),
        )


@dataclass(frozen=True)
class AuthenticatedFinalization:
    """Workflow-owned graph result with intentionally opaque authority types."""

    proof: PhysicalFinalizationProof
    envelope: object
    root: object
    predecessor: object
    predecessor_envelope: object
    before: object
    after: object
    diagnostic: object

    @property
    def continuation_evidence_id(self) -> str:
        return str(getattr(self.envelope, "evidence_id"))


# Publicly useful compatibility names; the wire identities above remain the
# only source of truth.
PhysicalContinuationFinalizationProof = PhysicalFinalizationProof
PhysicalContinuationFinalizationAttempt = PhysicalFinalizationAttempt


__all__ = [
    "FINALIZATION_ATTEMPT_SCHEMA", "FINALIZATION_EXECUTION_SOURCE",
    "FINALIZATION_OPERATION", "FINALIZATION_POLICY_DIGEST", "FINALIZATION_POLICY_SCHEMA",
    "FINALIZATION_PROJECT_ORIGIN", "FINALIZATION_REQUEST_SCHEMA", "FINALIZATION_ROOT_TYPE",
    "FINALIZATION_SCENARIO_DIGEST", "FINALIZATION_SCENARIO_ID", "FINALIZATION_SCENARIO_VERSION",
    "FINALIZATION_STAGES", "FINALIZATION_TRANSPORT", "FINALIZATION_WINDOW_SECONDS",
    "FINALIZATION_SCHEMA", "AuthenticatedFinalization", "FinalizationEnvironmentError",
    "FinalizationIdentityError", "FinalizationRequest", "FinalizationValidationError",
    "PhysicalFinalizationAttempt", "PhysicalFinalizationProof", "finalization_policy_document",
    "ContinuationFinalizationValidationError", "ContinuationFinalizationIdentityError",
    "PhysicalContinuationFinalizationProof", "PhysicalContinuationFinalizationAttempt",
]
