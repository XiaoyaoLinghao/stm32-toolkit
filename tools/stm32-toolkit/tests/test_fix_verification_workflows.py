from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.replay import (
    MonitorReplayError,
    MonitorReplayDocument,
    ingest_monitor_replay,
)
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
import stm32_toolkit.testing_workflows as testing_workflows
import test_vs08b_scenarios as vs08b
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_verification_plan,
    diagnostic_assess_hypothesis,
    diagnostic_attach_marker,
    diagnostic_begin,
    diagnostic_complete_verification,
    diagnostic_declare_source_change,
    diagnostic_show,
    diagnostic_show_verification,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import (
    DiagnosticMarkerRef,
    FixVerification,
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
    *,
    sync_transcript_root: bool = False,
) -> None:
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    root = get_root(evidence, "monitor-run-ref", operation_id)
    transcript_root = (
        get_root(evidence, "monitor-run", operation_id)
        if sync_transcript_root
        else None
    )
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
    if transcript_root is not None:
        transcript_metadata = dict(transcript_root.metadata)
        transcript_metadata["run_ref_sha256"] = payload["run_ref_sha256"]
        _evidence_root_path(workspace, "monitor-run", operation_id).unlink()
        put_root(
            evidence,
            RootRecord(
                root_type="monitor-run",
                root_id=operation_id,
                manifest_id=transcript_root.manifest_id,
                metadata=transcript_metadata,
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
    monitor_references: dict[str, object] = {}

    def publish_transcript(run: object, role: str) -> EvidenceEnvelope:
        if (
            analysis_mutation in {"unchanged", "invalid"}
            and monitor_session_overrides is None
            and analysis_session_id is None
        ):
            reference = ingest_monitor_replay(
                workspace,
                evidence,
                MONITOR_OPERATION_IDS[role],
                transcript_paths[role],
            )
            monitor_references[role] = reference
            transcript_root = get_root(
                evidence, "monitor-run", MONITOR_OPERATION_IDS[role]
            )
            return evidence.get_envelope(transcript_root.manifest_id)
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
        "before_run_id": (
            str(getattr(monitor_references["failed-before"], "run_ref_sha256"))
            if "failed-before" in monitor_references
            else str(before.envelope.evidence_id)
        ),
        "after_run_id": (
            str(getattr(monitor_references["fixed-after"], "run_ref_sha256"))
            if "fixed-after" in monitor_references
            else str(after.envelope.evidence_id)
        ),
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
    elif analysis_mutation == "unchanged":
        analysis.update(
            after_first=1,
            after_last=1,
            after_min=1,
            after_max=1,
            delta_first=0,
            delta_last=0,
            changed=False,
            reason_code="VALUES_UNCHANGED",
        )
    elif analysis_mutation == "invalid":
        analysis.update(
            quality="INVALID",
            conclusion="INCONCLUSIVE",
            reason_code="INSUFFICIENT_VALID_PAIRS",
            aligned_position_count=1,
            aligned_pair_count=0,
            excluded_position_count=1,
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


def _prepared_cross_state_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    DiagnosticWorkflowContext,
    str,
    WorkspacePaths,
    SourceChangeDeclaration,
    VerificationPlan,
    DiagnosticMarkerRef,
    object,
    object,
    object,
    object,
]:
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
    declared = diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
        actor="user",
    )
    assert declared.ok is True
    planned = diagnostic_add_verification_plan(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification-plan.add",
        diagnostic_session_id=session_id,
        expected_revision=4,
        verification_plan=plan,
        actor="user",
    )
    assert planned.ok is True
    started = diagnostic_start_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.start",
        diagnostic_session_id=session_id,
        expected_revision=5,
        verification_plan_id=plan.verification_plan_id,
        actor="tool",
    )
    assert started.ok is True
    attached = diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
        actor="tool",
    )
    assert attached.ok is True
    return (
        diagnostic_context,
        session_id,
        workspace,
        declaration,
        plan,
        marker_ref,
        declared,
        planned,
        started,
        attached,
    )


def _prepare_durable_bound_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> tuple[DiagnosticWorkflowContext, str, WorkspacePaths, dict[str, object]]:
    if operation in {"show", "begin", "hypothesis"}:
        diagnostic_context, session_id, _replay, workspace = _replay_and_open_session(
            monkeypatch, tmp_path
        )
        if operation == "show":
            request = {"diagnostic_session_id": session_id}
        elif operation == "begin":
            request = {
                "operation_id": "durable-begin",
                "diagnostic_session_id": session_id,
                "expected_revision": 3,
            }
        else:
            request = {
                "operation_id": "durable-hypothesis",
                "diagnostic_session_id": session_id,
                "expected_revision": 3,
                "statement": "the durable target authority remains required",
            }
        return diagnostic_context, session_id, workspace, request

    if operation in {"declaration", "plan"}:
        (
            diagnostic_context,
            session_id,
            workspace,
            declaration,
            plan,
            _marker_ref,
        ) = _prepared_checkpoint_for_plan(monkeypatch, tmp_path)
        if operation == "declaration":
            request = {
                "operation_id": "durable-declaration",
                "diagnostic_session_id": session_id,
                "expected_revision": 4,
                "source_change_declaration": declaration,
            }
        else:
            request = {
                "operation_id": "durable-plan",
                "diagnostic_session_id": session_id,
                "expected_revision": 4,
                "verification_plan": plan,
            }
        return diagnostic_context, session_id, workspace, request

    if operation in {"verification-start", "marker"}:
        (
            diagnostic_context,
            session_id,
            workspace,
            _declaration,
            plan,
            marker_ref,
        ) = _prepared_checkpoint_for_attach(monkeypatch, tmp_path)
        if operation == "verification-start":
            request = {
                "operation_id": "durable-verification-start",
                "diagnostic_session_id": session_id,
                "expected_revision": 5,
                "verification_plan_id": plan.verification_plan_id,
            }
        else:
            request = {
                "operation_id": "durable-marker",
                "diagnostic_session_id": session_id,
                "expected_revision": 6,
                "diagnostic_marker_ref": marker_ref,
            }
        return diagnostic_context, session_id, workspace, request

    raise AssertionError(f"unknown durable bound operation: {operation}")


def test_task7a_mutations_retry_after_later_state_with_exact_or_conflicting_intent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        declaration,
        plan,
        marker_ref,
        declared,
        planned,
        started,
        attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)

    changed_declaration = SourceChangeDeclaration.new(
        before_source_sha256=declaration.before_source_sha256,
        after_source_sha256=declaration.after_source_sha256,
        before_build_id=declaration.before_build_id,
        before_elf_sha256=declaration.before_elf_sha256,
        after_build_id=declaration.after_build_id,
        after_elf_sha256=declaration.after_elf_sha256,
        changed_paths=tuple(
            sorted((*declaration.changed_paths, "src/durable-retry-change.c"))
        ),
        diff_evidence_id=declaration.diff_evidence_id,
        diff_artifact=declaration.diff_artifact,
        claimed_hypothesis_ids=declaration.claimed_hypothesis_ids,
        validation_plan_id=declaration.validation_plan_id,
    )
    changed_plan = VerificationPlan.new(
        verification_plan_id="e" * 64,
        diagnostic_session_id=plan.diagnostic_session_id,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        required_analysis_ids=plan.required_analysis_ids,
        required_analysis_evidence_ids=plan.required_analysis_evidence_ids,
        required_monitor_quality=plan.required_monitor_quality,
        expected_changed=plan.expected_changed,
    )
    changed_marker = DiagnosticMarkerRef.new(
        marker_id="d" * 64,
        marker_evidence_id=marker_ref.marker_evidence_id,
        analysis_id=marker_ref.analysis_id,
        analysis_evidence_id=marker_ref.analysis_evidence_id,
        diagnostic_session_id=marker_ref.diagnostic_session_id,
        hypothesis_id=marker_ref.hypothesis_id,
        polarity=marker_ref.polarity,
        label=marker_ref.label,
        rationale=marker_ref.rationale + " changed",
    )
    cases = {
        "declaration": {
            "operation_id": "diagnostic.source-change.declare",
            "expected_revision": 3,
            "actor": "user",
            "request": declaration,
            "changed_request": changed_declaration,
            "original": declared,
            "output_key": "source_change_declaration",
        },
        "plan": {
            "operation_id": "diagnostic.verification-plan.add",
            "expected_revision": 4,
            "actor": "user",
            "request": plan,
            "changed_request": changed_plan,
            "original": planned,
            "output_key": "verification_plan",
        },
        "verification-start": {
            "operation_id": "diagnostic.verification.start",
            "expected_revision": 5,
            "actor": "tool",
            "request": plan.verification_plan_id,
            "changed_request": "e" * 64,
            "original": started,
            "output_key": "verification_plan_id",
        },
        "marker": {
            "operation_id": "diagnostic.marker.attach",
            "expected_revision": 6,
            "actor": "tool",
            "request": marker_ref,
            "changed_request": changed_marker,
            "original": attached,
            "output_key": "diagnostic_marker_ref",
        },
    }

    def invoke(
        name: str,
        *,
        operation_id: str,
        expected_revision: int,
        actor: str,
        request: object,
    ) -> object:
        context = _fresh_diagnostic_context(diagnostic_context)
        if name == "declaration":
            return diagnostic_declare_source_change(
                context,
                operation_id=operation_id,
                diagnostic_session_id=session_id,
                expected_revision=expected_revision,
                source_change_declaration=request,
                actor=actor,
            )
        if name == "plan":
            return diagnostic_add_verification_plan(
                context,
                operation_id=operation_id,
                diagnostic_session_id=session_id,
                expected_revision=expected_revision,
                verification_plan=request,
                actor=actor,
            )
        if name == "verification-start":
            return diagnostic_start_verification(
                context,
                operation_id=operation_id,
                diagnostic_session_id=session_id,
                expected_revision=expected_revision,
                verification_plan_id=request,
                actor=actor,
            )
        if name == "marker":
            return diagnostic_attach_marker(
                context,
                operation_id=operation_id,
                diagnostic_session_id=session_id,
                expected_revision=expected_revision,
                diagnostic_marker_ref=request,
                actor=actor,
            )
        raise AssertionError(f"unknown operation: {name}")

    final_session = attached.data["session"]
    for name, case in cases.items():
        before = _authority_snapshot(workspace)
        retry = invoke(
            name,
            operation_id=case["operation_id"],
            expected_revision=case["expected_revision"],
            actor=case["actor"],
            request=case["request"],
        )
        after = _authority_snapshot(workspace)
        assert retry.ok is True
        assert retry.data["session"] == final_session
        assert retry.data[case["output_key"]] == case["original"].data[case["output_key"]]
        assert after == before

    for name, case in cases.items():
        before = _authority_snapshot(workspace)
        conflict = invoke(
            name,
            operation_id=case["operation_id"],
            expected_revision=case["expected_revision"],
            actor="ai-client",
            request=case["request"],
        )
        after = _authority_snapshot(workspace)
        assert conflict.ok is False
        assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
        assert after == before

    for name, case in cases.items():
        before = _authority_snapshot(workspace)
        conflict = invoke(
            name,
            operation_id=case["operation_id"],
            expected_revision=case["expected_revision"],
            actor=case["actor"],
            request=case["changed_request"],
        )
        after = _authority_snapshot(workspace)
        assert conflict.ok is False
        assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
        assert after == before

    for name, case in cases.items():
        before = _authority_snapshot(workspace)
        conflict = invoke(
            name,
            operation_id=f"fresh.stale.{name}",
            expected_revision=case["expected_revision"],
            actor=case["actor"],
            request=case["request"],
        )
        after = _authority_snapshot(workspace)
        assert conflict.ok is False
        assert conflict.code == "DIAGNOSTIC_REVISION_CONFLICT"
        assert after == before


