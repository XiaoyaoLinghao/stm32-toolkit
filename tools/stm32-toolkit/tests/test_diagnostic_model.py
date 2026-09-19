from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity
from stm32_toolkit.monitor_analysis_contract import (
    NativeAnalysisContractError,
    evaluate_physical_monitor_fact,
)
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    DIAGNOSTIC_PLAN_INVALID,
    DiagnosticMarkerRef,
    EvidenceAssessment,
    Hypothesis,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    DiagnosticSession,
    DiagnosticValidationError,
    SourceChangeDeclaration,
    calculate_assessment_id,
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


def _fact_sample(
    *,
    selector_kind: str = "register",
    selector: str = "GPIOE.ODR",
    value: int = 0,
) -> dict[str, object]:
    width = 8 if selector_kind == "register" else 32
    watch = (
        {"kind": "register", "registerPath": selector}
        if selector_kind == "register"
        else {"kind": "variable", "expression": selector}
    )
    type_name = f"uint{width}_register" if selector_kind == "register" else "long unsigned int"
    return {
        "watch": watch,
        "status": "OK",
        "typedValue": {
            "bitWidth": width,
            "expression": selector,
            "rawHex": f"0x{value:0{width // 4}x}",
            "typeName": type_name,
            "value": value,
        },
        "code": None,
        "definition": {"kind": selector_kind, "selector": selector},
    }


def _fact_batch(sample: dict[str, object]) -> dict[str, object]:
    return {"values": [sample]}


def test_physical_monitor_fact_evaluator_is_strict_and_recomputable() -> None:
    variable_batches = [
        _fact_batch(_fact_sample(selector_kind="variable", selector="testtime", value=0)),
        _fact_batch(_fact_sample(selector_kind="variable", selector="testtime", value=1)),
    ]
    assert evaluate_physical_monitor_fact(
        variable_batches,
        selector_kind="variable",
        selector="testtime",
        fact="value-varies",
        minimum_valid_samples=2,
    ) == 1

    register_batches = [
        _fact_batch(_fact_sample(value=0)),
        _fact_batch(_fact_sample(value=1)),
    ]
    assert evaluate_physical_monitor_fact(
        register_batches,
        selector_kind="register",
        selector="GPIOE.ODR",
        fact="bit-values-mask",
        minimum_valid_samples=2,
        bit_index=0,
    ) == 3

    malformed = [
        {**_fact_sample(value=0), "typedValue": {**_fact_sample(value=0)["typedValue"], "value": True}},
        {**_fact_sample(value=0), "typedValue": {**_fact_sample(value=0)["typedValue"], "value": 0.0}},
        {**_fact_sample(value=0), "typedValue": {**_fact_sample(value=0)["typedValue"], "rawHex": "0X00"}},
        {**_fact_sample(value=0), "watch": {"kind": "register", "registerPath": "GPIOE.ODR", "extra": 1}},
    ]
    for sample in malformed:
        with pytest.raises(NativeAnalysisContractError):
            evaluate_physical_monitor_fact(
                [_fact_batch(sample)],
                selector_kind="register",
                selector="GPIOE.ODR",
                fact="bit-values-mask",
                minimum_valid_samples=1,
                bit_index=0,
            )

    duplicate = _fact_sample(value=0)
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            [{"values": [duplicate, _fact_sample(value=1)]}],
            selector_kind="register",
            selector="GPIOE.ODR",
            fact="bit-values-mask",
            minimum_valid_samples=1,
            bit_index=0,
        )
    malformed_duplicate = _fact_sample(value=1)
    malformed_duplicate["watch"] = {
        "kind": "register",
        "registerPath": "GPIOE.ODR",
        "unexpected": "field",
    }
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            [{"values": [duplicate, malformed_duplicate]}],
            selector_kind="register",
            selector="GPIOE.ODR",
            fact="bit-values-mask",
            minimum_valid_samples=1,
            bit_index=0,
        )
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            [_fact_batch(_fact_sample(selector="GPIOE.IDR", value=0))],
            selector_kind="register",
            selector="GPIOE.ODR",
            fact="bit-values-mask",
            minimum_valid_samples=1,
            bit_index=0,
        )
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            register_batches[:1],
            selector_kind="register",
            selector="GPIOE.ODR",
            fact="bit-values-mask",
            minimum_valid_samples=2,
            bit_index=0,
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


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("hypotheses", {}),
        ("observation_plans", "not-an-array"),
        ("observation_results", {}),
    ],
)
def test_session_decode_rejects_non_json_lifecycle_collections_without_materializing(
    field: str, replacement: object,
) -> None:
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
    candidate = session.to_dict()
    candidate[field] = replacement
    before = deepcopy(candidate)

    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession.from_value(candidate)

    assert error.value.code == DIAGNOSTIC_INVALID_EVENT
    assert candidate == before


