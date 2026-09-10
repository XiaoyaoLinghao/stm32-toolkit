from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_STAGE_OUTPUT_KEYS,
    SourceChangeIntent,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    checkpoint_acceptance_attempt,
)
from stm32_toolkit.evidence import EvidenceIdentity, canonical_json_bytes


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"
PROJECT_ID = "00000000-0000-4000-8000-000000000002"
WORKSPACE_ID = "a" * 64
TARGET = "STM32F429ZITx"


def _intent() -> SourceChangeIntent:
    return SourceChangeIntent.expanded(
        changes=[
            {
                "path": "src/main.c",
                "beforeSha256": "1" * 64,
                "afterSha256": "2" * 64,
                "afterSize": 20,
            }
        ],
        before_input_snapshot_sha256="3" * 64,
        expected_after_input_snapshot_sha256="4" * 64,
    )


def _physical_pair(
    *,
    session_id: str = "session-a",
    probe_id: str = "5" * 64,
    transport: str = "mailbox",
    transport_config_digest: str = "a" * 64,
):
    identity = EvidenceIdentity(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        session_id=session_id,
        build_id="6" * 64,
        elf_sha256="7" * 64,
        target_device=TARGET,
        input_snapshot_sha256="8" * 64,
        git_commit="9" * 40,
        git_dirty=False,
    )
    metadata = {
        "probe_id": probe_id,
        "target_id": TARGET,
        "transport_config_digest": transport_config_digest,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }
    def published():
        return SimpleNamespace(
            manifest=SimpleNamespace(identity=identity, transport=transport),
            envelope=SimpleNamespace(metadata=dict(metadata)),
        )
    return published(), published()


def test_physical_pair_requires_probe_target_transport_and_identity_session_match():
    before, after = _physical_pair()
    assert diagnostic_workflows._validate_pair_execution_policy(before, after) == (
        "physical",
        True,
    )

    changed_build = replace(
        after.manifest.identity,
        build_id="b" * 64,
        elf_sha256="c" * 64,
    )
    after.manifest = SimpleNamespace(identity=changed_build, transport="mailbox")
    assert diagnostic_workflows._validate_pair_execution_policy(before, after) == (
        "physical",
        True,
    )

    after.envelope.metadata["probe_id"] = "d" * 64
    with pytest.raises(diagnostic_workflows._WorkflowFailure) as probe_error:
        diagnostic_workflows._validate_pair_execution_policy(before, after)
    assert probe_error.value.code == "INCOMPATIBLE_IDENTITY"

    before, after = _physical_pair()
    after.manifest = SimpleNamespace(
        identity=replace(after.manifest.identity, session_id="other-session"),
        transport="mailbox",
    )
    with pytest.raises(diagnostic_workflows._WorkflowFailure) as session_error:
        diagnostic_workflows._validate_pair_execution_policy(before, after)
    assert session_error.value.code == "INCOMPATIBLE_IDENTITY"


def test_physical_pair_binds_mailbox_config_but_allows_transport_specific_digests():
    before, after = _physical_pair()
    after.envelope.metadata["transport_config_digest"] = "b" * 64
    with pytest.raises(diagnostic_workflows._WorkflowFailure) as mailbox_error:
        diagnostic_workflows._validate_pair_execution_policy(before, after)
    assert mailbox_error.value.code == "INCOMPATIBLE_IDENTITY"

    for transport in ("rtt", "semihosting"):
        before, after = _physical_pair(transport=transport)
        after.manifest = SimpleNamespace(
            identity=replace(
                after.manifest.identity,
                build_id="b" * 64,
                elf_sha256="c" * 64,
            ),
            transport=transport,
        )
        after.envelope.metadata["transport_config_digest"] = "d" * 64
        assert diagnostic_workflows._validate_pair_execution_policy(before, after) == (
            "physical",
            True,
        )


