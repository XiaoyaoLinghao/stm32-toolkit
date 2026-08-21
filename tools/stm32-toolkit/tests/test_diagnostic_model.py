from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    DIAGNOSTIC_PLAN_INVALID,
    EvidenceAssessment,
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


def test_failed_run_mode_is_omitted_for_host_and_round_trips_for_target() -> None:
    host = DiagnosticSession(
        diagnostic_session_id="f" * 32,
        revision=1,
        state="OPEN",
        identity=IDENTITY,
        failed_test_run_id="run-1",
        failed_evidence_id="0" * 64,
        event_head="3" * 64,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
    )
    host_wire = host.to_dict()
    assert "failed_run_mode" not in host_wire
    assert DiagnosticSession.from_value(host_wire) == host

    target = replace(host, failed_run_mode="target")
    assert target.to_dict() == {**host_wire, "failed_run_mode": "target"}
    assert DiagnosticSession.from_value(target.to_dict()) == target


@pytest.mark.parametrize("value", ["host", "unknown", 1, None])
def test_explicit_failed_run_mode_wire_values_are_rejected(value: object) -> None:
    session = DiagnosticSession(
        diagnostic_session_id="f" * 32,
        revision=1,
        state="OPEN",
        identity=IDENTITY,
        failed_test_run_id="run-1",
        failed_evidence_id="0" * 64,
        event_head="3" * 64,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
    )
    wire = {**session.to_dict(), "failed_run_mode": value}
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession.from_value(wire)
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT


def test_closed_models_round_trip_with_fresh_json_containers() -> None:
    step = _step()
    plan = _plan()
    result = ObservationResult(
        plan_id=plan.plan_id,
        step_id=step.step_id,
        evidence_id="0" * 64,
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


def test_materialized_session_rejects_observation_evidence_not_from_failed_run() -> None:
    plan = _plan()
    result = ObservationResult(
        plan_id=plan.plan_id,
        step_id=plan.steps[0].step_id,
        evidence_id="1" * 64,
        selector=plan.steps[0].selector,
        observed_value="failed",
        expected_value="failed",
        matched=True,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession(
            diagnostic_session_id=plan.diagnostic_session_id,
            revision=4,
            state="INVESTIGATING",
            identity=IDENTITY,
            failed_test_run_id="run-1",
            failed_evidence_id="0" * 64,
            event_head="3" * 64,
            hypotheses=(),
            observation_plans=(plan,),
            observation_results=(result,),
        )
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


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
    "value,expected_code",
    [
        ({"kind": "run-state", "extra": True}, DIAGNOSTIC_INVALID_EVENT),
        ({"kind": "case-state"}, DIAGNOSTIC_INVALID_EVENT),
        ({"kind": "case-count", "state": "unknown"}, DIAGNOSTIC_PLAN_INVALID),
    ],
)
def test_invalid_selectors_are_closed_and_stable(value: dict[str, object], expected_code: str) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        ObservationStep("step", value, "failed", "purpose")
    assert error.value.code == expected_code
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


@pytest.mark.parametrize(
    "factory,expected_code",
    [
        (
            lambda: DiagnosticSession(
                "g" * 32,
                1,
                "OPEN",
                IDENTITY,
                "run-1",
                "0" * 64,
                "1" * 64,
                (),
                (),
                (),
            ),
            DIAGNOSTIC_INVALID_EVENT,
        ),
        (lambda: ObservationStep("BAD", {"kind": "run-state"}, "failed", "purpose"), DIAGNOSTIC_INVALID_EVENT),
        (lambda: Hypothesis("g" * 32, "statement", "open", "unrated", (), ()), DIAGNOSTIC_INVALID_EVENT),
        (
            lambda: ObservationPlan("g" * 64, "f" * 32, 1, (_step(),), "g" * 64),
            DIAGNOSTIC_INVALID_EVENT,
        ),
    ],
)
def test_invalid_ids_fail_with_exact_codes(factory, expected_code: str) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        factory()
    assert error.value.code == expected_code


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ObservationStep("step", {"kind": "run-state"}, "failed", "x" * (64 * 1024 + 1)),
        lambda: Hypothesis("1" * 32, "x" * (64 * 1024 + 1), "open", "unrated", (), ()),
        lambda: EvidenceAssessment.new(
            hypothesis_id="1" * 32,
            plan_id="2" * 64,
            step_id="step",
            evidence_id="3" * 64,
            selector={"kind": "run-state"},
            observed_value="failed",
            polarity="supports",
            rationale="x" * (64 * 1024 + 1),
        ),
    ],
)
def test_statement_and_purpose_byte_bounds_are_fixed(factory) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        factory()
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED


def test_plan_and_assessment_collection_bounds_are_fixed() -> None:
    steps = tuple(
        ObservationStep(f"step-{index}", {"kind": "run-state"}, "failed", "purpose")
        for index in range(65)
    )
    with pytest.raises(DiagnosticValidationError) as error:
        ObservationPlan("0" * 64, "f" * 32, 1, steps, "0" * 64)
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED

    assessment = EvidenceAssessment.new(
        hypothesis_id="1" * 32,
        plan_id="2" * 64,
        step_id="step",
        evidence_id="3" * 64,
        selector={"kind": "run-state"},
        observed_value="failed",
        polarity="supports",
        rationale="rationale",
    )
    with pytest.raises(DiagnosticValidationError) as error:
        Hypothesis("1" * 32, "statement", "open", "unrated", (assessment,) * 1025, ())
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED

    hypotheses = tuple(Hypothesis(f"{index:032x}", "statement", "open", "unrated", (), ()) for index in range(257))
    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession(
            "f" * 32,
            1,
            "INVESTIGATING",
            IDENTITY,
            "run-1",
            "0" * 64,
            "3" * 64,
            hypotheses,
            (),
            (),
        )
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED
