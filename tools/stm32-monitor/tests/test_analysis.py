from __future__ import annotations

import builtins
import json
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
import stm32_monitor.analysis as analysis_module

from stm32_monitor.analysis import (
    ANALYSIS_REQUEST_INVALID,
    AnalysisComputation,
    AnalysisEvidenceRef,
    AnalysisError,
    AnalysisLineage,
    AnalysisRequest,
    AnalysisResult,
    DiagnosticMarker,
    analyze_monitor_windows,
)
from stm32_monitor.models import MAX_SIGNED_INT64, SampleBatch, SampleValue, WatchItem
from stm32_monitor.replay import (
    MonitorReplayDocument,
    MonitorRunRef,
    _make_reference,
    _project_batches,
    canonical_replay_json_bytes,
)
from stm32_toolkit.paths import WorkspacePaths


FIXTURES = Path(__file__).parent / "fixtures" / "vs03"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
RUN_IDS = {
    "failed-before": UUID("33333333-3333-4333-8333-333333333333"),
    "fixed-after": UUID("44444444-4444-4444-8444-444444444444"),
}
COUNTER = WatchItem.variable("counter")
REGISTER = WatchItem.register("r0")


def _paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, PROJECT_ID, "analysis-import")


def _document(role: str) -> MonitorReplayDocument:
    raw = (FIXTURES / f"{role}.json").read_bytes()
    return MonitorReplayDocument.from_value(json.loads(raw.rstrip(b"\n").decode("utf-8")))


def _reference(
    document: MonitorReplayDocument,
    paths: WorkspacePaths,
    batches: tuple[SampleBatch, ...],
) -> MonitorRunRef:
    return _make_reference(
        document,
        paths,
        str(RUN_IDS[document.scenario_role]),
        batches,
        "a" * 64,
    )


def _case(tmp_path: Path):
    paths = _paths(tmp_path)
    before_document = _document("failed-before")
    after_document = _document("fixed-after")
    before = _project_batches(before_document, paths)
    after = _project_batches(after_document, paths)
    return (
        paths,
        before_document,
        after_document,
        before,
        after,
        _reference(before_document, paths, before),
        _reference(after_document, paths, after),
    )


def _request(before: MonitorRunRef, after: MonitorRunRef, *, minimum: int = 2) -> AnalysisRequest:
    return AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=before,
        after_run=after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=minimum,
    )


def _replace_counter(
    batch: SampleBatch,
    value: object,
    *,
    status: str = "OK",
    value_type: str = "uint32",
) -> SampleBatch:
    values = tuple(
        replace(
            sample,
            status=status,
            typed_value=None if status == "ERROR" else {"type": value_type, "value": value},
            code="SAMPLE_ERROR" if status == "ERROR" else None,
        )
        if sample.watch == COUNTER
        else sample
        for sample in batch.values
    )
    return replace(batch, values=values)


def _with_reference(
    document: MonitorReplayDocument,
    paths: WorkspacePaths,
    batches: tuple[SampleBatch, ...],
) -> MonitorRunRef:
    return _reference(document, paths, batches)


def _ref_with(reference: MonitorRunRef, **changes: object) -> MonitorRunRef:
    payload = reference.to_dict()
    payload.update(changes)
    unsigned = dict(payload)
    unsigned.pop("run_ref_sha256")
    payload["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    return MonitorRunRef.from_value(payload)


def test_request_and_computation_are_closed_canonical_values(tmp_path: Path) -> None:
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)

    assert request.request_digest == sha256(
        canonical_replay_json_bytes(request.to_dict())
    ).hexdigest()
    round_trip = AnalysisRequest.from_value(request.to_dict())
    assert round_trip == request
    copied = request.to_dict()
    copied["before_run"]["operation_id"] = "0" * 36
    assert request.before_run.operation_id != copied["before_run"]["operation_id"]

    result = analyze_monitor_windows(request, before, after)
    assert result.schema == "stm32-monitor-analysis-computation/1"
    assert result.request_digest == request.request_digest
    assert AnalysisComputation.from_value(result.to_dict()) == result
    assert "analysis_id" not in result.to_dict()
    assert "evidence_id" not in result.to_dict()


