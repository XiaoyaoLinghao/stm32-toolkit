from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_plan,
    diagnostic_assess_hypothesis,
    diagnostic_begin,
    diagnostic_declare_source_change,
    diagnostic_run_plan,
    diagnostic_start,
)
from stm32_toolkit.diagnostics import SourceChangeDeclaration
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing_workflows import (
    TargetWorkflowSeams,
    TestingWorkflowContext,
    target_test_execute,
    target_test_prepare,
)
from test_flash import _publish_current_debug_build
from test_physical_target_workflows import (
    CASES,
    RAW_PROBE,
    _Board,
    _fixed_v2_stream,
    _SourceChangeBackend,
)
from test_risk_recovery_public_producers import _initialize_git, _write_project

ATTEMPT_ID = "00000000-0000-4000-8000-000000000101"
SESSION_ID = "s18-physical-checkpoint-retry"
SCENARIO_ID = "legacy-keil-physical-repair"
SCENARIO_VERSION = "1"
TARGET_PROTOCOL = "stm32-target-frame/2"


def _ok(result: object) -> Mapping[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return data


def _wire(result: object) -> dict[str, object]:
    serializer = getattr(result, "to_dict", None)
    assert callable(serializer)
    value = serializer()
    assert isinstance(value, dict)
    return value


def _files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _trees(
    project_root: Path, data_root: Path
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    return _files(project_root), _files(data_root)


def _assert_attempt_retry(
    context: AcceptanceRecoveryContext,
    *,
    expected_wire: dict[str, object],
    expected_attempt: Mapping[str, object],
    expected_project: Path,
    expected_data: Path,
    retry_call,
) -> None:
    before = _trees(expected_project, expected_data)
    retried = retry_call()
    assert _wire(retried) == expected_wire
    assert _trees(expected_project, expected_data) == before

    shown = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    shown_data = _ok(shown)
    assert shown_data["attempt"] == expected_attempt
    assert _trees(expected_project, expected_data) == before

    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    resumed_data = _ok(resumed)
    assert resumed_data["attempt"] == expected_attempt
    assert _trees(expected_project, expected_data) == before


def _public_failed_target_run(
    project_root: Path,
    data_root: Path,
    build: Mapping[str, object],
) -> tuple[Mapping[str, object], list[tuple[object, ...]]]:
    events: list[tuple[object, ...]] = []
    board = _Board()
    model = load_project_model(project_root)
    assert model.memory.source == "keil"
    assert model.testing.target.protocol == TARGET_PROTOCOL
    declared_sources = tuple(model.build.sources)
    assert declared_sources
    assert all((project_root / source).is_file() for source in declared_sources)
    elf_path = project_root / "build" / "arm-debug" / "firmware.elf"
    flash_segment = elf_path.read_bytes()[84:404]

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": str(model.debug.target),
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": hashlib.sha256(
                    RAW_PROBE.encode("utf-8")
                ).hexdigest(),
            },
            stream=_fixed_v2_stream(case_state="failed"),
            flash_segment=flash_segment,
            events=events,
        )

    context = TestingWorkflowContext(project_root, data_root, SESSION_ID)
    seams = TargetWorkflowSeams(_test_backend_factory=backend_factory)
    prepared = asyncio.run(
        target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            _seams=seams,
        )
    )
    prepared_data = _ok(prepared)
    assert prepared_data["case_ids"] == list(CASES)
    action_digest = prepared_data["authorized_action_digest"]
    assert isinstance(action_digest, str) and len(action_digest) == 64

    executed = asyncio.run(
        target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=action_digest,
            _seams=seams,
        )
    )
    executed_data = _ok(executed)
    run = executed_data["run"]
    assert isinstance(run, Mapping)
    assert run["state"] == "failed"
    assert executed_data["execution_source"] == "physical"
    assert executed_data["physical_transport_evidence"] is True
    assert executed_data["origin_workspace_id"] == executed_data["import_workspace_id"]
    assert events
    assert any(event[:2] == ("flash", "modify") for event in events)
    assert any(event[:2] == ("transport.read", "modify") for event in events)
    return executed_data, events


