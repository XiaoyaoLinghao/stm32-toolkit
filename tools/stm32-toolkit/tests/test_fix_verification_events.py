from __future__ import annotations

import pytest
from dataclasses import replace

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DiagnosticEvent,
    DiagnosticMarkerRef,
    DiagnosticSession,
    DiagnosticValidationError,
    FixVerification,
    SourceChangeDeclaration,
    VerificationPlan,
    canonical_diagnostic_json_bytes,
    create_event,
    reduce_event,
)
from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity


IDENTITY = EvidenceIdentity(
    workspace_id="a" * 64,
    project_id="12345678-1234-5678-1234-567812345678",
    session_id="toolkit-session",
    build_id="b" * 64,
    elf_sha256="c" * 64,
    target_device="host:windows/amd64",
    input_snapshot_sha256="d" * 64,
    git_commit="e" * 40,
    git_dirty=False,
)
SID = "f" * 32
HYPOTHESIS_ID = "1" * 32
PLAN_ID = "2" * 64
ANALYSIS_IDS = ("3" * 64, "4" * 64)
ANALYSIS_EVIDENCE_IDS = ("5" * 64, "6" * 64)
UTC = "2026-08-21T12:00:00.000000Z"


def _event(
    *,
    sequence: int,
    event_type: str,
    request: dict[str, object],
    result: dict[str, object],
    previous_digest: str | None = None,
) -> DiagnosticEvent:
    return create_event(
        diagnostic_session_id=SID,
        operation_id=f"op-{sequence}",
        sequence=sequence,
        revision_before=sequence,
        event_type=event_type,
        occurred_at_utc=UTC,
        actor="user",
        previous_digest=previous_digest,
        payload={"request": request, "result": result},
    )


def _source(plan_id: str = PLAN_ID) -> SourceChangeDeclaration:
    return SourceChangeDeclaration.new(
        before_source_sha256="7" * 64,
        after_source_sha256="8" * 64,
        before_build_id="9" * 64,
        before_elf_sha256="a" * 64,
        after_build_id="b" * 64,
        after_elf_sha256="c" * 64,
        changed_paths=("src/main.c",),
        diff_evidence_id="d" * 64,
        diff_artifact=ArtifactRef(
            sha256="e" * 64,
            size_bytes=12,
            relative_path="changes.diff",
            kind="source-diff",
            media_type="text/x-diff",
        ),
        claimed_hypothesis_ids=(HYPOTHESIS_ID,),
        validation_plan_id=plan_id,
    )


def _plan(source: SourceChangeDeclaration | None = None, plan_id: str = PLAN_ID) -> VerificationPlan:
    declaration = _source(plan_id) if source is None else source
    return VerificationPlan.new(
        verification_plan_id=plan_id,
        diagnostic_session_id=SID,
        failed_before_run_id="run-1",
        failed_before_evidence_id="0" * 64,
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id="1" * 64,
        required_analysis_ids=ANALYSIS_IDS,
        required_analysis_evidence_ids=ANALYSIS_EVIDENCE_IDS,
        required_monitor_quality="VALID",
        expected_changed=True,
    )


def _marker(plan: VerificationPlan | None = None) -> DiagnosticMarkerRef:
    _ = plan
    return DiagnosticMarkerRef.new(
        marker_id="6" * 64,
        marker_evidence_id="7" * 64,
        analysis_id=ANALYSIS_IDS[0],
        analysis_evidence_id=ANALYSIS_EVIDENCE_IDS[0],
        diagnostic_session_id=SID,
        hypothesis_id=HYPOTHESIS_ID,
        polarity="supports",
        label="change-observed",
        rationale="the fixed result changed the selected value",
    )


def _fix(plan: VerificationPlan | None = None, *, status: str = "PASSED", reason: str = "VERIFICATION_PASSED") -> FixVerification:
    value = _plan() if plan is None else plan
    return FixVerification.new(
        diagnostic_session_id=SID,
        failed_before_run_id=value.failed_before_run_id,
        failed_before_evidence_id=value.failed_before_evidence_id,
        source_change_declaration_id=value.source_change_declaration_id,
        fixed_after_run_id=value.fixed_after_run_id,
        fixed_after_evidence_id=value.fixed_after_evidence_id,
        verification_plan_id=value.verification_plan_id,
        verification_plan_digest=value.plan_digest,
        analysis_ids=value.required_analysis_ids,
        analysis_evidence_ids=value.required_analysis_evidence_ids,
        executed_operation_ids=("verification.start", "verification.complete"),
        status=status,
        reason_code=reason,
        completed_at_utc="2026-08-21T12:34:56.000000Z",
    )