def test_changed_window_is_valid_and_exactly_aligned(tmp_path: Path) -> None:
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, after)

    assert result.quality == "VALID"
    assert result.conclusion == "COMPLETED"
    assert result.reason_code == "VALUES_CHANGED"
    assert result.aligned_position_count == 2
    assert result.aligned_pair_count == 2
    assert result.excluded_position_count == 0
    assert result.before_first == 10
    assert result.before_last == 11
    assert result.before_min == 10
    assert result.before_max == 11
    assert result.after_first == 15
    assert result.after_last == 16
    assert result.after_min == 15
    assert result.after_max == 16
    assert result.delta_first == 5
    assert result.delta_last == 5
    assert result.changed is True


def test_identical_window_is_unchanged(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    unchanged_after = tuple(
        _replace_counter(batch, before[index].values[0].typed_value["value"])
        for index, batch in enumerate(after)
    )
    after_ref = _with_reference(after_document, paths, unchanged_after)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, unchanged_after)

    assert result.quality == "VALID"
    assert result.reason_code == "VALUES_UNCHANGED"
    assert result.changed is False
    assert result.delta_first == 0
    assert result.delta_last == 0


def test_run_relative_alignment_never_interpolates_or_uses_capture_time(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    shifted = tuple(
        replace(
            batch,
            scheduled_unix_ns=batch.scheduled_unix_ns + (500 if batch.sequence else 0),
            captured_unix_ns=batch.captured_unix_ns + (500 if batch.sequence else 0),
        )
        for batch in after
    )
    after_ref = _with_reference(after_document, paths, shifted)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, shifted)

    assert result.aligned_position_count == 3
    assert result.aligned_pair_count == 1
    assert result.excluded_position_count == 2
    assert result.quality == "INVALID"
    assert result.conclusion == "INCONCLUSIVE"
    assert result.reason_code == "INSUFFICIENT_VALID_PAIRS"
    assert result.changed is None
    assert result.before_first is None
    assert result.after_max is None


def test_captured_timestamp_shift_does_not_change_scheduled_alignment(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    shifted = tuple(
        replace(batch, captured_unix_ns=batch.captured_unix_ns + 500)
        for batch in after
    )
    after_ref = _with_reference(after_document, paths, shifted)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, shifted)

    assert result.quality == "VALID"
    assert result.aligned_position_count == 2
    assert result.aligned_pair_count == 2
    assert result.excluded_position_count == 0


def test_selector_vocabulary_mismatch_is_rejected_before_comparison(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    no_register = tuple(
        replace(batch, values=tuple(sample for sample in batch.values if sample.watch != REGISTER))
        for batch in after
    )
    after_ref = _with_reference(after_document, paths, no_register)

    with pytest.raises(AnalysisError) as error:
        analyze_monitor_windows(_request(before_ref, after_ref), before, no_register)
    assert error.value.code == ANALYSIS_REQUEST_INVALID


def test_same_selector_with_different_typed_type_is_excluded(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    different_type = tuple(
        _replace_counter(batch, batch.values[0].typed_value["value"], value_type="int32")
        for batch in after
    )
    after_ref = _with_reference(after_document, paths, different_type)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, different_type)

    assert result.aligned_position_count == 2
    assert result.aligned_pair_count == 0
    assert result.excluded_position_count == 2
    assert result.quality == "INVALID"
    assert result.reason_code == "INSUFFICIENT_VALID_PAIRS"


def test_missing_error_and_invalid_samples_are_degraded_when_minimum_is_met(tmp_path: Path) -> None:
    paths, before_document, after_document, before, after, before_ref, _ = _case(tmp_path)
    before_three = before + (
        replace(
            before[-1],
            sequence=2,
            scheduled_unix_ns=before[-1].scheduled_unix_ns + 1_000_000,
            captured_unix_ns=before[-1].captured_unix_ns + 1_000_000,
        ),
    )
    after_three = after + (
        _replace_counter(
            replace(
                after[-1],
                sequence=2,
                scheduled_unix_ns=after[-1].scheduled_unix_ns + 1_000_000,
                captured_unix_ns=after[-1].captured_unix_ns + 1_000_000,
            ),
            "not numeric",
        ),
    )
    after_three = after_three[:-1] + (_replace_counter(after_three[-1], 17, status="ERROR"),)
    before_ref = _with_reference(before_document, paths, before_three)
    after_ref = _with_reference(after_document, paths, after_three)
    result = analyze_monitor_windows(
        _request(before_ref, after_ref), before_three, after_three
    )

    assert result.quality == "DEGRADED"
    assert result.conclusion == "COMPLETED"
    assert result.reason_code == "VALUES_CHANGED_WITH_EXCLUSIONS"
    assert result.aligned_position_count == 3
    assert result.aligned_pair_count == 2
    assert result.excluded_position_count == 1


@pytest.mark.parametrize("bad_value", ("text", True))
def test_nonnumeric_and_boolean_values_are_excluded(tmp_path: Path, bad_value: object) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    invalid = tuple(_replace_counter(batch, bad_value) for batch in after)
    after_ref = _with_reference(after_document, paths, invalid)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, invalid)

    assert result.quality == "INVALID"
    assert result.reason_code == "INSUFFICIENT_VALID_PAIRS"
    assert result.aligned_pair_count == 0
    assert result.before_first is None
    assert result.changed is None


