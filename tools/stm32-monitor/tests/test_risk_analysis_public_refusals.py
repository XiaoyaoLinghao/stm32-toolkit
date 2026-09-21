from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path
from uuid import UUID

import pytest
from stm32_monitor.analysis import (
    ANALYSIS_REQUEST_INVALID,
    AnalysisComputation,
    AnalysisError,
    AnalysisLineage,
    AnalysisRequest,
    AnalysisResult,
    DiagnosticMarker,
    analyze_monitor_windows,
)
from test_analysis import _case, _request


@pytest.mark.parametrize(
    ("variant", "expected_message"),
    [
        ("bounded-message", "analysis error message is invalid"),
        ("nested-depth", "analysis value exceeds its nesting limit"),
        ("noncanonical-register", "selector is not canonical"),
        ("logical-project-id-type", "logical project ID is invalid"),
        ("logical-project-id-uppercase", "logical project ID is invalid"),
        ("unchanged-statistics", "unchanged analysis statistics are inconsistent"),
        ("marker-schema", "diagnostic marker schema is invalid"),
    ],
)
def test_public_analysis_wire_refusal_preserves_and_restores_graph(
    tmp_path: Path, variant: str, expected_message: str
) -> None:
    fixture_root = tmp_path / "analysis"
    fixture_root.mkdir()
    _, _, _, before, after, before_ref, after_ref = _case(fixture_root)
    request = _request(before_ref, after_ref)
    computation = analyze_monitor_windows(request, before, after)
    lineage = AnalysisLineage.new(
        before_run=before_ref,
        after_run=after_ref,
        source_change_declaration_id="d" * 64,
    )
    result = AnalysisResult.new(
        request=request,
        computation=computation,
        lineage=lineage,
    )

    request_wire = request.to_dict()
    computation_wire = computation.to_dict()
    lineage_wire = lineage.to_dict()
    result_wire = result.to_dict()

    operation = None
    if variant == "bounded-message":
        valid_message = "v" * 256
        valid_error = AnalysisError(ANALYSIS_REQUEST_INVALID, valid_message)
        assert valid_error.code == ANALYSIS_REQUEST_INVALID
        assert valid_error.message == valid_message
        with pytest.raises(ValueError) as empty_error:
            AnalysisError(ANALYSIS_REQUEST_INVALID, "")
        assert str(empty_error.value) == expected_message
        with pytest.raises(ValueError) as oversized_error:
            AnalysisError(ANALYSIS_REQUEST_INVALID, "x" * 257)
        assert str(oversized_error.value) == expected_message
    elif variant == "nested-depth":
        nested: object = "leaf"
        for _ in range(40):
            nested = {"nested": nested}
        invalid = request.to_dict()
        invalid["before_run"] = nested
        operation = partial(AnalysisRequest.from_value, invalid)
    elif variant == "noncanonical-register":
        invalid = request.to_dict()
        invalid["selector_kind"] = "register"
        invalid["selector"] = "r0 "
        operation = partial(AnalysisRequest.from_value, invalid)
    elif variant in {"logical-project-id-type", "logical-project-id-uppercase"}:
        invalid = lineage.to_dict()
        invalid["logical_project_id"] = (
            7
            if variant == "logical-project-id-type"
            else lineage.logical_project_id.upper()
        )
        operation = partial(AnalysisLineage.from_value, invalid)
    elif variant == "unchanged-statistics":
        invalid = computation.to_dict()
        invalid["changed"] = False
        invalid["reason_code"] = "VALUES_UNCHANGED"
        operation = partial(AnalysisComputation.from_value, invalid)
    else:
        marker = DiagnosticMarker.new(
            analysis_id=result.analysis_id,
            analysis_evidence_id="e" * 64,
            diagnostic_session_id="f" * 32,
            hypothesis_id="1" * 32,
            polarity="supports",
            label="change-observed",
            rationale="changed values support the hypothesis",
        )
        invalid = marker.to_dict()
        invalid["schema"] = "stm32-diagnostic-marker/9"
        operation = partial(DiagnosticMarker.from_value, invalid)

    if operation is not None:
        with pytest.raises(AnalysisError) as error:
            operation()
        assert error.value.code == ANALYSIS_REQUEST_INVALID
        assert error.value.message == expected_message

    assert request.to_dict() == request_wire
    assert computation.to_dict() == computation_wire
    assert lineage.to_dict() == lineage_wire
    assert result.to_dict() == result_wire
    assert AnalysisRequest.from_value(request_wire) == request
    assert AnalysisComputation.from_value(computation_wire) == computation
    assert AnalysisLineage.from_value(lineage_wire) == lineage
    assert AnalysisResult.from_value(result_wire) == result
    assert analyze_monitor_windows(request, before, after) == computation


@pytest.mark.parametrize(
    ("variant", "expected_message"),
    [
        ("ordinary-object", "analysis batch value types are invalid"),
        ("wrong-run", "analysis batch run identity is invalid"),
        ("wrong-group", "analysis batch group identity is invalid"),
        (
            "continuation-provider",
            "continuation requires its authoritative EvidenceStore",
        ),
    ],
)
def test_public_analysis_window_refusal_preserves_and_restores_inputs(
    tmp_path: Path, variant: str, expected_message: str
) -> None:
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)
    before_snapshot = before
    after_snapshot = after
    request_snapshot = request.to_dict()

    if variant == "ordinary-object":
        invalid_after = (object(), after[1])
        operation = partial(analyze_monitor_windows, request, before, invalid_after)
    elif variant == "wrong-run":
        invalid_after = tuple(
            replace(
                batch,
                run_id=UUID("99999999-9999-4999-8999-999999999999"),
            )
            if index == 0
            else batch
            for index, batch in enumerate(after)
        )
        operation = partial(analyze_monitor_windows, request, before, invalid_after)
    elif variant == "wrong-group":
        invalid_after = tuple(
            replace(
                batch,
                group_id=UUID("99999999-9999-4999-8999-999999999999"),
            )
            if index == 0
            else batch
            for index, batch in enumerate(after)
        )
        operation = partial(analyze_monitor_windows, request, before, invalid_after)
    else:
        operation = partial(
            analyze_monitor_windows,
            request,
            before,
            after,
            continuation_evidence_id="e" * 64,
            evidence_store=None,
            diagnostics_root=None,
        )

    with pytest.raises(AnalysisError) as error:
        operation()
    assert error.value.code == ANALYSIS_REQUEST_INVALID
    assert error.value.message == expected_message

    assert before == before_snapshot
    assert after == after_snapshot
    assert request.to_dict() == request_snapshot
    restored = analyze_monitor_windows(request, before, after)
    assert restored.quality == "VALID"
    assert restored.conclusion == "COMPLETED"
    assert restored.reason_code == "VALUES_CHANGED"
