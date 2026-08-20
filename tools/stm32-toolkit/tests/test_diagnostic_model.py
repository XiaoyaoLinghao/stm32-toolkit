from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    EvidenceAssessment,
    EvidenceIdentity,
    Hypothesis,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    DiagnosticSession,
    DiagnosticValidationError,
    calculate_plan_digest,
    canonical_diagnostic_json_bytes,
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


def _step() -> ObservationStep:
    return ObservationStep(
        step_id="failed-state",
        selector={"kind": "run-state"},
        expected_value="failed",
        purpose="bind the original failed run",
    )


def _plan() -> ObservationPlan:
    step = _step()
    fields = {
        "diagnostic_session_id": "f" * 32,
        "created_revision": 3,
        "steps": [step.to_dict()],
    }
    digest = calculate_plan_digest(fields)
    return ObservationPlan(
        plan_id=digest,
        diagnostic_session_id=fields["diagnostic_session_id"],
        created_revision=fields["created_revision"],
        steps=(step,),
        digest=digest,
    )


def test_closed_models_round_trip_with_fresh_json_containers() -> None:
    step = _step()
    plan = _plan()
    result = ObservationResult(
        plan_id=plan.plan_id,
        step_id=step.step_id,
        evidence_id="1" * 64,
        selector=step.selector,
        observed_value="failed",
        expected_value="failed",
        matched=True,
    )
    assessment = EvidenceAssessment.new(
        hypothesis_id="2" * 32,
        plan_id=plan.plan_id,
        step_id=step.step_id,
        evidence_id=result.evidence_id,
        selector=step.selector,
        observed_value=result.observed_value,
        polarity="supports",
        rationale="the observed failed state supports this hypothesis",
    )
    hypothesis = Hypothesis(
        hypothesis_id=assessment.hypothesis_id,
        statement="the host test failed",
        status="open",
        confidence_basis="unrated",
        supporting=(assessment,),
        refuting=(),
    )
    session = DiagnosticSession(
        diagnostic_session_id="f" * 32,
        revision=4,
        state="INVESTIGATING",
        identity=IDENTITY,
        failed_test_run_id="run-1",
        failed_evidence_id="0" * 64,
        event_head="3" * 64,
        hypotheses=(hypothesis,),
        observation_plans=(plan,),
        observation_results=(result,),
    )

    encoded = session.to_dict()
    encoded["hypotheses"][0]["supporting"][0]["rationale"] = "changed copy"
    assert session.hypotheses[0].supporting[0].rationale != "changed copy"
    assert DiagnosticSession.from_value(session.to_dict()) == session
    assert canonical_diagnostic_json_bytes(session.to_dict()) == canonical_diagnostic_json_bytes(
        session.to_dict()
    )
    with pytest.raises(FrozenInstanceError):
        session.revision = 5  # type: ignore[misc]


def test_plan_and_assessment_hashes_bind_canonical_content() -> None:
    plan = _plan()
    assert plan.plan_id == plan.digest
    assert calculate_plan_digest(plan.to_dict()) == plan.digest
    assert plan.digest == sha256(
        canonical_diagnostic_json_bytes(
            {
                "created_revision": plan.created_revision,
                "diagnostic_session_id": plan.diagnostic_session_id,
                "steps": [step.to_dict() for step in plan.steps],
            }
        )
    ).hexdigest()


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "run-state", "extra": True},
        {"kind": "case-state"},
        {"kind": "case-count", "state": "unknown"},
    ],
)
def test_invalid_selectors_are_closed_and_stable(value: dict[str, object]) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        ObservationStep("step", value, "failed", "purpose")
    assert error.value.code in {DIAGNOSTIC_INVALID_EVENT, DIAGNOSTIC_LIMIT_EXCEEDED, "DIAGNOSTIC_PLAN_INVALID"}
    assert error.value.message == str(error.value)


def test_unknown_model_fields_and_tuple_json_are_rejected() -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        ObservationStep.from_value(
            {
                "step_id": "step",
                "selector": {"kind": "run-state"},
                "expected_value": "failed",
                "purpose": "purpose",
                "extra": 1,
            }
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    with pytest.raises(DiagnosticValidationError):
        canonical_diagnostic_json_bytes({"tuple": (1, 2)})
