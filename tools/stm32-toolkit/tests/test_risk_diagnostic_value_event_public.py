from __future__ import annotations

from copy import deepcopy

import pytest
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
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
    calculate_fix_verification_id,
    calculate_plan_digest,
    calculate_source_change_declaration_id,
    calculate_verification_plan_digest,
    reduce_event,
)
from stm32_toolkit.evidence import ArtifactRef
from test_diagnostic_events import (
    SID,
)
from test_diagnostic_events import (
    _event as fixture_event,
)
from test_diagnostic_events import (
    _session_with_executed_plan as fixture_session_with_executed_plan,
)
from test_diagnostic_events import (
    _session_with_plan as fixture_session_with_plan,
)
from test_diagnostic_model import (
    _plan as fixture_plan,
)
from test_diagnostic_model import (
    _session_components,
    _session_kwargs,
    _session_source,
)

_MESSAGES = {
    DIAGNOSTIC_INVALID_EVENT: "event/model/operation intent is invalid",
    DIAGNOSTIC_INVALID_TRANSITION: "event is illegal in current state",
    DIAGNOSTIC_PLAN_INVALID: "selector, expected value, plan, or step reference is invalid",
}


class DerivedArtifactRef(ArtifactRef):
    pass


class DerivedSourceChangeDeclaration(SourceChangeDeclaration):
    pass


class DerivedVerificationPlan(VerificationPlan):
    pass


class DerivedDiagnosticMarkerRef(DiagnosticMarkerRef):
    pass


class DerivedFixVerification(FixVerification):
    pass


def _expect_failure(factory, expected_code: str, candidate: object = None) -> None:
    before = deepcopy(candidate) if candidate is not None else None
    with pytest.raises(DiagnosticValidationError) as raised:
        factory()
    error = raised.value
    assert (error.code, error.message) == (expected_code, _MESSAGES[expected_code])
    if candidate is not None:
        assert candidate == before


def _assessment(
    plan_id: str,
    step: dict[str, object],
    *,
    observed_value: str = "failed",
    hypothesis_id: str = "1" * 32,
    polarity: str = "supports",
    rationale: str = "supports",
) -> EvidenceAssessment:
    return EvidenceAssessment.new(
        hypothesis_id=hypothesis_id,
        plan_id=plan_id,
        step_id=step["step_id"],
        evidence_id="0" * 64,
        selector=step["selector"],
        observed_value=observed_value,
        polarity=polarity,
        rationale=rationale,
    )


def _assessed_prefix() -> tuple[object, str, dict[str, object], object]:
    session, plan_id, step, _execute = fixture_session_with_executed_plan()
    hypothesis = {
        "hypothesis_id": "1" * 32,
        "statement": "the host test failed",
        "status": "open",
        "confidence_basis": "unrated",
        "supporting": [],
        "refuting": [],
    }
    add_hypothesis = fixture_event(
        sequence=session.revision,
        event_type="hypothesis.added",
        request={"statement": hypothesis["statement"]},
        result={"hypothesis": hypothesis},
        previous_digest=session.event_head,
    )
    session = reduce_event(session, add_hypothesis)
    assessment = _assessment(plan_id, step)
    assessed = fixture_event(
        sequence=session.revision,
        event_type="hypothesis.assessed",
        request={
            "hypothesis_id": assessment.hypothesis_id,
            "plan_id": assessment.plan_id,
            "step_id": assessment.step_id,
            "polarity": assessment.polarity,
            "rationale": assessment.rationale,
        },
        result={"assessment": assessment.to_dict()},
        previous_digest=session.event_head,
    )
    return reduce_event(session, assessed), plan_id, step, assessed


