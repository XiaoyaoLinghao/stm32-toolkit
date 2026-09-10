from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.history import HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.replay import publish_physical_monitor_run
import test_vs08a_scenarios as vs08a_fixtures
from stm32_toolkit import __version__
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_STAGE_OUTPUT_KEYS,
    SourceChangeIntent,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
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
from stm32_toolkit.diagnostics import DiagnosticSession, SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunPublisher as _TestRunPublisher
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"
PROJECT_ID = "00000000-0000-4000-8000-000000000002"
WORKSPACE_ID = "a" * 64
TARGET = "STM32F429ZITx"

PHYSICAL_BEFORE_BUILD = "c6b3ea0b953c3d62d50db1bbf4226cd2ff3652ecc271a7a8b5e58913e084f2d0"
PHYSICAL_BEFORE_ELF = "13dbac824a8ef5ff8034860da48cc55243ab60673a539e73c366e59d40412880"
PHYSICAL_AFTER_BUILD = "65e2176034d1f74df3ab4ff1c6099938420ca6cb6367f76458f40ad4dee36ece"
PHYSICAL_AFTER_ELF = "2b2268ba7c6caa110688f872a4f4264ffdf2c75ceff9bc341d17c2eaedf106c0"
PHYSICAL_RAW_PROBE = "probe/t10/01"
PHYSICAL_PROBE = hashlib.sha256(PHYSICAL_RAW_PROBE.encode("utf-8")).hexdigest()
PHYSICAL_TRANSPORT_CONFIG = "c" * 64
PHYSICAL_FAILED_RUN = "target-v2-failed-t10"
PHYSICAL_FIXED_RUN = "target-v2-fixed-t10"


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


def _ok(result: object):
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return data


def _write_physical_project(project_root: Path) -> None:
    project_root.mkdir()
    manifest = vs08a_fixtures._project_manifest("keil")
    manifest["logicalProjectId"] = str(PROJECT_ID)
    manifest["target"]["device"] = "stm32:vs03-fixture"
    manifest["debug"]["target"] = "board:t10"
    manifest["generatedBy"]["version"] = __version__
    manifest_bytes = canonical_json_bytes(manifest)
    (project_root / ".stm32-project.json").write_bytes(manifest_bytes)
    (project_root / "App").mkdir()
    (project_root / "App" / "main.c").write_bytes(b"int main(void) { return 0; }\n")
    managed = {
        "schemaVersion": 1,
        "tool": "stm32-toolkit",
        "toolVersion": __version__,
        "templateVersion": 1,
        "projectManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "files": [],
    }
    managed_path = project_root / ".stm32-toolkit"
    managed_path.mkdir()
    (managed_path / "generated-files.json").write_bytes(canonical_json_bytes(managed))


def _publish_physical_from_seed(
    tmp_path: Path,
    project_root: Path,
    data_root: Path,
    session_id: str,
    seed_run_id: str,
    physical_run_id: str,
    identity: EvidenceIdentity,
) -> object:
    workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        UUID(identity.project_id),
        session_id,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    seed = TestRunRepository(evidence).load(seed_run_id)
    manifest = replace(
        seed.manifest,
        run_id=physical_run_id,
        identity=identity,
        transport="mailbox",
    )
    manifest_path = tmp_path / f"{physical_run_id}-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = evidence.ingest_file(
        manifest_path,
        kind="test-manifest",
        media_type="application/json",
    )
    action_digest = hashlib.sha256(physical_run_id.encode("utf-8")).hexdigest()
    inventory_digest = calculate_inventory_digest(
        "target", identity, tuple(case.case_id for case in manifest.cases)
    )
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-physical",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, manifest.raw_events),
        metadata={
            "action_digest": action_digest,
            "execution_source": "physical",
            "flash_session_id": f"flash-{physical_run_id}",
            "import_session_id": identity.session_id,
            "import_workspace_id": identity.workspace_id,
            "intent_digest": action_digest,
            "inventory_digest": inventory_digest,
            "lease_id": f"lease-{physical_run_id}",
            "origin_session_id": identity.session_id,
            "origin_workspace_id": identity.workspace_id,
            "physical_transport_evidence": True,
            "probe_id": PHYSICAL_PROBE,
            "target_id": identity.target_device,
            "transport_config_digest": PHYSICAL_TRANSPORT_CONFIG,
        },
    )
    evidence.put_envelope(envelope)
    return _TestRunPublisher(
        evidence,
        project_root,
        tmp_path / f"{physical_run_id}-results",
    ).publish_target_physical(manifest, envelope)


