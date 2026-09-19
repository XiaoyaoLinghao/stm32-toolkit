from __future__ import annotations

from collections.abc import Mapping
import json
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
import stm32_monitor.analysis_workflows as workflows

from stm32_monitor.analysis import AnalysisEvidenceRef, AnalysisRequest, DiagnosticMarker
from stm32_monitor.analysis import analyze_monitor_windows
from stm32_monitor.analysis_workflows import (
    AnalysisBundleRef,
    AnalysisPublication,
    AnalysisWorkflowError,
    ANALYSIS_WORKFLOW_INVALID,
    ENVIRONMENT_FAILURE,
    EVIDENCE_INTEGRITY_FAILURE,
    compare_monitor_runs,
    export_analysis_bundle,
)
from stm32_monitor.history import HistoryQuery, HistoryPage, HistoryStore
from stm32_monitor.models import HistoryBatchSlice, SampleBatch
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    MonitorReplayDocument,
    MonitorRunRef,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.diagnostics import DiagnosticMarkerRef, SourceChangeDeclaration
from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import get_root, plan_gc
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.model import TestCaseResult, TestRunManifest, calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunPublisher
from stm32_toolkit.testing.replay import (
    TargetReplayDescriptor,
    calculate_replay_id,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from test_acceptance_continuation import prepare_pair
from test_continuation_monitor import _monitor_baseline
from test_physical_publication import (
    _append_physical_history,
    _physical_context,
    _publish_physical_test_run,
)
from stm32_monitor.replay import load_monitor_run_reference, publish_physical_monitor_run


def test_analysis_bundle_ref_is_closed_and_content_addressed():
    payload = b'{"schema":"stm32-monitor-analysis-bundle/1"}'
    digest = sha256(payload).hexdigest()
    artifact = ArtifactRef(
        sha256=digest, size_bytes=len(payload),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind="monitor-analysis-bundle", media_type="application/json",
    )
    ref = AnalysisBundleRef("stm32-monitor-analysis-bundle-ref/1", digest, "a" * 64, artifact)
    assert ref.to_dict()["artifact"] == artifact.to_dict()
    assert AnalysisBundleRef.from_value(ref.to_dict()) == ref
    with pytest.raises(AnalysisWorkflowError):
        AnalysisBundleRef("stm32-monitor-analysis-bundle-ref/1", "A" * 64, "a" * 64, artifact)

    malformed_artifact = artifact.to_dict()
    malformed_artifact["kind"] = "other-evidence"
    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisBundleRef.from_value(
            {
                "schema": "stm32-monitor-analysis-bundle-ref/1",
                "bundle_id": digest,
                "evidence_id": "a" * 64,
                "artifact": malformed_artifact,
            }
        )
    assert error.value.code == "ANALYSIS_WORKFLOW_INVALID"


def test_export_analysis_bundle_reloads_real_target_runs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    payload, ref = workflows.export_analysis_bundle(
        paths, evidence, _request(before, after), publication, failed_id, fixed_id, declaration
    )
    body = json.loads(payload.decode("utf-8"))
    assert list(body) == sorted(["schema", "before_run", "after_run", "analysis_request",
        "analysis_result", "analysis_evidence_ref", "diagnostic_marker",
        "diagnostic_marker_ref", "failed_before_test_run_id", "fixed_after_test_run_id",
        "source_change_declaration_id", "digest_table"])
    assert ref.bundle_id == sha256(payload).hexdigest()
    bundle_root = get_root(evidence, "monitor-analysis-bundle", ref.bundle_id)
    bundle = evidence.get_envelope(bundle_root.manifest_id)
    assert bundle.parents == (before.transcript_evidence_id, after.transcript_evidence_id,
        publication.analysis_evidence_ref.evidence_id, publication.diagnostic_marker_ref.marker_evidence_id,
        declaration.diff_evidence_id)
    assert evidence.read_artifact(ref.artifact, maximum_bytes=1_000_000) == payload
    again, same_ref = workflows.export_analysis_bundle(
        paths, evidence, _request(before, after), publication, failed_id, fixed_id, declaration
    )
    assert (again, same_ref) == (payload, ref)


@pytest.mark.parametrize("case", ["missing-analysis", "forged-marker"])
def test_export_analysis_bundle_rejects_upstream_contradiction_without_bundle_mutation(
    tmp_path: Path, case: str
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    if case == "missing-analysis":
        analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
        artifact = evidence.get_envelope(analysis_root.manifest_id).artifacts[0]
        (evidence.root / artifact.relative_path).unlink()
        expected = EVIDENCE_INTEGRITY_FAILURE
    else:
        forged = replace(publication.diagnostic_marker_ref, marker_evidence_id="a" * 64)
        publication = AnalysisPublication(publication.analysis_result, publication.analysis_evidence_ref,
                                          publication.diagnostic_marker, forged)
        expected = EVIDENCE_INTEGRITY_FAILURE
    with pytest.raises(AnalysisWorkflowError) as error:
        workflows.export_analysis_bundle(paths, evidence, _request(before, after), publication,
                                         failed_id, fixed_id, declaration)
    assert error.value.code == expected
    assert not any("monitor-analysis-bundle" in path for path in _evidence_tree(evidence))


def test_export_analysis_bundle_maps_source_provider_failure_without_bundle_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    before_tree = _evidence_tree(evidence)
    original_read = EvidenceStore.read_artifact

    def fail_source_diff(
        store: EvidenceStore, artifact: ArtifactRef, *, maximum_bytes: int
    ) -> bytes:
        if artifact.kind == "source-diff":
            raise OSError("private source provider")
        return original_read(store, artifact, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(EvidenceStore, "read_artifact", fail_source_diff)
    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )
    assert error.value.code == ENVIRONMENT_FAILURE
    assert "private source provider" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis-bundle" in path for path in _evidence_tree(evidence))


def test_export_analysis_bundle_maps_target_provider_failure_without_bundle_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    before_tree = _evidence_tree(evidence)
    calls: list[str] = []

    def fail_target_load(self: object, run_id: str) -> object:
        del self
        calls.append(run_id)
        raise OSError("private target provider")

    monkeypatch.setattr(workflows.TestRunRepository, "load", fail_target_load)
    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )

    assert calls == [failed_id]
    assert error.value.code == ENVIRONMENT_FAILURE
    assert "private target provider" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis-bundle" in path for path in _evidence_tree(evidence))


@pytest.mark.parametrize(
    "case",
    ("publication-type", "run-id-type", "request", "lineage", "replay-test-run"),
)
def test_export_analysis_bundle_rejects_public_mismatches_before_bundle_write(
    tmp_path: Path, case: str
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    request = _request(before, after)
    export_declaration = declaration
    if case == "request":
        request = _request(before, after, minimum=3)
    elif case == "lineage":
        export_declaration = _declaration(
            tmp_path,
            evidence,
            before,
            after,
            mutate={"validation_plan_id": "3" * 64},
        )

    before_tree = _evidence_tree(evidence)
    with pytest.raises(AnalysisWorkflowError) as error:
        if case == "publication-type":
            export_analysis_bundle(
                paths,
                evidence,
                _request(before, after),
                object(),
                failed_id,
                fixed_id,
                declaration,
            )
        elif case == "run-id-type":
            export_analysis_bundle(
                paths,
                evidence,
                request,
                publication,
                1,
                fixed_id,
                export_declaration,
            )
        else:
            export_analysis_bundle(
                paths,
                evidence,
                request,
                publication,
                fixed_id if case == "replay-test-run" else failed_id,
                fixed_id,
                export_declaration,
            )

    assert error.value.code == (
        ANALYSIS_WORKFLOW_INVALID
        if case in {"publication-type", "run-id-type"}
        else "INCOMPATIBLE_IDENTITY"
    )
    assert error.value.message == {
        "publication-type": "analysis publication is invalid",
        "run-id-type": "test run IDs are invalid",
        "request": "analysis request does not match publication",
        "lineage": "analysis lineage does not match publication",
        "replay-test-run": "TestRun does not match replay reference",
    }[case]
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis-bundle" in path for path in _evidence_tree(evidence))


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


def _publish_target_pair(paths: WorkspacePaths, evidence: EvidenceStore) -> tuple[str, str]:
    target_dir = Path(__file__).parents[2] / "stm32-toolkit" / "tests" / "fixtures" / "vs03" / "target"
    publisher = TestRunPublisher(evidence, paths.project_root, paths.data_root.parent / "target-results")
    run_ids = ("vs03-failed-before", "vs03-fixed-after")
    for role, run_id in zip(("failed-before", "fixed-after"), run_ids):
        fixture = load_target_replay_fixture(target_dir / f"{role}.json", target_dir / f"{role}.hex")
        descriptor_path = paths.project_root / f"{role}.json"
        descriptor_path.write_bytes((target_dir / f"{role}.json").read_bytes())
        descriptor_artifact = evidence.ingest_file(descriptor_path, kind="target-replay-descriptor", media_type="application/json")
        stream_path = paths.project_root / f"{role}.bin"
        stream_path.write_bytes(fixture.stream_bytes)
        stream_artifact = evidence.ingest_file(stream_path, kind="target-replay-stream", media_type="application/octet-stream")
        descriptor = EvidenceEnvelope(
            identity=fixture.descriptor.identity, operation="target-replay-input",
            produced_at_utc="2026-08-21T00:00:00.000000Z", parents=(),
            artifacts=(descriptor_artifact, stream_artifact), metadata={
                "replay_id": fixture.descriptor.replay_id, "scenario_role": role,
                "stream_sha256": fixture.descriptor.stream.sha256,
                "stream_size_bytes": fixture.descriptor.stream.size_bytes,
                "execution_source": "replay", "physical_transport_evidence": False,
                "origin_workspace_id": fixture.descriptor.identity.workspace_id,
                "import_workspace_id": paths.workspace_id,
            })
        frames = TargetFrameDecoder().feed(fixture.stream_bytes)
        decoder = TargetFrameDecoder(); frames = decoder.feed(fixture.stream_bytes); decoder.finish()
        starts = {str(f.payload["case_id"]): f.payload for f in frames if f.kind == 3}
        cases = tuple(TestCaseResult(str(f.payload["case_id"]), str(f.payload["state"]),
            str(starts[str(f.payload["case_id"])] ["started_at_utc"]), str(f.payload["ended_at_utc"]),
            int(f.payload["duration_ms"]), f.payload["message"], None, None)
            for f in frames if f.kind == 4)
        raw_path = paths.project_root / f"{role}.events"
        raw_path.write_bytes(fixture.stream_bytes)
        raw = evidence.ingest_file(raw_path, kind="test-events", media_type="application/vnd.stm32.target-events")
        manifest = TestRunManifest("stm32-test/1", run_id, "target", str(frames[-1].payload["state"]),
            fixture.descriptor.identity, "replay", cases, str(frames[1].payload["started_at_utc"]),
            str(frames[-1].payload["ended_at_utc"]), int(frames[-1].payload["duration_ms"]), None, None, raw)
        publisher.publish_target_replay(manifest, descriptor, paths.workspace_id)
    return run_ids


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
    identity_override: EvidenceIdentity | None = None,
) -> SourceChangeDeclaration:
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(b"--- a/src/main.c\n+++ b/src/main.c\n")
    artifact = evidence.ingest_file(diff_path, kind="source-diff", media_type="text/x-diff")
    identity = identity_override or EvidenceIdentity(
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


def _monitor_ref_root_path(evidence: EvidenceStore, operation_id: str) -> Path:
    roots = tuple((evidence.root / "roots" / "monitor-run-ref").glob("*.json"))
    assert len(roots) == 2
    for path in roots:
        if get_root(evidence, "monitor-run-ref", operation_id).to_dict() == json.loads(
            path.read_text(encoding="utf-8")
        ):
            return path
    raise AssertionError("monitor reference root was not found")


def _monitor_run_root_path(evidence: EvidenceStore, operation_id: str) -> Path:
    directory = evidence.root / "roots" / "monitor-run"
    for path in directory.glob("*.json"):
        if json.loads(path.read_bytes().decode("utf-8"))["root_id"] == operation_id:
            return path
    raise AssertionError("monitor run root was not found")


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


def _synthetic_changed_after(before: MonitorRunRef) -> MonitorRunRef:
    """Create a valid changed-firmware reference for declaration setup only."""

    document = _document("fixed-after")
    values = before.to_dict()
    operation_id = str(UUID("55555555-5555-4555-8555-555555555555"))
    values.update(
        operation_id=operation_id,
        scenario_role="fixed-after",
        origin_run_id=operation_id,
        projected_run_id=operation_id,
        build_id=document.binding.build_id,
        elf_sha256=document.binding.elf_sha256,
        input_snapshot_sha256=document.binding.input_snapshot_sha256,
        git_head=document.binding.git_head,
        fixture_sha256=document.fixture_sha256,
        transcript_evidence_id="b" * 64,
        projected_batch_sha256s=list(before.projected_batch_sha256s),
    )
    unsigned = {key: value for key, value in values.items() if key != "run_ref_sha256"}
    values["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    return MonitorRunRef.from_value(values)


def _data_tree(paths: WorkspacePaths) -> dict[str, bytes]:
    if not paths.data_root.exists():
        return {}
    return {
        str(path.relative_to(paths.data_root)): path.read_bytes()
        for path in paths.data_root.rglob("*")
        if path.is_file()
    }


def _thaw_target_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_target_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_target_value(item) for item in value]
    return value


def _target_stream_for_identity(
    fixture: object, identity: EvidenceIdentity
) -> tuple[TargetReplayDescriptor, bytes]:
    descriptor = cast(TargetReplayDescriptor, getattr(fixture, "descriptor"))
    stream_bytes = cast(bytes, getattr(fixture, "stream_bytes"))
    if descriptor.identity == identity:
        return descriptor, stream_bytes

    decoder = TargetFrameDecoder()
    frames = decoder.feed(stream_bytes)
    decoder.finish()
    inventory = cast(dict[str, object], _thaw_target_value(frames[0].payload))
    case_ids = cast(list[str], inventory["case_ids"])
    inventory_digest = calculate_inventory_digest("target", identity, case_ids)
    rebuilt: list[bytes] = []
    for frame in frames[:-1]:
        payload = cast(dict[str, object], _thaw_target_value(frame.payload))
        if frame.kind == 1:
            payload["identity"] = identity.to_dict()
            payload["inventory_digest"] = inventory_digest
        elif frame.kind == 2:
            payload["inventory_digest"] = inventory_digest
        rebuilt.append(
            encode_frame(frame.kind, frame.sequence, payload, version=frame.version)
        )
    stream_digest = sha256(b"".join(rebuilt)).hexdigest()
    terminal = cast(dict[str, object], _thaw_target_value(frames[-1].payload))
    terminal.update(
        inventory_digest=inventory_digest,
        build_id=identity.build_id,
        elf_sha256=identity.elf_sha256,
        target_device=identity.target_device,
        event_stream_digest=stream_digest,
    )
    rebuilt.append(
        encode_frame(
            frames[-1].kind,
            frames[-1].sequence,
            terminal,
            version=frames[-1].version,
        )
    )
    rebuilt_stream = b"".join(rebuilt)
    descriptor_payload = descriptor.to_dict()
    descriptor_payload["identity"] = identity.to_dict()
    descriptor_payload["inventory_digest"] = inventory_digest
    stream_payload = cast(dict[str, object], descriptor_payload["stream"])
    stream_payload.update(
        sha256=sha256(rebuilt_stream).hexdigest(),
        size_bytes=len(rebuilt_stream),
    )
    descriptor_payload["replay_id"] = "0" * 64
    descriptor_payload["replay_id"] = calculate_replay_id(descriptor_payload)
    return TargetReplayDescriptor.from_value(descriptor_payload), rebuilt_stream


def _publish_target_pair_variant(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    *,
    identity_overrides: Mapping[str, EvidenceIdentity] | None = None,
    import_workspace_overrides: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    target_dir = Path(__file__).parents[2] / "stm32-toolkit" / "tests" / "fixtures" / "vs03" / "target"
    publisher = TestRunPublisher(
        evidence, paths.project_root, paths.data_root.parent / "target-results"
    )
    run_ids = ("vs03-failed-before", "vs03-fixed-after")
    identity_overrides = {} if identity_overrides is None else dict(identity_overrides)
    import_workspace_overrides = (
        {} if import_workspace_overrides is None else dict(import_workspace_overrides)
    )
    for role, run_id in zip(("failed-before", "fixed-after"), run_ids):
        fixture = load_target_replay_fixture(
            target_dir / f"{role}.json", target_dir / f"{role}.hex"
        )
        identity = identity_overrides.get(role, fixture.descriptor.identity)
        descriptor_value, stream_bytes = _target_stream_for_identity(fixture, identity)
        descriptor_path = paths.project_root / f"{role}-variant.json"
        descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor_value.to_dict()))
        descriptor_artifact = evidence.ingest_file(
            descriptor_path,
            kind="target-replay-descriptor",
            media_type="application/json",
        )
        stream_path = paths.project_root / f"{role}-variant.bin"
        stream_path.write_bytes(stream_bytes)
        stream_artifact = evidence.ingest_file(
            stream_path,
            kind="target-replay-stream",
            media_type="application/octet-stream",
        )
        import_workspace_id = import_workspace_overrides.get(role, paths.workspace_id)
        descriptor_envelope = EvidenceEnvelope(
            identity=descriptor_value.identity,
            operation="target-replay-input",
            produced_at_utc="2026-08-21T00:00:00.000000Z",
            parents=(),
            artifacts=(descriptor_artifact, stream_artifact),
            metadata={
                "replay_id": descriptor_value.replay_id,
                "scenario_role": role,
                "stream_sha256": descriptor_value.stream.sha256,
                "stream_size_bytes": descriptor_value.stream.size_bytes,
                "execution_source": "replay",
                "physical_transport_evidence": False,
                "origin_workspace_id": descriptor_value.identity.workspace_id,
                "import_workspace_id": import_workspace_id,
            },
        )
        decoder = TargetFrameDecoder()
        frames = decoder.feed(stream_bytes)
        decoder.finish()
        starts = {
            str(frame.payload["case_id"]): frame.payload
            for frame in frames
            if frame.kind == 3
        }
        cases = tuple(
            TestCaseResult(
                str(frame.payload["case_id"]),
                str(frame.payload["state"]),
                str(starts[str(frame.payload["case_id"])] ["started_at_utc"]),
                str(frame.payload["ended_at_utc"]),
                int(frame.payload["duration_ms"]),
                frame.payload["message"],
                None,
                None,
            )
            for frame in frames
            if frame.kind == 4
        )
        raw_path = paths.project_root / f"{role}-variant.events"
        raw_path.write_bytes(stream_bytes)
        raw = evidence.ingest_file(
            raw_path,
            kind="test-events",
            media_type="application/vnd.stm32.target-events",
        )
        manifest = TestRunManifest(
            "stm32-test/1",
            run_id,
            "target",
            str(frames[-1].payload["state"]),
            descriptor_value.identity,
            "replay",
            cases,
            str(frames[1].payload["started_at_utc"]),
            str(frames[-1].payload["ended_at_utc"]),
            int(frames[-1].payload["duration_ms"]),
            None,
            None,
            raw,
        )
        publisher.publish_target_replay(manifest, descriptor_envelope, import_workspace_id)
    return run_ids


def _physical_pair(
    tmp_path: Path,
) -> tuple[WorkspacePaths, EvidenceStore, str, str, str, MonitorRunRefV2, MonitorRunRefV2]:
    paths, evidence, failed_test_run_id, raw_probe, failed_run_id, failed_group_id = (
        _physical_context(tmp_path)
    )
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=failed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=failed_run_id,
    )
    failed_batches = _append_physical_history(
        paths,
        raw_probe,
        failed_run_id,
        failed_group_id,
        scenario_role="failed-before",
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=failed_test_run_id,
        run_id=str(failed_run_id),
        group_id=str(failed_group_id),
        start_sequence=failed_batches[0].sequence,
        end_sequence_exclusive=failed_batches[-1].sequence + 1,
        start_captured_unix_ns=failed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=failed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    fixed_test_run_id = "physical-test-run-02"
    fixed_run_id = UUID("33333333-3333-4333-8333-333333333333")
    fixed_group_id = UUID("44444444-4444-4444-8444-444444444444")
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=fixed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=fixed_run_id,
        state="passed",
        build_id="0" * 64,
        elf_sha256="1" * 64,
        input_snapshot_sha256="2" * 64,
        git_head="f" * 40,
    )
    fixed_batches = _append_physical_history(
        paths,
        raw_probe,
        fixed_run_id,
        fixed_group_id,
        scenario_role="fixed-after",
        value_offset=10,
        build_id="0" * 64,
        elf_sha256="1" * 64,
        input_snapshot_sha256="2" * 64,
        git_head="f" * 40,
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="fixed-after",
        test_run_id=fixed_test_run_id,
        run_id=str(fixed_run_id),
        group_id=str(fixed_group_id),
        start_sequence=fixed_batches[0].sequence,
        end_sequence_exclusive=fixed_batches[-1].sequence + 1,
        start_captured_unix_ns=fixed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=fixed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    before = cast(MonitorRunRefV2, load_monitor_run_reference(paths, evidence, str(failed_run_id)))
    after = cast(MonitorRunRefV2, load_monitor_run_reference(paths, evidence, str(fixed_run_id)))
    return paths, evidence, failed_test_run_id, fixed_test_run_id, raw_probe, before, after


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


def test_compare_physical_runs_uses_transcripts_after_history_is_discarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, evidence, failed_test_run_id, raw_probe, failed_run_id, failed_group_id = (
        _physical_context(tmp_path)
    )
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=failed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=failed_run_id,
    )
    failed_batches = _append_physical_history(
        paths,
        raw_probe,
        failed_run_id,
        failed_group_id,
        scenario_role="failed-before",
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=failed_test_run_id,
        run_id=str(failed_run_id),
        group_id=str(failed_group_id),
        start_sequence=failed_batches[0].sequence,
        end_sequence_exclusive=failed_batches[-1].sequence + 1,
        start_captured_unix_ns=failed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=failed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    fixed_test_run_id = "physical-test-run-02"
    fixed_run_id = UUID("33333333-3333-4333-8333-333333333333")
    fixed_group_id = UUID("44444444-4444-4444-8444-444444444444")
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=fixed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=fixed_run_id,
        state="passed",
        build_id="0" * 64,
        elf_sha256="1" * 64,
        input_snapshot_sha256="2" * 64,
        git_head="f" * 40,
    )
    fixed_batches = _append_physical_history(
        paths,
        raw_probe,
        fixed_run_id,
        fixed_group_id,
        scenario_role="fixed-after",
        value_offset=10,
        build_id="0" * 64,
        elf_sha256="1" * 64,
        input_snapshot_sha256="2" * 64,
        git_head="f" * 40,
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="fixed-after",
        test_run_id=fixed_test_run_id,
        run_id=str(fixed_run_id),
        group_id=str(fixed_group_id),
        start_sequence=fixed_batches[0].sequence,
        end_sequence_exclusive=fixed_batches[-1].sequence + 1,
        start_captured_unix_ns=fixed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=fixed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    before = load_monitor_run_reference(paths, evidence, str(failed_run_id))
    after = load_monitor_run_reference(paths, evidence, str(fixed_run_id))

    class _HistoryMustNotBeRead:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("physical compare must not open Monitor History")

    monkeypatch.setattr(workflows, "HistoryStore", _HistoryMustNotBeRead)
    declaration = _declaration(tmp_path, evidence, before, after)
    publication = compare_monitor_runs(
        paths,
        evidence,
        _request(before, after),
        "f" * 32,
        HYPOTHESIS_ID,
        "supports",
        "the physical fixed run changed the observed counter",
        declaration,
    )

    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.conclusion == "COMPLETED"
    assert publication.analysis_result.changed is True
    analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    analysis_envelope = evidence.get_envelope(analysis_root.manifest_id)
    assert analysis_envelope.parents == (
        before.transcript_evidence_id,
        after.transcript_evidence_id,
        declaration.diff_evidence_id,
    )
    assert analysis_envelope.metadata["execution_source"] == "physical"
    assert analysis_envelope.metadata["physical_transport_evidence"] is True
    assert raw_probe.encode("utf-8") not in json.dumps(
        dict(analysis_envelope.metadata),
        sort_keys=True,
    ).encode("utf-8")
    bundle, bundle_ref = export_analysis_bundle(
        paths,
        evidence,
        _request(before, after),
        publication,
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    retry_bundle, retry_ref = export_analysis_bundle(
        paths,
        EvidenceStore(paths.workspace_root / "evidence"),
        _request(before, after),
        publication,
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    assert (retry_bundle, retry_ref) == (bundle, bundle_ref)
    bundle_document = json.loads(bundle.decode("utf-8"))
    assert bundle_document["before_run"]["schema"] == "stm32-monitor-run-ref/2"
    assert bundle_document["after_run"]["schema"] == "stm32-monitor-run-ref/2"
    assert bundle_document["before_run"]["execution_source"] == "physical"
    assert bundle_document["after_run"]["physical_transport_evidence"] is True
    assert raw_probe not in bundle.decode("utf-8")


@pytest.mark.parametrize("mismatch", ("case", "inventory"))
def test_export_physical_bundle_rejects_case_or_inventory_scope_mismatch_before_writes(
    tmp_path: Path,
    mismatch: str,
) -> None:
    paths, evidence, failed_test_run_id, raw_probe, failed_run_id, failed_group_id = (
        _physical_context(tmp_path)
    )
    fixed_test_run_id = "physical-test-run-02"
    fixed_run_id = UUID("33333333-3333-4333-8333-333333333333")
    fixed_group_id = UUID("44444444-4444-4444-8444-444444444444")
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=failed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=failed_run_id,
        case_id="case.counter",
    )
    failed_batches = _append_physical_history(
        paths, raw_probe, failed_run_id, failed_group_id, scenario_role="failed-before"
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=failed_test_run_id,
        run_id=str(failed_run_id),
        group_id=str(failed_group_id),
        start_sequence=failed_batches[0].sequence,
        end_sequence_exclusive=failed_batches[-1].sequence + 1,
        start_captured_unix_ns=failed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=failed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=fixed_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=fixed_run_id,
        state="passed",
        case_id="case.other" if mismatch == "case" else "case.counter",
        inventory_digest="2" * 64 if mismatch == "inventory" else None,
    )
    fixed_batches = _append_physical_history(
        paths, raw_probe, fixed_run_id, fixed_group_id, scenario_role="fixed-after", value_offset=10
    )
    publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="fixed-after",
        test_run_id=fixed_test_run_id,
        run_id=str(fixed_run_id),
        group_id=str(fixed_group_id),
        start_sequence=fixed_batches[0].sequence,
        end_sequence_exclusive=fixed_batches[-1].sequence + 1,
        start_captured_unix_ns=fixed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=fixed_batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    before = load_monitor_run_reference(paths, evidence, str(failed_run_id))
    after = load_monitor_run_reference(paths, evidence, str(fixed_run_id))
    publication = compare_monitor_runs(paths, evidence, _request(before, after), "f" * 32, HYPOTHESIS_ID, "supports", "scope mismatch")
    snapshot = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        workflows.export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_test_run_id,
            fixed_test_run_id,
        )

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == snapshot


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


def test_analysis_publication_has_exact_closed_wire_round_trip(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    publication = _publish(paths, evidence, before, after, declaration)

    wire = publication.to_dict()
    assert set(wire) == {
        "schema",
        "analysis_result",
        "analysis_evidence_ref",
        "diagnostic_marker",
        "diagnostic_marker_ref",
    }
    assert wire["schema"] == "stm32-monitor-analysis-publication/1"
    assert AnalysisPublication.from_value(wire) == publication

    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisPublication.from_value(publication)
    assert error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    wrong_schema = dict(wire)
    wrong_schema["schema"] = "stm32-monitor-analysis-publication/0"
    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisPublication.from_value(wrong_schema)
    assert error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisPublication.from_value({**wire, "unexpected": None})
    assert error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    forged = dict(wire)
    forged["diagnostic_marker_ref"] = {
        **publication.diagnostic_marker_ref.to_dict(),
        "rationale": "contradictory",
    }
    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisPublication.from_value(forged)
    assert error.value.code == "ANALYSIS_WORKFLOW_INVALID"


def test_analysis_publication_rejects_cross_linked_public_graph_references(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    publication = _publish(paths, evidence, before, after, declaration)
    wire = publication.to_dict()
    before_tree = _evidence_tree(evidence)

    forged_evidence = dict(wire)
    forged_evidence["analysis_evidence_ref"] = {
        **cast(dict[str, object], wire["analysis_evidence_ref"]),
        "analysis_id": "f" * 64,
    }
    with pytest.raises(AnalysisWorkflowError) as evidence_error:
        AnalysisPublication.from_value(forged_evidence)
    assert evidence_error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    marker = publication.diagnostic_marker
    marker_with_wrong_analysis = DiagnosticMarker.new(
        analysis_id="f" * 64,
        analysis_evidence_id=publication.analysis_evidence_ref.evidence_id,
        diagnostic_session_id=marker.diagnostic_session_id,
        hypothesis_id=marker.hypothesis_id,
        polarity=marker.polarity,
        label=marker.label,
        rationale=marker.rationale,
    )
    assert DiagnosticMarker.from_value(marker_with_wrong_analysis.to_dict()) == marker_with_wrong_analysis
    forged_marker = dict(wire)
    forged_marker["diagnostic_marker"] = marker_with_wrong_analysis.to_dict()
    with pytest.raises(AnalysisWorkflowError) as marker_error:
        AnalysisPublication.from_value(forged_marker)
    assert marker_error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    marker_with_wrong_evidence = DiagnosticMarker.new(
        analysis_id=publication.analysis_result.analysis_id,
        analysis_evidence_id="e" * 64,
        diagnostic_session_id=marker.diagnostic_session_id,
        hypothesis_id=marker.hypothesis_id,
        polarity=marker.polarity,
        label=marker.label,
        rationale=marker.rationale,
    )
    assert DiagnosticMarker.from_value(marker_with_wrong_evidence.to_dict()) == marker_with_wrong_evidence
    forged_marker_evidence = dict(wire)
    forged_marker_evidence["diagnostic_marker"] = marker_with_wrong_evidence.to_dict()
    with pytest.raises(AnalysisWorkflowError) as marker_evidence_error:
        AnalysisPublication.from_value(forged_marker_evidence)
    assert marker_evidence_error.value.code == "ANALYSIS_WORKFLOW_INVALID"

    forged_marker_ref = dict(wire)
    forged_marker_ref["diagnostic_marker_ref"] = {
        **cast(dict[str, object], wire["diagnostic_marker_ref"]),
        "marker_id": "f" * 64,
    }
    with pytest.raises(AnalysisWorkflowError) as marker_ref_error:
        AnalysisPublication.from_value(forged_marker_ref)
    assert marker_ref_error.value.code == "ANALYSIS_WORKFLOW_INVALID"
    assert _evidence_tree(evidence) == before_tree


@pytest.mark.parametrize(
    "mutation",
    ("missing-root", "missing-manifest", "corrupt-artifact", "contradictory-root"),
)
def test_compare_validates_complete_monitor_reference_authority_before_history(
    tmp_path: Path, mutation: str
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    root_path = _monitor_ref_root_path(evidence, before.operation_id)
    ref_root = get_root(evidence, "monitor-run-ref", before.operation_id)
    if mutation == "missing-root":
        root_path.unlink()
    elif mutation == "missing-manifest":
        (evidence.root / "manifests" / f"{ref_root.manifest_id}.json").unlink()
    elif mutation == "corrupt-artifact":
        envelope = evidence.get_envelope(ref_root.manifest_id)
        (evidence.root / envelope.artifacts[0].relative_path).write_bytes(b"corrupt-ref")
    else:
        payload = json.loads(root_path.read_text(encoding="utf-8"))
        payload["metadata"]["run_ref_sha256"] = "0" * 64
        root_path.write_bytes(canonical_json_bytes(payload))
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _evidence_tree(evidence) == before_tree


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


def test_derived_publication_rejects_provider_artifact_identity_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    calls: list[str] = []

    def return_wrong_artifact(
        store: EvidenceStore,
        source: Path,
        *,
        kind: str,
        media_type: str,
    ) -> ArtifactRef:
        del store
        calls.append(kind)
        digest = "0" * 64
        return ArtifactRef(
            sha256=digest,
            size_bytes=source.stat().st_size,
            relative_path=f"objects/sha256/{digest[:2]}/{digest}",
            kind=kind,
            media_type=media_type,
        )

    monkeypatch.setattr(EvidenceStore, "ingest_file", return_wrong_artifact)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == ["monitor-analysis"]
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


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


@pytest.mark.parametrize(
    ("provider_code", "expected_code"),
    [
        ("MONITOR_STORAGE_CORRUPT", EVIDENCE_INTEGRITY_FAILURE),
        ("MONITOR_STORAGE_BUSY", ENVIRONMENT_FAILURE),
        ("MONITOR_STORAGE_TIMEOUT", ENVIRONMENT_FAILURE),
    ],
)
def test_history_provider_failures_are_classified_before_derived_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_code: str,
    expected_code: str,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    calls: list[HistoryQuery] = []

    def fail_query(self: HistoryStore, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        del self
        calls.append(query)
        return ProtocolResult(False, "history.query", provider_code, "provider failed", None)

    monkeypatch.setattr(HistoryStore, "query_history", fail_query)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)
    assert error.value.code == expected_code
    assert calls
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_oserror_is_environment_failure_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    calls: list[HistoryQuery] = []

    def fail_query(self: HistoryStore, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        del self
        calls.append(query)
        raise OSError("private history provider")

    monkeypatch.setattr(HistoryStore, "query_history", fail_query)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls
    assert error.value.code == ENVIRONMENT_FAILURE
    assert "private history provider" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_partial_first_slice_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def partial_first_slice(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, query)
        assert result.ok and result.data is not None
        page = result.data
        first = page.batches[0]
        partial = replace(
            first,
            start_ordinal=1,
            batch_value_count=first.batch_value_count + 1,
        )
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((partial, *page.batches[1:]), next_cursor=page.next_cursor),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", partial_first_slice)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 1
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_page_order_is_authoritative_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def reversed_page(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, query)
        assert result.ok and result.data is not None
        page = result.data
        assert len(page.batches) >= 2
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create(tuple(reversed(page.batches)), next_cursor=None),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", reversed_page)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 1
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_repeated_cursor_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    first_page: HistoryPage | None = None
    second_page: HistoryPage | None = None
    queries: list[HistoryQuery] = []
    calls = 0

    def repeated_cursor(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls, first_page, second_page
        calls += 1
        queries.append(query)
        result = original(self, replace(query, limit=1))
        assert result.ok and result.data is not None
        if first_page is None:
            first_page = result.data
        else:
            second = result.data.batches[0]
            repeated_batch = replace(
                second,
                sequence=first_page.batches[0].sequence + 1,
                start_ordinal=0,
            )
            second_page = HistoryPage.create(
                (repeated_batch,),
                next_cursor=first_page.next_cursor,
            )
            result = ProtocolResult(
                True,
                result.operation,
                "OK",
                "",
                second_page,
                protocol=result.protocol,
            )
        return result

    monkeypatch.setattr(HistoryStore, "query_history", repeated_cursor)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 2
    assert first_page is not None and first_page.next_cursor is not None
    assert second_page is not None
    assert queries[1].cursor == first_page.next_cursor
    assert second_page.batches[0].start_ordinal + len(second_page.batches[0].values) - 1 == 0
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_multipage_reopened_batch_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    first_batch: HistoryBatchSlice | None = None
    calls = 0

    def reopened_batch(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls, first_batch
        calls += 1
        result = original(self, replace(query, cursor=None))
        assert result.ok and result.data is not None
        source = result.data.batches[0]
        if first_batch is None:
            first_batch = source
            page_batch = source
            next_cursor = f"1:{source.start_ordinal + len(source.values) - 1}"
        elif calls == 2:
            page_batch = replace(source, sequence=first_batch.sequence + 1)
            next_cursor = f"2:{page_batch.start_ordinal + len(page_batch.values) - 1}"
        else:
            page_batch = replace(source, sequence=first_batch.sequence)
            next_cursor = None
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((page_batch,), next_cursor=next_cursor),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", reopened_batch)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 3
    assert first_batch is not None
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_multipage_static_contradiction_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def static_contradiction(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, replace(query, cursor=None))
        assert result.ok and result.data is not None
        source = result.data.batches[0]
        declared_count = max(source.batch_value_count, 2)
        if calls == 1:
            first = replace(
                source,
                start_ordinal=0,
                batch_value_count=declared_count,
                values=(source.values[0],),
            )
            next_cursor = f"1:{len(first.values) - 1}"
            page_batch = first
        else:
            page_batch = replace(
                source,
                start_ordinal=1,
                batch_value_count=declared_count,
                values=(source.values[0],),
                group_revision=source.group_revision + 1,
            )
            next_cursor = None
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((page_batch,), next_cursor=next_cursor),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", static_contradiction)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 2
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_multipage_value_limit_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def oversized_window(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, replace(query, cursor=None))
        assert result.ok and result.data is not None
        source = result.data.batches[0]
        if calls == 1:
            page_batches = tuple(
                replace(
                    source,
                    sequence=source.sequence + index,
                    scheduled_unix_ns=source.scheduled_unix_ns + index,
                    captured_unix_ns=source.captured_unix_ns + index,
                    start_ordinal=0,
                    batch_value_count=250,
                    values=(source.values[0],) * 250,
                )
                for index in range(40)
            )
            return ProtocolResult(
                True,
                result.operation,
                "OK",
                "",
                HistoryPage.create(page_batches, next_cursor="1:249"),
                protocol=result.protocol,
            )
        final_batch = replace(
            source,
            sequence=source.sequence + 40,
            start_ordinal=0,
            batch_value_count=1,
            values=(source.values[0],),
        )
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((final_batch,), next_cursor=None),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", oversized_window)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 2
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_multipage_incomplete_batch_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def incomplete_batch(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, query)
        assert result.ok and result.data is not None
        source = result.data.batches[0]
        incomplete = replace(
            source,
            start_ordinal=0,
            batch_value_count=max(source.batch_value_count, 2),
            values=(source.values[0],),
        )
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((incomplete, *result.data.batches[1:]), next_cursor=None),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", incomplete_batch)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 1
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


def test_history_multipage_binding_identity_is_rejected_before_derived_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _evidence_tree(evidence)
    original = HistoryStore.query_history
    calls = 0

    def mismatched_binding(
        self: HistoryStore, query: HistoryQuery
    ) -> ProtocolResult[HistoryPage]:
        nonlocal calls
        calls += 1
        result = original(self, query)
        assert result.ok and result.data is not None
        source = result.data.batches[0]
        wrong_build_id = "f" * 64 if source.binding.build_id != "f" * 64 else "0" * 64
        wrong = replace(source, binding=replace(source.binding, build_id=wrong_build_id))
        return ProtocolResult(
            True,
            result.operation,
            "OK",
            "",
            HistoryPage.create((wrong, *result.data.batches[1:]), next_cursor=None),
            protocol=result.protocol,
        )

    monkeypatch.setattr(HistoryStore, "query_history", mismatched_binding)
    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls == 1
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis" in path for path in _evidence_tree(evidence))


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


def test_derived_preflight_rejects_corrupt_root_without_mutation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    first = _publish(paths, evidence, before, after, declaration)
    root_path = next((evidence.root / "roots" / "monitor-analysis").glob("*.json"))
    root_path.write_bytes(b"corrupt-derived-root")
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert first.analysis_result.analysis_id
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _evidence_tree(evidence) == before_tree


def test_derived_preflight_maps_root_provider_io_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    first = _publish(paths, evidence, before, after, declaration)
    original_get_root = workflows.get_root

    def fail_derived_root(store: EvidenceStore, root_type: str, root_id: str) -> object:
        if root_type == "monitor-analysis" and root_id == first.analysis_result.analysis_id:
            raise OSError("derived-root-provider-secret")
        return original_get_root(store, root_type, root_id)

    monkeypatch.setattr(workflows, "get_root", fail_derived_root)
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == ENVIRONMENT_FAILURE
    assert "derived-root-provider-secret" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree


def test_derived_preflight_rejects_existing_envelope_intent_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    first = _publish(paths, evidence, before, after, declaration)
    alternate = evidence.get_envelope(before.transcript_evidence_id)
    original_get_envelope = EvidenceStore.get_envelope

    def return_different_envelope(store: EvidenceStore, evidence_id: str) -> object:
        if evidence_id == first.analysis_evidence_ref.evidence_id:
            return alternate
        return original_get_envelope(store, evidence_id)

    monkeypatch.setattr(EvidenceStore, "get_envelope", return_different_envelope)
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == "OPERATION_CONFLICT"
    assert _evidence_tree(evidence) == before_tree


def test_derived_publication_reload_rejects_published_root_mismatch_without_rollback(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    state: dict[str, object] = {"root_mutated": False, "root_path": None}

    def mutate_after_root_publish(point: str) -> None:
        if point != "gc-root.after_publish" or state["root_mutated"]:
            return
        root_path = next((evidence.root / "roots" / "monitor-analysis").glob("*.json"))
        payload = json.loads(root_path.read_bytes().decode("utf-8"))
        metadata = dict(cast(dict[str, object], payload["metadata"]))
        metadata["origin_workspace_id"] = "9" * 64
        payload["metadata"] = metadata
        root_path.write_bytes(canonical_json_bytes(payload))
        state["root_mutated"] = True
        state["root_path"] = root_path

    faulty = EvidenceStore(evidence.root, fault_injector=mutate_after_root_publish)
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, faulty, before, after, declaration)

    assert state["root_mutated"] is True
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert state["root_path"] is not None
    assert _evidence_tree(evidence) != before_tree
    assert not any((evidence.root / "roots" / "diagnostic-marker").glob("*.json"))


def test_derived_publication_reload_rejects_provider_envelope_mismatch_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    alternate = evidence.get_envelope(before.transcript_evidence_id)
    state: dict[str, object] = {"analysis_manifest_id": None}

    def record_analysis_root_publish(point: str) -> None:
        if point != "gc-root.after_publish" or state["analysis_manifest_id"] is not None:
            return
        root_path = next((evidence.root / "roots" / "monitor-analysis").glob("*.json"))
        state["analysis_manifest_id"] = json.loads(root_path.read_bytes().decode("utf-8"))["manifest_id"]

    original_get_envelope = EvidenceStore.get_envelope

    def return_alternate_after_publish(store: EvidenceStore, evidence_id: str) -> object:
        if state["analysis_manifest_id"] == evidence_id:
            return alternate
        return original_get_envelope(store, evidence_id)

    monkeypatch.setattr(EvidenceStore, "get_envelope", return_alternate_after_publish)
    faulty = EvidenceStore(evidence.root, fault_injector=record_analysis_root_publish)
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, faulty, before, after, declaration)

    assert state["analysis_manifest_id"] is not None
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _evidence_tree(evidence) != before_tree
    assert not any((evidence.root / "roots" / "diagnostic-marker").glob("*.json"))


def test_derived_publication_reload_rejects_provider_artifact_bytes_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    state = {"analysis_root_published": False}

    def record_analysis_root_publish(point: str) -> None:
        if point == "gc-root.after_publish" and not state["analysis_root_published"]:
            state["analysis_root_published"] = True

    original_read_artifact = EvidenceStore.read_artifact

    def return_wrong_reload_bytes(
        store: EvidenceStore, artifact: ArtifactRef, *, maximum_bytes: int
    ) -> bytes:
        if state["analysis_root_published"] and artifact.kind == "monitor-analysis":
            return b"derived-reload-mismatch"
        return original_read_artifact(store, artifact, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(EvidenceStore, "read_artifact", return_wrong_reload_bytes)
    faulty = EvidenceStore(evidence.root, fault_injector=record_analysis_root_publish)
    before_tree = _evidence_tree(evidence)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, faulty, before, after, declaration)

    assert state["analysis_root_published"] is True
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _evidence_tree(evidence) != before_tree
    assert not any((evidence.root / "roots" / "diagnostic-marker").glob("*.json"))


@pytest.mark.parametrize(
    ("authority", "expected_code"),
    [
        ("root", EVIDENCE_INTEGRITY_FAILURE),
        ("manifest", EVIDENCE_INTEGRITY_FAILURE),
        ("envelope", EVIDENCE_INTEGRITY_FAILURE),
        ("bytes", EVIDENCE_INTEGRITY_FAILURE),
        ("provider", ENVIRONMENT_FAILURE),
    ],
)
def test_export_rejects_upstream_derived_authority_without_bundle_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
    expected_code: str,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    analysis_root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    analysis_envelope = evidence.get_envelope(analysis_root.manifest_id)

    if authority == "root":
        root_path = next((evidence.root / "roots" / "monitor-analysis").glob("*.json"))
        payload = json.loads(root_path.read_bytes().decode("utf-8"))
        metadata = dict(cast(dict[str, object], payload["metadata"]))
        metadata["origin_workspace_id"] = "8" * 64
        payload["metadata"] = metadata
        root_path.write_bytes(canonical_json_bytes(payload))
    elif authority == "manifest":
        (evidence.root / "manifests" / f"{analysis_root.manifest_id}.json").unlink()
    elif authority == "envelope":
        alternate = evidence.get_envelope(before.transcript_evidence_id)
        original_get_envelope = EvidenceStore.get_envelope

        def return_alternate(store: EvidenceStore, evidence_id: str) -> object:
            if evidence_id == analysis_envelope.evidence_id:
                return alternate
            return original_get_envelope(store, evidence_id)

        monkeypatch.setattr(EvidenceStore, "get_envelope", return_alternate)
    elif authority in {"bytes", "provider"}:
        original_read_artifact = EvidenceStore.read_artifact

        def read_upstream_variant(
            store: EvidenceStore, artifact: ArtifactRef, *, maximum_bytes: int
        ) -> bytes:
            if artifact.kind == "monitor-analysis":
                if authority == "bytes":
                    return b"upstream-derived-bytes-differ"
                raise OSError("upstream-derived-provider-secret")
            return original_read_artifact(store, artifact, maximum_bytes=maximum_bytes)

        monkeypatch.setattr(EvidenceStore, "read_artifact", read_upstream_variant)

    before_tree = _evidence_tree(evidence)
    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )

    assert error.value.code == expected_code
    if authority == "provider":
        assert "upstream-derived-provider-secret" not in str(error.value)
    assert _evidence_tree(evidence) == before_tree
    assert not any("monitor-analysis-bundle" in path for path in _evidence_tree(evidence))


def test_awf_1a_rejects_invalid_diagnostic_session_before_write(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(
            paths,
            evidence,
            before,
            after,
            declaration,
            diagnostic_session_id="invalid-diagnostic-session",
        )

    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "diagnostic session ID is invalid"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_1b_rejects_empty_rationale_before_write(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration, rationale="")

    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "rationale is invalid"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_1c_rejects_non_declaration_argument_before_provider_access(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, object())

    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "analysis workflow arguments are invalid"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_1d_rejects_declaration_for_identical_firmware(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    before = ingest_monitor_replay(
        paths, evidence, _operation("failed-before"), _fixture("failed-before")
    )
    declaration = _declaration(
        tmp_path, evidence, before, _synthetic_changed_after(before)
    )
    identical_after_path = _write_same_firmware_after(tmp_path)
    after = ingest_monitor_replay(
        paths, evidence, _operation("fixed-after"), identical_after_path
    )
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == "identical firmware cannot carry a source declaration"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_1e_rejects_source_diff_identity_mismatch_before_publication(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    foreign_identity = EvidenceIdentity(
        workspace_id="9" * 64,
        project_id=after.logical_project_id,
        session_id=after.origin_session_id,
        build_id=before.build_id,
        elf_sha256=before.elf_sha256,
        target_device=after.target_device,
        input_snapshot_sha256=before.input_snapshot_sha256,
        git_commit=before.git_head,
        git_dirty=before.git_dirty,
    )
    declaration = _declaration(
        tmp_path,
        evidence,
        before,
        after,
        identity_override=foreign_identity,
    )
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == "source-change diff Evidence identity is incompatible"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_2a_rejects_monitor_root_intent_mismatch_before_history(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    root_path = _monitor_run_root_path(evidence, before.operation_id)
    root_payload = json.loads(root_path.read_bytes().decode("utf-8"))
    root_payload["metadata"]["fixture_sha256"] = "0" * 64
    root_path.write_bytes(canonical_json_bytes(root_payload))
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == "OPERATION_CONFLICT"
    assert error.value.message == "replay run root has a different intent"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_2b_rejects_projected_digest_contradiction_after_public_ref_rebuild(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, original_before, after = _ingest_pair(paths)
    reference_values = original_before.to_dict()
    projected_digests = list(original_before.projected_batch_sha256s)
    projected_digests[0] = "0" * 64
    reference_values["projected_batch_sha256s"] = projected_digests
    unsigned = {
        key: value for key, value in reference_values.items() if key != "run_ref_sha256"
    }
    reference_values["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    before = MonitorRunRef.from_value(reference_values)
    declaration = _declaration(tmp_path, evidence, before, after)
    root_path = _monitor_run_root_path(evidence, before.operation_id)
    root_payload = json.loads(root_path.read_bytes().decode("utf-8"))
    root_payload["metadata"]["run_ref_sha256"] = before.run_ref_sha256
    root_path.write_bytes(canonical_json_bytes(root_payload))
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "replay projected batch digests contradict the run reference"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_2d_maps_physical_transcript_provider_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, evidence, _failed_test_run_id, _fixed_test_run_id, _raw_probe, before, after = (
        _physical_pair(tmp_path)
    )
    declaration = _declaration(tmp_path, evidence, before, after)
    original_read = EvidenceStore.read_artifact

    def fail_physical_transcript(
        store: EvidenceStore, artifact: ArtifactRef, *, maximum_bytes: int
    ) -> bytes:
        if artifact.kind == "monitor-physical-transcript":
            raise OSError("physical transcript provider secret")
        return original_read(store, artifact, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(EvidenceStore, "read_artifact", fail_physical_transcript)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == ENVIRONMENT_FAILURE
    assert error.value.message == "physical Monitor Evidence provider failed"
    assert "physical transcript provider secret" not in str(error.value)
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_2e_maps_malformed_persisted_physical_transcript(
    tmp_path: Path,
) -> None:
    paths, evidence, _failed_test_run_id, _fixed_test_run_id, _raw_probe, before, after = (
        _physical_pair(tmp_path)
    )
    declaration = _declaration(tmp_path, evidence, before, after)
    transcript_root = get_root(evidence, "monitor-run", before.operation_id)
    transcript = evidence.get_envelope(transcript_root.manifest_id)
    transcript_object = evidence.root / transcript.artifacts[0].relative_path
    transcript_object.write_bytes(b"[]")
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "physical Monitor Evidence is corrupt"
    assert _data_tree(paths) == before_tree
    assert transcript_object.read_bytes() == b"[]"
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_2f_maps_unrecognized_history_provider_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    calls: list[HistoryQuery] = []

    def fail_query(self: HistoryStore, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        del self
        calls.append(query)
        return ProtocolResult(False, "history.query", "UNRECOGNIZED_PROVIDER", "provider failed", None)

    monkeypatch.setattr(HistoryStore, "query_history", fail_query)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, after, declaration)

    assert calls
    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "monitor history query failed"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis").exists()


def test_awf_3a_rejects_continuation_with_different_diagnostic_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _monitor_baseline(pair, tmp_path)
    paths, evidence, request, _old_session, hypothesis, polarity, rationale, declaration = (
        baseline.compare_args
    )
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        compare_monitor_runs(
            paths,
            evidence,
            request,
            "e" * 32,
            hypothesis,
            polarity,
            rationale,
            declaration,
            continuation_evidence_id=baseline.continuation_id,
        )

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == "continuation does not match Diagnostic declaration"
    assert _data_tree(paths) == before_tree


def test_awf_3b_exports_identical_firmware_without_source_row(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    before = ingest_monitor_replay(
        paths, evidence, _operation("failed-before"), _fixture("failed-before")
    )
    identical_after_path = _write_same_firmware_after(tmp_path)
    after = ingest_monitor_replay(
        paths, evidence, _operation("fixed-after"), identical_after_path
    )
    failed_id, fixed_id = _publish_target_pair_variant(
        paths,
        evidence,
        identity_overrides={
            "failed-before": EvidenceIdentity(
                workspace_id=before.origin_workspace_id,
                project_id=before.logical_project_id,
                session_id=before.origin_session_id,
                build_id=before.build_id,
                elf_sha256=before.elf_sha256,
                target_device=before.target_device,
                input_snapshot_sha256=before.input_snapshot_sha256,
                git_commit=before.git_head,
                git_dirty=before.git_dirty,
            ),
            "fixed-after": EvidenceIdentity(
                workspace_id=after.origin_workspace_id,
                project_id=after.logical_project_id,
                session_id=after.origin_session_id,
                build_id=after.build_id,
                elf_sha256=after.elf_sha256,
                target_device=after.target_device,
                input_snapshot_sha256=after.input_snapshot_sha256,
                git_commit=after.git_head,
                git_dirty=after.git_dirty,
            ),
        },
    )
    publication = _publish(paths, evidence, before, after, None)
    before_tree = _data_tree(paths)

    payload, bundle_ref = export_analysis_bundle(
        paths,
        evidence,
        _request(before, after),
        publication,
        failed_id,
        fixed_id,
    )
    body = json.loads(payload.decode("utf-8"))
    assert body["source_change_declaration_id"] is None
    assert not any(
        row["role"] == "source-change-declaration" for row in body["digest_table"]
    )
    bundle_root = get_root(evidence, "monitor-analysis-bundle", bundle_ref.bundle_id)
    bundle = evidence.get_envelope(bundle_root.manifest_id)
    assert bundle.parents == (
        before.transcript_evidence_id,
        after.transcript_evidence_id,
        publication.analysis_evidence_ref.evidence_id,
        publication.diagnostic_marker_ref.marker_evidence_id,
    )
    assert evidence.read_artifact(bundle_ref.artifact, maximum_bytes=1_000_000) == payload
    after_first_tree = _data_tree(paths)
    assert all(after_first_tree[path] == value for path, value in before_tree.items())
    bundle_root_paths = tuple(
        (evidence.root / "roots" / "monitor-analysis-bundle").glob("*.json")
    )
    assert len(bundle_root_paths) == 1
    bundle_root_path = bundle_root_paths[0]
    added_paths = set(after_first_tree).difference(before_tree)
    expected_added_paths = {
        str((evidence.root / bundle_ref.artifact.relative_path).relative_to(paths.data_root)),
        str((evidence.root / "manifests" / f"{bundle.evidence_id}.json").relative_to(paths.data_root)),
        str(bundle_root_path.relative_to(paths.data_root)),
    }
    assert added_paths == expected_added_paths
    assert len(added_paths) == 3
    assert bundle_root.root_type == "monitor-analysis-bundle"
    assert bundle_root.root_id == bundle_ref.bundle_id
    assert bundle_root.manifest_id == str(bundle.evidence_id)
    assert json.loads(bundle_root_path.read_bytes().decode("utf-8")) == bundle_root.to_dict()
    retry_payload, retry_ref = export_analysis_bundle(
        paths,
        EvidenceStore(evidence.root),
        _request(before, after),
        publication,
        failed_id,
        fixed_id,
    )
    assert (retry_payload, retry_ref) == (payload, bundle_ref)
    assert _data_tree(paths) == after_first_tree


def test_awf_3c_rejects_analysis_reference_drift_before_bundle_write(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair(paths, evidence)
    publication = _publish(paths, evidence, before, after, declaration)
    analysis_ref = AnalysisEvidenceRef.new(
        analysis_id=publication.analysis_result.analysis_id,
        evidence_id="e" * 64,
    )
    marker = DiagnosticMarker.new(
        analysis_id=publication.analysis_result.analysis_id,
        analysis_evidence_id=analysis_ref.evidence_id,
        diagnostic_session_id=publication.diagnostic_marker.diagnostic_session_id,
        hypothesis_id=publication.diagnostic_marker.hypothesis_id,
        polarity=publication.diagnostic_marker.polarity,
        label=publication.diagnostic_marker.label,
        rationale=publication.diagnostic_marker.rationale,
    )
    marker_ref = DiagnosticMarkerRef.new(
        marker_id=marker.marker_id,
        marker_evidence_id=publication.diagnostic_marker_ref.marker_evidence_id,
        analysis_id=marker.analysis_id,
        analysis_evidence_id=marker.analysis_evidence_id,
        diagnostic_session_id=marker.diagnostic_session_id,
        hypothesis_id=marker.hypothesis_id,
        polarity=marker.polarity,
        label=marker.label,
        rationale=marker.rationale,
    )
    publication = AnalysisPublication(
        publication.analysis_result, analysis_ref, marker, marker_ref
    )
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "analysis evidence reference does not match stored envelope"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis-bundle").exists()


def test_awf_3d_rejects_coherent_target_root_workspace_mismatch(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    failed_id, fixed_id = _publish_target_pair_variant(
        paths,
        evidence,
        import_workspace_overrides={
            "failed-before": "9" * 64,
            "fixed-after": "9" * 64,
        },
    )
    publication = _publish(paths, evidence, before, after, declaration)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == "TestRun root metadata does not match replay reference"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis-bundle").exists()


def test_awf_3e_rejects_target_test_runs_with_distinct_sessions(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence, before, after = _ingest_pair(paths)
    declaration = _declaration(tmp_path, evidence, before, after)
    alternate_after_identity = EvidenceIdentity(
        workspace_id=after.origin_workspace_id,
        project_id=after.logical_project_id,
        session_id="target-session-other",
        build_id=after.build_id,
        elf_sha256=after.elf_sha256,
        target_device=after.target_device,
        input_snapshot_sha256=after.input_snapshot_sha256,
        git_commit=after.git_head,
        git_dirty=after.git_dirty,
    )
    failed_id, fixed_id = _publish_target_pair_variant(
        paths,
        evidence,
        identity_overrides={"fixed-after": alternate_after_identity},
    )
    publication = _publish(paths, evidence, before, after, declaration)
    before_tree = _data_tree(paths)

    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            _request(before, after),
            publication,
            failed_id,
            fixed_id,
            declaration,
        )

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == "Target TestRuns do not share a session"
    assert _data_tree(paths) == before_tree
    assert not (evidence.root / "roots" / "monitor-analysis-bundle").exists()