def test_extended_open_session_requires_lifecycle_data_before_materializing() -> None:
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
    candidate = {
        **session.to_dict(),
        "source_change_declarations": [],
        "verification_plans": [],
        "diagnostic_marker_refs": [],
        "fix_verifications": [],
        "active_verification_plan_id": None,
    }
    before = deepcopy(candidate)

    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession.from_value(candidate)

    assert error.value.code == DIAGNOSTIC_INVALID_EVENT
    assert candidate == before


def test_extended_session_decode_rejects_non_array_lifecycle_collection() -> None:
    session = DiagnosticSession(
        diagnostic_session_id="f" * 32,
        revision=1,
        state="ABANDONED",
        identity=IDENTITY,
        failed_test_run_id="run-1",
        failed_evidence_id="0" * 64,
        event_head="3" * 64,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
    )
    candidate = {
        **session.to_dict(),
        "source_change_declarations": {},
        "verification_plans": [],
        "diagnostic_marker_refs": [],
        "fix_verifications": [],
        "active_verification_plan_id": None,
    }
    before = deepcopy(candidate)

    with pytest.raises(DiagnosticValidationError) as error:
        DiagnosticSession.from_value(candidate)

    assert error.value.code == DIAGNOSTIC_INVALID_EVENT
    assert candidate == before


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


_MODEL_INVALID_MESSAGE = "event/model/operation intent is invalid"
_MODEL_LIMIT_MESSAGE = "a diagnostic collection or byte limit is exceeded"
_MODEL_PLAN_MESSAGE = "selector, expected value, plan, or step reference is invalid"
_MISSING_CANDIDATE = object()


def _expect_model_failure(
    factory,
    expected_code: str,
    expected_message: str,
    candidate: object = _MISSING_CANDIDATE,
) -> None:
    before = deepcopy(candidate) if candidate is not _MISSING_CANDIDATE else _MISSING_CANDIDATE
    with pytest.raises(DiagnosticValidationError) as error:
        factory()
    assert error.value.code == expected_code
    assert error.value.message == expected_message
    assert str(error.value) == expected_message
    if candidate is not _MISSING_CANDIDATE:
        assert candidate == before


