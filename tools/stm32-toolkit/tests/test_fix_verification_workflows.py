from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs
from stm32_monitor.replay import (
    MonitorReplayError,
    MonitorReplayDocument,
    ingest_monitor_replay,
)
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
import stm32_toolkit.testing_workflows as testing_workflows
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_verification_plan,
    diagnostic_attach_marker,
    diagnostic_begin,
    diagnostic_declare_source_change,
    diagnostic_show,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import (
    DiagnosticMarkerRef,
    SourceChangeDeclaration,
    VerificationPlan,
)
from stm32_toolkit.evidence import (
    ArtifactRef,
    EVIDENCE_CORRUPT,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing.replay import load_target_replay_fixture


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
MONITOR_OPERATION_IDS = {
    "failed-before": "33333333-3333-4333-8333-333333333333",
    "fixed-after": "44444444-4444-4444-8444-444444444444",
}


def _producer_canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _install_model(
    monkeypatch: pytest.MonkeyPatch,
    project_id: UUID = PROJECT_ID,
) -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=project_id,
        testing=SimpleNamespace(host=None, target=object()),
    )
    monkeypatch.setattr(testing_workflows, "_load_project_model", lambda _root: model)
    monkeypatch.setattr(diagnostic_workflows, "_load_project_model", lambda _root: model)


def _contexts(tmp_path: Path) -> tuple[testing_workflows.TestingWorkflowContext, DiagnosticWorkflowContext]:
    project = tmp_path / "project"
    project.mkdir()
    data = tmp_path / "data"
    return (
        testing_workflows.TestingWorkflowContext(project, data, "replay-session"),
        DiagnosticWorkflowContext(project, data, "replay-session"),
    )


def _fresh_diagnostic_context(context: DiagnosticWorkflowContext) -> DiagnosticWorkflowContext:
    return DiagnosticWorkflowContext(
        Path(context.project_root), Path(context.data_root), str(context.session_id)
    )


def _replay_and_open_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[DiagnosticWorkflowContext, str, object, WorkspacePaths]:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True

    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    session_id = started.data["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.begin",
        diagnostic_session_id=session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    added = diagnostic_add_hypothesis(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.hypothesis.add",
        diagnostic_session_id=session_id,
        expected_revision=2,
        statement="the replayed failed run identifies the faulty behavior",
    )
    assert added.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    return diagnostic_context, session_id, replay, workspace


def _tree_snapshot(root: Path) -> tuple[tuple[str, bytes | None], ...]:
    if not root.exists():
        return ()
    entries: list[tuple[str, bytes | None]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        entries.append((relative, path.read_bytes() if path.is_file() else None))
    return tuple(entries)


def _authority_snapshot(workspace: WorkspacePaths) -> tuple[object, object]:
    return (
        _tree_snapshot(workspace.diagnostics_root),
        _tree_snapshot(workspace.workspace_root / "evidence"),
    )


def _target_test_run_root(workspace: WorkspacePaths) -> Path:
    roots = tuple((workspace.workspace_root / "evidence" / "roots" / "test-run").glob("*.json"))
    assert len(roots) == 1
    return roots[0]


def _monitor_ref_root_path(workspace: WorkspacePaths, operation_id: str) -> Path:
    roots = tuple((workspace.workspace_root / "evidence" / "roots" / "monitor-run-ref").glob("*.json"))
    for path in roots:
        if json.loads(path.read_text(encoding="utf-8"))["root_id"] == operation_id:
            return path
    raise AssertionError(f"monitor-run-ref root is absent: {operation_id}")


def _evidence_root_path(workspace: WorkspacePaths, root_type: str, root_id: str) -> Path:
    roots = tuple((workspace.workspace_root / "evidence" / "roots" / root_type).glob("*.json"))
    for path in roots:
        if json.loads(path.read_text(encoding="utf-8"))["root_id"] == root_id:
            return path
    raise AssertionError(f"{root_type} root is absent: {root_id}")


def _replace_monitor_reference_authority(
    tmp_path: Path,
    workspace: WorkspacePaths,
    operation_id: str,
    mutate,
) -> None:
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    root = get_root(evidence, "monitor-run-ref", operation_id)
    envelope = evidence.get_envelope(root.manifest_id)
    payload = json.loads(
        evidence.read_artifact(envelope.artifacts[0], maximum_bytes=1_000_000).decode("utf-8")
    )
    mutate(payload)
    unsigned = {key: value for key, value in payload.items() if key != "run_ref_sha256"}
    payload["run_ref_sha256"] = hashlib.sha256(
        _producer_canonical_json_bytes(unsigned)
    ).hexdigest()
    raw = _producer_canonical_json_bytes(payload)
    source = tmp_path / f"mutated-monitor-ref-{operation_id}.json"
    source.write_bytes(raw)
    artifact = evidence.ingest_file(source, kind="monitor-run-ref", media_type="application/json")
    identity = EvidenceIdentity(
        workspace_id=payload["origin_workspace_id"],
        project_id=payload["logical_project_id"],
        session_id=payload["origin_session_id"],
        build_id=payload["build_id"],
        elf_sha256=payload["elf_sha256"],
        target_device=payload["target_device"],
        input_snapshot_sha256=payload["input_snapshot_sha256"],
        git_commit=payload["git_head"],
        git_dirty=payload["git_dirty"],
    )
    metadata = {
        "operation_id": payload["operation_id"],
        "run_ref_sha256": payload["run_ref_sha256"],
        "fixture_sha256": payload["fixture_sha256"],
        "scenario_role": payload["scenario_role"],
        "origin_workspace_id": payload["origin_workspace_id"],
        "import_workspace_id": payload["import_workspace_id"],
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    replacement = EvidenceEnvelope(
        identity=identity,
        operation="monitor-run-ref",
        produced_at_utc=envelope.produced_at_utc,
        parents=(payload["transcript_evidence_id"],),
        artifacts=(artifact,),
        metadata=metadata,
    )
    evidence.put_envelope(replacement)
    _monitor_ref_root_path(workspace, operation_id).unlink()
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run-ref",
            root_id=operation_id,
            manifest_id=str(replacement.evidence_id),
            metadata=metadata,
        ),
    )


def _swap_monitor_reference_authority(
    workspace: WorkspacePaths, before_operation_id: str, after_operation_id: str
) -> None:
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    after_root = get_root(evidence, "monitor-run-ref", after_operation_id)
    _monitor_ref_root_path(workspace, before_operation_id).unlink()
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run-ref",
            root_id=before_operation_id,
            manifest_id=after_root.manifest_id,
            metadata=dict(after_root.metadata),
        ),
    )


