from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    DiagnosticMarkerRef,
    DiagnosticValidationError,
    FixVerification,
    SourceChangeDeclaration,
    VerificationPlan,
    calculate_fix_verification_id,
    calculate_source_change_declaration_id,
    calculate_verification_plan_digest,
    canonical_diagnostic_json_bytes,
)
from stm32_toolkit.evidence import ArtifactRef


SESSION_ID = "a" * 32
HYPOTHESIS_IDS = ("1" * 32, "2" * 32)
ANALYSIS_IDS = ("3" * 64, "4" * 64)
ANALYSIS_EVIDENCE_IDS = ("5" * 64, "6" * 64)
PLAN_ID = "0" * 64
ARTIFACT = ArtifactRef(
    sha256="7" * 64,
    size_bytes=17,
    relative_path="changes.diff",
    kind="source-diff",
    media_type="text/x-diff",
)


def _source(validation_plan_id: str = PLAN_ID) -> SourceChangeDeclaration:
    return SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=("src/main.c", "src/monitor.c"),
        diff_evidence_id="e" * 64,
        diff_artifact=ARTIFACT,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id=validation_plan_id,
    )


def _plan(
    source: SourceChangeDeclaration | None = None,
    verification_plan_id: str = PLAN_ID,
    continuation_evidence_id: str | None = None,
) -> VerificationPlan:
    declaration = _source(verification_plan_id) if source is None else source
    return VerificationPlan.new(
        verification_plan_id=verification_plan_id,
        diagnostic_session_id=SESSION_ID,
        failed_before_run_id="failed-before",
        failed_before_evidence_id="1" * 64,
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="fixed-after",
        fixed_after_evidence_id="2" * 64,
        required_analysis_ids=ANALYSIS_IDS,
        required_analysis_evidence_ids=ANALYSIS_EVIDENCE_IDS,
        required_monitor_quality="VALID",
        expected_changed=True,
        continuation_evidence_id=continuation_evidence_id,
    )


def _marker(plan: VerificationPlan | None = None) -> DiagnosticMarkerRef:
    _ = plan
    return DiagnosticMarkerRef.new(
        marker_id="0" * 64,
        marker_evidence_id="f" * 64,
        analysis_id=ANALYSIS_IDS[0],
        analysis_evidence_id=ANALYSIS_EVIDENCE_IDS[0],
        diagnostic_session_id=SESSION_ID,
        hypothesis_id=HYPOTHESIS_IDS[0],
        polarity="supports",
        label="change-observed",
        rationale="the fixed replay changed the selected monitor value",
    )


def _fix(
    source: SourceChangeDeclaration | None = None,
    verification_plan_id: str = PLAN_ID,
) -> FixVerification:
    plan = _plan(source, verification_plan_id)
    return FixVerification.new(
        diagnostic_session_id=SESSION_ID,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        verification_plan_id=plan.verification_plan_id,
        verification_plan_digest=plan.plan_digest,
        analysis_ids=plan.required_analysis_ids,
        analysis_evidence_ids=plan.required_analysis_evidence_ids,
        executed_operation_ids=("verification.start", "verification.complete"),
        status="PASSED",
        reason_code="VERIFICATION_PASSED",
        completed_at_utc="2026-08-21T12:34:56.000000Z",
    )


def _expect_invalid(factory, expected_code: str = DIAGNOSTIC_INVALID_EVENT) -> None:
    with pytest.raises(DiagnosticValidationError) as error:
        factory()
    assert error.value.code == expected_code


def test_new_round_trip_fresh_containers_frozen_and_artifact_snapshot() -> None:
    source = _source()
    plan = _plan(source)
    marker = _marker(plan)
    verification = _fix(source)

    for value, cls in (
        (source, SourceChangeDeclaration),
        (plan, VerificationPlan),
        (marker, DiagnosticMarkerRef),
        (verification, FixVerification),
    ):
        encoded = value.to_dict()
        assert cls.from_value(encoded) == value
        assert encoded is not value.to_dict()
        with pytest.raises(FrozenInstanceError):
            value.schema = "tampered"  # type: ignore[misc]

    encoded = source.to_dict()
    encoded["changed_paths"].append("src/other.c")
    encoded["diff_artifact"]["relative_path"] = "changed.diff"
    assert source.changed_paths == ("src/main.c", "src/monitor.c")
    assert source.diff_artifact.relative_path == "changes.diff"
    assert source.diff_artifact is not ARTIFACT
    assert type(source.diff_artifact) is ArtifactRef


