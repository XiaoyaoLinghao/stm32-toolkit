from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.replay import ingest_monitor_replay
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
import test_vs08a_scenarios as vs08a
from stm32_toolkit.acceptance.model import REQUIRED_STAGES
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
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
    diagnostic_show_verification,
    diagnostic_run_plan,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import FIX_VERIFICATION_SCHEMA, FixVerification, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.evidence.gc import RootRecord, get_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.result import OperationResult
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing.replay import calculate_replay_id, canonical_replay_json_bytes
from stm32_toolkit.testing.replay import load_target_replay_fixture
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run
from test_vs08a_scenarios import (
    FAILED_RUN_ID,
    FIXED_RUN_ID,
    RECORD_ID,
    _complete_existing_chain,
    _project_manifest,
    _source_change,
    MONITOR_FIXTURES,
    MONITOR_OPERATION_IDS,
    PROJECT_ID,
)


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def _result_data(result: object) -> dict[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, dict) or hasattr(data, "items")
    return data  # type: ignore[return-value]


def _prepare_real_diagnostic_before_source(
    tmp_path: Path,
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
    runtime_session_id: str,
) -> tuple[Path, Path, str, str, Path, Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    manifest = _project_manifest(origin)
    manifest["target"]["device"] = "stm32:vs03-fixture"
    (project_root / ".stm32-project.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    data_root = tmp_path / "data"
    monkeypatch.setattr(vs08a.diagnostic_workflows_module, "_session_id_factory", lambda: "00000000000040008000000000000004")
    testing = TestingWorkflowContext(project_root, data_root, runtime_session_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, runtime_session_id)
    failed_descriptor, failed_stream = vs08a._canonical_replay_inputs(tmp_path, "failed-before", FAILED_RUN_ID)
    fixed_descriptor, fixed_stream = vs08a._canonical_replay_inputs(tmp_path, "fixed-after", FIXED_RUN_ID)
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, UUID("123e4567-e89b-42d3-a456-426614174000"), runtime_session_id
    )
    for descriptor_path, stream_path in ((failed_descriptor, failed_stream), (fixed_descriptor, fixed_stream)):
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        descriptor["identity"]["workspace_id"] = workspace.workspace_id
        stream = bytes.fromhex(stream_path.read_text(encoding="ascii"))
        decoder = TargetFrameDecoder(max_stream_bytes=len(stream))
        frames = decoder.feed(stream)
        decoder.finish()
        encoded: list[bytes] = []
        for frame in frames[:-1]:
            payload = vs08a._json_thaw(frame.payload)
            if isinstance(payload, dict) and isinstance(payload.get("identity"), dict):
                payload["identity"]["workspace_id"] = workspace.workspace_id
            encoded.append(encode_frame(frame.kind, frame.sequence, payload))
        terminal = vs08a._json_thaw(frames[-1].payload)
        assert isinstance(terminal, dict)
        terminal["event_stream_digest"] = hashlib.sha256(b"".join(encoded)).hexdigest()
        encoded.append(encode_frame(frames[-1].kind, frames[-1].sequence, terminal))
        rewritten = b"".join(encoded)
        stream_path.write_text(rewritten.hex(), encoding="ascii")
        descriptor["stream"]["sha256"] = hashlib.sha256(rewritten).hexdigest()
        descriptor["stream"]["size_bytes"] = len(rewritten)
        descriptor["replay_id"] = calculate_replay_id(descriptor)
        descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor))
    assert target_replay_run(testing, FAILED_RUN_ID, failed_descriptor, failed_stream).ok
    started = _result_data(diagnostic_start(
        diagnostic,
        operation_id="vs08b-diagnostic-start",
        failed_test_run_id=FAILED_RUN_ID,
        failed_run_mode="target",
    ))
    session = started["session"]
    assert isinstance(session, dict) or hasattr(session, "items")
    diagnostic_id = str(session["diagnostic_session_id"])
    assert diagnostic_begin(
        diagnostic, operation_id="vs08b-diagnostic-begin", diagnostic_session_id=diagnostic_id, expected_revision=1
    ).ok
    hypothesis = _result_data(diagnostic_add_hypothesis(
        diagnostic,
        operation_id="vs08b-hypothesis-add",
        diagnostic_session_id=diagnostic_id,
        expected_revision=2,
        statement="the failed replay identifies the faulty behavior",
    ))["hypothesis"]
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = _result_data(diagnostic_add_plan(
        diagnostic,
        operation_id="vs08b-observation-plan-add",
        diagnostic_session_id=diagnostic_id,
        expected_revision=3,
        steps=[{"step_id": "failed-run", "selector": {"kind": "run-state"}, "expected_value": "failed", "purpose": "confirm the failed replay"}],
    ))["observation_plan"]
    plan_id = str(plan["plan_id"])
    assert diagnostic_run_plan(
        diagnostic, operation_id="vs08b-observation-plan-run", diagnostic_session_id=diagnostic_id, expected_revision=4, plan_id=plan_id
    ).ok
    assert diagnostic_assess_hypothesis(
        diagnostic,
        operation_id="vs08b-hypothesis-assess",
        diagnostic_session_id=diagnostic_id,
        expected_revision=5,
        hypothesis_id=hypothesis_id,
        plan_id=plan_id,
        step_id="failed-run",
        polarity="supports",
        rationale="the failed replay supports the hypothesis",
    ).ok
    return project_root, data_root, vs08a._wire_diagnostic_id(diagnostic_id), hypothesis_id, failed_descriptor, fixed_descriptor, fixed_stream


def _fake_authorities(monkeypatch: pytest.MonkeyPatch, *, origin: str = "keil") -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
        memory=SimpleNamespace(source=origin),
        target_device="STM32F429ZITx",
    )
    monkeypatch.setattr(recovery_workflows, "_load_project_model", lambda _root: model)
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_build_project_context",
        lambda *_args: OperationResult.success(
            "project.context",
            {"build": {"elfFresh": True, "preset": "arm-debug", "buildId": "b" * 64, "elfSha256": "e" * 64}},
        ),
    )


@pytest.mark.parametrize(
    ("origin", "scenario_id"),
    [("keil", "legacy-keil-migration"), ("cubemx", "new-cubemx-project")],
)
def test_each_accepted_origin_begins_and_resumes_software_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    scenario_id: str,
):
    _fake_authorities(monkeypatch, origin=origin)
    project = tmp_path / origin
    project.mkdir()
    context = AcceptanceRecoveryContext(project, tmp_path / "data", "session-a")
    result = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id=scenario_id,
        scenario_version="1",
    )
    assert result.ok is True
    attempt = result.data["attempt"]
    assert attempt["executionSource"] == "replay"
    assert attempt["physicalTransportEvidence"] is False
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["nextStage"] == "project-materialized"
    assert resumed.data["recoveryPolicy"]["physicalTransportEvidence"] is False


def test_timeout_refuses_advancement_without_publishing_a_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _fake_authorities(monkeypatch)
    current = ["2026-08-24T00:00:00.000000Z"]
    context = AcceptanceRecoveryContext(
        tmp_path / "project", tmp_path / "data", "session-a", clock=lambda: current[0]
    )
    context.project_root.mkdir()
    begun = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert begun.ok is True
    current[0] = "2026-08-24T00:01:00.000001Z"
    timed_out = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert timed_out.ok is False
    assert timed_out.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    shown = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert shown.ok is True
    assert shown.data["attempt"]["revision"] == 0
    assert shown.data["timedOut"] is True