def _diagnostic_prefix(
    project_root: Path,
    data_root: Path,
    failed_run_id: str,
) -> tuple[DiagnosticWorkflowContext, str, str]:
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, SESSION_ID)
    started = _ok(
        diagnostic_start(
            diagnostic,
            operation_id="s18-diagnostic-start",
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
            operation_id="s18-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id="s18-hypothesis-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=2,
            statement="the public failed target run identifies the changed source path",
        )
    )["hypothesis"]
    assert isinstance(hypothesis, Mapping)
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = _ok(
        diagnostic_add_plan(
            diagnostic,
            operation_id="s18-observation-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "failed-target-run",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "confirm the public failed target run",
                }
            ],
        )
    )["observation_plan"]
    assert isinstance(plan, Mapping)
    plan_id = str(plan["plan_id"])
    _ok(
        diagnostic_run_plan(
            diagnostic,
            operation_id="s18-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    _ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="s18-hypothesis-assess",
            diagnostic_session_id=diagnostic_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="failed-target-run",
            polarity="supports",
            rationale="the public failed target run supports the source-change hypothesis",
        )
    )
    return diagnostic, diagnostic_id, hypothesis_id


def _public_source_declaration(
    project_root: Path,
    data_root: Path,
    *,
    before_identity: object,
    after_build: Mapping[str, object],
    before_snapshot_sha256: str,
    after_snapshot_sha256: str,
    changed_path: str,
    before_source: bytes,
    after_source: bytes,
    hypothesis_id: str,
) -> SourceChangeDeclaration:
    assert after_build["inputSnapshotSha256"] == after_snapshot_sha256
    workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        UUID(str(before_identity.project_id)),
        SESSION_ID,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    diff_path = project_root.parent / "s18-source-change.diff"
    diff_text = "".join(
        difflib.unified_diff(
            before_source.decode("utf-8").splitlines(keepends=True),
            after_source.decode("utf-8").splitlines(keepends=True),
            fromfile=f"a/{changed_path}",
            tofile=f"b/{changed_path}",
        )
    )
    diff_path.write_bytes(diff_text.encode("utf-8"))
    diff_artifact = evidence.ingest_file(
        diff_path,
        kind="source-diff",
        media_type="text/x-diff",
    )
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-09-22T00:00:00.000000Z",
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    return SourceChangeDeclaration.new(
        before_source_sha256=before_snapshot_sha256,
        after_source_sha256=after_snapshot_sha256,
        before_build_id=str(before_identity.build_id),
        before_elf_sha256=str(before_identity.elf_sha256),
        after_build_id=str(after_build["buildId"]),
        after_elf_sha256=str(after_build["elfSha256"]),
        changed_paths=(changed_path,),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )


