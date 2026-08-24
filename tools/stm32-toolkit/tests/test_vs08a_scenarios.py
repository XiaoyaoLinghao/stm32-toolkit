from __future__ import annotations

import gc
import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.replay import ingest_monitor_replay
from stm32_toolkit.acceptance.model import AcceptanceRecord, describe_scenario
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
import stm32_toolkit.acceptance.workflows as acceptance_workflows
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
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows_module
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EVIDENCE_CORRUPT, EvidenceEnvelope, EvidenceValidationError
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.publication import (
    TestRunPublisher as RunPublisher,
    TestRunRepository as RunRepository,
)
from stm32_toolkit.testing.replay import (
    calculate_replay_id,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from stm32_toolkit.testing_workflows import (
    TestingWorkflowContext as TestContext,
    target_replay_run,
)

TestContext.__test__ = False
RunRepository.__test__ = False


PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
TOOLKIT_FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
MONITOR_FIXTURES = Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03"
FAILED_RUN_ID = "00000000-0000-4000-8000-000000000002"
FIXED_RUN_ID = "00000000-0000-4000-8000-000000000003"
RECORD_ID = "00000000-0000-4000-8000-000000000001"
ALTERNATE_FIXED_RUN_ID = "00000000-0000-4000-8000-000000000006"
MONITOR_OPERATION_IDS = {
    "failed-before": "33333333-3333-4333-8333-333333333333",
    "fixed-after": "44444444-4444-4444-8444-444444444444",
}


def _project_manifest(origin: str) -> dict[str, object]:
    return {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.8.0"},
        "project": {
            "name": f"vs08a-{origin}-fixture",
            "origin": "keil-migration" if origin == "keil" else "cubemx",
        },
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
        "memory": {"source": origin, "regions": []},
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


def _ok(result: object) -> Mapping[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return data


def _json_thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_thaw(item) for item in value]
    return value


def _wire_diagnostic_id(compact: str) -> str:
    return f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}"


def _canonical_replay_inputs(
    tmp_path: Path, role: str, run_id: str
) -> tuple[Path, Path]:
    fixture_root = TOOLKIT_FIXTURES
    descriptor = json.loads((fixture_root / f"{role}.json").read_text(encoding="utf-8"))
    source_stream = bytes.fromhex(
        "".join((fixture_root / f"{role}.hex").read_text(encoding="ascii").split())
    )
    decoder = TargetFrameDecoder(max_stream_bytes=len(source_stream))
    frames = decoder.feed(source_stream)
    decoder.finish()
    encoded: list[bytes] = []
    for frame in frames[:-1]:
        payload = _json_thaw(frame.payload)
        assert isinstance(payload, dict)
        if frame.kind == 2:
            payload["run_id"] = run_id
        encoded.append(encode_frame(frame.kind, frame.sequence, payload))
    terminal = _json_thaw(frames[-1].payload)
    assert isinstance(terminal, dict)
    terminal["event_stream_digest"] = hashlib.sha256(b"".join(encoded)).hexdigest()
    encoded.append(encode_frame(frames[-1].kind, frames[-1].sequence, terminal))
    stream = b"".join(encoded)
    descriptor["stream"]["sha256"] = hashlib.sha256(stream).hexdigest()
    descriptor["stream"]["size_bytes"] = len(stream)
    descriptor["replay_id"] = calculate_replay_id(descriptor)
    root = tmp_path / "replay-inputs" / f"{role}-{run_id}"
    root.mkdir(parents=True)
    descriptor_path = root / "descriptor.json"
    stream_path = root / "stream.hex"
    descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor))
    stream_path.write_text(stream.hex(), encoding="ascii")
    return descriptor_path, stream_path


