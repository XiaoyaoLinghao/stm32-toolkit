from __future__ import annotations

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticValidationError,
    EvidenceIdentity,
    calculate_event_digest,
    create_event,
    reduce_event,
)


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


def test_session_created_and_investigation_started_reduce_revisions() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    assert created.digest == calculate_event_digest(created.to_dict())
    session = reduce_event(None, created)
    assert session.revision == 1
    assert session.state == "OPEN"
    assert session.event_head == created.digest

    started = _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
    )
    session = reduce_event(session, started)
    assert session.revision == 2
    assert session.state == "INVESTIGATING"
    assert session.event_head == started.digest


def test_all_event_payloads_are_closed_and_event_round_trip_is_canonical() -> None:
    event = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    assert DiagnosticEvent.from_value(event.to_dict()) == event
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticEvent.from_value({**event.to_dict(), "unknown": True})
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT


def test_event_sequence_and_transition_links_fail_closed() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    session = reduce_event(None, created)

    bad_sequence = _event(
        sequence=2,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, bad_sequence)
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    bad_transition = _event(
        sequence=1,
        event_type="hypothesis.added",
        request={"statement": "not yet"},
        result={
            "hypothesis": {
                "hypothesis_id": "1" * 32,
                "statement": "not yet",
                "status": "open",
                "confidence_basis": "unrated",
                "supporting": [],
                "refuting": [],
            }
        },
        previous_digest=created.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, bad_transition)
    assert error.value.code == DIAGNOSTIC_INVALID_TRANSITION


def test_plan_result_digest_and_opposite_polarity_are_checked_by_reducer() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    session = reduce_event(None, created)
    started = _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
    )
    session = reduce_event(session, started)
    step = {
        "step_id": "failed-state",
        "selector": {"kind": "run-state"},
        "expected_value": "failed",
        "purpose": "observe the failed run",
    }
    from stm32_toolkit.diagnostics import calculate_plan_digest

    plan_fields = {"diagnostic_session_id": SID, "created_revision": 3, "steps": [step]}
    digest = calculate_plan_digest(plan_fields)
    plan_event = _event(
        sequence=2,
        event_type="observation.plan_added",
        request={"steps": [step]},
        result={
            "observation_plan": {
                **plan_fields,
                "plan_id": digest,
                "digest": digest,
            }
        },
        previous_digest=started.digest,
    )
    session = reduce_event(session, plan_event)
    execute = _event(
        sequence=3,
        event_type="observation.plan_executed",
        request={"plan_id": digest},
        result={
            "observation_results": [
                {
                    "plan_id": digest,
                    "step_id": "failed-state",
                    "evidence_id": "1" * 64,
                    "selector": {"kind": "run-state"},
                    "observed_value": "failed",
                    "expected_value": "failed",
                    "matched": True,
                }
            ]
        },
        previous_digest=plan_event.digest,
    )
    session = reduce_event(session, execute)
    hypothesis = {
        "hypothesis_id": "2" * 32,
        "statement": "the host test failed",
        "status": "open",
        "confidence_basis": "unrated",
        "supporting": [],
        "refuting": [],
    }
    add_hypothesis = _event(
        sequence=4,
        event_type="hypothesis.added",
        request={"statement": hypothesis["statement"]},
        result={"hypothesis": hypothesis},
        previous_digest=execute.digest,
    )
    session = reduce_event(session, add_hypothesis)
    assessment_content = {
        "hypothesis_id": hypothesis["hypothesis_id"],
        "plan_id": digest,
        "step_id": "failed-state",
        "evidence_id": "1" * 64,
        "selector": {"kind": "run-state"},
        "observed_value": "failed",
        "polarity": "supports",
        "rationale": "supports",
    }
    from stm32_toolkit.diagnostics import calculate_assessment_id

    assessment = {
        "assessment_id": calculate_assessment_id(assessment_content),
        **assessment_content,
    }
    assessed = _event(
        sequence=5,
        event_type="hypothesis.assessed",
        request={k: assessment_content[k] for k in ("hypothesis_id", "plan_id", "step_id", "polarity", "rationale")},
        result={"assessment": assessment},
        previous_digest=add_hypothesis.digest,
    )
    session = reduce_event(session, assessed)
    assert len(session.hypotheses[0].supporting) == 1

    opposite_content = {**assessment_content, "polarity": "refutes", "rationale": "refutes"}
    opposite = {
        "assessment_id": calculate_assessment_id(opposite_content),
        **opposite_content,
    }
    opposite_event = _event(
        sequence=6,
        event_type="hypothesis.assessed",
        request={k: opposite_content[k] for k in ("hypothesis_id", "plan_id", "step_id", "polarity", "rationale")},
        result={"assessment": opposite},
        previous_digest=assessed.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, opposite_event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID
