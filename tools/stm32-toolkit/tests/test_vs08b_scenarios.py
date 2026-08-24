from __future__ import annotations

import hashlib
import json
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
    diagnostic_run_plan,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope
from stm32_toolkit.evidence.gc import RootRecord
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