def _replace_monitor_transcript_and_analysis(
    tmp_path: Path,
    workspace: WorkspacePaths,
    operation_id: str,
    marker_ref: DiagnosticMarkerRef,
    plan: VerificationPlan,
    extra_kind: str,
) -> VerificationPlan:
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    transcript_root = get_root(evidence, "monitor-run", operation_id)
    transcript_envelope = evidence.get_envelope(transcript_root.manifest_id)
    transcript_document = json.loads(
        evidence.read_artifact(
            transcript_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    batch = transcript_document["batches"][0]
    if extra_kind == "batch":
        batch["unexpected"] = True
    elif extra_kind == "sample":
        batch["values"][0]["unexpected"] = True
    elif extra_kind == "typed":
        batch["values"][0]["typedValue"] = None
    elif extra_kind == "whitespace":
        for batch_value in transcript_document["batches"]:
            watch = batch_value["values"][0]["watch"]
            selector_key = "expression" if watch["kind"] == "variable" else "registerPath"
            watch[selector_key] = f" {watch[selector_key]} "
    else:
        assert extra_kind == "watch"
        batch["values"][0]["watch"]["unexpected"] = True
    unsigned_document = {
        key: value for key, value in transcript_document.items() if key != "fixture_sha256"
    }
    transcript_document["fixture_sha256"] = hashlib.sha256(
        _producer_canonical_json_bytes(unsigned_document)
    ).hexdigest()
    transcript_raw = _producer_canonical_json_bytes(transcript_document)
    transcript_source = tmp_path / f"extra-{extra_kind}-monitor-transcript.json"
    transcript_source.write_bytes(transcript_raw)
    transcript_artifact = evidence.ingest_file(
        transcript_source,
        kind="monitor-replay-transcript",
        media_type="application/json",
    )
    transcript_metadata = dict(transcript_envelope.metadata)
    transcript_metadata["fixture_sha256"] = transcript_document["fixture_sha256"]
    replacement_transcript = EvidenceEnvelope(
        identity=transcript_envelope.identity,
        operation=transcript_envelope.operation,
        produced_at_utc=transcript_envelope.produced_at_utc,
        parents=(),
        artifacts=(transcript_artifact,),
        metadata=transcript_metadata,
    )
    evidence.put_envelope(replacement_transcript)

    reference_root = get_root(evidence, "monitor-run-ref", operation_id)
    reference_envelope = evidence.get_envelope(reference_root.manifest_id)
    reference = json.loads(
        evidence.read_artifact(
            reference_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    reference["fixture_sha256"] = transcript_document["fixture_sha256"]
    reference["transcript_evidence_id"] = str(replacement_transcript.evidence_id)
    projected_binding = dict(transcript_document["binding"])
    projected_binding["workspaceId"] = reference["import_workspace_id"]
    projected_binding["sessionId"] = reference["projected_session_id"]
    reference["projected_batch_sha256s"] = [
        hashlib.sha256(
            _producer_canonical_json_bytes(
                {**batch_value, "binding": projected_binding}
            )
        ).hexdigest()
        for batch_value in transcript_document["batches"]
    ]
    unsigned_reference = {
        key: value for key, value in reference.items() if key != "run_ref_sha256"
    }
    reference["run_ref_sha256"] = hashlib.sha256(
        _producer_canonical_json_bytes(unsigned_reference)
    ).hexdigest()
    reference_raw = _producer_canonical_json_bytes(reference)
    reference_source = tmp_path / f"extra-{extra_kind}-monitor-ref.json"
    reference_source.write_bytes(reference_raw)
    reference_artifact = evidence.ingest_file(
        reference_source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    reference_metadata = dict(reference_envelope.metadata)
    reference_metadata.update(
        {
            "fixture_sha256": reference["fixture_sha256"],
            "run_ref_sha256": reference["run_ref_sha256"],
        }
    )
    replacement_reference = EvidenceEnvelope(
        identity=reference_envelope.identity,
        operation=reference_envelope.operation,
        produced_at_utc=reference_envelope.produced_at_utc,
        parents=(str(replacement_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(replacement_reference)

    monitor_root_metadata = dict(transcript_root.metadata)
    monitor_root_metadata.update(
        {
            "fixture_sha256": reference["fixture_sha256"],
            "run_ref_sha256": reference["run_ref_sha256"],
        }
    )
    replacement_transcript_root = RootRecord(
        root_type="monitor-run",
        root_id=operation_id,
        manifest_id=str(replacement_transcript.evidence_id),
        metadata=monitor_root_metadata,
    )
    replacement_reference_root = RootRecord(
        root_type="monitor-run-ref",
        root_id=operation_id,
        manifest_id=str(replacement_reference.evidence_id),
        metadata=reference_metadata,
    )
    _evidence_root_path(workspace, "monitor-run", operation_id).unlink()
    _monitor_ref_root_path(workspace, operation_id).unlink()
    put_root(evidence, replacement_transcript_root)
    put_root(evidence, replacement_reference_root)

    analysis_root = get_root(evidence, "monitor-analysis", marker_ref.analysis_id)
    analysis_envelope = evidence.get_envelope(analysis_root.manifest_id)
    analysis = json.loads(
        evidence.read_artifact(
            analysis_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    analysis["before_run_id"] = reference["run_ref_sha256"]
    unsigned_analysis = {
        key: value for key, value in analysis.items() if key != "analysis_id"
    }
    analysis["analysis_id"] = hashlib.sha256(
        _producer_canonical_json_bytes(unsigned_analysis)
    ).hexdigest()
    analysis_raw = _producer_canonical_json_bytes(analysis)
    analysis_source = tmp_path / f"extra-{extra_kind}-analysis.json"
    analysis_source.write_bytes(analysis_raw)
    analysis_artifact = evidence.ingest_file(
        analysis_source,
        kind="monitor-analysis",
        media_type="application/json",
    )
    analysis_metadata = dict(analysis_envelope.metadata)
    analysis_metadata.update(
        {
            "analysis_id": analysis["analysis_id"],
            "before_run_id": analysis["before_run_id"],
        }
    )
    replacement_analysis = EvidenceEnvelope(
        identity=analysis_envelope.identity,
        operation=analysis_envelope.operation,
        produced_at_utc=analysis_envelope.produced_at_utc,
        parents=(
            str(replacement_transcript.evidence_id),
            analysis_envelope.parents[1],
            analysis_envelope.parents[2],
        ),
        artifacts=(analysis_artifact,),
        metadata=analysis_metadata,
    )
    evidence.put_envelope(replacement_analysis)
    replacement_analysis_root = RootRecord(
        root_type="monitor-analysis",
        root_id=analysis["analysis_id"],
        manifest_id=str(replacement_analysis.evidence_id),
        metadata=analysis_metadata,
    )
    _evidence_root_path(workspace, "monitor-analysis", marker_ref.analysis_id).unlink()
    put_root(evidence, replacement_analysis_root)
    return VerificationPlan.new(
        verification_plan_id=plan.verification_plan_id,
        diagnostic_session_id=plan.diagnostic_session_id,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        required_analysis_ids=(analysis["analysis_id"],),
        required_analysis_evidence_ids=(str(replacement_analysis.evidence_id),),
        required_monitor_quality=plan.required_monitor_quality,
        expected_changed=plan.expected_changed,
    )


def _verification_checkpoint_inputs(
    tmp_path: Path,
    workspace: WorkspacePaths,
    session_id: str,
    hypothesis_id: str,
    marker_hypothesis_id: str | None = None,
    analysis_mutation: str | None = None,
    monitor_session_overrides: dict[str, str] | None = None,
    analysis_session_id: str | None = None,
) -> tuple[SourceChangeDeclaration, VerificationPlan, DiagnosticMarkerRef]:
    marker_hypothesis_id = hypothesis_id if marker_hypothesis_id is None else marker_hypothesis_id
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    repository = TestRunRepository(evidence)
    before = repository.load("vs03-failed-before")
    after = repository.load("vs03-fixed-after")

    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(b"--- a/src/main.c\n+++ b/src/main.c\n@@ -1 +1 @@\n-old\n+new\n")
    diff_artifact = evidence.ingest_file(
        diff_path, kind="source-diff", media_type="text/x-diff"
    )
    diff_envelope = EvidenceEnvelope(
        identity=before.envelope.identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-08-21T12:00:00.000000Z",
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    if (
        analysis_mutation is None
        and monitor_session_overrides is None
        and analysis_session_id is None
    ):
        monitor_fixture_dir = Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03"
        monitor_before = ingest_monitor_replay(
            workspace,
            evidence,
            MONITOR_OPERATION_IDS["failed-before"],
            monitor_fixture_dir / "failed-before.json",
        )
        monitor_after = ingest_monitor_replay(
            workspace,
            evidence,
            MONITOR_OPERATION_IDS["fixed-after"],
            monitor_fixture_dir / "fixed-after.json",
        )
        declaration = SourceChangeDeclaration.new(
            before_source_sha256=before.manifest.identity.input_snapshot_sha256,
            after_source_sha256=after.manifest.identity.input_snapshot_sha256,
            before_build_id=before.manifest.identity.build_id,
            before_elf_sha256=before.manifest.identity.elf_sha256,
            after_build_id=after.manifest.identity.build_id,
            after_elf_sha256=after.manifest.identity.elf_sha256,
            changed_paths=("src/main.c",),
            diff_evidence_id=str(diff_envelope.evidence_id),
            diff_artifact=diff_artifact,
            claimed_hypothesis_ids=(hypothesis_id,),
            validation_plan_id="b" * 64,
        )
        publication = compare_monitor_runs(
            workspace,
            evidence,
            AnalysisRequest(
                schema="stm32-monitor-analysis-request/1",
                before_run=monitor_before,
                after_run=monitor_after,
                selector_kind="variable",
                selector="counter",
                alignment="run-relative",
                minimum_valid_pairs=2,
            ),
            session_id,
            hypothesis_id,
            "supports",
            "the replayed analysis observed the declared source change",
            declaration,
        )
        plan = VerificationPlan.new(
            verification_plan_id="b" * 64,
            diagnostic_session_id=session_id,
            failed_before_run_id="vs03-failed-before",
            failed_before_evidence_id=str(before.envelope.evidence_id),
            source_change_declaration_id=declaration.declaration_id,
            fixed_after_run_id="vs03-fixed-after",
            fixed_after_evidence_id=str(after.envelope.evidence_id),
            required_analysis_ids=(publication.analysis_result.analysis_id,),
            required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
            required_monitor_quality=publication.analysis_result.quality,
            expected_changed=True,
        )
        marker_ref = publication.diagnostic_marker_ref
        if marker_hypothesis_id != hypothesis_id:
            marker_ref = replace(marker_ref, hypothesis_id=marker_hypothesis_id)
        return declaration, plan, marker_ref
    transcript_paths = {
        "failed-before": Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03" / "failed-before.json",
        "fixed-after": Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03" / "fixed-after.json",
    }

    def publish_transcript(run: object, role: str) -> EvidenceEnvelope:
        document = json.loads(transcript_paths[role].read_text(encoding="utf-8"))
        binding = document["binding"]
        monitor_session_id = (monitor_session_overrides or {}).get(role)
        if monitor_session_id is not None:
            binding = dict(binding)
            binding["sessionId"] = monitor_session_id
            document["binding"] = binding
            document["batches"] = [
                dict(batch, binding=dict(binding))
                for batch in document["batches"]
            ]
            unsigned_document = {
                key: value for key, value in document.items() if key != "fixture_sha256"
            }
            document["fixture_sha256"] = hashlib.sha256(
                _producer_canonical_json_bytes(unsigned_document)
            ).hexdigest()
            raw = _producer_canonical_json_bytes(document) + b"\n"
        else:
            raw = transcript_paths[role].read_bytes()
        monitor_run_id = str(document["batches"][0]["runId"])
        monitor_identity = EvidenceIdentity(
            workspace_id=binding["workspaceId"],
            project_id=binding["logicalProjectId"],
            session_id=binding["sessionId"],
            build_id=binding["buildId"],
            elf_sha256=binding["elfSha256"],
            target_device=binding["targetDevice"],
            input_snapshot_sha256=binding["inputSnapshotSha256"],
            git_commit=binding["gitHead"],
            git_dirty=binding["gitDirty"],
        )
        source = tmp_path / f"{role}-monitor-transcript.json"
        source.write_bytes(raw)
        artifact = evidence.ingest_file(
            source, kind="monitor-replay-transcript", media_type="application/json"
        )
        operation_id = monitor_run_id
        metadata = {
            "operation_id": operation_id,
            "scenario_role": role,
            "origin_workspace_id": monitor_identity.workspace_id,
            "import_workspace_id": workspace.workspace_id,
            "origin_run_id": monitor_run_id,
            "projected_run_id": monitor_run_id,
            "fixture_sha256": document["fixture_sha256"],
            "execution_source": "replay",
            "physical_transport_evidence": False,
        }
        envelope = EvidenceEnvelope(
            identity=monitor_identity,
            operation="monitor-replay-import",
            produced_at_utc="2026-08-21T12:00:30.000000Z",
            parents=(),
            artifacts=(artifact,),
            metadata=metadata,
        )
        evidence.put_envelope(envelope)
        put_root(
            evidence,
            RootRecord(
                root_type="monitor-run",
                root_id=operation_id,
                manifest_id=str(envelope.evidence_id),
                metadata={
                    "fixture_sha256": document["fixture_sha256"],
                    "run_ref_sha256": "a" * 64,
                    "origin_workspace_id": monitor_identity.workspace_id,
                    "import_workspace_id": workspace.workspace_id,
                    "execution_source": "replay",
                    "physical_transport_evidence": False,
                },
            ),
        )
        return envelope

    before_transcript = publish_transcript(before, "failed-before")
    after_transcript = publish_transcript(after, "fixed-after")
    plan_id = "b" * 64
    declaration = SourceChangeDeclaration.new(
        before_source_sha256=before.manifest.identity.input_snapshot_sha256,
        after_source_sha256=after.manifest.identity.input_snapshot_sha256,
        before_build_id=before.manifest.identity.build_id,
        before_elf_sha256=before.manifest.identity.elf_sha256,
        after_build_id=after.manifest.identity.build_id,
        after_elf_sha256=after.manifest.identity.elf_sha256,
        changed_paths=("src/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id=plan_id,
    )

    analysis: dict[str, object] = {
        "schema": "stm32-monitor-analysis/1",
        "analysis_id": "",
        "request_digest": "1" * 64,
        "before_run_id": str(before.envelope.evidence_id),
        "after_run_id": str(after.envelope.evidence_id),
        "identity": {
            "schema": "stm32-monitor-analysis-lineage/1",
            "origin_workspace_id": after.manifest.identity.workspace_id,
            "import_workspace_id": workspace.workspace_id,
            "logical_project_id": str(PROJECT_ID),
            "target_device": after.manifest.identity.target_device,
            "before_input_snapshot_sha256": before.manifest.identity.input_snapshot_sha256,
            "before_build_id": before.manifest.identity.build_id,
            "before_elf_sha256": before.manifest.identity.elf_sha256,
            "after_input_snapshot_sha256": after.manifest.identity.input_snapshot_sha256,
            "after_build_id": after.manifest.identity.build_id,
            "after_elf_sha256": after.manifest.identity.elf_sha256,
            "source_change_declaration_id": declaration.declaration_id,
        },
        "quality": "VALID",
        "conclusion": "COMPLETED",
        "reason_code": "VALUES_CHANGED",
        "aligned_position_count": 2,
        "aligned_pair_count": 2,
        "excluded_position_count": 0,
        "before_first": 1,
        "before_last": 1,
        "before_min": 1,
        "before_max": 1,
        "after_first": 2,
        "after_last": 2,
        "after_min": 2,
        "after_max": 2,
        "delta_first": 1,
        "delta_last": 1,
        "changed": True,
    }
    if analysis_mutation == "exclusions":
        analysis.update(
            aligned_position_count=3,
            aligned_pair_count=2,
            excluded_position_count=1,
            reason_code="VALUES_CHANGED_WITH_EXCLUSIONS",
        )
    elif analysis_mutation == "reason":
        analysis["reason_code"] = "VALUES_CHANGED_WITH_EXCLUSIONS"
    elif analysis_mutation == "ordering":
        analysis.update(before_min=5, before_max=5)
    elif analysis_mutation == "oversized-count":
        analysis.update(
            aligned_position_count=2049,
            aligned_pair_count=2,
            excluded_position_count=2047,
            reason_code="VALUES_CHANGED_WITH_EXCLUSIONS",
        )
    elif analysis_mutation == "overflow":
        analysis.update(before_first=1e308, after_first=-1e308, delta_first=0)
    elif analysis_mutation == "signed-int64":
        analysis.update(
            before_first=1 << 63,
            before_last=1 << 63,
            before_min=1 << 63,
            before_max=1 << 63,
            after_first=1 << 63,
            after_last=1 << 63,
            after_min=1 << 63,
            after_max=1 << 63,
            delta_first=0,
            delta_last=0,
        )
    elif analysis_mutation == "nfc":
        analysis["identity"]["target_device"] = "stm32:e\u0301"  # type: ignore[index]
    elif analysis_mutation == "string-budget":
        analysis["identity"]["target_device"] = "x" * (1_048_576 + 1)  # type: ignore[index]
    analysis_unsigned = {key: value for key, value in analysis.items() if key != "analysis_id"}
    try:
        analysis_unsigned_bytes = canonical_json_bytes(analysis_unsigned)
    except EvidenceValidationError:
        analysis_unsigned_bytes = _producer_canonical_json_bytes(analysis_unsigned)
    analysis["analysis_id"] = hashlib.sha256(analysis_unsigned_bytes).hexdigest()
    analysis_path = tmp_path / "analysis.json"
    try:
        analysis_bytes = canonical_json_bytes(analysis)
    except EvidenceValidationError:
        analysis_bytes = _producer_canonical_json_bytes(analysis)
    analysis_path.write_bytes(analysis_bytes)
    analysis_artifact = evidence.ingest_file(
        analysis_path, kind="monitor-analysis", media_type="application/json"
    )
    analysis_identity = (
        after_transcript.identity
        if analysis_session_id is None
        else replace(after_transcript.identity, session_id=analysis_session_id)
    )
    analysis_envelope = EvidenceEnvelope(
        identity=analysis_identity,
        operation="monitor-analysis",
        produced_at_utc="2026-08-21T12:01:00.000000Z",
        parents=(
            str(before_transcript.evidence_id),
            str(after_transcript.evidence_id),
            str(diff_envelope.evidence_id),
        ),
        artifacts=(analysis_artifact,),
        metadata={
            "analysis_id": analysis["analysis_id"],
            "before_run_id": analysis["before_run_id"],
            "after_run_id": analysis["after_run_id"],
            "source_change_declaration_id": declaration.declaration_id,
            "origin_workspace_id": after.manifest.identity.workspace_id,
            "import_workspace_id": workspace.workspace_id,
            "origin_session_id": analysis_identity.session_id,
            "execution_source": "replay",
            "physical_transport_evidence": False,
        },
    )
    evidence.put_envelope(analysis_envelope)
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-analysis",
            root_id=str(analysis["analysis_id"]),
            manifest_id=str(analysis_envelope.evidence_id),
            metadata={
                "analysis_id": analysis["analysis_id"],
                "before_run_id": analysis["before_run_id"],
                "after_run_id": analysis["after_run_id"],
                "source_change_declaration_id": declaration.declaration_id,
                "origin_workspace_id": after.manifest.identity.workspace_id,
                "import_workspace_id": workspace.workspace_id,
                "origin_session_id": analysis_identity.session_id,
                "execution_source": "replay",
                "physical_transport_evidence": False,
            },
        ),
    )

    marker: dict[str, object] = {
        "schema": "stm32-diagnostic-marker/1",
        "marker_id": "",
        "analysis_id": analysis["analysis_id"],
        "analysis_evidence_id": str(analysis_envelope.evidence_id),
        "diagnostic_session_id": session_id,
        "hypothesis_id": marker_hypothesis_id,
        "polarity": "supports",
        "label": "change-observed",
        "rationale": "the replayed analysis observed the declared source change",
    }
    marker["marker_id"] = hashlib.sha256(
        canonical_json_bytes({key: value for key, value in marker.items() if key != "marker_id"})
    ).hexdigest()
    marker_path = tmp_path / "marker.json"
    marker_bytes = canonical_json_bytes(marker)
    marker_path.write_bytes(marker_bytes)
    marker_artifact = evidence.ingest_file(
        marker_path, kind="diagnostic-marker", media_type="application/json"
    )
    marker_envelope = EvidenceEnvelope(
        identity=analysis_identity,
        operation="diagnostic-marker",
        produced_at_utc="2026-08-21T12:02:00.000000Z",
        parents=(str(analysis_envelope.evidence_id),),
        artifacts=(marker_artifact,),
        metadata={
            "marker_id": marker["marker_id"],
            "analysis_id": analysis["analysis_id"],
            "analysis_evidence_id": str(analysis_envelope.evidence_id),
            "origin_workspace_id": analysis_envelope.identity.workspace_id,
            "import_workspace_id": workspace.workspace_id,
            "origin_session_id": analysis_envelope.identity.session_id,
            "execution_source": "replay",
            "physical_transport_evidence": False,
        },
    )
    evidence.put_envelope(marker_envelope)
    put_root(
        evidence,
        RootRecord(
            root_type="diagnostic-marker",
            root_id=str(marker["marker_id"]),
            manifest_id=str(marker_envelope.evidence_id),
            metadata={
                "marker_id": marker["marker_id"],
                "analysis_id": analysis["analysis_id"],
                "analysis_evidence_id": str(analysis_envelope.evidence_id),
                "origin_workspace_id": analysis_envelope.identity.workspace_id,
                "import_workspace_id": workspace.workspace_id,
                "origin_session_id": analysis_envelope.identity.session_id,
                "execution_source": "replay",
                "physical_transport_evidence": False,
            },
        ),
    )

    plan = VerificationPlan.new(
        verification_plan_id=plan_id,
        diagnostic_session_id=session_id,
        failed_before_run_id="vs03-failed-before",
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="vs03-fixed-after",
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(str(analysis["analysis_id"]),),
        required_analysis_evidence_ids=(str(analysis_envelope.evidence_id),),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    marker_ref = DiagnosticMarkerRef.new(
        marker_id=str(marker["marker_id"]),
        marker_evidence_id=str(marker_envelope.evidence_id),
        analysis_id=str(analysis["analysis_id"]),
        analysis_evidence_id=str(analysis_envelope.evidence_id),
        diagnostic_session_id=session_id,
        hypothesis_id=marker_hypothesis_id,
        polarity="supports",
        label="change-observed",
        rationale="the replayed analysis observed the declared source change",
    )
    return declaration, plan, marker_ref


def _prepared_checkpoint_for_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    monitor_session_overrides: dict[str, str] | None = None,
    analysis_session_id: str | None = None,
) -> tuple[DiagnosticWorkflowContext, str, WorkspacePaths, SourceChangeDeclaration, VerificationPlan, DiagnosticMarkerRef]:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    fixed_replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    )
    assert fixed_replay.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, marker_ref = _verification_checkpoint_inputs(
        tmp_path,
        workspace,
        session_id,
        hypothesis_id,
        monitor_session_overrides=monitor_session_overrides,
        analysis_session_id=analysis_session_id,
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    ).ok is True
    return diagnostic_context, session_id, workspace, declaration, plan, marker_ref


def _prepared_checkpoint_for_attach(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    monitor_session_overrides: dict[str, str] | None = None,
    analysis_session_id: str | None = None,
) -> tuple[DiagnosticWorkflowContext, str, WorkspacePaths, SourceChangeDeclaration, VerificationPlan, DiagnosticMarkerRef]:
    (
        diagnostic_context,
        session_id,
        workspace,
        declaration,
        plan,
        marker_ref,
    ) = _prepared_checkpoint_for_plan(
        monkeypatch,
        tmp_path,
        monitor_session_overrides=monitor_session_overrides,
        analysis_session_id=analysis_session_id,
    )
    assert diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    ).ok is True
    assert diagnostic_start_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.start",
        diagnostic_session_id=session_id,
        expected_revision=5,
        verification_plan_id=plan.verification_plan_id,
    ).ok is True
    return diagnostic_context, session_id, workspace, declaration, plan, marker_ref


def test_target_replay_diagnostic_session_reloads_with_origin_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    origin_workspace_id = replay.data["run"]["identity"]["workspace_id"]
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert replay.ok is True
    assert started.ok is True and started.data["session"]["state"] == "OPEN"
    session_id = started.data["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.begin",
        diagnostic_session_id=session_id,
        expected_revision=1,
    )
    assert begun.ok is True and begun.data["session"]["state"] == "INVESTIGATING"
    added = diagnostic_add_hypothesis(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.hypothesis.add",
        diagnostic_session_id=session_id,
        expected_revision=2,
        statement="the replayed failed run identifies the faulty behavior",
    )
    assert added.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    assert shown.data["session"]["identity"]["workspace_id"] == origin_workspace_id
    assert origin_workspace_id != WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
    ).workspace_id


def test_target_replay_start_rejects_foreign_project_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    foreign_project_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch, foreign_project_id)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        foreign_project_id,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.foreign-project",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("missing", "EVIDENCE_INTEGRITY_FAILURE"),
        ("provider", "ENVIRONMENT_FAILURE"),
    ),
)
def test_target_replay_start_classifies_repository_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )

    class FailingRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            if failure == "missing":
                raise FileNotFoundError("immutable TestRun material is missing")
            raise OSError("evidence provider is unavailable")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", FailingRepository)
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.start.{failure}",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == expected_code
    assert after == before


def test_target_replay_real_repository_provider_failure_is_environment_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )

    def provider_failure(
        _store: EvidenceStore, _artifact: object, *, maximum_bytes: int
    ) -> bytes:
        raise OSError("evidence provider is unavailable")

    monkeypatch.setattr(EvidenceStore, "read_artifact", provider_failure)
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-provider-real",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "ENVIRONMENT_FAILURE"
    assert after == before


def test_target_replay_start_missing_published_root_is_integrity_failure_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    _target_test_run_root(workspace).unlink()
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-missing-root",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_default_host_repository_corruption_keeps_legacy_failure_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)

    class CorruptRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "corrupt")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", CorruptRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.host-corrupt",
        failed_test_run_id="host-failed-run",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    assert started.message == "required TestRun evidence is absent or damaged"
    assert started.details == {}
    assert after == before


