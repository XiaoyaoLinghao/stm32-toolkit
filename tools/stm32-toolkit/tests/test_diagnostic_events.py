from __future__ import annotations

import pytest

from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticValidationError,
    calculate_event_digest,
    calculate_assessment_id,
    calculate_plan_digest,
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


def _canonical_payloads() -> list[tuple[str, dict[str, object], dict[str, object]]]:
    step = {
        "step_id": "failed-state",
        "selector": {"kind": "run-state"},
        "expected_value": "failed",
        "purpose": "observe the failed run",
    }
    plan_fields = {"diagnostic_session_id": SID, "created_revision": 3, "steps": [step]}
    plan_id = calculate_plan_digest(plan_fields)
    hypothesis_id = "2" * 32
    assessment_content = {
        "hypothesis_id": hypothesis_id,
        "plan_id": plan_id,
        "step_id": "failed-state",
        "evidence_id": "0" * 64,
        "selector": {"kind": "run-state"},
        "observed_value": "failed",
        "polarity": "supports",
        "rationale": "supports",
    }
    return [
        (
            "session.created",
            {"failed_test_run_id": "run-1"},
            {"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
        ),
        ("investigation.started", {}, {}),
        (
            "hypothesis.added",
            {"statement": "the host test failed"},
            {
                "hypothesis": {
                    "hypothesis_id": hypothesis_id,
                    "statement": "the host test failed",
                    "status": "open",
                    "confidence_basis": "unrated",
                    "supporting": [],
                    "refuting": [],
                }
            },
        ),
        (
            "observation.plan_added",
            {"steps": [step]},
            {"observation_plan": {**plan_fields, "plan_id": plan_id, "digest": plan_id}},
        ),
        (
            "observation.plan_executed",
            {"plan_id": plan_id},
            {
                "observation_results": [
                    {
                        "plan_id": plan_id,
                        "step_id": "failed-state",
                        "evidence_id": "0" * 64,
                        "selector": {"kind": "run-state"},
                        "observed_value": "failed",
                        "expected_value": "failed",
                        "matched": True,
                    }
                ]
            },
        ),
        (
            "hypothesis.assessed",
            {
                "hypothesis_id": hypothesis_id,
                "plan_id": plan_id,
                "step_id": "failed-state",
                "polarity": "supports",
                "rationale": "supports",
            },
            {"assessment": {"assessment_id": calculate_assessment_id(assessment_content), **assessment_content}},
        ),
    ]


def _session_with_plan() -> tuple[DiagnosticSession, str, dict[str, object], DiagnosticEvent]:
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
    plan_fields = {"diagnostic_session_id": SID, "created_revision": 3, "steps": [step]}
    plan_id = calculate_plan_digest(plan_fields)
    plan_event = _event(
        sequence=2,
        event_type="observation.plan_added",
        request={"steps": [step]},
        result={"observation_plan": {**plan_fields, "plan_id": plan_id, "digest": plan_id}},
        previous_digest=started.digest,
    )
    return reduce_event(session, plan_event), plan_id, step, plan_event


def _session_with_executed_plan() -> tuple[DiagnosticSession, str, dict[str, object], DiagnosticEvent]:
    session, plan_id, step, plan_event = _session_with_plan()
    execute = _event(
        sequence=3,
        event_type="observation.plan_executed",
        request={"plan_id": plan_id},
        result={
            "observation_results": [
                {
                    "plan_id": plan_id,
                    "step_id": "failed-state",
                    "evidence_id": "0" * 64,
                    "selector": {"kind": "run-state"},
                    "observed_value": "failed",
                    "expected_value": "failed",
                    "matched": True,
                }
            ]
        },
        previous_digest=plan_event.digest,
    )
    return reduce_event(session, execute), plan_id, step, execute


def test_session_created_and_investigation_started_reduce_revisions() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    assert created.digest == "8dad9ef72887e1de571e91fa8f13d1d9910fb6b74c88158eedef483875a8c432"
    assert created.digest == calculate_event_digest(created.to_dict())
    session = reduce_event(None, created)
    assert session.to_dict() == {
        "diagnostic_session_id": SID,
        "revision": 1,
        "state": "OPEN",
        "identity": IDENTITY.to_dict(),
        "failed_test_run_id": "run-1",
        "failed_evidence_id": "0" * 64,
        "event_head": created.digest,
        "hypotheses": [],
        "observation_plans": [],
        "observation_results": [],
    }
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


def test_target_session_created_and_investigation_started_preserve_mode() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "vs03-failed-before", "failed_run_mode": "target"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    session = reduce_event(None, created)
    assert session.failed_run_mode == "target"
    assert session.to_dict()["failed_run_mode"] == "target"

    started = _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
    )
    session = reduce_event(session, started)
    assert session.failed_run_mode == "target"