def _append_physical_monitor_history(
    workspace: WorkspacePaths,
    identity: EvidenceIdentity,
    raw_probe: str,
    flash_session_id: str,
    lease_id: str,
    run_id: str,
    *,
    value_offset: int,
) -> tuple[SampleBatch, ...]:
    """Create monitor history bound to the corresponding physical TestRun."""
    monitor_run_id = UUID(run_id)
    group_id = UUID("11111111-1111-4111-8111-111111111111")
    binding = ObservationBinding(
        workspace_id=identity.workspace_id,
        logical_project_id=identity.project_id,
        session_id=identity.session_id,
        probe_id=raw_probe,
        target_device=identity.target_device,
        physical_target="board:t10",
        build_id=identity.build_id,
        elf_sha256=identity.elf_sha256,
        input_snapshot_sha256=identity.input_snapshot_sha256,
        git_head=identity.git_commit,
        git_dirty=identity.git_dirty,
        flash_session_id=flash_session_id,
        lease_id=lease_id,
        dwarf_sha256="e" * 64,
        svd_sha256=None,
    )
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": sequence + value_offset},
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(workspace)
    try:
        appended = history.append_batches(batches)
        assert appended.ok, appended.to_dict()
    finally:
        history.close()
    return batches


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
        "_physical_build_data",
        lambda *_args: (
            {
                "buildId": "f" * 64,
                "elfSha256": "3" * 64,
                "inputSnapshotSha256": "4" * 64,
            },
            SimpleNamespace(sha256="4" * 64, entries=()),
        ),
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


def test_physical_build_authority_rejects_snapshot_mutated_after_fresh_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    model = SimpleNamespace(
        logical_project_id=UUID(PROJECT_ID),
        target_device=TARGET,
        build=SimpleNamespace(sources=("src/main.c",), assembly_sources=()),
    )
    context = AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a")
    facts = SimpleNamespace(
        build_id=PHYSICAL_BEFORE_BUILD,
        elf_sha256=PHYSICAL_BEFORE_ELF,
        input_snapshot_sha256="1" * 64,
    )
    monkeypatch.setattr(
        recovery_workflows, "_load_fresh_firmware_facts", lambda _root: facts
    )
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256="2" * 64, entries=()),
    )
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._physical_build_data(context, model)
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