def _created() -> tuple[DiagnosticSession, DiagnosticEvent]:
    event = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    return reduce_event(None, event), event


def _investigating_with_hypothesis() -> tuple[DiagnosticSession, DiagnosticEvent]:
    session, previous = _created()
    started = _event(
        sequence=session.revision,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, started)
    hypothesis = _event(
        sequence=session.revision,
        event_type="hypothesis.added",
        request={"statement": "the source fix changes the monitor value"},
        result={
            "hypothesis": {
                "hypothesis_id": HYPOTHESIS_ID,
                "statement": "the source fix changes the monitor value",
                "status": "open",
                "confidence_basis": "unrated",
                "supporting": [],
                "refuting": [],
            }
        },
        previous_digest=started.digest,
    )
    return reduce_event(session, hypothesis), hypothesis


def _proposed() -> tuple[DiagnosticSession, SourceChangeDeclaration, VerificationPlan, DiagnosticEvent]:
    session, previous = _investigating_with_hypothesis()
    source = _source()
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, declared)
    plan = _plan(source)
    added = _event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": plan.to_dict()},
        result={"verification_plan_id": plan.verification_plan_id, "plan_digest": plan.plan_digest},
        previous_digest=declared.digest,
    )
    return reduce_event(session, added), source, plan, added


def _verifying() -> tuple[DiagnosticSession, SourceChangeDeclaration, VerificationPlan, DiagnosticEvent]:
    session, source, plan, previous = _proposed()
    started = _event(
        sequence=session.revision,
        event_type="verification.started",
        request={"verification_plan_id": plan.verification_plan_id},
        result={"verification_plan_id": plan.verification_plan_id},
        previous_digest=previous.digest,
    )
    return reduce_event(session, started), source, plan, started


def test_new_lifecycle_reduces_and_extended_session_round_trips() -> None:
    session, source, plan, previous = _verifying()
    marker = _marker(plan)
    attached = _event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, attached)
    assert session.state == "VERIFYING"
    assert session.active_verification_plan_id == plan.verification_plan_id
    assert session.diagnostic_marker_refs == (marker,)

    verification = _fix(plan)
    completed = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=attached.digest,
    )
    session = reduce_event(session, completed)
    assert session.state == "RESOLVED"
    assert session.active_verification_plan_id is None
    assert session.source_change_declarations == (source,)
    assert session.verification_plans == (plan,)
    assert session.fix_verifications == (verification,)
    encoded = session.to_dict()
    assert set(encoded) == {
        "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id",
        "failed_evidence_id", "event_head", "hypotheses", "observation_plans", "observation_results",
        "source_change_declarations", "verification_plans", "diagnostic_marker_refs",
        "fix_verifications", "active_verification_plan_id",
    }
    assert DiagnosticSession.from_value(encoded) == session


def test_legacy_session_shape_and_constructor_remain_unchanged() -> None:
    session, _ = _created()
    assert set(session.to_dict()) == {
        "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id",
        "failed_evidence_id", "event_head", "hypotheses", "observation_plans", "observation_results",
    }
    assert DiagnosticSession.from_value(session.to_dict()) == session
    assert canonical_diagnostic_json_bytes(session.to_dict()) == canonical_diagnostic_json_bytes(
        {
            "diagnostic_session_id": SID,
            "revision": 1,
            "state": "OPEN",
            "identity": IDENTITY.to_dict(),
            "failed_test_run_id": "run-1",
            "failed_evidence_id": "0" * 64,
            "event_head": session.event_head,
            "hypotheses": [],
            "observation_plans": [],
            "observation_results": [],
        }
    )
    positional = DiagnosticSession(
        SID, 1, "OPEN", IDENTITY, "run-1", "0" * 64, session.event_head, (), (), ()
    )
    assert positional.to_dict() == session.to_dict()