@pytest.mark.parametrize(
    "event_request",
    [
        {"failed_test_run_id": "run-1", "failed_run_mode": "host"},
        {"failed_test_run_id": "run-1", "failed_run_mode": "unknown"},
        {"failed_test_run_id": "run-1", "failed_run_mode": None},
        {"failed_run_mode": "target"},
        {"failed_test_run_id": "run-1", "failed_run_mode": "target", "extra": True},
    ],
)
def test_session_created_rejects_non_target_or_non_exact_mode_requests(event_request: dict[str, object]) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        _event(
            sequence=0,
            event_type="session.created",
            request=event_request,
            result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT


@pytest.mark.parametrize("event_type,event_request,event_result", _canonical_payloads())
def test_all_event_payloads_are_closed_and_event_round_trip_is_canonical(
    event_type: str, event_request: dict[str, object], event_result: dict[str, object]
) -> None:
    event = _event(sequence=0, event_type=event_type, request=event_request, result=event_result)
    assert DiagnosticEvent.from_value(event.to_dict()) == event
    bad_top_level = {**event.to_dict(), "unknown": True}
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticEvent.from_value(bad_top_level)
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT
    for side in ("request", "result"):
        changed = event.to_dict()
        changed_payload = dict(changed["payload"])
        changed_side = dict(changed_payload[side])
        changed_side["unknown"] = True
        changed_payload[side] = changed_side
        changed["payload"] = changed_payload
        with pytest.raises(DiagnosticValidationError) as error:
            DiagnosticEvent.from_value(changed)
        assert error.value.code == DIAGNOSTIC_INVALID_EVENT


def test_changed_digest_and_previous_link_fail_with_invalid_event() -> None:
    created = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    )
    changed = created.to_dict()
    changed["digest"] = ("a" if created.digest[0] != "a" else "b") * 64
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticEvent.from_value(changed)
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    session = reduce_event(None, created)
    bad_link = _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest="0" * 64,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, bad_link)
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT


def test_plan_and_assessment_digest_corruption_is_rejected_with_plan_invalid() -> None:
    cases = (_canonical_payloads()[3], _canonical_payloads()[5])
    for event_type, request, result in cases:
        corrupted = dict(result)
        if event_type == "observation.plan_added":
            plan = dict(corrupted["observation_plan"])
            plan["digest"] = ("a" if plan["digest"][0] != "a" else "b") * 64
            corrupted["observation_plan"] = plan
        else:
            assessment = dict(corrupted["assessment"])
            assessment["assessment_id"] = ("a" if assessment["assessment_id"][0] != "a" else "b") * 64
            corrupted["assessment"] = assessment
        with pytest.raises(DiagnosticValidationError) as error:
            _event(sequence=0, event_type=event_type, request=request, result=corrupted)
        assert error.value.code == DIAGNOSTIC_PLAN_INVALID


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


@pytest.mark.parametrize("mode", ["missing-plan", "missing-step", "cross-linked"])
def test_plan_execution_rejects_missing_or_cross_linked_results(mode: str) -> None:
    session, plan_id, step, plan_event = _session_with_plan()
    if mode == "missing-plan":
        request_plan_id = "1" * 64
        results: list[dict[str, object]] = []
    else:
        request_plan_id = plan_id
        result_selector = {"kind": "run-state"} if mode == "missing-step" else {
            "kind": "case-state",
            "case_id": "other-case",
        }
        results = [
            {
                "plan_id": plan_id,
                "step_id": "other-step" if mode == "missing-step" else step["step_id"],
                "evidence_id": "0" * 64,
                "selector": result_selector,
                "observed_value": "failed",
                "expected_value": "failed",
                "matched": True,
            }
        ]
    event = _event(
        sequence=session.revision,
        event_type="observation.plan_executed",
        request={"plan_id": request_plan_id},
        result={"observation_results": results},
        previous_digest=plan_event.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


def test_plan_execution_rejects_evidence_unrelated_to_failed_test_run() -> None:
    session, plan_id, step, plan_event = _session_with_plan()
    event = _event(
        sequence=session.revision,
        event_type="observation.plan_executed",
        request={"plan_id": plan_id},
        result={
            "observation_results": [
                {
                    "plan_id": plan_id,
                    "step_id": step["step_id"],
                    "evidence_id": "1" * 64,
                    "selector": step["selector"],
                    "observed_value": "failed",
                    "expected_value": "failed",
                    "matched": True,
                }
            ]
        },
        previous_digest=plan_event.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


def test_reducer_rejects_missing_hypothesis_and_duplicate_hypothesis_id() -> None:
    session, plan_id, step, execute = _session_with_executed_plan()
    content = {
        "hypothesis_id": "3" * 32,
        "plan_id": plan_id,
        "step_id": step["step_id"],
        "evidence_id": "0" * 64,
        "selector": step["selector"],
        "observed_value": "failed",
        "polarity": "supports",
        "rationale": "supports",
    }
    assessment = {"assessment_id": calculate_assessment_id(content), **content}
    missing = _event(
        sequence=session.revision,
        event_type="hypothesis.assessed",
        request={k: content[k] for k in ("hypothesis_id", "plan_id", "step_id", "polarity", "rationale")},
        result={"assessment": assessment},
        previous_digest=execute.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, missing)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID

    # The duplicate check is exercised against a session that already contains the ID.
    investigated = reduce_event(None, _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": "0" * 64, "identity": IDENTITY.to_dict()},
    ))
    investigated = reduce_event(investigated, _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=investigated.event_head,
    ))
    add = _event(
        sequence=2,
        event_type="hypothesis.added",
        request={"statement": "same"},
        result={
            "hypothesis": {
                "hypothesis_id": "4" * 32,
                "statement": "same",
                "status": "open",
                "confidence_basis": "unrated",
                "supporting": [],
                "refuting": [],
            }
        },
        previous_digest=investigated.event_head,
    )
    first = reduce_event(investigated, add)
    duplicate = _event(
        sequence=first.revision,
        event_type="hypothesis.added",
        request={"statement": "same"},
        result=add.to_dict()["payload"]["result"],
        previous_digest=first.event_head,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(first, duplicate)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


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
                    "evidence_id": "0" * 64,
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
        "evidence_id": "0" * 64,
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
