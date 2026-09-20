from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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
    FINALIZATION_EXECUTION_SOURCE,
    FINALIZATION_POLICY_DIGEST,
    FINALIZATION_REQUEST_SCHEMA,
    FINALIZATION_PROJECT_ORIGIN,
    FINALIZATION_ROOT_TYPE,
    FINALIZATION_SCHEMA,
    FINALIZATION_SCENARIO_DIGEST,
    FINALIZATION_SCENARIO_ID,
    FINALIZATION_SCENARIO_VERSION,
    FINALIZATION_WINDOW_SECONDS,
    FinalizationRequest,
    FinalizationValidationError,
    PhysicalFinalizationAttempt,
    PhysicalFinalizationProof,
    finalization_policy_document,
)
from stm32_toolkit.acceptance.recovery import SourceChangeIntent
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
from stm32_toolkit.evidence import (
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
)
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


def test_finalization_request_wire_guards_preserve_input() -> None:
    invalid_revision = {
        "schema": FINALIZATION_REQUEST_SCHEMA,
        "kind": "bind",
        "predecessorAttemptId": "00000000-0000-4000-8000-000000000001",
        "predecessorCheckpointId": "a" * 64,
        "predecessorEvidenceId": "b" * 64,
        "fixedAfterTestRunId": "target-v2-fixed-t10",
        "fixedAfterEvidenceId": "c" * 64,
        "diagnosticRevision": True,
        "diagnosticEventHead": "d" * 64,
        "fixVerificationId": "e" * 64,
    }
    before_invalid_revision = dict(invalid_revision)
    with pytest.raises(FinalizationValidationError):
        FinalizationRequest.from_value(invalid_revision)
    assert invalid_revision == before_invalid_revision

    invalid_reuse_kind = {
        "schema": FINALIZATION_REQUEST_SCHEMA,
        "kind": "bind",
        "continuationEvidenceId": "f" * 64,
    }
    before_invalid_reuse_kind = dict(invalid_reuse_kind)
    with pytest.raises(FinalizationValidationError):
        FinalizationRequest.from_value(invalid_reuse_kind)
    assert invalid_reuse_kind == before_invalid_reuse_kind


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


def _replace_attempt_envelope_identity(
    case: PersistedCase,
    attempt_id: str,
    revision: int,
    *,
    session_id: str,
) -> None:
    root = get_root(
        case.evidence,
        "acceptance-attempt",
        recovery_workflows._root_id(attempt_id, revision),
    )
    old_envelope = case.evidence.get_envelope(root.manifest_id)
    replacement = EvidenceEnvelope(
        identity=replace(old_envelope.identity, session_id=session_id),
        operation=old_envelope.operation,
        produced_at_utc=old_envelope.produced_at_utc,
        parents=old_envelope.parents,
        artifacts=old_envelope.artifacts,
        metadata=old_envelope.metadata,
    )
    case.evidence.put_envelope(replacement)
    root_payload = root.to_dict()
    root_payload["manifest_id"] = str(replacement.evidence_id)
    _root_path(case, attempt_id, revision).write_bytes(
        canonical_json_bytes(root_payload)
    )


def _replace_finalization_root_metadata(
    case: PersistedCase,
    proof: PhysicalFinalizationProof,
) -> None:
    root = get_root(
        case.evidence,
        recovery_workflows.FINALIZATION_ROOT_TYPE,
        proof.continuation_id,
    )
    root_payload = root.to_dict()
    root_payload["metadata"] = {"continuation_id": "0" * 64}
    recovery_workflows._typed_root_path(
        case.evidence,
        proof.continuation_id,
        recovery_workflows.FINALIZATION_ROOT_TYPE,
    ).write_bytes(canonical_json_bytes(root_payload))


def _persisted_snapshot(case: PersistedCase) -> dict[str, bytes]:
    return {
        path.relative_to(case.data).as_posix(): path.read_bytes()
        for path in case.data.rglob("*")
        if path.is_file()
    }


def _run_finalization_route(
    case: PersistedCase,
    attempt_id: str,
    proof: PhysicalFinalizationProof,
    route: str,
):
    if route == "show":
        return show_acceptance_attempt(_context(case), attempt_id=attempt_id)
    if route == "begin":
        return _begin(case, attempt_id)
    if route == "checkpoint":
        return _checkpoint(case, attempt_id, proof)
    raise AssertionError(f"unsupported finalization route: {route}")


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


