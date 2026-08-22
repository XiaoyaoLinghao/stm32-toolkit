"""Runnable VS-03 Scenario B acceptance through public workflows."""

from __future__ import annotations

import gc
import json
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest, AnalysisResult, DiagnosticMarker
from stm32_monitor.analysis_workflows import (
    AnalysisBundleRef,
    AnalysisPublication,
    AnalysisWorkflowError,
    compare_monitor_runs,
    export_analysis_bundle,
)
from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.replay import MonitorRunRef, ingest_monitor_replay
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_plan,
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
    diagnostic_run_plan,
)
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository as _TestRunRepository
from stm32_toolkit.testing.replay import TargetReplayDescriptor, load_target_replay_fixture
import stm32_toolkit.testing_workflows as testing_workflows


PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
SESSION_ID = "vs03-scenario-b-session-0001"
TOOLKIT_FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
MONITOR_FIXTURES = Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03"
MONITOR_OPERATION_IDS = {
    "failed-before": "33333333-3333-4333-8333-333333333333",
    "fixed-after": "44444444-4444-4444-8444-444444444444",
}


def _project_manifest() -> dict[str, object]:
    return {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.6.0"},
        "project": {"name": "vs03-fixture", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
        "testing": {
            "target": {
                "executable": "build/test/firmware-tests.elf",
                "timeout_seconds": 120,
                "transport": {
                    "kind": "memory-mailbox",
                    "options": {"address": 0x20010000, "size": 4096},
                },
            }
        },
    }


def _project_snapshot(project_root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        sorted(
            (path.relative_to(project_root).as_posix(), path.read_bytes())
            for path in project_root.rglob("*")
            if path.is_file()
        )
    )


def _contexts(tmp_path: Path) -> tuple[testing_workflows.TestingWorkflowContext, DiagnosticWorkflowContext]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".stm32-project.json").write_bytes(
        json.dumps(_project_manifest(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    data_root = tmp_path / "data"
    return (
        testing_workflows.TestingWorkflowContext(project_root, data_root, SESSION_ID),
        DiagnosticWorkflowContext(project_root, data_root, SESSION_ID),
    )


def _fresh(context: DiagnosticWorkflowContext) -> DiagnosticWorkflowContext:
    return DiagnosticWorkflowContext(
        Path(context.project_root), Path(context.data_root), str(context.session_id)
    )


def _assert_ok(result: object) -> Mapping[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return data


def _run_target_replay(
    context: testing_workflows.TestingWorkflowContext, role: str
) -> dict[str, object]:
    operation_id = "vs03-" + ("failed-before" if role == "failed-before" else "fixed-after")
    result = testing_workflows.target_replay_run(
        context,
        operation_id,
        TOOLKIT_FIXTURES / f"{role}.json",
        TOOLKIT_FIXTURES / f"{role}.hex",
    )
    return _assert_ok(result)


def _ingest_monitor_pair(workspace: WorkspacePaths, evidence: EvidenceStore) -> dict[str, MonitorRunRef]:
    return {
        role: ingest_monitor_replay(
            workspace,
            evidence,
            MONITOR_OPERATION_IDS[role],
            MONITOR_FIXTURES / f"{role}.json",
        )
        for role in ("failed-before", "fixed-after")
    }


def _target_pair(evidence: EvidenceStore) -> tuple[object, object]:
    repository = _TestRunRepository(evidence)
    return repository.load("vs03-failed-before"), repository.load("vs03-fixed-after")


def _source_change(
    tmp_path: Path,
    evidence: EvidenceStore,
    before: object,
    after_identity: object,
    hypothesis_id: str,
) -> SourceChangeDeclaration:
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(b"--- a/src/main.c\n+++ b/src/main.c\n@@ -1 +1 @@\n-old\n+new\n")
    diff_artifact = evidence.ingest_file(diff_path, kind="source-diff", media_type="text/x-diff")
    before_identity = before.manifest.identity
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-08-22T00:00:00.000000Z",
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    return SourceChangeDeclaration.new(
        before_source_sha256=before_identity.input_snapshot_sha256,
        after_source_sha256=after_identity.input_snapshot_sha256,
        before_build_id=before_identity.build_id,
        before_elf_sha256=before_identity.elf_sha256,
        after_build_id=after_identity.build_id,
        after_elf_sha256=after_identity.elf_sha256,
        changed_paths=("src/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )


def _assert_sha256(value: object) -> str:
    assert isinstance(value, str)
    assert len(value) == 64
    assert all(character in "0123456789abcdef" for character in value)
    return value


def _assert_public_target_show(
    shown: Mapping[str, object],
    *,
    expected_state: str,
    expected_run_id: str,
    expected_evidence_id: str,
    expected_origin_workspace_id: str,
    import_workspace_id: str,
) -> None:
    assert shown["authoritative"] is True
    assert _assert_sha256(shown["evidence_id"]) == expected_evidence_id
    assert shown["execution_source"] == "replay"
    assert shown["physical_transport_evidence"] is False
    assert _assert_sha256(shown["origin_workspace_id"]) == expected_origin_workspace_id
    assert _assert_sha256(shown["import_workspace_id"]) == import_workspace_id
    assert shown["origin_workspace_id"] != shown["import_workspace_id"]
    run = shown["run"]
    assert isinstance(run, Mapping)
    assert run["run_id"] == expected_run_id
    assert run["mode"] == "target"
    assert run["transport"] == "replay"
    assert run["state"] == expected_state
    identity = run["identity"]
    assert isinstance(identity, Mapping)
    assert _assert_sha256(identity["workspace_id"]) == expected_origin_workspace_id


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


def _authority_snapshot(workspace: WorkspacePaths) -> tuple[tuple[tuple[str, bytes], ...], tuple[tuple[str, bytes], ...]]:
    def files(root: Path) -> tuple[tuple[str, bytes], ...]:
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (path.relative_to(root).as_posix(), path.read_bytes())
                for path in root.rglob("*")
                if path.is_file()
            )
        )

    return files(workspace.diagnostics_root), files(workspace.workspace_root / "evidence")


def _event_snapshot(workspace: WorkspacePaths, session_id: str) -> tuple[tuple[str, bytes], ...]:
    root = workspace.diagnostics_root / "sessions" / session_id / "events"
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (path.name, path.read_bytes())
            for path in root.glob("*.json")
            if path.is_file()
        )
    )


def _prepare_diagnostic_session(
    tmp_path: Path,
) -> tuple[DiagnosticWorkflowContext, str, str, WorkspacePaths, EvidenceStore]:
    testing_context, diagnostic_context = _contexts(tmp_path)
    failed = _run_target_replay(testing_context, "failed-before")
    failed_run = failed["run"]
    assert isinstance(failed_run, Mapping)
    session = _assert_ok(
        diagnostic_start(
            _fresh(diagnostic_context),
            operation_id="negative-diagnostic-start",
            failed_test_run_id=str(failed_run["run_id"]),
            failed_run_mode="target",
        )
    )["session"]
    assert isinstance(session, Mapping)
    session_id = str(session["diagnostic_session_id"])
    _assert_ok(
        diagnostic_begin(
            _fresh(diagnostic_context),
            operation_id="negative-diagnostic-begin",
            diagnostic_session_id=session_id,
            expected_revision=1,
        )
    )
    hypothesis = _assert_ok(
        diagnostic_add_hypothesis(
            _fresh(diagnostic_context),
            operation_id="negative-diagnostic-hypothesis",
            diagnostic_session_id=session_id,
            expected_revision=2,
            statement="the failed replay identifies the faulty behavior",
        )
    )["hypothesis"]
    assert isinstance(hypothesis, Mapping)
    workspace = WorkspacePaths.from_roots(
        testing_context.data_root,
        testing_context.project_root,
        PROJECT_ID,
        SESSION_ID,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    return diagnostic_context, session_id, str(hypothesis["hypothesis_id"]), workspace, evidence


def test_scenario_b_incompatible_monitor_identity_does_not_append_or_publish(
    tmp_path: Path,
) -> None:
    diagnostic_context, session_id, hypothesis_id, workspace, evidence = _prepare_diagnostic_session(
        tmp_path
    )
    refs = _ingest_monitor_pair(workspace, evidence)
    before_authority = _authority_snapshot(workspace)
    before_session = _assert_ok(
        diagnostic_show(_fresh(diagnostic_context), diagnostic_session_id=session_id)
    )["session"]
    assert isinstance(before_session, Mapping)
    before_revision = before_session["revision"]
    before_events = _event_snapshot(workspace, session_id)

    with pytest.raises(AnalysisWorkflowError) as raised:
        compare_monitor_runs(
            WorkspacePaths.from_roots(
                workspace.data_root,
                workspace.project_root,
                PROJECT_ID,
                SESSION_ID,
            ),
            EvidenceStore(workspace.workspace_root / "evidence"),
            _request(refs["failed-before"], refs["fixed-after"]),
            session_id,
            hypothesis_id,
            "supports",
            "an undeclared firmware change must fail closed",
        )
    assert raised.value.code == "INCOMPATIBLE_IDENTITY"
    assert _authority_snapshot(workspace) == before_authority
    after_session = _assert_ok(
        diagnostic_show(_fresh(diagnostic_context), diagnostic_session_id=session_id)
    )["session"]
    assert isinstance(after_session, Mapping)
    assert after_session["revision"] == before_revision
    assert _event_snapshot(workspace, session_id) == before_events
    assert not (workspace.workspace_root / "evidence" / "roots" / "monitor-analysis").exists()


def test_scenario_b_insufficient_monitor_pairs_are_inconclusive_and_reopen_session(
    tmp_path: Path,
) -> None:
    diagnostic_context, session_id, hypothesis_id, workspace, evidence = _prepare_diagnostic_session(
        tmp_path
    )
    testing_context = testing_workflows.TestingWorkflowContext(
        diagnostic_context.project_root,
        diagnostic_context.data_root,
        diagnostic_context.session_id,
    )
    fixed = _run_target_replay(testing_context, "fixed-after")
    fixed_run = fixed["run"]
    assert isinstance(fixed_run, Mapping)
    assert fixed_run["state"] == "passed"

    refs = _ingest_monitor_pair(workspace, evidence)
    before, after = _target_pair(evidence)
    declaration = _source_change(tmp_path, evidence, before, after.manifest.identity, hypothesis_id)
    request = _request(refs["failed-before"], refs["fixed-after"], minimum=3)
    publication = compare_monitor_runs(
        WorkspacePaths.from_roots(
            workspace.data_root,
            workspace.project_root,
            PROJECT_ID,
            SESSION_ID,
        ),
        EvidenceStore(workspace.workspace_root / "evidence"),
        request,
        session_id,
        hypothesis_id,
        "supports",
        "the replay pair is too short to establish a change",
        declaration,
    )
    assert publication.analysis_result.quality == "INVALID"
    assert publication.analysis_result.conclusion == "INCONCLUSIVE"
    assert publication.analysis_result.changed is None
    assert publication.diagnostic_marker.label == "analysis-inconclusive"

    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=session_id,
        failed_before_run_id="vs03-failed-before",
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="vs03-fixed-after",
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    _assert_ok(
        diagnostic_declare_source_change(
            _fresh(diagnostic_context),
            operation_id="insufficient-source-change-declare",
            diagnostic_session_id=session_id,
            expected_revision=3,
            source_change_declaration=declaration,
        )
    )
    _assert_ok(
        diagnostic_add_verification_plan(
            _fresh(diagnostic_context),
            operation_id="insufficient-verification-plan-add",
            diagnostic_session_id=session_id,
            expected_revision=4,
            verification_plan=verification_plan,
        )
    )
    _assert_ok(
        diagnostic_start_verification(
            _fresh(diagnostic_context),
            operation_id="insufficient-verification-start",
            diagnostic_session_id=session_id,
            expected_revision=5,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    _assert_ok(
        diagnostic_attach_marker(
            _fresh(diagnostic_context),
            operation_id="insufficient-marker-attach",
            diagnostic_session_id=session_id,
            expected_revision=6,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    completed = _assert_ok(
        diagnostic_complete_verification(
            _fresh(diagnostic_context),
            operation_id="insufficient-verification-complete",
            diagnostic_session_id=session_id,
            expected_revision=7,
            executed_operation_ids=["vs03-fixed-after", "monitor.analysis.compare"],
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == "INCONCLUSIVE"
    assert verification["reason_code"] == "ANALYSIS_NOT_VALID"
    assert completed["session"]["state"] == "INVESTIGATING"
    shown = _assert_ok(
        diagnostic_show_verification(
            _fresh(diagnostic_context), diagnostic_session_id=session_id
        )
    )
    assert shown["fix_verifications"][0]["status"] == "INCONCLUSIVE"
    assert shown["session"]["state"] == "INVESTIGATING"


def test_scenario_b_public_target_monitor_loop_survives_fresh_reload(
    tmp_path: Path,
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    project_before = _project_snapshot(testing_context.project_root)

    failed_data = _run_target_replay(testing_context, "failed-before")
    failed_run = failed_data["run"]
    assert isinstance(failed_run, Mapping)
    assert failed_run["state"] == "failed"
    failed_run_id = str(failed_run["run_id"])

    started = _assert_ok(
        diagnostic_start(
            _fresh(diagnostic_context),
            operation_id="scenario-b-diagnostic-start",
            failed_test_run_id=failed_run_id,
            failed_run_mode="target",
        )
    )
    session = started["session"]
    assert isinstance(session, Mapping)
    diagnostic_session_id = str(session["diagnostic_session_id"])
    assert session["state"] == "OPEN"
    _assert_ok(
        diagnostic_begin(
            _fresh(diagnostic_context),
            operation_id="scenario-b-diagnostic-begin",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=1,
        )
    )
    first_hypothesis = _assert_ok(
        diagnostic_add_hypothesis(
            _fresh(diagnostic_context),
            operation_id="scenario-b-hypothesis-one",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=2,
            statement="the failing replay case identifies the faulty behavior",
        )
    )["hypothesis"]
    second_hypothesis = _assert_ok(
        diagnostic_add_hypothesis(
            _fresh(diagnostic_context),
            operation_id="scenario-b-hypothesis-two",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=3,
            statement="the failing case count is incidental",
        )
    )["hypothesis"]
    assert isinstance(first_hypothesis, Mapping)
    assert isinstance(second_hypothesis, Mapping)
    first_hypothesis_id = str(first_hypothesis["hypothesis_id"])
    second_hypothesis_id = str(second_hypothesis["hypothesis_id"])
    assert first_hypothesis_id != second_hypothesis_id

    workspace = WorkspacePaths.from_roots(
        testing_context.data_root,
        testing_context.project_root,
        PROJECT_ID,
        SESSION_ID,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    monitor_before = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["failed-before"],
        MONITOR_FIXTURES / "failed-before.json",
    )

    steps = [
        {
            "step_id": "failed-case",
            "selector": {"kind": "case-state", "case_id": "case.replay"},
            "expected_value": "failed",
            "purpose": "confirm the replayed failing case",
        },
        {
            "step_id": "failed-count",
            "selector": {"kind": "case-count", "state": "failed"},
            "expected_value": 1,
            "purpose": "confirm one failed case",
        },
    ]
    plan_data = _assert_ok(
        diagnostic_add_plan(
            _fresh(diagnostic_context),
            operation_id="scenario-b-observation-plan-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=4,
            steps=steps,
        )
    )
    observation_plan = plan_data["observation_plan"]
    assert isinstance(observation_plan, Mapping)
    observation_plan_id = str(observation_plan["plan_id"])
    observed = _assert_ok(
        diagnostic_run_plan(
            _fresh(diagnostic_context),
            operation_id="scenario-b-observation-plan-run",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=5,
            plan_id=observation_plan_id,
        )
    )
    observations = observed["observation_results"]
    assert isinstance(observations, (list, tuple))
    assert len(observations) == 2
    assert all(item["matched"] is True for item in observations)
    _assert_ok(
        diagnostic_assess_hypothesis(
            _fresh(diagnostic_context),
            operation_id="scenario-b-hypothesis-assess-one",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=6,
            hypothesis_id=first_hypothesis_id,
            plan_id=observation_plan_id,
            step_id="failed-case",
            polarity="supports",
            rationale="the failed case supports the first hypothesis",
        )
    )
    _assert_ok(
        diagnostic_assess_hypothesis(
            _fresh(diagnostic_context),
            operation_id="scenario-b-hypothesis-assess-two",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=7,
            hypothesis_id=second_hypothesis_id,
            plan_id=observation_plan_id,
            step_id="failed-count",
            polarity="refutes",
            rationale="the failed count refutes the competing hypothesis",
        )
    )

    before = _TestRunRepository(evidence).load("vs03-failed-before")
    fixed_fixture = load_target_replay_fixture(
        TOOLKIT_FIXTURES / "fixed-after.json",
        TOOLKIT_FIXTURES / "fixed-after.hex",
    )
    declaration = _source_change(
        tmp_path,
        evidence,
        before,
        fixed_fixture.descriptor.identity,
        first_hypothesis_id,
    )
    declared = _assert_ok(
        diagnostic_declare_source_change(
            _fresh(diagnostic_context),
            operation_id="scenario-b-source-change-declare",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=8,
            source_change_declaration=declaration,
        )
    )
    assert declared["source_change_declaration"]["declaration_id"] == declaration.declaration_id

    fixed_data = _run_target_replay(testing_context, "fixed-after")
    fixed_run = fixed_data["run"]
    assert isinstance(fixed_run, Mapping)
    assert fixed_run["state"] == "passed"
    fixed_run_id = str(fixed_run["run_id"])
    monitor_after = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["fixed-after"],
        MONITOR_FIXTURES / "fixed-after.json",
    )
    assert monitor_before.import_workspace_id == workspace.workspace_id
    assert monitor_after.import_workspace_id == workspace.workspace_id
    assert monitor_before.origin_workspace_id != monitor_before.import_workspace_id
    assert monitor_after.origin_workspace_id != monitor_after.import_workspace_id

    before, after = _target_pair(evidence)
    request = _request(monitor_before, monitor_after)
    publication = compare_monitor_runs(
        WorkspacePaths.from_roots(
            testing_context.data_root,
            testing_context.project_root,
            PROJECT_ID,
            SESSION_ID,
        ),
        EvidenceStore(workspace.workspace_root / "evidence"),
        request,
        diagnostic_session_id,
        first_hypothesis_id,
        "supports",
        "the fixed replay changed the observed counter",
        declaration,
    )
    assert isinstance(publication, AnalysisPublication)
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.conclusion == "COMPLETED"
    assert publication.analysis_result.changed is True

    bundle_bytes, bundle_ref = export_analysis_bundle(
        WorkspacePaths.from_roots(
            testing_context.data_root,
            testing_context.project_root,
            PROJECT_ID,
            SESSION_ID,
        ),
        EvidenceStore(workspace.workspace_root / "evidence"),
        request,
        publication,
        failed_run_id,
        fixed_run_id,
        declaration,
    )
    assert isinstance(bundle_ref, AnalysisBundleRef)
    assert bundle_bytes == export_analysis_bundle(
        WorkspacePaths.from_roots(
            testing_context.data_root,
            testing_context.project_root,
            PROJECT_ID,
            SESSION_ID,
        ),
        EvidenceStore(workspace.workspace_root / "evidence"),
        request,
        AnalysisPublication.from_value(publication.to_dict()),
        failed_run_id,
        fixed_run_id,
        declaration,
    )[0]

    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_session_id,
        failed_before_run_id=failed_run_id,
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=fixed_run_id,
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality=publication.analysis_result.quality,
        expected_changed=True,
    )
    _assert_ok(
        diagnostic_add_verification_plan(
            _fresh(diagnostic_context),
            operation_id="scenario-b-verification-plan-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=9,
            verification_plan=verification_plan,
        )
    )
    _assert_ok(
        diagnostic_start_verification(
            _fresh(diagnostic_context),
            operation_id="scenario-b-verification-start",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=10,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    attached = _assert_ok(
        diagnostic_attach_marker(
            _fresh(diagnostic_context),
            operation_id="scenario-b-marker-attach",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=11,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    assert attached["session"]["state"] == "VERIFYING"
    completed = _assert_ok(
        diagnostic_complete_verification(
            _fresh(diagnostic_context),
            operation_id="scenario-b-verification-complete",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=12,
            executed_operation_ids=[
                "vs03-failed-before",
                "vs03-fixed-after",
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == "PASSED"
    assert verification["reason_code"] == "VERIFICATION_PASSED"
    assert completed["session"]["state"] == "RESOLVED"

    stable_project_root = Path(testing_context.project_root)
    stable_data_root = Path(testing_context.data_root)
    stable_session_id = str(testing_context.session_id)
    import_workspace_id = _assert_sha256(str(workspace.workspace_id))
    failed_origin_workspace_id = _assert_sha256(str(before.envelope.identity.workspace_id))
    fixed_origin_workspace_id = _assert_sha256(str(after.envelope.identity.workspace_id))
    failed_evidence_id = _assert_sha256(str(before.envelope.evidence_id))
    fixed_evidence_id = _assert_sha256(str(after.envelope.evidence_id))
    analysis_id = _assert_sha256(publication.analysis_result.analysis_id)
    analysis_evidence_id = _assert_sha256(str(publication.analysis_evidence_ref.evidence_id))
    marker_id = _assert_sha256(publication.diagnostic_marker.marker_id)
    marker_evidence_id = _assert_sha256(str(publication.diagnostic_marker_ref.marker_evidence_id))
    bundle_id = _assert_sha256(bundle_ref.bundle_id)
    bundle_evidence_id = _assert_sha256(str(bundle_ref.evidence_id))
    request_digest = _assert_sha256(request.request_digest)
    source_change_id = _assert_sha256(declaration.declaration_id)
    expected_bundle_bytes = bytes(bundle_bytes)
    analysis_lineage = dict(publication.analysis_result.identity.to_dict())
    monitor_origin_workspace_ids = {
        role: _assert_sha256(ref.origin_workspace_id)
        for role, ref in (("failed-before", monitor_before), ("fixed-after", monitor_after))
    }
    monitor_import_workspace_ids = {
        role: _assert_sha256(ref.import_workspace_id)
        for role, ref in (("failed-before", monitor_before), ("fixed-after", monitor_after))
    }
    assert failed_origin_workspace_id == fixed_origin_workspace_id
    assert monitor_origin_workspace_ids["failed-before"] == failed_origin_workspace_id
    assert monitor_origin_workspace_ids["fixed-after"] == fixed_origin_workspace_id
    assert monitor_import_workspace_ids == {
        "failed-before": import_workspace_id,
        "fixed-after": import_workspace_id,
    }

    del (
        testing_context,
        diagnostic_context,
        workspace,
        evidence,
        before,
        after,
        monitor_before,
        monitor_after,
        request,
        declaration,
        verification_plan,
        fixed_fixture,
        failed_data,
        failed_run,
        fixed_data,
        fixed_run,
        started,
        session,
        first_hypothesis,
        second_hypothesis,
        declared,
        plan_data,
        observation_plan,
        observed,
        observations,
        publication,
        bundle_ref,
        bundle_bytes,
        attached,
        completed,
        verification,
    )
    gc.collect()

    fresh_testing_context = testing_workflows.TestingWorkflowContext(
        stable_project_root,
        stable_data_root,
        stable_session_id,
    )
    fresh_diagnostic_context = DiagnosticWorkflowContext(
        stable_project_root,
        stable_data_root,
        stable_session_id,
    )
    fresh_workspace = WorkspacePaths.from_roots(
        stable_data_root,
        stable_project_root,
        PROJECT_ID,
        stable_session_id,
    )
    fresh_evidence = EvidenceStore(fresh_workspace.workspace_root / "evidence")

    fresh_target_shows: dict[str, Mapping[str, object]] = {}
    target_expectations = {
        "failed-before": ("failed", failed_run_id, failed_evidence_id, failed_origin_workspace_id),
        "fixed-after": ("passed", fixed_run_id, fixed_evidence_id, fixed_origin_workspace_id),
    }
    for role, (state, run_id, evidence_id, origin_workspace_id) in target_expectations.items():
        shown = _assert_ok(
            testing_workflows.test_show(fresh_testing_context, run_id=run_id)
        )
        fresh_target_shows[role] = shown
        _assert_public_target_show(
            shown,
            expected_state=state,
            expected_run_id=run_id,
            expected_evidence_id=evidence_id,
            expected_origin_workspace_id=origin_workspace_id,
            import_workspace_id=import_workspace_id,
        )

        run_root = get_root(fresh_evidence, "test-run", run_id)
        assert run_root.manifest_id == evidence_id
        run_envelope = fresh_evidence.get_envelope(run_root.manifest_id)
        assert _assert_sha256(str(run_envelope.identity.workspace_id)) == origin_workspace_id
        assert run_envelope.metadata["import_workspace_id"] == import_workspace_id
        descriptor_envelope = fresh_evidence.get_envelope(run_envelope.parents[0])
        descriptor_artifact = next(
            artifact
            for artifact in descriptor_envelope.artifacts
            if artifact.kind == "target-replay-descriptor"
        )
        descriptor = TargetReplayDescriptor.from_value(
            json.loads(
                fresh_evidence.read_artifact(
                    descriptor_artifact,
                    maximum_bytes=256 * 1024,
                ).decode("utf-8")
            )
        )
        assert _assert_sha256(descriptor.identity.workspace_id) == origin_workspace_id
        assert descriptor.identity.workspace_id == run_envelope.metadata["origin_workspace_id"]
        assert descriptor.physical_transport_evidence is False
        assert descriptor.source == "toolkit-generated-protocol-replay"

    fresh_monitor_refs: dict[str, MonitorRunRef] = {}
    for role, operation_id in MONITOR_OPERATION_IDS.items():
        ref_root = get_root(fresh_evidence, "monitor-run-ref", operation_id)
        ref_envelope = fresh_evidence.get_envelope(ref_root.manifest_id)
        payload = json.loads(
            fresh_evidence.read_artifact(ref_envelope.artifacts[0], maximum_bytes=1_000_000)
            .decode("utf-8")
        )
        fresh_monitor_refs[role] = MonitorRunRef.from_value(payload)
        ref = fresh_monitor_refs[role]
        expected_origin = monitor_origin_workspace_ids[role]
        assert ref.execution_source == "replay"
        assert ref.physical_transport_evidence is False
        assert _assert_sha256(ref.origin_workspace_id) == expected_origin
        assert _assert_sha256(ref.import_workspace_id) == import_workspace_id
        assert ref.import_workspace_id != ref.origin_workspace_id
        target_show = fresh_target_shows[role]
        assert ref.origin_workspace_id == target_show["origin_workspace_id"]
        assert ref.import_workspace_id == target_show["import_workspace_id"]
        history = HistoryStore(fresh_workspace)
        try:
            history_result = history.query_history(
                HistoryQuery(
                    session_id=SESSION_ID,
                    start_ns=0,
                    end_ns=(1 << 63) - 1,
                    run_id=UUID(ref.projected_run_id),
                    limit=32,
                )
            )
            assert history_result.ok is True
            assert history_result.data is not None
            assert len(history_result.data.batches) == 2
        finally:
            history.close()

    analysis_root = get_root(fresh_evidence, "monitor-analysis", analysis_id)
    assert analysis_root.manifest_id == analysis_evidence_id
    analysis_envelope = fresh_evidence.get_envelope(analysis_root.manifest_id)
    assert _assert_sha256(str(analysis_envelope.identity.workspace_id)) == fixed_origin_workspace_id
    assert analysis_envelope.metadata["origin_workspace_id"] == fixed_origin_workspace_id
    assert analysis_envelope.metadata["import_workspace_id"] == import_workspace_id
    analysis_payload = json.loads(
        fresh_evidence.read_artifact(analysis_envelope.artifacts[0], maximum_bytes=1_000_000)
        .decode("utf-8")
    )
    reloaded_analysis = AnalysisResult.from_value(analysis_payload)
    assert reloaded_analysis.analysis_id == analysis_id
    assert reloaded_analysis.request_digest == request_digest
    assert reloaded_analysis.identity.to_dict() == analysis_lineage
    assert reloaded_analysis.identity.origin_workspace_id == fixed_origin_workspace_id
    assert reloaded_analysis.identity.import_workspace_id == import_workspace_id
    assert reloaded_analysis.identity.source_change_declaration_id == source_change_id
    assert reloaded_analysis.quality == "VALID"
    assert reloaded_analysis.conclusion == "COMPLETED"
    assert reloaded_analysis.changed is True

    marker_root = get_root(fresh_evidence, "diagnostic-marker", marker_id)
    assert marker_root.manifest_id == marker_evidence_id
    marker_envelope = fresh_evidence.get_envelope(marker_root.manifest_id)
    assert _assert_sha256(str(marker_envelope.identity.workspace_id)) == fixed_origin_workspace_id
    assert marker_envelope.metadata["origin_workspace_id"] == fixed_origin_workspace_id
    assert marker_envelope.metadata["import_workspace_id"] == import_workspace_id
    marker_payload = json.loads(
        fresh_evidence.read_artifact(marker_envelope.artifacts[0], maximum_bytes=1_000_000)
        .decode("utf-8")
    )
    reloaded_marker = DiagnosticMarker.from_value(marker_payload)
    assert reloaded_marker.analysis_id == analysis_id
    assert reloaded_marker.label == "change-observed"

    bundle_root = get_root(fresh_evidence, "monitor-analysis-bundle", bundle_id)
    assert bundle_root.manifest_id == bundle_evidence_id
    assert bundle_root.metadata["origin_workspace_id"] == fixed_origin_workspace_id
    assert bundle_root.metadata["import_workspace_id"] == import_workspace_id
    bundle_envelope = fresh_evidence.get_envelope(bundle_root.manifest_id)
    assert _assert_sha256(str(bundle_envelope.identity.workspace_id)) == fixed_origin_workspace_id
    assert bundle_envelope.metadata["origin_workspace_id"] == fixed_origin_workspace_id
    assert bundle_envelope.metadata["import_workspace_id"] == import_workspace_id
    assert (
        fresh_evidence.read_artifact(bundle_envelope.artifacts[0], maximum_bytes=2_000_000)
        == expected_bundle_bytes
    )
    bundle_document = json.loads(expected_bundle_bytes.decode("utf-8"))
    assert bundle_document["schema"] == "stm32-monitor-analysis-bundle/1"
    assert bundle_document["analysis_result"]["analysis_id"] == analysis_id
    assert bundle_document["analysis_result"]["identity"]["origin_workspace_id"] == fixed_origin_workspace_id
    assert bundle_document["analysis_result"]["identity"]["import_workspace_id"] == import_workspace_id
    assert bundle_document["before_run"]["origin_workspace_id"] == failed_origin_workspace_id
    assert bundle_document["before_run"]["import_workspace_id"] == import_workspace_id
    assert bundle_document["after_run"]["origin_workspace_id"] == fixed_origin_workspace_id
    assert bundle_document["after_run"]["import_workspace_id"] == import_workspace_id
    assert bundle_document["source_change_declaration_id"] == source_change_id

    reloaded_verification = _assert_ok(
        diagnostic_show_verification(
            fresh_diagnostic_context, diagnostic_session_id=diagnostic_session_id
        )
    )
    assert reloaded_verification["session"]["state"] == "RESOLVED"
    assert reloaded_verification["fix_verifications"][0]["status"] == "PASSED"
    reloaded_session = _assert_ok(
        diagnostic_show(
            fresh_diagnostic_context, diagnostic_session_id=diagnostic_session_id
        )
    )["session"]
    assert reloaded_session["revision"] == 13
    assert reloaded_session["state"] == "RESOLVED"
    reloaded_hypotheses = reloaded_session["hypotheses"]
    assert isinstance(reloaded_hypotheses, (list, tuple))
    assert len(reloaded_hypotheses[0]["supporting"]) == 1
    assert len(reloaded_hypotheses[1]["refuting"]) == 1
    event_paths = sorted(
        (
            fresh_workspace.diagnostics_root
            / "sessions"
            / diagnostic_session_id
            / "events"
        ).glob("*.json")
    )
    assert len(event_paths) == 13
    assert json.loads(event_paths[-1].read_text(encoding="utf-8"))["event_type"] == (
        "verification.completed"
    )
    for revision in range(1, 14):
        checkpoint = get_root(
            fresh_evidence,
            "diagnostic-session",
            f"{diagnostic_session_id}.{revision:08d}",
        )
        checkpoint_envelope = fresh_evidence.get_envelope(checkpoint.manifest_id)
        assert checkpoint_envelope.operation == "diagnostic-event"
        assert checkpoint.metadata["revision"] == revision
    assert _project_snapshot(stable_project_root) == project_before