def test_artifact_subclass_is_rejected_without_provider_exception_leak() -> None:
    class ExplodingArtifactRef(ArtifactRef):
        def to_dict(self) -> dict[str, object]:
            raise RuntimeError("provider-controlled failure")

    malicious = ExplodingArtifactRef(
        sha256=ARTIFACT.sha256,
        size_bytes=ARTIFACT.size_bytes,
        relative_path=ARTIFACT.relative_path,
        kind=ARTIFACT.kind,
        media_type=ARTIFACT.media_type,
    )
    _expect_invalid(lambda: SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=("src/main.c", "src/monitor.c"),
        diff_evidence_id="e" * 64,
        diff_artifact=malicious,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id=PLAN_ID,
    ))

    wire = _source().to_dict()
    wire["diff_artifact"] = malicious
    _expect_invalid(lambda: SourceChangeDeclaration.from_value(wire))


def test_source_plan_fix_bind_without_digest_fixed_point() -> None:
    plan_id = "e" * 64
    source = _source(plan_id)
    plan = _plan(source, plan_id)
    verification = _fix(source, plan_id)
    assert source.validation_plan_id == plan_id
    assert plan.verification_plan_id == plan_id
    assert plan.verification_plan_id != plan.plan_digest
    assert plan.source_change_declaration_id == source.declaration_id
    assert verification.verification_plan_id == plan_id
    assert verification.verification_plan_digest == plan.plan_digest

    changed_plan = plan.to_dict()
    changed_plan["verification_plan_id"] = "d" * 64
    _expect_invalid(lambda: VerificationPlan.from_value(changed_plan))
    changed_verification = verification.to_dict()
    changed_verification["verification_plan_digest"] = "c" * 64
    _expect_invalid(lambda: FixVerification.from_value(changed_verification))


def test_v2_verification_plan_requires_and_binds_continuation_evidence() -> None:
    plan = _plan(continuation_evidence_id="8" * 64)
    wire = plan.to_dict()

    assert wire["schema"] == "stm32-verification-plan/2"
    assert wire["continuation_evidence_id"] == "8" * 64
    assert VerificationPlan.from_value(wire) == plan

    for mutation in ("missing", "legacy-schema", "changed-id"):
        candidate = deepcopy(wire)
        if mutation == "missing":
            candidate.pop("continuation_evidence_id")
        elif mutation == "legacy-schema":
            candidate["schema"] = "stm32-verification-plan/1"
        else:
            candidate["continuation_evidence_id"] = "9" * 64
        before = deepcopy(candidate)

        _expect_invalid(lambda candidate=candidate: VerificationPlan.from_value(candidate))
        assert candidate == before


def test_derived_ids_are_canonical_and_bind_every_field() -> None:
    source = _source()
    plan = _plan(source)
    marker = _marker(plan)
    verification = _fix(source)

    source_fields = source.to_dict()
    source_fields.pop("declaration_id")
    assert source.declaration_id == sha256(
        canonical_diagnostic_json_bytes(source_fields)
    ).hexdigest()
    assert calculate_source_change_declaration_id(source.to_dict()) == source.declaration_id

    plan_fields = plan.to_dict()
    plan_fields.pop("plan_digest")
    assert plan.verification_plan_id == PLAN_ID
    assert plan.plan_digest == sha256(
        canonical_diagnostic_json_bytes(plan_fields)
    ).hexdigest()
    assert calculate_verification_plan_digest(plan.to_dict()) == plan.plan_digest

    assert marker.marker_id == "0" * 64
    assert marker.marker_evidence_id == "f" * 64
    assert marker.schema == "stm32-diagnostic-marker-ref/1"
    marker_fields = marker.to_dict()
    marker_fields["marker_evidence_id"] = "not-a-digest"
    _expect_invalid(lambda: DiagnosticMarkerRef.from_value(marker_fields))

    verification_fields = verification.to_dict()
    verification_fields.pop("fix_verification_id")
    assert verification.fix_verification_id == sha256(
        canonical_diagnostic_json_bytes(verification_fields)
    ).hexdigest()
    assert calculate_fix_verification_id(verification.to_dict()) == verification.fix_verification_id