def test_task7b_completion_pass_show_and_evidence_independent_exact_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        _marker_ref,
        _declared,
        _planned,
        _started,
        attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)
    assert attached.data["session"]["revision"] == 7

    completed = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.complete",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    assert completed.ok is True
    assert completed.operation == "diagnostic.verification.complete"
    verification = completed.data["fix_verification"]
    assert verification["status"] == "PASSED"
    assert verification["reason_code"] == "VERIFICATION_PASSED"
    fixed = TestRunRepository(EvidenceStore(workspace.workspace_root / "evidence")).load(
        "vs03-fixed-after"
    )
    assert verification["completed_at_utc"] == fixed.manifest.ended_at_utc
    assert completed.data["session"]["state"] == "RESOLVED"

    shown = diagnostic_show_verification(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    assert shown.operation == "diagnostic.verification.show"
    assert shown.data["authoritative"] is True
    assert shown.data["session"] == completed.data["session"]
    assert shown.data["fix_verifications"] == (verification,)

    before = _authority_snapshot(workspace)
    with monkeypatch.context() as isolated:
        isolated.setattr(
            diagnostic_workflows,
            "_load_bound_session",
            lambda *_args, **_kwargs: pytest.fail("exact completion retry dereferenced Evidence"),
        )
        retry = diagnostic_complete_verification(
            _fresh_diagnostic_context(diagnostic_context),
            operation_id="diagnostic.verification.complete",
            diagnostic_session_id=session_id,
            expected_revision=7,
            executed_operation_ids=["target-test.vs03"],
        )
    assert retry.ok is True
    assert retry.data["session"] == completed.data["session"]
    assert retry.data["fix_verification"] == verification
    assert _authority_snapshot(workspace) == before

    for kwargs in (
        {"actor": "ai-client"},
        {"executed_operation_ids": ["target-test.other"]},
        {"cancelled": True},
    ):
        before = _authority_snapshot(workspace)
        conflict = diagnostic_complete_verification(
            _fresh_diagnostic_context(diagnostic_context),
            operation_id="diagnostic.verification.complete",
            diagnostic_session_id=session_id,
            expected_revision=7,
            executed_operation_ids=kwargs.pop("executed_operation_ids", ["target-test.vs03"]),
            cancelled=kwargs.pop("cancelled", False),
            actor=kwargs.pop("actor", "tool"),
        )
        assert conflict.ok is False
        assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
        assert _authority_snapshot(workspace) == before

    before = _authority_snapshot(workspace)
    stale = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.verification.complete.new",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert _authority_snapshot(workspace) == before


def test_task7b_completion_deterministic_outcome_priority_and_zero_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("corrupt", "failed-fixed", "cancelled"):
        (tmp_path / name).mkdir()
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        _marker_ref,
    ) = _prepared_checkpoint_for_attach(monkeypatch, tmp_path)
    missing_marker = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.missing-marker",
        diagnostic_session_id=session_id,
        expected_revision=6,
        executed_operation_ids=["target-test.vs03"],
    )
    assert missing_marker.ok is True
    assert missing_marker.data["fix_verification"]["status"] == "INCONCLUSIVE"
    assert missing_marker.data["fix_verification"]["reason_code"] == "MANDATORY_EVIDENCE_MISSING"
    assert missing_marker.data["session"]["state"] == "INVESTIGATING"

    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path / "corrupt")
    analysis_root = _evidence_root_path(workspace, "monitor-analysis", marker_ref.analysis_id)
    analysis_root.write_bytes(b"{}")
    before = _authority_snapshot(workspace)
    corrupt_analysis = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.corrupt-analysis",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    after = _authority_snapshot(workspace)
    assert corrupt_analysis.ok is False
    assert corrupt_analysis.code == "DIAGNOSTIC_CHAIN_CORRUPT"
    assert corrupt_analysis.data is None
    assert after == before

    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        _marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path / "failed-fixed")
    real_repository_factory = diagnostic_workflows._repository_factory

    class FailedFixedRepository:
        def __init__(self, evidence_store: EvidenceStore) -> None:
            self._repository = real_repository_factory(evidence_store)

        def load(self, run_id: str) -> object:
            published = self._repository.load(run_id)
            if run_id != "vs03-fixed-after":
                return published
            manifest = replace(
                published.manifest,
                state="failed",
                cases=(replace(published.manifest.cases[0], state="failed"),),
            )
            root = replace(
                published.root,
                metadata={**dict(published.root.metadata), "state": "failed"},
            )
            return replace(published, manifest=manifest, root=root)

    with monkeypatch.context() as isolated:
        isolated.setattr(
            diagnostic_workflows,
            "_repository_factory",
            lambda evidence_store: FailedFixedRepository(evidence_store),
        )
        failed_fixed = diagnostic_complete_verification(
            _fresh_diagnostic_context(diagnostic_context),
            operation_id="complete.failed-fixed",
            diagnostic_session_id=session_id,
            expected_revision=7,
            executed_operation_ids=["target-test.vs03"],
        )
    assert failed_fixed.ok is True
    assert failed_fixed.data["fix_verification"]["status"] == "FAILED"
    assert failed_fixed.data["fix_verification"]["reason_code"] == "FIXED_TEST_FAILED"
    assert failed_fixed.data["session"]["state"] == "INVESTIGATING"

    (
        diagnostic_context,
        session_id,
        _workspace,
        _declaration,
        _plan,
        _marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path / "cancelled")
    cancelled = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.cancelled",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
        cancelled=True,
    )
    assert cancelled.ok is True
    assert cancelled.data["fix_verification"]["status"] == "CANCELLED"
    assert cancelled.data["fix_verification"]["reason_code"] == "CALLER_CANCELLED"
    assert cancelled.data["session"]["state"] == "INVESTIGATING"


def test_task7b_plan_accepts_trustworthy_failed_fixed_after_for_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (
        diagnostic_context,
        session_id,
        _failed_replay,
        workspace,
    ) = _replay_and_open_session(monkeypatch, tmp_path)
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
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, _marker_ref = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    ).ok is True

    real_repository_factory = diagnostic_workflows._repository_factory

    class FailedFixedRepository:
        def __init__(self, evidence_store: EvidenceStore) -> None:
            self._repository = real_repository_factory(evidence_store)

        def load(self, run_id: str) -> object:
            published = self._repository.load(run_id)
            if run_id != "vs03-fixed-after":
                return published
            return replace(
                published,
                manifest=replace(
                    published.manifest,
                    state="failed",
                    cases=(replace(published.manifest.cases[0], state="failed"),),
                ),
                root=replace(
                    published.root,
                    metadata={**dict(published.root.metadata), "state": "failed"},
                ),
            )

    with monkeypatch.context() as isolated:
        isolated.setattr(
            diagnostic_workflows,
            "_repository_factory",
            lambda evidence_store: FailedFixedRepository(evidence_store),
        )
        planned = diagnostic_add_verification_plan(
            _fresh_diagnostic_context(diagnostic_context),
            operation_id="diagnostic.verification-plan.add.failed-fixed",
            diagnostic_session_id=session_id,
            expected_revision=4,
            verification_plan=plan,
        )
    assert planned.ok is True
    assert planned.data["verification_plan"]["fixed_after_run_id"] == "vs03-fixed-after"


def test_task7b_completion_valid_analysis_contradiction_has_deterministic_failure(
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
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, marker_ref = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id, analysis_mutation="unchanged"
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    ).ok is True
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
    assert diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
    ).ok is True
    completed = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.contradicted-analysis",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    assert completed.ok is True
    assert completed.data["fix_verification"]["status"] == "FAILED"
    assert completed.data["fix_verification"]["reason_code"] == "ANALYSIS_CONTRADICTED"
    assert completed.data["session"]["state"] == "INVESTIGATING"


