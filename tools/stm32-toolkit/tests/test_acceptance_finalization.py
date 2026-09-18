from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import compare_monitor_runs, export_analysis_bundle
from stm32_monitor.replay import publish_physical_monitor_run
from stm32_toolkit.acceptance.finalization import (
    FINALIZATION_ATTEMPT_SCHEMA,
    PhysicalFinalizationAttempt,
    PhysicalFinalizationProof,
)
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
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
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.evidence.gc import RootRecord, get_root
from stm32_toolkit.evidence.store import EvidenceStore, MAX_EVIDENCE_READ_BYTES
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run

import test_acceptance_physical_recovery as physical_fixture
import test_vs08a_scenarios as vs08a_fixtures


SCENARIO = "new-cubemx-physical-repair"
VERSION = "1"
SESSION = os.environ.get("VS10B_SESSION_ID", "vs10b-closed-loop-20260918-01")
SAFE_TIME = "2026-09-18T14:50:00.000000Z"
COMMIT_TIME = "2026-09-18T14:55:00.000000Z"
LATE_TIME = "2026-09-18T15:16:00.000000Z"


@dataclass
class PersistedCase:
    project: Path
    data: Path
    request: dict[str, object]
    evidence: EvidenceStore
    workspace: WorkspacePaths


def _configured_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _build_synthetic_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PersistedCase:
    """Build a portable persisted B graph from the existing physical fixtures.

    The fixture is synthetic replay evidence and is deliberately kept separate
    from the optional card-copy integration path.  It exercises the real
    EvidenceStore, Diagnostic, Monitor, TestRun and acceptance readers.
    """
    project = tmp_path / "project"
    physical_fixture._write_physical_project(project, "cubemx")
    data = tmp_path / "data"
    testing = TestingWorkflowContext(project, data, SESSION)
    diagnostic = DiagnosticWorkflowContext(project, data, SESSION)
    model = load_project_model(project)
    source_path = project / "App" / "main.c"
    before_source = source_path.read_bytes()
    before_snapshot = snapshot_project_inputs(model)
    after_source = b"int main(void) { return 1; }\n"
    source_path.write_bytes(after_source)
    after_snapshot = snapshot_project_inputs(load_project_model(project))
    source_path.write_bytes(before_source)
    before_source_sha256 = hashlib.sha256(before_source).hexdigest()
    after_source_sha256 = hashlib.sha256(after_source).hexdigest()

    workspace = WorkspacePaths.from_roots(
        data,
        project,
        UUID(physical_fixture.PROJECT_ID),
        SESSION,
    )
    before_identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=physical_fixture.PROJECT_ID,
        session_id=SESSION,
        build_id=physical_fixture.PHYSICAL_BEFORE_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        target_device=model.target.device,
        input_snapshot_sha256=before_snapshot.sha256,
        git_commit="b" * 40,
        git_dirty=False,
    )
    after_identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=physical_fixture.PROJECT_ID,
        session_id=SESSION,
        build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_AFTER_ELF,
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
    physical_fixture._ok(
        target_replay_run(testing, "seed-failed-t10", failed_descriptor, failed_stream)
    )
    physical_fixture._ok(
        target_replay_run(testing, "seed-fixed-t10", fixed_descriptor, fixed_stream)
    )
    failed_physical = physical_fixture._publish_physical_from_seed(
        tmp_path,
        project,
        data,
        SESSION,
        "seed-failed-t10",
        physical_fixture.PHYSICAL_FAILED_RUN,
        before_identity,
    )
    fixed_physical = physical_fixture._publish_physical_from_seed(
        tmp_path,
        project,
        data,
        SESSION,
        "seed-fixed-t10",
        physical_fixture.PHYSICAL_FIXED_RUN,
        after_identity,
    )

    build_after = {"value": False}

    def fresh_firmware_facts(_project: Path):
        current_model = load_project_model(project)
        current_snapshot = snapshot_project_inputs(current_model)
        if build_after["value"]:
            build_id, elf_sha = (
                physical_fixture.PHYSICAL_AFTER_BUILD,
                physical_fixture.PHYSICAL_AFTER_ELF,
            )
        else:
            build_id, elf_sha = (
                physical_fixture.PHYSICAL_BEFORE_BUILD,
                physical_fixture.PHYSICAL_BEFORE_ELF,
            )
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
    monkeypatch.setattr(diagnostic_workflows, "_session_id_factory", lambda: "9" * 32)

    def ok(result: object) -> Mapping[str, object]:
        assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
        data_value = getattr(result, "data", None)
        assert isinstance(data_value, Mapping)
        return data_value

    started = ok(
        diagnostic_start(
            diagnostic,
            operation_id="vs10b-synthetic-diagnostic-start",
            failed_test_run_id=physical_fixture.PHYSICAL_FAILED_RUN,
            failed_run_mode="target",
        )
    )
    diagnostic_id = str(started["session"]["diagnostic_session_id"])
    ok(
        diagnostic_begin(
            diagnostic,
            operation_id="vs10b-synthetic-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id="vs10b-synthetic-hypothesis-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=2,
            statement="the failed physical run identifies the faulty behavior",
        )
    )["hypothesis"]
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = ok(
        diagnostic_add_plan(
            diagnostic,
            operation_id="vs10b-synthetic-observation-plan-add",
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
    ok(
        diagnostic_run_plan(
            diagnostic,
            operation_id="vs10b-synthetic-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="vs10b-synthetic-hypothesis-assess",
            diagnostic_session_id=diagnostic_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="physical-failed-run",
            polarity="supports",
            rationale="the failed physical run supports the hypothesis",
        )
    )

    recovery_context = AcceptanceRecoveryContext(
        project,
        data,
        SESSION,
        clock=lambda: "2026-09-10T00:00:00.000000Z",
    )
    physical_attempt_id = physical_fixture.ATTEMPT_ID
    ok(
        begin_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            scenario_id="new-cubemx-physical-repair",
            scenario_version="1",
        )
    )
    ok(
        checkpoint_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=0,
            stage="project-materialized",
        )
    )
    ok(
        checkpoint_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=1,
            stage="firmware-built-before",
        )
    )
    ok(
        checkpoint_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=2,
            stage="target-failure-observed",
            test_run_id=physical_fixture.PHYSICAL_FAILED_RUN,
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
    ok(
        checkpoint_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=3,
            stage="diagnosis-completed",
            diagnostic_session_id=diagnostic_id,
            source_change_intent=intent_input,
        )
    )
    resumed = ok(resume_acceptance_attempt(recovery_context, attempt_id=physical_attempt_id))
    action_digest = str(resumed["actionDigest"])
    ok(
        authorize_acceptance_source_change(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=4,
            action_digest=action_digest,
            authorized=True,
        )
    )

    source_path.write_bytes(after_source)
    build_after["value"] = True
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(
        b"--- a/App/main.c\n+++ b/App/main.c\n@@ -1 +1 @@\n"
        b"-int main(void) { return 0; }\n+int main(void) { return 1; }\n"
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
        before_build_id=physical_fixture.PHYSICAL_BEFORE_BUILD,
        before_elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        after_build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        after_elf_sha256=physical_fixture.PHYSICAL_AFTER_ELF,
        changed_paths=("App/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )
    ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id="vs10b-synthetic-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=declaration,
        )
    )
    ok(
        checkpoint_acceptance_attempt(
            recovery_context,
            attempt_id=physical_attempt_id,
            expected_revision=5,
            stage="firmware-built-after",
        )
    )

    failed_batches = physical_fixture._append_physical_monitor_history(
        workspace,
        before_identity,
        physical_fixture.PHYSICAL_RAW_PROBE,
        f"flash-{physical_fixture.PHYSICAL_FAILED_RUN}",
        f"lease-{physical_fixture.PHYSICAL_FAILED_RUN}",
        vs08a_fixtures.MONITOR_OPERATION_IDS["failed-before"],
        value_offset=0,
    )
    fixed_batches = physical_fixture._append_physical_monitor_history(
        workspace,
        after_identity,
        physical_fixture.PHYSICAL_RAW_PROBE,
        f"flash-{physical_fixture.PHYSICAL_FIXED_RUN}",
        f"lease-{physical_fixture.PHYSICAL_FIXED_RUN}",
        vs08a_fixtures.MONITOR_OPERATION_IDS["fixed-after"],
        value_offset=10,
    )
    monitor_before = publish_physical_monitor_run(
        workspace,
        evidence,
        scenario_role="failed-before",
        test_run_id=physical_fixture.PHYSICAL_FAILED_RUN,
        run_id=vs08a_fixtures.MONITOR_OPERATION_IDS["failed-before"],
        group_id=str(failed_batches[0].group_id),
        start_sequence=failed_batches[0].sequence,
        end_sequence_exclusive=failed_batches[-1].sequence + 1,
        start_captured_unix_ns=failed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=failed_batches[-1].captured_unix_ns + 1,
        probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
    )
    monitor_after = publish_physical_monitor_run(
        workspace,
        evidence,
        scenario_role="fixed-after",
        test_run_id=physical_fixture.PHYSICAL_FIXED_RUN,
        run_id=vs08a_fixtures.MONITOR_OPERATION_IDS["fixed-after"],
        group_id=str(fixed_batches[0].group_id),
        start_sequence=fixed_batches[0].sequence,
        end_sequence_exclusive=fixed_batches[-1].sequence + 1,
        start_captured_unix_ns=fixed_batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=fixed_batches[-1].captured_unix_ns + 1,
        probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
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
        diagnostic_id,
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
        physical_fixture.PHYSICAL_FAILED_RUN,
        physical_fixture.PHYSICAL_FIXED_RUN,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=diagnostic_id,
        failed_before_run_id=physical_fixture.PHYSICAL_FAILED_RUN,
        failed_before_evidence_id=str(failed_physical.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=physical_fixture.PHYSICAL_FIXED_RUN,
        fixed_after_evidence_id=str(fixed_physical.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    ok(
        diagnostic_add_verification_plan(
            diagnostic,
            operation_id="vs10b-synthetic-verification-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=7,
            verification_plan=verification_plan,
        )
    )
    ok(
        diagnostic_start_verification(
            diagnostic,
            operation_id="vs10b-synthetic-verification-start",
            diagnostic_session_id=diagnostic_id,
            expected_revision=8,
            verification_plan_id=verification_plan.verification_plan_id,
        )
    )
    ok(
        diagnostic_attach_marker(
            diagnostic,
            operation_id="vs10b-synthetic-marker-attach",
            diagnostic_session_id=diagnostic_id,
            expected_revision=9,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    completed = ok(
        diagnostic_complete_verification(
            diagnostic,
            operation_id="vs10b-synthetic-verification-complete",
            diagnostic_session_id=diagnostic_id,
            expected_revision=10,
            executed_operation_ids=[
                physical_fixture.PHYSICAL_FAILED_RUN,
                physical_fixture.PHYSICAL_FIXED_RUN,
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
            cancelled=False,
        )
    )
    assert completed["session"]["state"] == "RESOLVED"
    predecessor = ok(
        resume_acceptance_attempt(recovery_context, attempt_id=physical_attempt_id)
    )["attempt"]
    assert predecessor["revision"] == 6
    predecessor_root = get_root(
        evidence,
        "acceptance-attempt",
        recovery_workflows._root_id(physical_attempt_id, 6),
    )
    request = {
        "schema": "stm32-physical-continuation-request/2",
        "kind": "bind",
        "predecessorAttemptId": physical_attempt_id,
        "predecessorCheckpointId": predecessor["checkpointId"],
        "predecessorEvidenceId": predecessor_root.manifest_id,
        "fixedAfterTestRunId": physical_fixture.PHYSICAL_FIXED_RUN,
        "fixedAfterEvidenceId": str(fixed_physical.envelope.evidence_id),
        "diagnosticRevision": completed["session"]["revision"],
        "diagnosticEventHead": completed["session"]["event_head"],
        "fixVerificationId": completed["fix_verification"]["fix_verification_id"],
    }
    return PersistedCase(
        project=project,
        data=data,
        request=request,
        evidence=evidence,
        workspace=workspace,
    )


@pytest.fixture
def persisted_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PersistedCase:
    source_data = _configured_path("VS10B_DATA_COPY")
    project = _configured_path("VS10B_PROJECT_ROOT")
    request_path = _configured_path("VS10B_BIND_REQUEST")
    configured = (source_data, project, request_path)
    if all(value is None for value in configured):
        # Portable default: synthetic replay evidence built through the same
        # real stores and validators as the existing B physical tests.
        return _build_synthetic_case(tmp_path, monkeypatch)
    if (
        source_data is None
        or project is None
        or request_path is None
        or not source_data.is_dir()
        or not project.is_dir()
        or not request_path.is_file()
    ):
        pytest.fail(
            "VS10-B persisted fixture paths were explicitly configured but are incomplete: "
            "VS10B_DATA_COPY, VS10B_PROJECT_ROOT and VS10B_BIND_REQUEST must all exist"
        )
    data = tmp_path / "data"
    shutil.copytree(source_data, data)
    model = load_project_model(project)
    workspace = WorkspacePaths.from_roots(
        data,
        project,
        UUID(str(model.logical_project_id)),
        SESSION,
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert isinstance(request, dict)
    return PersistedCase(
        project=project,
        data=data,
        request=request,
        evidence=EvidenceStore(workspace.workspace_root / "evidence"),
        workspace=workspace,
    )


def test_explicit_external_fixture_paths_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VS10B_DATA_COPY", str(tmp_path / "missing-data"))
    monkeypatch.setenv("VS10B_PROJECT_ROOT", str(tmp_path / "missing-project"))
    monkeypatch.setenv("VS10B_BIND_REQUEST", str(tmp_path / "missing-request.json"))
    with pytest.raises(
        pytest.fail.Exception,
        match="explicitly configured but are incomplete",
    ):
        persisted_case.__wrapped__(tmp_path, monkeypatch)


def _context(case: PersistedCase, clock=lambda: SAFE_TIME) -> AcceptanceRecoveryContext:
    return AcceptanceRecoveryContext(case.project, case.data, SESSION, clock=clock)


def _begin(case: PersistedCase, attempt_id: str, continuation: object | None = None, *, clock=lambda: SAFE_TIME):
    return begin_acceptance_attempt(
        _context(case, clock),
        attempt_id=attempt_id,
        scenario_id=SCENARIO,
        scenario_version=VERSION,
        continuation=case.request if continuation is None else continuation,
    )


def _proof(case: PersistedCase, attempt: Mapping[str, object]) -> PhysicalFinalizationProof:
    envelope = case.evidence.get_envelope(str(attempt["continuationEvidenceId"]))
    assert len(envelope.artifacts) == 1
    payload = case.evidence.read_artifact(
        envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES
    )
    return PhysicalFinalizationProof.from_value(json.loads(payload.decode("utf-8")))


def _checkpoint(
    case: PersistedCase,
    attempt_id: str,
    proof: PhysicalFinalizationProof,
    *,
    clock=lambda: SAFE_TIME,
    diagnostic_session_id: str | None = None,
):
    return checkpoint_acceptance_attempt(
        _context(case, clock),
        attempt_id=attempt_id,
        expected_revision=0,
        stage="target-fix-verified",
        test_run_id=proof.fixed_after_test_run_id,
        diagnostic_session_id=proof.diagnostic_session_id if diagnostic_session_id is None else diagnostic_session_id,
        acceptance_record_id=None,
        source_change_intent=None,
        fix_verification_id=proof.fix_verification_id,
    )


def _root_path(case: PersistedCase, attempt_id: str, revision: int) -> Path:
    return recovery_workflows._typed_root_path(
        case.evidence, recovery_workflows._root_id(attempt_id, revision)
    )


def _replace_attempt_root(
    case: PersistedCase,
    attempt_id: str,
    revision: int,
    mutation: Mapping[str, object],
) -> PhysicalFinalizationAttempt:
    old_root = get_root(
        case.evidence,
        "acceptance-attempt",
        recovery_workflows._root_id(attempt_id, revision),
    )
    old_envelope = case.evidence.get_envelope(old_root.manifest_id)
    raw_attempt = dict(old_envelope.metadata["attempt"])
    raw_attempt.update(mutation)
    candidate = recovery_workflows._finalization_snapshot(raw_attempt)
    parents = (
        (candidate.continuation_evidence_id,)
        if revision == 0
        else old_envelope.parents
    )
    replacement = EvidenceEnvelope(
        identity=old_envelope.identity,
        operation=old_envelope.operation,
        produced_at_utc=candidate.updated_at_utc,
        parents=parents,
        artifacts=(),
        metadata=recovery_workflows._finalization_envelope_metadata(candidate),
    )
    case.evidence.put_envelope(replacement)
    _root_path(case, attempt_id, revision).unlink()
    with case.evidence._mutation_lock():
        recovery_workflows._publish_root_locked(
            case.evidence,
            RootRecord(
                "acceptance-attempt",
                recovery_workflows._root_id(attempt_id, revision),
                str(replacement.evidence_id),
                recovery_workflows._finalization_root_metadata(candidate),
            ),
        )
    return candidate


def _publish_extra_revision(case: PersistedCase, attempt_id: str, attempt: Mapping[str, object]) -> None:
    root_id = recovery_workflows._root_id(attempt_id, 3)
    # Use an existing valid attempt envelope as the manifest target.  The
    # rejection under test is the closed revision range, rather than a
    # missing or otherwise malformed evidence reference.
    valid_manifest_id = get_root(
        case.evidence,
        "acceptance-attempt",
        recovery_workflows._root_id(attempt_id, 0),
    ).manifest_id
    with case.evidence._mutation_lock():
        recovery_workflows._publish_root_locked(
            case.evidence,
            RootRecord(
                "acceptance-attempt",
                root_id,
                valid_manifest_id,
                {"attempt_sha256": str(attempt["checkpointId"])},
            ),
        )


def _swap_proof_parents(case: PersistedCase, attempt: Mapping[str, object]) -> str:
    """Publish a proof envelope with valid bytes but the wrong parent order."""
    proof = _proof(case, attempt)
    evidence_id = str(attempt["continuationEvidenceId"])
    old_envelope = case.evidence.get_envelope(evidence_id)
    assert len(old_envelope.parents) == 5
    swapped = EvidenceEnvelope(
        identity=old_envelope.identity,
        operation=old_envelope.operation,
        produced_at_utc=old_envelope.produced_at_utc,
        parents=(old_envelope.parents[1], old_envelope.parents[0], *old_envelope.parents[2:]),
        artifacts=old_envelope.artifacts,
        metadata=old_envelope.metadata,
    )
    case.evidence.put_envelope(swapped)
    root_path = recovery_workflows._typed_root_path(
        case.evidence, proof.continuation_id, recovery_workflows.FINALIZATION_ROOT_TYPE
    )
    root = get_root(case.evidence, recovery_workflows.FINALIZATION_ROOT_TYPE, proof.continuation_id)
    root_payload = root.to_dict()
    root_payload["manifest_id"] = str(swapped.evidence_id)
    root_path.write_bytes(canonical_json_bytes(root_payload))
    return str(swapped.evidence_id)


def _duplicate_physical_predecessor(
    case: PersistedCase,
    source_attempt_id: str,
    duplicate_attempt_id: str,
) -> dict[str, object]:
    """Copy the persisted /4 rev0..rev6 chain with a new valid attempt ID."""
    source_chain = recovery_workflows._load_physical_chain(
        case.evidence,
        attempt_id=source_attempt_id,
        workspace_id=case.workspace.workspace_id,
        logical_project_id=str(load_project_model(case.project).logical_project_id),
    )
    previous: PhysicalFinalizationAttempt | None = None
    previous_envelope: EvidenceEnvelope | None = None
    duplicated_action_digest: str | None = None
    copied: list[tuple[PhysicalFinalizationAttempt, EvidenceEnvelope]] = []
    for revision, (_old_attempt, old_envelope) in enumerate(source_chain):
        raw = json.loads(
            canonical_json_bytes(old_envelope.metadata["attempt"]).decode("utf-8")
        )
        raw["attemptId"] = duplicate_attempt_id
        raw["previousCheckpointId"] = None if previous is None else previous.checkpoint_id
        if revision >= 5:
            authorization = dict(raw["sourceChangeAuthorization"])
            if previous is not None and revision == 5:
                duplicated_action_digest = recovery_workflows._physical_action_digest(previous)
            if duplicated_action_digest is not None:
                authorization["actionDigest"] = duplicated_action_digest
            raw["sourceChangeAuthorization"] = authorization
        raw.pop("checkpointId", None)
        raw["checkpointId"] = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
        attempt = recovery_workflows.PhysicalAcceptanceAttempt.from_value(raw)
        parents = () if previous_envelope is None else (str(previous_envelope.evidence_id),)
        envelope = EvidenceEnvelope(
            identity=old_envelope.identity,
            operation=old_envelope.operation,
            produced_at_utc=attempt.updated_at_utc,
            parents=parents,
            artifacts=old_envelope.artifacts,
            metadata=recovery_workflows._physical_envelope_metadata(attempt),
        )
        case.evidence.put_envelope(envelope)
        with case.evidence._mutation_lock():
            recovery_workflows._publish_root_locked(
                case.evidence,
                RootRecord(
                    "acceptance-attempt",
                    recovery_workflows._root_id(duplicate_attempt_id, revision),
                    str(envelope.evidence_id),
                    recovery_workflows._physical_root_metadata(attempt),
                ),
            )
        copied.append((attempt, envelope))
        previous = attempt
        previous_envelope = envelope
    recovery_workflows._validate_physical_chain_semantics(
        copied,
        model=load_project_model(case.project),
        workspace=case.workspace,
        session_id=SESSION,
    )
    return {
        "attempt": copied[-1][0].to_dict(),
        "evidenceId": str(copied[-1][1].evidence_id),
    }


def _fresh_show(case: PersistedCase, attempt_id: str) -> dict[str, object]:
    code = (
        "import json,sys; "
        "from pathlib import Path; "
        "from stm32_toolkit.acceptance.recovery_workflows import "
        "AcceptanceRecoveryContext,show_acceptance_attempt; "
        "r=show_acceptance_attempt(AcceptanceRecoveryContext(Path(sys.argv[1]), "
        "Path(sys.argv[2]), sys.argv[3]), attempt_id=sys.argv[4]); "
        "print(json.dumps({'ok':r.ok,'code':r.code}, sort_keys=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(case.project), str(case.data), SESSION, attempt_id],
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    return json.loads(result.stdout)


def test_finalization_persisted_round_trip_and_exact_explicit_retry(
    persisted_case: PersistedCase,
) -> None:
    attempt_id = "00000000-0000-4000-8000-000000000301"
    started = _begin(persisted_case, attempt_id)
    assert started.ok
    rev0 = started.data["attempt"]
    assert rev0["schema"] == FINALIZATION_ATTEMPT_SCHEMA
    proof = _proof(persisted_case, rev0)
    completed = _checkpoint(persisted_case, attempt_id, proof)
    assert completed.ok
    retry = _checkpoint(persisted_case, attempt_id, proof)
    assert retry.ok
    assert retry.data == completed.data
    fresh = _fresh_show(persisted_case, attempt_id)
    assert fresh == {"code": "OK", "ok": True}


def test_expired_attempt_retry_and_fresh_uuid_proof_reuse_lifecycle(
    persisted_case: PersistedCase,
) -> None:
    expired_id = "00000000-0000-4000-8000-000000000314"
    started = _begin(persisted_case, expired_id, clock=lambda: SAFE_TIME)
    assert started.ok
    original = started.data["attempt"]
    assert isinstance(original, Mapping)
    original_deadline = original["deadlineAtUtc"]
    proof = _proof(persisted_case, original)

    late_first = _checkpoint(
        persisted_case,
        expired_id,
        proof,
        clock=lambda: LATE_TIME,
    )
    assert not late_first.ok
    assert late_first.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    assert not _root_path(persisted_case, expired_id, 1).exists()

    exact_retry = _begin(
        persisted_case,
        expired_id,
        clock=lambda: LATE_TIME,
    )
    assert exact_retry.ok
    assert exact_retry.data == started.data
    assert exact_retry.data["attempt"]["deadlineAtUtc"] == original_deadline

    reuse_request = {
        "schema": "stm32-physical-continuation-request/2",
        "kind": "reuse",
        "continuationEvidenceId": str(original["continuationEvidenceId"]),
    }
    fresh_id = "00000000-0000-4000-8000-000000000315"
    fresh_started = _begin(
        persisted_case,
        fresh_id,
        reuse_request,
        clock=lambda: LATE_TIME,
    )
    assert fresh_started.ok
    fresh_proof = _proof(persisted_case, fresh_started.data["attempt"])
    fresh_completed = _checkpoint(
        persisted_case,
        fresh_id,
        fresh_proof,
        clock=lambda: LATE_TIME,
    )
    assert fresh_completed.ok
    assert fresh_completed.data["attempt"]["revision"] == 1

    late_completed_retry = _checkpoint(
        persisted_case,
        fresh_id,
        fresh_proof,
        clock=lambda: "2026-09-18T15:35:00.000000Z",
    )
    assert late_completed_retry.ok
    assert late_completed_retry.data == fresh_completed.data


def test_b_authority_graph_rejections_use_persisted_proof_and_context(
    persisted_case: PersistedCase,
) -> None:
    wrong_head = dict(persisted_case.request)
    wrong_head["diagnosticEventHead"] = "0" * 64
    wrong_head_id = "00000000-0000-4000-8000-000000000316"
    wrong_head_result = _begin(persisted_case, wrong_head_id, wrong_head)
    assert not wrong_head_result.ok
    assert wrong_head_result.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert not _root_path(persisted_case, wrong_head_id, 0).exists()

    foreign_context = AcceptanceRecoveryContext(
        persisted_case.project,
        persisted_case.data,
        "foreign-session-20260918",
    )
    foreign_id = "00000000-0000-4000-8000-000000000317"
    foreign_result = begin_acceptance_attempt(
        foreign_context,
        attempt_id=foreign_id,
        scenario_id=SCENARIO,
        scenario_version=VERSION,
        continuation=persisted_case.request,
    )
    assert not foreign_result.ok
    assert foreign_result.code in {
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
    }
    assert not _root_path(persisted_case, foreign_id, 0).exists()

    started = _begin(
        persisted_case,
        "00000000-0000-4000-8000-000000000318",
    )
    assert started.ok
    swapped_evidence_id = _swap_proof_parents(
        persisted_case,
        started.data["attempt"],
    )
    tampered_reuse = {
        "schema": "stm32-physical-continuation-request/2",
        "kind": "reuse",
        "continuationEvidenceId": swapped_evidence_id,
    }
    tampered_id = "00000000-0000-4000-8000-000000000319"
    tampered_result = _begin(persisted_case, tampered_id, tampered_reuse)
    assert not tampered_result.ok
    assert tampered_result.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    assert not _root_path(persisted_case, tampered_id, 0).exists()


def test_begin_rechecks_current_firmware_before_commit_phase(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = recovery_workflows._physical_build_data
    calls = {"count": 0}

    def drifted(context: AcceptanceRecoveryContext, model: object):
        calls["count"] += 1
        build, snapshot = original(context, model)
        if calls["count"] == 4:
            build = {**build, "buildId": "0" * 64}
        return build, snapshot

    monkeypatch.setattr(recovery_workflows, "_physical_build_data", drifted)
    attempt_id = "00000000-0000-4000-8000-000000000302"
    result = _begin(persisted_case, attempt_id)
    assert not result.ok
    assert result.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert not _root_path(persisted_case, attempt_id, 0).exists()
    assert calls["count"] >= 4


def test_same_uuid_two_authenticated_reuse_proofs_cannot_cross_return(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _begin(
        persisted_case,
        "00000000-0000-4000-8000-000000000303",
    )
    assert first.ok
    proof_a = _proof(persisted_case, first.data["attempt"])
    duplicate = _duplicate_physical_predecessor(
        persisted_case,
        physical_fixture.ATTEMPT_ID,
        "00000000-0000-4000-8000-000000000399",
    )
    second_request = dict(persisted_case.request)
    second_request.update(
        {
            "predecessorAttemptId": duplicate["attempt"]["attemptId"],
            "predecessorCheckpointId": duplicate["attempt"]["checkpointId"],
            "predecessorEvidenceId": duplicate["evidenceId"],
        }
    )
    second = _begin(
        persisted_case,
        "00000000-0000-4000-8000-000000000304",
        second_request,
    )
    assert second.ok
    proof_b = _proof(persisted_case, second.data["attempt"])
    assert proof_a != proof_b
    reuse_a = {
        "schema": "stm32-physical-continuation-request/2",
        "kind": "reuse",
        "continuationEvidenceId": str(first.data["attempt"]["continuationEvidenceId"]),
    }
    reuse_b = {
        "schema": "stm32-physical-continuation-request/2",
        "kind": "reuse",
        "continuationEvidenceId": str(second.data["attempt"]["continuationEvidenceId"]),
    }
    race_id = "00000000-0000-4000-8000-000000000305"
    original_publish = recovery_workflows._publish_finalization_proof
    injected = {"done": False, "competitor": None}

    def publish_then_compete(*args: object, **kwargs: object):
        association = original_publish(*args, **kwargs)
        if not injected["done"]:
            injected["done"] = True
            context = args[0]
            assert isinstance(context, AcceptanceRecoveryContext)
            injected["competitor"] = begin_acceptance_attempt(
                context,
                attempt_id=race_id,
                scenario_id=SCENARIO,
                scenario_version=VERSION,
                continuation=reuse_b,
            )
        return association

    monkeypatch.setattr(
        recovery_workflows,
        "_publish_finalization_proof",
        publish_then_compete,
    )
    outer = begin_acceptance_attempt(
        _context(persisted_case),
        attempt_id=race_id,
        scenario_id=SCENARIO,
        scenario_version=VERSION,
        continuation=reuse_a,
    )
    assert not outer.ok
    assert outer.code == "ACCEPTANCE_ATTEMPT_CONFLICT"
    assert injected["competitor"] is not None
    assert injected["competitor"].ok
    shown = show_acceptance_attempt(_context(persisted_case), attempt_id=race_id)
    assert shown.ok
    assert shown.data["attempt"]["continuationEvidenceId"] == reuse_b["continuationEvidenceId"]


@pytest.mark.parametrize(
    ("revision", "field", "value"),
    (
        (0, "fixedAfterTestRunId", "target-v2-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        (0, "fixedAfterEvidenceId", "a" * 64),
        (0, "continuationEvidenceId", "b" * 64),
        (1, "fixVerificationId", "c" * 64),
    ),
)
def test_persisted_attempt_binding_mutations_are_rejected(
    persisted_case: PersistedCase,
    revision: int,
    field: str,
    value: object,
) -> None:
    attempt_id = f"00000000-0000-4000-8000-{revision + 304:012d}"
    started = _begin(persisted_case, attempt_id)
    assert started.ok
    proof = _proof(persisted_case, started.data["attempt"])
    if revision == 1:
        completed = _checkpoint(persisted_case, attempt_id, proof)
        assert completed.ok
    _replace_attempt_root(persisted_case, attempt_id, revision, {field: value})
    for result in (
        show_acceptance_attempt(_context(persisted_case), attempt_id=attempt_id),
        _begin(persisted_case, attempt_id),
        _checkpoint(persisted_case, attempt_id, proof),
    ):
        assert not result.ok
        assert result.code in {
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
            "ACCEPTANCE_ATTEMPT_CONFLICT",
        }


def test_unexpected_revision_rejected_by_read_mutation_and_fresh_process(
    persisted_case: PersistedCase,
) -> None:
    attempt_id = "00000000-0000-4000-8000-000000000309"
    started = _begin(persisted_case, attempt_id)
    assert started.ok
    _publish_extra_revision(persisted_case, attempt_id, started.data["attempt"])
    shown = show_acceptance_attempt(_context(persisted_case), attempt_id=attempt_id)
    assert not shown.ok
    assert shown.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    begun_again = _begin(persisted_case, attempt_id)
    assert not begun_again.ok
    assert begun_again.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    proof = _proof(persisted_case, started.data["attempt"])
    checkpoint = _checkpoint(persisted_case, attempt_id, proof)
    assert not checkpoint.ok
    assert checkpoint.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    fresh = _fresh_show(persisted_case, attempt_id)
    assert fresh == {"code": "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED", "ok": False}


def test_malformed_b_requests_are_input_invalid_without_persisted_mutation(
    persisted_case: PersistedCase,
) -> None:
    before = tuple(sorted(path.relative_to(persisted_case.data).as_posix() for path in persisted_case.data.rglob("*")))
    for continuation in (
        [],
        {"kind": "reuse"},
        {"schema": "stm32-physical-continuation/1", "kind": "reuse"},
        {"schema": "stm32-physical-continuation/9", "kind": "reuse"},
        {},
    ):
        result = begin_acceptance_attempt(
            _context(persisted_case),
            attempt_id="00000000-0000-4000-8000-000000000310",
            scenario_id=SCENARIO,
            scenario_version=VERSION,
            continuation=continuation,
        )
        if continuation == {}:
            assert result.code == "ACCEPTANCE_ATTEMPT_STAGE_INVALID"
        else:
            assert result.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    after = tuple(sorted(path.relative_to(persisted_case.data).as_posix() for path in persisted_case.data.rglob("*")))
    assert after == before


def test_commit_timestamp_is_sampled_after_begin_authority_recheck(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase = {"rechecked": False}
    original = recovery_workflows._finalization_recheck_before_attempt_publication_locked

    def recheck(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        phase["rechecked"] = True
        return result

    def clock() -> str:
        return COMMIT_TIME if phase["rechecked"] else SAFE_TIME

    monkeypatch.setattr(
        recovery_workflows,
        "_finalization_recheck_before_attempt_publication_locked",
        recheck,
    )
    attempt_id = "00000000-0000-4000-8000-000000000311"
    result = _begin(persisted_case, attempt_id, clock=clock)
    assert result.ok
    assert result.data["attempt"]["openedAtUtc"] == COMMIT_TIME
    assert result.data["attempt"]["updatedAtUtc"] == COMMIT_TIME


def test_commit_timestamp_is_sampled_after_checkpoint_authority_recheck(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = _begin(
        persisted_case,
        "00000000-0000-4000-8000-000000000312",
        clock=lambda: SAFE_TIME,
    )
    assert started.ok
    proof = _proof(persisted_case, started.data["attempt"])
    phase = {"rechecked": False}
    original = recovery_workflows._finalization_recheck_before_attempt_publication_locked

    def recheck(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        phase["rechecked"] = True
        return result

    def clock() -> str:
        return COMMIT_TIME if phase["rechecked"] else SAFE_TIME

    monkeypatch.setattr(
        recovery_workflows,
        "_finalization_recheck_before_attempt_publication_locked",
        recheck,
    )
    result = _checkpoint(
        persisted_case,
        "00000000-0000-4000-8000-000000000312",
        proof,
        clock=clock,
    )
    assert result.ok
    assert result.data["attempt"]["updatedAtUtc"] == COMMIT_TIME


def test_final_deadline_check_rejects_new_root_after_envelope_persist(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase = {"rechecked": False, "commit_seen": False}
    original = recovery_workflows._finalization_recheck_before_attempt_publication_locked

    def recheck(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        phase["rechecked"] = True
        return result

    def clock() -> str:
        if not phase["rechecked"]:
            return SAFE_TIME
        if not phase["commit_seen"]:
            phase["commit_seen"] = True
            return "2026-09-18T15:00:00.000000Z"
        return LATE_TIME

    monkeypatch.setattr(
        recovery_workflows,
        "_finalization_recheck_before_attempt_publication_locked",
        recheck,
    )
    attempt_id = "00000000-0000-4000-8000-000000000313"
    result = _begin(persisted_case, attempt_id, clock=clock)
    assert not result.ok
    assert result.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    assert not _root_path(persisted_case, attempt_id, 0).exists()


def test_final_deadline_check_rejects_rev1_root_after_envelope_persist(
    persisted_case: PersistedCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_id = "00000000-0000-4000-8000-000000000320"
    started = _begin(persisted_case, attempt_id, clock=lambda: SAFE_TIME)
    assert started.ok
    proof = _proof(persisted_case, started.data["attempt"])
    phase = {"rechecked": False, "commit_seen": False}
    original = recovery_workflows._finalization_recheck_before_attempt_publication_locked

    def recheck(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        phase["rechecked"] = True
        return result

    def clock() -> str:
        if not phase["rechecked"]:
            return SAFE_TIME
        if not phase["commit_seen"]:
            phase["commit_seen"] = True
            return COMMIT_TIME
        return LATE_TIME

    monkeypatch.setattr(
        recovery_workflows,
        "_finalization_recheck_before_attempt_publication_locked",
        recheck,
    )
    result = _checkpoint(
        persisted_case,
        attempt_id,
        proof,
        clock=clock,
    )
    assert not result.ok
    assert result.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    assert _root_path(persisted_case, attempt_id, 0).exists()
    assert not _root_path(persisted_case, attempt_id, 1).exists()