@pytest.mark.parametrize(
    "factory,field",
    [
        (lambda value: SourceChangeDeclaration.from_value(value), "before_source_sha256"),
        (lambda value: VerificationPlan.from_value(value), "diagnostic_session_id"),
        (lambda value: FixVerification.from_value(value), "status"),
    ],
)
def test_one_field_tamper_breaks_each_derived_id(factory, field: str) -> None:
    values = [_source().to_dict(), _plan().to_dict(), _fix().to_dict()]
    value = values[{"before_source_sha256": 0, "diagnostic_session_id": 1, "status": 2}[field]]
    if field == "before_source_sha256":
        value[field] = "0" * 64
    elif field == "diagnostic_session_id":
        value[field] = "b" * 32
    else:
        value[field] = "CANCELLED"
    _expect_invalid(lambda: factory(value))


def test_closed_wire_fields_tuples_subclasses_and_types_are_rejected() -> None:
    source = _source()
    source_value = source.to_dict()
    source_value["changed_paths"] = tuple(source_value["changed_paths"])
    _expect_invalid(lambda: SourceChangeDeclaration.from_value(source_value))

    plan_value = _plan(source).to_dict()
    plan_value["required_analysis_ids"] = [ANALYSIS_IDS[0], ANALYSIS_IDS[0]]
    _expect_invalid(lambda: VerificationPlan.from_value(plan_value))

    marker_value = _marker().to_dict()
    marker_value["rationale"] = True
    _expect_invalid(lambda: DiagnosticMarkerRef.from_value(marker_value))

    marker_value = _marker().to_dict()
    marker_value["marker_id"] = "not-a-digest"
    _expect_invalid(lambda: DiagnosticMarkerRef.from_value(marker_value))

    fix_value = _fix().to_dict()
    fix_value["expected_changed"] = True
    _expect_invalid(lambda: FixVerification.from_value(fix_value))

    class SourceSubclass(SourceChangeDeclaration):
        pass

    subclass = SourceSubclass(
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
    _expect_invalid(lambda: SourceChangeDeclaration.from_value(subclass))


def test_public_wire_collection_and_identity_guards_preserve_input() -> None:
    source_paths_empty = _source().to_dict()
    source_paths_empty["changed_paths"] = []
    source_hypotheses_duplicate = _source().to_dict()
    source_hypotheses_duplicate["claimed_hypothesis_ids"] = [HYPOTHESIS_IDS[0], HYPOTHESIS_IDS[0]]
    source_hypotheses_unsorted = _source().to_dict()
    source_hypotheses_unsorted["claimed_hypothesis_ids"] = list(reversed(HYPOTHESIS_IDS))
    source_same_hash = _source().to_dict()
    source_same_hash["after_source_sha256"] = source_same_hash["before_source_sha256"]
    source_paths_too_many = _source().to_dict()
    source_paths_too_many["changed_paths"] = [f"src/{index}.c" for index in range(129)]

    plan_quality = _plan().to_dict()
    plan_quality["required_monitor_quality"] = "INVALID"
    plan_expected_unchanged = _plan().to_dict()
    plan_expected_unchanged["expected_changed"] = False
    plan_analysis_mismatch = _plan().to_dict()
    plan_analysis_mismatch["required_analysis_evidence_ids"] = [ANALYSIS_EVIDENCE_IDS[0]]
    plan_analysis_scalar = _plan().to_dict()
    plan_analysis_scalar["required_analysis_ids"] = ANALYSIS_IDS[0]
    plan_analysis_too_many = _plan().to_dict()
    plan_analysis_too_many["required_analysis_ids"] = [f"{index:064x}" for index in range(17)]
    plan_analysis_too_many["required_analysis_evidence_ids"] = [f"{index + 17:064x}" for index in range(17)]

    marker_polarity = _marker().to_dict()
    marker_polarity["polarity"] = "neutral"
    marker_label = _marker().to_dict()
    marker_label["label"] = "unknown-label"

    fix_operations_duplicate = _fix().to_dict()
    fix_operations_duplicate["executed_operation_ids"] = ["verification.complete", "verification.complete"]
    fix_operations_scalar = _fix().to_dict()
    fix_operations_scalar["executed_operation_ids"] = "verification.complete"
    fix_status = _fix().to_dict()
    fix_status["status"] = "UNKNOWN"

    cases = (
        (SourceChangeDeclaration.from_value, source_paths_empty, DIAGNOSTIC_INVALID_EVENT),
        (SourceChangeDeclaration.from_value, source_hypotheses_duplicate, DIAGNOSTIC_INVALID_EVENT),
        (SourceChangeDeclaration.from_value, source_hypotheses_unsorted, DIAGNOSTIC_INVALID_EVENT),
        (SourceChangeDeclaration.from_value, source_same_hash, DIAGNOSTIC_INVALID_EVENT),
        (SourceChangeDeclaration.from_value, source_paths_too_many, DIAGNOSTIC_LIMIT_EXCEEDED),
        (VerificationPlan.from_value, plan_quality, DIAGNOSTIC_INVALID_EVENT),
        (VerificationPlan.from_value, plan_expected_unchanged, DIAGNOSTIC_INVALID_EVENT),
        (VerificationPlan.from_value, plan_analysis_mismatch, DIAGNOSTIC_INVALID_EVENT),
        (VerificationPlan.from_value, plan_analysis_scalar, DIAGNOSTIC_INVALID_EVENT),
        (VerificationPlan.from_value, plan_analysis_too_many, DIAGNOSTIC_LIMIT_EXCEEDED),
        (DiagnosticMarkerRef.from_value, marker_polarity, DIAGNOSTIC_INVALID_EVENT),
        (DiagnosticMarkerRef.from_value, marker_label, DIAGNOSTIC_INVALID_EVENT),
        (VerificationPlan.from_value, None, DIAGNOSTIC_INVALID_EVENT),
        (DiagnosticMarkerRef.from_value, None, DIAGNOSTIC_INVALID_EVENT),
        (FixVerification.from_value, fix_operations_duplicate, DIAGNOSTIC_INVALID_EVENT),
        (FixVerification.from_value, fix_operations_scalar, DIAGNOSTIC_INVALID_EVENT),
        (FixVerification.from_value, fix_status, DIAGNOSTIC_INVALID_EVENT),
        (FixVerification.from_value, None, DIAGNOSTIC_INVALID_EVENT),
    )

    for factory, candidate, expected_code in cases:
        before = deepcopy(candidate)
        _expect_invalid(lambda factory=factory, candidate=candidate: factory(candidate), expected_code)
        assert candidate == before


def test_public_constructor_requires_tuple_collections() -> None:
    _expect_invalid(lambda: SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=["src/main.c"],  # type: ignore[arg-type]
        diff_evidence_id="e" * 64,
        diff_artifact=ARTIFACT,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id=PLAN_ID,
    ))


