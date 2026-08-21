from __future__ import annotations

import json
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
import stm32_monitor.analysis_workflows as workflows

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis import analyze_monitor_windows
from stm32_monitor.analysis_workflows import (
    AnalysisPublication,
    AnalysisWorkflowError,
    compare_monitor_runs,
)
from stm32_monitor.history import HistoryQuery, HistoryPage, HistoryStore
from stm32_monitor.models import HistoryBatchSlice, SampleBatch
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    MonitorReplayDocument,
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.diagnostics import DiagnosticMarkerRef, SourceChangeDeclaration
from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import get_root, plan_gc
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths


FIXTURES = Path(__file__).parent / "fixtures" / "vs03"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
RUN_IDS = {
    "failed-before": UUID("33333333-3333-4333-8333-333333333333"),
    "fixed-after": UUID("44444444-4444-4444-8444-444444444444"),
}
HYPOTHESIS_ID = "1" * 32


def _paths(tmp_path: Path, session_id: str = "analysis-import") -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, PROJECT_ID, session_id)


def _evidence(paths: WorkspacePaths) -> EvidenceStore:
    return EvidenceStore(paths.workspace_root / "evidence")


def _fixture(role: str) -> Path:
    return FIXTURES / f"{role}.json"


def _document(role: str) -> MonitorReplayDocument:
    raw = _fixture(role).read_bytes()
    return MonitorReplayDocument.from_value(json.loads(raw.rstrip(b"\n").decode("utf-8")))


def _operation(role: str) -> str:
    return str(RUN_IDS[role])


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


def _ingest_pair(paths: WorkspacePaths) -> tuple[EvidenceStore, MonitorRunRef, MonitorRunRef]:
    evidence = _evidence(paths)
    before = ingest_monitor_replay(paths, evidence, _operation("failed-before"), _fixture("failed-before"))
    after = ingest_monitor_replay(paths, evidence, _operation("fixed-after"), _fixture("fixed-after"))
    return evidence, before, after


