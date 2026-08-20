"""Application workflows for the VS-02 failed-run diagnostic boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
from typing import Callable

from stm32_toolkit.diagnostics import (
    ACTORS,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DIAGNOSTIC_REVISION_CONFLICT,
    DiagnosticSession,
    DiagnosticStore,
    DiagnosticValidationError,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    calculate_plan_digest,
    create_event,
)
from stm32_toolkit.evidence import EvidenceValidationError
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import TestProtocolError
from stm32_toolkit.testing.publication import TestRunRepository


_START_OPERATION = "diagnostic.start"
_SHOW_OPERATION = "diagnostic.show"
_BEGIN_OPERATION = "diagnostic.begin"
_HYPOTHESIS_ADD_OPERATION = "diagnostic.hypothesis.add"
_PLAN_ADD_OPERATION = "diagnostic.plan.add"
_PLAN_RUN_OPERATION = "diagnostic.plan.run"
_OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DIAGNOSTIC_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_PLAN_ID = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


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


def _failure(operation: str, code: str) -> OperationResult[None]:
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
    if (
        getattr(identity, "project_id", None) != str(state.model.logical_project_id)
        or getattr(identity, "workspace_id", None) != state.workspace.workspace_id
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_IDENTITY_MISMATCH)


def _load_failed_run(state: _WorkflowState, failed_test_run_id: str) -> object:
    try:
        return state.repository.load(failed_test_run_id)
    except (EvidenceValidationError, TestProtocolError, OSError, TypeError, ValueError, KeyError, IndexError) as error:
        raise _WorkflowFailure(DIAGNOSTIC_EVIDENCE_MISSING) from error


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
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    failed_test_run_id = _validate_run_id(failed_test_run_id)
    actor = _validate_actor(actor)
    state = _make_state(context)
    published = _load_failed_run(state, failed_test_run_id)
    manifest = getattr(published, "manifest")
    if getattr(manifest, "mode", None) != "host" or getattr(manifest, "state", None) != "failed":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    identity = getattr(manifest, "identity")
    _require_identity(state, identity)
    envelope = getattr(published, "envelope")
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
            "request": {"failed_test_run_id": failed_test_run_id},
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


def _load_bound_session(state: _WorkflowState, diagnostic_session_id: str) -> DiagnosticSession:
    session = state.diagnostic_store.load(diagnostic_session_id)
    _require_identity(state, session.identity)
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


def _load_bound_failed_run(state: _WorkflowState, session: DiagnosticSession) -> object:
    published = _load_failed_run(state, session.failed_test_run_id)
    manifest = getattr(published, "manifest", None)
    envelope = getattr(published, "envelope", None)
    if (
        manifest is None
        or envelope is None
        or getattr(manifest, "mode", None) != "host"
        or getattr(manifest, "state", None) != "failed"
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    if getattr(envelope, "evidence_id", None) != session.failed_evidence_id:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    if (
        getattr(manifest, "identity", None) != session.identity
        or getattr(envelope, "identity", None) != session.identity
    ):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    return manifest


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


def diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    failed_test_run_id: str,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _START_OPERATION,
        lambda: _diagnostic_start(
            context,
            operation_id=operation_id,
            failed_test_run_id=failed_test_run_id,
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
    "diagnostic_add_plan",
    "diagnostic_run_plan",
]
