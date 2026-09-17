"""Immutable cross-session physical continuation proof and v3 attempt values.

This module deliberately sits below the workflow adapters.  It only knows the
canonical EvidenceStore, the immutable v2 attempt model, Diagnostic event
reducers, and the TestRun publication authority.  In particular it does not
load ``DiagnosticStore`` or any workflow module while authenticating a proof.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import cast

from stm32_toolkit.diagnostics.events import reduce_event, diagnostic_event_references
from stm32_toolkit.diagnostics.model import (
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticValidationError,
    FixVerification,
    SourceChangeDeclaration,
    canonical_diagnostic_json_bytes,
)
from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
    get_root,
)
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.store import EvidenceStore, MAX_EVIDENCE_READ_BYTES
from stm32_toolkit.testing.publication import PublishedTestRun, TestRunRepository

from .recovery import (
    AcceptanceRecoveryValidationError,
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_SCENARIO_DIGEST,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_TRANSPORT,
    PHYSICAL_STAGES,
    physical_acceptance_recovery_policy,
    PhysicalAcceptanceAttempt,
    SourceChangeIntent,
)


CONTINUATION_SCHEMA = "stm32-physical-continuation/1"
CONTINUATION_REQUEST_SCHEMA = "stm32-physical-continuation-request/1"
CONTINUATION_ROOT_TYPE = "physical-continuation"
CONTINUATION_OPERATION = "physical-continuation"
CONTINUATION_ATTEMPT_SCHEMA = "stm32-acceptance-attempt/3"
CONTINUATION_POLICY_SCHEMA = "stm32-physical-continuation-policy/1"
CONTINUATION_LINEAGE_SCHEMA = "stm32-monitor-analysis-lineage/2"
CONTINUATION_ANALYSIS_SCHEMA = "stm32-monitor-analysis/2"
VERIFICATION_PLAN_CONTINUATION_SCHEMA = "stm32-verification-plan/2"
CONTINUATION_WINDOW_SECONDS = 900
CONTINUATION_STAGES = ("verification-pending", "target-fix-verified")

_HASH = re.compile(r"^[0-9a-f]{64}$\Z")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_RUN = re.compile(r"^[a-z0-9][a-z0-9._-]*\Z")
_DIAGNOSTIC = re.compile(r"^[0-9a-f]{32}\Z")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")


class ContinuationValidationError(ValueError):
    """Raised when an immutable continuation input or graph is invalid."""


def _reject_tuples(value: object) -> None:
    if isinstance(value, (tuple, frozenset)):
        raise ContinuationValidationError("tuples are not accepted on the JSON boundary")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_tuples(item)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item)


def _mapping(value: object, fields: frozenset[str]) -> dict[str, object]:
    _reject_tuples(value)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContinuationValidationError("continuation object fields are not closed")
    return dict(cast(Mapping[str, object], value))


def _text(field: str, value: object, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 64 * 1024:
        raise ContinuationValidationError(f"{field} is invalid")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContinuationValidationError(f"{field} is invalid")
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
        datetime.strptime(result, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ContinuationValidationError(f"{field} is invalid") from error
    return result


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _hash_payload(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


_PROOF_FIELDS = frozenset(
    {
        "schema", "predecessorAttemptId", "predecessorCheckpointId",
        "predecessorEvidenceId", "diagnosticSessionId", "diagnosticRevision",
        "diagnosticEventHead", "diagnosticEvidenceId", "sourceChangeDeclarationId",
        "sourceChangeIntent", "failedBeforeTestRunId", "failedBeforeEvidenceId",
        "fixedAfterTestRunId", "fixedAfterEvidenceId",
    }
)


def _intent(value: object) -> SourceChangeIntent:
    try:
        intent = SourceChangeIntent.from_value(value)
    except (AcceptanceRecoveryValidationError, TypeError, ValueError) as error:
        raise ContinuationValidationError("sourceChangeIntent is invalid") from error
    if intent.before_input_snapshot_sha256 is None or intent.expected_after_input_snapshot_sha256 is None:
        raise ContinuationValidationError("continuation intent must be expanded")
    return intent


@dataclass(frozen=True)
class PhysicalContinuationProof:
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

    def __post_init__(self) -> None:
        if self.schema != CONTINUATION_SCHEMA:
            raise ContinuationValidationError("continuation schema is unsupported")
        _uuid("predecessorAttemptId", self.predecessor_attempt_id)
        _hash("predecessorCheckpointId", self.predecessor_checkpoint_id)
        _hash("predecessorEvidenceId", self.predecessor_evidence_id)
        _diagnostic_id("diagnosticSessionId", self.diagnostic_session_id)
        if type(self.diagnostic_revision) is not int or self.diagnostic_revision < 0:
            raise ContinuationValidationError("diagnosticRevision is invalid")
        _hash("diagnosticEventHead", self.diagnostic_event_head)
        _hash("diagnosticEvidenceId", self.diagnostic_evidence_id)
        _hash("sourceChangeDeclarationId", self.source_change_declaration_id)
        if type(self.source_change_intent) is not SourceChangeIntent:
            raise ContinuationValidationError("sourceChangeIntent is invalid")
        _run_id("failedBeforeTestRunId", self.failed_before_test_run_id)
        _hash("failedBeforeEvidenceId", self.failed_before_evidence_id)
        _run_id("fixedAfterTestRunId", self.fixed_after_test_run_id)
        _hash("fixedAfterEvidenceId", self.fixed_after_evidence_id)
        if self.failed_before_test_run_id == self.fixed_after_test_run_id:
            raise ContinuationValidationError("before and after TestRuns must differ")
        if self.failed_before_evidence_id == self.fixed_after_evidence_id:
            raise ContinuationValidationError("before and after evidence must differ")

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
        }

    @property
    def continuation_id(self) -> str:
        return _hash_payload(self.to_dict())

    @classmethod
    def from_value(cls, value: object) -> "PhysicalContinuationProof":
        data = _mapping(value, _PROOF_FIELDS)
        return cls(
            schema=_text("schema", data["schema"]),
            predecessor_attempt_id=_uuid("predecessorAttemptId", data["predecessorAttemptId"]),
            predecessor_checkpoint_id=_hash("predecessorCheckpointId", data["predecessorCheckpointId"]),
            predecessor_evidence_id=_hash("predecessorEvidenceId", data["predecessorEvidenceId"]),
            diagnostic_session_id=_diagnostic_id("diagnosticSessionId", data["diagnosticSessionId"]),
            diagnostic_revision=data["diagnosticRevision"],  # type: ignore[arg-type]
            diagnostic_event_head=_hash("diagnosticEventHead", data["diagnosticEventHead"]),
            diagnostic_evidence_id=_hash("diagnosticEvidenceId", data["diagnosticEvidenceId"]),
            source_change_declaration_id=_hash("sourceChangeDeclarationId", data["sourceChangeDeclarationId"]),
            source_change_intent=_intent(data["sourceChangeIntent"]),
            failed_before_test_run_id=_run_id("failedBeforeTestRunId", data["failedBeforeTestRunId"]),
            failed_before_evidence_id=_hash("failedBeforeEvidenceId", data["failedBeforeEvidenceId"]),
            fixed_after_test_run_id=_run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
            fixed_after_evidence_id=_hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
        )


_BIND_FIELDS = frozenset(
    {
        "schema", "kind", "predecessorAttemptId", "predecessorCheckpointId",
        "predecessorEvidenceId", "fixedAfterTestRunId", "fixedAfterEvidenceId",
        "diagnosticRevision", "diagnosticEventHead",
    }
)
_REUSE_FIELDS = frozenset({"schema", "kind", "continuationEvidenceId"})


@dataclass(frozen=True)
class ContinuationRequest:
    schema: str
    kind: str
    predecessor_attempt_id: str | None = None
    predecessor_checkpoint_id: str | None = None
    predecessor_evidence_id: str | None = None
    fixed_after_test_run_id: str | None = None
    fixed_after_evidence_id: str | None = None
    diagnostic_revision: int | None = None
    diagnostic_event_head: str | None = None
    continuation_evidence_id: str | None = None

    @classmethod
    def from_value(cls, value: object) -> "ContinuationRequest":
        _reject_tuples(value)
        if not isinstance(value, Mapping):
            raise ContinuationValidationError("continuation request must be an object")
        keys = set(value)
        if keys == _BIND_FIELDS:
            data = dict(value)
            if data.get("schema") != CONTINUATION_REQUEST_SCHEMA or data.get("kind") != "bind":
                raise ContinuationValidationError("bind request schema or kind is invalid")
            revision = data["diagnosticRevision"]
            if type(revision) is not int or revision < 0:
                raise ContinuationValidationError("diagnosticRevision is invalid")
            return cls(
                CONTINUATION_REQUEST_SCHEMA, "bind",
                _uuid("predecessorAttemptId", data["predecessorAttemptId"]),
                _hash("predecessorCheckpointId", data["predecessorCheckpointId"]),
                _hash("predecessorEvidenceId", data["predecessorEvidenceId"]),
                _run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
                _hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
                revision,
                _hash("diagnosticEventHead", data["diagnosticEventHead"]),
                None,
            )
        if keys == _REUSE_FIELDS:
            data = dict(value)
            if data.get("schema") != CONTINUATION_REQUEST_SCHEMA or data.get("kind") != "reuse":
                raise ContinuationValidationError("reuse request schema or kind is invalid")
            return cls(
                CONTINUATION_REQUEST_SCHEMA, "reuse", continuation_evidence_id=_hash(
                    "continuationEvidenceId", data["continuationEvidenceId"]
                )
            )
        raise ContinuationValidationError("continuation request fields are not closed")


def continuation_policy_document() -> dict[str, object]:
    scenario_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "schema": CONTINUATION_ATTEMPT_SCHEMA,
                "scenarioId": PHYSICAL_SCENARIO_ID,
                "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
                "projectOrigin": "keil",
                "executionSource": "physical",
                "physicalTransport": PHYSICAL_TRANSPORT,
                "physicalTransportEvidence": True,
                "stages": list(CONTINUATION_STAGES),
            }
        )
    ).hexdigest()
    return {
        "schema": CONTINUATION_POLICY_SCHEMA,
        "attemptSchema": CONTINUATION_ATTEMPT_SCHEMA,
        "scenarioDigest": scenario_digest,
        "completionWindowSeconds": CONTINUATION_WINDOW_SECONDS,
        "intrusiveActions": {},
    }


CONTINUATION_SCENARIO_DIGEST = cast(str, continuation_policy_document()["scenarioDigest"])
CONTINUATION_POLICY_DIGEST = _hash_payload(continuation_policy_document())


def _attempt_payload(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("checkpointId", None)
    return payload


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


@dataclass(frozen=True)
class PhysicalContinuationAttempt:
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
        if self.schema != CONTINUATION_ATTEMPT_SCHEMA:
            raise ContinuationValidationError("attempt schema is unsupported")
        _uuid("attemptId", self.attempt_id)
        if type(self.revision) is not int or self.revision not in (0, 1):
            raise ContinuationValidationError("attempt revision is invalid")
        if self.revision == 0 and self.previous_checkpoint_id is not None:
            raise ContinuationValidationError("rev0 cannot have a predecessor")
        if self.revision == 1 and self.previous_checkpoint_id is None:
            raise ContinuationValidationError("rev1 needs a predecessor")
        if self.previous_checkpoint_id is not None:
            _hash("previousCheckpointId", self.previous_checkpoint_id)
        if self.scenario_id != PHYSICAL_SCENARIO_ID or self.scenario_version != PHYSICAL_SCENARIO_VERSION:
            raise ContinuationValidationError("scenario identity is not frozen")
        if self.scenario_digest != CONTINUATION_SCENARIO_DIGEST or self.recovery_policy_digest != CONTINUATION_POLICY_DIGEST:
            raise ContinuationValidationError("continuation policy identity is not frozen")
        _hash("scenarioDigest", self.scenario_digest)
        _hash("recoveryPolicyDigest", self.recovery_policy_digest)
        _hash("workspaceId", self.workspace_id)
        _uuid("logicalProjectId", self.logical_project_id)
        _text("sessionId", self.session_id)
        if self.project_origin != "keil" or self.execution_source != "physical" or self.physical_transport_evidence is not True:
            raise ContinuationValidationError("physical continuation provenance is invalid")
        if self.revision == 0:
            if self.status != "IN_PROGRESS" or self.stage != CONTINUATION_STAGES[0] or self.fix_verification_id is not None:
                raise ContinuationValidationError("rev0 state is invalid")
        else:
            if self.status != "COMPLETED" or self.stage != CONTINUATION_STAGES[1] or self.fix_verification_id is None:
                raise ContinuationValidationError("rev1 state is invalid")
            _hash("fixVerificationId", self.fix_verification_id)
        _hash("continuationEvidenceId", self.continuation_evidence_id)
        _run_id("fixedAfterTestRunId", self.fixed_after_test_run_id)
        _hash("fixedAfterEvidenceId", self.fixed_after_evidence_id)
        opened = _utc("openedAtUtc", self.opened_at_utc)
        updated = _utc("updatedAtUtc", self.updated_at_utc)
        deadline = _utc("deadlineAtUtc", self.deadline_at_utc)
        if _time(updated) < _time(opened) or deadline != (
            (_time(opened) + timedelta(seconds=CONTINUATION_WINDOW_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ):
            raise ContinuationValidationError("attempt time window is invalid")
        if self.revision == 0 and updated != opened:
            raise ContinuationValidationError("rev0 opened and updated times differ")
        if self.revision == 1 and self.previous_checkpoint_id is None:
            raise ContinuationValidationError("rev1 predecessor is absent")
        if _time(updated) > _time(deadline):
            raise ContinuationValidationError("attempt update follows its deadline")
        if _hash_payload(_attempt_payload(self.to_dict())) != self.checkpoint_id:
            raise ContinuationValidationError("checkpointId does not match the snapshot")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema, "attemptId": self.attempt_id, "revision": self.revision,
            "checkpointId": self.checkpoint_id, "previousCheckpointId": self.previous_checkpoint_id,
            "scenarioId": self.scenario_id, "scenarioVersion": self.scenario_version,
            "scenarioDigest": self.scenario_digest, "recoveryPolicyDigest": self.recovery_policy_digest,
            "workspaceId": self.workspace_id, "logicalProjectId": self.logical_project_id,
            "sessionId": self.session_id, "projectOrigin": self.project_origin,
            "executionSource": self.execution_source,
            "physicalTransportEvidence": self.physical_transport_evidence,
            "status": self.status, "stage": self.stage,
            "continuationEvidenceId": self.continuation_evidence_id,
            "fixedAfterTestRunId": self.fixed_after_test_run_id,
            "fixedAfterEvidenceId": self.fixed_after_evidence_id,
            "fixVerificationId": self.fix_verification_id,
            "openedAtUtc": self.opened_at_utc, "updatedAtUtc": self.updated_at_utc,
            "deadlineAtUtc": self.deadline_at_utc,
        }

    @classmethod
    def from_value(cls, value: object) -> "PhysicalContinuationAttempt":
        data = _mapping(value, _ATTEMPT_FIELDS)
        return cls(
            schema=_text("schema", data["schema"]), attempt_id=_uuid("attemptId", data["attemptId"]),
            revision=data["revision"], checkpoint_id=_hash("checkpointId", data["checkpointId"]),  # type: ignore[arg-type]
            previous_checkpoint_id=None if data["previousCheckpointId"] is None else _hash("previousCheckpointId", data["previousCheckpointId"]),
            scenario_id=_text("scenarioId", data["scenarioId"]), scenario_version=_text("scenarioVersion", data["scenarioVersion"]),
            scenario_digest=_hash("scenarioDigest", data["scenarioDigest"]), recovery_policy_digest=_hash("recoveryPolicyDigest", data["recoveryPolicyDigest"]),
            workspace_id=_hash("workspaceId", data["workspaceId"]), logical_project_id=_uuid("logicalProjectId", data["logicalProjectId"]),
            session_id=_text("sessionId", data["sessionId"]), project_origin=_text("projectOrigin", data["projectOrigin"]),
            execution_source=_text("executionSource", data["executionSource"]), physical_transport_evidence=data["physicalTransportEvidence"],  # type: ignore[arg-type]
            status=_text("status", data["status"]), stage=_text("stage", data["stage"]),
            continuation_evidence_id=_hash("continuationEvidenceId", data["continuationEvidenceId"]),
            fixed_after_test_run_id=_run_id("fixedAfterTestRunId", data["fixedAfterTestRunId"]),
            fixed_after_evidence_id=_hash("fixedAfterEvidenceId", data["fixedAfterEvidenceId"]),
            fix_verification_id=None if data["fixVerificationId"] is None else _hash("fixVerificationId", data["fixVerificationId"]),
            opened_at_utc=_utc("openedAtUtc", data["openedAtUtc"]), updated_at_utc=_utc("updatedAtUtc", data["updatedAtUtc"]),
            deadline_at_utc=_utc("deadlineAtUtc", data["deadlineAtUtc"]),
        )


@dataclass(frozen=True)
class DiagnosticPrefix:
    session: DiagnosticSession
    events: tuple[DiagnosticEvent, ...]
    checkpoint_envelope: EvidenceEnvelope
    declaration: SourceChangeDeclaration


@dataclass(frozen=True)
class AuthenticatedContinuation:
    proof: PhysicalContinuationProof
    envelope: EvidenceEnvelope
    root: RootRecord
    predecessor: PhysicalAcceptanceAttempt
    predecessor_envelope: EvidenceEnvelope
    before: PublishedTestRun
    after: PublishedTestRun
    diagnostic: DiagnosticPrefix

    @property
    def continuation_evidence_id(self) -> str:
        return str(self.envelope.evidence_id)


def _typed_root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    name = hashlib.sha256(canonical_json_bytes({"root_type": root_type, "root_id": root_id})).hexdigest() + ".json"
    return evidence.root / "roots" / root_type / name


def _load_v2_attempt(
    evidence: EvidenceStore,
    attempt_id: str,
    *,
    workspace_id: str,
    project_id: str,
    revision: int,
) -> tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]:
    root_id = f"{attempt_id}.{revision:08d}"
    try:
        root = get_root(evidence, "acceptance-attempt", root_id)
        envelope = evidence.get_envelope(root.manifest_id)
        raw = envelope.metadata["attempt"]
        attempt = PhysicalAcceptanceAttempt.from_value(json.loads(canonical_json_bytes(raw).decode("utf-8")))
    except (EvidenceValidationError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError, AcceptanceRecoveryValidationError) as error:
        raise ContinuationValidationError("predecessor attempt evidence is corrupt") from error
    if (
        root.root_type != "acceptance-attempt" or root.root_id != root_id
        or set(root.metadata) != {"attempt_sha256", "revision", "workspace_id", "logical_project_id"}
        or envelope.operation != "acceptance-attempt"
        or set(envelope.metadata) != {"attempt", "attempt_sha256"}
        or root.manifest_id != str(envelope.evidence_id)
        or root.metadata.get("revision") != revision
        or root.metadata.get("workspace_id") != workspace_id
        or root.metadata.get("logical_project_id") != project_id
        or envelope.identity.workspace_id != workspace_id
        or envelope.identity.project_id != project_id
        or attempt.attempt_id != attempt_id
        or attempt.revision != revision
        or attempt.checkpoint_id != root.metadata.get("attempt_sha256")
        or attempt.checkpoint_id != envelope.metadata.get("attempt_sha256")
        or canonical_json_bytes(envelope.metadata["attempt"]) != canonical_json_bytes(attempt.to_dict())
    ):
        raise ContinuationValidationError("predecessor attempt evidence is incompatible")
    return attempt, envelope


def _load_v2_chain_prefix(
    evidence: EvidenceStore,
    attempt_id: str,
    *,
    workspace_id: str,
    project_id: str,
    last_revision: int,
) -> tuple[list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]], PhysicalAcceptanceAttempt, EvidenceEnvelope]:
    if last_revision != 6:
        raise ContinuationValidationError("continuation predecessor must be v2 revision six")
    chain: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]] = []
    for revision in range(last_revision + 1):
        item = _load_v2_attempt(evidence, attempt_id, workspace_id=workspace_id, project_id=project_id, revision=revision)
        attempt, envelope = item
        if envelope.parents != (() if revision == 0 else (chain[-1][1].evidence_id,)):
            raise ContinuationValidationError("predecessor attempt chain is corrupt")
        if attempt.previous_checkpoint_id != (None if revision == 0 else chain[-1][0].checkpoint_id):
            raise ContinuationValidationError("predecessor attempt chain is corrupt")
        if envelope.artifacts != () or envelope.produced_at_utc != attempt.updated_at_utc:
            raise ContinuationValidationError("predecessor attempt envelope is corrupt")
        first = attempt if not chain else chain[0][0]
        immutable = ("attempt_id", "scenario_id", "scenario_version", "scenario_digest",
                     "recovery_policy_digest", "workspace_id", "logical_project_id",
                     "project_origin", "execution_source", "opened_at_utc")
        if any(getattr(attempt, key) != getattr(first, key) for key in immutable):
            raise ContinuationValidationError("predecessor immutable fields changed")
        if chain:
            previous = chain[-1][0]
            if not (_time(previous.updated_at_utc) <= _time(attempt.updated_at_utc) <= _time(previous.deadline_at_utc)):
                raise ContinuationValidationError("predecessor transition was outside its deadline")
            if any(value is not None and attempt.stage_outputs.get(key) != value
                   for key, value in previous.stage_outputs.items()):
                raise ContinuationValidationError("predecessor outputs changed")
            if (previous.source_change_intent is not None and previous.source_change_intent != attempt.source_change_intent
                or previous.source_change_authorization is not None and previous.source_change_authorization != attempt.source_change_authorization):
                raise ContinuationValidationError("predecessor source authority changed")
            if envelope.identity.session_id != chain[0][1].identity.session_id:
                raise ContinuationValidationError("predecessor session changed")
        stage = PHYSICAL_STAGES[revision if revision <= 4 else revision - 1]
        expected_deadline = (_time(attempt.updated_at_utc) + timedelta(
            seconds=physical_acceptance_recovery_policy().stage_timeout_seconds[stage]
        )).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if attempt.deadline_at_utc != expected_deadline or revision == 0 and attempt.opened_at_utc != attempt.updated_at_utc:
            raise ContinuationValidationError("predecessor policy deadline differs")
        chain.append(item)
    predecessor = chain[-1][0]
    if (
        predecessor.schema != PHYSICAL_ATTEMPT_SCHEMA or predecessor.status != "ACTIVE"
        or predecessor.stage_outputs.get("sourceChangeDeclarationId") is None
        or predecessor.stage_outputs.get("fixedAfterTestRunId") is not None
        or predecessor.source_change_authorization is None
        or predecessor.source_change_intent is None
    ):
        raise ContinuationValidationError("predecessor is not the authorized v2 after-build state")
    return chain, chain[-1][0], chain[-1][1]


def _load_diagnostic_prefix(
    evidence: EvidenceStore,
    diagnostics_root: Path,
    *,
    session_id: str,
    revision: int,
    event_head: str,
    evidence_id: str,
) -> DiagnosticPrefix:
    """Read only rooted immutable events, never the mutable Diagnostic loader.

    A proof pins the prefix before verification. Later events may refer back
    to the proof without being traversed by this reader.
    """
    from stm32_toolkit.diagnostics.model import MAX_EVENTS, MAX_EVENT_BYTES

    _diagnostic_id("diagnosticSessionId", session_id)
    if type(revision) is not int or not 1 <= revision <= MAX_EVENTS:
        raise ContinuationValidationError("diagnostic revision is invalid")
    session = None
    events = []
    operations = set()
    previous_envelope = None
    for sequence in range(revision):
        root = get_root(evidence, "diagnostic-session", f"{session_id}.{sequence + 1:08d}")
        envelope = evidence.get_envelope(root.manifest_id)
        if (envelope.operation != "diagnostic-event" or len(envelope.artifacts) != 1
            or envelope.artifacts[0].kind != "diagnostic-event"
            or envelope.artifacts[0].media_type != "application/json"):
            raise ContinuationValidationError("Diagnostic event envelope differs")
        raw = evidence.read_artifact(envelope.artifacts[0], maximum_bytes=MAX_EVENT_BYTES)
        event = DiagnosticEvent.from_value(json.loads(raw.decode("utf-8")))
        if (raw != canonical_diagnostic_json_bytes(event.to_dict())
            or event.sequence != sequence or event.diagnostic_session_id != session_id
            or event.operation_id in operations
            or event.event_type in {"verification.plan_added", "verification.started",
                "analysis.marker_attached", "verification.completed"}):
            raise ContinuationValidationError("Diagnostic prefix is not a pre-verification chain")
        operations.add(event.operation_id)
        session = reduce_event(session, event)
        refs = diagnostic_event_references(event)
        parents = (() if previous_envelope is None else (str(previous_envelope.evidence_id),))
        parents = tuple(dict.fromkeys((*parents, *refs)))
        if (envelope.identity != session.identity or envelope.produced_at_utc != event.occurred_at_utc
            or envelope.parents != parents
            or dict(envelope.metadata) != {"diagnostic_session_id": session_id,
                "sequence": sequence, "revision": session.revision, "event_digest": event.digest}
            or dict(root.metadata) != {"diagnostic_session_id": session_id,
                "revision": session.revision, "state": session.state, "event_digest": event.digest}):
            raise ContinuationValidationError("Diagnostic checkpoint graph differs")
        for reference in refs:
            parent = evidence.get_envelope(reference)
            if event.event_type == "source_change.declared":
                declaration = session.source_change_declarations[-1]
                if (parent.identity.workspace_id != session.identity.workspace_id
                    or parent.identity.project_id != session.identity.project_id
                    or parent.identity.session_id != session.identity.session_id
                    or parent.identity.target_device != session.identity.target_device
                    or declaration.diff_artifact not in parent.artifacts):
                    raise ContinuationValidationError("source diff identity differs")
                evidence.read_artifact(declaration.diff_artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES)
            elif parent.identity != session.identity:
                raise ContinuationValidationError("Diagnostic prefix reference identity differs")
        events.append(event)
        previous_envelope = envelope
    if (session is None or session.revision != revision or session.event_head != event_head
        or str(envelope.evidence_id) != evidence_id or session.state != "FIX_PROPOSED"
        or len(session.source_change_declarations) != 1):
        raise ContinuationValidationError("Diagnostic pinned declaration checkpoint differs")
    return DiagnosticPrefix(session, tuple(events), envelope, session.source_change_declarations[0])


def _validate_physical_test_run(loaded, *, run_id, evidence_id, state):
    manifest, envelope = loaded.manifest, loaded.envelope
    metadata = envelope.metadata
    if (manifest.run_id != run_id or str(envelope.evidence_id) != evidence_id
        or manifest.mode != "target" or manifest.transport != PHYSICAL_TRANSPORT
        or manifest.state != state or envelope.operation != "target-test-physical"
        or loaded.root.metadata.get("execution_source") != "physical"
        or loaded.root.metadata.get("physical_transport_evidence") is not True
        or metadata.get("execution_source") != "physical"
        or metadata.get("physical_transport_evidence") is not True
        or metadata.get("target_id") != manifest.identity.target_device):
        raise ContinuationValidationError("physical TestRun does not match proof")
    _hash("probe_id", metadata.get("probe_id"))
    _hash("transport_config_digest", metadata.get("transport_config_digest"))


def _validate_proof_graph(evidence, diagnostics_root, proof):
    predecessor_root = get_root(evidence, "acceptance-attempt", f"{proof.predecessor_attempt_id}.00000006")
    predecessor_envelope = evidence.get_envelope(predecessor_root.manifest_id)
    chain, predecessor, predecessor_envelope = _load_v2_chain_prefix(
        evidence, proof.predecessor_attempt_id,
        workspace_id=predecessor_envelope.identity.workspace_id,
        project_id=predecessor_envelope.identity.project_id, last_revision=6,
    )
    if (predecessor.checkpoint_id != proof.predecessor_checkpoint_id
        or str(predecessor_envelope.evidence_id) != proof.predecessor_evidence_id
        or predecessor.source_change_intent != proof.source_change_intent):
        raise ContinuationValidationError("predecessor does not match proof")
    # The historical source action authorizes the exact rev4 intent. A proof
    # cannot generate a new action or extend that authorization's deadline.
    authorized = chain[4][0]
    action = {
        "schema": PHYSICAL_ATTEMPT_SCHEMA, "action": "source-change",
        "attemptId": authorized.attempt_id, "revision": authorized.revision,
        "checkpointId": authorized.checkpoint_id, "scenarioId": authorized.scenario_id,
        "scenarioVersion": authorized.scenario_version, "scenarioDigest": authorized.scenario_digest,
        "recoveryPolicyDigest": authorized.recovery_policy_digest,
        "workspaceId": authorized.workspace_id, "logicalProjectId": authorized.logical_project_id,
        **{key: authorized.stage_outputs[key] for key in ("failedBeforeTestRunId", "failedBeforeEvidenceId",
            "diagnosticSessionId", "diagnosticRevision", "diagnosticEventHead")},
        "intentDigest": authorized.source_change_intent.intent_digest,
    }
    authorization = predecessor.source_change_authorization
    if (authorization["actionDigest"] != _hash_payload(action)
        or not (_time(authorized.updated_at_utc) <= _time(authorization["authorizedAtUtc"]) <= _time(authorized.deadline_at_utc))):
        raise ContinuationValidationError("historical source authorization differs")
    repository = TestRunRepository(evidence)
    before = repository.load(proof.failed_before_test_run_id)
    after = repository.load(proof.fixed_after_test_run_id)
    _validate_physical_test_run(before, run_id=proof.failed_before_test_run_id,
        evidence_id=proof.failed_before_evidence_id, state="failed")
    _validate_physical_test_run(after, run_id=proof.fixed_after_test_run_id,
        evidence_id=proof.fixed_after_evidence_id, state="passed")
    left, right = before.manifest.identity, after.manifest.identity
    if (any(getattr(left, key) != getattr(right, key) for key in ("workspace_id", "project_id", "target_device"))
        or left.session_id == right.session_id
        or left.session_id != predecessor_envelope.identity.session_id
        or left.workspace_id != predecessor.workspace_id or left.project_id != predecessor.logical_project_id
        or any(before.envelope.metadata[key] != after.envelope.metadata[key]
               for key in ("probe_id", "target_id", "transport_config_digest"))):
        raise ContinuationValidationError("physical pair scope or probe/mailbox identity differs")
    diagnostic = _load_diagnostic_prefix(evidence, diagnostics_root,
        session_id=proof.diagnostic_session_id, revision=proof.diagnostic_revision,
        event_head=proof.diagnostic_event_head, evidence_id=proof.diagnostic_evidence_id)
    declaration, session = diagnostic.declaration, diagnostic.session
    outputs = predecessor.stage_outputs
    auth_revision = authorization["diagnosticRevision"]
    if (not 1 <= auth_revision <= len(diagnostic.events)
        or diagnostic.events[auth_revision - 1].digest != authorization["diagnosticEventHead"]
        or proof.diagnostic_revision <= auth_revision
        or declaration.declaration_id != proof.source_change_declaration_id
        or declaration.declaration_id != outputs["sourceChangeDeclarationId"]
        or proof.diagnostic_session_id != outputs["diagnosticSessionId"]
        or session.identity != left or session.failed_test_run_id != proof.failed_before_test_run_id
        or session.failed_evidence_id != proof.failed_before_evidence_id
        or outputs["failedBeforeTestRunId"] != proof.failed_before_test_run_id
        or outputs["failedBeforeEvidenceId"] != proof.failed_before_evidence_id):
        raise ContinuationValidationError("Diagnostic declaration does not descend from source authorization")
    for prefix, identity in (("before", left), ("after", right)):
        for suffix, identity_field, declaration_field in (
            ("BuildId", "build_id", "build_id"), ("ElfSha256", "elf_sha256", "elf_sha256"),
            ("InputSnapshotSha256", "input_snapshot_sha256", "source_sha256")):
            if (outputs[prefix + suffix] != getattr(identity, identity_field)
                or getattr(declaration, prefix + "_" + declaration_field) != getattr(identity, identity_field)):
                raise ContinuationValidationError("TestRun firmware lineage differs from declared source intent")
    intent = proof.source_change_intent
    if (declaration.before_source_sha256 != intent.before_input_snapshot_sha256
        or declaration.after_source_sha256 != intent.expected_after_input_snapshot_sha256
        or tuple(declaration.changed_paths) != tuple(item["path"] for item in intent.changes)):
        raise ContinuationValidationError("declared paths or snapshot differ from intent")
    return predecessor, predecessor_envelope, before, after, diagnostic


def proof_parents(proof, declaration):
    parents = (proof.predecessor_evidence_id, proof.diagnostic_evidence_id,
        proof.failed_before_evidence_id, proof.fixed_after_evidence_id, declaration.diff_evidence_id)
    if len(set(parents)) != 5:
        raise ContinuationValidationError("continuation parents must be distinct")
    return parents


def authenticate_continuation(evidence_store, diagnostics_root, continuation_evidence_id, *,
    expected_workspace_id=None, expected_project_id=None, expected_session_id=None,
    expected_diagnostic_session_id=None, expected_fixed_after_test_run_id=None,
    expected_fixed_after_evidence_id=None, expected_diagnostic_revision=None,
    expected_diagnostic_event_head=None):
    """Authenticate the rooted proof and its pinned, acyclic immutable graph."""
    _hash("continuationEvidenceId", continuation_evidence_id)
    try:
        envelope = evidence_store.get_envelope(continuation_evidence_id)
        if (envelope.operation != CONTINUATION_OPERATION or len(envelope.artifacts) != 1
            or envelope.artifacts[0].kind != CONTINUATION_ROOT_TYPE
            or envelope.artifacts[0].media_type != "application/json"):
            raise ContinuationValidationError("continuation envelope differs")
        payload = evidence_store.read_artifact(envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES)
        proof = PhysicalContinuationProof.from_value(json.loads(payload.decode("utf-8")))
        if canonical_json_bytes(proof.to_dict()) != payload:
            raise ContinuationValidationError("continuation bytes are not canonical")
        root = get_root(evidence_store, CONTINUATION_ROOT_TYPE, proof.continuation_id)
        predecessor, predecessor_envelope, before, after, diagnostic = _validate_proof_graph(evidence_store, diagnostics_root, proof)
        if (root.manifest_id != str(envelope.evidence_id)
            or envelope.identity != before.manifest.identity
            or dict(root.metadata) != {"continuation_id": proof.continuation_id}
            or dict(envelope.metadata) != dict(root.metadata)
            or envelope.parents != proof_parents(proof, diagnostic.declaration)):
            raise ContinuationValidationError("continuation root, identity or parents differ")
        for expected, actual in (
            (expected_workspace_id, envelope.identity.workspace_id),
            (expected_project_id, envelope.identity.project_id),
            (expected_session_id, envelope.identity.session_id),
            (expected_diagnostic_session_id, proof.diagnostic_session_id),
            (expected_fixed_after_test_run_id, proof.fixed_after_test_run_id),
            (expected_fixed_after_evidence_id, proof.fixed_after_evidence_id),
            (expected_diagnostic_revision, proof.diagnostic_revision),
            (expected_diagnostic_event_head, proof.diagnostic_event_head)):
            if expected is not None and expected != actual:
                raise ContinuationValidationError("continuation does not match consumer context")
        return AuthenticatedContinuation(proof, envelope, root, predecessor, predecessor_envelope, before, after, diagnostic)
    except ContinuationValidationError:
        raise
    except (EvidenceValidationError, DiagnosticValidationError, AcceptanceRecoveryValidationError,
            OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        raise ContinuationValidationError("continuation evidence graph is corrupt") from error


def prepare_continuation(evidence_store, diagnostics_root, request, *, workspace_id, project_id, expected_session_id=None):
    """Validate bind inputs; publication additionally holds the mutable-head locks."""
    if type(request) is not ContinuationRequest or request.kind != "bind":
        raise ContinuationValidationError("a bind request is required")
    _chain, predecessor, predecessor_envelope = _load_v2_chain_prefix(evidence_store,
        request.predecessor_attempt_id, workspace_id=workspace_id, project_id=project_id, last_revision=6)
    diagnostic_id = predecessor.stage_outputs["diagnosticSessionId"]
    diagnostic_root = get_root(evidence_store, "diagnostic-session", f"{diagnostic_id}.{request.diagnostic_revision:08d}")
    diagnostic = _load_diagnostic_prefix(evidence_store, diagnostics_root, session_id=diagnostic_id,
        revision=request.diagnostic_revision, event_head=request.diagnostic_event_head,
        evidence_id=diagnostic_root.manifest_id)
    proof = PhysicalContinuationProof(CONTINUATION_SCHEMA, request.predecessor_attempt_id,
        request.predecessor_checkpoint_id, request.predecessor_evidence_id, diagnostic_id,
        request.diagnostic_revision, request.diagnostic_event_head, diagnostic_root.manifest_id,
        diagnostic.declaration.declaration_id, predecessor.source_change_intent,
        predecessor.stage_outputs["failedBeforeTestRunId"], predecessor.stage_outputs["failedBeforeEvidenceId"],
        request.fixed_after_test_run_id, request.fixed_after_evidence_id)
    values = _validate_proof_graph(evidence_store, diagnostics_root, proof)
    if expected_session_id is not None and values[2].manifest.identity.session_id != expected_session_id:
        raise ContinuationValidationError("continuation caller session differs")
    return (proof, *values)


authenticated_proof_for_plan = authenticate_continuation


def authenticate_plan_continuation(evidence, diagnostics_root, plan, session):
    """Bind a v2 plan to this Diagnostic and the exact immutable TestRun pair."""
    association = authenticate_continuation(evidence, diagnostics_root, plan.continuation_evidence_id,
        expected_workspace_id=session.identity.workspace_id,
        expected_project_id=session.identity.project_id, expected_session_id=session.identity.session_id,
        expected_diagnostic_session_id=session.diagnostic_session_id,
        expected_fixed_after_test_run_id=plan.fixed_after_run_id,
        expected_fixed_after_evidence_id=plan.fixed_after_evidence_id)
    proof = association.proof
    if (session.revision < proof.diagnostic_revision
        or session.identity != association.before.manifest.identity
        or plan.diagnostic_session_id != proof.diagnostic_session_id
        or plan.failed_before_run_id != proof.failed_before_test_run_id
        or plan.failed_before_evidence_id != proof.failed_before_evidence_id
        or plan.source_change_declaration_id != proof.source_change_declaration_id
        or plan.verification_plan_id != association.diagnostic.declaration.validation_plan_id
        or association.diagnostic.declaration not in session.source_change_declarations):
        raise ContinuationValidationError("verification plan differs from continuation")
    return association


def validate_continuation_reference(evidence, association, envelope):
    """Check v2 event references without invoking Diagnostic event replay."""
    if envelope.identity != association.after.manifest.identity:
        raise ContinuationValidationError("continuation reference after identity differs")
    if envelope.operation == "target-test-physical":
        if envelope != association.after.envelope:
            raise ContinuationValidationError("continuation reference names another TestRun")
        return
    if envelope.operation == "diagnostic-marker":
        if len(envelope.parents) != 1:
            raise ContinuationValidationError("continuation marker parent differs")
        analysis = evidence.get_envelope(envelope.parents[0])
        if analysis.operation != "monitor-analysis":
            raise ContinuationValidationError("continuation marker must reference an analysis")
        validate_continuation_reference(evidence, association, analysis)
        return
    if (envelope.operation != "monitor-analysis" or len(envelope.artifacts) != 1
        or len(envelope.parents) != 4
        or envelope.parents[2:] != (association.diagnostic.declaration.diff_evidence_id,
                                    association.continuation_evidence_id)
        or envelope.metadata.get("continuation_evidence_id") != association.continuation_evidence_id):
        raise ContinuationValidationError("continuation analysis parents differ")
    raw = evidence.read_artifact(envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES)
    payload = json.loads(raw.decode("utf-8"))
    if (not isinstance(payload, dict) or canonical_json_bytes(payload) != raw
        or payload.get("schema") != CONTINUATION_ANALYSIS_SCHEMA):
        raise ContinuationValidationError("continuation analysis payload differs")
    unsigned = {key: value for key, value in payload.items() if key != "analysis_id"}
    if payload.get("analysis_id") != _hash_payload(unsigned):
        raise ContinuationValidationError("continuation analysis digest differs")
    lineage = payload.get("identity")
    if (not isinstance(lineage, dict) or lineage.get("schema") != CONTINUATION_LINEAGE_SCHEMA
        or lineage.get("continuation_evidence_id") != association.continuation_evidence_id
        or lineage.get("before_session_id") != association.before.manifest.identity.session_id
        or lineage.get("after_session_id") != association.after.manifest.identity.session_id):
        raise ContinuationValidationError("continuation analysis lineage differs")
    for parent_id, loaded in zip(envelope.parents[:2], (association.before, association.after)):
        parent = evidence.get_envelope(parent_id)
        if parent.operation != "monitor-physical-window" or parent.identity != loaded.manifest.identity:
            raise ContinuationValidationError("continuation transcript identity differs")
