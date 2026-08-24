from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_toolkit.acceptance.model import REQUIRED_STAGES
import stm32_toolkit.acceptance.workflows as acceptance_workflows
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    describe_acceptance_scenario,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import TestCaseResult as CaseResult, TestRunManifest as RunManifest
from stm32_toolkit.testing.publication import PublishedTestRun


_PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")
_RECORD_ID = "00000000-0000-4000-8000-000000000001"
_BEFORE_ID = "00000000-0000-4000-8000-000000000002"
_AFTER_ID = "00000000-0000-4000-8000-000000000003"
_SESSION_ID = "00000000-0000-4000-8000-000000000004"


def _published_run(
    evidence: EvidenceStore,
    workspace_id: str,
    run_id: str,
    state: str,
    build_id: str,
    elf_sha256: str,
) -> PublishedTestRun:
    evidence.root.parent.mkdir(parents=True, exist_ok=True)
    identity = EvidenceIdentity(
        workspace_id=workspace_id,
        project_id=str(_PROJECT_ID),
        session_id="session-a",
        build_id=build_id,
        elf_sha256=elf_sha256,
        target_device="stm32f429zgtx",
        input_snapshot_sha256=build_id,
        git_commit="a" * 40,
        git_dirty=False,
    )
    raw_path = evidence.root.parent / f"{run_id}.bin"
    raw_path.write_bytes(b"raw")
    raw = evidence.ingest_file(
        raw_path,
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    manifest = RunManifest(
        "stm32-test/1", run_id, "target", state, identity, "replay",
        (CaseResult(
            "case", "failed" if state == "failed" else "passed",
            "2026-08-24T00:00:00.000000Z", "2026-08-24T00:00:00.000000Z", 0,
            None, None, None,
        ),),
        "2026-08-24T00:00:00.000000Z", "2026-08-24T00:00:00.000000Z", 0,
        None, None, raw,
    )
    manifest_path = evidence.root.parent / f"{run_id}.json"
    manifest_path.write_bytes(b"manifest")
    manifest_artifact = evidence.ingest_file(
        manifest_path,
        kind="test-manifest",
        media_type="application/json",
    )
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-replay",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, raw),
        metadata={
            "execution_source": "replay",
            "physical_transport_evidence": False,
            "import_workspace_id": workspace_id,
            "origin_workspace_id": workspace_id,
            "test_run_id": run_id,
            "operation_id": run_id,
            "descriptor_evidence_id": "b" * 64,
            "operation_intent_sha256": "c" * 64,
            "test_manifest_sha256": manifest_artifact.sha256,
        },
    )
    evidence.put_envelope(envelope)
    root = RootRecord(
        "test-run", run_id, str(envelope.evidence_id),
        {
            "mode": "target", "state": state, "execution_source": "replay",
            "physical_transport_evidence": False,
            "origin_workspace_id": workspace_id, "import_workspace_id": workspace_id,
        },
    )
    return PublishedTestRun(manifest, manifest_artifact, envelope, root)


def test_describe_is_state_free_and_returns_the_fixed_definition(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    before = tuple(tmp_path.rglob("*"))
    result = describe_acceptance_scenario(context, scenario_id="legacy-keil-migration", scenario_version="1")
    assert result.ok is True
    assert result.operation == "acceptance.scenario.describe"
    assert tuple(result.data["scenario"]["requiredStages"]) == REQUIRED_STAGES
    assert tuple(tmp_path.rglob("*")) == before


@pytest.mark.parametrize(
    ("scenario_id", "scenario_version", "code"),
    [
        ("unknown", "1", "ACCEPTANCE_SCENARIO_UNKNOWN"),
        ("legacy-keil-migration", "2", "ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED"),
    ],
)
def test_describe_rejects_unknown_definition_without_state(
    tmp_path: Path, scenario_id: str, scenario_version: str, code: str
):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = describe_acceptance_scenario(
        context, scenario_id=scenario_id, scenario_version=scenario_version
    )
    assert result.ok is False
    assert result.code == code
    assert not (tmp_path / "data").exists()


def test_record_rejects_malformed_uuid_before_loading_project(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = record_acceptance_scenario(
        context,
        record_id="not-a-uuid",
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id="00000000-0000-4000-8000-000000000002",
        fixed_after_test_run_id="00000000-0000-4000-8000-000000000003",
        diagnostic_session_id="00000000-0000-4000-8000-000000000004",
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_INPUT_INVALID"


def test_show_missing_root_is_typed_and_does_not_create_state(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = show_acceptance_scenario(
        context, record_id="00000000-0000-4000-8000-000000000001"
    )
    assert result.ok is False
    assert result.code in {"ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED", "ACCEPTANCE_REFERENCE_INVALID"}


def test_completed_replay_chain_publishes_reloadable_immutable_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    data_root = tmp_path / "data"
    context = AcceptanceWorkflowContext(project_root, data_root, "session-a")
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=_PROJECT_ID,
        memory=SimpleNamespace(source="keil"),
    )
    monkeypatch.setattr(acceptance_workflows, "_load_project_model", lambda _root: model)
    workspace = acceptance_workflows.WorkspacePaths.from_roots(
        data_root, project_root, _PROJECT_ID, "session-a"
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before = _published_run(evidence, workspace.workspace_id, _BEFORE_ID, "failed", "1" * 64, "2" * 64)
    after = _published_run(evidence, workspace.workspace_id, _AFTER_ID, "passed", "3" * 64, "4" * 64)
    diagnostic_envelope = EvidenceEnvelope(
        identity=after.manifest.identity,
        operation="diagnostic-event",
        produced_at_utc="2026-08-24T00:00:00.000000Z",
        parents=(),
        artifacts=(),
        metadata={"diagnostic_session_id": "diagnostic", "revision": 1},
    )
    evidence.put_envelope(diagnostic_envelope)
    diagnostic_root = RootRecord(
        "diagnostic-session", "diagnostic", str(diagnostic_envelope.evidence_id),
        {"diagnostic_session_id": "diagnostic", "revision": 1},
    )

    class Repository:
        def __init__(self, _evidence):
            pass

        def load(self, run_id):
            return {_BEFORE_ID: before, _AFTER_ID: after}[run_id]

    verification = SimpleNamespace(
        fix_verification_id="5" * 64,
    )
    monkeypatch.setattr(acceptance_workflows, "TestRunRepository", Repository)
    monkeypatch.setattr(
        acceptance_workflows,
        "test_show",
        lambda _context, *, run_id: OperationResult.success(
            "test.show",
            {_BEFORE_ID: before, _AFTER_ID: after}[run_id].public_data(authoritative=True),
        ),
    )
    monkeypatch.setattr(
        acceptance_workflows,
        "_load_diagnostic_chain",
        lambda *args, **kwargs: (None, verification, diagnostic_root),
    )
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: "2026-08-24T00:00:00.000000Z")

    result = record_acceptance_scenario(
        context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is True, result.to_dict()
    assert result.data["record"]["executionSource"] == "replay"
    assert result.data["record"]["physicalTransportEvidence"] is False
    shown = show_acceptance_scenario(context, record_id=_RECORD_ID)
    assert shown.ok is True, shown.to_dict()
    assert shown.data == {"authoritative": True, "record": result.data["record"]}

    retry = record_acceptance_scenario(
        context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert retry.ok is True
    assert retry.data == result.data
