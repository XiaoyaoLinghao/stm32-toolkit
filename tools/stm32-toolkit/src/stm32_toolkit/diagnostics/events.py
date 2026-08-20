"""Pure event construction and reduction for the VS-02 diagnostic domain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from stm32_toolkit.evidence import EvidenceIdentity

from .model import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DIAGNOSTIC_SCHEMA,
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticValidationError,
    EvidenceAssessment,
    Hypothesis,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    calculate_event_digest,
)
from .model import _fail


def create_event(
    diagnostic_session_id: str,
    operation_id: str,
    sequence: int,
    revision_before: int,
    event_type: str,
    occurred_at_utc: str,
    actor: str,
    previous_digest: str | None,
    payload: Mapping[str, object],
    *,
    schema: str = DIAGNOSTIC_SCHEMA,
) -> DiagnosticEvent:
    """Validate and hash one closed diagnostic event."""

    without_digest = {
        "schema": schema,
        "diagnostic_session_id": diagnostic_session_id,
        "operation_id": operation_id,
        "sequence": sequence,
        "revision_before": revision_before,
        "event_type": event_type,
        "occurred_at_utc": occurred_at_utc,
        "actor": actor,
        "previous_digest": previous_digest,
        "payload": payload,
    }
    digest = calculate_event_digest(without_digest)
    return DiagnosticEvent(
        schema,
        diagnostic_session_id,
        operation_id,
        sequence,
        revision_before,
        event_type,
        occurred_at_utc,
        actor,
        previous_digest,
        payload,
        digest,
    )


def _payload(event: DiagnosticEvent) -> tuple[dict[str, object], dict[str, object]]:
    raw = event.to_dict()["payload"]
    assert isinstance(raw, dict)
    request = raw["request"]
    result = raw["result"]
    assert isinstance(request, dict) and isinstance(result, dict)
    return request, result


def _advance(
    session: DiagnosticSession,
    event: DiagnosticEvent,
    *,
    state: str | None = None,
    hypotheses: tuple[Hypothesis, ...] | None = None,
    observation_plans: tuple[ObservationPlan, ...] | None = None,
    observation_results: tuple[ObservationResult, ...] | None = None,
) -> DiagnosticSession:
    return DiagnosticSession(
        diagnostic_session_id=session.diagnostic_session_id,
        revision=session.revision + 1,
        state=cast(str, session.state if state is None else state),
        identity=session.identity,
        failed_test_run_id=session.failed_test_run_id,
        failed_evidence_id=session.failed_evidence_id,
        event_head=event.digest,
        hypotheses=session.hypotheses if hypotheses is None else hypotheses,
        observation_plans=session.observation_plans if observation_plans is None else observation_plans,
        observation_results=session.observation_results if observation_results is None else observation_results,
    )


def _require_chain(session: DiagnosticSession | None, event: DiagnosticEvent) -> None:
    if session is None:
        if event.event_type != "session.created" or event.sequence != 0 or event.revision_before != 0 or event.previous_digest is not None:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        return
    if event.event_type == "session.created":
        _fail(DIAGNOSTIC_INVALID_TRANSITION)
    if (
        event.diagnostic_session_id != session.diagnostic_session_id
        or event.sequence != session.revision
        or event.revision_before != session.revision
        or event.previous_digest != session.event_head
    ):
        _fail(DIAGNOSTIC_INVALID_EVENT)


def _require_state(session: DiagnosticSession, event_type: str) -> None:
    if event_type == "investigation.started":
        if session.state != "OPEN":
            _fail(DIAGNOSTIC_INVALID_TRANSITION)
    elif session.state != "INVESTIGATING":
        _fail(DIAGNOSTIC_INVALID_TRANSITION)


def _reduce_created(event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    failed_test_run_id = request["failed_test_run_id"]
    failed_evidence_id = result["failed_evidence_id"]
    identity = result["identity"]
    if not isinstance(identity, Mapping):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    try:
        decoded_identity = EvidenceIdentity.from_dict(identity)
    except Exception:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    assert isinstance(decoded_identity, EvidenceIdentity)
    return DiagnosticSession(
        diagnostic_session_id=event.diagnostic_session_id,
        revision=1,
        state="OPEN",
        identity=decoded_identity,
        failed_test_run_id=cast(str, failed_test_run_id),
        failed_evidence_id=cast(str, failed_evidence_id),
        event_head=event.digest,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
    )


def _reduce_hypothesis_added(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    hypothesis_data = result["hypothesis"]
    hypothesis = Hypothesis.from_value(hypothesis_data)
    if hypothesis.statement != request["statement"] or any(
        item.hypothesis_id == hypothesis.hypothesis_id for item in session.hypotheses
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(session, event, hypotheses=session.hypotheses + (hypothesis,))


def _reduce_plan_added(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    request_steps = request["steps"]
    assert isinstance(request_steps, list)
    steps = tuple(ObservationStep.from_value(item) for item in request_steps)
    plan_data = result["observation_plan"]
    plan = ObservationPlan.from_value(plan_data)
    if (
        plan.diagnostic_session_id != session.diagnostic_session_id
        or plan.created_revision != session.revision + 1
        or plan.steps != steps
        or any(item.plan_id == plan.plan_id for item in session.observation_plans)
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(session, event, observation_plans=session.observation_plans + (plan,))


def _reduce_plan_executed(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    plan_id = cast(str, request["plan_id"])
    plan = next((item for item in session.observation_plans if item.plan_id == plan_id), None)
    if plan is None:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    values = result["observation_results"]
    assert isinstance(values, list)
    decoded = tuple(ObservationResult.from_value(item) for item in values)
    if len(decoded) != len(plan.steps) or any(
        item.evidence_id != session.failed_evidence_id
        or item.plan_id != plan.plan_id or item.step_id != plan.steps[index].step_id
        or item.selector != plan.steps[index].selector
        or item.expected_value != plan.steps[index].expected_value
        for index, item in enumerate(decoded)
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if any((item.plan_id, item.step_id) in {(old.plan_id, old.step_id) for old in session.observation_results} for item in decoded):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(session, event, observation_results=session.observation_results + decoded)


def _reduce_assessed(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    assessment = EvidenceAssessment.from_value(result["assessment"])
    if {
        key: assessment.to_dict()[key]
        for key in ("hypothesis_id", "plan_id", "step_id", "polarity", "rationale")
    } != request:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    hypothesis_index = next(
        (index for index, item in enumerate(session.hypotheses) if item.hypothesis_id == assessment.hypothesis_id),
        None,
    )
    if hypothesis_index is None:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    observation = next(
        (
            item
            for item in session.observation_results
            if item.plan_id == assessment.plan_id and item.step_id == assessment.step_id
        ),
        None,
    )
    if observation is None or (
        observation.evidence_id != assessment.evidence_id
        or observation.selector != assessment.selector
        or observation.observed_value != assessment.observed_value
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    hypothesis = session.hypotheses[hypothesis_index]
    all_assessments = hypothesis.supporting + hypothesis.refuting
    if any(item.assessment_id == assessment.assessment_id for item in all_assessments):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    key = (assessment.evidence_id, assessment.selector)
    opposite = hypothesis.refuting if assessment.polarity == "supports" else hypothesis.supporting
    if any((item.evidence_id, item.selector) == key for item in opposite):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if assessment.polarity == "supports":
        updated = Hypothesis(
            hypothesis.hypothesis_id,
            hypothesis.statement,
            hypothesis.status,
            hypothesis.confidence_basis,
            hypothesis.supporting + (assessment,),
            hypothesis.refuting,
        )
    else:
        updated = Hypothesis(
            hypothesis.hypothesis_id,
            hypothesis.statement,
            hypothesis.status,
            hypothesis.confidence_basis,
            hypothesis.supporting,
            hypothesis.refuting + (assessment,),
        )
    hypotheses = list(session.hypotheses)
    hypotheses[hypothesis_index] = updated
    return _advance(session, event, hypotheses=tuple(hypotheses))


def reduce_event(session_or_none: DiagnosticSession | None, event: DiagnosticEvent) -> DiagnosticSession:
    """Apply one validated event and return a new materialized session view."""

    if not isinstance(event, DiagnosticEvent):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _require_chain(session_or_none, event)
    if session_or_none is None:
        return _reduce_created(event)
    _require_state(session_or_none, event.event_type)
    if event.event_type == "investigation.started":
        return _advance(session_or_none, event, state="INVESTIGATING")
    if event.event_type == "hypothesis.added":
        return _reduce_hypothesis_added(session_or_none, event)
    if event.event_type == "observation.plan_added":
        return _reduce_plan_added(session_or_none, event)
    if event.event_type == "observation.plan_executed":
        return _reduce_plan_executed(session_or_none, event)
    if event.event_type == "hypothesis.assessed":
        return _reduce_assessed(session_or_none, event)
    _fail(DIAGNOSTIC_INVALID_EVENT)


__all__ = ["create_event", "reduce_event"]
