from __future__ import annotations

import json
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
from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import TestCaseResult as CaseResult, TestRunManifest as RunManifest
from stm32_toolkit.testing.publication import PublishedTestRun


_ORIGINAL_LOAD_DIAGNOSTIC_CHAIN = acceptance_workflows._load_diagnostic_chain
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
    *,
    physical: bool = False,
    project_id: UUID = _PROJECT_ID,
) -> PublishedTestRun:
    evidence.root.parent.mkdir(parents=True, exist_ok=True)
    identity = EvidenceIdentity(
        workspace_id=workspace_id,
        project_id=str(project_id),
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
        "stm32-test/1", run_id, "target", state, identity,
        "mailbox" if physical else "replay",
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
            "execution_source": "physical" if physical else "replay",
            "physical_transport_evidence": physical,
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
            "mode": "target", "state": state,
            "execution_source": "physical" if physical else "replay",
            "physical_transport_evidence": physical,
            "origin_workspace_id": workspace_id, "import_workspace_id": workspace_id,
        },
    )
    put_root(evidence, root)
    return PublishedTestRun(manifest, manifest_artifact, envelope, root)


def _fake_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    before_state: str = "failed",
    after_state: str = "passed",
    before_physical: bool = False,
    after_physical: bool = False,
    before_workspace_id: str | None = None,
    after_workspace_id: str | None = None,
    before_project_id: UUID = _PROJECT_ID,
    after_project_id: UUID = _PROJECT_ID,
    verification_ids: tuple[str, ...] = ("5" * 64,),
) -> SimpleNamespace:
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
    before = _published_run(
        evidence,
        before_workspace_id or workspace.workspace_id,
        _BEFORE_ID,
        before_state,
        "1" * 64,
        "2" * 64,
        physical=before_physical,
        project_id=before_project_id,
    )
    after = _published_run(
        evidence,
        after_workspace_id or workspace.workspace_id,
        _AFTER_ID,
        after_state,
        "3" * 64,
        "4" * 64,
        physical=after_physical,
        project_id=after_project_id,
    )
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

    monkeypatch.setattr(acceptance_workflows, "TestRunRepository", Repository)
    monkeypatch.setattr(
        acceptance_workflows,
        "test_show",
        lambda _context, *, run_id: OperationResult.success(
            "test.show",
            {_BEFORE_ID: before, _AFTER_ID: after}[run_id].public_data(authoritative=True),
        ),
    )
    verification_index = iter(verification_ids)

    def load_diagnostic_chain(*args, **kwargs):
        return (
            None,
            SimpleNamespace(fix_verification_id=next(verification_index)),
            diagnostic_root,
        )

    monkeypatch.setattr(acceptance_workflows, "_load_diagnostic_chain", load_diagnostic_chain)
    return SimpleNamespace(
        context=context,
        project_root=project_root,
        data_root=data_root,
        workspace=workspace,
        evidence=evidence,
        before=before,
        after=after,
        diagnostic_root=diagnostic_root,
    )


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
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"


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
    produced_at_ticks = iter(
        (
            "2026-08-24T00:00:00.000000Z",
            "2026-08-24T00:00:01.000000Z",
        )
    )
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: next(produced_at_ticks))

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


def _acceptance_bytes(evidence: EvidenceStore) -> dict[str, bytes]:
    root = evidence.root / "roots" / "acceptance-scenario"
    if not root.exists():
        return {}
    return {
        path.name: path.read_bytes()
        for path in root.glob("*.json")
        if path.is_file()
    }


def _evidence_snapshot(evidence: EvidenceStore) -> dict[str, bytes]:
    return {
        path.relative_to(evidence.root).as_posix(): path.read_bytes()
        for path in evidence.root.rglob("*")
        if path.is_file()
    }


def test_physical_replay_reference_is_rejected_without_acceptance_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path, before_physical=True)
    before = _evidence_snapshot(authority.evidence)
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN"
    assert _acceptance_bytes(authority.evidence) == {}
    assert _evidence_snapshot(authority.evidence) == before


def test_cross_workspace_reference_is_rejected_without_acceptance_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(
        monkeypatch,
        tmp_path,
        before_workspace_id="f" * 64,
    )
    before = _evidence_snapshot(authority.evidence)
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_IDENTITY_MISMATCH"
    assert _acceptance_bytes(authority.evidence) == {}
    assert _evidence_snapshot(authority.evidence) == before


def test_cross_project_reference_is_rejected_without_acceptance_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(
        monkeypatch,
        tmp_path,
        before_project_id=UUID("87654321-4321-8765-4321-876543214321"),
    )
    before = _evidence_snapshot(authority.evidence)
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_IDENTITY_MISMATCH"
    assert _acceptance_bytes(authority.evidence) == {}
    assert _evidence_snapshot(authority.evidence) == before


@pytest.mark.parametrize(
    ("before_state", "after_state"),
    [("passed", "passed"), ("failed", "failed")],
    ids=["before-not-failed", "after-not-passed"],
)
def test_wrong_failed_fixed_states_are_rejected_without_acceptance_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    before_state: str,
    after_state: str,
):
    authority = _fake_authority(
        monkeypatch,
        tmp_path,
        before_state=before_state,
        after_state=after_state,
    )
    before = _evidence_snapshot(authority.evidence)
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"
    assert _acceptance_bytes(authority.evidence) == {}
    assert _evidence_snapshot(authority.evidence) == before


