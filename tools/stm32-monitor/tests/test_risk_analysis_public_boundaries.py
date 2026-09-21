from __future__ import annotations

from pathlib import Path

import pytest
from stm32_monitor.analysis import (
    ANALYSIS_REQUEST_INVALID,
    AnalysisComputation,
    AnalysisError,
    AnalysisEvidenceRef,
    AnalysisLineage,
    AnalysisRequest,
    AnalysisResult,
    DiagnosticMarker,
    analyze_monitor_windows,
)
from test_analysis import _authoritative_case, _native_physical_source


def test_public_analysis_graph_preserves_identity_and_wire_roundtrips(
    tmp_path: Path,
) -> None:
    request, computation, lineage, result = _authoritative_case(tmp_path)
    evidence_ref = AnalysisEvidenceRef.new(
        analysis_id=result.analysis_id,
        evidence_id="e" * 64,
    )
    marker = DiagnosticMarker.new(
        analysis_id=result.analysis_id,
        analysis_evidence_id=evidence_ref.evidence_id,
        diagnostic_session_id="f" * 32,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="the changed values support the hypothesis",
    )

    for value, cls in (
        (request, AnalysisRequest),
        (computation, AnalysisComputation),
        (lineage, AnalysisLineage),
        (result, AnalysisResult),
        (evidence_ref, AnalysisEvidenceRef),
        (marker, DiagnosticMarker),
    ):
        assert cls.from_value(value) is value
        payload = value.to_dict()
        restored = cls.from_value(payload)
        assert restored == value
        assert restored.to_dict() == payload

    assert "evidence_id" not in result.to_dict()
    assert "evidence_id" not in marker.to_dict()


def test_public_native_inconclusive_result_below_threshold_roundtrips() -> None:
    before_ref, before = _native_physical_source(
        role="failed-before",
        operation_id="11111111-1111-4111-8111-111111111111",
        group_id="22222222-2222-4222-8222-222222222222",
        values=(10, 20),
    )
    after_ref, after = _native_physical_source(
        role="fixed-after",
        operation_id="33333333-3333-4333-8333-333333333333",
        group_id="44444444-4444-4444-8444-444444444444",
        values=(11, 25),
    )
    request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/2",
        before_run=before_ref,
        after_run=after_ref,
        selector_kind="register",
        selector="r0",
        alignment="bounded-run-relative",
        minimum_valid_pairs=3,
        scalar_policy="native-uint-register/1",
        max_pairing_skew_ns=1,
    )

    computation = analyze_monitor_windows(request, before, after)
    assert computation.quality == "INVALID"
    assert computation.conclusion == "INCONCLUSIVE"
    assert computation.reason_code == "INSUFFICIENT_VALID_PAIRS"
    assert computation.aligned_pair_count == 2
    assert computation.aligned_pair_count < request.minimum_valid_pairs

    lineage = AnalysisLineage.new(
        before_run=before_ref,
        after_run=after_ref,
        source_change_declaration_id=None,
    )
    result = AnalysisResult.new(
        request=request,
        computation=computation,
        lineage=lineage,
    )

    assert result.schema == "stm32-monitor-analysis/3"
    assert result.quality == "INVALID"
    assert result.conclusion == "INCONCLUSIVE"
    assert AnalysisResult.from_value(result.to_dict()) == result


def test_public_analysis_boundaries_reject_invalid_inputs_without_mutating_graph(
    tmp_path: Path,
) -> None:
    request, computation, lineage, result = _authoritative_case(tmp_path)
    request_wire = request.to_dict()
    computation_wire = computation.to_dict()
    lineage_wire = lineage.to_dict()
    result_wire = result.to_dict()

    invalid_quality = computation.to_dict()
    invalid_quality["quality"] = "NOT_A_QUALITY"
    with pytest.raises(AnalysisError) as quality_error:
        AnalysisComputation.from_value(invalid_quality)
    assert quality_error.value.code == ANALYSIS_REQUEST_INVALID
    assert quality_error.value.message == "analysis state is invalid"

    nonclosed_computation = computation.to_dict()
    nonclosed_computation["unknown"] = True
    with pytest.raises(AnalysisError) as nonclosed_error:
        AnalysisComputation.from_value(nonclosed_computation)
    assert nonclosed_error.value.code == ANALYSIS_REQUEST_INVALID
    assert nonclosed_error.value.message == "analysis computation fields are not closed"

    with pytest.raises(AnalysisError) as run_type_error:
        AnalysisLineage.new(
            before_run=object(),
            after_run=request.after_run,
            source_change_declaration_id=None,
        )
    assert run_type_error.value.code == ANALYSIS_REQUEST_INVALID
    assert run_type_error.value.message == "analysis lineage run references are invalid"

    native_after, _ = _native_physical_source(
        role="fixed-after",
        operation_id="55555555-5555-4555-8555-555555555555",
        group_id="66666666-6666-4666-8666-666666666666",
        values=(11, 25),
    )
    with pytest.raises(AnalysisError) as family_error:
        AnalysisLineage.new(
            before_run=request.before_run,
            after_run=native_after,
            source_change_declaration_id=None,
        )
    assert family_error.value.code == ANALYSIS_REQUEST_INVALID
    assert family_error.value.message == (
        "analysis lineage run reference families are incompatible"
    )

    with pytest.raises(AnalysisError) as evidence_schema_error:
        AnalysisEvidenceRef(
            "stm32-monitor-analysis-evidence-ref/9",
            result.analysis_id,
            "e" * 64,
        )
    assert evidence_schema_error.value.code == ANALYSIS_REQUEST_INVALID
    assert evidence_schema_error.value.message == (
        "analysis evidence reference schema is invalid"
    )

    with pytest.raises(AnalysisError) as polarity_error:
        DiagnosticMarker.new(
            analysis_id=result.analysis_id,
            analysis_evidence_id="e" * 64,
            diagnostic_session_id="f" * 32,
            hypothesis_id="1" * 32,
            polarity="unknown",
            label="change-observed",
            rationale="invalid polarity",
        )
    assert polarity_error.value.code == ANALYSIS_REQUEST_INVALID
    assert polarity_error.value.message == "diagnostic marker polarity is invalid"

    with pytest.raises(AnalysisError) as label_error:
        DiagnosticMarker.new(
            analysis_id=result.analysis_id,
            analysis_evidence_id="e" * 64,
            diagnostic_session_id="f" * 32,
            hypothesis_id="1" * 32,
            polarity="supports",
            label="unknown",
            rationale="invalid label",
        )
    assert label_error.value.code == ANALYSIS_REQUEST_INVALID
    assert label_error.value.message == "diagnostic marker label is invalid"

    assert request.before_run.run_ref_sha256 == result.before_run_id
    assert computation.request_digest == request.request_digest
    assert lineage == result.identity
    assert result.request_digest == request.request_digest
    assert request.to_dict() == request_wire
    assert computation.to_dict() == computation_wire
    assert lineage.to_dict() == lineage_wire
    assert result.to_dict() == result_wire
    assert AnalysisRequest.from_value(request_wire) == request
    assert AnalysisComputation.from_value(computation_wire) == computation
    assert AnalysisLineage.from_value(lineage_wire) == lineage
    assert AnalysisResult.from_value(result_wire) == result
