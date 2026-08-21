"""Application workflows for the VS-02 failed-run diagnostic boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import re
import secrets
from typing import Callable, Literal, cast
from uuid import UUID

from stm32_toolkit.diagnostics import (
    ACTORS,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DIAGNOSTIC_REVISION_CONFLICT,
    DiagnosticSession,
    DiagnosticMarkerRef,
    DiagnosticStore,
    DiagnosticValidationError,
    EvidenceAssessment,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    SourceChangeDeclaration,
    VerificationPlan,
    calculate_plan_digest,
    create_event,
)
from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceValidationError,
    get_root,
)
from stm32_toolkit.evidence.store import MAX_EVIDENCE_READ_BYTES
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.monitor_replay_contract import (
    MONITOR_REPLAY_EXECUTION_SOURCE,
    MONITOR_REPLAY_SCHEMA,
    MONITOR_REPLAY_SOURCE,
    MONITOR_RUN_REF_SCHEMA,
    ReplayContractError,
    canonical_replay_json_bytes as _shared_canonical_replay_json_bytes,
    decode_canonical_json_bytes,
    validate_replay_document,
    validate_run_reference,
)
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import TestProtocolError
from stm32_toolkit.testing.publication import TestRunRepository


_START_OPERATION = "diagnostic.start"
_SHOW_OPERATION = "diagnostic.show"
_BEGIN_OPERATION = "diagnostic.begin"
_HYPOTHESIS_ADD_OPERATION = "diagnostic.hypothesis.add"
_HYPOTHESIS_ASSESS_OPERATION = "diagnostic.hypothesis.assess"
_PLAN_ADD_OPERATION = "diagnostic.plan.add"
_PLAN_RUN_OPERATION = "diagnostic.plan.run"
_SOURCE_CHANGE_DECLARE_OPERATION = "diagnostic.source-change.declare"
_VERIFICATION_PLAN_ADD_OPERATION = "diagnostic.verification-plan.add"
_VERIFICATION_START_OPERATION = "diagnostic.verification.start"
_MARKER_ATTACH_OPERATION = "diagnostic.marker.attach"
_OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DIAGNOSTIC_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_PLAN_ID = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_INCOMPATIBLE_IDENTITY = "INCOMPATIBLE_IDENTITY"
_ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
_EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"

_TARGET_REPLAY_OPERATION = "target-test-replay"
_ANALYSIS_OPERATION = "monitor-analysis"
_MARKER_OPERATION = "diagnostic-marker"
_ANALYSIS_ROOT = "monitor-analysis"
_MARKER_ROOT = "diagnostic-marker"
_ANALYSIS_SCHEMA = "stm32-monitor-analysis/1"
_ANALYSIS_LINEAGE_SCHEMA = "stm32-monitor-analysis-lineage/1"
_MARKER_SCHEMA = "stm32-diagnostic-marker/1"
_ANALYSIS_FIELDS = frozenset(
    {
        "schema", "analysis_id", "request_digest", "before_run_id", "after_run_id", "identity",
        "quality", "conclusion", "reason_code", "aligned_position_count", "aligned_pair_count",
        "excluded_position_count", "before_first", "before_last", "before_min", "before_max",
        "after_first", "after_last", "after_min", "after_max", "delta_first", "delta_last", "changed",
    }
)
_ANALYSIS_IDENTITY_FIELDS = frozenset(
    {
        "schema", "origin_workspace_id", "import_workspace_id", "logical_project_id", "target_device",
        "before_input_snapshot_sha256", "before_build_id", "before_elf_sha256",
        "after_input_snapshot_sha256", "after_build_id", "after_elf_sha256", "source_change_declaration_id",
    }
)
_MARKER_FIELDS = frozenset(
    {
        "schema", "marker_id", "analysis_id", "analysis_evidence_id", "diagnostic_session_id",
        "hypothesis_id", "polarity", "label", "rationale",
    }
)
_MONITOR_REF_METADATA_FIELDS = frozenset(
    {
        "operation_id", "run_ref_sha256", "fixture_sha256", "scenario_role",
        "origin_workspace_id", "import_workspace_id", "execution_source",
        "physical_transport_evidence",
    }
)
def _canonical_replay_json_bytes(value: object) -> bytes:
    try:
        return _shared_canonical_replay_json_bytes(value)
    except ReplayContractError as error:
        raise ValueError(str(error)) from error


def _decode_replay_json(payload: bytes) -> object:
    try:
        return decode_canonical_json_bytes(payload, require_object=False)
    except ReplayContractError as error:
        raise ValueError(str(error)) from error


@dataclass(frozen=True)
class DiagnosticWorkflowContext:
    """Caller context; storage roots are derived from the loaded Project v3 model."""

    project_root: Path
    data_root: Path
    session_id: str


@dataclass(frozen=True)
class _WorkflowState:
    model: object
    workspace: WorkspacePaths
    evidence_store: EvidenceStore
    diagnostic_store: DiagnosticStore
    repository: TestRunRepository


class _WorkflowFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# These are deliberately narrow seams for deterministic application tests.
_load_project_model = load_project_model
_workspace_paths_factory: Callable[..., WorkspacePaths] = WorkspacePaths.from_roots
_evidence_store_factory = EvidenceStore
_diagnostic_store_factory = DiagnosticStore
_repository_factory = TestRunRepository
_session_id_factory = lambda: secrets.token_hex(16)
_hypothesis_id_factory = lambda: secrets.token_hex(16)
_utc_now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_AUTHORITY_MESSAGES = {
    _INCOMPATIBLE_IDENTITY: "Target replay identity is incompatible.",
    _ENVIRONMENT_FAILURE: "Target replay environment failed.",
    _EVIDENCE_INTEGRITY_FAILURE: "Target replay evidence failed integrity validation.",
}


def _failure(operation: str, code: str) -> OperationResult[None]:
    authority_message = _AUTHORITY_MESSAGES.get(code)
    if authority_message is not None:
        return OperationResult.failure(operation, code, authority_message, {})
    error = DiagnosticValidationError(code)
    return OperationResult.failure(operation, error.code, error.message, {})


def _result(operation: str, action: Callable[[], OperationResult[object]]) -> OperationResult[object]:
    try:
        return action()
    except DiagnosticValidationError as error:
        return OperationResult.failure(operation, error.code, error.message, {})
    except _WorkflowFailure as error:
        return _failure(operation, error.code)


def _validate_context(context: DiagnosticWorkflowContext) -> None:
    if not isinstance(context, DiagnosticWorkflowContext):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    if not isinstance(context.project_root, Path) or not isinstance(context.data_root, Path):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    if not isinstance(context.session_id, str):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    try:
        require_safe_session_id(context.session_id)
    except (TypeError, ValueError):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from None


def _validate_operation_id(operation_id: object) -> str:
    if not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return operation_id


def _validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return run_id


def _validate_actor(actor: object) -> str:
    if not isinstance(actor, str) or actor not in ACTORS:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return actor


def _validate_failed_run_mode(value: object) -> Literal["host", "target"]:
    if not isinstance(value, str) or value not in {"host", "target"}:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return cast(Literal["host", "target"], value)


def _validate_session_id(session_id: object) -> str:
    if not isinstance(session_id, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(session_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return session_id


def _validate_revision(expected_revision: object) -> int:
    if type(expected_revision) is not int or expected_revision < 0:
        raise _WorkflowFailure(DIAGNOSTIC_REVISION_CONFLICT)
    return expected_revision


def _validate_plan_id(plan_id: object) -> str:
    if not isinstance(plan_id, str) or _PLAN_ID.fullmatch(plan_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_PLAN_INVALID)
    return plan_id


def _validate_hypothesis_id(hypothesis_id: object) -> str:
    if not isinstance(hypothesis_id, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(hypothesis_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_PLAN_INVALID)
    return hypothesis_id


def _validate_step_id(step_id: object) -> str:
    if not isinstance(step_id, str) or _OPERATION_ID.fullmatch(step_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_PLAN_INVALID)
    return step_id


def _make_state(context: DiagnosticWorkflowContext) -> _WorkflowState:
    _validate_context(context)
    try:
        model = _load_project_model(context.project_root)
        if getattr(model, "schema_version", None) != 3:
            raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
        logical_project_id = getattr(model, "logical_project_id")
        workspace = _workspace_paths_factory(
            context.data_root,
            context.project_root,
            logical_project_id,
            context.session_id,
        )
    except _WorkflowFailure:
        raise
    except ProjectManifestError as error:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from error
    except (OSError, TypeError, ValueError, AttributeError) as error:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from error
    evidence_store = _evidence_store_factory(workspace.workspace_root / "evidence")
    diagnostic_store = _diagnostic_store_factory(workspace.diagnostics_root, evidence_store)
    repository = _repository_factory(evidence_store)
    return _WorkflowState(model, workspace, evidence_store, diagnostic_store, repository)


def _require_identity(state: _WorkflowState, identity: object) -> None:
    if not (
        getattr(identity, "project_id", None) == str(state.model.logical_project_id)
        and getattr(identity, "workspace_id", None) == state.workspace.workspace_id
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_IDENTITY_MISMATCH)


def _has_provider_os_error(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and not isinstance(current, FileNotFoundError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _load_failed_run(
    state: _WorkflowState,
    failed_test_run_id: str,
    *,
    failed_run_mode: Literal["host", "target"],
) -> object:
    target_mode = failed_run_mode == "target"
    try:
        return state.repository.load(failed_test_run_id)
    except FileNotFoundError as error:
        code = _EVIDENCE_INTEGRITY_FAILURE if target_mode else DIAGNOSTIC_EVIDENCE_MISSING
        raise _WorkflowFailure(code) from error
    except OSError as error:
        code = _ENVIRONMENT_FAILURE if target_mode else DIAGNOSTIC_EVIDENCE_MISSING
        raise _WorkflowFailure(code) from error
    except (
        EvidenceValidationError,
        TestProtocolError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
    ) as error:
        if target_mode and _has_provider_os_error(error):
            raise _WorkflowFailure(_ENVIRONMENT_FAILURE) from error
        code = _EVIDENCE_INTEGRITY_FAILURE if target_mode else DIAGNOSTIC_EVIDENCE_MISSING
        raise _WorkflowFailure(code) from error


def _validate_target_authority(
    state: _WorkflowState,
    published: object,
    failed_test_run_id: str,
    *,
    expected_identity: object | None,
) -> object:
    manifest = getattr(published, "manifest", None)
    envelope = getattr(published, "envelope", None)
    root = getattr(published, "root", None)
    identity = getattr(manifest, "identity", None)
    if identity is None:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if (
        expected_identity is not None and identity != expected_identity
    ) or identity.project_id != str(state.model.logical_project_id):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    if (
        getattr(manifest, "run_id", None) != failed_test_run_id
        or getattr(manifest, "mode", None) != "target"
        or getattr(manifest, "state", None) != "failed"
        or getattr(manifest, "transport", None) != "replay"
        or getattr(envelope, "identity", None) != identity
        or getattr(envelope, "operation", None) != "target-test-replay"
        or getattr(root, "manifest_id", None) != getattr(envelope, "evidence_id", None)
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    expected_root_metadata = {
        "mode": "target",
        "state": "failed",
        "execution_source": "replay",
        "physical_transport_evidence": False,
        "origin_workspace_id": identity.workspace_id,
        "import_workspace_id": state.workspace.workspace_id,
    }
    if getattr(root, "metadata", None) != expected_root_metadata:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    return manifest


def _load_authoritative_run(
    state: _WorkflowState,
    failed_test_run_id: str,
    *,
    failed_run_mode: Literal["host", "target"],
    expected_identity: object | None = None,
) -> object:
    published = _load_failed_run(
        state,
        failed_test_run_id,
        failed_run_mode=failed_run_mode,
    )
    manifest = getattr(published, "manifest", None)
    if failed_run_mode == "target":
        if getattr(manifest, "mode", None) != "target":
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        _validate_target_authority(
            state,
            published,
            failed_test_run_id,
            expected_identity=expected_identity,
        )
        return published
    if getattr(manifest, "mode", None) != "host" or getattr(manifest, "state", None) != "failed":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    if expected_identity is None:
        _require_identity(state, getattr(manifest, "identity", None))
    else:
        _require_identity(state, expected_identity)
        if (
            getattr(manifest, "identity", None) != expected_identity
            or getattr(getattr(published, "envelope", None), "identity", None) != expected_identity
        ):
            raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    return published


def _session_data(session: DiagnosticSession, *, authoritative: bool = False) -> dict[str, object]:
    data: dict[str, object] = {"session": session.to_dict()}
    if authoritative:
        data["authoritative"] = True
    return data


def _diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    failed_test_run_id: object,
    failed_run_mode: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    failed_test_run_id = _validate_run_id(failed_test_run_id)
    failed_run_mode = _validate_failed_run_mode(failed_run_mode)
    actor = _validate_actor(actor)
    state = _make_state(context)
    published = _load_authoritative_run(
        state,
        failed_test_run_id,
        failed_run_mode=failed_run_mode,
    )
    manifest = getattr(published, "manifest")
    identity = getattr(manifest, "identity")
    envelope = getattr(published, "envelope")
    request: dict[str, object] = {"failed_test_run_id": failed_test_run_id}
    if failed_run_mode == "target":
        request["failed_run_mode"] = "target"
    event = create_event(
        diagnostic_session_id=_new_session_id(),
        operation_id=operation_id,
        sequence=0,
        revision_before=0,
        event_type="session.created",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=None,
        payload={
            "request": request,
            "result": {
                "failed_evidence_id": str(envelope.evidence_id),
                "identity": identity.to_dict(),
            },
        },
    )
    accepted = state.diagnostic_store.create(event)
    return OperationResult.success(_START_OPERATION, {"session": accepted.session.to_dict()})


def _new_session_id() -> str:
    value = _session_id_factory()
    if not isinstance(value, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(value) is None:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    return value


def _new_hypothesis_id() -> str:
    value = _hypothesis_id_factory()
    if not isinstance(value, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(value) is None:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    return value


def _new_timestamp() -> str:
    value = _utc_now()
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    return value


def _stored_session_is_target(state: _WorkflowState, diagnostic_session_id: str) -> bool:
    event_path = (
        state.workspace.diagnostics_root
        / "sessions"
        / diagnostic_session_id
        / "events"
        / "00000000.json"
    )
    try:
        document = json.loads(event_path.read_bytes().decode("utf-8"))
        payload = document.get("payload")
        request = payload.get("request") if isinstance(payload, dict) else None
        return isinstance(request, dict) and request.get("failed_run_mode") == "target"
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return False


def _load_bound_session(
    state: _WorkflowState,
    diagnostic_session_id: str,
    *,
    target_projection: bool = False,
) -> DiagnosticSession:
    try:
        session = state.diagnostic_store.load(diagnostic_session_id)
    except DiagnosticValidationError as error:
        if target_projection and _stored_session_is_target(state, diagnostic_session_id):
            if error.code == DIAGNOSTIC_EVIDENCE_MISSING:
                raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
            if error.code == DIAGNOSTIC_IDENTITY_MISMATCH:
                raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY) from error
        raise
    _load_authoritative_run(
        state,
        session.failed_test_run_id,
        failed_run_mode=session.failed_run_mode,
        expected_identity=session.identity,
    )
    return session


def _diagnostic_show(
    context: DiagnosticWorkflowContext,
    *,
    diagnostic_session_id: object,
) -> OperationResult[object]:
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    return OperationResult.success(_SHOW_OPERATION, _session_data(session, authoritative=True))


def _diagnostic_begin(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="investigation.started",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={"request": {}, "result": {}},
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    return OperationResult.success(_BEGIN_OPERATION, {"session": accepted.session.to_dict()})


def _diagnostic_add_hypothesis(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    statement: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    if session.state != "INVESTIGATING":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="hypothesis.added",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"statement": statement},
            "result": {
                "hypothesis": {
                    "hypothesis_id": _new_hypothesis_id(),
                    "statement": statement,
                    "status": "open",
                    "confidence_basis": "unrated",
                    "supporting": [],
                    "refuting": [],
                }
            },
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    accepted_payload = accepted.event.to_dict()["payload"]
    assert isinstance(accepted_payload, dict)
    accepted_result = accepted_payload["result"]
    assert isinstance(accepted_result, dict)
    hypothesis = accepted_result["hypothesis"]
    assert isinstance(hypothesis, dict)
    return OperationResult.success(
        _HYPOTHESIS_ADD_OPERATION,
        {"session": accepted.session.to_dict(), "hypothesis": hypothesis},
    )


def _diagnostic_assess_hypothesis(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    hypothesis_id: object,
    plan_id: object,
    step_id: object,
    polarity: object,
    rationale: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    hypothesis_id = _validate_hypothesis_id(hypothesis_id)
    plan_id = _validate_plan_id(plan_id)
    step_id = _validate_step_id(step_id)
    if not isinstance(polarity, str) or polarity not in {"supports", "refutes"}:
        raise _WorkflowFailure(DIAGNOSTIC_PLAN_INVALID)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    if session.state != "INVESTIGATING":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    hypotheses = tuple(item for item in session.hypotheses if item.hypothesis_id == hypothesis_id)
    plans = tuple(item for item in session.observation_plans if item.plan_id == plan_id)
    if len(hypotheses) != 1 or len(plans) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    hypothesis = hypotheses[0]
    plan = plans[0]
    steps = tuple(item for item in plan.steps if item.step_id == step_id)
    results = tuple(
        item
        for item in session.observation_results
        if item.plan_id == plan_id and item.step_id == step_id
    )
    if len(steps) != 1 or len(results) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    step = steps[0]
    observation = results[0]
    if (
        observation.selector != step.selector
        or observation.expected_value != step.expected_value
        or observation.evidence_id != session.failed_evidence_id
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    assessment = EvidenceAssessment.new(
        hypothesis_id=hypothesis.hypothesis_id,
        plan_id=plan.plan_id,
        step_id=step.step_id,
        evidence_id=observation.evidence_id,
        selector=observation.selector,
        observed_value=observation.observed_value,
        polarity=polarity,
        rationale=rationale,
    )
    assessment_data = assessment.to_dict()
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="hypothesis.assessed",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {
                "hypothesis_id": hypothesis.hypothesis_id,
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "polarity": polarity,
                "rationale": rationale,
            },
            "result": {"assessment": assessment_data},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    accepted_payload = accepted.event.to_dict()["payload"]
    assert isinstance(accepted_payload, dict)
    accepted_result = accepted_payload["result"]
    assert isinstance(accepted_result, dict)
    accepted_assessment = accepted_result["assessment"]
    assert isinstance(accepted_assessment, dict)
    return OperationResult.success(
        _HYPOTHESIS_ASSESS_OPERATION,
        {"session": accepted.session.to_dict(), "assessment": accepted_assessment},
    )


def _load_bound_failed_run(state: _WorkflowState, session: DiagnosticSession) -> object:
    published = _load_authoritative_run(
        state,
        session.failed_test_run_id,
        failed_run_mode=session.failed_run_mode,
        expected_identity=session.identity,
    )
    envelope = getattr(published, "envelope", None)
    if getattr(envelope, "evidence_id", None) != session.failed_evidence_id:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    return getattr(published, "manifest")


def _hash_value(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    return value


def _same_scope(left: object, right: object) -> bool:
    return all(
        getattr(left, field, None) == getattr(right, field, None)
        for field in ("workspace_id", "project_id", "session_id", "target_device")
    )


def _same_replay_identity(left: object, right: object) -> bool:
    return all(
        getattr(left, field, None) == getattr(right, field, None)
        for field in (
            "workspace_id", "project_id", "build_id", "elf_sha256", "target_device",
            "input_snapshot_sha256", "git_commit", "git_dirty",
        )
    )


def _load_target_run(
    state: _WorkflowState,
    run_id: str,
    *,
    expected_state: Literal["failed", "passed"],
    expected_identity: object | None = None,
) -> object:
    published = _load_failed_run(state, run_id, failed_run_mode="target")
    manifest = getattr(published, "manifest", None)
    envelope = getattr(published, "envelope", None)
    root = getattr(published, "root", None)
    identity = getattr(manifest, "identity", None)
    if identity is None or identity.project_id != str(state.model.logical_project_id):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    if expected_identity is not None and not _same_scope(identity, expected_identity):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    expected_metadata = {
        "mode": "target",
        "state": expected_state,
        "execution_source": "replay",
        "physical_transport_evidence": False,
        "origin_workspace_id": identity.workspace_id,
        "import_workspace_id": state.workspace.workspace_id,
    }
    if (
        getattr(manifest, "run_id", None) != run_id
        or getattr(manifest, "mode", None) != "target"
        or getattr(manifest, "state", None) != expected_state
        or getattr(manifest, "transport", None) != "replay"
        or getattr(envelope, "identity", None) != identity
        or getattr(envelope, "operation", None) != _TARGET_REPLAY_OPERATION
        or getattr(root, "manifest_id", None) != getattr(envelope, "evidence_id", None)
        or getattr(root, "metadata", None) != expected_metadata
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    return published


def _validate_declaration_lineage(
    declaration: SourceChangeDeclaration,
    *,
    before_identity: object,
    after_identity: object | None = None,
) -> None:
    if (
        declaration.before_source_sha256 != getattr(before_identity, "input_snapshot_sha256", None)
        or declaration.before_build_id != getattr(before_identity, "build_id", None)
        or declaration.before_elf_sha256 != getattr(before_identity, "elf_sha256", None)
    ):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    if after_identity is not None and (
        declaration.after_source_sha256 != getattr(after_identity, "input_snapshot_sha256", None)
        or declaration.after_build_id != getattr(after_identity, "build_id", None)
        or declaration.after_elf_sha256 != getattr(after_identity, "elf_sha256", None)
    ):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)


def _read_json_evidence(
    state: _WorkflowState,
    *,
    root_type: str,
    root_id: str,
    operation: str,
    kind: str,
) -> tuple[object, EvidenceEnvelope, ArtifactRef, bytes, dict[str, object]]:
    try:
        root = get_root(state.evidence_store, root_type, root_id)
        envelope = state.evidence_store.get_envelope(root.manifest_id)
        if (
            root.root_type != root_type
            or root.root_id != root_id
            or root.manifest_id != str(envelope.evidence_id)
            or root.metadata != envelope.metadata
            or envelope.operation != operation
            or len(envelope.artifacts) != 1
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        artifact = envelope.artifacts[0]
        if artifact.kind != kind or artifact.media_type != "application/json":
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        payload = state.evidence_store.read_artifact(
            artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
        )
        if (
            artifact.size_bytes != len(payload)
            or artifact.sha256 != hashlib.sha256(payload).hexdigest()
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        decoded = _decode_replay_json(payload)
        if not isinstance(decoded, dict) or _canonical_replay_json_bytes(decoded) != payload:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        return root, envelope, artifact, payload, cast(dict[str, object], decoded)
    except _WorkflowFailure:
        raise
    except FileNotFoundError as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except (EvidenceValidationError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except OSError as error:
        raise _WorkflowFailure(_ENVIRONMENT_FAILURE) from error


def _read_transcript_parent(
    state: _WorkflowState,
    *,
    evidence_id: str,
    run: object,
    expected_role: str,
) -> tuple[EvidenceEnvelope, dict[str, object]]:
    try:
        run_identity = getattr(run, "identity", run)
        envelope = state.evidence_store.get_envelope(evidence_id)
        metadata = dict(envelope.metadata)
        expected_metadata_fields = {
            "operation_id", "scenario_role", "origin_workspace_id", "import_workspace_id",
            "origin_run_id", "projected_run_id", "fixture_sha256", "execution_source",
            "physical_transport_evidence",
        }
        if (
            envelope.operation != "monitor-replay-import"
            or envelope.parents
            or len(envelope.artifacts) != 1
            or set(metadata) != expected_metadata_fields
            or metadata["scenario_role"] != expected_role
            or metadata["origin_workspace_id"] != getattr(run_identity, "workspace_id", None)
            or metadata["import_workspace_id"] != state.workspace.workspace_id
            or metadata["execution_source"] != "replay"
            or metadata["physical_transport_evidence"] is not False
            or not _same_replay_identity(envelope.identity, run_identity)
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        operation_id = metadata["operation_id"]
        if not isinstance(operation_id, str) or not operation_id:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        try:
            operation_uuid = UUID(operation_id)
            origin_run_uuid = UUID(str(metadata["origin_run_id"]))
            projected_run_uuid = UUID(str(metadata["projected_run_id"]))
        except (AttributeError, TypeError, ValueError) as error:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
        if (
            str(operation_uuid) != operation_id
            or origin_run_uuid != operation_uuid
            or projected_run_uuid != origin_run_uuid
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        root = get_root(state.evidence_store, "monitor-run", operation_id)
        root_metadata = dict(root.metadata)
        expected_root_fields = {
            "fixture_sha256", "run_ref_sha256", "origin_workspace_id", "import_workspace_id",
            "execution_source", "physical_transport_evidence",
        }
        if (
            root.root_id != operation_id
            or root.manifest_id != str(envelope.evidence_id)
            or set(root_metadata) != expected_root_fields
            or root_metadata["fixture_sha256"] != metadata["fixture_sha256"]
            or root_metadata["origin_workspace_id"] != metadata["origin_workspace_id"]
            or root_metadata["import_workspace_id"] != metadata["import_workspace_id"]
            or root_metadata["execution_source"] != "replay"
            or root_metadata["physical_transport_evidence"] is not False
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        _hash_value(metadata["fixture_sha256"])
        _hash_value(root_metadata["run_ref_sha256"])
        artifact = envelope.artifacts[0]
        if artifact.kind != "monitor-replay-transcript" or artifact.media_type != "application/json":
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        raw = state.evidence_store.read_artifact(
            artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
        )
        if artifact.size_bytes != len(raw) or artifact.sha256 != hashlib.sha256(raw).hexdigest():
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        body = raw[:-1] if raw.endswith(b"\n") else raw
        decoded = _decode_replay_json(body)
        canonical = _canonical_replay_json_bytes(decoded)
        if not isinstance(decoded, dict) or raw not in (
            canonical, canonical + b"\n"
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        try:
            decoded = validate_replay_document(decoded)
        except ReplayContractError as error:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
        if (
            decoded["schema"] != MONITOR_REPLAY_SCHEMA
            or decoded["source"] != MONITOR_REPLAY_SOURCE
            or decoded["scenario_role"] != expected_role
            or decoded["fixture_sha256"] != metadata["fixture_sha256"]
            or decoded["physical_transport_evidence"] is not False
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        binding = cast(dict[str, object], decoded["binding"])
        expected_binding = {
            "workspaceId": run_identity.workspace_id,
            "logicalProjectId": run_identity.project_id,
            "targetDevice": run_identity.target_device,
            "buildId": run_identity.build_id,
            "elfSha256": run_identity.elf_sha256,
            "inputSnapshotSha256": run_identity.input_snapshot_sha256,
            "gitHead": run_identity.git_commit,
            "gitDirty": run_identity.git_dirty,
        }
        if any(binding.get(key) != value for key, value in expected_binding.items()):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        if binding.get("sessionId") != envelope.identity.session_id:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        batches = cast(list[object], decoded["batches"])
        if any(
            not isinstance(batch, dict)
            or batch.get("runId") != metadata["origin_run_id"]
            or batch.get("binding") != binding
            for batch in batches
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        reference = _read_monitor_reference_authority(
            state,
            operation_id=operation_id,
            expected_role=expected_role,
            run_identity=run_identity,
            transcript_root=root,
            transcript_envelope=envelope,
            transcript_metadata=metadata,
            transcript_document=decoded,
            transcript_binding=binding,
            transcript_batches=batches,
        )
        return envelope, reference
    except _WorkflowFailure:
        raise
    except FileNotFoundError as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except EvidenceValidationError as error:
        code = _ENVIRONMENT_FAILURE if _has_provider_os_error(error) else _EVIDENCE_INTEGRITY_FAILURE
        raise _WorkflowFailure(code) from error
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except OSError as error:
        raise _WorkflowFailure(_ENVIRONMENT_FAILURE) from error


def _read_monitor_reference_authority(
    state: _WorkflowState,
    *,
    operation_id: str,
    expected_role: str,
    run_identity: object,
    transcript_root: object,
    transcript_envelope: EvidenceEnvelope,
    transcript_metadata: dict[str, object],
    transcript_document: dict[str, object],
    transcript_binding: dict[str, object],
    transcript_batches: list[object],
) -> dict[str, object]:
    """Load the shared wire projection, then validate Toolkit-side authority bindings."""
    try:
        reference_root = get_root(
            state.evidence_store,
            "monitor-run-ref",
            operation_id,
        )
        root_metadata = dict(reference_root.metadata)
        if (
            reference_root.root_type != "monitor-run-ref"
            or reference_root.root_id != operation_id
            or set(root_metadata) != _MONITOR_REF_METADATA_FIELDS
            or root_metadata["operation_id"] != operation_id
            or root_metadata["fixture_sha256"] != transcript_metadata["fixture_sha256"]
            or root_metadata["scenario_role"] != expected_role
            or root_metadata["origin_workspace_id"] != transcript_binding["workspaceId"]
            or root_metadata["import_workspace_id"] != state.workspace.workspace_id
            or root_metadata["execution_source"] != "replay"
            or root_metadata["physical_transport_evidence"] is not False
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        _hash_value(root_metadata["run_ref_sha256"])
        reference_envelope = state.evidence_store.get_envelope(reference_root.manifest_id)
        if (
            reference_root.manifest_id != str(reference_envelope.evidence_id)
            or reference_envelope.operation != "monitor-run-ref"
            or reference_envelope.parents != (str(transcript_envelope.evidence_id),)
            or len(reference_envelope.artifacts) != 1
            or dict(reference_envelope.metadata) != root_metadata
            or reference_envelope.produced_at_utc != transcript_envelope.produced_at_utc
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        artifact = reference_envelope.artifacts[0]
        if artifact.kind != "monitor-run-ref" or artifact.media_type != "application/json":
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        raw = state.evidence_store.read_artifact(
            artifact,
            maximum_bytes=MAX_EVIDENCE_READ_BYTES,
        )
        if (
            artifact.size_bytes != len(raw)
            or artifact.sha256 != hashlib.sha256(raw).hexdigest()
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        decoded = _decode_replay_json(raw)
        if not isinstance(decoded, dict) or _canonical_replay_json_bytes(decoded) != raw:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        try:
            reference = validate_run_reference(decoded)
        except ReplayContractError as error:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error

        if (
            reference["schema"] != MONITOR_RUN_REF_SCHEMA
            or reference["operation_id"] != operation_id
            or reference["scenario_role"] != expected_role
            or reference["execution_source"] != "replay"
            or reference["physical_transport_evidence"] is not False
            or reference["run_ref_sha256"] != root_metadata["run_ref_sha256"]
            or reference["fixture_sha256"] != transcript_metadata["fixture_sha256"]
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        try:
            if str(UUID(operation_id)) != operation_id:
                raise ValueError("operation_id is not canonical")
        except (TypeError, ValueError) as error:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error

        expected_reference = {
            "origin_workspace_id": transcript_binding["workspaceId"],
            "import_workspace_id": state.workspace.workspace_id,
            "logical_project_id": transcript_binding["logicalProjectId"],
            "origin_session_id": transcript_binding["sessionId"],
            "projected_session_id": state.workspace.session_id,
            "origin_run_id": transcript_metadata["origin_run_id"],
            "projected_run_id": transcript_metadata["projected_run_id"],
            "target_device": transcript_binding["targetDevice"],
            "probe_id": transcript_binding["probeId"],
            "physical_target": transcript_binding["physicalTarget"],
            "build_id": transcript_binding["buildId"],
            "elf_sha256": transcript_binding["elfSha256"],
            "input_snapshot_sha256": transcript_binding["inputSnapshotSha256"],
            "git_head": transcript_binding["gitHead"],
            "git_dirty": transcript_binding["gitDirty"],
            "flash_session_id": transcript_binding["flashSessionId"],
            "lease_id": transcript_binding["leaseId"],
            "dwarf_sha256": transcript_binding["dwarfSha256"],
            "svd_sha256": transcript_binding["svdSha256"],
        }
        if any(reference[key] != value for key, value in expected_reference.items()):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        if (
            reference["logical_project_id"] != str(state.model.logical_project_id)
            or reference["origin_workspace_id"] != getattr(run_identity, "workspace_id", None)
            or reference["logical_project_id"] != getattr(run_identity, "project_id", None)
        ):
            raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)

        expected_transcript_identity = {
            "workspace_id": reference["origin_workspace_id"],
            "project_id": reference["logical_project_id"],
            "session_id": reference["origin_session_id"],
            "build_id": reference["build_id"],
            "elf_sha256": reference["elf_sha256"],
            "target_device": reference["target_device"],
            "input_snapshot_sha256": reference["input_snapshot_sha256"],
            "git_commit": reference["git_head"],
            "git_dirty": reference["git_dirty"],
        }
        if any(
            getattr(reference_envelope.identity, key, None) != value
            for key, value in expected_transcript_identity.items()
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        if reference["transcript_evidence_id"] != str(transcript_envelope.evidence_id):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        if (
            transcript_root.root_type != "monitor-run"
            or transcript_root.root_id != operation_id
            or transcript_root.manifest_id != str(transcript_envelope.evidence_id)
            or dict(transcript_root.metadata)
            != {
                "fixture_sha256": reference["fixture_sha256"],
                "run_ref_sha256": reference["run_ref_sha256"],
                "origin_workspace_id": reference["origin_workspace_id"],
                "import_workspace_id": reference["import_workspace_id"],
                "execution_source": "replay",
                "physical_transport_evidence": False,
            }
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        if (
            hashlib.sha256(
                _canonical_replay_json_bytes(
                    {key: value for key, value in transcript_document.items() if key != "fixture_sha256"}
                )
            ).hexdigest()
            != reference["fixture_sha256"]
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        group_id = transcript_batches[0].get("groupId")
        group_revision = transcript_batches[0].get("groupRevision")
        start_sequence = transcript_batches[0].get("sequence")
        end_sequence_exclusive = transcript_batches[-1].get("sequence")
        start_captured = transcript_batches[0].get("capturedUnixNs")
        end_captured_exclusive = transcript_batches[-1].get("capturedUnixNs")
        if (
            not isinstance(group_id, str)
            or not isinstance(group_revision, int)
            or isinstance(group_revision, bool)
            or not isinstance(start_sequence, int)
            or isinstance(start_sequence, bool)
            or not isinstance(end_sequence_exclusive, int)
            or isinstance(end_sequence_exclusive, bool)
            or not isinstance(start_captured, int)
            or isinstance(start_captured, bool)
            or not isinstance(end_captured_exclusive, int)
            or isinstance(end_captured_exclusive, bool)
            or reference["group_id"] != group_id
            or reference["group_revision"] != group_revision
            or reference["start_sequence"] != start_sequence
            or reference["end_sequence_exclusive"] != end_sequence_exclusive + 1
            or reference["start_captured_unix_ns"] != start_captured
            or reference["end_captured_unix_ns_exclusive"] != end_captured_exclusive + 1
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        if any(
            not isinstance(batch, dict)
            or batch.get("groupId") != group_id
            or batch.get("groupRevision") != group_revision
            or batch.get("sequence") != start_sequence + index
            or batch.get("runId") != reference["origin_run_id"]
            for index, batch in enumerate(transcript_batches)
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        projected_digests = reference["projected_batch_sha256s"]
        if not isinstance(projected_digests, list) or len(projected_digests) != len(transcript_batches):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        if any(
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in projected_digests
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        projected_binding = dict(transcript_binding)
        projected_binding["workspaceId"] = reference["import_workspace_id"]
        projected_binding["sessionId"] = reference["projected_session_id"]
        calculated_digests: list[str] = []
        for batch in transcript_batches:
            if not isinstance(batch, dict):
                raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
            projected_batch = dict(batch)
            projected_batch["binding"] = projected_binding
            calculated_digests.append(
                hashlib.sha256(_canonical_replay_json_bytes(projected_batch)).hexdigest()
            )
        if projected_digests != calculated_digests:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)

        return reference
    except _WorkflowFailure:
        raise
    except FileNotFoundError as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except EvidenceValidationError as error:
        code = _ENVIRONMENT_FAILURE if _has_provider_os_error(error) else _EVIDENCE_INTEGRITY_FAILURE
        raise _WorkflowFailure(code) from error
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except OSError as error:
        raise _WorkflowFailure(_ENVIRONMENT_FAILURE) from error


def _read_diff_evidence(
    state: _WorkflowState,
    session: DiagnosticSession,
    declaration: SourceChangeDeclaration,
) -> None:
    try:
        envelope = state.evidence_store.get_envelope(declaration.diff_evidence_id)
        if (
            envelope.operation != "diagnostic-source-change"
            or envelope.parents
            or len(envelope.artifacts) != 1
            or envelope.metadata != {"kind": "source-change-diff"}
            or not _same_scope(envelope.identity, session.identity)
            or envelope.artifacts[0] != declaration.diff_artifact
            or declaration.diff_artifact.kind != "source-diff"
            or declaration.diff_artifact.media_type != "text/x-diff"
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        payload = state.evidence_store.read_artifact(
            declaration.diff_artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
        )
        if (
            len(payload) != declaration.diff_artifact.size_bytes
            or hashlib.sha256(payload).hexdigest() != declaration.diff_artifact.sha256
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    except _WorkflowFailure:
        raise
    except FileNotFoundError as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except EvidenceValidationError as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    except OSError as error:
        raise _WorkflowFailure(_ENVIRONMENT_FAILURE) from error


def _require_exact_mapping(value: object, fields: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    return cast(dict[str, object], value)


def _validate_analysis(
    state: _WorkflowState,
    session: DiagnosticSession,
    declaration: SourceChangeDeclaration,
    plan: VerificationPlan,
    before: object,
    after: object,
    analysis_id: str,
    analysis_evidence_id: str,
) -> EvidenceEnvelope:
    _root, envelope, _artifact, _payload, analysis = _read_json_evidence(
        state,
        root_type=_ANALYSIS_ROOT,
        root_id=analysis_id,
        operation=_ANALYSIS_OPERATION,
        kind=_ANALYSIS_ROOT,
    )
    if str(envelope.evidence_id) != analysis_evidence_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    after_identity = getattr(after, "identity", None)
    before_identity = getattr(before, "identity", None)
    if not isinstance(after_identity, object) or not isinstance(before_identity, object):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if not _same_replay_identity(envelope.identity, after_identity):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    expected_metadata = {
        "analysis_id": analysis_id,
        "before_run_id": analysis.get("before_run_id"),
        "after_run_id": analysis.get("after_run_id"),
        "source_change_declaration_id": declaration.declaration_id,
        "origin_workspace_id": after_identity.workspace_id,
        "import_workspace_id": state.workspace.workspace_id,
        "origin_session_id": envelope.identity.session_id,
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    if dict(envelope.metadata) != expected_metadata:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if envelope.parents != tuple(envelope.parents) or len(envelope.parents) != 3:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if envelope.parents[2] != declaration.diff_evidence_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    before_transcript, before_reference = _read_transcript_parent(
        state,
        evidence_id=envelope.parents[0],
        run=before_identity,
        expected_role="failed-before",
    )
    after_transcript, after_reference = _read_transcript_parent(
        state,
        evidence_id=envelope.parents[1],
        run=after_identity,
        expected_role="fixed-after",
    )
    if (
        analysis.get("before_run_id") != before_reference["run_ref_sha256"]
        or analysis.get("after_run_id") != after_reference["run_ref_sha256"]
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if before_transcript.identity.session_id != after_transcript.identity.session_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if envelope.identity != after_transcript.identity:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if set(analysis) != _ANALYSIS_FIELDS:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if analysis["schema"] != _ANALYSIS_SCHEMA or analysis["analysis_id"] != analysis_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    unsigned = {key: value for key, value in analysis.items() if key != "analysis_id"}
    try:
        calculated_analysis_id = hashlib.sha256(
            _canonical_replay_json_bytes(unsigned)
        ).hexdigest()
    except (TypeError, ValueError, OverflowError, UnicodeError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    if calculated_analysis_id != analysis_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    for field in ("request_digest", "before_run_id", "after_run_id"):
        _hash_value(analysis[field])
    identity = _require_exact_mapping(analysis["identity"], _ANALYSIS_IDENTITY_FIELDS)
    if (
        identity["schema"] != _ANALYSIS_LINEAGE_SCHEMA
        or identity["origin_workspace_id"] != after_identity.workspace_id
        or identity["import_workspace_id"] != state.workspace.workspace_id
        or identity["logical_project_id"] != str(state.model.logical_project_id)
        or identity["target_device"] != after_identity.target_device
        or identity["source_change_declaration_id"] != declaration.declaration_id
        or identity["before_input_snapshot_sha256"] != before_identity.input_snapshot_sha256
        or identity["before_build_id"] != before_identity.build_id
        or identity["before_elf_sha256"] != before_identity.elf_sha256
        or identity["after_input_snapshot_sha256"] != after_identity.input_snapshot_sha256
        or identity["after_build_id"] != after_identity.build_id
        or identity["after_elf_sha256"] != after_identity.elf_sha256
    ):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    for field in (
        "origin_workspace_id", "import_workspace_id", "before_input_snapshot_sha256", "before_build_id",
        "before_elf_sha256", "after_input_snapshot_sha256", "after_build_id", "after_elf_sha256",
    ):
        _hash_value(identity[field])
    if (
        analysis["quality"] != plan.required_monitor_quality
        or analysis["quality"] != "VALID"
        or analysis["conclusion"] != "COMPLETED"
        or analysis["changed"] is not True
        or analysis["reason_code"] != "VALUES_CHANGED"
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    for field in ("aligned_position_count", "aligned_pair_count", "excluded_position_count"):
        value = analysis[field]
        if type(value) is not int or isinstance(value, bool) or not 0 <= value <= 2048:
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if (
        analysis["aligned_position_count"] < 1
        or analysis["aligned_pair_count"] < 2
        or analysis["aligned_pair_count"] > analysis["aligned_position_count"]
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if (
        analysis["excluded_position_count"]
        != analysis["aligned_position_count"] - analysis["aligned_pair_count"]
        or analysis["excluded_position_count"] != 0
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    numeric_fields = (
        "before_first", "before_last", "before_min", "before_max", "after_first", "after_last",
        "after_min", "after_max", "delta_first", "delta_last",
    )
    for field in numeric_fields:
        value = analysis[field]
        if type(value) not in (int, float) or isinstance(value, bool) or (
            type(value) is float and not math.isfinite(value)
        ):
            raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    try:
        for prefix in ("before", "after"):
            minimum = analysis[f"{prefix}_min"]
            first = analysis[f"{prefix}_first"]
            last = analysis[f"{prefix}_last"]
            maximum = analysis[f"{prefix}_max"]
            if not (minimum <= first <= maximum and minimum <= last <= maximum):
                raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
        expected_delta_first = analysis["after_first"] - analysis["before_first"]
        expected_delta_last = analysis["after_last"] - analysis["before_last"]
    except _WorkflowFailure:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    if (
        (type(expected_delta_first) is float and not math.isfinite(expected_delta_first))
        or (type(expected_delta_last) is float and not math.isfinite(expected_delta_last))
        or analysis["delta_first"] != expected_delta_first
        or analysis["delta_last"] != expected_delta_last
    ):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    return envelope


def _validate_marker(
    state: _WorkflowState,
    session: DiagnosticSession,
    declaration: SourceChangeDeclaration,
    before: object,
    after: object,
    marker: DiagnosticMarkerRef,
    analysis_identity: object,
) -> None:
    _root, envelope, _artifact, _payload, payload = _read_json_evidence(
        state,
        root_type=_MARKER_ROOT,
        root_id=marker.marker_id,
        operation=_MARKER_OPERATION,
        kind=_MARKER_ROOT,
    )
    if envelope.identity != analysis_identity:
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    expected_metadata = {
        "marker_id": marker.marker_id,
        "analysis_id": marker.analysis_id,
        "analysis_evidence_id": marker.analysis_evidence_id,
        "origin_workspace_id": analysis_identity.workspace_id,
        "import_workspace_id": state.workspace.workspace_id,
        "origin_session_id": analysis_identity.session_id,
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    if dict(envelope.metadata) != expected_metadata or envelope.parents != (marker.analysis_evidence_id,):
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if str(envelope.evidence_id) != marker.marker_evidence_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if set(payload) != _MARKER_FIELDS or payload["schema"] != _MARKER_SCHEMA:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    if payload["marker_id"] != marker.marker_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    unsigned = {key: value for key, value in payload.items() if key != "marker_id"}
    try:
        calculated_marker_id = hashlib.sha256(_canonical_replay_json_bytes(unsigned)).hexdigest()
    except (TypeError, ValueError, OverflowError, UnicodeError) as error:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE) from error
    if calculated_marker_id != marker.marker_id:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)
    expected_shared = {
        "marker_id": marker.marker_id,
        "analysis_id": marker.analysis_id,
        "analysis_evidence_id": marker.analysis_evidence_id,
        "diagnostic_session_id": marker.diagnostic_session_id,
        "hypothesis_id": marker.hypothesis_id,
        "polarity": marker.polarity,
        "label": marker.label,
        "rationale": marker.rationale,
    }
    if {key: payload[key] for key in expected_shared} != expected_shared:
        raise _WorkflowFailure(_EVIDENCE_INTEGRITY_FAILURE)


def _diagnostic_declare_source_change(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    source_change_declaration: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    declaration = SourceChangeDeclaration.from_value(source_change_declaration)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id, target_projection=True)
    if session.state not in {"INVESTIGATING", "FIX_PROPOSED"}:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    failed = _load_target_run(
        state,
        session.failed_test_run_id,
        expected_state="failed",
        expected_identity=session.identity,
    )
    _validate_declaration_lineage(
        declaration, before_identity=getattr(failed, "manifest").identity
    )
    _read_diff_evidence(state, session, declaration)
    if session.state == "FIX_PROPOSED" and not any(
        item.declaration_id == declaration.declaration_id
        for item in session.source_change_declarations
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    declaration_data = declaration.to_dict()
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="source_change.declared",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"source_change_declaration": declaration_data},
            "result": {"declaration_id": declaration.declaration_id},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id, event, expected_revision=expected_revision
    )
    return OperationResult.success(
        _SOURCE_CHANGE_DECLARE_OPERATION,
        {
            "session": accepted.session.to_dict(),
            "source_change_declaration": declaration_data,
        },
    )


def _diagnostic_add_verification_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    verification_plan: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    plan = VerificationPlan.from_value(verification_plan)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id, target_projection=True)
    if session.state != "FIX_PROPOSED":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    declarations = tuple(
        item
        for item in session.source_change_declarations
        if item.declaration_id == plan.source_change_declaration_id
    )
    if (
        len(declarations) != 1
        or plan.diagnostic_session_id != session.diagnostic_session_id
        or plan.failed_before_run_id != session.failed_test_run_id
        or plan.failed_before_evidence_id != session.failed_evidence_id
        or plan.verification_plan_id != declarations[0].validation_plan_id
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    declaration = declarations[0]
    _read_diff_evidence(state, session, declaration)
    before = _load_target_run(
        state,
        plan.failed_before_run_id,
        expected_state="failed",
        expected_identity=session.identity,
    )
    after = _load_target_run(
        state,
        plan.fixed_after_run_id,
        expected_state="passed",
        expected_identity=session.identity,
    )
    _validate_declaration_lineage(
        declaration,
        before_identity=getattr(before, "manifest").identity,
        after_identity=getattr(after, "manifest").identity,
    )
    if (
        str(getattr(before, "envelope").evidence_id) != plan.failed_before_evidence_id
        or str(getattr(after, "envelope").evidence_id) != plan.fixed_after_evidence_id
    ):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    if len(plan.required_analysis_ids) == 0:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    for analysis_id, analysis_evidence_id in zip(
        plan.required_analysis_ids, plan.required_analysis_evidence_ids
    ):
        _validate_analysis(
            state,
            session,
            declaration,
            plan,
            getattr(before, "manifest"),
            getattr(after, "manifest"),
            analysis_id,
            analysis_evidence_id,
        )
    plan_data = plan.to_dict()
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="verification.plan_added",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"verification_plan": plan_data},
            "result": {
                "verification_plan_id": plan.verification_plan_id,
                "plan_digest": plan.plan_digest,
            },
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id, event, expected_revision=expected_revision
    )
    return OperationResult.success(
        _VERIFICATION_PLAN_ADD_OPERATION,
        {"session": accepted.session.to_dict(), "verification_plan": plan_data},
    )


def _diagnostic_start_verification(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    verification_plan_id: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    verification_plan_id = _validate_plan_id(verification_plan_id)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id, target_projection=True)
    if session.state not in {"FIX_PROPOSED", "VERIFYING"}:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    plans = tuple(
        item
        for item in session.verification_plans
        if item.verification_plan_id == verification_plan_id
    )
    if len(plans) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="verification.started",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"verification_plan_id": verification_plan_id},
            "result": {"verification_plan_id": verification_plan_id},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id, event, expected_revision=expected_revision
    )
    return OperationResult.success(
        _VERIFICATION_START_OPERATION,
        {"session": accepted.session.to_dict(), "verification_plan_id": verification_plan_id},
    )


def _diagnostic_attach_marker(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    diagnostic_marker_ref: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    marker = DiagnosticMarkerRef.from_value(diagnostic_marker_ref)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id, target_projection=True)
    if session.state != "VERIFYING":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    if session.active_verification_plan_id is None:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    plans = tuple(
        item
        for item in session.verification_plans
        if item.verification_plan_id == session.active_verification_plan_id
    )
    if len(plans) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    plan = plans[0]
    declarations = tuple(
        item
        for item in session.source_change_declarations
        if item.declaration_id == plan.source_change_declaration_id
    )
    if len(declarations) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    declaration = declarations[0]
    if marker.hypothesis_id not in declaration.claimed_hypothesis_ids:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    if not any(
        marker.analysis_id == analysis_id and marker.analysis_evidence_id == evidence_id
        for analysis_id, evidence_id in zip(
            plan.required_analysis_ids, plan.required_analysis_evidence_ids
        )
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    before = _load_target_run(
        state,
        plan.failed_before_run_id,
        expected_state="failed",
        expected_identity=session.identity,
    )
    after = _load_target_run(
        state,
        plan.fixed_after_run_id,
        expected_state="passed",
        expected_identity=session.identity,
    )
    _validate_declaration_lineage(
        declaration,
        before_identity=getattr(before, "manifest").identity,
        after_identity=getattr(after, "manifest").identity,
    )
    if (
        str(getattr(before, "envelope").evidence_id) != plan.failed_before_evidence_id
        or str(getattr(after, "envelope").evidence_id) != plan.fixed_after_evidence_id
    ):
        raise _WorkflowFailure(_INCOMPATIBLE_IDENTITY)
    analysis_envelope = _validate_analysis(
        state,
        session,
        declaration,
        plan,
        getattr(before, "manifest"),
        getattr(after, "manifest"),
        marker.analysis_id,
        marker.analysis_evidence_id,
    )
    _validate_marker(
        state,
        session,
        declaration,
        getattr(before, "manifest"),
        getattr(after, "manifest"),
        marker,
        analysis_identity=analysis_envelope.identity,
    )
    marker_data = marker.to_dict()
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="analysis.marker_attached",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"diagnostic_marker_ref": marker_data},
            "result": {"marker_id": marker.marker_id},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id, event, expected_revision=expected_revision
    )
    return OperationResult.success(
        _MARKER_ATTACH_OPERATION,
        {"session": accepted.session.to_dict(), "diagnostic_marker_ref": marker_data},
    )


def _observation_plan(
    session: DiagnosticSession,
    steps: object,
) -> ObservationPlan:
    if not isinstance(steps, list):
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    decoded_steps = tuple(ObservationStep.from_value(item) for item in steps)
    fields = {
        "diagnostic_session_id": session.diagnostic_session_id,
        "created_revision": session.revision + 1,
        "steps": [step.to_dict() for step in decoded_steps],
    }
    digest = calculate_plan_digest(fields)
    return ObservationPlan(
        plan_id=digest,
        diagnostic_session_id=session.diagnostic_session_id,
        created_revision=session.revision + 1,
        steps=decoded_steps,
        digest=digest,
    )


def _resolve_observation_selector(manifest: object, step: ObservationStep) -> object:
    selector = step.selector
    kind = selector["kind"]
    if kind == "run-state":
        return getattr(manifest, "state")
    if kind == "case-state":
        case_id = selector["case_id"]
        matches = tuple(
            case for case in getattr(manifest, "cases") if getattr(case, "case_id", None) == case_id
        )
        if len(matches) != 1:
            raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
        return getattr(matches[0], "state")
    if kind == "case-count":
        state = selector["state"]
        return sum(
            getattr(case, "state", None) == state
            for case in getattr(manifest, "cases")
        )
    raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)


def _diagnostic_add_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    steps: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    if session.state != "INVESTIGATING":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    manifest = _load_bound_failed_run(state, session)
    plan = _observation_plan(session, steps)
    for step in plan.steps:
        _resolve_observation_selector(manifest, step)
    plan_data = plan.to_dict()
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="observation.plan_added",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"steps": plan_data["steps"]},
            "result": {"observation_plan": plan_data},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    accepted_payload = accepted.event.to_dict()["payload"]
    assert isinstance(accepted_payload, dict)
    accepted_result = accepted_payload["result"]
    assert isinstance(accepted_result, dict)
    observation_plan = accepted_result["observation_plan"]
    assert isinstance(observation_plan, dict)
    return OperationResult.success(
        _PLAN_ADD_OPERATION,
        {"session": accepted.session.to_dict(), "observation_plan": observation_plan},
    )


def _diagnostic_run_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    plan_id: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    plan_id = _validate_plan_id(plan_id)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    if session.state != "INVESTIGATING":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_TRANSITION)
    matching_plans = tuple(plan for plan in session.observation_plans if plan.plan_id == plan_id)
    if len(matching_plans) != 1:
        raise DiagnosticValidationError(DIAGNOSTIC_PLAN_INVALID)
    plan = matching_plans[0]
    manifest = _load_bound_failed_run(state, session)
    observation_results_list: list[ObservationResult] = []
    for step in plan.steps:
        observed = _resolve_observation_selector(manifest, step)
        observation_results_list.append(
            ObservationResult(
                plan_id=plan.plan_id,
                step_id=step.step_id,
                evidence_id=session.failed_evidence_id,
                selector=step.selector,
                observed_value=observed,
                expected_value=step.expected_value,
                matched=observed == step.expected_value,
            )
        )
    observation_results = tuple(observation_results_list)
    result_data = [item.to_dict() for item in observation_results]
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="observation.plan_executed",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={
            "request": {"plan_id": plan.plan_id},
            "result": {"observation_results": result_data},
        },
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    accepted_payload = accepted.event.to_dict()["payload"]
    assert isinstance(accepted_payload, dict)
    accepted_result = accepted_payload["result"]
    assert isinstance(accepted_result, dict)
    accepted_observation_results = accepted_result["observation_results"]
    assert isinstance(accepted_observation_results, list)
    return OperationResult.success(
        _PLAN_RUN_OPERATION,
        {
            "session": accepted.session.to_dict(),
            "observation_results": accepted_observation_results,
        },
    )


def diagnostic_declare_source_change(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    source_change_declaration: SourceChangeDeclaration | dict[str, object],
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _SOURCE_CHANGE_DECLARE_OPERATION,
        lambda: _diagnostic_declare_source_change(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            source_change_declaration=source_change_declaration,
            actor=actor,
        ),
    )


def diagnostic_add_verification_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    verification_plan: VerificationPlan | dict[str, object],
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _VERIFICATION_PLAN_ADD_OPERATION,
        lambda: _diagnostic_add_verification_plan(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            verification_plan=verification_plan,
            actor=actor,
        ),
    )


def diagnostic_start_verification(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    verification_plan_id: str,
    actor: str = "tool",
) -> OperationResult[object]:
    return _result(
        _VERIFICATION_START_OPERATION,
        lambda: _diagnostic_start_verification(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            verification_plan_id=verification_plan_id,
            actor=actor,
        ),
    )


def diagnostic_attach_marker(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    diagnostic_marker_ref: DiagnosticMarkerRef | dict[str, object],
    actor: str = "tool",
) -> OperationResult[object]:
    return _result(
        _MARKER_ATTACH_OPERATION,
        lambda: _diagnostic_attach_marker(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            diagnostic_marker_ref=diagnostic_marker_ref,
            actor=actor,
        ),
    )


def diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    failed_test_run_id: str,
    failed_run_mode: Literal["host", "target"] = "host",
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _START_OPERATION,
        lambda: _diagnostic_start(
            context,
            operation_id=operation_id,
            failed_test_run_id=failed_test_run_id,
            failed_run_mode=failed_run_mode,
            actor=actor,
        ),
    )


def diagnostic_show(
    context: DiagnosticWorkflowContext,
    *,
    diagnostic_session_id: str,
) -> OperationResult[object]:
    return _result(
        _SHOW_OPERATION,
        lambda: _diagnostic_show(context, diagnostic_session_id=diagnostic_session_id),
    )


def diagnostic_begin(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _BEGIN_OPERATION,
        lambda: _diagnostic_begin(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            actor=actor,
        ),
    )


def diagnostic_add_hypothesis(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    statement: str,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _HYPOTHESIS_ADD_OPERATION,
        lambda: _diagnostic_add_hypothesis(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            statement=statement,
            actor=actor,
        ),
    )


def diagnostic_assess_hypothesis(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    hypothesis_id: str,
    plan_id: str,
    step_id: str,
    polarity: str,
    rationale: str,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _HYPOTHESIS_ASSESS_OPERATION,
        lambda: _diagnostic_assess_hypothesis(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id=step_id,
            polarity=polarity,
            rationale=rationale,
            actor=actor,
        ),
    )


def diagnostic_add_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    steps: list[object],
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _PLAN_ADD_OPERATION,
        lambda: _diagnostic_add_plan(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            steps=steps,
            actor=actor,
        ),
    )


def diagnostic_run_plan(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    plan_id: str,
    actor: str = "tool",
) -> OperationResult[object]:
    return _result(
        _PLAN_RUN_OPERATION,
        lambda: _diagnostic_run_plan(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            plan_id=plan_id,
            actor=actor,
        ),
    )


__all__ = [
    "DiagnosticWorkflowContext",
    "diagnostic_start",
    "diagnostic_show",
    "diagnostic_begin",
    "diagnostic_add_hypothesis",
    "diagnostic_assess_hypothesis",
    "diagnostic_add_plan",
    "diagnostic_run_plan",
    "diagnostic_declare_source_change",
    "diagnostic_add_verification_plan",
    "diagnostic_start_verification",
    "diagnostic_attach_marker",
]