def test_invalid_failed_run_mode_is_rejected_before_repository_access_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)

    class ForbiddenRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise AssertionError("invalid mode must be rejected before repository access")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", ForbiddenRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.invalid-mode",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="invalid",  # type: ignore[arg-type]
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_INVALID_EVENT"
    assert after == before


def test_target_mode_rejects_host_record_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    original_factory = diagnostic_workflows._repository_factory

    class HostRecordRepository:
        def __init__(self, evidence_store: object) -> None:
            self._repository = original_factory(evidence_store)

        def load(self, run_id: str) -> object:
            published = self._repository.load(run_id)
            return replace(
                published,
                manifest=replace(published.manifest, mode="host", transport=None),
            )

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", HostRecordRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-host-record",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_default_host_mode_rejects_target_record_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.host-target-record",
        failed_test_run_id="vs03-failed-before",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_INVALID_EVENT"
    assert after == before


def test_target_alias_show_uses_durable_mode_after_published_root_is_deleted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    origin_workspace_id = load_target_replay_fixture(
        FIXTURES / "failed-before.json", FIXTURES / "failed-before.hex"
    ).descriptor.identity.workspace_id
    original_factory = WorkspacePaths.from_roots

    def alias_factory(
        data_root: Path,
        project_root: Path,
        logical_project_id: UUID,
        session_id: str | None = None,
    ) -> WorkspacePaths:
        actual = original_factory(data_root, project_root, logical_project_id, session_id)
        return replace(actual, workspace_id=origin_workspace_id)

    monkeypatch.setattr(testing_workflows.WorkspacePaths, "from_roots", alias_factory)
    monkeypatch.setattr(diagnostic_workflows, "_workspace_paths_factory", alias_factory)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.alias-missing-root",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    session_id = started.data["session"]["diagnostic_session_id"]
    workspace = original_factory(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    _target_test_run_root(workspace).unlink()
    before = _authority_snapshot(workspace)
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    after = _authority_snapshot(workspace)
    assert shown.ok is False
    assert shown.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_target_replay_alias_workspace_is_legal_for_start_and_show(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    origin_workspace_id = load_target_replay_fixture(
        FIXTURES / "failed-before.json", FIXTURES / "failed-before.hex"
    ).descriptor.identity.workspace_id
    original_factory = WorkspacePaths.from_roots

    def alias_factory(
        data_root: Path,
        project_root: Path,
        logical_project_id: UUID,
        session_id: str | None = None,
    ) -> WorkspacePaths:
        actual = original_factory(data_root, project_root, logical_project_id, session_id)
        return replace(actual, workspace_id=origin_workspace_id)

    monkeypatch.setattr(testing_workflows.WorkspacePaths, "from_roots", alias_factory)
    monkeypatch.setattr(diagnostic_workflows, "_workspace_paths_factory", alias_factory)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.alias",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context),
        diagnostic_session_id=started.data["session"]["diagnostic_session_id"],
    )
    assert shown.ok is True
    assert shown.data["session"]["identity"]["workspace_id"] == origin_workspace_id


def _tamper_published(kind: str, published: object) -> object:
    manifest = published.manifest
    root = published.root
    if kind == "foreign_manifest_identity":
        foreign = replace(manifest.identity, workspace_id="f" * 64)
        return replace(published, manifest=replace(manifest, identity=foreign))
    if kind == "physical_flag":
        metadata = dict(root.metadata)
        metadata["physical_transport_evidence"] = True
        return replace(published, root=replace(root, metadata=metadata))
    if kind == "non_replay_transport":
        return replace(published, manifest=replace(manifest, transport="physical"))
    if kind == "wrong_origin_metadata":
        metadata = dict(root.metadata)
        metadata["origin_workspace_id"] = "a" * 64
        return replace(published, root=replace(root, metadata=metadata))
    if kind == "wrong_current_import_metadata":
        metadata = dict(root.metadata)
        metadata["import_workspace_id"] = "b" * 64
        return replace(published, root=replace(root, metadata=metadata))
    raise AssertionError(f"unknown tamper kind: {kind}")


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    (
        ("foreign_manifest_identity", "INCOMPATIBLE_IDENTITY"),
        ("physical_flag", "EVIDENCE_INTEGRITY_FAILURE"),
        ("non_replay_transport", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong_origin_metadata", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong_current_import_metadata", "EVIDENCE_INTEGRITY_FAILURE"),
    ),
)
def test_target_replay_authority_rejects_foreign_or_contradictory_records_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    expected_code: str,
) -> None:
    diagnostic_context, session_id, _replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    original_factory = diagnostic_workflows._repository_factory

    class TamperedRepository:
        def __init__(self, evidence_store: object) -> None:
            self._repository = original_factory(evidence_store)

        def load(self, run_id: str) -> object:
            return _tamper_published(kind, self._repository.load(run_id))

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", TamperedRepository)
    before = _authority_snapshot(workspace)
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    after = _authority_snapshot(workspace)
    assert shown.ok is False
    assert shown.code == expected_code
    assert after == before