@pytest.mark.parametrize(
    "case_id",
    [
        "observation-purpose-nfc",
        "observation-purpose-control",
        "observation-wire-depth",
        "observation-wire-node-limit",
        "canonical-evidence-integer-limit",
        "canonical-evidence-invalid-value",
        "canonical-event-byte-limit",
        "selector-nonmapping",
        "selector-case-count-shape",
        "case-state-domain",
        "plan-step-type",
        "plan-fields-object-control",
        "plan-fields-nonmapping",
        "plan-fields-extra",
        "plan-fields-scalar-steps",
        "plan-fields-tuple-steps-control",
        "plan-wire-steps-type",
        "result-matched",
    ],
    ids=lambda case_id: case_id,
)
def test_public_observation_model_boundaries(case_id: str) -> None:
    if case_id == "observation-purpose-nfc":
        candidate = _step().to_dict()
        candidate["purpose"] = "e\u0301"
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "observation-purpose-control":
        candidate = _step().to_dict()
        candidate["purpose"] = "purpose\u0001"
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "observation-wire-depth":
        candidate = _step().to_dict()
        nested: object = "leaf"
        for _ in range(33):
            nested = [nested]
        candidate["purpose"] = nested
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
            candidate,
        )
        return
    if case_id == "observation-wire-node-limit":
        candidate = _step().to_dict()
        candidate["purpose"] = ["x"] * 100_000
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
            candidate,
        )
        return
    if case_id == "canonical-evidence-integer-limit":
        nearby = canonical_diagnostic_json_bytes(1 << 62)
        assert nearby
        _expect_model_failure(
            lambda: canonical_diagnostic_json_bytes(1 << 63),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
            1 << 63,
        )
        return
    if case_id == "canonical-evidence-invalid-value":
        control = {"value": 1}
        assert canonical_diagnostic_json_bytes(control)
        candidate = {"value": set()}
        _expect_model_failure(
            lambda: canonical_diagnostic_json_bytes(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "canonical-event-byte-limit":
        control = ["0123456789abcdef"] * 10
        assert canonical_diagnostic_json_bytes(control)
        candidate = ["0123456789abcdef"] * 90_000
        _expect_model_failure(
            lambda: canonical_diagnostic_json_bytes(candidate),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
            candidate,
        )
        return
    if case_id == "selector-nonmapping":
        candidate = _step().to_dict()
        candidate["selector"] = None
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "selector-case-count-shape":
        candidate = _step().to_dict()
        candidate["selector"] = {"kind": "case-count"}
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "case-state-domain":
        candidate = _step().to_dict()
        candidate["selector"] = {"kind": "case-state", "case_id": "case-1"}
        candidate["expected_value"] = "unknown"
        _expect_model_failure(
            lambda: ObservationStep.from_value(candidate),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
            candidate,
        )
        return
    if case_id == "plan-step-type":
        plan = _plan()
        invalid_steps = ({"not": "an ObservationStep"},)
        _expect_model_failure(
            lambda: ObservationPlan(
                plan.plan_id,
                plan.diagnostic_session_id,
                plan.created_revision,
                invalid_steps,
                plan.digest,
            ),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            invalid_steps,
        )
        return
    if case_id == "plan-fields-object-control":
        plan = _plan()
        before = plan.to_dict()
        assert calculate_plan_digest(plan) == plan.digest
        assert plan.to_dict() == before
        return
    if case_id == "plan-fields-nonmapping":
        candidate = "not-a-plan"
        _expect_model_failure(
            lambda: calculate_plan_digest(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "plan-fields-extra":
        candidate = _plan().to_dict()
        candidate.pop("plan_id")
        candidate.pop("digest")
        candidate["extra"] = True
        _expect_model_failure(
            lambda: calculate_plan_digest(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "plan-fields-scalar-steps":
        candidate = _plan().to_dict()
        candidate.pop("plan_id")
        candidate.pop("digest")
        candidate["steps"] = "not-a-sequence"
        _expect_model_failure(
            lambda: calculate_plan_digest(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "plan-fields-tuple-steps-control":
        steps = (_step(),)
        candidate = {
            "diagnostic_session_id": "f" * 32,
            "created_revision": 3,
            "steps": steps,
        }
        before = {
            "diagnostic_session_id": candidate["diagnostic_session_id"],
            "created_revision": candidate["created_revision"],
            "steps": tuple(step.to_dict() for step in steps),
        }
        assert calculate_plan_digest(candidate) == _plan().digest
        assert candidate["steps"] is steps
        assert candidate["steps"][0] is steps[0]
        assert candidate["diagnostic_session_id"] == before["diagnostic_session_id"]
        assert candidate["created_revision"] == before["created_revision"]
        assert tuple(step.to_dict() for step in candidate["steps"]) == before["steps"]
        return
    if case_id == "plan-wire-steps-type":
        candidate = _plan().to_dict()
        candidate["steps"] = "not-a-list"
        _expect_model_failure(
            lambda: ObservationPlan.from_value(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "result-matched":
        plan = _plan()
        step = plan.steps[0]
        candidate = ObservationResult(
            plan_id=plan.plan_id,
            step_id=step.step_id,
            evidence_id="0" * 64,
            selector=step.selector,
            observed_value="failed",
            expected_value="failed",
            matched=True,
        ).to_dict()
        candidate["matched"] = False
        _expect_model_failure(
            lambda: ObservationResult.from_value(candidate),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
            candidate,
        )
        return
    raise AssertionError(f"unhandled case: {case_id}")


def _assessment_for(
    *,
    hypothesis_id: str = "1" * 32,
    polarity: str = "supports",
    rationale: str = "the observed failed state supports this hypothesis",
) -> EvidenceAssessment:
    step = _step()
    return EvidenceAssessment.new(
        hypothesis_id=hypothesis_id,
        plan_id=_plan().plan_id,
        step_id=step.step_id,
        evidence_id="0" * 64,
        selector=step.selector,
        observed_value="failed",
        polarity=polarity,
        rationale=rationale,
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "assessment-object-control",
        "assessment-nonmapping",
        "assessment-extra",
        "assessment-polarity",
        "hypothesis-state",
        "hypothesis-collections",
        "hypothesis-member-type",
        "hypothesis-foreign-assessment",
        "hypothesis-duplicate-assessment",
        "hypothesis-overlap",
    ],
    ids=lambda case_id: case_id,
)
def test_public_hypothesis_assessment_boundaries(case_id: str) -> None:
    if case_id == "assessment-object-control":
        assessment = _assessment_for()
        assert calculate_assessment_id(assessment) == assessment.assessment_id
        return
    if case_id == "assessment-nonmapping":
        candidate = "not-an-assessment"
        _expect_model_failure(
            lambda: calculate_assessment_id(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "assessment-extra":
        candidate = _assessment_for().to_dict()
        candidate["extra"] = True
        _expect_model_failure(
            lambda: calculate_assessment_id(candidate),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            candidate,
        )
        return
    if case_id == "assessment-polarity":
        _expect_model_failure(
            lambda: EvidenceAssessment.new(
                hypothesis_id="1" * 32,
                plan_id=_plan().plan_id,
                step_id=_step().step_id,
                evidence_id="0" * 64,
                selector=_step().selector,
                observed_value="failed",
                polarity="neutral",
                rationale="invalid polarity",
            ),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "hypothesis-state":
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "closed", "unrated", (), ()),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "hypothesis-collections":
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "open", "unrated", [], ()),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "hypothesis-member-type":
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "open", "unrated", (object(),), ()),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "hypothesis-foreign-assessment":
        assessment = _assessment_for(hypothesis_id="2" * 32)
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "open", "unrated", (assessment,), ()),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "hypothesis-duplicate-assessment":
        assessment = _assessment_for()
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "open", "unrated", (assessment, assessment), ()),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "hypothesis-overlap":
        supporting = _assessment_for(polarity="supports")
        refuting = _assessment_for(
            polarity="refutes",
            rationale="the observed failed state refutes this hypothesis",
        )
        assert supporting.assessment_id != refuting.assessment_id
        _expect_model_failure(
            lambda: Hypothesis("1" * 32, "statement", "open", "unrated", (supporting,), (refuting,)),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    raise AssertionError(f"unhandled case: {case_id}")


_SESSION_ARTIFACT = ArtifactRef(
    sha256="7" * 64,
    size_bytes=17,
    relative_path="changes.diff",
    kind="source-diff",
    media_type="text/x-diff",
)


def _session_source(
    *,
    claimed_hypothesis_ids: tuple[str, ...] = ("1" * 32,),
    validation_plan_id: str = "0" * 64,
) -> SourceChangeDeclaration:
    return SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=("src/main.c",),
        diff_evidence_id="e" * 64,
        diff_artifact=_SESSION_ARTIFACT,
        claimed_hypothesis_ids=claimed_hypothesis_ids,
        validation_plan_id=validation_plan_id,
    )


def _session_components() -> tuple[Hypothesis, ObservationPlan, ObservationResult]:
    plan = _plan()
    step = plan.steps[0]
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
        hypothesis_id="1" * 32,
        plan_id=plan.plan_id,
        step_id=step.step_id,
        evidence_id=result.evidence_id,
        selector=step.selector,
        observed_value=result.observed_value,
        polarity="supports",
        rationale="the observed failed state supports this hypothesis",
    )
    hypothesis = Hypothesis(
        "1" * 32,
        "the host test failed",
        "open",
        "unrated",
        (assessment,),
        (),
    )
    return hypothesis, plan, result


def _session_kwargs() -> dict[str, object]:
    hypothesis, plan, result = _session_components()
    return {
        "diagnostic_session_id": "f" * 32,
        "revision": 4,
        "state": "INVESTIGATING",
        "identity": IDENTITY,
        "failed_test_run_id": "run-1",
        "failed_evidence_id": "0" * 64,
        "event_head": "3" * 64,
        "hypotheses": (hypothesis,),
        "observation_plans": (plan,),
        "observation_results": (result,),
    }


def _session_plan_for_other_session() -> ObservationPlan:
    step = _step()
    fields = {
        "diagnostic_session_id": "e" * 32,
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


def _session_marker_for_other_session() -> DiagnosticMarkerRef:
    return DiagnosticMarkerRef.new(
        marker_id="0" * 64,
        marker_evidence_id="f" * 64,
        analysis_id="1" * 64,
        analysis_evidence_id="2" * 64,
        diagnostic_session_id="e" * 32,
        hypothesis_id="2" * 32,
        polarity="supports",
        label="change-observed",
        rationale="the marker belongs to another valid session",
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "session-run-id",
        "session-revision-type",
        "session-state",
        "session-run-mode",
        "session-identity-type",
        "session-legacy-collections",
        "session-result-limit",
        "session-hypothesis-member",
        "session-plan-member",
        "session-result-member",
        "session-duplicate-hypothesis",
        "session-duplicate-plan",
        "session-plan-session-binding",
        "session-result-reference",
        "session-duplicate-result",
        "session-assessment-result-binding",
        "session-extended-collection-type",
        "session-extended-limit",
        "session-duplicate-extended",
        "session-declaration-foreign-hypothesis",
        "session-marker-binding",
        "session-wire-nonmapping",
    ],
    ids=lambda case_id: case_id,
)
def test_public_session_lifecycle_boundaries(case_id: str) -> None:
    if case_id == "session-run-id":
        kwargs = _session_kwargs()
        kwargs["failed_test_run_id"] = "Invalid Run ID"
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-revision-type":
        kwargs = _session_kwargs()
        kwargs["revision"] = True
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-state":
        kwargs = _session_kwargs()
        kwargs["state"] = "UNKNOWN"
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-run-mode":
        kwargs = _session_kwargs()
        kwargs["failed_run_mode"] = "invalid"
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-identity-type":
        kwargs = _session_kwargs()
        kwargs["identity"] = {}
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-legacy-collections":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = []
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-result-limit":
        kwargs = _session_kwargs()
        result = kwargs["observation_results"][0]
        kwargs["observation_results"] = (result,) * 4097
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
        )
        return
    if case_id == "session-hypothesis-member":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = (object(),)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-plan-member":
        kwargs = _session_kwargs()
        kwargs["observation_plans"] = (object(),)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-result-member":
        kwargs = _session_kwargs()
        kwargs["observation_results"] = (object(),)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-duplicate-hypothesis":
        hypothesis, _, _ = _session_components()
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = (hypothesis, hypothesis)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-duplicate-plan":
        _, plan, _ = _session_components()
        kwargs = _session_kwargs()
        kwargs["observation_plans"] = (plan, plan)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-plan-session-binding":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = (_session_plan_for_other_session(),)
        kwargs["observation_results"] = ()
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-result-reference":
        plan = _plan()
        step = plan.steps[0]
        result = ObservationResult(
            plan_id=plan.plan_id,
            step_id="missing-step",
            evidence_id="0" * 64,
            selector=step.selector,
            observed_value="failed",
            expected_value="failed",
            matched=True,
        )
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = (plan,)
        kwargs["observation_results"] = (result,)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-duplicate-result":
        _, plan, result = _session_components()
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = (plan,)
        kwargs["observation_results"] = (result, result)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-assessment-result-binding":
        hypothesis, plan, _ = _session_components()
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = (hypothesis,)
        kwargs["observation_plans"] = (plan,)
        kwargs["observation_results"] = ()
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-extended-collection-type":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = ()
        kwargs["observation_results"] = ()
        kwargs["source_change_declarations"] = [_session_source()]
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
        )
        return
    if case_id == "session-extended-limit":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = ()
        kwargs["observation_results"] = ()
        source = _session_source()
        kwargs["source_change_declarations"] = (source,) * 65
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_LIMIT_EXCEEDED,
            _MODEL_LIMIT_MESSAGE,
        )
        return
    if case_id == "session-duplicate-extended":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = ()
        kwargs["observation_results"] = ()
        source = _session_source()
        kwargs["source_change_declarations"] = (source, source)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-declaration-foreign-hypothesis":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = ()
        kwargs["observation_results"] = ()
        kwargs["source_change_declarations"] = (_session_source(claimed_hypothesis_ids=("2" * 32,)),)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-marker-binding":
        kwargs = _session_kwargs()
        kwargs["hypotheses"] = ()
        kwargs["observation_plans"] = ()
        kwargs["observation_results"] = ()
        kwargs["diagnostic_marker_refs"] = (_session_marker_for_other_session(),)
        _expect_model_failure(
            lambda: DiagnosticSession(**kwargs),
            DIAGNOSTIC_PLAN_INVALID,
            _MODEL_PLAN_MESSAGE,
        )
        return
    if case_id == "session-wire-nonmapping":
        _expect_model_failure(
            lambda: DiagnosticSession.from_value("not-a-session"),
            DIAGNOSTIC_INVALID_EVENT,
            _MODEL_INVALID_MESSAGE,
            "not-a-session",
        )
        return
    raise AssertionError(f"unhandled case: {case_id}")