def _failed_verification_prefix() -> tuple[object, SourceChangeDeclaration]:
    session, _plan_id, _step, _ = _assessed_prefix()
    source = _session_source()
    declared = fixture_event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    session = reduce_event(session, declared)
    verification_plan = VerificationPlan.new(
        verification_plan_id=source.validation_plan_id,
        diagnostic_session_id=SID,
        failed_before_run_id="run-1",
        failed_before_evidence_id="0" * 64,
        source_change_declaration_id=source.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id="1" * 64,
        required_analysis_ids=("a" * 64,),
        required_analysis_evidence_ids=("b" * 64,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    plan_added = fixture_event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": verification_plan.to_dict()},
        result={
            "verification_plan_id": verification_plan.verification_plan_id,
            "plan_digest": verification_plan.plan_digest,
        },
        previous_digest=session.event_head,
    )
    session = reduce_event(session, plan_added)
    started = fixture_event(
        sequence=session.revision,
        event_type="verification.started",
        request={"verification_plan_id": verification_plan.verification_plan_id},
        result={"verification_plan_id": verification_plan.verification_plan_id},
        previous_digest=session.event_head,
    )
    session = reduce_event(session, started)
    marker = DiagnosticMarkerRef.new(
        marker_id="c" * 64,
        marker_evidence_id="d" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="the public analysis observed the change",
    )
    attached = fixture_event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=session.event_head,
    )
    session = reduce_event(session, attached)
    verification = FixVerification.new(
        diagnostic_session_id=SID,
        failed_before_run_id="run-1",
        failed_before_evidence_id="0" * 64,
        source_change_declaration_id=source.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id="1" * 64,
        verification_plan_id=verification_plan.verification_plan_id,
        verification_plan_digest=verification_plan.plan_digest,
        analysis_ids=("a" * 64,),
        analysis_evidence_ids=("b" * 64,),
        executed_operation_ids=("verify-operation",),
        status="FAILED",
        reason_code="FIXED_TEST_FAILED",
        completed_at_utc="2026-08-21T12:00:00.000000Z",
    )
    completed = fixture_event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=session.event_head,
    )
    return reduce_event(session, completed), source