def test_target_replay_prepares_and_reloads_fix_verification_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    fixed_replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    )
    assert fixed_replay.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, marker_ref = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id
    )
    monitor_evidence = EvidenceStore(workspace.workspace_root / "evidence")
    analysis_envelope = monitor_evidence.get_envelope(marker_ref.analysis_evidence_id)
    analysis_payload = json.loads(
        monitor_evidence.read_artifact(
            analysis_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    assert analysis_payload["before_run_id"] == get_root(
        monitor_evidence,
        "monitor-run-ref",
        MONITOR_OPERATION_IDS["failed-before"],
    ).metadata["run_ref_sha256"]
    assert analysis_payload["after_run_id"] == get_root(
        monitor_evidence,
        "monitor-run-ref",
        MONITOR_OPERATION_IDS["fixed-after"],
    ).metadata["run_ref_sha256"]
    analysis_envelope = EvidenceStore(workspace.workspace_root / "evidence").get_envelope(
        marker_ref.analysis_evidence_id
    )
    assert analysis_envelope.identity.session_id != shown.data["session"]["identity"]["session_id"]
    evidence_before = _tree_snapshot(workspace.workspace_root / "evidence")

    declared = diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    )
    assert declared.ok is True
    added = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    assert added.ok is True
    started = diagnostic_start_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.start",
        diagnostic_session_id=session_id,
        expected_revision=5,
        verification_plan_id=plan.verification_plan_id,
    )
    assert started.ok is True
    attached = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
    )
    assert attached.ok is True
    assert attached.data["session"]["state"] == "VERIFYING"
    assert attached.data["diagnostic_marker_ref"] == marker_ref.to_dict()
    marker_envelope = EvidenceStore(workspace.workspace_root / "evidence").get_envelope(
        marker_ref.marker_evidence_id
    )
    assert marker_envelope.identity == analysis_envelope.identity
    assert marker_envelope.metadata["origin_session_id"] == analysis_envelope.identity.session_id
    evidence_after = dict(_tree_snapshot(workspace.workspace_root / "evidence"))
    assert all(evidence_after.get(path) == payload for path, payload in evidence_before)

    reloaded = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert reloaded.ok is True
    reloaded_session = reloaded.data["session"]
    assert reloaded_session["state"] == "VERIFYING"
    assert json.loads(canonical_json_bytes(reloaded_session["source_change_declarations"])) == [
        declaration.to_dict()
    ]
    assert json.loads(canonical_json_bytes(reloaded_session["verification_plans"])) == [
        plan.to_dict()
    ]
    assert json.loads(canonical_json_bytes(reloaded_session["diagnostic_marker_refs"])) == [
        marker_ref.to_dict()
    ]

    retry = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
    )
    assert retry.to_dict() == attached.to_dict()