def test_same_attempt_id_isolated_by_project_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _fake_authorities(monkeypatch)
    left_project = tmp_path / "left"
    right_project = tmp_path / "right"
    left_project.mkdir()
    right_project.mkdir()
    left = AcceptanceRecoveryContext(left_project, tmp_path / "data", "session-a")
    right = AcceptanceRecoveryContext(right_project, tmp_path / "data", "session-a")
    left_result = begin_acceptance_attempt(left, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1")
    right_result = begin_acceptance_attempt(right, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1")
    assert left_result.ok is True and right_result.ok is True
    assert left_result.data["attempt"]["workspaceId"] != right_result.data["attempt"]["workspaceId"]


@pytest.mark.parametrize(
    ("origin", "scenario_id"),
    [("keil", "legacy-keil-migration"), ("cubemx", "new-cubemx-project")],
)
def test_real_replay_diagnostic_acceptance_chain_reaches_revision_seven(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    scenario_id: str,
):
    runtime_session_id = f"vs08a-{origin}-session"
    project_root, data_root, diagnostic_id, hypothesis_id, failed_descriptor, fixed_descriptor, fixed_stream = _prepare_real_diagnostic_before_source(
        tmp_path, origin, monkeypatch, runtime_session_id
    )
    before = {
        "buildId": "c6b3ea0b953c3d62d50db1bbf4226cd2ff3652ecc271a7a8b5e58913e084f2d0",
        "elfSha256": "13dbac824a8ef5ff8034860da48cc55243ab60673a539e73c366e59d40412880",
        "inputSnapshotSha256": "7104a6333bf42b87ff41445a90f5b547e7256acd84c8e06e4c87eace48c6f139",
    }
    after = {
        "buildId": "65e2176034d1f74df3ab4ff1c6099938420ca6cb6367f76458f40ad4dee36ece",
        "elfSha256": "2b2268ba7c6caa110688f872a4f4264ffdf2c75ceff9bc341d17c2eaedf106c0",
        "inputSnapshotSha256": "70891c0e753d1b65d7fa40f0bbfd78f04b9432e733d89d342081df4b4af813dd",
    }
    build_calls = 0

    def build_context(*_args: object) -> OperationResult[dict[str, object]]:
        nonlocal build_calls
        value = before if build_calls == 0 else after
        build_calls += 1
        return OperationResult.success(
            "project.context",
            {"build": {"elfFresh": True, "preset": "arm-debug", **value}},
        )

    monkeypatch.setattr(recovery_workflows, "_build_project_context", build_context)
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(
            sha256=before["inputSnapshotSha256"] if build_calls <= 1 else after["inputSnapshotSha256"]
        ),
    )
    clock = lambda: "2026-08-24T00:00:00.000000Z"
    context = AcceptanceRecoveryContext(project_root, data_root, f"vs08a-{origin}-session", clock=clock)
    attempt_id = "00000000-0000-4000-8000-000000000010"
    assert begin_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        scenario_id=scenario_id,
        scenario_version="1",
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=0, stage="project-materialized"
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=0, stage="project-materialized"
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=1, stage="firmware-built-before"
    ).ok
    assert checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=1,
        stage="firmware-built-before",
    ).ok
    failed = checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    )
    assert failed.ok is True, failed.to_dict()
    assert checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    ).data == failed.data
    context = AcceptanceRecoveryContext(project_root, data_root, f"vs08a-{origin}-session", clock=clock)
    diagnosed = checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=diagnostic_id,
    )
    assert diagnosed.ok is True, diagnosed.to_dict()
    assert checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=diagnostic_id,
    ).data == diagnosed.data
    action_digest = resume_acceptance_attempt(context, attempt_id=attempt_id).data["actionDigest"]
    authorized = recovery_workflows.authorize_acceptance_source_change(
        context,
        attempt_id=attempt_id,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert authorized.ok is True, authorized.to_dict()
    assert recovery_workflows.authorize_acceptance_source_change(
        context,
        attempt_id=attempt_id,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    ).data == authorized.data
    workspace = WorkspacePaths.from_roots(data_root, project_root, PROJECT_ID, runtime_session_id)
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before_run = TestRunRepository(evidence).load(FAILED_RUN_ID)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = _source_change(tmp_path, evidence, before_run, fixed_fixture.descriptor.identity, hypothesis_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, runtime_session_id)
    diagnostic_storage_id = diagnostic_id.replace("-", "")
    assert diagnostic_declare_source_change(
        diagnostic,
        operation_id="vs08b-source-change-declare",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        source_change_declaration=declaration,
    ).ok
    assert target_replay_run(
        TestingWorkflowContext(project_root, data_root, runtime_session_id),
        FIXED_RUN_ID,
        fixed_descriptor,
        fixed_stream,
    ).ok
    after_run = TestRunRepository(evidence).load(FIXED_RUN_ID)
    monitor_paths: dict[str, Path] = {}
    for role in ("failed-before", "fixed-after"):
        source = MONITOR_FIXTURES / f"{role}.json"
        descriptor = json.loads(source.read_text(encoding="utf-8"))
        descriptor["binding"]["workspaceId"] = workspace.workspace_id
        for batch in descriptor["batches"]:
            batch["binding"]["workspaceId"] = workspace.workspace_id
        unsigned = {key: value for key, value in descriptor.items() if key != "fixture_sha256"}
        descriptor["fixture_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        target = tmp_path / f"monitor-{role}.json"
        target.write_text(json.dumps(descriptor, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        monitor_paths[role] = target
    monitor_before = ingest_monitor_replay(
        workspace, evidence, MONITOR_OPERATION_IDS["failed-before"], monitor_paths["failed-before"]
    )
    monitor_after = ingest_monitor_replay(
        workspace, evidence, MONITOR_OPERATION_IDS["fixed-after"], monitor_paths["fixed-after"]
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
        workspace, evidence, analysis_request, publication, FAILED_RUN_ID, FIXED_RUN_ID, declaration
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_storage_id,
        failed_before_run_id=FAILED_RUN_ID,
        failed_before_evidence_id=str(before_run.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=FIXED_RUN_ID,
        fixed_after_evidence_id=str(after_run.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    assert diagnostic_add_verification_plan(
        diagnostic,
        operation_id="vs08b-verification-plan-add",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=verification_plan,
    ).ok
    assert diagnostic_start_verification(
        diagnostic,
        operation_id="vs08b-verification-start",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=8,
        verification_plan_id=verification_plan.verification_plan_id,
    ).ok
    marker = diagnostic_attach_marker(
        diagnostic,
        operation_id="vs08b-marker-attach",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=9,
        diagnostic_marker_ref=publication.diagnostic_marker_ref,
    )
    assert marker.ok is True
    completed_diagnostic = diagnostic_complete_verification(
        diagnostic,
        operation_id="vs08b-verification-complete",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=10,
        executed_operation_ids=[FAILED_RUN_ID, FIXED_RUN_ID, "monitor.analysis.compare", "monitor.analysis.bundle"],
        cancelled=False,
    )
    assert completed_diagnostic.ok is True
    after_build = checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=5, stage="firmware-built-after"
    )
    assert after_build.ok is True, after_build.to_dict()
    assert checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=5, stage="firmware-built-after"
    ).data == after_build.data
    record = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, f"vs08a-{origin}-session"),
        record_id=RECORD_ID,
        scenario_id=scenario_id,
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert record.ok is True, record.to_dict()
    completed = checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=6,
        stage="target-fix-verified",
        acceptance_record_id=RECORD_ID,
    )
    assert completed.ok is True, completed.to_dict()
    assert checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=6,
        stage="target-fix-verified",
        acceptance_record_id=RECORD_ID,
    ).data == completed.data
    shown = recovery_workflows.show_acceptance_attempt(context, attempt_id=attempt_id)
    assert shown.ok is True and shown.data["attempt"]["revision"] == 7
    assert shown.data["attempt"]["executionSource"] == "replay"
    assert shown.data["attempt"]["physicalTransportEvidence"] is False
    assert show_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, f"vs08a-{origin}-session"),
        record_id=RECORD_ID,
    ).ok
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    root_id = recovery_workflows._root_id(attempt_id, 6)
    root = recovery_workflows.get_root(evidence, "acceptance-attempt", root_id)
    old_envelope = evidence.get_envelope(root.manifest_id)
    payload = json.loads(
        recovery_workflows.canonical_json_bytes(old_envelope.metadata["attempt"]).decode("utf-8")
    )
    payload["sourceChangeAuthorization"]["actionDigest"] = "0" * 64
    payload["checkpointId"] = "0" * 64
    payload["checkpointId"] = hashlib.sha256(
        recovery_workflows.canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "checkpointId"}
        )
    ).hexdigest()
    tampered = recovery_workflows.AcceptanceAttempt.from_value(payload)
    tampered_envelope = EvidenceEnvelope(
        identity=old_envelope.identity,
        operation=old_envelope.operation,
        produced_at_utc=old_envelope.produced_at_utc,
        parents=old_envelope.parents,
        artifacts=old_envelope.artifacts,
        metadata=recovery_workflows._envelope_metadata(tampered),
    )
    with evidence._mutation_lock():
        evidence._put_envelope_locked(tampered_envelope)
        recovery_workflows._typed_root_path(evidence, root_id).unlink()
        recovery_workflows._publish_root_locked(
            evidence,
            RootRecord(
                "acceptance-attempt",
                root_id,
                str(tampered_envelope.evidence_id),
                recovery_workflows._root_metadata(tampered),
            ),
        )
    # Remove only the downstream test root so the assertion isolates the
    # revision-5 authorization invariant rather than a broken rev6->rev7 link.
    recovery_workflows._typed_root_path(evidence, recovery_workflows._root_id(attempt_id, 7)).unlink()
    assert recovery_workflows.show_acceptance_attempt(context, attempt_id=attempt_id).code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def _prepare_completion_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str, str, VerificationPlan, object, object]:
    """Build one real replay/diagnostic graph through the revision-10 marker."""

    runtime_session_id = "vs08b-completion-session"
    project_root, data_root, diagnostic_id, hypothesis_id, failed_descriptor, fixed_descriptor, fixed_stream = (
        _prepare_real_diagnostic_before_source(
            tmp_path,
            "cubemx",
            monkeypatch,
            runtime_session_id,
        )
    )
    workspace = WorkspacePaths.from_roots(data_root, project_root, PROJECT_ID, runtime_session_id)
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before_run = TestRunRepository(evidence).load(FAILED_RUN_ID)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = _source_change(
        tmp_path,
        evidence,
        before_run,
        fixed_fixture.descriptor.identity,
        hypothesis_id,
    )
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, runtime_session_id)
    diagnostic_storage_id = diagnostic_id.replace("-", "")
    assert diagnostic_declare_source_change(
        diagnostic,
        operation_id="vs08b-completion-source-change",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=6,
        source_change_declaration=declaration,
    ).ok
    testing = TestingWorkflowContext(project_root, data_root, runtime_session_id)
    assert target_replay_run(testing, FIXED_RUN_ID, fixed_descriptor, fixed_stream).ok
    after_run = TestRunRepository(evidence).load(FIXED_RUN_ID)

    monitor_paths: dict[str, Path] = {}
    for role in ("failed-before", "fixed-after"):
        source = MONITOR_FIXTURES / f"{role}.json"
        descriptor = json.loads(source.read_text(encoding="utf-8"))
        descriptor["binding"]["workspaceId"] = workspace.workspace_id
        for batch in descriptor["batches"]:
            batch["binding"]["workspaceId"] = workspace.workspace_id
        unsigned = {key: value for key, value in descriptor.items() if key != "fixture_sha256"}
        descriptor["fixture_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        target = tmp_path / f"completion-monitor-{role}.json"
        target.write_text(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        monitor_paths[role] = target
    monitor_before = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["failed-before"],
        monitor_paths["failed-before"],
    )
    monitor_after = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["fixed-after"],
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
        FAILED_RUN_ID,
        FIXED_RUN_ID,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_storage_id,
        failed_before_run_id=FAILED_RUN_ID,
        failed_before_evidence_id=str(before_run.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=FIXED_RUN_ID,
        fixed_after_evidence_id=str(after_run.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    assert diagnostic_add_verification_plan(
        diagnostic,
        operation_id="vs08b-completion-verification-plan",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=7,
        verification_plan=verification_plan,
    ).ok
    assert diagnostic_start_verification(
        diagnostic,
        operation_id="vs08b-completion-verification-start",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=8,
        verification_plan_id=verification_plan.verification_plan_id,
    ).ok
    assert diagnostic_attach_marker(
        diagnostic,
        operation_id="vs08b-completion-marker-attach",
        diagnostic_session_id=diagnostic_storage_id,
        expected_revision=9,
        diagnostic_marker_ref=publication.diagnostic_marker_ref,
    ).ok
    return (
        project_root,
        data_root,
        runtime_session_id,
        diagnostic_storage_id,
        verification_plan,
        publication,
        after_run,
    )


def test_completion_artifact_public_wire_and_persistence_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (
        project_root,
        data_root,
        runtime_session_id,
        diagnostic_storage_id,
        verification_plan,
        publication,
        after_run,
    ) = _prepare_completion_graph(tmp_path, monkeypatch)
    baseline_workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        PROJECT_ID,
        runtime_session_id,
    )
    marker_ref = publication.diagnostic_marker_ref
    marker_id = marker_ref.marker_id
    executed_operation_ids = (
        FAILED_RUN_ID,
        FIXED_RUN_ID,
        "monitor.analysis.compare",
        "monitor.analysis.bundle",
    )
    variants = [
        {"name": "positive-valid", "mutation": "valid", "status": "PASSED", "reason": "VERIFICATION_PASSED"},
        {"name": "root-metadata-mismatch", "mutation": "root-metadata", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "envelope-operation-mismatch", "mutation": "envelope-operation", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "zero-artifacts", "mutation": "zero-artifacts", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "root-empty-object", "mutation": "root-empty", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "root-noncanonical-json", "mutation": "root-noncanonical", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "artifact-kind-mismatch", "mutation": "artifact-kind", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "artifact-media-mismatch", "mutation": "artifact-media", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "artifact-array-json", "mutation": "artifact-array", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
        {"name": "artifact-noncanonical-object", "mutation": "artifact-noncanonical", "status": "INCONCLUSIVE", "reason": "MANDATORY_EVIDENCE_CORRUPT"},
    ]
    variants_root = tmp_path / "completion-variants"
    variants_root.mkdir()
    for variant in variants:
        case_name = variant["name"]
        clone_data = variants_root / case_name
        shutil.copytree(data_root, clone_data)
        clone_workspace = WorkspacePaths.from_roots(
            clone_data,
            project_root,
            PROJECT_ID,
            runtime_session_id,
        )
        assert clone_workspace.workspace_id == baseline_workspace.workspace_id
        clone_diagnostic = DiagnosticWorkflowContext(
            project_root,
            clone_data,
            runtime_session_id,
        )
        shown_before = diagnostic_show_verification(
            clone_diagnostic,
            diagnostic_session_id=diagnostic_storage_id,
        )
        shown_before_wire = shown_before.to_dict()
        assert shown_before_wire["protocol"] == "stm32-toolkit/1"
        assert shown_before_wire["ok"] is True
        assert shown_before_wire["operation"] == "diagnostic.verification.show"
        assert shown_before_wire["code"] == "OK"
        assert shown_before_wire["message"] == ""
        assert shown_before_wire["details"] == {}
        shown_before_data = shown_before_wire["data"]
        assert isinstance(shown_before_data, dict)
        assert shown_before_data["authoritative"] is True
        before_session = shown_before_data["session"]
        assert isinstance(before_session, dict)
        assert before_session["revision"] == 10
        assert before_session["state"] == "VERIFYING"
        assert before_session["active_verification_plan_id"] == verification_plan.verification_plan_id

        clone_evidence = EvidenceStore(clone_workspace.workspace_root / "evidence")
        marker_root = get_root(clone_evidence, "diagnostic-marker", marker_id)
        marker_envelope = clone_evidence.get_envelope(marker_root.manifest_id)
        marker_payload = clone_evidence.read_artifact(
            marker_envelope.artifacts[0],
            maximum_bytes=64 * 1024 * 1024,
        )

        def root_file(root_type: str, root_id: str) -> Path:
            key_digest = hashlib.sha256(
                canonical_json_bytes({"root_type": root_type, "root_id": root_id})
            ).hexdigest()
            return clone_evidence.root / "roots" / root_type / f"{key_digest}.json"

        marker_root_path = root_file("diagnostic-marker", marker_id)
        prior_session_root_id = f"{diagnostic_storage_id}.00000010"
        prior_session_root_path = root_file("diagnostic-session", prior_session_root_id)
        prior_session_root_bytes = prior_session_root_path.read_bytes()
        prior_session_roots = {
            path.name
            for path in (clone_evidence.root / "roots" / "diagnostic-session").glob("*.json")
        }
        original_marker_manifest_bytes = (
            clone_evidence.root / "manifests" / f"{marker_ref.marker_evidence_id}.json"
        ).read_bytes()

        mutation = variant["mutation"]
        if mutation == "valid":
            pass
        elif mutation == "root-empty":
            marker_root_path.write_bytes(b"{}")
        elif mutation == "root-noncanonical":
            marker_root_path.write_bytes(
                json.dumps(marker_root.to_dict(), indent=1, ensure_ascii=False).encode("utf-8")
            )
        else:
            envelope_operation = marker_envelope.operation
            root_metadata = dict(marker_envelope.metadata)
            artifacts = ()
            if mutation != "zero-artifacts":
                if mutation in {"artifact-array", "artifact-noncanonical"}:
                    artifact_payload = b"[]" if mutation == "artifact-array" else b'{"b":2,"a":1}'
                else:
                    artifact_payload = marker_payload
                artifact_source = tmp_path / "completion-artifacts" / f"{case_name}.json"
                artifact_source.parent.mkdir(exist_ok=True)
                artifact_source.write_bytes(artifact_payload)
                artifact = clone_evidence.ingest_file(
                    artifact_source,
                    kind="diagnostic-marker",
                    media_type="application/json",
                )
                if mutation == "artifact-kind":
                    artifact = replace(artifact, kind="wrong-diagnostic-kind")
                elif mutation == "artifact-media":
                    artifact = replace(artifact, media_type="text/plain")
                artifacts = (artifact,)
            if mutation == "envelope-operation":
                envelope_operation = "diagnostic-marker-corrupt"
            envelope = EvidenceEnvelope(
                identity=marker_envelope.identity,
                operation=envelope_operation,
                produced_at_utc=marker_envelope.produced_at_utc,
                parents=marker_envelope.parents,
                artifacts=artifacts,
                metadata=marker_envelope.metadata,
            )
            clone_evidence.put_envelope(envelope)
            if mutation == "root-metadata":
                root_metadata["fixture_mutation"] = "root-metadata-mismatch"
            replacement_root = RootRecord(
                "diagnostic-marker",
                marker_id,
                str(envelope.evidence_id),
                root_metadata,
            )
            marker_root_path.write_bytes(canonical_json_bytes(replacement_root.to_dict()))

        mutation_snapshot = vs08a._evidence_snapshot(clone_data)
        completed = diagnostic_complete_verification(
            clone_diagnostic,
            operation_id=f"vs08b-completion-{case_name}",
            diagnostic_session_id=diagnostic_storage_id,
            expected_revision=10,
            executed_operation_ids=list(executed_operation_ids),
            cancelled=False,
        )
        wire = completed.to_dict()
        assert wire["protocol"] == "stm32-toolkit/1"
        assert wire["ok"] is True
        assert wire["operation"] == "diagnostic.verification.complete"
        assert wire["code"] == "OK"
        assert wire["message"] == ""
        assert wire["details"] == {}
        data = wire["data"]
        assert isinstance(data, dict)
        assert set(data) == {"session", "fix_verification"}
        expected_state = "RESOLVED" if variant["status"] == "PASSED" else "INVESTIGATING"
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
            executed_operation_ids=executed_operation_ids,
            status=variant["status"],
            reason_code=variant["reason"],
            completed_at_utc=after_run.manifest.ended_at_utc,
        ).to_dict()
        verification = data["fix_verification"]
        assert verification == expected_verification
        assert verification["schema"] == FIX_VERIFICATION_SCHEMA
        session = data["session"]
        assert isinstance(session, dict)
        assert session["revision"] == 11
        assert session["state"] == expected_state
        assert session["active_verification_plan_id"] is None
        assert session["fix_verifications"] == [expected_verification]

        shown_after = diagnostic_show_verification(
            clone_diagnostic,
            diagnostic_session_id=diagnostic_storage_id,
        )
        shown_after_data = shown_after.to_dict()["data"]
        assert isinstance(shown_after_data, dict)
        assert shown_after_data["authoritative"] is True
        assert shown_after_data["session"] == session
        assert shown_after_data["fix_verifications"] == [expected_verification]

        latest_session_root_id = f"{diagnostic_storage_id}.00000011"
        latest_session_root = get_root(
            clone_evidence,
            "diagnostic-session",
            latest_session_root_id,
        )
        latest_session_root_path = root_file("diagnostic-session", latest_session_root_id)
        after_session_roots = {
            path.name
            for path in (clone_evidence.root / "roots" / "diagnostic-session").glob("*.json")
        }
        assert after_session_roots == prior_session_roots | {latest_session_root_path.name}
        assert prior_session_root_path.read_bytes() == prior_session_root_bytes
        assert latest_session_root.metadata["diagnostic_session_id"] == diagnostic_storage_id
        assert latest_session_root.metadata["revision"] == 11
        assert latest_session_root.metadata["state"] == expected_state
        completion_envelope = clone_evidence.get_envelope(latest_session_root.manifest_id)
        assert completion_envelope.operation == "diagnostic-event"
        assert len(completion_envelope.artifacts) == 1
        completion_event = json.loads(
            clone_evidence.read_artifact(
                completion_envelope.artifacts[0],
                maximum_bytes=64 * 1024 * 1024,
            ).decode("utf-8")
        )
        assert completion_event["event_type"] == "verification.completed"
        assert completion_event["sequence"] == 10
        assert completion_event["revision_before"] == 10
        assert completion_event["payload"]["request"]["fix_verification"] == expected_verification
        assert completion_event["payload"]["result"] == {
            "fix_verification_id": expected_verification["fix_verification_id"],
            "status": variant["status"],
            "reason_code": variant["reason"],
        }
        assert latest_session_root.metadata["event_digest"] == completion_event["digest"]
        assert (
            clone_evidence.root / "manifests" / f"{marker_ref.marker_evidence_id}.json"
        ).read_bytes() == original_marker_manifest_bytes
        assert clone_evidence.get_envelope(marker_ref.marker_evidence_id).to_dict() == marker_envelope.to_dict()
        after_mutation_snapshot = vs08a._evidence_snapshot(clone_data)
        assert {
            relative: after_mutation_snapshot[relative]
            for relative in mutation_snapshot
        } == mutation_snapshot