def _declaration(
    tmp_path: Path,
    evidence: EvidenceStore,
    before: MonitorRunRef,
    after: MonitorRunRef,
    *,
    hypothesis_id: str = HYPOTHESIS_ID,
    mutate: dict[str, object] | None = None,
) -> SourceChangeDeclaration:
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(b"--- a/src/main.c\n+++ b/src/main.c\n")
    artifact = evidence.ingest_file(diff_path, kind="source-diff", media_type="text/x-diff")
    identity = EvidenceIdentity(
        workspace_id=after.origin_workspace_id,
        project_id=after.logical_project_id,
        session_id=after.origin_session_id,
        build_id=before.build_id,
        elf_sha256=before.elf_sha256,
        target_device=after.target_device,
        input_snapshot_sha256=before.input_snapshot_sha256,
        git_commit=before.git_head,
        git_dirty=before.git_dirty,
    )
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-08-21T12:00:00.000000Z",
        parents=(),
        artifacts=(artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(envelope)
    values: dict[str, object] = {
        "before_source_sha256": before.input_snapshot_sha256,
        "after_source_sha256": after.input_snapshot_sha256,
        "before_build_id": before.build_id,
        "before_elf_sha256": before.elf_sha256,
        "after_build_id": after.build_id,
        "after_elf_sha256": after.elf_sha256,
        "changed_paths": ("src/main.c",),
        "diff_evidence_id": str(envelope.evidence_id),
        "diff_artifact": artifact,
        "claimed_hypothesis_ids": (hypothesis_id,),
        "validation_plan_id": "2" * 64,
    }
    if mutate:
        values.update(mutate)
    return SourceChangeDeclaration.new(**values)


def _history_batches(paths: WorkspacePaths, run_id: UUID) -> tuple[SampleBatch, ...]:
    history = HistoryStore(paths)
    try:
        result = history.query_history(
            HistoryQuery(
                session_id=paths.session_id,
                start_ns=0,
                end_ns=(1 << 63) - 1,
                run_id=run_id,
                limit=10_000,
            )
        )
        assert result.ok and result.data is not None, result.to_dict()
        assert result.data.next_cursor is None
        return tuple(
            SampleBatch(
                binding=batch.binding,
                group_id=batch.group_id,
                group_revision=batch.group_revision,
                run_id=batch.run_id,
                sequence=batch.sequence,
                scheduled_unix_ns=batch.scheduled_unix_ns,
                captured_unix_ns=batch.captured_unix_ns,
                latency_ns=batch.latency_ns,
                actual_rate_hz=batch.actual_rate_hz,
                subscriber_drops=batch.subscriber_drops,
                history_drops=batch.history_drops,
                deadline_drops=batch.deadline_drops,
                values=batch.values,
            )
            for batch in result.data.batches
        )
    finally:
        history.close()


def _write_same_firmware_after(tmp_path: Path) -> Path:
    """Build a canonical fixed-after replay with the failed-before firmware identity."""

    before = _document("failed-before")
    after = _document("fixed-after")
    unsigned = after.to_dict()
    unsigned["binding"] = before.binding.to_dict()
    unsigned["batches"] = [
        replace(batch, binding=before.binding).to_dict() for batch in after.batches
    ]
    unsigned.pop("fixture_sha256")
    payload = dict(unsigned)
    payload["fixture_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    target = tmp_path / "fixed-after-identical.json"
    target.write_bytes(canonical_replay_json_bytes(payload) + b"\n")
    return target


def _evidence_tree(evidence: EvidenceStore) -> dict[str, bytes]:
    if not evidence.root.exists():
        return {}
    return {
        str(path.relative_to(evidence.root)): path.read_bytes()
        for path in evidence.root.rglob("*")
        if path.is_file()
    }


def _publish(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    before: MonitorRunRef,
    after: MonitorRunRef,
    declaration: SourceChangeDeclaration | None,
    *,
    minimum: int = 2,
    diagnostic_session_id: str = "f" * 32,
    hypothesis_id: str = HYPOTHESIS_ID,
    polarity: str = "supports",
    rationale: str = "the fixed replay changed the observed counter",
) -> AnalysisPublication:
    return compare_monitor_runs(
        paths,
        evidence,
        _request(before, after, minimum=minimum),
        diagnostic_session_id,
        hypothesis_id,
        polarity,
        rationale,
        declaration,
    )


def test_compare_monitor_runs_publishes_changed_analysis_and_marker(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)

    publication = compare_monitor_runs(
        paths,
        evidence,
        _request(before, after),
        "f" * 32,
        HYPOTHESIS_ID,
        "supports",
        "the fixed replay changed the observed counter",
        declaration,
    )

    assert type(publication) is AnalysisPublication
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.conclusion == "COMPLETED"
    assert publication.analysis_result.changed is True
    assert publication.analysis_evidence_ref.analysis_id == publication.analysis_result.analysis_id
    assert publication.diagnostic_marker.analysis_id == publication.analysis_result.analysis_id
    assert publication.diagnostic_marker.label == "change-observed"
    assert type(publication.diagnostic_marker_ref) is DiagnosticMarkerRef
    assert publication.diagnostic_marker_ref.marker_id == publication.diagnostic_marker.marker_id
    assert publication.diagnostic_marker_ref.marker_evidence_id

    analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    marker_root = get_root(evidence, "diagnostic-marker", publication.diagnostic_marker.marker_id)
    analysis_envelope = evidence.get_envelope(analysis_root.manifest_id)
    marker_envelope = evidence.get_envelope(marker_root.manifest_id)
    assert analysis_envelope.parents == (
        before.transcript_evidence_id,
        after.transcript_evidence_id,
        declaration.diff_evidence_id,
    )
    assert marker_envelope.parents == (analysis_root.manifest_id,)
    assert analysis_root.metadata["origin_workspace_id"] == after.origin_workspace_id
    assert analysis_root.metadata["import_workspace_id"] == paths.workspace_id
    assert analysis_envelope.identity.workspace_id == after.origin_workspace_id
    assert analysis_envelope.identity.session_id == after.origin_session_id
    assert analysis_envelope.identity.workspace_id != paths.workspace_id
    assert plan_gc(evidence).reachable_manifests


def test_publication_fields_identity_and_transcript_metadata_are_exact(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    publication = _publish(paths, evidence, before, after, declaration)

    assert [field.name for field in fields(AnalysisPublication)] == [
        "analysis_result",
        "analysis_evidence_ref",
        "diagnostic_marker",
        "diagnostic_marker_ref",
    ]
    assert not hasattr(publication, "__dict__")
    assert {
        "fixture_sha256",
        "run_ref_sha256",
        "origin_workspace_id",
        "import_workspace_id",
        "execution_source",
        "physical_transport_evidence",
    } == set(get_root(evidence, "monitor-run", before.operation_id).metadata)
    for reference, role in ((before, "failed-before"), (after, "fixed-after")):
        envelope = evidence.get_envelope(reference.transcript_evidence_id)
        assert {
            "operation_id",
            "scenario_role",
            "origin_workspace_id",
            "import_workspace_id",
            "origin_run_id",
            "projected_run_id",
            "fixture_sha256",
            "execution_source",
            "physical_transport_evidence",
        } == set(envelope.metadata)
        assert envelope.metadata["scenario_role"] == role
        assert envelope.identity.workspace_id == reference.origin_workspace_id
        assert envelope.identity.session_id == reference.origin_session_id
        assert evidence.read_artifact(
            envelope.artifacts[0], maximum_bytes=64 * 1024 * 1024
        ) == _fixture(role).read_bytes()
    analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    assert analysis_root.manifest_id == publication.analysis_evidence_ref.evidence_id
    assert analysis_root.metadata["origin_workspace_id"] == after.origin_workspace_id
    assert analysis_root.metadata["import_workspace_id"] == paths.workspace_id
    assert analysis_root.metadata["execution_source"] == "replay"
    assert analysis_root.metadata["physical_transport_evidence"] is False


def test_insufficient_pairs_are_published_as_retained_inconclusive_result(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)

    publication = _publish(paths, evidence, before, after, declaration, minimum=3)

    result = publication.analysis_result
    assert result.quality == "INVALID"
    assert result.conclusion == "INCONCLUSIVE"
    assert result.reason_code == "INSUFFICIENT_VALID_PAIRS"
    assert result.aligned_pair_count == 2
    assert result.changed is None
    assert publication.diagnostic_marker.label == "analysis-inconclusive"
    assert get_root(evidence, "monitor-analysis", result.analysis_id)
    assert get_root(evidence, "diagnostic-marker", publication.diagnostic_marker.marker_id)


def test_identical_firmware_replay_publishes_without_a_source_declaration(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    before = ingest_monitor_replay(paths, evidence, _operation("failed-before"), _fixture("failed-before"))
    identical_after_path = _write_same_firmware_after(tmp_path)
    after = ingest_monitor_replay(paths, evidence, _operation("fixed-after"), identical_after_path)

    publication = _publish(paths, evidence, before, after, None)

    assert publication.analysis_result.identity.source_change_declaration_id is None
    assert publication.analysis_result.changed is True
    assert publication.diagnostic_marker.label == "change-observed"
    analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    analysis_envelope = evidence.get_envelope(analysis_root.manifest_id)
    assert analysis_envelope.parents == (
        before.transcript_evidence_id,
        after.transcript_evidence_id,
    )


@pytest.mark.parametrize("missing_piece", ("root", "manifest", "artifact"))
def test_repeat_fresh_reload_and_partial_marker_publication_repair_is_idempotent(
    tmp_path: Path, missing_piece: str
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)

    first = _publish(paths, evidence, before, after, declaration)
    before_repeat = _evidence_tree(evidence)
    second = _publish(paths, evidence, before, after, declaration)
    assert second == first
    assert _evidence_tree(evidence) == before_repeat

    marker_root = get_root(evidence, "diagnostic-marker", first.diagnostic_marker.marker_id)
    marker_envelope = evidence.get_envelope(marker_root.manifest_id)
    if missing_piece == "root":
        next((evidence.root / "roots" / "diagnostic-marker").glob("*.json")).unlink()
    elif missing_piece == "manifest":
        (evidence.root / "manifests" / f"{marker_root.manifest_id}.json").unlink()
    else:
        artifact = marker_envelope.artifacts[0]
        (evidence.root / "objects" / "sha256" / artifact.sha256[:2] / artifact.sha256).unlink()
    repaired = _publish(paths, evidence, before, after, declaration)
    assert repaired == first
    assert get_root(evidence, "diagnostic-marker", first.diagnostic_marker.marker_id)

    fresh = EvidenceStore(evidence.root)
    assert _publish(paths, fresh, before, after, declaration) == first


def test_different_bytes_at_existing_analysis_root_are_an_operation_conflict(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    first = _publish(paths, evidence, before, after, declaration)
    root = get_root(evidence, "monitor-analysis", first.analysis_result.analysis_id)
    altered = root.to_dict()
    altered_metadata = dict(cast(dict[str, object], altered["metadata"]))
    altered_metadata["origin_workspace_id"] = "9" * 64
    altered["metadata"] = altered_metadata
    root_file = next((evidence.root / "roots" / "monitor-analysis").glob("*.json"))
    root_file.write_bytes(canonical_replay_json_bytes(altered))
    before_retry = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)
    assert error.value.code == "OPERATION_CONFLICT"
    assert _evidence_tree(evidence) == before_retry


def test_public_query_pages_are_coalesced_and_validated_against_frozen_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    original = HistoryStore.query_history

    def one_value_page(self: HistoryStore, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        return original(self, replace(query, limit=1))

    monkeypatch.setattr(HistoryStore, "query_history", one_value_page)
    publication = _publish(paths, evidence, before, after, declaration)
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.aligned_pair_count == 2


def test_history_digest_contradiction_is_rejected_without_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def contradictory_page(self: HistoryStore, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        result = original(self, query)
        if calls == 0 and result.ok and result.data is not None:
            page = result.data
            first = page.batches[0]
            value = replace(
                first.values[0],
                typed_value={"type": "uint32", "value": 999},
            )
            corrupted = replace(first, values=(value, *first.values[1:]))
            page = HistoryPage.create(
                (corrupted, *page.batches[1:]),
                next_cursor=page.next_cursor,
            )
            result = ProtocolResult(
                True, result.operation, "OK", "", page, protocol=result.protocol
            )
        calls += 1
        return result

    monkeypatch.setattr(HistoryStore, "query_history", contradictory_page)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


@pytest.mark.parametrize(
    ("label", "kwargs", "expected"),
    [
        ("polarity", {"polarity": "maybe"}, "ANALYSIS_WORKFLOW_INVALID"),
        ("missing declaration", {"declaration": None}, "INCOMPATIBLE_IDENTITY"),
        ("wrong hypothesis", {"hypothesis_id": "2" * 32}, "INCOMPATIBLE_IDENTITY"),
    ],
)
def test_prepublication_rejections_leave_evidence_unchanged(
    tmp_path: Path,
    label: str,
    kwargs: dict[str, object],
    expected: str,
) -> None:
    del label
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    supplied = cast(SourceChangeDeclaration | None, kwargs.pop("declaration", declaration))

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(
            paths,
            evidence,
            before,
            after,
            supplied,
            hypothesis_id=cast(str, kwargs.pop("hypothesis_id", HYPOTHESIS_ID)),
            polarity=cast(str, kwargs.pop("polarity", "supports")),
        )
    assert error.value.code == expected
    assert _evidence_tree(evidence) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()
    assert not (evidence.root / "roots" / "diagnostic-marker").exists()


def test_import_workspace_and_role_contradictions_fail_before_publication(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)

    different_session = WorkspacePaths.from_roots(
        paths.data_root, paths.project_root, PROJECT_ID, "other-import"
    )
    with pytest.raises(AnalysisWorkflowError) as scope_error:
        _publish(different_session, evidence, before, after, declaration)
    assert scope_error.value.code == "INCOMPATIBLE_IDENTITY"

    payload = after.to_dict()
    payload["scenario_role"] = "failed-before"
    unsigned = dict(payload)
    unsigned.pop("run_ref_sha256")
    payload["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    wrong_role = MonitorRunRef.from_value(payload)
    with pytest.raises(AnalysisWorkflowError) as role_error:
        _publish(paths, evidence, before, wrong_role, declaration)
    assert role_error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree


def test_transcript_run_reference_group_contradiction_is_rejected_before_derived_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    original_request = _request(before, after)
    before_batches = _history_batches(paths, UUID(before.projected_run_id))
    after_batches = _history_batches(paths, UUID(after.projected_run_id))
    valid_computation = analyze_monitor_windows(original_request, before_batches, after_batches)

    payload = before.to_dict()
    payload["group_revision"] = before.group_revision + 1
    unsigned = dict(payload)
    unsigned.pop("run_ref_sha256")
    payload["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    contradictory_before = MonitorRunRef.from_value(payload)
    root_file = None
    for candidate in (evidence.root / "roots" / "monitor-run").glob("*.json"):
        candidate_payload = json.loads(candidate.read_bytes().decode("utf-8"))
        if candidate_payload["metadata"]["fixture_sha256"] == before.fixture_sha256:
            root_file = candidate
            break
    assert root_file is not None
    root_payload = json.loads(root_file.read_bytes().decode("utf-8"))
    root_payload["metadata"]["run_ref_sha256"] = contradictory_before.run_ref_sha256
    root_file.write_bytes(canonical_replay_json_bytes(root_payload))

    monkeypatch.setattr(workflows, "analyze_monitor_windows", lambda *args: valid_computation)
    before_tree = _evidence_tree(evidence)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, contradictory_before, after, declaration)
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert _evidence_tree(evidence) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_derived_provider_exception_is_bounded_and_exact_artifact_prefix_retries(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    state = {"enabled": True}

    def fail_after_artifact_publish(point: str) -> None:
        if state["enabled"] and point == "artifact.after_publish":
            raise RuntimeError("provider-private-secret")

    faulty = EvidenceStore(evidence.root, fault_injector=fail_after_artifact_publish)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, faulty, before, after, declaration)
    assert error.value.code == "ENVIRONMENT_FAILURE"
    assert "provider-private-secret" not in str(error.value)
    assert not (evidence.root / "roots" / "monitor-analysis").exists()

    state["enabled"] = False
    repaired = _publish(paths, faulty, before, after, declaration)
    assert repaired.analysis_result.quality == "VALID"
    assert get_root(evidence, "monitor-analysis", repaired.analysis_result.analysis_id)


def test_transcript_artifact_io_failure_is_environment_error_without_derived_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original_read = EvidenceStore.read_artifact

    def fail_transcript_read(
        store: EvidenceStore, artifact: ArtifactRef, *, maximum_bytes: int
    ) -> bytes:
        if artifact.kind == "monitor-replay-transcript":
            raise OSError("provider-private-secret")
        return original_read(store, artifact, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(EvidenceStore, "read_artifact", fail_transcript_read)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)
    assert error.value.code == "ENVIRONMENT_FAILURE"
    assert "provider-private-secret" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()