@pytest.mark.parametrize(
    ("mutation", "route", "expected_code"),
    (
        ("rev1-previous-checkpoint", "show", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-previous-checkpoint", "begin", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-previous-checkpoint", "checkpoint", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-immutable-session", "show", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-immutable-session", "begin", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-immutable-session", "checkpoint", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("rev1-envelope-session", "show", "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"),
        ("rev1-envelope-session", "begin", "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"),
        ("rev1-envelope-session", "checkpoint", "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"),
        ("proof-root-metadata", "show", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("proof-root-metadata", "begin", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
        ("proof-root-metadata", "checkpoint", "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"),
    ),
    ids=(
        "rev1-previous-checkpoint-show",
        "rev1-previous-checkpoint-begin",
        "rev1-previous-checkpoint-checkpoint",
        "rev1-immutable-session-show",
        "rev1-immutable-session-begin",
        "rev1-immutable-session-checkpoint",
        "rev1-envelope-session-show",
        "rev1-envelope-session-begin",
        "rev1-envelope-session-checkpoint",
        "proof-root-metadata-show",
        "proof-root-metadata-begin",
        "proof-root-metadata-checkpoint",
    ),
)
def test_finalization_persisted_authority_mutations_refuse_without_new_revision(
    persisted_case: PersistedCase,
    mutation: str,
    route: str,
    expected_code: str,
) -> None:
    attempt_id = "00000000-0000-4000-8000-000000000330"
    started = _begin(persisted_case, attempt_id)
    assert started.ok
    proof = _proof(persisted_case, started.data["attempt"])
    completed = _checkpoint(
        persisted_case,
        attempt_id,
        proof,
        clock=lambda: COMMIT_TIME,
    )
    assert completed.ok

    if mutation == "rev1-previous-checkpoint":
        _replace_attempt_root(
            persisted_case,
            attempt_id,
            1,
            {"previousCheckpointId": "d" * 64},
        )
    elif mutation == "rev1-immutable-session":
        _replace_attempt_root(
            persisted_case,
            attempt_id,
            1,
            {"sessionId": "foreign-session-20260918"},
        )
    elif mutation == "rev1-envelope-session":
        _replace_attempt_envelope_identity(
            persisted_case,
            attempt_id,
            1,
            session_id="foreign-session-20260918",
        )
    elif mutation == "proof-root-metadata":
        _replace_finalization_root_metadata(persisted_case, proof)
    else:
        raise AssertionError(f"unsupported finalization mutation: {mutation}")

    before = _persisted_snapshot(persisted_case)
    result = _run_finalization_route(persisted_case, attempt_id, proof, route)
    assert not result.ok
    assert result.code == expected_code
    assert _persisted_snapshot(persisted_case) == before
    assert _root_path(persisted_case, attempt_id, 0).exists()
    assert _root_path(persisted_case, attempt_id, 1).exists()
    assert not _root_path(persisted_case, attempt_id, 2).exists()


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


def _assert_finalization_wire_rejection(callable_input, value: object, expected: str) -> None:
    before = deepcopy(value)
    with pytest.raises(FinalizationValidationError) as error:
        callable_input()
    assert str(error.value) == expected
    assert value == before


def _finalization_bind_wire() -> dict[str, object]:
    return {
        "schema": FINALIZATION_REQUEST_SCHEMA,
        "kind": "bind",
        "predecessorAttemptId": "00000000-0000-4000-8000-000000000401",
        "predecessorCheckpointId": "a" * 64,
        "predecessorEvidenceId": "b" * 64,
        "fixedAfterTestRunId": "fixed-after-401",
        "fixedAfterEvidenceId": "c" * 64,
        "diagnosticRevision": 7,
        "diagnosticEventHead": "d" * 64,
        "fixVerificationId": "e" * 64,
    }


def _finalization_reuse_wire() -> dict[str, object]:
    return {
        "schema": FINALIZATION_REQUEST_SCHEMA,
        "kind": "reuse",
        "continuationEvidenceId": "f" * 64,
    }


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param(
            "non-object",
            "finalization request must be an object",
            id="request-274-275-non-object",
        ),
        pytest.param(
            "nested-tuple",
            "tuples are not accepted on the JSON boundary",
            id="request-63-64-nested-tuple",
        ),
        pytest.param(
            "invalid-bind-schema",
            "bind request schema or kind is invalid",
            id="request-279-280-invalid-bind-schema",
        ),
        pytest.param(
            "reuse-extra-field",
            "finalization request fields are not closed",
            id="request-297-306-reuse-extra-field",
        ),
    ],
)
def test_finalization_request_public_json_boundaries(case_name: str, expected: str) -> None:
    bind = _finalization_bind_wire()
    reuse = _finalization_reuse_wire()
    parsed_bind = FinalizationRequest.from_value(deepcopy(bind))
    assert {
        "schema": parsed_bind.schema,
        "kind": parsed_bind.kind,
        "predecessorAttemptId": parsed_bind.predecessor_attempt_id,
        "predecessorCheckpointId": parsed_bind.predecessor_checkpoint_id,
        "predecessorEvidenceId": parsed_bind.predecessor_evidence_id,
        "fixedAfterTestRunId": parsed_bind.fixed_after_test_run_id,
        "fixedAfterEvidenceId": parsed_bind.fixed_after_evidence_id,
        "diagnosticRevision": parsed_bind.diagnostic_revision,
        "diagnosticEventHead": parsed_bind.diagnostic_event_head,
        "fixVerificationId": parsed_bind.fix_verification_id,
    } == bind
    parsed_reuse = FinalizationRequest.from_value(deepcopy(reuse))
    assert {
        "schema": parsed_reuse.schema,
        "kind": parsed_reuse.kind,
        "continuationEvidenceId": parsed_reuse.continuation_evidence_id,
    } == reuse

    if case_name == "non-object":
        candidate: object = None
        callable_input = lambda: FinalizationRequest.from_value(candidate)
    elif case_name == "nested-tuple":
        candidate = deepcopy(bind)
        candidate["diagnosticEventHead"] = ("d" * 64,)
        callable_input = lambda: FinalizationRequest.from_value(candidate)
    elif case_name == "invalid-bind-schema":
        candidate = deepcopy(bind)
        candidate["schema"] = "stm32-physical-continuation-request/9"
        callable_input = lambda: FinalizationRequest.from_value(candidate)
    else:
        candidate = deepcopy(reuse)
        candidate["unexpected"] = True
        callable_input = lambda: FinalizationRequest.from_value(candidate)
    _assert_finalization_wire_rejection(callable_input, candidate, expected)


def _finalization_source_changes() -> list[dict[str, object]]:
    return [
        {
            "path": "src/main.c",
            "beforeSha256": "1" * 64,
            "afterSha256": "2" * 64,
            "afterSize": 12,
        }
    ]


def _finalization_expanded_intent() -> SourceChangeIntent:
    return SourceChangeIntent.expanded(
        changes=_finalization_source_changes(),
        before_input_snapshot_sha256="3" * 64,
        expected_after_input_snapshot_sha256="4" * 64,
    )


def _finalization_proof_wire() -> dict[str, object]:
    return {
        "schema": FINALIZATION_SCHEMA,
        "predecessorAttemptId": "00000000-0000-4000-8000-000000000402",
        "predecessorCheckpointId": "5" * 64,
        "predecessorEvidenceId": "6" * 64,
        "diagnosticSessionId": "7" * 32,
        "diagnosticRevision": 9,
        "diagnosticEventHead": "8" * 64,
        "diagnosticEvidenceId": "9" * 64,
        "sourceChangeDeclarationId": "a" * 64,
        "sourceChangeIntent": _finalization_expanded_intent().to_dict(),
        "failedBeforeTestRunId": "failed-before-402",
        "failedBeforeEvidenceId": "b" * 64,
        "fixedAfterTestRunId": "fixed-after-402",
        "fixedAfterEvidenceId": "c" * 64,
        "fixVerificationId": "d" * 64,
    }


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param(
            "extra-field",
            "finalization object fields are not closed",
            id="proof-76-77-extra-field",
        ),
        pytest.param("empty-schema", "schema is invalid", id="proof-82-83-empty-schema"),
        pytest.param(
            "malformed-predecessor",
            "predecessorAttemptId is invalid",
            id="proof-84-85-malformed-predecessor",
        ),
        pytest.param(
            "unsupported-schema",
            "finalization proof schema is unsupported",
            id="proof-170-171-unsupported-schema",
        ),
        pytest.param(
            "diagnostic-revision",
            "diagnosticRevision is invalid",
            id="proof-226-227-diagnostic-revision",
        ),
        pytest.param(
            "unexpanded-intent",
            "finalization intent must be expanded",
            id="proof-129-134-unexpanded-intent",
        ),
        pytest.param(
            "equal-runs",
            "before and after TestRuns must differ",
            id="proof-194-195-equal-runs",
        ),
        pytest.param(
            "equal-evidence",
            "before and after evidence must differ",
            id="proof-196-197-equal-evidence",
        ),
    ],
)
def test_physical_finalization_proof_public_json_boundaries(case_name: str, expected: str) -> None:
    proof = _finalization_proof_wire()
    assert PhysicalFinalizationProof.from_value(deepcopy(proof)).to_dict() == proof
    if case_name == "extra-field":
        candidate = deepcopy(proof)
        candidate["unexpected"] = True
    elif case_name == "empty-schema":
        candidate = deepcopy(proof)
        candidate["schema"] = ""
    elif case_name == "malformed-predecessor":
        candidate = deepcopy(proof)
        candidate["predecessorAttemptId"] = "malformed"
    elif case_name == "unsupported-schema":
        candidate = deepcopy(proof)
        candidate["schema"] = "stm32-physical-continuation/9"
    elif case_name == "diagnostic-revision":
        candidate = deepcopy(proof)
        candidate["diagnosticRevision"] = True
    elif case_name == "unexpanded-intent":
        candidate = deepcopy(proof)
        candidate["sourceChangeIntent"] = SourceChangeIntent.new(
            changes=_finalization_source_changes(),
        ).to_dict()
    elif case_name == "equal-runs":
        candidate = deepcopy(proof)
        candidate["fixedAfterTestRunId"] = candidate["failedBeforeTestRunId"]
    else:
        candidate = deepcopy(proof)
        candidate["fixedAfterEvidenceId"] = candidate["failedBeforeEvidenceId"]
    _assert_finalization_wire_rejection(
        lambda: PhysicalFinalizationProof.from_value(candidate),
        candidate,
        expected,
    )