@pytest.mark.parametrize(
    "status,reason,expected_state",
    [
        ("FAILED", "FIXED_TEST_FAILED", "INVESTIGATING"),
        ("INCONCLUSIVE", "ANALYSIS_NOT_VALID", "INVESTIGATING"),
        ("CANCELLED", "CALLER_CANCELLED", "INVESTIGATING"),
    ],
)
def test_non_passed_completion_keeps_attempt_and_returns_to_investigating(
    status: str, reason: str, expected_state: str,
) -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan, status=status, reason=reason)
    event = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": status,
            "reason_code": reason,
        },
        previous_digest=previous.digest,
    )
    reduced = reduce_event(session, event)
    assert reduced.state == expected_state
    assert reduced.active_verification_plan_id is None
    assert reduced.fix_verifications == (verification,)


def test_reducer_rejects_missing_reference_plan_mismatch_and_wrong_marker_pair() -> None:
    session, previous = _investigating_with_hypothesis()
    source = _source("f" * 64)
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=previous.digest,
    )
    proposed = reduce_event(session, declared)
    wrong_plan = _plan(source, "e" * 64)
    mismatch = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": wrong_plan.to_dict()},
        result={"verification_plan_id": wrong_plan.verification_plan_id, "plan_digest": wrong_plan.plan_digest},
        previous_digest=declared.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(proposed, mismatch)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID

    valid_plan = _plan(source, "f" * 64)
    added = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": valid_plan.to_dict()},
        result={"verification_plan_id": valid_plan.verification_plan_id, "plan_digest": valid_plan.plan_digest},
        previous_digest=declared.digest,
    )
    proposed = reduce_event(proposed, added)
    started = _event(
        sequence=proposed.revision,
        event_type="verification.started",
        request={"verification_plan_id": valid_plan.verification_plan_id},
        result={"verification_plan_id": valid_plan.verification_plan_id},
        previous_digest=added.digest,
    )
    verifying = reduce_event(proposed, started)
    wrong_marker = DiagnosticMarkerRef.new(
        marker_id="8" * 64,
        marker_evidence_id="9" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id=HYPOTHESIS_ID,
        polarity="supports",
        label="change-observed",
        rationale="wrong analysis pair",
    )
    marker_event = _event(
        sequence=verifying.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": wrong_marker.to_dict()},
        result={"marker_id": wrong_marker.marker_id},
        previous_digest=started.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(verifying, marker_event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


def test_new_payloads_are_closed_and_transitions_are_rejected() -> None:
    session, previous = _investigating_with_hypothesis()
    source = _source()
    # The payload validator runs while the event is created.
    with pytest.raises(DiagnosticValidationError) as error:
        _event(
            sequence=session.revision,
            event_type="source_change.declared",
            request={"source_change_declaration": source.to_dict(), "extra": True},
            result={"declaration_id": source.declaration_id},
            previous_digest=previous.digest,
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    created, created_event = _created()
    source_event = _event(
        sequence=created.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=created_event.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(created, source_event)
    assert error.value.code == DIAGNOSTIC_INVALID_TRANSITION


def test_completion_must_bind_active_plan_and_all_identity_fields() -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan)
    tampered = verification.to_dict()
    tampered["fixed_after_run_id"] = "run-other"
    with pytest.raises(DiagnosticValidationError):
        # The fixed verification ID still belongs to the original content, so event
        # construction must fail closed before reduction.
        _event(
            sequence=session.revision,
            event_type="verification.completed",
            request={"fix_verification": tampered},
            result={
                "fix_verification_id": verification.fix_verification_id,
                "status": verification.status,
                "reason_code": verification.reason_code,
            },
            previous_digest=previous.digest,
        )


def test_completion_result_status_and_reason_are_closed_and_terminal_states_reject_events() -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan)
    with pytest.raises(DiagnosticValidationError) as error:
        _event(
            sequence=session.revision,
            event_type="verification.completed",
            request={"fix_verification": verification.to_dict()},
            result={
                "fix_verification_id": verification.fix_verification_id,
                "status": "FAILED",
                "reason_code": "FIXED_TEST_FAILED",
            },
            previous_digest=previous.digest,
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    completed = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=previous.digest,
    )
    resolved = reduce_event(session, completed)
    for terminal in (resolved, replace(resolved, state="ABANDONED")):
        later = _event(
            sequence=terminal.revision,
            event_type="investigation.started",
            request={},
            result={},
            previous_digest=terminal.event_head,
        )
        with pytest.raises(DiagnosticValidationError) as error:
            reduce_event(terminal, later)
        assert error.value.code == DIAGNOSTIC_INVALID_TRANSITION