@pytest.mark.parametrize(
    "mutation",
    ("digest-only", "swapped", "binding", "window", "group", "batch-digest"),
)
def test_target_replay_plan_requires_complete_monitor_reference_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str
) -> None:
    diagnostic_context, session_id, workspace, declaration, plan, _marker_ref = (
        _prepared_checkpoint_for_plan(monkeypatch, tmp_path)
    )
    before_operation_id = MONITOR_OPERATION_IDS["failed-before"]
    if mutation == "digest-only":
        _monitor_ref_root_path(workspace, before_operation_id).unlink()
    elif mutation == "swapped":
        _swap_monitor_reference_authority(
            workspace,
            before_operation_id,
            MONITOR_OPERATION_IDS["fixed-after"],
        )
    elif mutation == "binding":
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload.update(target_device="stm32:swapped-device"),
        )
    elif mutation == "window":
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload.update(start_sequence=1, end_sequence_exclusive=2),
        )
    elif mutation == "group":
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload.update(group_id="22222222-2222-4222-8222-222222222222"),
        )
    else:
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload["projected_batch_sha256s"].__setitem__(0, "0" * 64),
        )
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.verification-plan.add.monitor-ref-{mutation}",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


@pytest.mark.parametrize("extra_kind", ("batch", "sample", "typed", "watch"))
def test_target_replay_rejects_nonclosed_monitor_projection_fields_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_kind: str,
) -> None:
    diagnostic_context, session_id, workspace, declaration, plan, marker_ref = (
        _prepared_checkpoint_for_plan(monkeypatch, tmp_path)
    )
    plan = _replace_monitor_transcript_and_analysis(
        tmp_path,
        workspace,
        MONITOR_OPERATION_IDS["failed-before"],
        marker_ref,
        plan,
        extra_kind,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    transcript_root = get_root(
        evidence,
        "monitor-run",
        MONITOR_OPERATION_IDS["failed-before"],
    )
    transcript_envelope = evidence.get_envelope(transcript_root.manifest_id)
    transcript_payload = json.loads(
        evidence.read_artifact(
            transcript_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    with pytest.raises(MonitorReplayError):
        MonitorReplayDocument.from_value(transcript_payload)
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.verification-plan.add.extra-{extra_kind}",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_target_replay_rejects_self_consistent_whitespace_selector_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostic_context, session_id, workspace, declaration, plan, marker_ref = (
        _prepared_checkpoint_for_plan(monkeypatch, tmp_path)
    )
    plan = _replace_monitor_transcript_and_analysis(
        tmp_path,
        workspace,
        MONITOR_OPERATION_IDS["failed-before"],
        marker_ref,
        plan,
        "whitespace",
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    transcript_root = get_root(
        evidence,
        "monitor-run",
        MONITOR_OPERATION_IDS["failed-before"],
    )
    transcript_envelope = evidence.get_envelope(transcript_root.manifest_id)
    transcript_payload = json.loads(
        evidence.read_artifact(
            transcript_envelope.artifacts[0], maximum_bytes=1_000_000
        ).decode("utf-8")
    )
    with pytest.raises(MonitorReplayError):
        MonitorReplayDocument.from_value(transcript_payload)
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add.whitespace-selector",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


@pytest.mark.parametrize(
    ("mutation", "monitor_session_overrides", "analysis_session_id"),
    (
        (
            "transcript-session-mismatch",
            {"failed-before": "vs03-monitor-before-only"},
            None,
        ),
        ("analysis-identity-session-mismatch", None, "vs03-monitor-third"),
    ),
)
def test_target_replay_rejects_monitor_producer_pair_mismatch_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    monitor_session_overrides: dict[str, str] | None,
    analysis_session_id: str | None,
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        plan,
        _marker_ref,
    ) = _prepared_checkpoint_for_plan(
        monkeypatch,
        tmp_path,
        monitor_session_overrides=monitor_session_overrides,
        analysis_session_id=analysis_session_id,
    )
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.verification-plan.add.{mutation}",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_target_replay_declaration_rejects_rehashed_before_lineage_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    fixed_replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    )
    assert fixed_replay.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, _plan, _marker = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id
    )
    wrong_before = SourceChangeDeclaration.new(
        before_source_sha256="f" * 64,
        after_source_sha256=declaration.after_source_sha256,
        before_build_id=declaration.before_build_id,
        before_elf_sha256=declaration.before_elf_sha256,
        after_build_id=declaration.after_build_id,
        after_elf_sha256=declaration.after_elf_sha256,
        changed_paths=declaration.changed_paths,
        diff_evidence_id=declaration.diff_evidence_id,
        diff_artifact=declaration.diff_artifact,
        claimed_hypothesis_ids=declaration.claimed_hypothesis_ids,
        validation_plan_id=declaration.validation_plan_id,
    )
    before = _authority_snapshot(workspace)
    result = diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare.wrong-before",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=wrong_before,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


def test_target_replay_plan_rejects_rehashed_after_lineage_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    assert testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    ).ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, _marker = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id
    )
    wrong_after = SourceChangeDeclaration.new(
        before_source_sha256=declaration.before_source_sha256,
        after_source_sha256="e" * 64,
        before_build_id=declaration.before_build_id,
        before_elf_sha256=declaration.before_elf_sha256,
        after_build_id=declaration.after_build_id,
        after_elf_sha256=declaration.after_elf_sha256,
        changed_paths=declaration.changed_paths,
        diff_evidence_id=declaration.diff_evidence_id,
        diff_artifact=declaration.diff_artifact,
        claimed_hypothesis_ids=declaration.claimed_hypothesis_ids,
        validation_plan_id=declaration.validation_plan_id,
    )
    wrong_plan = VerificationPlan.new(
        verification_plan_id=plan.verification_plan_id,
        diagnostic_session_id=plan.diagnostic_session_id,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=wrong_after.declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        required_analysis_ids=plan.required_analysis_ids,
        required_analysis_evidence_ids=plan.required_analysis_evidence_ids,
        required_monitor_quality=plan.required_monitor_quality,
        expected_changed=plan.expected_changed,
    )
    declared = diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare.wrong-after",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=wrong_after,
    )
    assert declared.ok is True
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add.wrong-after",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=wrong_plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