def _source_change(
    tmp_path: Path,
    evidence: EvidenceStore,
    before: object,
    after_identity: object,
    hypothesis_id: str,
) -> SourceChangeDeclaration:
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(b"--- a/App/main.c\n+++ b/App/main.c\n@@ -1 +1 @@\n-old\n+new\n")
    diff_artifact = evidence.ingest_file(
        diff_path, kind="source-diff", media_type="text/x-diff"
    )
    before_identity = before.manifest.identity
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-08-24T00:00:00.000000Z",
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
        changed_paths=("App/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )


def _complete_existing_chain(
    tmp_path: Path,
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    complete_verification: bool = True,
    cancelled: bool = False,
    failed_run_id: str = FAILED_RUN_ID,
    fixed_run_id: str = FIXED_RUN_ID,
    diagnostic_compact_id: str = "00000000000040008000000000000004",
    operation_prefix: str = "vs08a",
) -> tuple[Path, Path, str]:
    monkeypatch.setattr(
        diagnostic_workflows_module,
        "_session_id_factory",
        lambda: diagnostic_compact_id,
    )
    project_root = tmp_path / "project"
    project_root.mkdir(exist_ok=True)
    (project_root / ".stm32-project.json").write_bytes(
        json.dumps(_project_manifest(origin), sort_keys=True, separators=(",", ":")).encode()
    )
    data_root = tmp_path / "data"
    runtime_session_id = f"vs08a-{origin}-session"
    testing = TestContext(project_root, data_root, runtime_session_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, runtime_session_id)

    failed_descriptor, failed_stream = _canonical_replay_inputs(
        tmp_path, "failed-before", failed_run_id
    )
    fixed_descriptor, fixed_stream = _canonical_replay_inputs(
        tmp_path, "fixed-after", fixed_run_id
    )
    _ok(target_replay_run(testing, failed_run_id, failed_descriptor, failed_stream))
    started = _ok(
        diagnostic_start(
            diagnostic,
            operation_id=f"{operation_prefix}-diagnostic-start",
            failed_test_run_id=failed_run_id,
            failed_run_mode="target",
        )
    )
    session = started["session"]
    assert isinstance(session, Mapping)
    diagnostic_id = str(session["diagnostic_session_id"])
    _ok(
        diagnostic_begin(
            diagnostic,
            operation_id=f"{operation_prefix}-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id=f"{operation_prefix}-hypothesis-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=2,
            statement="the failed replay identifies the faulty behavior",
        )
    )["hypothesis"]
    assert isinstance(hypothesis, Mapping)
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = _ok(
        diagnostic_add_plan(
            diagnostic,
            operation_id=f"{operation_prefix}-observation-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "failed-run",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "confirm the failed replay",
                }
            ],
        )
    )["observation_plan"]
    assert isinstance(plan, Mapping)
    plan_id = str(plan["plan_id"])
    _ok(
        diagnostic_run_plan(
            diagnostic,
            operation_id=f"{operation_prefix}-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    _ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id=f"{operation_prefix}-hypothesis-assess",
            diagnostic_session_id=diagnostic_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="failed-run",
            polarity="supports",
            rationale="the failed replay supports the hypothesis",
        )
    )

    workspace = WorkspacePaths.from_roots(data_root, project_root, PROJECT_ID, runtime_session_id)
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before = RunRepository(evidence).load(failed_run_id)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = _source_change(
        tmp_path, evidence, before, fixed_fixture.descriptor.identity, hypothesis_id
    )
    _ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id=f"{operation_prefix}-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=declaration,
        )
    )
    _ok(target_replay_run(testing, fixed_run_id, fixed_descriptor, fixed_stream))
    after = RunRepository(evidence).load(fixed_run_id)
    monitor_before = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["failed-before"],
        MONITOR_FIXTURES / "failed-before.json",
    )
    monitor_after = ingest_monitor_replay(
        workspace,
        evidence,
        MONITOR_OPERATION_IDS["fixed-after"],
        MONITOR_FIXTURES / "fixed-after.json",
    )
    request = AnalysisRequest(
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
        request,
        diagnostic_id,
        hypothesis_id,
        "supports",
        "the fixed replay changed the observed counter",
        declaration,
    )
    export_analysis_bundle(
        workspace,
        evidence,
        request,
        publication,
        failed_run_id,
        fixed_run_id,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_id,
        failed_before_run_id=failed_run_id,
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=fixed_run_id,
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    _ok(
        diagnostic_add_verification_plan(
            diagnostic,
            operation_id=f"{operation_prefix}-verification-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=7,
            verification_plan=verification_plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            diagnostic,
            operation_id=f"{operation_prefix}-verification-start",
            diagnostic_session_id=diagnostic_id,
            expected_revision=8,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    _ok(
        diagnostic_attach_marker(
            diagnostic,
            operation_id=f"{operation_prefix}-marker-attach",
            diagnostic_session_id=diagnostic_id,
            expected_revision=9,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    if not complete_verification:
        return project_root, data_root, _wire_diagnostic_id(diagnostic_id)
    completed = _ok(
        diagnostic_complete_verification(
            diagnostic,
            operation_id=f"{operation_prefix}-verification-complete",
            diagnostic_session_id=diagnostic_id,
            expected_revision=10,
            executed_operation_ids=[
                failed_run_id,
                fixed_run_id,
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
            cancelled=cancelled,
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == ("CANCELLED" if cancelled else "PASSED")
    return project_root, data_root, _wire_diagnostic_id(diagnostic_id)


def _evidence_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _record(
    project_root: Path,
    data_root: Path,
    *,
    record_id: str = RECORD_ID,
    failed_run_id: str = FAILED_RUN_ID,
    fixed_run_id: str = FIXED_RUN_ID,
    diagnostic_id: str,
    scenario_id: str = "legacy-keil-migration",
) -> OperationResult[object]:
    return record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=record_id,
        scenario_id=scenario_id,
        scenario_version="1",
        failed_before_test_run_id=failed_run_id,
        fixed_after_test_run_id=fixed_run_id,
        diagnostic_session_id=diagnostic_id,
    )


def _publish_valid_physical_fixture(
    tmp_path: Path,
    project_root: Path,
    data_root: Path,
    run_id: str,
) -> None:
    """Create a valid stored physical publication through TestRunPublisher."""
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    replay = RunRepository(evidence).load(FAILED_RUN_ID)
    manifest = replace(replay.manifest, run_id=run_id, transport="mailbox")
    manifest_path = tmp_path / f"{run_id}-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = evidence.ingest_file(
        manifest_path, kind="test-manifest", media_type="application/json"
    )
    identity = manifest.identity
    digest = "a" * 64
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-physical",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, manifest.raw_events),
        metadata={
            "action_digest": digest,
            "execution_source": "physical",
            "flash_session_id": "flash-vs08a-fixture",
            "import_session_id": identity.session_id,
            "import_workspace_id": identity.workspace_id,
            "intent_digest": digest,
            "inventory_digest": "b" * 64,
            "lease_id": "lease-vs08a-fixture",
            "origin_session_id": identity.session_id,
            "origin_workspace_id": identity.workspace_id,
            "physical_transport_evidence": True,
            "probe_id": "d" * 64,
            "target_id": identity.target_device,
            "transport_config_digest": "c" * 64,
        },
    )
    evidence.put_envelope(envelope)
    RunPublisher(evidence, project_root, tmp_path / "physical-results").publish_target_physical(
        manifest, envelope
    )


@pytest.mark.parametrize("origin,scenario_id", [
    ("keil", "legacy-keil-migration"),
    ("cubemx", "new-cubemx-project"),
])
def test_vs08a_completed_software_chain_reloads_acceptance_record(
    tmp_path: Path, origin: str, scenario_id: str, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, origin, monkeypatch
    )
    gc.collect()
    context = AcceptanceWorkflowContext(project_root, data_root, f"vs08a-{origin}-session")
    result = record_acceptance_scenario(
        context,
        record_id=RECORD_ID,
        scenario_id=scenario_id,
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert result.ok is True, result.to_dict()
    record = result.data["record"]
    assert isinstance(record, Mapping)
    assert record["executionSource"] == "replay"
    assert record["physicalTransportEvidence"] is False
    assert record["verdict"] == "SOFTWARE_PASSED"
    shown = show_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, f"vs08a-{origin}-session"),
        record_id=RECORD_ID,
    )
    assert shown.ok is True, shown.to_dict()
    assert shown.data == {"authoritative": True, "record": record}


def test_vs08a_real_reader_idempotency_survives_advancing_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    ticks = iter(
        (
            "2026-08-24T00:00:00.000000Z",
            "2026-08-24T00:00:01.000000Z",
        )
    )
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: next(ticks))
    first = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert first.ok is True, first.to_dict()
    retry = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert retry.ok is True, retry.to_dict()
    assert retry.data == first.data


def test_vs08a_real_reader_conflict_preserves_existing_acceptance_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, first_diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    first = _record(project_root, data_root, diagnostic_id=first_diagnostic_id)
    assert first.ok is True, first.to_dict()
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    second_failed_id = "00000000-0000-4000-8000-000000000007"
    second_fixed_id = "00000000-0000-4000-8000-000000000008"
    _, _, second_diagnostic_id = _complete_existing_chain(
        tmp_path,
        "keil",
        monkeypatch,
        failed_run_id=second_failed_id,
        fixed_run_id=second_fixed_id,
        diagnostic_compact_id="00000000000040008000000000000005",
        operation_prefix="vs08a-alt",
    )
    before = _evidence_snapshot(evidence_root)
    conflict = _record(
        project_root,
        data_root,
        diagnostic_id=second_diagnostic_id,
        failed_run_id=second_failed_id,
        fixed_run_id=second_fixed_id,
    )
    assert conflict.ok is False
    assert conflict.code == "ACCEPTANCE_RECORD_CONFLICT"
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_real_physical_publication_is_rejected_without_acceptance_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    physical_run_id = "00000000-0000-4000-8000-000000000009"
    _publish_valid_physical_fixture(tmp_path, project_root, data_root, physical_run_id)
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = _record(
        project_root,
        data_root,
        diagnostic_id=diagnostic_id,
        failed_run_id=physical_run_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


@pytest.mark.parametrize(
    ("damage", "expected"),
    [
        ("missing", "ACCEPTANCE_REFERENCE_INVALID"),
        ("corrupt", "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"),
    ],
    ids=["missing-acceptance-root", "corrupt-acceptance-root"],
)
def test_vs08a_real_acceptance_show_distinguishes_missing_and_corrupt_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
    expected: str,
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    created = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert created.ok is True, created.to_dict()
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    acceptance_root = next(
        (evidence_root / "roots" / "acceptance-scenario").glob("*.json")
    )
    if damage == "missing":
        acceptance_root.unlink()
    else:
        acceptance_root.write_bytes(b"{}")
    before = _evidence_snapshot(evidence_root)
    shown = show_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=RECORD_ID,
    )
    assert shown.ok is False
    assert shown.code == expected
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_real_envelope_corruption_is_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    monkeypatch.setattr(
        acceptance_workflows,
        "_utc_now",
        lambda: "2026-08-24T00:00:00.000000Z",
    )
    created = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert created.ok is True, created.to_dict()
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    root_path = next(
        (evidence_root / "roots" / "acceptance-scenario").glob("*.json")
    )
    manifest_id = json.loads(root_path.read_bytes().decode("utf-8"))["manifest_id"]
    root_path.unlink()
    (evidence_root / "manifests" / f"{manifest_id}.json").write_bytes(b"{}")
    before = _evidence_snapshot(evidence_root)
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is False
    assert result.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_real_root_publication_corruption_is_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    raised = False

    def fail_before_root_publish(point: str):
        nonlocal raised
        if point == "gc-root.before_publish" and not raised:
            raised = True
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "root store corruption")

    monkeypatch.setattr(
        acceptance_workflows,
        "_evidence_store_factory",
        lambda _path: EvidenceStore(
            workspace.workspace_root / "evidence",
            fault_injector=fail_before_root_publish,
        ),
    )
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is False
    assert result.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    assert raised is True
    assert not list(
        (workspace.workspace_root / "evidence" / "roots" / "acceptance-scenario").glob(
            "*.json"
        )
    )


def test_vs08a_real_different_root_race_is_record_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    monkeypatch.setattr(
        acceptance_workflows,
        "_utc_now",
        lambda: "2026-08-24T00:00:00.000000Z",
    )
    created = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert created.ok is True, created.to_dict()
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    acceptance_root = next(
        (evidence.root / "roots" / "acceptance-scenario").glob("*.json")
    )
    root_document = json.loads(acceptance_root.read_bytes().decode("utf-8"))
    original_envelope = evidence.get_envelope(root_document["manifest_id"])
    alternate_data = dict(created.data["record"])
    alternate_data["completedStages"] = list(alternate_data["completedStages"])
    alternate_data["fixVerificationId"] = "e" * 64
    alternate_record = AcceptanceRecord.from_value(alternate_data)
    alternate_envelope = acceptance_workflows._acceptance_envelope(
        alternate_record,
        identity=original_envelope.identity,
        parents=original_envelope.parents,
    )
    evidence.put_envelope(alternate_envelope)
    alternate_root = RootRecord(
        "acceptance-scenario",
        RECORD_ID,
        str(alternate_envelope.evidence_id),
        acceptance_workflows._acceptance_root_metadata(alternate_record),
    )
    acceptance_root.unlink()
    raced = False
    target = acceptance_workflows._typed_root_path(
        evidence, "acceptance-scenario", RECORD_ID
    )

    def publish_different_root(point: str):
        nonlocal raced
        if point == "gc-root.before_publish" and not raced:
            raced = True
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical_json_bytes(alternate_root.to_dict()))

    monkeypatch.setattr(
        acceptance_workflows,
        "_evidence_store_factory",
        lambda _path: EvidenceStore(
            workspace.workspace_root / "evidence",
            fault_injector=publish_different_root,
        ),
    )
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is False
    assert result.code == "ACCEPTANCE_RECORD_CONFLICT"
    assert raced is True
    assert target.read_bytes() == canonical_json_bytes(alternate_root.to_dict())


def test_vs08a_real_identical_root_publication_race_reloads_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    raised = False

    def publish_then_raise(point: str):
        nonlocal raised
        if point == "gc-root.after_publish" and not raised:
            raised = True
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "identical root race")

    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    monkeypatch.setattr(
        acceptance_workflows,
        "_evidence_store_factory",
        lambda _path: EvidenceStore(
            workspace.workspace_root / "evidence",
            fault_injector=publish_then_raise,
        ),
    )
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is True, result.to_dict()
    assert raised is True