def test_task7b_completion_invalid_analysis_has_deterministic_inconclusive_result(
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
    hypothesis_id = shown.data["session"]["hypotheses"][0]["hypothesis_id"]
    declaration, plan, marker_ref = _verification_checkpoint_inputs(
        tmp_path, workspace, session_id, hypothesis_id, analysis_mutation="invalid"
    )
    assert diagnostic_declare_source_change(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.source-change.declare",
        diagnostic_session_id=session_id,
        expected_revision=3,
        source_change_declaration=declaration,
    ).ok is True
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
    assert diagnostic_attach_marker(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.marker.attach",
        diagnostic_session_id=session_id,
        expected_revision=6,
        diagnostic_marker_ref=marker_ref,
    ).ok is True
    completed = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.invalid-analysis",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    assert completed.ok is True
    assert completed.data["fix_verification"]["status"] == "INCONCLUSIVE"
    assert completed.data["fix_verification"]["reason_code"] == "ANALYSIS_NOT_VALID"
    assert completed.data["session"]["state"] == "INVESTIGATING"


def _install_completion_identity_view(
    monkeypatch: pytest.MonkeyPatch,
    workspace: WorkspacePaths,
    marker_ref: DiagnosticMarkerRef,
    kind: str,
) -> None:
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    original_get_envelope = EvidenceStore.get_envelope
    if kind == "analysis":
        evidence_id = marker_ref.analysis_evidence_id
    else:
        assert kind == "marker"
        evidence_id = marker_ref.marker_evidence_id
    envelope = evidence.get_envelope(evidence_id)
    foreign_envelope = copy.copy(envelope)
    object.__setattr__(
        foreign_envelope,
        "identity",
        replace(envelope.identity, workspace_id="f" * 64),
    )
    envelope_views = {evidence_id: foreign_envelope}

    def view_get_envelope(store: EvidenceStore, requested_id: str) -> EvidenceEnvelope:
        if requested_id in envelope_views:
            return envelope_views[requested_id]
        return original_get_envelope(store, requested_id)

    monkeypatch.setattr(EvidenceStore, "get_envelope", view_get_envelope)


def test_task7b_completion_rejects_rebound_fixed_after_evidence_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        _marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)
    real_repository_factory = diagnostic_workflows._repository_factory

    class ReboundFixedAfterRepository:
        def __init__(self, evidence_store: EvidenceStore) -> None:
            self._repository = real_repository_factory(evidence_store)

        def load(self, run_id: str) -> object:
            published = self._repository.load(run_id)
            if run_id != "vs03-fixed-after":
                return published
            metadata = dict(published.envelope.metadata)
            metadata["operation_intent_sha256"] = "0" * 64
            rebound_envelope = EvidenceEnvelope(
                identity=published.envelope.identity,
                operation=published.envelope.operation,
                produced_at_utc=published.envelope.produced_at_utc,
                parents=published.envelope.parents,
                artifacts=published.envelope.artifacts,
                metadata=metadata,
            )
            rebound_root = replace(
                published.root,
                manifest_id=str(rebound_envelope.evidence_id),
            )
            return replace(
                published,
                envelope=rebound_envelope,
                root=rebound_root,
            )

    monkeypatch.setattr(
        diagnostic_workflows,
        "_repository_factory",
        lambda evidence_store: ReboundFixedAfterRepository(evidence_store),
    )
    before = _authority_snapshot(workspace)
    result = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="complete.rebound-fixed-after",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


@pytest.mark.parametrize("kind", ("analysis", "marker"))
def test_task7b_completion_rejects_analysis_or_marker_identity_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)
    _install_completion_identity_view(monkeypatch, workspace, marker_ref, kind)
    before = _authority_snapshot(workspace)
    result = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"complete.identity.{kind}",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


@pytest.mark.parametrize("kind", ("analysis", "marker"))
def test_task7b_completion_artifact_provider_oserror_is_environment_failure_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)
    root_type = "monitor-analysis" if kind == "analysis" else "diagnostic-marker"
    root_id = marker_ref.analysis_id if kind == "analysis" else marker_ref.marker_id
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    root = get_root(evidence, root_type, root_id)
    artifact = evidence.get_envelope(root.manifest_id).artifacts[0]

    completion_reader_entered = False
    provider_calls: list[object] = []
    original_completion_reader = diagnostic_workflows._read_completion_json_evidence
    original_read_artifact = EvidenceStore.read_artifact

    def completion_reader(*args: object, **kwargs: object) -> object:
        nonlocal completion_reader_entered
        completion_reader_entered = True
        return original_completion_reader(*args, **kwargs)

    def provider_failure(
        store: EvidenceStore, requested_artifact: object, *, maximum_bytes: int
    ) -> bytes:
        if completion_reader_entered and requested_artifact == artifact:
            provider_calls.append(requested_artifact)
            raise OSError("completion evidence provider is unavailable")
        return original_read_artifact(
            store, requested_artifact, maximum_bytes=maximum_bytes
        )

    monkeypatch.setattr(
        diagnostic_workflows, "_read_completion_json_evidence", completion_reader
    )
    monkeypatch.setattr(EvidenceStore, "read_artifact", provider_failure)

    before = _authority_snapshot(workspace)
    result = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"complete.provider.{kind}",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    after = _authority_snapshot(workspace)

    assert completion_reader_entered is True
    assert provider_calls == [artifact]
    assert result.ok is False
    assert result.code == "ENVIRONMENT_FAILURE"
    assert result.data is None
    assert after == before


@pytest.mark.parametrize("kind", ("analysis-missing", "marker-corrupt"))
def test_task7b_completion_artifact_failure_kind_is_classified_without_evidence_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    (
        diagnostic_context,
        session_id,
        workspace,
        _declaration,
        _plan,
        marker_ref,
        _declared,
        _planned,
        _started,
        _attached,
    ) = _prepared_cross_state_operations(monkeypatch, tmp_path)
    if kind == "analysis-missing":
        root_type = "monitor-analysis"
        root_id = marker_ref.analysis_id
        expected_reason = "MANDATORY_EVIDENCE_MISSING"
    else:
        assert kind == "marker-corrupt"
        root_type = "diagnostic-marker"
        root_id = marker_ref.marker_id
        expected_reason = "MANDATORY_EVIDENCE_CORRUPT"
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    root = get_root(evidence, root_type, root_id)
    artifact = evidence.get_envelope(root.manifest_id).artifacts[0]

    completion_reader_entered = False
    completion_reader_active = False
    provider_calls: list[object] = []
    original_completion_reader = diagnostic_workflows._read_completion_json_evidence
    original_read_artifact = EvidenceStore.read_artifact

    def completion_reader(*args: object, **kwargs: object) -> object:
        nonlocal completion_reader_active, completion_reader_entered
        completion_reader_entered = True
        completion_reader_active = True
        try:
            return original_completion_reader(*args, **kwargs)
        finally:
            completion_reader_active = False

    def selected_artifact_failure(
        store: EvidenceStore, requested_artifact: object, *, maximum_bytes: int
    ) -> bytes:
        if completion_reader_active and requested_artifact == artifact:
            provider_calls.append(requested_artifact)
            if kind == "analysis-missing":
                raise FileNotFoundError("completion analysis evidence is missing")
            return b"not-json"
        return original_read_artifact(
            store, requested_artifact, maximum_bytes=maximum_bytes
        )

    monkeypatch.setattr(
        diagnostic_workflows, "_read_completion_json_evidence", completion_reader
    )
    monkeypatch.setattr(EvidenceStore, "read_artifact", selected_artifact_failure)

    before_evidence = dict(_tree_snapshot(workspace.workspace_root / "evidence"))
    before_evidence_roots = {
        path: payload for path, payload in before_evidence.items() if path.startswith("roots/")
    }
    before_diagnostics = dict(_tree_snapshot(workspace.diagnostics_root))
    result = diagnostic_complete_verification(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"complete.{kind}",
        diagnostic_session_id=session_id,
        expected_revision=7,
        executed_operation_ids=["target-test.vs03"],
    )
    after_evidence = dict(_tree_snapshot(workspace.workspace_root / "evidence"))
    after_evidence_roots = {
        path: payload for path, payload in after_evidence.items() if path.startswith("roots/")
    }
    after_diagnostics = dict(_tree_snapshot(workspace.diagnostics_root))

    assert completion_reader_entered is True
    assert provider_calls == [artifact]
    assert result.ok is True
    assert result.operation == "diagnostic.verification.complete"
    assert result.code == "OK"
    assert result.message == ""
    assert result.details == {}
    assert result.data is not None
    assert result.data["fix_verification"]["status"] == "INCONCLUSIVE"
    assert result.data["fix_verification"]["reason_code"] == expected_reason
    assert result.data["session"]["revision"] == 8
    assert result.data["session"]["state"] == "INVESTIGATING"

    assert set(before_evidence) <= set(after_evidence)
    assert {path: after_evidence[path] for path in before_evidence} == before_evidence
    assert set(before_diagnostics) <= set(after_diagnostics)
    assert {
        path: after_diagnostics[path] for path in before_diagnostics
    } == before_diagnostics
    new_evidence_root_paths = set(after_evidence_roots) - set(before_evidence_roots)
    assert len(new_evidence_root_paths) == 1
    new_evidence_root_path = next(iter(new_evidence_root_paths))
    checkpoint_root = get_root(evidence, "diagnostic-session", f"{session_id}.00000008")
    checkpoint_root_path = workspace.workspace_root / "evidence" / new_evidence_root_path
    checkpoint_root_bytes = checkpoint_root_path.read_bytes()
    checkpoint_root_payload = json.loads(checkpoint_root_bytes.decode("utf-8"))
    assert canonical_json_bytes(checkpoint_root_payload) == checkpoint_root_bytes
    assert RootRecord.from_value(checkpoint_root_payload).to_dict() == checkpoint_root.to_dict()
    checkpoint_envelope = evidence.get_envelope(checkpoint_root.manifest_id)
    checkpoint_paths = {
        new_evidence_root_path,
        f"manifests/{checkpoint_root.manifest_id}.json",
        checkpoint_envelope.artifacts[0].relative_path,
    }
    pending_parents = list(checkpoint_envelope.parents)
    while pending_parents:
        parent_manifest_id = pending_parents.pop()
        parent_manifest_path = f"manifests/{parent_manifest_id}.json"
        if parent_manifest_path in before_evidence or parent_manifest_path in checkpoint_paths:
            continue
        parent_envelope = evidence.get_envelope(parent_manifest_id)
        checkpoint_paths.add(parent_manifest_path)
        checkpoint_paths.update(
            artifact.relative_path
            for artifact in parent_envelope.artifacts
            if artifact.relative_path not in before_evidence
        )
        pending_parents.extend(
            parent_id
            for parent_id in parent_envelope.parents
            if f"manifests/{parent_id}.json" not in before_evidence
        )
    for checkpoint_path in tuple(checkpoint_paths):
        parent = Path(checkpoint_path).parent
        while parent != Path("."):
            parent_path = parent.as_posix()
            if parent_path not in before_evidence:
                checkpoint_paths.add(parent_path)
            parent = parent.parent
    assert set(after_evidence) - set(before_evidence) == checkpoint_paths
    assert set(after_diagnostics) - set(before_diagnostics) == {
        f"sessions/{session_id}/events/00000007.json",
    }
    event_path = workspace.diagnostics_root / "sessions" / session_id / "events" / "00000007.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["event_type"] == "verification.completed"
    assert event["sequence"] == 7
    assert event["revision_before"] == 7
    assert event["payload"]["result"]["status"] == "INCONCLUSIVE"
    assert event["payload"]["result"]["reason_code"] == expected_reason


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