def _finalization_attempt_wire(
    revision: int,
    *,
    previous_checkpoint_id: str | None = None,
) -> dict[str, object]:
    opened = "2026-09-18T14:50:00.000000Z"
    payload: dict[str, object] = {
        "schema": FINALIZATION_ATTEMPT_SCHEMA,
        "attemptId": "00000000-0000-4000-8000-000000000403",
        "revision": revision,
        "checkpointId": "0" * 64,
        "previousCheckpointId": previous_checkpoint_id if revision == 1 else None,
        "scenarioId": FINALIZATION_SCENARIO_ID,
        "scenarioVersion": FINALIZATION_SCENARIO_VERSION,
        "scenarioDigest": FINALIZATION_SCENARIO_DIGEST,
        "recoveryPolicyDigest": FINALIZATION_POLICY_DIGEST,
        "workspaceId": "1" * 64,
        "logicalProjectId": "00000000-0000-4000-8000-000000000404",
        "sessionId": "finalization-wire-session",
        "projectOrigin": FINALIZATION_PROJECT_ORIGIN,
        "executionSource": FINALIZATION_EXECUTION_SOURCE,
        "physicalTransportEvidence": True,
        "status": "IN_PROGRESS" if revision == 0 else "COMPLETED",
        "stage": "verification-pending" if revision == 0 else "target-fix-verified",
        "continuationEvidenceId": "2" * 64,
        "fixedAfterTestRunId": "fixed-after-403",
        "fixedAfterEvidenceId": "3" * 64,
        "fixVerificationId": None if revision == 0 else "4" * 64,
        "openedAtUtc": opened,
        "updatedAtUtc": opened if revision == 0 else "2026-09-18T14:55:00.000000Z",
        "deadlineAtUtc": "2026-09-18T15:05:00.000000Z",
    }
    unsigned = dict(payload)
    unsigned.pop("checkpointId")
    payload["checkpointId"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    return payload


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param(
            "unsupported-schema",
            "attempt schema is unsupported",
            id="attempt-383-384-unsupported-schema",
        ),
        pytest.param(
            "revision-bool",
            "attempt revision is invalid",
            id="attempt-386-387-revision-bool",
        ),
        pytest.param(
            "rev0-predecessor",
            "rev0 cannot have a predecessor",
            id="attempt-388-389-rev0-predecessor",
        ),
        pytest.param(
            "rev1-predecessor",
            "rev1 needs a predecessor",
            id="attempt-390-391-rev1-predecessor",
        ),
        pytest.param(
            "scenario-identity",
            "finalization scenario or policy identity is not frozen",
            id="attempt-394-400-scenario-identity",
        ),
        pytest.param(
            "provenance",
            "finalization provenance is invalid",
            id="attempt-406-411-provenance",
        ),
        pytest.param(
            "status",
            "finalization status is invalid",
            id="attempt-412-413-status",
        ),
        pytest.param(
            "stage",
            "finalization stage is invalid",
            id="attempt-414-415-stage",
        ),
        pytest.param(
            "rev0-fix-verification",
            "rev0 cannot carry fixVerificationId",
            id="attempt-420-421-rev0-fix-verification",
        ),
        pytest.param(
            "outside-window",
            "attempt update is outside its offline window",
            id="attempt-427-428-outside-window",
        ),
        pytest.param(
            "wrong-deadline",
            "attempt deadline differs from rev0 publication window",
            id="attempt-432-433-wrong-deadline",
        ),
        pytest.param(
            "rev0-time",
            "rev0 opened and updated times differ",
            id="attempt-434-435-rev0-time",
        ),
        pytest.param(
            "checkpoint",
            "checkpointId does not match the snapshot",
            id="attempt-436-437-checkpoint",
        ),
    ],
)
def test_physical_finalization_attempt_public_json_boundaries(case_name: str, expected: str) -> None:
    rev0 = _finalization_attempt_wire(0)
    rev1 = _finalization_attempt_wire(1, previous_checkpoint_id=rev0["checkpointId"])
    parsed_rev0 = PhysicalFinalizationAttempt.from_value(deepcopy(rev0))
    assert parsed_rev0.to_dict() == rev0
    assert parsed_rev0.next_stage == "target-fix-verified"
    parsed_rev1 = PhysicalFinalizationAttempt.from_value(deepcopy(rev1))
    assert parsed_rev1.to_dict() == rev1
    assert parsed_rev1.previous_checkpoint_id == rev0["checkpointId"]
    assert parsed_rev1.next_stage is None

    if case_name == "rev1-predecessor":
        candidate = deepcopy(rev1)
        candidate["previousCheckpointId"] = None
    elif case_name in {"scenario-identity", "provenance", "status", "stage"}:
        candidate = deepcopy(rev0)
        if case_name == "scenario-identity":
            candidate["scenarioId"] = "other-scenario"
        elif case_name == "provenance":
            candidate["executionSource"] = "replay"
        elif case_name == "status":
            candidate["status"] = "COMPLETED"
        else:
            candidate["stage"] = "target-fix-verified"
    elif case_name == "unsupported-schema":
        candidate = deepcopy(rev0)
        candidate["schema"] = "stm32-acceptance-attempt/9"
    elif case_name == "revision-bool":
        candidate = deepcopy(rev0)
        candidate["revision"] = True
    elif case_name == "rev0-predecessor":
        candidate = deepcopy(rev0)
        candidate["previousCheckpointId"] = "5" * 64
    elif case_name == "rev0-fix-verification":
        candidate = deepcopy(rev0)
        candidate["fixVerificationId"] = "6" * 64
    elif case_name == "outside-window":
        candidate = deepcopy(rev0)
        candidate["updatedAtUtc"] = "2026-09-18T15:06:00.000000Z"
    elif case_name == "wrong-deadline":
        candidate = deepcopy(rev0)
        candidate["deadlineAtUtc"] = "2026-09-18T15:10:00.000000Z"
    elif case_name == "rev0-time":
        candidate = deepcopy(rev0)
        candidate["updatedAtUtc"] = "2026-09-18T14:51:00.000000Z"
    else:
        candidate = deepcopy(rev0)
        candidate["checkpointId"] = "0" * 64
    _assert_finalization_wire_rejection(
        lambda: PhysicalFinalizationAttempt.from_value(candidate),
        candidate,
        expected,
    )