@pytest.mark.parametrize(
    "changed_paths,expected_code",
    [
        ((), DIAGNOSTIC_INVALID_EVENT),
        (("src/z.c", "src/a.c"), DIAGNOSTIC_INVALID_EVENT),
        (("src/a.c", "src/a.c"), DIAGNOSTIC_INVALID_EVENT),
        (("/absolute.c",), DIAGNOSTIC_INVALID_EVENT),
        (("C:/drive.c",), DIAGNOSTIC_INVALID_EVENT),
        (("src\\bad.c",), DIAGNOSTIC_INVALID_EVENT),
        (("src//bad.c",), DIAGNOSTIC_INVALID_EVENT),
        (("src/./bad.c",), DIAGNOSTIC_INVALID_EVENT),
        (("src/../bad.c",), DIAGNOSTIC_INVALID_EVENT),
        (("src/bad/",), DIAGNOSTIC_INVALID_EVENT),
        (("src/" + "x" * 256 + ".c",), DIAGNOSTIC_LIMIT_EXCEEDED),
    ],
)
def test_changed_paths_are_safe_sorted_unique_and_bounded(
    changed_paths: tuple[str, ...], expected_code: str,
) -> None:
    _expect_invalid(lambda: SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=changed_paths,
        diff_evidence_id="e" * 64,
        diff_artifact=ARTIFACT,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id="f" * 64,
    ), expected_code)


def test_path_and_tuple_limits_use_stable_limit_code() -> None:
    long_paths = tuple("src/" + f"{index:02d}-" + "x" * 245 for index in range(18))
    _expect_invalid(lambda: SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=long_paths,
        diff_evidence_id="e" * 64,
        diff_artifact=ARTIFACT,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id="f" * 64,
    ), DIAGNOSTIC_LIMIT_EXCEEDED)

    _expect_invalid(lambda: SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=tuple(f"src/{index}.c" for index in range(129)),
        diff_evidence_id="e" * 64,
        diff_artifact=ARTIFACT,
        claimed_hypothesis_ids=HYPOTHESIS_IDS,
        validation_plan_id="f" * 64,
    ), DIAGNOSTIC_LIMIT_EXCEEDED)


