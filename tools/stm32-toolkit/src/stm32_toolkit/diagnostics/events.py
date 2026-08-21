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
    DiagnosticMarkerRef,
    DiagnosticSession,
    DiagnosticValidationError,
    EvidenceAssessment,
    FixVerification,
    Hypothesis,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    SourceChangeDeclaration,
    VerificationPlan,
    calculate_event_digest,
)
from .model import _fail


_KEEP_ACTIVE_PLAN = object()


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
    source_change_declarations: tuple[SourceChangeDeclaration, ...] | None = None,
    verification_plans: tuple[VerificationPlan, ...] | None = None,
    diagnostic_marker_refs: tuple[DiagnosticMarkerRef, ...] | None = None,
    fix_verifications: tuple[FixVerification, ...] | None = None,
    active_verification_plan_id: str | None | object = _KEEP_ACTIVE_PLAN,
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
        source_change_declarations=(
            session.source_change_declarations
            if source_change_declarations is None
            else source_change_declarations
        ),
        verification_plans=session.verification_plans if verification_plans is None else verification_plans,
        diagnostic_marker_refs=(
            session.diagnostic_marker_refs
            if diagnostic_marker_refs is None
            else diagnostic_marker_refs
        ),
        fix_verifications=session.fix_verifications if fix_verifications is None else fix_verifications,
        active_verification_plan_id=(
            session.active_verification_plan_id
            if active_verification_plan_id is _KEEP_ACTIVE_PLAN
            else cast(str | None, active_verification_plan_id)
        ),
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
    elif event_type == "source_change.declared":
        if session.state != "INVESTIGATING":
            _fail(DIAGNOSTIC_INVALID_TRANSITION)
    elif event_type in {"verification.plan_added", "verification.started"}:
        if session.state != "FIX_PROPOSED":
            _fail(DIAGNOSTIC_INVALID_TRANSITION)
    elif event_type in {"analysis.marker_attached", "verification.completed"}:
        if session.state != "VERIFYING":
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


def _reduce_source_change_declared(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    declaration = SourceChangeDeclaration.from_value(request["source_change_declaration"])
    if result["declaration_id"] != declaration.declaration_id:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if any(item.declaration_id == declaration.declaration_id for item in session.source_change_declarations):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if any(
        hypothesis_id not in {item.hypothesis_id for item in session.hypotheses}
        for hypothesis_id in declaration.claimed_hypothesis_ids
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(
        session,
        event,
        state="FIX_PROPOSED",
        source_change_declarations=session.source_change_declarations + (declaration,),
    )


def _reduce_verification_plan_added(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    plan = VerificationPlan.from_value(request["verification_plan"])
    if result["verification_plan_id"] != plan.verification_plan_id or result["plan_digest"] != plan.plan_digest:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if any(item.verification_plan_id == plan.verification_plan_id for item in session.verification_plans):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    declaration = next(
        (
            item
            for item in session.source_change_declarations
            if item.declaration_id == plan.source_change_declaration_id
        ),
        None,
    )
    if (
        declaration is None
        or plan.diagnostic_session_id != session.diagnostic_session_id
        or plan.verification_plan_id != declaration.validation_plan_id
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(
        session,
        event,
        verification_plans=session.verification_plans + (plan,),
    )


def _reduce_verification_started(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    plan_id = cast(str, request["verification_plan_id"])
    if result["verification_plan_id"] != plan_id:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    plan = next((item for item in session.verification_plans if item.verification_plan_id == plan_id), None)
    if plan is None or session.active_verification_plan_id is not None:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(session, event, state="VERIFYING", active_verification_plan_id=plan_id)


def _reduce_marker_attached(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    marker = DiagnosticMarkerRef.from_value(request["diagnostic_marker_ref"])
    if result["marker_id"] != marker.marker_id:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if any(item.marker_id == marker.marker_id for item in session.diagnostic_marker_refs):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if (
        marker.diagnostic_session_id != session.diagnostic_session_id
        or marker.hypothesis_id not in {item.hypothesis_id for item in session.hypotheses}
        or session.active_verification_plan_id is None
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    plan = next(
        (
            item
            for item in session.verification_plans
            if item.verification_plan_id == session.active_verification_plan_id
        ),
        None,
    )
    if plan is None or not any(
        marker.analysis_id == analysis_id and marker.analysis_evidence_id == evidence_id
        for analysis_id, evidence_id in zip(
            plan.required_analysis_ids,
            plan.required_analysis_evidence_ids,
        )
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return _advance(
        session,
        event,
        diagnostic_marker_refs=session.diagnostic_marker_refs + (marker,),
    )


def _reduce_verification_completed(session: DiagnosticSession, event: DiagnosticEvent) -> DiagnosticSession:
    request, result = _payload(event)
    verification = FixVerification.from_value(request["fix_verification"])
    if (
        result["fix_verification_id"] != verification.fix_verification_id
        or result["status"] != verification.status
        or result["reason_code"] != verification.reason_code
    ):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if any(item.fix_verification_id == verification.fix_verification_id for item in session.fix_verifications):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if session.active_verification_plan_id is None:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    plan = next(
        (
            item
            for item in session.verification_plans
            if item.verification_plan_id == session.active_verification_plan_id
        ),
        None,
    )
    declaration = next(
        (
            item
            for item in session.source_change_declarations
            if item.declaration_id == verification.source_change_declaration_id
        ),
        None,
    )
    if plan is None or declaration is None:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if (
        verification.diagnostic_session_id != session.diagnostic_session_id
        or verification.source_change_declaration_id != plan.source_change_declaration_id
        or verification.failed_before_run_id != session.failed_test_run_id
        or verification.failed_before_evidence_id != session.failed_evidence_id
        or verification.failed_before_run_id != plan.failed_before_run_id
        or verification.failed_before_evidence_id != plan.failed_before_evidence_id
        or verification.fixed_after_run_id != plan.fixed_after_run_id
        or verification.fixed_after_evidence_id != plan.fixed_after_evidence_id
        or verification.verification_plan_id != plan.verification_plan_id
        or verification.verification_plan_digest != plan.plan_digest
        or verification.analysis_ids != plan.required_analysis_ids
        or verification.analysis_evidence_ids != plan.required_analysis_evidence_ids
    ):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    next_state = "RESOLVED" if verification.status == "PASSED" else "INVESTIGATING"
    return _advance(
        session,
        event,
        state=next_state,
        fix_verifications=session.fix_verifications + (verification,),
        active_verification_plan_id=None,
    )


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
    if event.event_type == "source_change.declared":
        return _reduce_source_change_declared(session_or_none, event)
    if event.event_type == "verification.plan_added":
        return _reduce_verification_plan_added(session_or_none, event)
    if event.event_type == "verification.started":
        return _reduce_verification_started(session_or_none, event)
    if event.event_type == "analysis.marker_attached":
        return _reduce_marker_attached(session_or_none, event)
    if event.event_type == "verification.completed":
        return _reduce_verification_completed(session_or_none, event)
    _fail(DIAGNOSTIC_INVALID_EVENT)


__all__ = ["create_event", "reduce_event"]