def _journey_wire(result: object) -> dict[str, object]:
    to_dict = getattr(result, "to_dict", None)
    assert callable(to_dict)
    wire = to_dict()
    assert isinstance(wire, dict)
    return wire


def _journey_success(wire: Mapping[str, object], operation: str, data: object) -> None:
    assert wire == {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "operation": operation,
        "code": "OK",
        "message": "",
        "data": data,
        "details": {},
    }


def _journey_failure(
    wire: Mapping[str, object], operation: str, code: str
) -> None:
    messages = {
        "ACCEPTANCE_ATTEMPT_CONFLICT": (
            "Acceptance attempt content conflicts with an immutable revision."
        ),
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT": (
            "Acceptance attempt revision conflicts with the current chain."
        ),
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID": "Acceptance attempt stage is invalid.",
        "ACCEPTANCE_ATTEMPT_INPUT_INVALID": "Acceptance attempt input is invalid.",
        "ACCEPTANCE_ATTEMPT_TIMED_OUT": "Acceptance attempt stage deadline has elapsed.",
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH": (
            "Acceptance attempt identity does not match."
        ),
    }
    assert wire == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": messages[code],
        "data": None,
        "details": {},
    }


def _journey_root_id(attempt_id: str, revision: int) -> str:
    return f"{attempt_id}.{revision:08d}"