@pytest.mark.parametrize("operation", ("show", "begin", "hypothesis", "declaration", "plan", "verification-start", "marker"))
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("missing", "EVIDENCE_INTEGRITY_FAILURE"),
        ("corrupt", "EVIDENCE_INTEGRITY_FAILURE"),
        ("provider", "ENVIRONMENT_FAILURE"),
        ("identity", "INCOMPATIBLE_IDENTITY"),
    ),
)
def test_target_bound_operations_project_durable_mode_failures_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
    failure: str,
    expected_code: str,
) -> None:
    diagnostic_context, session_id, workspace, request = _prepare_durable_bound_operation(
        monkeypatch, tmp_path, operation
    )
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    failed_evidence_id = shown.data["session"]["failed_evidence_id"]
    manifest_path = workspace.workspace_root / "evidence" / "manifests" / f"{failed_evidence_id}.json"

    if failure == "missing":
        manifest_path.unlink()
    elif failure == "corrupt":
        manifest_path.write_bytes(b"{}")
    elif failure == "provider":
        original_get_envelope = EvidenceStore.get_envelope

        def provider_failure(self: EvidenceStore, evidence_id: str) -> object:
            if evidence_id == failed_evidence_id:
                raise OSError("durable Evidence provider unavailable")
            return original_get_envelope(self, evidence_id)

        monkeypatch.setattr(EvidenceStore, "get_envelope", provider_failure)
    elif failure == "identity":
        original_get_envelope = EvidenceStore.get_envelope
        evidence = EvidenceStore(workspace.workspace_root / "evidence")
        original_envelope = original_get_envelope(evidence, failed_evidence_id)
        foreign_envelope = EvidenceEnvelope(
            identity=replace(
                original_envelope.identity,
                project_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
            ),
            operation=original_envelope.operation,
            produced_at_utc=original_envelope.produced_at_utc,
            parents=original_envelope.parents,
            artifacts=original_envelope.artifacts,
            metadata=original_envelope.metadata,
        )
        evidence.put_envelope(foreign_envelope)
        foreign_evidence_id = str(foreign_envelope.evidence_id)

        def foreign_identity(self: EvidenceStore, evidence_id: str) -> object:
            if evidence_id != failed_evidence_id:
                return original_get_envelope(self, evidence_id)
            return original_get_envelope(self, foreign_evidence_id)

        monkeypatch.setattr(EvidenceStore, "get_envelope", foreign_identity)
    else:
        raise AssertionError(f"unknown failure: {failure}")

    before = _authority_snapshot(workspace)
    callers = {
        "show": diagnostic_show,
        "begin": diagnostic_begin,
        "hypothesis": diagnostic_add_hypothesis,
        "declaration": diagnostic_declare_source_change,
        "plan": diagnostic_add_verification_plan,
        "verification-start": diagnostic_start_verification,
        "marker": diagnostic_attach_marker,
    }
    result = callers[operation](
        _fresh_diagnostic_context(diagnostic_context),
        **request,
    )
    after = _authority_snapshot(workspace)
    assert result.ok is False
    assert result.code == expected_code
    assert after == before


def _assert_public_failure(
    result: object,
    operation: str,
    code: str,
    *,
    case_name: str | None = None,
) -> dict[str, object]:
    messages = {
        "DIAGNOSTIC_INVALID_EVENT": "event/model/operation intent is invalid",
        "DIAGNOSTIC_INVALID_TRANSITION": "event is illegal in current state",
        "DIAGNOSTIC_PLAN_INVALID": "selector, expected value, plan, or step reference is invalid",
        "INCOMPATIBLE_IDENTITY": "Target replay identity is incompatible.",
        "EVIDENCE_INTEGRITY_FAILURE": "Target replay evidence failed integrity validation.",
    }
    wire = result.to_dict()  # type: ignore[union-attr]
    assert wire == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": messages[code],
        "data": None,
        "details": {},
    }, case_name or operation
    return wire


def _assert_public_success(result: object, operation: str) -> dict[str, object]:
    wire = result.to_dict()  # type: ignore[union-attr]
    assert wire["protocol"] == "stm32-toolkit/1"
    assert wire["ok"] is True
    assert wire["operation"] == operation
    assert wire["code"] == "OK"
    assert wire["message"] == ""
    assert wire["details"] == {}
    assert wire["data"] is not None
    return wire


def _copy_public_diagnostic_prefix(
    source_root: Path,
    target_root: Path,
    *,
    project_root: Path,
    session_id: str,
    excluded_root: tuple[str, str] | None = None,
) -> Path:
    shutil.copytree(source_root, target_root)
    if excluded_root is not None:
        root_type, root_id = excluded_root
        evidence = EvidenceStore(
            WorkspacePaths.from_roots(
                target_root,
                project_root,
                PROJECT_ID,
                session_id,
            ).workspace_root
            / "evidence"
        )
        key_digest = hashlib.sha256(
            canonical_json_bytes({"root_type": root_type, "root_id": root_id})
        ).hexdigest()
        root_path = evidence.root / "roots" / root_type / f"{key_digest}.json"
        assert root_path.exists()
        root_path.unlink()
    return target_root


def _public_diagnostic_root_file(
    evidence: EvidenceStore, root_type: str, root_id: str
) -> Path:
    key_digest = hashlib.sha256(
        canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    ).hexdigest()
    return evidence.root / "roots" / root_type / f"{key_digest}.json"


def _publish_public_analysis_variant(
    evidence: EvidenceStore,
    *,
    root_id: str,
    envelope: EvidenceEnvelope,
    metadata: dict[str, object],
) -> None:
    evidence.put_envelope(envelope)
    root_path = _public_diagnostic_root_file(evidence, "monitor-analysis", root_id)
    assert not root_path.exists()
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-analysis",
            root_id=root_id,
            manifest_id=str(envelope.evidence_id),
            metadata=metadata,
        ),
    )