def test_physical_loader_rejects_replay_publication_without_reinterpreting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    replay = SimpleNamespace(
        manifest=SimpleNamespace(
            run_id="target-v2-replay",
            mode="target",
            state="failed",
            transport="replay",
            identity=SimpleNamespace(
                project_id=PROJECT_ID,
                workspace_id=WORKSPACE_ID,
                session_id="session-a",
                target_device=TARGET,
            ),
        ),
        envelope=SimpleNamespace(
            operation="target-test-replay",
            metadata={"execution_source": "replay", "physical_transport_evidence": False},
            evidence_id="e" * 64,
        ),
        root=SimpleNamespace(
            manifest_id="e" * 64,
            metadata={"physical_transport_evidence": False},
        ),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_evidence_store_factory",
        lambda _root: object(),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "TestRunRepository",
        lambda _store: SimpleNamespace(load=lambda _run_id: replay),
    )
    model = SimpleNamespace(logical_project_id=UUID(PROJECT_ID), target_device=TARGET)
    workspace = SimpleNamespace(workspace_id=WORKSPACE_ID, workspace_root=tmp_path)
    context = AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a")
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._load_physical_test_run(
            context,
            model,
            workspace,
            "target-v2-replay",
            expected_state="failed",
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"


def test_native_target_run_id_round_trips_in_physical_outputs():
    outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    outputs.update(
        {
            "projectModelDigest": "1" * 64,
            "beforeBuildId": "2" * 64,
            "beforeElfSha256": "3" * 64,
            "beforeInputSnapshotSha256": "4" * 64,
            "failedBeforeTestRunId": "target-v2-failed-20260910",
            "failedBeforeEvidenceId": "5" * 64,
        }
    )
    attempt = recovery_workflows._physical_base_snapshot(
        attempt_id=ATTEMPT_ID,
        opened_at="2026-09-10T00:00:00.000000Z",
        updated_at="2026-09-10T00:00:00.000000Z",
        workspace_id=WORKSPACE_ID,
        logical_project_id=PROJECT_ID,
        revision=3,
        previous_checkpoint_id="6" * 64,
        outputs=outputs,
        deadline_at="2026-09-10T00:05:00.000000Z",
    )
    decoded = recovery_workflows.PhysicalAcceptanceAttempt.from_value(attempt.to_dict())
    assert decoded.stage_outputs["failedBeforeTestRunId"] == "target-v2-failed-20260910"
    assert decoded.physical_transport_evidence is True


def test_source_intent_uses_the_complete_before_snapshot_and_rejects_undeclared_paths():
    model = SimpleNamespace(
        build=SimpleNamespace(sources=("src/main.c",), assembly_sources=()),
    )
    entries = (
        SimpleNamespace(path=".stm32-project.json", size=2, sha256="a" * 64),
        SimpleNamespace(path="src/main.c", size=10, sha256="b" * 64),
    )
    before_payload = [
        {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
        for entry in entries
    ]
    before_hash = hashlib.sha256(canonical_json_bytes(before_payload)).hexdigest()
    replacement = SourceChangeIntent.new(
        changes=[
            {
                "path": "src/main.c",
                "beforeSha256": "b" * 64,
                "afterSha256": "c" * 64,
                "afterSize": 11,
            }
        ]
    )
    snapshot = SimpleNamespace(entries=entries, sha256=before_hash)
    expanded = recovery_workflows._derive_physical_intent(
        model, replacement, snapshot, expected_before_hash=before_hash
    )
    expected_after = hashlib.sha256(
        canonical_json_bytes(
            [
                {"path": ".stm32-project.json", "size": 2, "sha256": "a" * 64},
                {"path": "src/main.c", "size": 11, "sha256": "c" * 64},
            ]
        )
    ).hexdigest()
    assert expanded.expected_after_input_snapshot_sha256 == expected_after

    undeclared = SourceChangeIntent.new(
        changes=[
            {
                "path": "src/other.c",
                "beforeSha256": "b" * 64,
                "afterSha256": "d" * 64,
                "afterSize": 1,
            }
        ]
    )
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._derive_physical_intent(
            model, undeclared, snapshot, expected_before_hash=before_hash
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"


def test_source_declaration_paths_must_equal_the_approved_intent():
    outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    outputs.update(
        {
            "projectModelDigest": "1" * 64,
            "beforeBuildId": "2" * 64,
            "beforeElfSha256": "3" * 64,
            "beforeInputSnapshotSha256": "3" * 64,
            "failedBeforeTestRunId": "target-v2-failed",
            "failedBeforeEvidenceId": "5" * 64,
            "diagnosticSessionId": "0" * 32,
            "diagnosticRevision": 4,
            "diagnosticEventHead": "4" * 64,
        }
    )
    attempt = recovery_workflows._physical_base_snapshot(
        attempt_id=ATTEMPT_ID,
        opened_at="2026-09-10T00:00:00.000000Z",
        updated_at="2026-09-10T00:00:00.000000Z",
        workspace_id=WORKSPACE_ID,
        logical_project_id=PROJECT_ID,
        revision=4,
        previous_checkpoint_id="5" * 64,
        outputs=outputs,
        intent=_intent(),
        deadline_at="2026-09-10T00:15:00.000000Z",
    )
    declaration = SimpleNamespace(
        before_source_sha256="3" * 64,
        before_build_id="2" * 64,
        before_elf_sha256="3" * 64,
        after_source_sha256="4" * 64,
        after_build_id="6" * 64,
        after_elf_sha256="7" * 64,
        changed_paths=("src/main.c", "src/extra.c"),
    )
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._physical_validate_declaration(
            declaration,
            attempt,
            _intent(),
            after_build={
                "inputSnapshotSha256": "4" * 64,
                "buildId": "6" * 64,
                "elfSha256": "7" * 64,
            },
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


def test_diagnosis_rechecks_the_fresh_before_build_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    outputs.update(
        {
            "projectModelDigest": "1" * 64,
            "beforeBuildId": "2" * 64,
            "beforeElfSha256": "3" * 64,
            "beforeInputSnapshotSha256": "4" * 64,
            "failedBeforeTestRunId": "target-v2-failed",
            "failedBeforeEvidenceId": "5" * 64,
        }
    )
    attempt = recovery_workflows._physical_base_snapshot(
        attempt_id=ATTEMPT_ID,
        opened_at="2026-09-10T00:00:00.000000Z",
        updated_at="2026-09-10T00:00:00.000000Z",
        workspace_id=WORKSPACE_ID,
        logical_project_id=PROJECT_ID,
        revision=3,
        previous_checkpoint_id="6" * 64,
        outputs=outputs,
        deadline_at="2026-09-10T00:05:00.000000Z",
    )
    model = SimpleNamespace(
        logical_project_id=UUID(PROJECT_ID),
        target_device=TARGET,
        build=SimpleNamespace(sources=("src/main.c",), assembly_sources=()),
    )
    workspace = SimpleNamespace(workspace_id=WORKSPACE_ID, workspace_root=tmp_path)
    context = AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a")
    session = SimpleNamespace(
        diagnostic_session_id="9" * 32,
        failed_test_run_id="target-v2-failed",
        failed_evidence_id="5" * 64,
        failed_run_mode="target",
        state="INVESTIGATING",
        identity=SimpleNamespace(
            project_id=PROJECT_ID,
            workspace_id=WORKSPACE_ID,
            session_id="session-a",
            target_device=TARGET,
            build_id="2" * 64,
            elf_sha256="3" * 64,
            input_snapshot_sha256="4" * 64,
        ),
        source_change_declarations=(),
        revision=1,
        event_head="a" * 64,
    )
    monkeypatch.setattr(recovery_workflows, "_physical_diagnostic_data", lambda *_args: session)
    monkeypatch.setattr(
        recovery_workflows,
        "_build_data",
        lambda *_args: {
            "buildId": "f" * 64,
            "elfSha256": "3" * 64,
            "inputSnapshotSha256": "4" * 64,
        },
    )
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._physical_build_transition(
            context,
            model,
            workspace,
            attempt,
            "diagnosis-completed",
            test_run_id=None,
            diagnostic_session_id="9" * 32,
            fix_verification_id=None,
            source_change_intent={
                "schema": "stm32-source-change-intent/1",
                "changes": [{
                    "path": "src/main.c",
                    "beforeSha256": "b" * 64,
                    "afterSha256": "c" * 64,
                    "afterSize": 12,
                }],
            },
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


def test_v1_attempt_rejects_physical_stage_and_physical_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    monkeypatch.setattr(
        recovery_workflows,
        "_load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID(PROJECT_ID),
            memory=SimpleNamespace(source="keil"),
            target_device=TARGET,
        ),
    )
    context = AcceptanceRecoveryContext(project, data, "session-a")
    started = recovery_workflows.begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert started.ok
    physical_stage = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="target-failure-observed",
        test_run_id="target-v2-failed",
    )
    assert physical_stage.code == "ACCEPTANCE_ATTEMPT_STAGE_INVALID"

    expanded = _intent()
    physical_input = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="diagnosis-completed",
        diagnostic_session_id="0" * 32,
        source_change_intent=expanded.to_dict(),
    )
    assert physical_input.code == "ACCEPTANCE_ATTEMPT_STAGE_INVALID"


def test_existing_physical_attempt_dispatches_plain_build_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    monkeypatch.setattr(
        recovery_workflows,
        "_attempt_schema_for_context",
        lambda _context, _attempt_id: PHYSICAL_ATTEMPT_SCHEMA,
    )

    def physical_checkpoint(_context, **_kwargs):
        calls.append("physical")
        return recovery_workflows.OperationResult.success(
            "acceptance.attempt.checkpoint", {"attempt": {}}
        )

    monkeypatch.setattr(recovery_workflows, "_checkpoint_physical_attempt", physical_checkpoint)
    monkeypatch.setattr(
        recovery_workflows,
        "_checkpoint_attempt",
        lambda *_args, **_kwargs: calls.append("v1"),
    )

    result = checkpoint_acceptance_attempt(
        AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a"),
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert result.ok
    assert calls == ["physical"]