def test_target_replay_attach_rejects_same_identity_nontranscript_analysis_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_context, session_id, workspace, _declaration, _plan, marker_ref = (
        _prepared_checkpoint_for_attach(monkeypatch, tmp_path)
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    failed = TestRunRepository(evidence).load("vs03-failed-before")
    original_get_envelope = EvidenceStore.get_envelope

    def tampered_get_envelope(
        store: EvidenceStore, evidence_id: str
    ) -> EvidenceEnvelope:
        envelope = original_get_envelope(store, evidence_id)
        if evidence_id != marker_ref.analysis_evidence_id:
            return envelope
        tampered = copy.copy(envelope)
        object.__setattr__(
            tampered,
            "parents",
            (str(failed.envelope.evidence_id), envelope.parents[1], envelope.parents[2]),
        )
        return tampered

    monkeypatch.setattr(EvidenceStore, "get_envelope", tampered_get_envelope)
    before = _authority_snapshot(workspace)
    result = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach.wrong-parent",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_target_replay_attach_rejects_unclaimed_marker_hypothesis_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    claimed_hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    second = diagnostic_add_hypothesis(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.hypothesis.add.second",
        diagnostic_session_id=session_id,
        expected_revision=3,
        statement="a second existing hypothesis is not claimed by the source change",
    )
    assert second.ok is True
    unclaimed_hypothesis_id = second.data["hypothesis"]["hypothesis_id"]
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    assert testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    ).ok is True
    declaration, plan, marker_ref = _verification_checkpoint_inputs(
        tmp_path,
        workspace,
        session_id,
        claimed_hypothesis_id,
        marker_hypothesis_id=unclaimed_hypothesis_id,
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare.unclaimed",
        diagnostic_session_id=session_id,
        expected_revision=4,
        source_change_declaration=declaration,
    ).ok is True
    assert diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add.unclaimed",
        diagnostic_session_id=session_id,
        expected_revision=5,
        verification_plan=plan,
    ).ok is True
    assert diagnostic_start_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.start.unclaimed",
        diagnostic_session_id=session_id,
        expected_revision=6,
        verification_plan_id=plan.verification_plan_id,
    ).ok is True
    before = _authority_snapshot(workspace)
    result = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach.unclaimed",
        diagnostic_session_id=session_id,
        expected_revision=7,
        diagnostic_marker_ref=marker_ref,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_PLAN_INVALID"
    assert after == before