def test_vs08a_definition_origin_mismatch_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    before_acceptance_roots = tuple(
        sorted(
            path.relative_to(data_root).as_posix()
            for path in data_root.rglob("*")
            if path.is_file() and "acceptance-scenario" in path.parts
        )
    )
    result = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=RECORD_ID,
        scenario_id="new-cubemx-project",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_PROJECT_ORIGIN_MISMATCH"
    after_acceptance_roots = tuple(
        sorted(
            path.relative_to(data_root).as_posix()
            for path in data_root.rglob("*")
            if path.is_file() and "acceptance-scenario" in path.parts
        )
    )
    assert after_acceptance_roots == before_acceptance_roots == ()


def test_vs08a_real_reader_cross_workspace_reference_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    other_project_root = tmp_path / "other-workspace-project"
    other_project_root.mkdir()
    (other_project_root / ".stm32-project.json").write_bytes(
        (project_root / ".stm32-project.json").read_bytes()
    )
    source_workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    other_workspace = WorkspacePaths.from_roots(
        data_root, other_project_root, PROJECT_ID, "vs08a-keil-session"
    )
    shutil.copytree(
        source_workspace.workspace_root / "evidence",
        other_workspace.workspace_root / "evidence",
    )
    evidence_root = other_workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = _record(
        other_project_root,
        data_root,
        diagnostic_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_IDENTITY_MISMATCH"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_real_reader_cross_project_reference_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    other_project_id = UUID("87654321-4321-8765-4321-876543214321")
    other_project_root = tmp_path / "other-logical-project"
    other_project_root.mkdir()
    manifest = _project_manifest("keil")
    manifest["logicalProjectId"] = str(other_project_id)
    (other_project_root / ".stm32-project.json").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    )
    source_workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    other_workspace = WorkspacePaths.from_roots(
        data_root, other_project_root, other_project_id, "vs08a-keil-session"
    )
    shutil.copytree(
        source_workspace.workspace_root / "evidence",
        other_workspace.workspace_root / "evidence",
    )
    evidence_root = other_workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = _record(
        other_project_root,
        data_root,
        diagnostic_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_IDENTITY_MISMATCH"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


@pytest.mark.parametrize(
    ("wrong_side", "role", "wrong_run_id"),
    [
        ("before", "fixed-after", "00000000-0000-4000-8000-000000000007"),
        ("after", "failed-before", "00000000-0000-4000-8000-000000000008"),
    ],
    ids=["before-not-failed", "after-not-passed"],
)
def test_vs08a_real_reader_wrong_failed_fixed_state_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wrong_side: str,
    role: str,
    wrong_run_id: str,
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    descriptor, stream = _canonical_replay_inputs(tmp_path, role, wrong_run_id)
    testing = TestContext(project_root, data_root, "vs08a-keil-session")
    _ok(target_replay_run(testing, wrong_run_id, descriptor, stream))
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = _record(
        project_root,
        data_root,
        diagnostic_id=diagnostic_id,
        failed_run_id=wrong_run_id if wrong_side == "before" else FAILED_RUN_ID,
        fixed_run_id=FIXED_RUN_ID if wrong_side == "before" else wrong_run_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


@pytest.mark.parametrize(
    ("damage", "expected"),
    [("missing", "ACCEPTANCE_REFERENCE_INVALID"), ("corrupt", "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")],
    ids=["missing-public-root", "corrupt-public-root"],
)
def test_vs08a_real_test_show_distinguishes_missing_and_corrupt_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
    expected: str,
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    fixed_root = next(
        path
        for path in (evidence_root / "roots" / "test-run").glob("*.json")
        if json.loads(path.read_bytes().decode())["root_id"] == FIXED_RUN_ID
    )
    if damage == "missing":
        fixed_root.unlink()
    else:
        fixed_root.write_bytes(b"{}")
    before = _evidence_snapshot(evidence_root)
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is False
    assert result.code == expected
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_real_diagnostic_show_corruption_is_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    events = workspace.diagnostics_root / "sessions" / diagnostic_id.replace("-", "") / "events"
    latest = sorted(events.glob("*.json"))[-1]
    latest.write_bytes(b"not-json")
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = _record(project_root, data_root, diagnostic_id=diagnostic_id)
    assert result.ok is False
    assert result.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    assert not list((evidence_root / "roots" / "acceptance-scenario").glob("*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_unresolved_diagnostic_is_rejected_without_acceptance_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch, complete_verification=False
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_NOT_COMPLETE"
    assert not list((data_root).rglob("*/roots/acceptance-scenario/*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_nonpassing_verification_is_rejected_without_acceptance_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch, cancelled=True
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_NOT_COMPLETE"
    assert not list((data_root).rglob("*/roots/acceptance-scenario/*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_verification_bound_to_different_fixed_run_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_root, data_root, diagnostic_id = _complete_existing_chain(
        tmp_path, "keil", monkeypatch
    )
    alternate_descriptor, alternate_stream = _canonical_replay_inputs(
        tmp_path, "fixed-after", ALTERNATE_FIXED_RUN_ID
    )
    testing = TestContext(project_root, data_root, "vs08a-keil-session")
    assert _ok(
        target_replay_run(
            testing,
            ALTERNATE_FIXED_RUN_ID,
            alternate_descriptor,
            alternate_stream,
        )
    )
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, "vs08a-keil-session"
    )
    evidence_root = workspace.workspace_root / "evidence"
    before = _evidence_snapshot(evidence_root)
    result = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, "vs08a-keil-session"),
        record_id=RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=ALTERNATE_FIXED_RUN_ID,
        diagnostic_session_id=diagnostic_id,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID", result.to_dict()
    assert not list((data_root).rglob("*/roots/acceptance-scenario/*.json"))
    assert _evidence_snapshot(evidence_root) == before


def test_vs08a_scenario_contract_is_software_only():
    for origin, scenario_id in (
        ("keil", "legacy-keil-migration"),
        ("cubemx", "new-cubemx-project"),
    ):
        scenario = describe_scenario(scenario_id, "1")
        assert scenario.project_origin == origin
        assert scenario.execution_profile == "software-replay"
        assert scenario.physical_transport_evidence is False