def test_evidence_corrupt_root_publication_failure_is_typed_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)

    def raise_corrupt(*args, **kwargs):
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "root collision")

    monkeypatch.setattr(acceptance_workflows, "put_root", raise_corrupt)
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert isinstance(result, OperationResult)
    assert result.ok is False
    assert result.code == "ACCEPTANCE_RECORD_CONFLICT"


def test_existing_corrupt_acceptance_root_show_is_integrity_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: "2026-08-24T00:00:00.000000Z")
    created = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert created.ok is True
    roots = list((authority.evidence.root / "roots" / "acceptance-scenario").glob("*.json"))
    assert len(roots) == 1
    roots[0].write_bytes(b"{}")
    shown = show_acceptance_scenario(authority.context, record_id=_RECORD_ID)
    assert shown.ok is False
    assert shown.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"


def test_existing_wrong_kind_acceptance_root_show_is_reference_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: "2026-08-24T00:00:00.000000Z")
    created = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert created.ok is True
    root_path = next((authority.evidence.root / "roots" / "acceptance-scenario").glob("*.json"))
    root_document = json.loads(root_path.read_bytes().decode("utf-8"))
    root_document["root_type"] = "diagnostic-session"
    root_path.write_bytes(canonical_json_bytes(root_document))
    shown = show_acceptance_scenario(authority.context, record_id=_RECORD_ID)
    assert shown.ok is False
    assert shown.code == "ACCEPTANCE_REFERENCE_INVALID"


def test_same_record_id_conflict_preserves_existing_acceptance_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(
        monkeypatch,
        tmp_path,
        verification_ids=("5" * 64, "6" * 64),
    )
    ticks = iter(
        (
            "2026-08-24T00:00:00.000000Z",
            "2026-08-24T00:00:01.000000Z",
        )
    )
    monkeypatch.setattr(acceptance_workflows, "_utc_now", lambda: next(ticks))
    first = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert first.ok is True
    before = _acceptance_bytes(authority.evidence)
    conflict = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert conflict.ok is False
    assert conflict.code == "ACCEPTANCE_RECORD_CONFLICT"
    assert _acceptance_bytes(authority.evidence) == before


def test_existing_public_test_root_corruption_maps_to_integrity_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)
    monkeypatch.setattr(
        acceptance_workflows,
        "test_show",
        lambda _context, *, run_id: OperationResult.failure(
            "test.show", EVIDENCE_CORRUPT, "Evidence is corrupt.", {}
        ),
    )
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"


def test_missing_public_test_root_maps_to_reference_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)
    missing_run_id = "00000000-0000-4000-8000-000000000005"
    monkeypatch.setattr(
        acceptance_workflows,
        "test_show",
        lambda _context, *, run_id: OperationResult.failure(
            "test.show", EVIDENCE_CORRUPT, "Evidence is corrupt.", {}
        ),
    )
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=missing_run_id,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"


def test_wrong_kind_public_test_root_maps_to_reference_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    authority = _fake_authority(monkeypatch, tmp_path)
    root_path = next((authority.evidence.root / "roots" / "test-run").glob("*.json"))
    root_document = json.loads(root_path.read_bytes().decode("utf-8"))
    root_document["root_type"] = "diagnostic-session"
    root_path.write_bytes(canonical_json_bytes(root_document))
    monkeypatch.setattr(
        acceptance_workflows,
        "test_show",
        lambda _context, *, run_id: OperationResult.failure(
            "test.show", EVIDENCE_CORRUPT, "Evidence is corrupt.", {}
        ),
    )
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"


@pytest.mark.parametrize(
    ("reader", "reader_code", "expected"),
    [
        ("diagnostic_show", "DIAGNOSTIC_IDENTITY_MISMATCH", "ACCEPTANCE_IDENTITY_MISMATCH"),
        ("diagnostic_show", "DIAGNOSTIC_NOT_FOUND", "ACCEPTANCE_REFERENCE_INVALID"),
        ("diagnostic_show", "DIAGNOSTIC_CHAIN_CORRUPT", "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"),
    ],
    ids=["diagnostic-identity", "diagnostic-not-found", "diagnostic-chain-corrupt"],
)
def test_public_diagnostic_reader_failures_map_to_closed_acceptance_codes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reader: str,
    reader_code: str,
    expected: str,
):
    authority = _fake_authority(monkeypatch, tmp_path)
    monkeypatch.setattr(
        acceptance_workflows,
        "_load_diagnostic_chain",
        _ORIGINAL_LOAD_DIAGNOSTIC_CHAIN,
    )
    monkeypatch.setattr(
        acceptance_workflows,
        reader,
        lambda _context, *, diagnostic_session_id: OperationResult.failure(
            "diagnostic.show", reader_code, "diagnostic reader failure", {}
        ),
    )
    result = record_acceptance_scenario(
        authority.context,
        record_id=_RECORD_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=_BEFORE_ID,
        fixed_after_test_run_id=_AFTER_ID,
        diagnostic_session_id=_SESSION_ID,
    )
    assert result.ok is False
    assert result.code == expected
    assert _acceptance_bytes(authority.evidence) == {}