@pytest.mark.parametrize("bad_value", (float("nan"), float("inf")))
def test_nonfinite_typed_values_are_rejected_before_analysis(tmp_path: Path, bad_value: float) -> None:
    _, _, _, _, after, _, _ = _case(tmp_path)
    with pytest.raises(ValueError):
        _replace_counter(after[0], bad_value)


def test_selector_missing_duplicate_and_type_mismatch_are_excluded(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    missing = tuple(
        replace(batch, values=tuple(sample for sample in batch.values if sample.watch != COUNTER))
        if batch.sequence == 0
        else batch
        for batch in after
    )
    duplicate = tuple(
        replace(batch, values=batch.values + (batch.values[0],))
        if batch.sequence == 1
        else batch
        for batch in missing
    )
    mismatch = tuple(
        _replace_counter(batch, batch.values[0].typed_value["value"], value_type="int32")
        if batch.sequence == 1
        else batch
        for batch in duplicate
    )
    after_ref = _with_reference(after_document, paths, mismatch)
    result = analyze_monitor_windows(_request(before_ref, after_ref), before, mismatch)

    assert result.aligned_position_count == 2
    assert result.aligned_pair_count == 0
    assert result.excluded_position_count == 2
    assert result.quality == "INVALID"
    assert result.changed is None


def test_insufficient_zero_and_one_pair_return_null_statistics(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    shifted = tuple(
        _replace_counter(batch, batch.values[0].typed_value["value"], value_type="int32")
        for batch in after
    )
    zero_ref = _with_reference(after_document, paths, shifted)
    zero = analyze_monitor_windows(_request(before_ref, zero_ref), before, shifted)
    assert zero.aligned_pair_count == 0
    assert zero.before_min is None and zero.after_max is None and zero.delta_last is None

    one = tuple(
        _replace_counter(batch, batch.values[0].typed_value["value"], value_type="int32")
        if batch.sequence == 1
        else batch
        for batch in after
    )
    one_ref = _with_reference(after_document, paths, one)
    one_result = analyze_monitor_windows(_request(before_ref, one_ref), before, one)
    assert one_result.aligned_pair_count == 1
    assert one_result.quality == "INVALID"
    assert one_result.before_first is None
    assert one_result.changed is None


def test_total_value_limit_is_distinct_from_batch_count_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    after_ref = _with_reference(after_document, paths, after)
    monkeypatch.setattr(analysis_module, "MAX_ANALYSIS_VALUES", 3)

    with pytest.raises(AnalysisError) as error:
        analyze_monitor_windows(_request(before_ref, after_ref), before, after)
    assert error.value.code == ANALYSIS_REQUEST_INVALID


def _assert_invalid_computation(payload: dict[str, object]) -> None:
    with pytest.raises(AnalysisError):
        AnalysisComputation(**payload)
    with pytest.raises(AnalysisError):
        AnalysisComputation.from_value(payload)


def test_computation_rejects_impossible_counts_statistics_and_deltas(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, after_ref = _case(tmp_path)
    changed = analyze_monitor_windows(_request(before_ref, after_ref), before, after)

    zero_positions = changed.to_dict()
    zero_positions.update(
        quality="INVALID",
        conclusion="INCONCLUSIVE",
        reason_code="INSUFFICIENT_VALID_PAIRS",
        aligned_position_count=0,
        aligned_pair_count=0,
        excluded_position_count=0,
        before_first=None,
        before_last=None,
        before_min=None,
        before_max=None,
        after_first=None,
        after_last=None,
        after_min=None,
        after_max=None,
        delta_first=None,
        delta_last=None,
        changed=None,
    )
    _assert_invalid_computation(zero_positions)

    one_pair = changed.to_dict()
    one_pair.update(aligned_position_count=1, aligned_pair_count=1, excluded_position_count=0)
    _assert_invalid_computation(one_pair)

    bad_order = changed.to_dict()
    bad_order["before_min"] = bad_order["before_first"] + 1
    _assert_invalid_computation(bad_order)

    bad_delta = changed.to_dict()
    bad_delta["delta_first"] = 0
    _assert_invalid_computation(bad_delta)

    unchanged_after = tuple(
        _replace_counter(batch, before[index].values[0].typed_value["value"])
        for index, batch in enumerate(after)
    )
    unchanged_ref = _with_reference(after_document, paths, unchanged_after)
    unchanged = analyze_monitor_windows(
        _request(before_ref, unchanged_ref), before, unchanged_after
    )
    assert unchanged.changed is False
    bad_unchanged = unchanged.to_dict()
    bad_unchanged["after_first"] = bad_unchanged["after_first"] + 1
    _assert_invalid_computation(bad_unchanged)


def test_invalid_request_ref_batch_digest_identity_and_limits_fail_closed(tmp_path: Path) -> None:
    paths, _, after_document, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)
    payload = request.to_dict()
    payload["minimum_valid_pairs"] = True
    with pytest.raises(AnalysisError) as request_error:
        AnalysisRequest.from_value(payload)
    assert request_error.value.code == ANALYSIS_REQUEST_INVALID

    wrong_ref = _ref_with(after_ref, import_workspace_id="f" * 64)
    with pytest.raises(AnalysisError) as identity_error:
        analyze_monitor_windows(_request(before_ref, wrong_ref), before, after)
    assert identity_error.value.code == ANALYSIS_REQUEST_INVALID

    wrong_digest = _ref_with(
        after_ref,
        projected_batch_sha256s=["0" * 64, *after_ref.projected_batch_sha256s[1:]],
    )
    with pytest.raises(AnalysisError) as digest_error:
        analyze_monitor_windows(_request(before_ref, wrong_digest), before, after)
    assert digest_error.value.code == ANALYSIS_REQUEST_INVALID

    wrong_batch = replace(
        after[0],
        binding=replace(after[0].binding, workspace_id="e" * 64),
    )
    with pytest.raises(AnalysisError) as batch_error:
        analyze_monitor_windows(_request(before_ref, after_ref), before, (wrong_batch, after[1]))
    assert batch_error.value.code == ANALYSIS_REQUEST_INVALID

    with pytest.raises(AnalysisError):
        analyze_monitor_windows(request, [], after)
    with pytest.raises(AnalysisError):
        analyze_monitor_windows(request, before, tuple(before) + (before[0],) * 1023)

    missing_timestamp = after[0]
    object.__setattr__(missing_timestamp, "scheduled_unix_ns", None)
    with pytest.raises(AnalysisError):
        analyze_monitor_windows(request, before, (missing_timestamp, after[1]))


def test_closed_types_subclasses_and_no_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)

    class RequestSubclass(AnalysisRequest):
        pass

    with pytest.raises(AnalysisError):
        AnalysisRequest.from_value(
            RequestSubclass(
                request.schema,
                request.before_run,
                request.after_run,
                request.selector_kind,
                request.selector,
                request.alignment,
                request.minimum_valid_pairs,
            )
        )

    class BatchTuple(tuple[SampleBatch, ...]):
        pass

    with pytest.raises(AnalysisError):
        analyze_monitor_windows(request, BatchTuple(before), after)

    def forbidden(*args, **kwargs):
        raise AssertionError("analysis attempted I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    result = analyze_monitor_windows(request, before, after)
    assert result.aligned_pair_count == 2


def test_analysis_error_is_bounded_and_stable() -> None:
    error = AnalysisError(ANALYSIS_REQUEST_INVALID, "x" * 40)
    assert error.code == ANALYSIS_REQUEST_INVALID
    assert len(error.message) <= 256
    with pytest.raises(ValueError):
        AnalysisError("OTHER", "bad")


def test_authoritative_analysis_values_round_trip_and_derive_closed_ids(tmp_path: Path) -> None:
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)
    computation = analyze_monitor_windows(request, before, after)
    lineage = AnalysisLineage.new(
        before_run=before_ref,
        after_run=after_ref,
        source_change_declaration_id="d" * 64,
    )
    result = AnalysisResult.new(request=request, computation=computation, lineage=lineage)
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
    assert AnalysisLineage.from_value(lineage.to_dict()) == lineage
    assert AnalysisResult.from_value(result.to_dict()) == result
    assert AnalysisEvidenceRef.from_value(evidence_ref.to_dict()) == evidence_ref
    assert DiagnosticMarker.from_value(marker.to_dict()) == marker
    assert "evidence_id" not in result.to_dict()


def _authoritative_case(tmp_path: Path):
    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    request = _request(before_ref, after_ref)
    computation = analyze_monitor_windows(request, before, after)
    lineage = AnalysisLineage.new(
        before_run=before_ref,
        after_run=after_ref,
        source_change_declaration_id="d" * 64,
    )
    return request, computation, lineage, AnalysisResult.new(
        request=request,
        computation=computation,
        lineage=lineage,
    )


def test_authoritative_dataclass_field_order_and_exact_payload_shapes(tmp_path: Path) -> None:
    request, computation, lineage, result = _authoritative_case(tmp_path)
    evidence = AnalysisEvidenceRef.new(analysis_id=result.analysis_id, evidence_id="e" * 64)
    marker = DiagnosticMarker.new(
        analysis_id=result.analysis_id,
        analysis_evidence_id=evidence.evidence_id,
        diagnostic_session_id="f" * 32,
        hypothesis_id="1" * 32,
        polarity="supports",
        label="change-observed",
        rationale="changed",
    )
    assert tuple(item.name for item in fields(AnalysisLineage)) == (
        "schema", "origin_workspace_id", "import_workspace_id", "logical_project_id", "target_device",
        "before_input_snapshot_sha256", "before_build_id", "before_elf_sha256",
        "after_input_snapshot_sha256", "after_build_id", "after_elf_sha256", "source_change_declaration_id",
    )
    assert tuple(item.name for item in fields(AnalysisResult)) == (
        "schema", "analysis_id", "request_digest", "before_run_id", "after_run_id", "identity",
        "quality", "conclusion", "reason_code", "aligned_position_count", "aligned_pair_count",
        "excluded_position_count", "before_first", "before_last", "before_min", "before_max",
        "after_first", "after_last", "after_min", "after_max", "delta_first", "delta_last", "changed",
    )
    assert tuple(item.name for item in fields(AnalysisEvidenceRef)) == (
        "schema", "analysis_id", "evidence_id",
    )
    assert tuple(item.name for item in fields(DiagnosticMarker)) == (
        "schema", "marker_id", "analysis_id", "analysis_evidence_id", "diagnostic_session_id",
        "hypothesis_id", "polarity", "label", "rationale",
    )
    assert set(result.to_dict()) == {
        "schema", "analysis_id", "request_digest", "before_run_id", "after_run_id", "identity",
        "quality", "conclusion", "reason_code", "aligned_position_count", "aligned_pair_count",
        "excluded_position_count", "before_first", "before_last", "before_min", "before_max",
        "after_first", "after_last", "after_min", "after_max", "delta_first", "delta_last", "changed",
    }
    assert set(lineage.to_dict()) == {
        "schema", "origin_workspace_id", "import_workspace_id", "logical_project_id", "target_device",
        "before_input_snapshot_sha256", "before_build_id", "before_elf_sha256",
        "after_input_snapshot_sha256", "after_build_id", "after_elf_sha256", "source_change_declaration_id",
    }
    assert request.request_digest == computation.request_digest
    assert result.before_run_id == request.before_run.run_ref_sha256
    assert result.after_run_id == request.after_run.run_ref_sha256
    unsigned_result = result.to_dict()
    analysis_id = unsigned_result.pop("analysis_id")
    assert analysis_id == sha256(canonical_replay_json_bytes(unsigned_result)).hexdigest()
    unsigned_marker = marker.to_dict()
    marker_id = unsigned_marker.pop("marker_id")
    assert marker_id == sha256(canonical_replay_json_bytes(unsigned_marker)).hexdigest()


def test_lineage_identical_firmware_allows_no_declaration_and_changed_requires_one(tmp_path: Path) -> None:
    paths, _, _, _, _, before_ref, after_ref = _case(tmp_path)
    identical_after = _ref_with(
        after_ref,
        origin_workspace_id=before_ref.origin_workspace_id,
        import_workspace_id=before_ref.import_workspace_id,
        logical_project_id=before_ref.logical_project_id,
        target_device=before_ref.target_device,
        input_snapshot_sha256=before_ref.input_snapshot_sha256,
        build_id=before_ref.build_id,
        elf_sha256=before_ref.elf_sha256,
    )
    identical = AnalysisLineage.new(
        before_run=before_ref,
        after_run=identical_after,
        source_change_declaration_id=None,
    )
    assert identical.source_change_declaration_id is None
    with pytest.raises(AnalysisError):
        AnalysisLineage.new(
            before_run=before_ref,
            after_run=identical_after,
            source_change_declaration_id="d" * 64,
        )
    _ = paths


@pytest.mark.parametrize("firmware_field", [
    "input_snapshot_sha256", "build_id", "elf_sha256",
])
def test_lineage_copies_each_changed_firmware_field_and_requires_declaration(
    tmp_path: Path, firmware_field: str
) -> None:
    _, _, _, _, _, before_ref, after_ref = _case(tmp_path)
    values = {
        "input_snapshot_sha256": before_ref.input_snapshot_sha256,
        "build_id": before_ref.build_id,
        "elf_sha256": before_ref.elf_sha256,
    }
    values[firmware_field] = "f" * 64
    changed_after = _ref_with(after_ref, **values)
    lineage = AnalysisLineage.new(
        before_run=before_ref,
        after_run=changed_after,
        source_change_declaration_id="d" * 64,
    )
    assert getattr(lineage, f"after_{firmware_field}") == "f" * 64


@pytest.mark.parametrize("scope_field,scope_value", [
    ("origin_workspace_id", "f" * 64),
    ("import_workspace_id", "f" * 64),
    ("logical_project_id", "123e4567-e89b-42d3-a456-426614174001"),
    ("target_device", "host:other"),
])
def test_lineage_rejects_each_mismatched_shared_scope(
    tmp_path: Path, scope_field: str, scope_value: str
) -> None:
    _, _, _, _, _, before_ref, after_ref = _case(tmp_path)
    with pytest.raises(AnalysisError):
        AnalysisLineage.new(
            before_run=before_ref,
            after_run=_ref_with(after_ref, **{scope_field: scope_value}),
            source_change_declaration_id="d" * 64,
        )


@pytest.mark.parametrize("quality", ["VALID", "DEGRADED", "INVALID"])
def test_result_preserves_all_computation_qualities(tmp_path: Path, quality: str) -> None:
    paths, before_document, after_document, before, after, before_ref, _ = _case(tmp_path)
    if quality == "INVALID":
        after = tuple(_replace_counter(batch, batch.values[0].typed_value["value"], value_type="int32") for batch in after)
    elif quality == "DEGRADED":
        before = before + (
            replace(before[-1], sequence=2, scheduled_unix_ns=before[-1].scheduled_unix_ns + 1_000_000,
                    captured_unix_ns=before[-1].captured_unix_ns + 1_000_000),
        )
        after = after + (
            _replace_counter(
                replace(after[-1], sequence=2, scheduled_unix_ns=after[-1].scheduled_unix_ns + 1_000_000,
                        captured_unix_ns=after[-1].captured_unix_ns + 1_000_000),
                "not numeric",
            ),
        )
    after_ref = _with_reference(after_document, paths, after)
    before_ref = _with_reference(before_document, paths, before)
    request = _request(before_ref, after_ref)
    computation = analyze_monitor_windows(request, before, after)
    lineage = AnalysisLineage.new(
        before_run=before_ref, after_run=after_ref, source_change_declaration_id="d" * 64,
    )
    result = AnalysisResult.new(request=request, computation=computation, lineage=lineage)
    assert result.quality == quality
    assert result.conclusion == computation.conclusion


def test_result_requires_request_digest_and_exact_lineage_binding(tmp_path: Path) -> None:
    request, computation, lineage, result = _authoritative_case(tmp_path)
    with pytest.raises(AnalysisError):
        AnalysisResult.new(
            request=request,
            computation=replace(computation, request_digest="e" * 64),
            lineage=lineage,
        )
    with pytest.raises(AnalysisError):
        AnalysisResult.new(
            request=request,
            computation=computation,
            lineage=replace(lineage, target_device="host:other"),
        )
    tampered = result.to_dict()
    tampered["analysis_id"] = "0" * 64
    with pytest.raises(AnalysisError):
        AnalysisResult.from_value(tampered)


@pytest.mark.parametrize("label", ["change-observed", "no-change-observed", "analysis-inconclusive"])
def test_marker_labels_ids_nfc_bounds_and_no_generic_evidence_field(tmp_path: Path, label: str) -> None:
    _, _, _, result = _authoritative_case(tmp_path)
    marker = DiagnosticMarker.new(
        analysis_id=result.analysis_id,
        analysis_evidence_id="e" * 64,
        diagnostic_session_id="f" * 32,
        hypothesis_id="1" * 32,
        polarity="refutes" if label == "no-change-observed" else "supports",
        label=label,
        rationale="é",
    )
    assert len(marker.marker_id) == 64
    assert len(marker.diagnostic_session_id) == 32
    assert len(marker.hypothesis_id) == 32
    assert "evidence_id" not in marker.to_dict()
    changed = marker.to_dict()
    changed["rationale"] = "different"
    with pytest.raises(AnalysisError):
        DiagnosticMarker.from_value(changed)
    with pytest.raises(AnalysisError):
        replace(marker, rationale="e\u0301")
    with pytest.raises(AnalysisError):
        replace(marker, rationale="x" * 4097)


@pytest.mark.parametrize("kind", ["lineage", "result", "evidence", "marker"])
def test_authoritative_values_reject_subclasses_tuples_and_unknown_fields(tmp_path: Path, kind: str) -> None:
    _, _, lineage, result = _authoritative_case(tmp_path)
    value = {
        "lineage": lineage,
        "result": result,
        "evidence": AnalysisEvidenceRef.new(analysis_id=result.analysis_id, evidence_id="e" * 64),
        "marker": DiagnosticMarker.new(
            analysis_id=result.analysis_id, analysis_evidence_id="e" * 64,
            diagnostic_session_id="f" * 32, hypothesis_id="1" * 32,
            polarity="supports", label="change-observed", rationale="x",
        ),
    }[kind]
    cls = type(value)
    subclass = type(f"{kind.title()}Subclass", (cls,), {})
    instance = subclass(*(getattr(value, item.name) for item in fields(cls)))
    with pytest.raises(AnalysisError):
        cls.from_value(instance)
    unknown = value.to_dict()
    unknown["unknown"] = True
    with pytest.raises(AnalysisError):
        cls.from_value(unknown)
    tuple_payload = value.to_dict()
    tuple_payload[next(iter(tuple_payload))] = ("tuple",)
    with pytest.raises(AnalysisError):
        cls.from_value(tuple_payload)


def test_authoritative_values_reject_malformed_numeric_and_id_fields(tmp_path: Path) -> None:
    _, _, lineage, result = _authoritative_case(tmp_path)
    lineage_payload = lineage.to_dict()
    lineage_payload["target_device"] = "\u0000"
    with pytest.raises(AnalysisError):
        AnalysisLineage.from_value(lineage_payload)
    evidence = AnalysisEvidenceRef.new(analysis_id=result.analysis_id, evidence_id="e" * 64).to_dict()
    evidence["analysis_id"] = "A" * 64
    with pytest.raises(AnalysisError):
        AnalysisEvidenceRef.from_value(evidence)
    marker = DiagnosticMarker.new(
        analysis_id=result.analysis_id, analysis_evidence_id="e" * 64,
        diagnostic_session_id="f" * 32, hypothesis_id="1" * 32,
        polarity="supports", label="change-observed", rationale="x",
    ).to_dict()
    marker["hypothesis_id"] = "1" * 31
    with pytest.raises(AnalysisError):
        DiagnosticMarker.from_value(marker)
    result_payload = result.to_dict()
    result_payload["aligned_pair_count"] = True
    with pytest.raises(AnalysisError):
        AnalysisResult.from_value(result_payload)
