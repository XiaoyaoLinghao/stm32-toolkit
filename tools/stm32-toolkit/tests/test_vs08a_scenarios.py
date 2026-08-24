from __future__ import annotations

import gc
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.replay import ingest_monitor_replay
from stm32_toolkit.acceptance.model import describe_scenario
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    record_acceptance_scenario,
    show_acceptance_scenario,
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
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows_module
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository as RunRepository
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
    root = tmp_path / "replay-inputs" / role
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
    tmp_path: Path, origin: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    monkeypatch.setattr(
        diagnostic_workflows_module,
        "_session_id_factory",
        lambda: "00000000000040008000000000000004",
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".stm32-project.json").write_bytes(
        json.dumps(_project_manifest(origin), sort_keys=True, separators=(",", ":")).encode()
    )
    data_root = tmp_path / "data"
    runtime_session_id = f"vs08a-{origin}-session"
    testing = TestContext(project_root, data_root, runtime_session_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, runtime_session_id)

    failed_descriptor, failed_stream = _canonical_replay_inputs(
        tmp_path, "failed-before", FAILED_RUN_ID
    )
    fixed_descriptor, fixed_stream = _canonical_replay_inputs(
        tmp_path, "fixed-after", FIXED_RUN_ID
    )
    _ok(target_replay_run(testing, FAILED_RUN_ID, failed_descriptor, failed_stream))
    started = _ok(
        diagnostic_start(
            diagnostic,
            operation_id="vs08a-diagnostic-start",
            failed_test_run_id=FAILED_RUN_ID,
            failed_run_mode="target",
        )
    )
    session = started["session"]
    assert isinstance(session, Mapping)
    diagnostic_id = str(session["diagnostic_session_id"])
    _ok(
        diagnostic_begin(
            diagnostic,
            operation_id="vs08a-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id="vs08a-hypothesis-add",
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
            operation_id="vs08a-observation-plan-add",
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
            operation_id="vs08a-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    _ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="vs08a-hypothesis-assess",
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
    before = RunRepository(evidence).load(FAILED_RUN_ID)
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = _source_change(
        tmp_path, evidence, before, fixed_fixture.descriptor.identity, hypothesis_id
    )
    _ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id="vs08a-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=declaration,
        )
    )
    _ok(target_replay_run(testing, FIXED_RUN_ID, fixed_descriptor, fixed_stream))
    after = RunRepository(evidence).load(FIXED_RUN_ID)
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
        FAILED_RUN_ID,
        FIXED_RUN_ID,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_id,
        failed_before_run_id=FAILED_RUN_ID,
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=FIXED_RUN_ID,
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    _ok(
        diagnostic_add_verification_plan(
            diagnostic,
            operation_id="vs08a-verification-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=7,
            verification_plan=verification_plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            diagnostic,
            operation_id="vs08a-verification-start",
            diagnostic_session_id=diagnostic_id,
            expected_revision=8,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    _ok(
        diagnostic_attach_marker(
            diagnostic,
            operation_id="vs08a-marker-attach",
            diagnostic_session_id=diagnostic_id,
            expected_revision=9,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    completed = _ok(
        diagnostic_complete_verification(
            diagnostic,
            operation_id="vs08a-verification-complete",
            diagnostic_session_id=diagnostic_id,
            expected_revision=10,
            executed_operation_ids=[
                FAILED_RUN_ID,
                FIXED_RUN_ID,
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == "PASSED"
    return project_root, data_root, _wire_diagnostic_id(diagnostic_id)


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


def test_vs08a_scenario_contract_is_software_only():
    for origin, scenario_id in (
        ("keil", "legacy-keil-migration"),
        ("cubemx", "new-cubemx-project"),
    ):
        scenario = describe_scenario(scenario_id, "1")
        assert scenario.project_origin == origin
        assert scenario.execution_profile == "software-replay"
        assert scenario.physical_transport_evidence is False