def test_public_physical_checkpoint_retries_preserve_authority_and_wire(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    manifest_path = project_root / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["testing"]["target"]["executable"] = "build/arm-debug/firmware.elf"
    manifest["testing"]["target"]["protocol"] = TARGET_PROTOCOL
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    _initialize_git(project_root)
    before_build = _publish_current_debug_build(project_root)
    data_root = tmp_path / "data"
    executed, _events = _public_failed_target_run(project_root, data_root, before_build)
    run = executed["run"]
    assert isinstance(run, Mapping)
    failed_run_id = str(run["run_id"])

    workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        UUID(str(before_build["logicalProjectId"])),
        SESSION_ID,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    failed_run = TestRunRepository(evidence).load(failed_run_id)
    before_identity = failed_run.manifest.identity
    before_snapshot = snapshot_project_inputs(load_project_model(project_root))
    assert before_identity.input_snapshot_sha256 == before_snapshot.sha256
    assert before_identity.build_id == str(before_build["buildId"])
    assert before_identity.elf_sha256 == str(before_build["elfSha256"])

    diagnostic, diagnostic_id, hypothesis_id = _diagnostic_prefix(
        project_root,
        data_root,
        failed_run_id,
    )
    context = AcceptanceRecoveryContext(
        project_root,
        data_root,
        SESSION_ID,
        clock=lambda: "2026-09-22T00:00:00.000000Z",
    )
    begun = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id=SCENARIO_ID,
        scenario_version=SCENARIO_VERSION,
    )
    begun_data = _ok(begun)
    assert begun_data["attempt"]["revision"] == 0

    project_materialized = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    project_materialized_data = _ok(project_materialized)
    project_materialized_attempt = project_materialized_data["attempt"]
    assert isinstance(project_materialized_attempt, Mapping)
    _assert_attempt_retry(
        context,
        expected_wire=_wire(project_materialized),
        expected_attempt=project_materialized_attempt,
        expected_project=project_root,
        expected_data=data_root,
        retry_call=lambda: checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=0,
            stage="project-materialized",
        ),
    )

    firmware_before = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    firmware_before_data = _ok(firmware_before)
    firmware_before_attempt = firmware_before_data["attempt"]
    assert isinstance(firmware_before_attempt, Mapping)
    assert (
        firmware_before_attempt["stageOutputs"]["beforeBuildId"]
        == before_build["buildId"]
    )
    _assert_attempt_retry(
        context,
        expected_wire=_wire(firmware_before),
        expected_attempt=firmware_before_attempt,
        expected_project=project_root,
        expected_data=data_root,
        retry_call=lambda: checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=1,
            stage="firmware-built-before",
        ),
    )

    target_failure = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=failed_run_id,
    )
    target_failure_data = _ok(target_failure)
    target_failure_attempt = target_failure_data["attempt"]
    assert isinstance(target_failure_attempt, Mapping)
    assert (
        target_failure_attempt["stageOutputs"]["failedBeforeTestRunId"] == failed_run_id
    )
    _assert_attempt_retry(
        context,
        expected_wire=_wire(target_failure),
        expected_attempt=target_failure_attempt,
        expected_project=project_root,
        expected_data=data_root,
        retry_call=lambda: checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=2,
            stage="target-failure-observed",
            test_run_id=failed_run_id,
        ),
    )

    model_before_source_edit = load_project_model(project_root)
    declared_sources = tuple(model_before_source_edit.build.sources)
    assert declared_sources
    changed_path = declared_sources[0]
    source_path = project_root / changed_path
    assert source_path.is_file()
    before_source = source_path.read_bytes()
    before_entries = {str(entry.path): entry for entry in before_snapshot.entries}
    before_entry = before_entries[changed_path]
    before_entry_sha256 = str(before_entry.sha256)
    after_source = b"int main(void) { return 1; }\r\n"
    intent_input = {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": changed_path,
                "beforeSha256": before_entry_sha256,
                "afterSha256": hashlib.sha256(after_source).hexdigest(),
                "afterSize": len(after_source),
            }
        ],
    }
    diagnosis = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=diagnostic_id,
        source_change_intent=intent_input,
    )
    diagnosis_data = _ok(diagnosis)
    diagnosis_attempt = diagnosis_data["attempt"]
    assert isinstance(diagnosis_attempt, Mapping)
    _assert_attempt_retry(
        context,
        expected_wire=_wire(diagnosis),
        expected_attempt=diagnosis_attempt,
        expected_project=project_root,
        expected_data=data_root,
        retry_call=lambda: checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=3,
            stage="diagnosis-completed",
            diagnostic_session_id=diagnostic_id,
            source_change_intent=intent_input,
        ),
    )

    resumed = _ok(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    action_digest = resumed["actionDigest"]
    assert isinstance(action_digest, str) and len(action_digest) == 64
    authorized = _ok(
        authorize_acceptance_source_change(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=4,
            action_digest=action_digest,
            authorized=True,
        )
    )
    assert authorized["attempt"]["revision"] == 5

    source_path.write_bytes(after_source)
    subprocess.run(
        ["git", "add", changed_path],
        cwd=project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tk-test",
            "-c",
            "user.email=tk-test@example.com",
            "commit",
            "-q",
            "-m",
            "s18 source change",
        ],
        cwd=project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    after_build = _publish_current_debug_build(project_root)
    after_snapshot = snapshot_project_inputs(load_project_model(project_root))
    assert after_snapshot.sha256 != before_snapshot.sha256
    declaration = _public_source_declaration(
        project_root,
        data_root,
        before_identity=before_identity,
        after_build=after_build,
        before_snapshot_sha256=before_snapshot.sha256,
        after_snapshot_sha256=after_snapshot.sha256,
        changed_path=changed_path,
        before_source=before_source,
        after_source=after_source,
        hypothesis_id=hypothesis_id,
    )
    declared = _ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id="s18-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=declaration,
        )
    )
    assert declared["session"]["revision"] == 7

    firmware_after = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    firmware_after_data = _ok(firmware_after)
    firmware_after_attempt = firmware_after_data["attempt"]
    assert isinstance(firmware_after_attempt, Mapping)
    assert (
        firmware_after_attempt["stageOutputs"]["afterBuildId"] == after_build["buildId"]
    )
    _assert_attempt_retry(
        context,
        expected_wire=_wire(firmware_after),
        expected_attempt=firmware_after_attempt,
        expected_project=project_root,
        expected_data=data_root,
        retry_call=lambda: checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=5,
            stage="firmware-built-after",
        ),
    )

    final_show = _ok(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    assert final_show["attempt"] == firmware_after_attempt
    final_resume = _ok(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    assert final_resume["attempt"] == firmware_after_attempt
    assert final_resume["nextStage"] == "target-fix-verified"
    assert before_source != after_source