def _prepare_public_diagnostic_authorities(
    tmp_path: Path,
    project_root: Path,
    data_root: Path,
    runtime_session_id: str,
    diagnostic_storage_id: str,
    hypothesis_id: str,
    declaration: SourceChangeDeclaration,
    fixed_descriptor: Path,
    fixed_stream: Path,
) -> tuple[WorkspacePaths, VerificationPlan, object, object]:
    workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        PROJECT_ID,
        runtime_session_id,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    testing = testing_workflows.TestingWorkflowContext(
        project_root,
        data_root,
        runtime_session_id,
    )
    assert testing_workflows.target_replay_run(
        testing,
        vs08b.FIXED_RUN_ID,
        fixed_descriptor,
        fixed_stream,
    ).ok
    before_run = TestRunRepository(evidence).load(vs08b.FAILED_RUN_ID)
    after_run = TestRunRepository(evidence).load(vs08b.FIXED_RUN_ID)

    monitor_paths: dict[str, Path] = {}
    for role in ("failed-before", "fixed-after"):
        source = vs08b.MONITOR_FIXTURES / f"{role}.json"
        descriptor = json.loads(source.read_text(encoding="utf-8"))
        descriptor["binding"]["workspaceId"] = workspace.workspace_id
        for batch in descriptor["batches"]:
            batch["binding"]["workspaceId"] = workspace.workspace_id
        unsigned = {
            key: value for key, value in descriptor.items() if key != "fixture_sha256"
        }
        descriptor["fixture_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        target = tmp_path / f"public-diagnostic-monitor-{role}.json"
        target.write_text(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        monitor_paths[role] = target
    monitor_before = ingest_monitor_replay(
        workspace,
        evidence,
        vs08b.MONITOR_OPERATION_IDS["failed-before"],
        monitor_paths["failed-before"],
    )
    monitor_after = ingest_monitor_replay(
        workspace,
        evidence,
        vs08b.MONITOR_OPERATION_IDS["fixed-after"],
        monitor_paths["fixed-after"],
    )
    analysis_request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=monitor_before,
        after_run=monitor_after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    )
    publication = compare_monitor_runs(
        workspace,
        evidence,
        analysis_request,
        diagnostic_storage_id,
        hypothesis_id,
        "supports",
        "the fixed replay changed the observed counter",
        declaration,
    )
    export_analysis_bundle(
        workspace,
        evidence,
        analysis_request,
        publication,
        vs08b.FAILED_RUN_ID,
        vs08b.FIXED_RUN_ID,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_storage_id,
        failed_before_run_id=vs08b.FAILED_RUN_ID,
        failed_before_evidence_id=str(before_run.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=vs08b.FIXED_RUN_ID,
        fixed_after_evidence_id=str(after_run.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    return workspace, verification_plan, publication, after_run


def test_public_diagnostic_caller_journey_replay_to_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey_root = tmp_path / "diagnostic-public-journey"
    journey_root.mkdir()
    (
        project_root,
        data_root,
        diagnostic_id,
        hypothesis_id,
        _failed_descriptor,
        fixed_descriptor,
        fixed_stream,
    ) = vs08b._prepare_real_diagnostic_before_source(
        journey_root,
        "cubemx",
        monkeypatch,
        "dj1-session",
    )
    diagnostic_storage_id = diagnostic_id.replace("-", "")
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, "dj1-session")
    baseline_workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        PROJECT_ID,
        "dj1-session",
    )

    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic),
        diagnostic_session_id=diagnostic_storage_id,
    )
    shown_wire = _assert_public_success(shown, "diagnostic.show")
    shown_data = shown_wire["data"]
    assert isinstance(shown_data, dict)
    shown_session = shown_data["session"]
    assert isinstance(shown_session, dict)
    assert shown_data == {"session": shown_session, "authoritative": True}
    assert shown_session["revision"] == 6
    assert shown_session["state"] == "INVESTIGATING"
    observation_plan_id = shown_session["observation_plans"][0]["plan_id"]

    prefix6 = journey_root / "prefix6"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix6,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix6_original_bytes = dict(_tree_snapshot(data_root))
    invalid_hypothesis_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "invalid-hypothesis",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix6,
        invalid_hypothesis_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(invalid_hypothesis_context.data_root)
    invalid_hypothesis = diagnostic_assess_hypothesis(
        invalid_hypothesis_context,
        operation_id="dj1.invalid-hypothesis",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        hypothesis_id="not-a-hypothesis-id",
        plan_id=observation_plan_id,
        step_id="failed-run",
        polarity="supports",
        rationale="invalid hypothesis syntax is rejected before state access",
    )
    _assert_public_failure(
        invalid_hypothesis,
        "diagnostic.hypothesis.assess",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="invalid-hypothesis",
    )
    assert _tree_snapshot(invalid_hypothesis_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix6_original_bytes

    invalid_step_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "invalid-step",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix6,
        invalid_step_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(invalid_step_context.data_root)
    invalid_step = diagnostic_assess_hypothesis(
        invalid_step_context,
        operation_id="dj1.invalid-step",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        hypothesis_id=hypothesis_id,
        plan_id=observation_plan_id,
        step_id="invalid step id",
        polarity="supports",
        rationale="invalid step syntax is rejected before state access",
    )
    _assert_public_failure(
        invalid_step,
        "diagnostic.hypothesis.assess",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="invalid-step",
    )
    assert _tree_snapshot(invalid_step_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix6_original_bytes

    start_before_declaration_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "start-before-declaration",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix6,
        start_before_declaration_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(start_before_declaration_context.data_root)
    start_before_declaration = diagnostic_start_verification(
        start_before_declaration_context,
        operation_id="dj1.start-before-declaration",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        verification_plan_id="b" * 64,
    )
    _assert_public_failure(
        start_before_declaration,
        "diagnostic.verification.start",
        "DIAGNOSTIC_INVALID_TRANSITION",
        case_name="start-before-declaration",
    )
    assert _tree_snapshot(start_before_declaration_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix6_original_bytes

    evidence = EvidenceStore(baseline_workspace.workspace_root / "evidence")
    before_run = TestRunRepository(evidence).load(vs08b.FAILED_RUN_ID)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = vs08b._source_change(
        journey_root,
        evidence,
        before_run,
        fixed_fixture.descriptor.identity,
        hypothesis_id,
    )
    declaration_before_bytes = dict(_tree_snapshot(data_root))
    declared = diagnostic_declare_source_change(
        diagnostic,
        operation_id="dj1.source-change.declare",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        source_change_declaration=declaration,
    )
    declared_wire = _assert_public_success(
        declared,
        "diagnostic.source-change.declare",
    )
    declared_data = declared_wire["data"]
    assert isinstance(declared_data, dict)
    declared_session = declared_data["session"]
    assert isinstance(declared_session, dict)
    assert declared_data == {
        "session": declared_session,
        "source_change_declaration": declaration.to_dict(),
    }
    assert declared_session["revision"] == 7
    assert declared_session["state"] == "FIX_PROPOSED"
    assert declared_session["source_change_declarations"] == [declaration.to_dict()]
    assert declared_session["event_head"] != shown_session["event_head"]
    assert len(declared_session["event_head"]) == 64
    declaration_after_bytes = dict(_tree_snapshot(data_root))
    assert all(
        declaration_after_bytes.get(path) == payload
        for path, payload in declaration_before_bytes.items()
    )
    assert set(declaration_after_bytes) > set(declaration_before_bytes)

    workspace, verification_plan, publication, after_run = _prepare_public_diagnostic_authorities(
        journey_root,
        project_root,
        data_root,
        "dj1-session",
        diagnostic_storage_id,
        hypothesis_id,
        declaration,
        fixed_descriptor,
        fixed_stream,
    )
    assert workspace.workspace_id == baseline_workspace.workspace_id
    prefix7 = journey_root / "prefix7"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix7,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix7_original_bytes = dict(_tree_snapshot(data_root))

    extra_declaration = SourceChangeDeclaration.new(
        before_source_sha256=declaration.before_source_sha256,
        after_source_sha256=declaration.after_source_sha256,
        before_build_id=declaration.before_build_id,
        before_elf_sha256=declaration.before_elf_sha256,
        after_build_id=declaration.after_build_id,
        after_elf_sha256=declaration.after_elf_sha256,
        changed_paths=("App/main.c", "App/extra.c"),
        diff_evidence_id=declaration.diff_evidence_id,
        diff_artifact=declaration.diff_artifact,
        claimed_hypothesis_ids=declaration.claimed_hypothesis_ids,
        validation_plan_id=declaration.validation_plan_id,
    )
    extra_declaration_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "extra-declaration",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix7,
        extra_declaration_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(extra_declaration_context.data_root)
    extra_declaration_result = diagnostic_declare_source_change(
        extra_declaration_context,
        operation_id="dj1.extra-declaration",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        source_change_declaration=extra_declaration,
    )
    _assert_public_failure(
        extra_declaration_result,
        "diagnostic.source-change.declare",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="extra-declaration",
    )
    assert _tree_snapshot(extra_declaration_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix7_original_bytes

    different_session_plan = VerificationPlan.new(
        verification_plan_id=verification_plan.verification_plan_id,
        diagnostic_session_id="c" * 32,
        failed_before_run_id=verification_plan.failed_before_run_id,
        failed_before_evidence_id=verification_plan.failed_before_evidence_id,
        source_change_declaration_id=verification_plan.source_change_declaration_id,
        fixed_after_run_id=verification_plan.fixed_after_run_id,
        fixed_after_evidence_id=verification_plan.fixed_after_evidence_id,
        required_analysis_ids=verification_plan.required_analysis_ids,
        required_analysis_evidence_ids=verification_plan.required_analysis_evidence_ids,
        required_monitor_quality=verification_plan.required_monitor_quality,
        expected_changed=verification_plan.expected_changed,
    )
    different_session_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "different-session-plan",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix7,
        different_session_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(different_session_context.data_root)
    different_session_result = diagnostic_add_verification_plan(
        different_session_context,
        operation_id="dj1.different-session-plan",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=different_session_plan,
    )
    _assert_public_failure(
        different_session_result,
        "diagnostic.verification-plan.add",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="different-session-plan",
    )
    assert _tree_snapshot(different_session_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix7_original_bytes

    before_evidence_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "different-fixed-evidence",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix7,
        before_evidence_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    different_fixed_evidence_plan = VerificationPlan.new(
        verification_plan_id=verification_plan.verification_plan_id,
        diagnostic_session_id=verification_plan.diagnostic_session_id,
        failed_before_run_id=verification_plan.failed_before_run_id,
        failed_before_evidence_id=verification_plan.failed_before_evidence_id,
        source_change_declaration_id=verification_plan.source_change_declaration_id,
        fixed_after_run_id=verification_plan.fixed_after_run_id,
        fixed_after_evidence_id=verification_plan.failed_before_evidence_id,
        required_analysis_ids=verification_plan.required_analysis_ids,
        required_analysis_evidence_ids=verification_plan.required_analysis_evidence_ids,
        required_monitor_quality=verification_plan.required_monitor_quality,
        expected_changed=verification_plan.expected_changed,
    )
    before = _tree_snapshot(before_evidence_context.data_root)
    different_fixed_evidence_result = diagnostic_add_verification_plan(
        before_evidence_context,
        operation_id="dj1.different-fixed-evidence",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=different_fixed_evidence_plan,
    )
    _assert_public_failure(
        different_fixed_evidence_result,
        "diagnostic.verification-plan.add",
        "INCOMPATIBLE_IDENTITY",
        case_name="different-fixed-evidence",
    )
    assert _tree_snapshot(before_evidence_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix7_original_bytes

    absent_plan_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "absent-plan",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix7,
        absent_plan_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(absent_plan_context.data_root)
    absent_plan_result = diagnostic_start_verification(
        absent_plan_context,
        operation_id="dj1.absent-plan",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan_id="a" * 64,
    )
    _assert_public_failure(
        absent_plan_result,
        "diagnostic.verification.start",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="absent-plan",
    )
    assert _tree_snapshot(absent_plan_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix7_original_bytes

    plan_before_bytes = dict(_tree_snapshot(data_root))
    added = diagnostic_add_verification_plan(
        diagnostic,
        operation_id="dj1.verification-plan.add",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=verification_plan,
    )
    added_wire = _assert_public_success(
        added,
        "diagnostic.verification-plan.add",
    )
    added_data = added_wire["data"]
    assert isinstance(added_data, dict)
    added_session = added_data["session"]
    assert isinstance(added_session, dict)
    assert added_data == {
        "session": added_session,
        "verification_plan": verification_plan.to_dict(),
    }
    assert added_session["revision"] == 8
    assert added_session["state"] == "FIX_PROPOSED"
    assert added_session["event_head"] != declared_session["event_head"]
    assert len(added_session["event_head"]) == 64
    plan_after_bytes = dict(_tree_snapshot(data_root))
    assert all(
        plan_after_bytes.get(path) == payload
        for path, payload in plan_before_bytes.items()
    )
    assert set(plan_after_bytes) > set(plan_before_bytes)

    prefix8 = journey_root / "prefix8"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix8,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix8_original_bytes = dict(_tree_snapshot(data_root))
    attach_before_start_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "attach-before-start",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix8,
        attach_before_start_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(attach_before_start_context.data_root)
    attach_before_start = diagnostic_attach_marker(
        attach_before_start_context,
        operation_id="dj1.attach-before-start",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=8,
        diagnostic_marker_ref=publication.diagnostic_marker_ref,
    )
    _assert_public_failure(
        attach_before_start,
        "diagnostic.marker.attach",
        "DIAGNOSTIC_INVALID_TRANSITION",
        case_name="attach-before-start",
    )
    assert _tree_snapshot(attach_before_start_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix8_original_bytes

    start_before_bytes = dict(_tree_snapshot(data_root))
    started = diagnostic_start_verification(
        diagnostic,
        operation_id="dj1.verification.start",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=8,
        verification_plan_id=verification_plan.verification_plan_id,
    )
    started_wire = _assert_public_success(
        started,
        "diagnostic.verification.start",
    )
    started_data = started_wire["data"]
    assert isinstance(started_data, dict)
    started_session = started_data["session"]
    assert isinstance(started_session, dict)
    assert started_data == {
        "session": started_session,
        "verification_plan_id": verification_plan.verification_plan_id,
    }
    assert started_session["revision"] == 9
    assert started_session["state"] == "VERIFYING"
    assert started_session["event_head"] != added_session["event_head"]
    assert len(started_session["event_head"]) == 64
    start_after_bytes = dict(_tree_snapshot(data_root))
    assert all(
        start_after_bytes.get(path) == payload
        for path, payload in start_before_bytes.items()
    )
    assert set(start_after_bytes) > set(start_before_bytes)

    prefix9 = journey_root / "prefix9"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix9,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix9_original_bytes = dict(_tree_snapshot(data_root))
    marker_ref = publication.diagnostic_marker_ref
    unpaired_marker = DiagnosticMarkerRef.new(
        marker_id="c" * 64,
        marker_evidence_id=marker_ref.marker_evidence_id,
        analysis_id=marker_ref.analysis_id,
        analysis_evidence_id=verification_plan.failed_before_evidence_id,
        diagnostic_session_id=marker_ref.diagnostic_session_id,
        hypothesis_id=marker_ref.hypothesis_id,
        polarity=marker_ref.polarity,
        label=marker_ref.label,
        rationale=marker_ref.rationale,
    )
    unpaired_marker_context = DiagnosticWorkflowContext(
        project_root,
        journey_root / "unpaired-marker",
        "dj1-session",
    )
    _copy_public_diagnostic_prefix(
        prefix9,
        unpaired_marker_context.data_root,
        project_root=project_root,
        session_id="dj1-session",
    )
    before = _tree_snapshot(unpaired_marker_context.data_root)
    unpaired_marker_result = diagnostic_attach_marker(
        unpaired_marker_context,
        operation_id="dj1.unpaired-marker",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=9,
        diagnostic_marker_ref=unpaired_marker,
    )
    _assert_public_failure(
        unpaired_marker_result,
        "diagnostic.marker.attach",
        "DIAGNOSTIC_PLAN_INVALID",
        case_name="unpaired-marker",
    )
    assert _tree_snapshot(unpaired_marker_context.data_root) == before
    assert _tree_snapshot(data_root) == prefix9_original_bytes

    attach_before_bytes = dict(_tree_snapshot(data_root))
    attached = diagnostic_attach_marker(
        diagnostic,
        operation_id="dj1.marker.attach",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=9,
        diagnostic_marker_ref=marker_ref,
    )
    attached_wire = _assert_public_success(
        attached,
        "diagnostic.marker.attach",
    )
    attached_data = attached_wire["data"]
    assert isinstance(attached_data, dict)
    attached_session = attached_data["session"]
    assert isinstance(attached_session, dict)
    assert attached_data == {
        "session": attached_session,
        "diagnostic_marker_ref": marker_ref.to_dict(),
    }
    assert attached_session["revision"] == 10
    assert attached_session["state"] == "VERIFYING"
    assert attached_session["event_head"] != started_session["event_head"]
    assert len(attached_session["event_head"]) == 64
    attach_after_bytes = dict(_tree_snapshot(data_root))
    assert all(
        attach_after_bytes.get(path) == payload
        for path, payload in attach_before_bytes.items()
    )
    assert set(attach_after_bytes) > set(attach_before_bytes)

    prefix10 = journey_root / "prefix10"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix10,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix10_original_bytes = dict(_tree_snapshot(data_root))
    invalid_completion_cases = (
        ("empty-executed", [], False),
        (
            "too-many-executed",
            [f"dj1.executed.{index}" for index in range(65)],
            False,
        ),
        ("duplicate-executed", [vs08b.FAILED_RUN_ID, vs08b.FAILED_RUN_ID], False),
        (
            "cancelled-one",
            [vs08b.FAILED_RUN_ID],
            1,
        ),
    )
    for case_name, executed_operation_ids, cancelled in invalid_completion_cases:
        case_context = DiagnosticWorkflowContext(
            project_root,
            journey_root / f"completion-{case_name}",
            "dj1-session",
        )
        _copy_public_diagnostic_prefix(
            prefix10,
            case_context.data_root,
            project_root=project_root,
            session_id="dj1-session",
        )
        before = _tree_snapshot(case_context.data_root)
        invalid_completion = diagnostic_complete_verification(
            case_context,
            operation_id=f"dj1.completion.{case_name}",
            diagnostic_session_id=diagnostic_storage_id,
            expected_revision=10,
            executed_operation_ids=executed_operation_ids,
            cancelled=cancelled,
        )
        _assert_public_failure(
            invalid_completion,
            "diagnostic.verification.complete",
            "DIAGNOSTIC_INVALID_EVENT",
            case_name=case_name,
        )
        assert _tree_snapshot(case_context.data_root) == before
        assert _tree_snapshot(data_root) == prefix10_original_bytes

    prefix10_session = diagnostic_show(
        _fresh_diagnostic_context(diagnostic),
        diagnostic_session_id=diagnostic_storage_id,
    ).to_dict()["data"]["session"]
    assert isinstance(prefix10_session, dict)
    prefix10_event_head = prefix10_session["event_head"]
    executed_operation_ids = [
        vs08b.FAILED_RUN_ID,
        vs08b.FIXED_RUN_ID,
        "monitor.analysis.compare",
        "monitor.analysis.bundle",
    ]
    completed = diagnostic_complete_verification(
        diagnostic,
        operation_id="dj1.completion",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=10,
        executed_operation_ids=executed_operation_ids,
        cancelled=False,
    )
    completed_wire = _assert_public_success(
        completed,
        "diagnostic.verification.complete",
    )
    completed_data = completed_wire["data"]
    assert isinstance(completed_data, dict)
    expected_verification = FixVerification.new(
        diagnostic_session_id=diagnostic_storage_id,
        failed_before_run_id=verification_plan.failed_before_run_id,
        failed_before_evidence_id=verification_plan.failed_before_evidence_id,
        source_change_declaration_id=verification_plan.source_change_declaration_id,
        fixed_after_run_id=verification_plan.fixed_after_run_id,
        fixed_after_evidence_id=verification_plan.fixed_after_evidence_id,
        verification_plan_id=verification_plan.verification_plan_id,
        verification_plan_digest=verification_plan.plan_digest,
        analysis_ids=verification_plan.required_analysis_ids,
        analysis_evidence_ids=verification_plan.required_analysis_evidence_ids,
        executed_operation_ids=tuple(executed_operation_ids),
        status="PASSED",
        reason_code="VERIFICATION_PASSED",
        completed_at_utc=after_run.manifest.ended_at_utc,
    ).to_dict()
    completed_session = completed_data["session"]
    assert isinstance(completed_session, dict)
    assert completed_data == {
        "session": completed_session,
        "fix_verification": expected_verification,
    }
    assert completed_session["revision"] == 11
    assert completed_session["state"] == "RESOLVED"
    assert completed_session["active_verification_plan_id"] is None
    assert completed_session["event_head"] != prefix10_event_head
    assert len(completed_session["event_head"]) == 64
    assert completed_session["fix_verifications"] == [expected_verification]
    prefix10_bytes = dict(_tree_snapshot(prefix10))
    after_completion_bytes = dict(_tree_snapshot(data_root))
    assert all(
        after_completion_bytes.get(path) == payload
        for path, payload in prefix10_bytes.items()
    )
    assert set(after_completion_bytes) > set(prefix10_bytes)
    prefix11 = journey_root / "prefix11"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix11,
        project_root=project_root,
        session_id="dj1-session",
    )
    prefix11_bytes = dict(_tree_snapshot(prefix11))
    assert prefix11_bytes == after_completion_bytes

    shown_after = diagnostic_show_verification(
        _fresh_diagnostic_context(diagnostic),
        diagnostic_session_id=diagnostic_storage_id,
    )
    shown_after_wire = _assert_public_success(
        shown_after,
        "diagnostic.verification.show",
    )
    assert shown_after_wire["data"] == {
        "session": completed_session,
        "fix_verifications": [expected_verification],
        "authoritative": True,
    }

    before_retry = _tree_snapshot(data_root)
    assert dict(before_retry) == prefix11_bytes
    retry = diagnostic_complete_verification(
        diagnostic,
        operation_id="dj1.completion",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=10,
        executed_operation_ids=executed_operation_ids,
        cancelled=False,
    )
    assert retry.to_dict() == completed_wire  # type: ignore[union-attr]
    assert _tree_snapshot(data_root) == before_retry

    before_new_completion = _tree_snapshot(data_root)
    new_completion = diagnostic_complete_verification(
        diagnostic,
        operation_id="dj1.completion-new-operation",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=11,
        executed_operation_ids=executed_operation_ids,
        cancelled=False,
    )
    _assert_public_failure(
        new_completion,
        "diagnostic.verification.complete",
        "DIAGNOSTIC_INVALID_TRANSITION",
        case_name="new-completion-operation",
    )
    assert _tree_snapshot(data_root) == before_new_completion

    before_new_declaration = _tree_snapshot(data_root)
    new_declaration = diagnostic_declare_source_change(
        diagnostic,
        operation_id="dj1.source-change.new-operation",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=11,
        source_change_declaration=declaration,
    )
    _assert_public_failure(
        new_declaration,
        "diagnostic.source-change.declare",
        "DIAGNOSTIC_INVALID_TRANSITION",
        case_name="new-declaration-operation",
    )
    assert _tree_snapshot(data_root) == before_new_declaration


def test_public_diagnostic_caller_journey_authority_refusals_preserve_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey_root = tmp_path / "diagnostic-public-authority-journey"
    journey_root.mkdir()
    (
        project_root,
        data_root,
        diagnostic_id,
        hypothesis_id,
        _failed_descriptor,
        fixed_descriptor,
        fixed_stream,
    ) = vs08b._prepare_real_diagnostic_before_source(
        journey_root,
        "cubemx",
        monkeypatch,
        "dj2-session",
    )
    diagnostic_storage_id = diagnostic_id.replace("-", "")
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, "dj2-session")
    baseline_workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        PROJECT_ID,
        "dj2-session",
    )
    baseline_evidence = EvidenceStore(baseline_workspace.workspace_root / "evidence")
    before_run = TestRunRepository(baseline_evidence).load(vs08b.FAILED_RUN_ID)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = vs08b._source_change(
        journey_root,
        baseline_evidence,
        before_run,
        fixed_fixture.descriptor.identity,
        hypothesis_id,
    )
    base_diff_envelope = baseline_evidence.get_envelope(declaration.diff_evidence_id)
    base_diff_artifact = declaration.diff_artifact

    prefix6 = journey_root / "prefix6"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix6,
        project_root=project_root,
        session_id="dj2-session",
    )
    prefix6_bytes = dict(_tree_snapshot(data_root))
    diff_cases = (
        "operation",
        "artifact-kind",
        "media-type",
    )
    for case_name in diff_cases:
        case_data = journey_root / f"diff-{case_name}"
        case_context = DiagnosticWorkflowContext(project_root, case_data, "dj2-session")
        _copy_public_diagnostic_prefix(
            prefix6,
            case_data,
            project_root=project_root,
            session_id="dj2-session",
        )
        case_workspace = WorkspacePaths.from_roots(
            case_data,
            project_root,
            PROJECT_ID,
            "dj2-session",
        )
        case_evidence = EvidenceStore(case_workspace.workspace_root / "evidence")
        variant_artifact = base_diff_artifact
        variant_operation = base_diff_envelope.operation
        variant_media_type = base_diff_artifact.media_type
        variant_kind = base_diff_artifact.kind
        if case_name == "operation":
            variant_operation = "diagnostic-source-change.variant-operation"
        elif case_name == "artifact-kind":
            variant_kind = "wrong-source-diff-kind"
        else:
            variant_media_type = "application/octet-stream"
        if case_name != "operation":
            source = journey_root / f"diff-{case_name}.bin"
            source.write_bytes(
                case_evidence.read_artifact(
                    base_diff_artifact,
                    maximum_bytes=1_000_000,
                )
            )
            variant_artifact = case_evidence.ingest_file(
                source,
                kind=variant_kind,
                media_type=variant_media_type,
            )
        variant_envelope = EvidenceEnvelope(
            identity=base_diff_envelope.identity,
            operation=variant_operation,
            produced_at_utc=base_diff_envelope.produced_at_utc,
            parents=base_diff_envelope.parents,
            artifacts=(variant_artifact,),
            metadata=dict(base_diff_envelope.metadata),
        )
        case_evidence.put_envelope(variant_envelope)
        variant_declaration = SourceChangeDeclaration.new(
            before_source_sha256=declaration.before_source_sha256,
            after_source_sha256=declaration.after_source_sha256,
            before_build_id=declaration.before_build_id,
            before_elf_sha256=declaration.before_elf_sha256,
            after_build_id=declaration.after_build_id,
            after_elf_sha256=declaration.after_elf_sha256,
            changed_paths=declaration.changed_paths,
            diff_evidence_id=str(variant_envelope.evidence_id),
            diff_artifact=variant_artifact,
            claimed_hypothesis_ids=declaration.claimed_hypothesis_ids,
            validation_plan_id=declaration.validation_plan_id,
        )
        before = _tree_snapshot(case_data)
        result = diagnostic_declare_source_change(
            case_context,
            operation_id=f"dj2.diff.{case_name}",
            diagnostic_session_id=diagnostic_storage_id,
            expected_revision=6,
            source_change_declaration=variant_declaration,
        )
        _assert_public_failure(
            result,
            "diagnostic.source-change.declare",
            "EVIDENCE_INTEGRITY_FAILURE",
            case_name=case_name,
        )
        assert _tree_snapshot(case_data) == before
        assert _tree_snapshot(data_root) == prefix6_bytes

    declaration_before_bytes = dict(_tree_snapshot(data_root))
    before_declaration_wire = _assert_public_success(
        diagnostic_show(
            _fresh_diagnostic_context(diagnostic),
            diagnostic_session_id=diagnostic_storage_id,
        ),
        "diagnostic.show",
    )
    before_declaration_data = before_declaration_wire["data"]
    assert isinstance(before_declaration_data, dict)
    before_declaration_session = before_declaration_data["session"]
    assert isinstance(before_declaration_session, dict)
    assert before_declaration_data == {
        "session": before_declaration_session,
        "authoritative": True,
    }
    declared = diagnostic_declare_source_change(
        diagnostic,
        operation_id="dj2.source-change.declare",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        source_change_declaration=declaration,
    )
    declared_wire = _assert_public_success(
        declared,
        "diagnostic.source-change.declare",
    )
    declared_data = declared_wire["data"]
    assert isinstance(declared_data, dict)
    declared_session = declared_data["session"]
    assert isinstance(declared_session, dict)
    assert declared_data == {
        "session": declared_session,
        "source_change_declaration": declaration.to_dict(),
    }
    assert declared_session["revision"] == 7
    assert declared_session["state"] == "FIX_PROPOSED"
    assert declared_session["event_head"] != before_declaration_session["event_head"]
    assert len(declared_session["event_head"]) == 64
    declaration_after_bytes = dict(_tree_snapshot(data_root))
    assert all(
        declaration_after_bytes.get(path) == payload
        for path, payload in declaration_before_bytes.items()
    )
    assert set(declaration_after_bytes) > set(declaration_before_bytes)

    workspace, verification_plan, publication, _after_run = _prepare_public_diagnostic_authorities(
        journey_root,
        project_root,
        data_root,
        "dj2-session",
        diagnostic_storage_id,
        hypothesis_id,
        declaration,
        fixed_descriptor,
        fixed_stream,
    )
    assert workspace.workspace_id == baseline_workspace.workspace_id
    prefix7 = journey_root / "prefix7"
    _copy_public_diagnostic_prefix(
        data_root,
        prefix7,
        project_root=project_root,
        session_id="dj2-session",
    )
    prefix7_bytes = dict(_tree_snapshot(data_root))
    analysis_id = publication.analysis_result.analysis_id
    analysis_root = get_root(baseline_evidence, "monitor-analysis", analysis_id)
    analysis_envelope = baseline_evidence.get_envelope(analysis_root.manifest_id)
    analysis_artifact = analysis_envelope.artifacts[0]
    analysis_payload = json.loads(
        baseline_evidence.read_artifact(
            analysis_artifact,
            maximum_bytes=1_000_000,
        ).decode("utf-8")
    )

    def plan_for(analysis_ref: str, evidence_ref: str) -> VerificationPlan:
        return VerificationPlan.new(
            verification_plan_id=verification_plan.verification_plan_id,
            diagnostic_session_id=verification_plan.diagnostic_session_id,
            failed_before_run_id=verification_plan.failed_before_run_id,
            failed_before_evidence_id=verification_plan.failed_before_evidence_id,
            source_change_declaration_id=verification_plan.source_change_declaration_id,
            fixed_after_run_id=verification_plan.fixed_after_run_id,
            fixed_after_evidence_id=verification_plan.fixed_after_evidence_id,
            required_analysis_ids=(analysis_ref,),
            required_analysis_evidence_ids=(evidence_ref,),
            required_monitor_quality=verification_plan.required_monitor_quality,
            expected_changed=verification_plan.expected_changed,
        )

    def assert_plan_refusal(
        case_name: str,
        case_data: Path,
        plan: VerificationPlan,
    ) -> None:
        context = DiagnosticWorkflowContext(project_root, case_data, "dj2-session")
        before = _tree_snapshot(case_data)
        result = diagnostic_add_verification_plan(
            context,
            operation_id=f"dj2.plan.{case_name}",
            diagnostic_session_id=diagnostic_storage_id,
            expected_revision=7,
            verification_plan=plan,
        )
        _assert_public_failure(
            result,
            "diagnostic.verification-plan.add",
            "EVIDENCE_INTEGRITY_FAILURE",
            case_name=case_name,
        )
        assert _tree_snapshot(case_data) == before
        assert _tree_snapshot(data_root) == prefix7_bytes

    wrong_plan_evidence = plan_for(
        analysis_id,
        verification_plan.failed_before_evidence_id,
    )
    wrong_plan_data = journey_root / "plan-evidence-mismatch"
    _copy_public_diagnostic_prefix(
        prefix7,
        wrong_plan_data,
        project_root=project_root,
        session_id="dj2-session",
    )
    assert_plan_refusal("evidence-mismatch", wrong_plan_data, wrong_plan_evidence)

    for case_name, parents in (
        ("parents-count", analysis_envelope.parents[:2]),
        (
            "third-parent",
            (
                analysis_envelope.parents[0],
                analysis_envelope.parents[1],
                str(TestRunRepository(baseline_evidence).load(vs08b.FAILED_RUN_ID).envelope.evidence_id),
            ),
        ),
    ):
        case_data = journey_root / f"analysis-{case_name}"
        _copy_public_diagnostic_prefix(
            prefix7,
            case_data,
            project_root=project_root,
            session_id="dj2-session",
            excluded_root=("monitor-analysis", analysis_id),
        )
        case_workspace = WorkspacePaths.from_roots(
            case_data,
            project_root,
            PROJECT_ID,
            "dj2-session",
        )
        case_evidence = EvidenceStore(case_workspace.workspace_root / "evidence")
        variant_envelope = EvidenceEnvelope(
            identity=analysis_envelope.identity,
            operation=analysis_envelope.operation,
            produced_at_utc=analysis_envelope.produced_at_utc,
            parents=parents,
            artifacts=analysis_envelope.artifacts,
            metadata=dict(analysis_envelope.metadata),
        )
        _publish_public_analysis_variant(
            case_evidence,
            root_id=analysis_id,
            envelope=variant_envelope,
            metadata=dict(analysis_root.metadata),
        )
        assert_plan_refusal(
            case_name,
            case_data,
            plan_for(analysis_id, str(variant_envelope.evidence_id)),
        )

    import_metadata_data = journey_root / "analysis-import-workspace"
    _copy_public_diagnostic_prefix(
        prefix7,
        import_metadata_data,
        project_root=project_root,
        session_id="dj2-session",
        excluded_root=("monitor-analysis", analysis_id),
    )
    import_metadata_workspace = WorkspacePaths.from_roots(
        import_metadata_data,
        project_root,
        PROJECT_ID,
        "dj2-session",
    )
    import_metadata_evidence = EvidenceStore(
        import_metadata_workspace.workspace_root / "evidence"
    )
    changed_metadata = dict(analysis_envelope.metadata)
    changed_metadata["import_workspace_id"] = "f" * 32
    import_variant = EvidenceEnvelope(
        identity=analysis_envelope.identity,
        operation=analysis_envelope.operation,
        produced_at_utc=analysis_envelope.produced_at_utc,
        parents=analysis_envelope.parents,
        artifacts=analysis_envelope.artifacts,
        metadata=changed_metadata,
    )
    _publish_public_analysis_variant(
        import_metadata_evidence,
        root_id=analysis_id,
        envelope=import_variant,
        metadata=changed_metadata,
    )
    assert_plan_refusal(
        "import-workspace",
        import_metadata_data,
        plan_for(analysis_id, str(import_variant.evidence_id)),
    )

    canonical_array_data = journey_root / "analysis-canonical-array"
    _copy_public_diagnostic_prefix(
        prefix7,
        canonical_array_data,
        project_root=project_root,
        session_id="dj2-session",
        excluded_root=("monitor-analysis", analysis_id),
    )
    canonical_array_workspace = WorkspacePaths.from_roots(
        canonical_array_data,
        project_root,
        PROJECT_ID,
        "dj2-session",
    )
    canonical_array_evidence = EvidenceStore(
        canonical_array_workspace.workspace_root / "evidence"
    )
    array_source = journey_root / "analysis-canonical-array.json"
    array_source.write_bytes(canonical_json_bytes([]))
    array_artifact = canonical_array_evidence.ingest_file(
        array_source,
        kind="monitor-analysis",
        media_type="application/json",
    )
    array_envelope = EvidenceEnvelope(
        identity=analysis_envelope.identity,
        operation=analysis_envelope.operation,
        produced_at_utc=analysis_envelope.produced_at_utc,
        parents=analysis_envelope.parents,
        artifacts=(array_artifact,),
        metadata=dict(analysis_envelope.metadata),
    )
    _publish_public_analysis_variant(
        canonical_array_evidence,
        root_id=analysis_id,
        envelope=array_envelope,
        metadata=dict(analysis_root.metadata),
    )
    assert_plan_refusal(
        "canonical-array",
        canonical_array_data,
        plan_for(analysis_id, str(array_envelope.evidence_id)),
    )

    claimed_id_data = journey_root / "analysis-claimed-id"
    _copy_public_diagnostic_prefix(
        prefix7,
        claimed_id_data,
        project_root=project_root,
        session_id="dj2-session",
        excluded_root=("monitor-analysis", analysis_id),
    )
    claimed_id_workspace = WorkspacePaths.from_roots(
        claimed_id_data,
        project_root,
        PROJECT_ID,
        "dj2-session",
    )
    claimed_id_evidence = EvidenceStore(claimed_id_workspace.workspace_root / "evidence")
    claimed_payload = copy.deepcopy(analysis_payload)
    claimed_payload["analysis_id"] = "e" * 64
    claimed_source = journey_root / "analysis-claimed-id.json"
    claimed_source.write_bytes(canonical_json_bytes(claimed_payload))
    claimed_artifact = claimed_id_evidence.ingest_file(
        claimed_source,
        kind="monitor-analysis",
        media_type="application/json",
    )
    claimed_envelope = EvidenceEnvelope(
        identity=analysis_envelope.identity,
        operation=analysis_envelope.operation,
        produced_at_utc=analysis_envelope.produced_at_utc,
        parents=analysis_envelope.parents,
        artifacts=(claimed_artifact,),
        metadata=dict(analysis_envelope.metadata),
    )
    _publish_public_analysis_variant(
        claimed_id_evidence,
        root_id=analysis_id,
        envelope=claimed_envelope,
        metadata=dict(analysis_root.metadata),
    )
    assert_plan_refusal(
        "claimed-analysis-id",
        claimed_id_data,
        plan_for(analysis_id, str(claimed_envelope.evidence_id)),
    )

    for case_name, payload_mutation in (
        ("nested-identity-extra", "nested"),
        ("top-level-extra", "top-level"),
        ("schema-two", "schema-two"),
    ):
        case_data = journey_root / f"analysis-{case_name}"
        _copy_public_diagnostic_prefix(
            prefix7,
            case_data,
            project_root=project_root,
            session_id="dj2-session",
        )
        case_workspace = WorkspacePaths.from_roots(
            case_data,
            project_root,
            PROJECT_ID,
            "dj2-session",
        )
        case_evidence = EvidenceStore(case_workspace.workspace_root / "evidence")
        payload = copy.deepcopy(analysis_payload)
        if payload_mutation == "nested":
            payload["identity"]["extra"] = "unexpected"
        elif payload_mutation == "top-level":
            payload["unexpected"] = True
        else:
            payload["schema"] = "stm32-monitor-analysis/2"
        unsigned_payload = {
            key: value for key, value in payload.items() if key != "analysis_id"
        }
        payload["analysis_id"] = hashlib.sha256(
            canonical_json_bytes(unsigned_payload)
        ).hexdigest()
        source = journey_root / f"analysis-{case_name}.json"
        source.write_bytes(canonical_json_bytes(payload))
        artifact = case_evidence.ingest_file(
            source,
            kind="monitor-analysis",
            media_type="application/json",
        )
        metadata = dict(analysis_envelope.metadata)
        metadata["analysis_id"] = payload["analysis_id"]
        envelope = EvidenceEnvelope(
            identity=analysis_envelope.identity,
            operation=analysis_envelope.operation,
            produced_at_utc=analysis_envelope.produced_at_utc,
            parents=analysis_envelope.parents,
            artifacts=(artifact,),
            metadata=metadata,
        )
        _publish_public_analysis_variant(
            case_evidence,
            root_id=payload["analysis_id"],
            envelope=envelope,
            metadata=metadata,
        )
        assert_plan_refusal(
            case_name,
            case_data,
            plan_for(str(payload["analysis_id"]), str(envelope.evidence_id)),
        )

    valid_plan_before = _tree_snapshot(data_root)
    assert valid_plan_before == prefix7_bytes
    valid_plan = diagnostic_add_verification_plan(
        diagnostic,
        operation_id="dj2.valid-plan-after-authority-refusals",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=verification_plan,
    )
    valid_plan_wire = _assert_public_success(
        valid_plan,
        "diagnostic.verification-plan.add",
    )
    valid_plan_data = valid_plan_wire["data"]
    assert isinstance(valid_plan_data, dict)
    assert valid_plan_data["verification_plan"] == verification_plan.to_dict()
    valid_plan_session = valid_plan_data["session"]
    assert isinstance(valid_plan_session, dict)
    assert valid_plan_session["revision"] == 8
    assert valid_plan_session["state"] == "FIX_PROPOSED"
    assert valid_plan_data == {
        "session": valid_plan_session,
        "verification_plan": verification_plan.to_dict(),
    }
    assert valid_plan_session["event_head"] != declared_session["event_head"]
    assert len(valid_plan_session["event_head"]) == 64
    valid_plan_after = dict(_tree_snapshot(data_root))
    assert all(valid_plan_after.get(path) == payload for path, payload in valid_plan_before)
    assert set(valid_plan_after) > set(valid_plan_before)


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
    (
        "digest-only",
        "swapped",
        "binding",
        "window",
        "group",
        "batch-digest",
        "projected-digest-count",
    ),
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
    elif mutation == "projected-digest-count":
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload["projected_batch_sha256s"].pop(),
            sync_transcript_root=True,
        )
    else:
        _replace_monitor_reference_authority(
            tmp_path,
            workspace,
            before_operation_id,
            lambda payload: payload["projected_batch_sha256s"].__setitem__(0, "0" * 64),
            sync_transcript_root=True,
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
    assert result.message == "Target replay evidence failed integrity validation."
    assert after == before
    assert result.data is None
    assert result.details == {}


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
        ("absent-analysis-root", "DIAGNOSTIC_CHAIN_CORRUPT"),
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
