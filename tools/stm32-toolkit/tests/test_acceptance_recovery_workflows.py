from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    _base_snapshot,
    _validate_diagnostic_session,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
from stm32_toolkit.evidence import EvidenceIdentity


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def test_begin_publishes_revision_zero_and_retry_returns_the_same_snapshot(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        "stm32_toolkit.acceptance.recovery_workflows._load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    context = AcceptanceRecoveryContext(project, data, "session-a")
    first = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert first.ok is True
    assert first.data["attempt"]["revision"] == 0
    second = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert second.ok is True
    assert second.data["attempt"] == first.data["attempt"]
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == first.data["attempt"]
    assert resumed.data["nextStage"] == "project-materialized"
    assert resumed.data["authorizationRequired"] is False


def test_identical_checkpoint_retry_returns_the_published_snapshot(
    tmp_path: Path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        "stm32_toolkit.acceptance.recovery_workflows._load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    context = AcceptanceRecoveryContext(project, tmp_path / "data", "session-a")
    assert begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    ).ok
    first = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert first.ok is True
    assert retry.ok is True
    assert retry.data == first.data


def test_distinct_stale_checkpoint_request_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1"
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized"
    ).ok
    stale = checkpoint_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="firmware-built-before"
    )
    assert stale.code == "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT"


def _project_transition_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        recovery_workflows,
        "_load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_build_project_context",
        lambda *_args: recovery_workflows.OperationResult.success(
            "project.context",
            {"build": {"elfFresh": True, "preset": "arm-debug", "buildId": "b" * 64, "elfSha256": "e" * 64}},
        ),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256="d" * 64),
    )
    return project, data, AcceptanceRecoveryContext(project, data, "session-a", clock=clock)


def test_checkpoint_at_exact_deadline_is_not_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    now = ["2026-08-24T00:00:00.000000Z"]
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: now[0])
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    now[0] = "2026-08-24T00:01:00.000000Z"
    result = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert result.ok is True, result.to_dict()


def test_chain_gap_and_corrupt_root_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    assert checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized").ok
    workspace = recovery_workflows._workspace_paths_factory(data, project, "00000000-0000-4000-8000-000000000002", "session-a")
    evidence = recovery_workflows._evidence_store_factory(workspace.workspace_root / "evidence")
    recovery_workflows._typed_root_path(evidence, recovery_workflows._root_id(ATTEMPT_ID, 0)).write_bytes(b"{}")
    assert resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID).code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def test_orphan_envelope_can_be_retried_to_publish_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    original = recovery_workflows._publish_root_locked
    calls = [0]
    def fail_once(evidence, root):
        if calls[0] == 0:
            calls[0] += 1
            raise OSError("simulated orphan root")
        return original(evidence, root)
    monkeypatch.setattr(recovery_workflows, "_publish_root_locked", fail_once)
    first = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert first.ok is False
    monkeypatch.setattr(recovery_workflows, "_publish_root_locked", original)
    retry = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert retry.ok is True, retry.to_dict()


def test_copied_workspace_root_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_a, data_a, context_a = _project_transition_context(tmp_path / "a", monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context_a, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    workspace_a = recovery_workflows._workspace_paths_factory(data_a, project_a, "00000000-0000-4000-8000-000000000002", "session-a")
    project_b = tmp_path / "b" / "project"
    data_b = tmp_path / "b" / "data"
    project_b.mkdir(parents=True)
    data_b.mkdir(parents=True)
    project_b_context = AcceptanceRecoveryContext(project_b, data_b, "session-b", clock=lambda: "2026-08-24T00:00:00.000000Z")
    monkeypatch.setattr(recovery_workflows, "_load_project_model", lambda _root: SimpleNamespace(schema_version=3, logical_project_id=UUID("00000000-0000-4000-8000-000000000002"), memory=SimpleNamespace(source="keil"), target_device="STM32F429ZITx"))
    workspace_b = recovery_workflows._workspace_paths_factory(data_b, project_b, "00000000-0000-4000-8000-000000000002", "session-b")
    shutil.copytree(workspace_a.workspace_root / "evidence", workspace_b.workspace_root / "evidence")
    result = resume_acceptance_attempt(project_b_context, attempt_id=ATTEMPT_ID)
    assert result.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def test_one_workspace_has_one_published_checkpoint_winner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    contexts = [AcceptanceRecoveryContext(project, data, "session-a", clock=lambda: "2026-08-24T00:00:00.000000Z") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: checkpoint_acceptance_attempt(item, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized"), contexts))
    assert all(result.ok for result in results), [result.to_dict() for result in results]
    assert results[0].data == results[1].data


@pytest.mark.parametrize(
    "field",
    ["diagnostic_session_id", "workspace_id", "project_id", "target_device", "build_id", "elf_sha256", "input_snapshot_sha256"],
)
def test_diagnostic_lineage_mismatch_fails_closed(field: str, tmp_path: Path):
    model = SimpleNamespace(
        logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
        target_device="STM32F429ZITx",
    )
    workspace = SimpleNamespace(workspace_id="a" * 64)
    attempt = _base_snapshot(
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        scenario_digest="e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        workspace_id=workspace.workspace_id,
        logical_project_id=str(model.logical_project_id),
        project_origin="keil",
        opened_at="2026-08-24T00:00:00.000000Z",
        updated_at="2026-08-24T00:00:00.000000Z",
        revision=4,
        previous_checkpoint_id="a" * 64,
        outputs={
            "projectModelDigest": "c" * 64,
            "beforeBuildId": "b" * 64,
            "beforeElfSha256": "e" * 64,
            "beforeInputSnapshotSha256": "d" * 64,
            "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000003",
            "failedBeforeEvidenceId": "f" * 64,
            "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
            "diagnosticRevision": 6,
            "diagnosticEventHead": "1" * 64,
            "afterBuildId": None,
            "afterElfSha256": None,
            "afterInputSnapshotSha256": None,
            "sourceChangeDeclarationId": None,
            "acceptanceRecordId": None,
        },
        deadline_at="2026-08-24T00:15:00.000000Z",
    )
    identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=str(model.logical_project_id),
        session_id="session-a",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        target_device=model.target_device,
        input_snapshot_sha256="d" * 64,
        git_commit="0" * 40,
        git_dirty=False,
    )
    session = SimpleNamespace(
        diagnostic_session_id="00000000000040008000000000000004",
        failed_test_run_id="00000000-0000-4000-8000-000000000003",
        failed_evidence_id="f" * 64,
        event_head="1" * 64,
        identity=identity,
        state="INVESTIGATING",
        source_change_declarations=(),
    )
    if field == "diagnostic_session_id":
        session.diagnostic_session_id = "00000000000040008000000000000005"
    elif field == "workspace_id":
        session.identity = replace(identity, workspace_id="2" * 64)
    elif field == "project_id":
        session.identity = replace(identity, project_id="00000000-0000-4000-8000-000000000005")
    else:
        session.identity = replace(identity, **{field: "2" * 64 if field != "target_device" else "other-target"})
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        _validate_diagnostic_session(
            session,
            attempt,
            model,
            workspace,
            expected_session_id="00000000000040008000000000000004",
            allow_source_change=False,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