@pytest.mark.parametrize(
    "analysis_mutation",
    (
        "exclusions", "reason", "ordering", "oversized-count", "overflow",
        "signed-int64", "nfc", "string-budget",
    ),
)
def test_target_replay_plan_rejects_impossible_valid_analysis_semantics_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, analysis_mutation: str
) -> None:
    diagnostic_context, session_id, _failed_replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    assert testing_workflows.target_replay_run(
        testing_context,
        "vs03-fixed-after",
        FIXTURES / "fixed-after.json",
        FIXTURES / "fixed-after.hex",
    ).ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, _marker = _verification_checkpoint_inputs(
        tmp_path,
        workspace,
        session_id,
        hypothesis_id,
        analysis_mutation=analysis_mutation,
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.source-change.declare.{analysis_mutation}",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    ).ok is True
    before = _authority_snapshot(workspace)
    result = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.verification-plan.add.{analysis_mutation}",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("payload-ref-schema", "DIAGNOSTIC_INVALID_EVENT"),
        ("extra-marker-field", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong-unsigned-marker-id", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong-marker-envelope-id", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong-operation", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong-kind-media", "EVIDENCE_INTEGRITY_FAILURE"),
        ("corrupt-artifact", "EVIDENCE_INTEGRITY_FAILURE"),
        ("noncanonical-artifact", "EVIDENCE_INTEGRITY_FAILURE"),
        ("absent-analysis-root", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong-analysis-unsigned-id", "EVIDENCE_INTEGRITY_FAILURE"),
        ("foreign-analysis-identity", "INCOMPATIBLE_IDENTITY"),
    ),
)
def test_target_replay_attach_fail_closed_matrix_preserves_complete_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    diagnostic_context, session_id, workspace, _declaration, _plan, marker_ref = (
        _prepared_checkpoint_for_attach(monkeypatch, tmp_path)
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    original_get_envelope = EvidenceStore.get_envelope
    original_read_artifact = EvidenceStore.read_artifact
    original_get_root = diagnostic_workflows.get_root
    marker_envelope = evidence.get_envelope(marker_ref.marker_evidence_id)
    analysis_envelope = evidence.get_envelope(marker_ref.analysis_evidence_id)

    view_envelopes: dict[str, EvidenceEnvelope] = {}
    view_roots: dict[tuple[str, str], RootRecord] = {}

    def install_artifact_view(
        envelope: EvidenceEnvelope,
        *,
        root_type: str,
        root_id: str,
        payload: bytes,
        parents: tuple[str, ...] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[EvidenceEnvelope, RootRecord, ArtifactRef]:
        digest = hashlib.sha256(payload).hexdigest()
        artifact = ArtifactRef(
            sha256=digest,
            size_bytes=len(payload),
            relative_path=f"objects/sha256/{digest[:2]}/{digest}",
            kind=envelope.artifacts[0].kind,
            media_type=envelope.artifacts[0].media_type,
        )
        view = EvidenceEnvelope(
            identity=envelope.identity,
            operation=envelope.operation,
            produced_at_utc=envelope.produced_at_utc,
            parents=envelope.parents if parents is None else parents,
            artifacts=(artifact,),
            metadata=envelope.metadata if metadata is None else metadata,
        )
        root = RootRecord(
            root_type=root_type,
            root_id=root_id,
            manifest_id=str(view.evidence_id),
            metadata=dict(view.metadata),
        )
        view_envelopes[str(view.evidence_id)] = view
        view_roots[(root_type, root_id)] = root
        assert artifact.size_bytes == len(payload)
        assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
        assert root.manifest_id == str(view.evidence_id)
        return view, root, artifact

    marker_input: object = marker_ref
    if mutation == "payload-ref-schema":
        marker_input = dict(marker_ref.to_dict())
        marker_input["schema"] = "stm32-diagnostic-marker/1"
    elif mutation == "wrong-marker-envelope-id":
        marker_input = DiagnosticMarkerRef.new(
            marker_id=marker_ref.marker_id,
            marker_evidence_id="0" * 64,
            analysis_id=marker_ref.analysis_id,
            analysis_evidence_id=marker_ref.analysis_evidence_id,
            diagnostic_session_id=marker_ref.diagnostic_session_id,
            hypothesis_id=marker_ref.hypothesis_id,
            polarity=marker_ref.polarity,
            label=marker_ref.label,
            rationale=marker_ref.rationale,
        )
    elif mutation in {"extra-marker-field", "wrong-unsigned-marker-id", "corrupt-artifact", "noncanonical-artifact"}:
        marker_payload = original_read_artifact(
            evidence, marker_envelope.artifacts[0], maximum_bytes=1_000_000
        )
        wrong_marker_id: str | None = None
        if mutation == "corrupt-artifact":
            tampered_marker_payload = b"not-json"
        else:
            payload = json.loads(marker_payload.decode("utf-8"))
            if mutation == "extra-marker-field":
                payload["extra"] = True
            elif mutation == "wrong-unsigned-marker-id":
                wrong_marker_id = "0" * 64
                payload["marker_id"] = wrong_marker_id
            else:
                tampered_marker_payload = b" {" + marker_payload.strip()[1:-1] + b" }"
            if mutation != "noncanonical-artifact":
                tampered_marker_payload = _producer_canonical_json_bytes(payload)

        if mutation != "corrupt-artifact":
            marker_id_for_view = marker_ref.marker_id if wrong_marker_id is None else wrong_marker_id
            view, marker_root, _artifact = install_artifact_view(
                marker_envelope,
                root_type="diagnostic-marker",
                root_id=marker_id_for_view,
                payload=tampered_marker_payload,
                metadata={
                    **marker_envelope.metadata,
                    "marker_id": marker_id_for_view,
                },
            )
            marker_input = DiagnosticMarkerRef.new(
                marker_id=marker_id_for_view,
                marker_evidence_id=str(view.evidence_id),
                analysis_id=marker_ref.analysis_id,
                analysis_evidence_id=marker_ref.analysis_evidence_id,
                diagnostic_session_id=marker_ref.diagnostic_session_id,
                hypothesis_id=marker_ref.hypothesis_id,
                polarity=marker_ref.polarity,
                label=marker_ref.label,
                rationale=marker_ref.rationale,
            )
            marker_payload_view = json.loads(tampered_marker_payload.decode("utf-8"))
            marker_unsigned_view = {
                key: value for key, value in marker_payload_view.items() if key != "marker_id"
            }
            assert marker_payload_view["marker_id"] == marker_id_for_view
            assert marker_input.marker_id == marker_id_for_view
            assert marker_root.root_id == marker_id_for_view
            assert marker_root.manifest_id == str(view.evidence_id)
            assert view.artifacts[0].sha256 == hashlib.sha256(tampered_marker_payload).hexdigest()
            if mutation == "wrong-unsigned-marker-id":
                assert hashlib.sha256(
                    _producer_canonical_json_bytes(marker_unsigned_view)
                ).hexdigest() != marker_id_for_view

        def tampered_read_artifact(
            store: EvidenceStore, artifact: object, *, maximum_bytes: int
        ) -> bytes:
            if mutation != "corrupt-artifact" and artifact == view.artifacts[0]:
                return tampered_marker_payload
            if mutation == "corrupt-artifact" and artifact == marker_envelope.artifacts[0]:
                return tampered_marker_payload
            return original_read_artifact(store, artifact, maximum_bytes=maximum_bytes)

        monkeypatch.setattr(EvidenceStore, "read_artifact", tampered_read_artifact)
    elif mutation == "wrong-analysis-unsigned-id":
        analysis_payload = original_read_artifact(
            evidence, analysis_envelope.artifacts[0], maximum_bytes=1_000_000
        )
        payload = json.loads(analysis_payload.decode("utf-8"))
        wrong_analysis_id = "0" * 64
        payload["analysis_id"] = wrong_analysis_id
        tampered_analysis_payload = _producer_canonical_json_bytes(payload)
        analysis_view, analysis_root, _artifact = install_artifact_view(
            analysis_envelope,
            root_type="monitor-analysis",
            root_id=wrong_analysis_id,
            payload=tampered_analysis_payload,
            metadata={
                **analysis_envelope.metadata,
                "analysis_id": wrong_analysis_id,
            },
        )
        wrong_analysis_evidence_id = str(analysis_view.evidence_id)
        analysis_payload_view = json.loads(tampered_analysis_payload.decode("utf-8"))
        analysis_unsigned_view = {
            key: value for key, value in analysis_payload_view.items() if key != "analysis_id"
        }
        assert analysis_payload_view["analysis_id"] == wrong_analysis_id
        assert analysis_root.root_id == wrong_analysis_id
        assert analysis_root.manifest_id == wrong_analysis_evidence_id
        assert analysis_view.artifacts[0].sha256 == hashlib.sha256(
            tampered_analysis_payload
        ).hexdigest()
        assert hashlib.sha256(
            _producer_canonical_json_bytes(analysis_unsigned_view)
        ).hexdigest() != wrong_analysis_id
        stored_state = diagnostic_workflows._make_state(
            _fresh_diagnostic_context(diagnostic_context)
        )
        stored_session = stored_state.diagnostic_store.load(session_id)
        original_load = diagnostic_workflows.DiagnosticStore.load
        original_plan = stored_session.verification_plans[0]
        mutated_plan = VerificationPlan.new(
            verification_plan_id=original_plan.verification_plan_id,
            diagnostic_session_id=original_plan.diagnostic_session_id,
            failed_before_run_id=original_plan.failed_before_run_id,
            failed_before_evidence_id=original_plan.failed_before_evidence_id,
            source_change_declaration_id=original_plan.source_change_declaration_id,
            fixed_after_run_id=original_plan.fixed_after_run_id,
            fixed_after_evidence_id=original_plan.fixed_after_evidence_id,
            required_analysis_ids=(wrong_analysis_id,),
            required_analysis_evidence_ids=(wrong_analysis_evidence_id,),
            required_monitor_quality=original_plan.required_monitor_quality,
            expected_changed=original_plan.expected_changed,
        )
        mutated_session = replace(
            stored_session,
            verification_plans=(mutated_plan,),
        )

        def tampered_load(store: object, requested_session_id: str) -> object:
            if requested_session_id == session_id:
                return mutated_session
            return original_load(store, requested_session_id)

        monkeypatch.setattr(diagnostic_workflows.DiagnosticStore, "load", tampered_load)
        marker_payload = json.loads(
            original_read_artifact(
                evidence, marker_envelope.artifacts[0], maximum_bytes=1_000_000
            ).decode("utf-8")
        )
        marker_payload["analysis_id"] = wrong_analysis_id
        marker_payload["analysis_evidence_id"] = wrong_analysis_evidence_id
        marker_unsigned = {
            key: value for key, value in marker_payload.items() if key != "marker_id"
        }
        wrong_marker_id = hashlib.sha256(
            _producer_canonical_json_bytes(marker_unsigned)
        ).hexdigest()
        marker_payload["marker_id"] = wrong_marker_id
        tampered_marker_payload = _producer_canonical_json_bytes(marker_payload)
        marker_view, marker_root, _artifact = install_artifact_view(
            marker_envelope,
            root_type="diagnostic-marker",
            root_id=wrong_marker_id,
            payload=tampered_marker_payload,
            parents=(wrong_analysis_evidence_id,),
            metadata={
                **marker_envelope.metadata,
                "marker_id": wrong_marker_id,
                "analysis_id": wrong_analysis_id,
                "analysis_evidence_id": wrong_analysis_evidence_id,
            },
        )
        marker_input = DiagnosticMarkerRef.new(
            marker_id=wrong_marker_id,
            marker_evidence_id=str(marker_view.evidence_id),
            analysis_id=wrong_analysis_id,
            analysis_evidence_id=wrong_analysis_evidence_id,
            diagnostic_session_id=marker_ref.diagnostic_session_id,
            hypothesis_id=marker_ref.hypothesis_id,
            polarity=marker_ref.polarity,
            label=marker_ref.label,
            rationale=marker_ref.rationale,
        )
        marker_payload_view = json.loads(tampered_marker_payload.decode("utf-8"))
        assert marker_payload_view["analysis_id"] == wrong_analysis_id
        assert marker_payload_view["analysis_evidence_id"] == wrong_analysis_evidence_id
        assert marker_payload_view["marker_id"] == wrong_marker_id
        assert marker_input.marker_id == wrong_marker_id
        assert marker_input.analysis_id == wrong_analysis_id
        assert marker_input.analysis_evidence_id == wrong_analysis_evidence_id
        assert marker_root.root_id == wrong_marker_id
        assert marker_root.manifest_id == str(marker_view.evidence_id)
        assert marker_view.parents == (wrong_analysis_evidence_id,)
        assert marker_view.artifacts[0].sha256 == hashlib.sha256(
            tampered_marker_payload
        ).hexdigest()
        assert hashlib.sha256(
            _producer_canonical_json_bytes(
                {key: value for key, value in marker_payload_view.items() if key != "marker_id"}
            )
        ).hexdigest() == wrong_marker_id

        def tampered_read_artifact(
            store: EvidenceStore, artifact: object, *, maximum_bytes: int
        ) -> bytes:
            if artifact == analysis_view.artifacts[0]:
                return tampered_analysis_payload
            if artifact == marker_view.artifacts[0]:
                return tampered_marker_payload
            return original_read_artifact(store, artifact, maximum_bytes=maximum_bytes)

        monkeypatch.setattr(EvidenceStore, "read_artifact", tampered_read_artifact)
    elif mutation == "absent-analysis-root":
        def absent_analysis_root(store: EvidenceStore, root_type: str, root_id: str) -> RootRecord:
            if root_type == "monitor-analysis" and root_id == marker_ref.analysis_id:
                raise EvidenceValidationError(EVIDENCE_CORRUPT, "analysis root is absent")
            return original_get_root(store, root_type, root_id)

        monkeypatch.setattr(diagnostic_workflows, "get_root", absent_analysis_root)
    elif mutation in {"wrong-operation", "wrong-kind-media", "foreign-analysis-identity"}:
        target_id = marker_ref.marker_evidence_id if mutation != "foreign-analysis-identity" else marker_ref.analysis_evidence_id
        target_seen = False

        def tampered_get_envelope(store: EvidenceStore, evidence_id: str) -> EvidenceEnvelope:
            nonlocal target_seen
            envelope = original_get_envelope(store, evidence_id)
            if evidence_id != target_id:
                return envelope
            if mutation == "foreign-analysis-identity" and not target_seen:
                target_seen = True
                return envelope
            tampered = copy.copy(envelope)
            if mutation == "wrong-operation":
                object.__setattr__(tampered, "operation", "wrong-operation")
            elif mutation == "wrong-kind-media":
                artifact = copy.copy(envelope.artifacts[0])
                object.__setattr__(artifact, "kind", "wrong-kind")
                object.__setattr__(artifact, "media_type", "text/plain")
                object.__setattr__(tampered, "artifacts", (artifact,))
            else:
                identity = replace(envelope.identity, workspace_id="f" * 64)
                object.__setattr__(tampered, "identity", identity)
            return tampered

        monkeypatch.setattr(EvidenceStore, "get_envelope", tampered_get_envelope)

    if view_envelopes or view_roots:
        def view_get_envelope(store: EvidenceStore, evidence_id: str) -> EvidenceEnvelope:
            if evidence_id in view_envelopes:
                return view_envelopes[evidence_id]
            return original_get_envelope(store, evidence_id)

        def view_get_root(store: EvidenceStore, root_type: str, root_id: str) -> RootRecord:
            if (root_type, root_id) in view_roots:
                return view_roots[(root_type, root_id)]
            return original_get_root(store, root_type, root_id)

        monkeypatch.setattr(EvidenceStore, "get_envelope", view_get_envelope)
        monkeypatch.setattr(diagnostic_workflows, "get_root", view_get_root)

    before = (
        _tree_snapshot(workspace.workspace_root / "evidence"),
        _tree_snapshot(workspace.diagnostics_root),
    )
    result = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.marker.attach.matrix.{mutation}",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_input,  # type: ignore[arg-type]
    )
    after = (
        _tree_snapshot(workspace.workspace_root / "evidence"),
        _tree_snapshot(workspace.diagnostics_root),
    )
    assert result.ok is False
    assert result.code == expected_code
    assert after == before