def test_persisted_physical_recovery_chain_uses_real_authorities_and_is_cas_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exercise the complete v2 chain against the real stores and authorities."""

    project_root = tmp_path / "project"
    _write_physical_project(project_root)
    data_root = tmp_path / "data"
    session_id = "t10-physical-session"
    testing = TestingWorkflowContext(project_root, data_root, session_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, session_id)

    model = load_project_model(project_root)
    source_path = project_root / "App" / "main.c"
    before_source = source_path.read_bytes()
    before_snapshot = snapshot_project_inputs(model)
    after_source = b"int main(void) { return 1; }\n"
    source_path.write_bytes(after_source)
    after_snapshot = snapshot_project_inputs(load_project_model(project_root))
    source_path.write_bytes(before_source)
    before_source_sha256 = hashlib.sha256(before_source).hexdigest()
    after_source_sha256 = hashlib.sha256(after_source).hexdigest()

    workspace = WorkspacePaths.from_roots(
        data_root, project_root, UUID(PROJECT_ID), session_id
    )
    before_identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=PROJECT_ID,
        session_id=session_id,
        build_id=PHYSICAL_BEFORE_BUILD,
        elf_sha256=PHYSICAL_BEFORE_ELF,
        target_device=model.target.device,
        input_snapshot_sha256=before_snapshot.sha256,
        git_commit="b" * 40,
        git_dirty=False,
    )
    after_identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=PROJECT_ID,
        session_id=session_id,
        build_id=PHYSICAL_AFTER_BUILD,
        elf_sha256=PHYSICAL_AFTER_ELF,
        target_device=model.target.device,
        input_snapshot_sha256=after_snapshot.sha256,
        git_commit="c" * 40,
        git_dirty=False,
    )

    failed_descriptor, failed_stream = vs08a_fixtures._canonical_replay_inputs(
        tmp_path, "failed-before", "seed-failed-t10"
    )
    fixed_descriptor, fixed_stream = vs08a_fixtures._canonical_replay_inputs(
        tmp_path, "fixed-after", "seed-fixed-t10"
    )
    _ok(target_replay_run(testing, "seed-failed-t10", failed_descriptor, failed_stream))
    _ok(target_replay_run(testing, "seed-fixed-t10", fixed_descriptor, fixed_stream))
    failed_physical = _publish_physical_from_seed(
        tmp_path,
        project_root,
        data_root,
        session_id,
        "seed-failed-t10",
        PHYSICAL_FAILED_RUN,
        before_identity,
    )
    fixed_physical = _publish_physical_from_seed(
        tmp_path,
        project_root,
        data_root,
        session_id,
        "seed-fixed-t10",
        PHYSICAL_FIXED_RUN,
        after_identity,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    repository = TestRunRepository(evidence)
    assert repository.load(PHYSICAL_FAILED_RUN).envelope == failed_physical.envelope
    assert repository.load(PHYSICAL_FIXED_RUN).envelope == fixed_physical.envelope

    build_after = {"value": False}

    def fresh_firmware_facts(_project: Path):
        current_model = load_project_model(project_root)
        current_snapshot = snapshot_project_inputs(current_model)
        if build_after["value"]:
            build_id, elf_sha = PHYSICAL_AFTER_BUILD, PHYSICAL_AFTER_ELF
        else:
            build_id, elf_sha = PHYSICAL_BEFORE_BUILD, PHYSICAL_BEFORE_ELF
        return SimpleNamespace(
            model=current_model,
            elf_path="build/arm-debug/firmware.elf",
            elf_sha256=elf_sha,
            build_id=build_id,
            input_snapshot_sha256=current_snapshot.sha256,
            git_commit="b" * 40,
            git_dirty=False,
            target_device=current_model.target.device,
        )

    monkeypatch.setattr(
        recovery_workflows, "_load_fresh_firmware_facts", fresh_firmware_facts
    )
    monkeypatch.setattr(
        diagnostic_workflows,
        "_session_id_factory",
        lambda: "9" * 32,
    )

    started = _ok(
        diagnostic_start(
            diagnostic,
            operation_id="t10-physical-diagnostic-start",
            failed_test_run_id=PHYSICAL_FAILED_RUN,
            failed_run_mode="target",
        )
    )
    diagnostic_id = str(started["session"]["diagnostic_session_id"])
    _ok(
        diagnostic_begin(
            diagnostic,
            operation_id="t10-physical-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id="t10-physical-hypothesis-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=2,
            statement="the failed physical run identifies the faulty behavior",
        )
    )["hypothesis"]
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = _ok(
        diagnostic_add_plan(
            diagnostic,
            operation_id="t10-physical-observation-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "physical-failed-run",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "confirm the physical failure",
                }
            ],
        )
    )["observation_plan"]
    plan_id = str(plan["plan_id"])
    _ok(
        diagnostic_run_plan(
            diagnostic,
            operation_id="t10-physical-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    _ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="t10-physical-hypothesis-assess",
            diagnostic_session_id=diagnostic_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="physical-failed-run",
            polarity="supports",
            rationale="the failed physical run supports the hypothesis",
        )
    )

    recovery_clock = lambda: "2026-09-10T00:00:00.000000Z"
    context = AcceptanceRecoveryContext(
        project_root, data_root, session_id, clock=recovery_clock
    )
    _ok(
        begin_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            scenario_id="legacy-keil-physical-repair",
            scenario_version="1",
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=0,
            stage="project-materialized",
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=1,
            stage="firmware-built-before",
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=2,
            stage="target-failure-observed",
            test_run_id=PHYSICAL_FAILED_RUN,
        )
    )
    intent_input = {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "App/main.c",
                "beforeSha256": before_source_sha256,
                "afterSha256": after_source_sha256,
                "afterSize": len(after_source),
            }
        ],
    }
    diagnosis = _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=3,
            stage="diagnosis-completed",
            diagnostic_session_id=diagnostic_id,
            source_change_intent=intent_input,
        )
    )["attempt"]
    assert diagnosis["revision"] == 4
    assert diagnosis["sourceChangeIntent"]["beforeInputSnapshotSha256"] == before_snapshot.sha256
    assert diagnosis["sourceChangeIntent"]["expectedAfterInputSnapshotSha256"] == after_snapshot.sha256

    unauthorized_after_build = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        stage="firmware-built-after",
    )
    assert unauthorized_after_build.ok is False
    assert unauthorized_after_build.code == "ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED"

    resume = _ok(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    action_digest = str(resume["actionDigest"])
    rejected = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest="e" * 64,
        authorized=True,
    )
    assert rejected.ok is False
    assert rejected.code == "ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH"

    physical_locked_diagnostic_data = recovery_workflows._load_physical_diagnostic_locked

    def stale_locked_diagnostic_data(*args):
        # Inject a Diagnostic revision change in the old validation-to-publish
        # gap; the locked publication path must refuse rev5.
        current_session = physical_locked_diagnostic_data(*args)
        return replace(current_session, revision=current_session.revision + 1)

    monkeypatch.setattr(
        recovery_workflows, "_load_physical_diagnostic_locked", stale_locked_diagnostic_data
    )
    stale_diagnostic = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert stale_diagnostic.ok is False
    assert stale_diagnostic.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    monkeypatch.setattr(
        recovery_workflows, "_load_physical_diagnostic_locked", physical_locked_diagnostic_data
    )

    expired_context = AcceptanceRecoveryContext(
        project_root,
        data_root,
        session_id,
        clock=lambda: "2026-09-10T23:59:59.000000Z",
    )
    expired = authorize_acceptance_source_change(
        expired_context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert expired.ok is False
    assert expired.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"

    original_put_envelope_locked = EvidenceStore._put_envelope_locked
    boundary_mode = {"value": "source"}
    boundary_expired = {"value": False}

    def boundary_clock() -> str:
        return (
            "2026-09-10T23:59:59.000000Z"
            if boundary_expired["value"]
            else "2026-09-10T00:00:00.000000Z"
        )

    def inject_publication_boundary_change(store, envelope, *args, **kwargs):
        result = original_put_envelope_locked(store, envelope, *args, **kwargs)
        attempt_metadata = getattr(envelope, "metadata", {}).get("attempt")
        if (
            isinstance(attempt_metadata, Mapping)
            and attempt_metadata.get("revision") in {5, 6, 7}
        ):
            if attempt_metadata.get("revision") == 5 and boundary_mode["value"] == "source":
                source_path.write_bytes(after_source)
            elif attempt_metadata.get("revision") == 5 and boundary_mode["value"] == "expiry":
                boundary_expired["value"] = True
            elif attempt_metadata.get("revision") == 6 and boundary_mode["value"] == "after-build-source":
                source_path.write_bytes(b"int main(void) { return 2; }\n")
            elif (
                attempt_metadata.get("revision") in {6, 7}
                and boundary_mode["value"]
                == f"expiry-rev{attempt_metadata.get('revision')}"
            ):
                boundary_expired["value"] = True
        return result

    monkeypatch.setattr(
        EvidenceStore,
        "_put_envelope_locked",
        inject_publication_boundary_change,
    )
    boundary_context = AcceptanceRecoveryContext(
        project_root, data_root, session_id, clock=boundary_clock
    )
    source_changed_at_boundary = authorize_acceptance_source_change(
        boundary_context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert source_changed_at_boundary.ok is False
    assert source_changed_at_boundary.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert not recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 5)
    ).exists()

    source_path.write_bytes(before_source)
    boundary_mode["value"] = "expiry"
    expired_at_boundary = authorize_acceptance_source_change(
        boundary_context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert expired_at_boundary.ok is False
    assert expired_at_boundary.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    assert not recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 5)
    ).exists()
    boundary_expired["value"] = False
    boundary_mode["value"] = "none"

    race_contexts = [
        AcceptanceRecoveryContext(
            project_root, data_root, session_id, clock=recovery_clock
        )
        for _ in range(2)
    ]
    race_barrier = Barrier(2)

    def authorize_at_barrier(race_context: AcceptanceRecoveryContext):
        race_barrier.wait()
        return authorize_acceptance_source_change(
            race_context,
            attempt_id=ATTEMPT_ID,
            expected_revision=4,
            action_digest=action_digest,
            authorized=True,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced_authorizations = list(pool.map(authorize_at_barrier, race_contexts))
    assert all(result.ok for result in raced_authorizations), [
        result.to_dict() for result in raced_authorizations
    ]
    assert raced_authorizations[0].data == raced_authorizations[1].data
    authorized = _ok(raced_authorizations[0])["attempt"]
    assert authorized["revision"] == 5
    root5 = recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 5)
    )
    assert root5.exists()
    assert len(tuple(root5.parent.glob("*.json"))) == 6
    retry_authorized = _ok(
        authorize_acceptance_source_change(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=4,
            action_digest=action_digest,
            authorized=True,
        )
    )["attempt"]
    assert retry_authorized == authorized

    source_path.write_bytes(after_source)
    build_after["value"] = True
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(
        b"--- a/App/main.c\n+++ b/App/main.c\n@@ -1 +1 @@\n-int main(void) { return 0; }\n+int main(void) { return 1; }\n"
    )
    diff_artifact = evidence.ingest_file(
        diff_path, kind="source-diff", media_type="text/x-diff"
    )
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-09-10T00:00:00.000000Z",
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    declaration = SourceChangeDeclaration.new(
        before_source_sha256=before_snapshot.sha256,
        after_source_sha256=after_snapshot.sha256,
        before_build_id=PHYSICAL_BEFORE_BUILD,
        before_elf_sha256=PHYSICAL_BEFORE_ELF,
        after_build_id=PHYSICAL_AFTER_BUILD,
        after_elf_sha256=PHYSICAL_AFTER_ELF,
        changed_paths=("App/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )
    _ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id="t10-physical-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=declaration,
        )
    )

    project_manifest_path = project_root / ".stm32-project.json"
    manifest_before_extra = project_manifest_path.read_bytes()
    manifest_document = json.loads(manifest_before_extra.decode("utf-8"))
    manifest_document["project"]["name"] = "vs08a-keil-fixture-extra-input"
    project_manifest_path.write_bytes(canonical_json_bytes(manifest_document))
    extra_change = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    assert extra_change.ok is False, extra_change.to_dict()
    assert extra_change.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH", extra_change.to_dict()
    project_manifest_path.write_bytes(manifest_before_extra)

    boundary_mode["value"] = "after-build-source"
    mixed_after_build = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    assert mixed_after_build.ok is False
    assert mixed_after_build.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert not recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 6)
    ).exists()
    source_path.write_bytes(after_source)
    boundary_mode["value"] = "expiry-rev6"
    expired_rev6 = checkpoint_acceptance_attempt(
        boundary_context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    assert expired_rev6.ok is False
    assert expired_rev6.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT", expired_rev6.to_dict()
    assert not recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 6)
    ).exists()
    assert _ok(
        resume_acceptance_attempt(boundary_context, attempt_id=ATTEMPT_ID)
    )["attempt"]["revision"] == 5
    boundary_expired["value"] = False
    boundary_mode["value"] = "none"
    after_build = _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=5,
            stage="firmware-built-after",
        )
    )["attempt"]
    assert after_build["revision"] == 6

    failed_batches = _append_physical_monitor_history(
        workspace,
        before_identity,
        PHYSICAL_RAW_PROBE,
        f"flash-{PHYSICAL_FAILED_RUN}",
        f"lease-{PHYSICAL_FAILED_RUN}",
        vs08a_fixtures.MONITOR_OPERATION_IDS["failed-before"],
        value_offset=0,
    )
    fixed_batches = _append_physical_monitor_history(
        workspace,
        after_identity,
        PHYSICAL_RAW_PROBE,
        f"flash-{PHYSICAL_FIXED_RUN}",
        f"lease-{PHYSICAL_FIXED_RUN}",
        vs08a_fixtures.MONITOR_OPERATION_IDS["fixed-after"],
        value_offset=10,
    )
    monitor_before = publish_physical_monitor_run(
        workspace,
        evidence,
        scenario_role="failed-before",
        test_run_id=PHYSICAL_FAILED_RUN,
        run_id=vs08a_fixtures.MONITOR_OPERATION_IDS["failed-before"],
        group_id=str(failed_batches[0].group_id),
        start_sequence=failed_batches[0].sequence,
        end_sequence_exclusive=failed_batches[-1].sequence + 1,
        start_captured_unix_ns=failed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=failed_batches[-1].captured_unix_ns + 1,
        probe_id=PHYSICAL_RAW_PROBE,
    )
    monitor_after = publish_physical_monitor_run(
        workspace,
        evidence,
        scenario_role="fixed-after",
        test_run_id=PHYSICAL_FIXED_RUN,
        run_id=vs08a_fixtures.MONITOR_OPERATION_IDS["fixed-after"],
        group_id=str(fixed_batches[0].group_id),
        start_sequence=fixed_batches[0].sequence,
        end_sequence_exclusive=fixed_batches[-1].sequence + 1,
        start_captured_unix_ns=fixed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=fixed_batches[-1].captured_unix_ns + 1,
        probe_id=PHYSICAL_RAW_PROBE,
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
        PHYSICAL_FAILED_RUN,
        PHYSICAL_FIXED_RUN,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_id,
        failed_before_run_id=PHYSICAL_FAILED_RUN,
        failed_before_evidence_id=str(failed_physical.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=PHYSICAL_FIXED_RUN,
        fixed_after_evidence_id=str(fixed_physical.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    _ok(
        diagnostic_add_verification_plan(
            diagnostic,
            operation_id="t10-physical-verification-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=7,
            verification_plan=verification_plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            diagnostic,
            operation_id="t10-physical-verification-start",
            diagnostic_session_id=diagnostic_id,
            expected_revision=8,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    _ok(
        diagnostic_attach_marker(
            diagnostic,
            operation_id="t10-physical-marker-attach",
            diagnostic_session_id=diagnostic_id,
            expected_revision=9,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    completed = _ok(
        diagnostic_complete_verification(
            diagnostic,
            operation_id="t10-physical-verification-complete",
            diagnostic_session_id=diagnostic_id,
            expected_revision=10,
            executed_operation_ids=[
                PHYSICAL_FAILED_RUN,
                PHYSICAL_FIXED_RUN,
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
            cancelled=False,
        )
    )
    verification = completed["fix_verification"]
    assert verification["status"] == "PASSED"
    assert completed["session"]["state"] == "RESOLVED"

    boundary_mode["value"] = "expiry-rev7"
    expired_final = checkpoint_acceptance_attempt(
        boundary_context,
        attempt_id=ATTEMPT_ID,
        expected_revision=6,
        stage="target-fix-verified",
        test_run_id=PHYSICAL_FIXED_RUN,
        fix_verification_id=verification["fix_verification_id"],
    )
    assert expired_final.ok is False
    assert expired_final.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT", expired_final.to_dict()
    assert not recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, 7)
    ).exists()
    assert _ok(
        resume_acceptance_attempt(boundary_context, attempt_id=ATTEMPT_ID)
    )["attempt"]["revision"] == 6
    boundary_expired["value"] = False
    boundary_mode["value"] = "none"
    final = _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=6,
            stage="target-fix-verified",
            test_run_id=PHYSICAL_FIXED_RUN,
            fix_verification_id=verification["fix_verification_id"],
        )
    )["attempt"]
    assert final["revision"] == 7
    assert final["status"] == "COMPLETED"
    assert final["stageOutputs"]["fixedAfterTestRunId"] == PHYSICAL_FIXED_RUN
    assert final["stageOutputs"]["fixVerificationId"] == verification["fix_verification_id"]
    retried_final = _ok(
        checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=6,
            stage="target-fix-verified",
            test_run_id=PHYSICAL_FIXED_RUN,
            fix_verification_id=verification["fix_verification_id"],
        )
    )["attempt"]
    assert retried_final == final