def test_public_lifecycle_values_round_trip_and_recalculate_digests() -> None:
    hypothesis, plan, result = _session_components()
    session = DiagnosticSession(**_session_kwargs())
    assert DiagnosticSession.from_value(session.to_dict()) == session
    assert ObservationPlan.from_value(plan.to_dict()) == plan
    assert ObservationResult.from_value(result.to_dict()) == result
    assert Hypothesis.from_value(hypothesis.to_dict()) == hypothesis

    source = _session_source()
    assert SourceChangeDeclaration.from_value(source.to_dict()) == source
    assert calculate_source_change_declaration_id(source) == source.declaration_id

    verification = VerificationPlan.new(
        verification_plan_id=source.validation_plan_id,
        diagnostic_session_id=SID,
        failed_before_run_id="run-before",
        failed_before_evidence_id="4" * 64,
        source_change_declaration_id=source.declaration_id,
        fixed_after_run_id="run-after",
        fixed_after_evidence_id="5" * 64,
        required_analysis_ids=("6" * 64,),
        required_analysis_evidence_ids=("7" * 64,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    assert VerificationPlan.from_value(verification.to_dict()) == verification
    assert calculate_verification_plan_digest(verification) == verification.plan_digest

    marker = DiagnosticMarkerRef.new(
        marker_id="8" * 64,
        marker_evidence_id="9" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="the public marker records the observation",
    )
    assert DiagnosticMarkerRef.from_value(marker.to_dict()) == marker

    fix = FixVerification.new(
        diagnostic_session_id=SID,
        failed_before_run_id=verification.failed_before_run_id,
        failed_before_evidence_id=verification.failed_before_evidence_id,
        source_change_declaration_id=verification.source_change_declaration_id,
        fixed_after_run_id=verification.fixed_after_run_id,
        fixed_after_evidence_id=verification.fixed_after_evidence_id,
        verification_plan_id=verification.verification_plan_id,
        verification_plan_digest=verification.plan_digest,
        analysis_ids=("6" * 64,),
        analysis_evidence_ids=("7" * 64,),
        executed_operation_ids=("verify-operation",),
        status="PASSED",
        reason_code="VERIFICATION_PASSED",
        completed_at_utc="2026-08-21T12:00:00.000000Z",
    )
    assert FixVerification.from_value(fix.to_dict()) == fix
    assert calculate_fix_verification_id(fix) == fix.fix_verification_id

    event = fixture_event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": session.identity.to_dict()},
    )
    assert calculate_event_digest(event) == event.digest
    assert DiagnosticEvent.from_value(event.to_dict()) == event


def test_public_invalid_values_refuse_without_mutating_external_wires() -> None:
    with pytest.raises(ValueError, match="unknown diagnostic validation error code"):
        DiagnosticValidationError("DIAGNOSTIC_UNKNOWN")

    event = fixture_event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={
            "failed_evidence_id": "0" * 64,
            "identity": _session_kwargs()["identity"].to_dict(),
        },
    )
    invalid_sequence = event.to_dict()
    invalid_sequence["sequence"] = -1
    _expect_failure(
        lambda: DiagnosticEvent.from_value(invalid_sequence),
        DIAGNOSTIC_INVALID_EVENT,
        invalid_sequence,
    )

    invalid_selector = {
        "step_id": "failed-state",
        "selector": {
            "kind": "physical-monitor-fact/1",
            "continuation_evidence_id": "1" * 64,
            "monitor_ref_evidence_id": "2" * 64,
            "monitor_run_ref": {},
            "selector_kind": "variable",
            "selector": "testtime",
            "fact": "value-varies",
            "minimum_valid_samples": 1,
            "bit_index": 0,
        },
        "expected_value": 1,
        "purpose": "invalid value-varies selector",
    }
    _expect_failure(
        lambda: ObservationStep.from_value(invalid_selector),
        DIAGNOSTIC_PLAN_INVALID,
        invalid_selector,
    )

    invalid_session = DiagnosticSession(**_session_kwargs()).to_dict()
    supporting = invalid_session["hypotheses"][0]["supporting"][0]
    invalid_assessment = EvidenceAssessment.new(
        hypothesis_id="2" * 32,
        plan_id=supporting["plan_id"],
        step_id=supporting["step_id"],
        evidence_id=supporting["evidence_id"],
        selector=supporting["selector"],
        observed_value=supporting["observed_value"],
        polarity=supporting["polarity"],
        rationale=supporting["rationale"],
    )
    invalid_session["hypotheses"][0]["supporting"][0] = invalid_assessment.to_dict()
    _expect_failure(
        lambda: DiagnosticSession.from_value(invalid_session),
        DIAGNOSTIC_PLAN_INVALID,
        invalid_session,
    )

    for field in (
        "source_change_declarations",
        "verification_plans",
        "diagnostic_marker_refs",
        "fix_verifications",
    ):
        kwargs = _session_kwargs()
        kwargs[field] = (object(),)
        _expect_failure(
            lambda kwargs=kwargs: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
        )

    invalid_payload = event.to_dict()
    invalid_payload["payload"] = {"request": [], "result": {}}
    _expect_failure(
        lambda: DiagnosticEvent.from_value(invalid_payload),
        DIAGNOSTIC_INVALID_EVENT,
        invalid_payload,
    )

    plan = fixture_plan()
    step = plan.steps[0].to_dict()
    assessment = _assessment(plan.plan_id, step)
    assessed = fixture_event(
        sequence=0,
        event_type="hypothesis.assessed",
        request={
            "hypothesis_id": assessment.hypothesis_id,
            "plan_id": assessment.plan_id,
            "step_id": assessment.step_id,
            "polarity": assessment.polarity,
            "rationale": assessment.rationale,
        },
        result={"assessment": assessment.to_dict()},
    )
    invalid_polarity = assessed.to_dict()
    invalid_polarity["payload"]["request"]["polarity"] = "neutral"
    _expect_failure(
        lambda: DiagnosticEvent.from_value(invalid_polarity),
        DIAGNOSTIC_PLAN_INVALID,
        invalid_polarity,
    )
    mismatch = assessed.to_dict()
    mismatch["payload"]["request"]["polarity"] = "refutes"
    _expect_failure(
        lambda: DiagnosticEvent.from_value(mismatch),
        DIAGNOSTIC_INVALID_EVENT,
        mismatch,
    )

    with pytest.raises(DiagnosticValidationError) as raised:
        calculate_event_digest(42)
    assert (raised.value.code, raised.value.message) == (
        DIAGNOSTIC_INVALID_EVENT,
        _MESSAGES[DIAGNOSTIC_INVALID_EVENT],
    )

    extra = event.to_dict()
    extra["unexpected"] = True
    _expect_failure(
        lambda: calculate_event_digest(extra),
        DIAGNOSTIC_INVALID_EVENT,
        extra,
    )
    wrong_schema = event.to_dict()
    wrong_schema["schema"] = "stm32-toolkit/other/v1"
    _expect_failure(
        lambda: calculate_event_digest(wrong_schema),
        DIAGNOSTIC_INVALID_EVENT,
        wrong_schema,
    )

    source = _session_source()
    verification = VerificationPlan.new(
        verification_plan_id=source.validation_plan_id,
        diagnostic_session_id=SID,
        failed_before_run_id="run-before",
        failed_before_evidence_id="4" * 64,
        source_change_declaration_id=source.declaration_id,
        fixed_after_run_id="run-after",
        fixed_after_evidence_id="5" * 64,
        required_analysis_ids=("6" * 64,),
        required_analysis_evidence_ids=("7" * 64,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    invalid_changed = verification.to_dict()
    invalid_changed["expected_changed"] = False
    _expect_failure(
        lambda: VerificationPlan.from_value(invalid_changed),
        DIAGNOSTIC_INVALID_EVENT,
        invalid_changed,
    )

    artifact = source.diff_artifact
    derived_artifact = DerivedArtifactRef(
        artifact.sha256,
        artifact.size_bytes,
        artifact.relative_path,
        artifact.kind,
        artifact.media_type,
    )
    _expect_failure(
        lambda: SourceChangeDeclaration.new(
            before_source_sha256=source.before_source_sha256,
            after_source_sha256=source.after_source_sha256,
            before_build_id=source.before_build_id,
            before_elf_sha256=source.before_elf_sha256,
            after_build_id=source.after_build_id,
            after_elf_sha256=source.after_elf_sha256,
            changed_paths=source.changed_paths,
            diff_evidence_id=source.diff_evidence_id,
            diff_artifact=derived_artifact,
            claimed_hypothesis_ids=source.claimed_hypothesis_ids,
            validation_plan_id=source.validation_plan_id,
        ),
        DIAGNOSTIC_INVALID_EVENT,
    )

    derived_source = DerivedSourceChangeDeclaration(
        source.schema,
        source.declaration_id,
        source.before_source_sha256,
        source.after_source_sha256,
        source.before_build_id,
        source.before_elf_sha256,
        source.after_build_id,
        source.after_elf_sha256,
        source.changed_paths,
        source.diff_evidence_id,
        source.diff_artifact,
        source.claimed_hypothesis_ids,
        source.validation_plan_id,
    )
    _expect_failure(
        lambda: calculate_source_change_declaration_id(derived_source),
        DIAGNOSTIC_INVALID_EVENT,
    )

    derived_verification = DerivedVerificationPlan(
        verification.schema,
        verification.verification_plan_id,
        verification.diagnostic_session_id,
        verification.failed_before_run_id,
        verification.failed_before_evidence_id,
        verification.source_change_declaration_id,
        verification.fixed_after_run_id,
        verification.fixed_after_evidence_id,
        verification.required_analysis_ids,
        verification.required_analysis_evidence_ids,
        verification.required_monitor_quality,
        verification.expected_changed,
        verification.plan_digest,
        verification.continuation_evidence_id,
    )
    _expect_failure(
        lambda: calculate_verification_plan_digest(derived_verification),
        DIAGNOSTIC_INVALID_EVENT,
    )
    _expect_failure(
        lambda: VerificationPlan.from_value(derived_verification),
        DIAGNOSTIC_INVALID_EVENT,
    )

    marker = DiagnosticMarkerRef.new(
        marker_id="8" * 64,
        marker_evidence_id="9" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="public marker",
    )
    derived_marker = DerivedDiagnosticMarkerRef(
        marker.schema,
        marker.marker_id,
        marker.marker_evidence_id,
        marker.analysis_id,
        marker.analysis_evidence_id,
        marker.diagnostic_session_id,
        marker.hypothesis_id,
        marker.polarity,
        marker.label,
        marker.rationale,
    )
    _expect_failure(lambda: derived_marker.to_dict(), DIAGNOSTIC_INVALID_EVENT)
    _expect_failure(
        lambda: DiagnosticMarkerRef.from_value(derived_marker),
        DIAGNOSTIC_INVALID_EVENT,
    )

    fix = FixVerification.new(
        diagnostic_session_id=SID,
        failed_before_run_id=verification.failed_before_run_id,
        failed_before_evidence_id=verification.failed_before_evidence_id,
        source_change_declaration_id=verification.source_change_declaration_id,
        fixed_after_run_id=verification.fixed_after_run_id,
        fixed_after_evidence_id=verification.fixed_after_evidence_id,
        verification_plan_id=verification.verification_plan_id,
        verification_plan_digest=verification.plan_digest,
        analysis_ids=("6" * 64,),
        analysis_evidence_ids=("7" * 64,),
        executed_operation_ids=("verify-operation",),
        status="PASSED",
        reason_code="VERIFICATION_PASSED",
        completed_at_utc="2026-08-21T12:00:00.000000Z",
    )
    derived_fix = DerivedFixVerification(
        fix.schema,
        fix.fix_verification_id,
        fix.diagnostic_session_id,
        fix.failed_before_run_id,
        fix.failed_before_evidence_id,
        fix.source_change_declaration_id,
        fix.fixed_after_run_id,
        fix.fixed_after_evidence_id,
        fix.verification_plan_id,
        fix.verification_plan_digest,
        fix.analysis_ids,
        fix.analysis_evidence_ids,
        fix.executed_operation_ids,
        fix.status,
        fix.reason_code,
        fix.completed_at_utc,
    )
    _expect_failure(
        lambda: calculate_fix_verification_id(derived_fix),
        DIAGNOSTIC_INVALID_EVENT,
    )
    _expect_failure(
        lambda: FixVerification.from_value(derived_fix),
        DIAGNOSTIC_INVALID_EVENT,
    )


def test_public_reducer_refusals_preserve_and_reuse_the_session() -> None:
    session, _, step, _ = fixture_session_with_plan()
    marker = DiagnosticMarkerRef.new(
        marker_id="8" * 64,
        marker_evidence_id="9" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="public marker",
    )
    marker_event = fixture_event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=session.event_head,
    )
    before = session.to_dict()
    _expect_failure(
        lambda: reduce_event(session, marker_event),
        DIAGNOSTIC_INVALID_TRANSITION,
    )
    assert session.to_dict() == before

    session, _, step, _ = fixture_session_with_plan()
    foreign_session_id = "e" * 32
    foreign_step = ObservationStep.from_value(step)
    foreign_plan_fields = {
        "diagnostic_session_id": foreign_session_id,
        "created_revision": session.revision,
        "steps": [foreign_step.to_dict()],
    }
    foreign_plan_digest = calculate_plan_digest(foreign_plan_fields)
    foreign_plan = ObservationPlan(
        plan_id=foreign_plan_digest,
        diagnostic_session_id=foreign_session_id,
        created_revision=session.revision,
        steps=(foreign_step,),
        digest=foreign_plan_digest,
    )
    assert ObservationPlan.from_value(foreign_plan.to_dict()) == foreign_plan
    bad_plan = fixture_event(
        sequence=session.revision,
        event_type="observation.plan_added",
        request={"steps": [step]},
        result={"observation_plan": foreign_plan.to_dict()},
        previous_digest=session.event_head,
    )
    before = session.to_dict()
    _expect_failure(
        lambda: reduce_event(session, bad_plan),
        DIAGNOSTIC_PLAN_INVALID,
    )
    assert session.to_dict() == before

    session, plan_id, step, _ = _assessed_prefix()
    invalid_result = _assessment(plan_id, step, observed_value="passed")
    assessed_event = fixture_event(
        sequence=session.revision,
        event_type="hypothesis.assessed",
        request={
            "hypothesis_id": invalid_result.hypothesis_id,
            "plan_id": invalid_result.plan_id,
            "step_id": invalid_result.step_id,
            "polarity": invalid_result.polarity,
            "rationale": invalid_result.rationale,
        },
        result={"assessment": invalid_result.to_dict()},
        previous_digest=session.event_head,
    )
    before = session.to_dict()
    _expect_failure(
        lambda: reduce_event(session, assessed_event),
        DIAGNOSTIC_PLAN_INVALID,
    )
    assert session.to_dict() == before

    session, source = _failed_verification_prefix()
    duplicate = fixture_event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    before = session.to_dict()
    _expect_failure(
        lambda: reduce_event(session, duplicate),
        DIAGNOSTIC_PLAN_INVALID,
    )
    assert session.to_dict() == before

    replacement = _session_source(
        claimed_hypothesis_ids=("1" * 32,),
        validation_plan_id="a" * 64,
    )
    valid_next = fixture_event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": replacement.to_dict()},
        result={"declaration_id": replacement.declaration_id},
        previous_digest=session.event_head,
    )
    continued = reduce_event(session, valid_next)
    assert continued.state == "FIX_PROPOSED"
    assert continued.revision == session.revision + 1
    assert continued.source_change_declarations[-1] == replacement

    session, _, _, _ = fixture_session_with_plan()
    before = session.to_dict()
    _expect_failure(
        lambda: reduce_event(session, object()),
        DIAGNOSTIC_INVALID_EVENT,
    )
    assert session.to_dict() == before