def _journey_resource_snapshot(
    evidence: EvidenceStore, root_type: str, root_id: str
) -> tuple[dict[str, object], dict[str, object], tuple[tuple[dict[str, object], bytes], ...]]:
    root = get_root(evidence, root_type, root_id)
    envelope = evidence.get_envelope(root.manifest_id)
    artifacts = tuple(
        (
            artifact.to_dict(),
            evidence.read_artifact(
                artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
            ),
        )
        for artifact in envelope.artifacts
    )
    return root.to_dict(), envelope.to_dict(), artifacts


def test_public_finalization_workflow_journey(
    persisted_case: PersistedCase,
) -> None:
    """Exercise finalization refusals, deadline paths, and the terminal retry."""

    case = persisted_case
    operation = "acceptance.attempt.begin"
    checkpoint_operation = "acceptance.attempt.checkpoint"
    attempt_id = "00000000-0000-4000-8000-000000000340"
    request_before = deepcopy(case.request)

    predecessor_id = str(case.request["predecessorAttemptId"])
    predecessor_root = get_root(
        case.evidence,
        "acceptance-attempt",
        _journey_root_id(predecessor_id, 6),
    )
    predecessor_envelope = case.evidence.get_envelope(predecessor_root.manifest_id)
    predecessor_attempt = predecessor_envelope.metadata["attempt"]
    assert isinstance(predecessor_attempt, Mapping)
    predecessor_deadline = str(predecessor_attempt["deadlineAtUtc"])

    started_wire = _journey_wire(_begin(case, attempt_id))
    started_data = started_wire["data"]
    assert isinstance(started_data, Mapping)
    started_attempt = started_data["attempt"]
    assert isinstance(started_attempt, Mapping)
    _journey_success(started_wire, operation, started_data)
    assert case.request == request_before
    assert started_attempt["schema"] == FINALIZATION_ATTEMPT_SCHEMA
    assert started_attempt["attemptId"] == attempt_id
    assert started_attempt["revision"] == 0
    assert started_attempt["status"] == "IN_PROGRESS"
    assert started_attempt["stage"] == "verification-pending"
    assert started_attempt["scenarioId"] == FINALIZATION_SCENARIO_ID
    assert started_attempt["scenarioVersion"] == FINALIZATION_SCENARIO_VERSION
    assert started_attempt["projectOrigin"] == FINALIZATION_PROJECT_ORIGIN
    assert started_attempt["executionSource"] == FINALIZATION_EXECUTION_SOURCE
    assert started_attempt["physicalTransportEvidence"] is True
    assert started_attempt["openedAtUtc"] == SAFE_TIME
    assert started_attempt["updatedAtUtc"] == SAFE_TIME
    assert started_attempt["deadlineAtUtc"] == (
        datetime.strptime(SAFE_TIME, "%Y-%m-%dT%H:%M:%S.%fZ")
        + timedelta(seconds=FINALIZATION_WINDOW_SECONDS)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert predecessor_deadline < SAFE_TIME < str(started_attempt["deadlineAtUtc"])

    proof = _proof(case, started_attempt)
    assert proof.fixed_after_test_run_id == case.request["fixedAfterTestRunId"]
    assert proof.fixed_after_evidence_id == case.request["fixedAfterEvidenceId"]
    proof_resource = _journey_resource_snapshot(
        case.evidence, FINALIZATION_ROOT_TYPE, proof.continuation_id
    )
    checkpoint_base: dict[str, object] = {
        "context": _context(case),
        "attempt_id": attempt_id,
        "expected_revision": 0,
        "stage": "target-fix-verified",
        "test_run_id": proof.fixed_after_test_run_id,
        "diagnostic_session_id": proof.diagnostic_session_id,
        "acceptance_record_id": None,
        "source_change_intent": None,
        "fix_verification_id": proof.fix_verification_id,
    }
    different_fix_id = "0" * 64
    if different_fix_id == proof.fix_verification_id:
        different_fix_id = "1" * 64
    checkpoint_variants = (
        ("revision-one", {"expected_revision": 1}, "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT"),
        ("revision-bool", {"expected_revision": True}, "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT"),
        ("stage", {"stage": "verification-pending"}, "ACCEPTANCE_ATTEMPT_STAGE_INVALID"),
        (
            "acceptance-record",
            {"acceptance_record_id": "a" * 64},
            "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        ),
        (
            "source-intent",
            {"source_change_intent": "b" * 64},
            "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        ),
        (
            "invalid-diagnostic",
            {"diagnostic_session_id": "not-a-diagnostic-id"},
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
        ),
        (
            "wrong-run",
            {"test_run_id": physical_fixture.PHYSICAL_FAILED_RUN},
            "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        ),
        (
            "wrong-diagnostic",
            {"diagnostic_session_id": "8" * 32},
            "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        ),
        ("wrong-fix", {"fix_verification_id": different_fix_id}, "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"),
    )
    for _name, changes, expected_code in checkpoint_variants:
        call = dict(checkpoint_base)
        call.update(changes)
        before = _persisted_snapshot(case)
        checkpoint_wire = _journey_wire(
            checkpoint_acceptance_attempt(**call)
        )
        _journey_failure(checkpoint_wire, checkpoint_operation, expected_code)
        assert _persisted_snapshot(case) == before

    conflict_request = deepcopy(case.request)
    conflict_request["diagnosticEventHead"] = "0" * 64
    if conflict_request["diagnosticEventHead"] == case.request["diagnosticEventHead"]:
        conflict_request["diagnosticEventHead"] = "1" * 64
    conflict_before = _persisted_snapshot(case)
    conflict_wire = _journey_wire(
        begin_acceptance_attempt(
            _context(case),
            attempt_id=attempt_id,
            scenario_id=SCENARIO,
            scenario_version=VERSION,
            continuation=conflict_request,
        )
    )
    _journey_failure(conflict_wire, operation, "ACCEPTANCE_ATTEMPT_CONFLICT")
    assert conflict_request != case.request
    assert _persisted_snapshot(case) == conflict_before

    def begin_fresh(fresh_id: str) -> Mapping[str, object]:
        wire = _journey_wire(_begin(case, fresh_id))
        data = wire["data"]
        assert isinstance(data, Mapping)
        attempt = data["attempt"]
        assert isinstance(attempt, Mapping)
        _journey_success(wire, operation, data)
        return attempt

    def run_timed_out_variant(
        fresh_id: str, clock_values: tuple[str, ...]
    ) -> None:
        fresh_attempt = begin_fresh(fresh_id)
        fresh_deadline = str(fresh_attempt["deadlineAtUtc"])
        assert predecessor_deadline < SAFE_TIME < fresh_deadline < LATE_TIME
        before = _persisted_snapshot(case)
        calls: list[str] = []
        values = iter(clock_values)

        def clock() -> str:
            value = next(values)
            calls.append(value)
            return value

        call = dict(checkpoint_base)
        call["context"] = _context(case, clock=clock)
        call["attempt_id"] = fresh_id
        timed_out_wire = _journey_wire(checkpoint_acceptance_attempt(**call))
        _journey_failure(
            timed_out_wire,
            checkpoint_operation,
            "ACCEPTANCE_ATTEMPT_TIMED_OUT",
        )
        assert tuple(calls) == clock_values
        assert _persisted_snapshot(case) == before
        with pytest.raises(EvidenceValidationError):
            get_root(
                case.evidence,
                "acceptance-attempt",
                _journey_root_id(fresh_id, 1),
            )

    run_timed_out_variant(
        "00000000-0000-4000-8000-000000000341",
        (SAFE_TIME, SAFE_TIME, LATE_TIME),
    )
    run_timed_out_variant(
        "00000000-0000-4000-8000-000000000342",
        (SAFE_TIME, SAFE_TIME, SAFE_TIME, SAFE_TIME, LATE_TIME),
    )

    valid_id = "00000000-0000-4000-8000-000000000343"
    begin_fresh(valid_id)
    valid_root0_resource = _journey_resource_snapshot(
        case.evidence, "acceptance-attempt", _journey_root_id(valid_id, 0)
    )
    valid_before = _persisted_snapshot(case)
    valid_wire = _journey_wire(_checkpoint(case, valid_id, proof))
    valid_data = valid_wire["data"]
    assert isinstance(valid_data, Mapping)
    completed_attempt = valid_data["attempt"]
    assert isinstance(completed_attempt, Mapping)
    _journey_success(valid_wire, checkpoint_operation, valid_data)
    assert completed_attempt["attemptId"] == valid_id
    assert completed_attempt["revision"] == 1
    assert completed_attempt["status"] == "COMPLETED"
    assert completed_attempt["stage"] == "target-fix-verified"
    assert completed_attempt["fixVerificationId"] == proof.fix_verification_id
    assert _persisted_snapshot(case) != valid_before
    assert _journey_resource_snapshot(
        case.evidence, FINALIZATION_ROOT_TYPE, proof.continuation_id
    ) == proof_resource
    assert _journey_resource_snapshot(
        case.evidence, "acceptance-attempt", _journey_root_id(valid_id, 0)
    ) == valid_root0_resource
    valid_root1_resource = _journey_resource_snapshot(
        case.evidence, "acceptance-attempt", _journey_root_id(valid_id, 1)
    )
    assert valid_root1_resource[0]["root_id"] == _journey_root_id(valid_id, 1)

    show_wire = _journey_wire(
        show_acceptance_attempt(_context(case), attempt_id=valid_id)
    )
    _journey_success(
        show_wire,
        "acceptance.attempt.show",
        {"authoritative": True, "attempt": dict(completed_attempt)},
    )
    resume_wire = _journey_wire(
        resume_acceptance_attempt(_context(case), attempt_id=valid_id)
    )
    _journey_success(
        resume_wire,
        "acceptance.attempt.resume",
        {
            "authoritative": True,
            "attempt": dict(completed_attempt),
            "nextStage": None,
            "authorizationRequired": False,
            "actionDigest": None,
            "timedOut": False,
            "recoveryPolicy": finalization_policy_document(),
        },
    )

    retry_before = _persisted_snapshot(case)
    retry_wire = _journey_wire(_checkpoint(case, valid_id, proof))
    retry_data = retry_wire["data"]
    assert isinstance(retry_data, Mapping)
    _journey_success(retry_wire, checkpoint_operation, retry_data)
    assert retry_data == {"attempt": dict(completed_attempt)}
    assert _persisted_snapshot(case) == retry_before

    begin_retry_wire = _journey_wire(_begin(case, valid_id))
    begin_retry_data = begin_retry_wire["data"]
    assert isinstance(begin_retry_data, Mapping)
    _journey_success(begin_retry_wire, operation, begin_retry_data)
    assert begin_retry_data == {"attempt": dict(completed_attempt)}
    assert _persisted_snapshot(case) == retry_before

    late_begin_before = _persisted_snapshot(case)
    late_begin_wire = _journey_wire(
        begin_acceptance_attempt(
            _context(case),
            attempt_id=valid_id,
            scenario_id=SCENARIO,
            scenario_version=VERSION,
            continuation=conflict_request,
        )
    )
    _journey_failure(late_begin_wire, operation, "ACCEPTANCE_ATTEMPT_CONFLICT")
    assert _persisted_snapshot(case) == late_begin_before