@pytest.mark.parametrize(
    "status,reason",
    [
        ("PASSED", "VERIFICATION_PASSED"),
        ("FAILED", "FIXED_TEST_FAILED"),
        ("FAILED", "ANALYSIS_CONTRADICTED"),
        ("INCONCLUSIVE", "MANDATORY_EVIDENCE_MISSING"),
        ("INCONCLUSIVE", "MANDATORY_EVIDENCE_CORRUPT"),
        ("INCONCLUSIVE", "ANALYSIS_NOT_VALID"),
        ("CANCELLED", "CALLER_CANCELLED"),
    ],
)
def test_fix_verification_closed_status_reason_pairs(status: str, reason: str) -> None:
    plan = _plan()
    value = FixVerification.new(
        diagnostic_session_id=SESSION_ID,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        verification_plan_id=plan.verification_plan_id,
        verification_plan_digest=plan.plan_digest,
        analysis_ids=plan.required_analysis_ids,
        analysis_evidence_ids=plan.required_analysis_evidence_ids,
        executed_operation_ids=("verification.complete",),
        status=status,
        reason_code=reason,
        completed_at_utc="2026-08-21T12:34:56.000000Z",
    )
    assert value.status == status
    invalid = value.to_dict()
    invalid["reason_code"] = "CALLER_CANCELLED" if reason != "CALLER_CANCELLED" else "VERIFICATION_PASSED"
    _expect_invalid(lambda: FixVerification.from_value(invalid))


def test_utc_and_evidence_pairing_and_parallel_tuple_rules() -> None:
    source = _source()
    plan = _plan(source)
    marker = _marker(plan)
    fix = _fix(source)

    invalid_marker = marker.to_dict()
    invalid_marker["rationale"] = ""
    _expect_invalid(lambda: DiagnosticMarkerRef.from_value(invalid_marker))

    invalid_fix = fix.to_dict()
    invalid_fix["completed_at_utc"] = "2026-08-21T12:34:56Z"
    _expect_invalid(lambda: FixVerification.from_value(invalid_fix))

    invalid_plan = plan.to_dict()
    invalid_plan["required_analysis_evidence_ids"] = [ANALYSIS_EVIDENCE_IDS[0]]
    _expect_invalid(lambda: VerificationPlan.from_value(invalid_plan))

    invalid_plan = plan.to_dict()
    invalid_plan["fixed_after_run_id"] = invalid_plan["failed_before_run_id"]
    _expect_invalid(lambda: VerificationPlan.from_value(invalid_plan))


def test_verification_plan_paired_analysis_evidence_ids_sort_together() -> None:
    declaration = _source()
    analysis_ids = ("f" * 64, "e" * 64)
    evidence_ids = ("1" * 64, "2" * 64)
    plan = VerificationPlan.new(
        verification_plan_id=PLAN_ID,
        diagnostic_session_id=SESSION_ID,
        failed_before_run_id="failed-before",
        failed_before_evidence_id="3" * 64,
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="fixed-after",
        fixed_after_evidence_id="4" * 64,
        required_analysis_ids=analysis_ids,
        required_analysis_evidence_ids=evidence_ids,
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    assert tuple(zip(plan.required_analysis_ids, plan.required_analysis_evidence_ids)) == (
        ("e" * 64, "2" * 64),
        ("f" * 64, "1" * 64),
    )
    assert VerificationPlan.from_value(plan.to_dict()) == plan


def test_fix_verification_paired_analysis_evidence_ids_sort_together() -> None:
    plan = _plan()
    analysis_ids = ("f" * 64, "e" * 64)
    evidence_ids = ("1" * 64, "2" * 64)
    verification = FixVerification.new(
        diagnostic_session_id=SESSION_ID,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        verification_plan_id=plan.verification_plan_id,
        verification_plan_digest=plan.plan_digest,
        analysis_ids=analysis_ids,
        analysis_evidence_ids=evidence_ids,
        executed_operation_ids=("verification.start", "verification.complete"),
        status="PASSED",
        reason_code="VERIFICATION_PASSED",
        completed_at_utc="2026-08-21T12:34:56.000000Z",
    )
    assert tuple(zip(verification.analysis_ids, verification.analysis_evidence_ids)) == (
        ("e" * 64, "2" * 64),
        ("f" * 64, "1" * 64),
    )
    assert FixVerification.from_value(verification.to_dict()) == verification
