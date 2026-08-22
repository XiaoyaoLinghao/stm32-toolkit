from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from test_physical_publication import (
    _append_physical_history,
    _physical_context,
    _publish_physical_test_run,
)

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import (
    AnalysisPublication,
    compare_monitor_runs,
    export_analysis_bundle,
)
from stm32_monitor.replay import load_monitor_run_reference, publish_physical_monitor_run
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_verification_plan,
    diagnostic_attach_marker,
    diagnostic_begin,
    diagnostic_complete_verification,
    diagnostic_declare_source_change,
    diagnostic_start,
    diagnostic_start_verification,
    diagnostic_show,
    diagnostic_show_verification,
)
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.testing.publication import TestRunRepository


def _ok(result: object) -> Mapping[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return data


def _publish_window(
    paths: object,
    evidence: EvidenceStore,
    *,
    test_run_id: str,
    monitor_run_id: UUID,
    group_id: UUID,
    scenario_role: str,
    state: str,
    value_offset: int,
    build_id: str,
    elf_sha256: str,
    input_snapshot_sha256: str,
    git_head: str,
    raw_probe: str,
) -> object:
    _publish_physical_test_run(
        paths,  # type: ignore[arg-type]
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
        state=state,
        build_id=build_id,
        elf_sha256=elf_sha256,
        input_snapshot_sha256=input_snapshot_sha256,
        git_head=git_head,
    )
    batches = _append_physical_history(
        paths,  # type: ignore[arg-type]
        raw_probe,
        monitor_run_id,
        group_id,
        scenario_role=scenario_role,
        value_offset=value_offset,
        build_id=build_id,
        elf_sha256=elf_sha256,
        input_snapshot_sha256=input_snapshot_sha256,
        git_head=git_head,
    )
    publish_physical_monitor_run(
        paths,  # type: ignore[arg-type]
        evidence,
        scenario_role=scenario_role,
        test_run_id=test_run_id,
        run_id=str(monitor_run_id),
        group_id=str(group_id),
        start_sequence=batches[0].sequence,
        end_sequence_exclusive=batches[-1].sequence + 1,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    return batches


def test_vs04b2_physical_diagnostic_survives_fresh_reload(tmp_path: Path, monkeypatch) -> None:
    paths, evidence, failed_test_run_id, raw_probe, failed_run_id, failed_group_id = (
        _physical_context(tmp_path)
    )
    fixed_test_run_id = "physical-test-run-02"
    fixed_run_id = UUID("33333333-3333-4333-8333-333333333333")
    fixed_group_id = UUID("44444444-4444-4444-8444-444444444444")
    fixed_build_id = "0" * 64
    fixed_elf_sha256 = "1" * 64
    fixed_input_snapshot_sha256 = "2" * 64
    fixed_git_head = "f" * 40

    _publish_window(
        paths,
        evidence,
        test_run_id=failed_test_run_id,
        monitor_run_id=failed_run_id,
        group_id=failed_group_id,
        scenario_role="failed-before",
        state="failed",
        value_offset=0,
        build_id="b" * 64,
        elf_sha256="c" * 64,
        input_snapshot_sha256="d" * 64,
        git_head="e" * 40,
        raw_probe=raw_probe,
    )
    _publish_window(
        paths,
        evidence,
        test_run_id=fixed_test_run_id,
        monitor_run_id=fixed_run_id,
        group_id=fixed_group_id,
        scenario_role="fixed-after",
        state="passed",
        value_offset=10,
        build_id=fixed_build_id,
        elf_sha256=fixed_elf_sha256,
        input_snapshot_sha256=fixed_input_snapshot_sha256,
        git_head=fixed_git_head,
        raw_probe=raw_probe,
    )
    before_ref = load_monitor_run_reference(paths, evidence, str(failed_run_id))
    after_ref = load_monitor_run_reference(paths, evidence, str(fixed_run_id))
    repository = TestRunRepository(evidence)
    failed = repository.load(failed_test_run_id)
    fixed = repository.load(fixed_test_run_id)

    diff_path = paths.project_root / "source-change.diff"
    diff_path.write_bytes(b"--- a/src/main.c\n+++ b/src/main.c\n")
    diff_artifact = evidence.ingest_file(diff_path, kind="source-diff", media_type="text/x-diff")
    diff_identity = fixed.manifest.identity
    diff_envelope = EvidenceEnvelope(
        identity=diff_identity,
        operation="diagnostic-source-change",
        produced_at_utc=fixed.manifest.ended_at_utc,
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    declaration = SourceChangeDeclaration.new(
        before_source_sha256=failed.manifest.identity.input_snapshot_sha256,
        after_source_sha256=fixed.manifest.identity.input_snapshot_sha256,
        before_build_id=failed.manifest.identity.build_id,
        before_elf_sha256=failed.manifest.identity.elf_sha256,
        after_build_id=fixed.manifest.identity.build_id,
        after_elf_sha256=fixed.manifest.identity.elf_sha256,
        changed_paths=("src/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=("a" * 32,),
        validation_plan_id="b" * 64,
    )

    context = DiagnosticWorkflowContext(paths.project_root, paths.data_root, paths.session_id)
    started = _ok(
        diagnostic_start(
            context,
            operation_id="b2-diagnostic-start",
            failed_test_run_id=failed_test_run_id,
            failed_run_mode="target",
        )
    )
    session = started["session"]
    assert isinstance(session, Mapping)
    diagnostic_session_id = str(session["diagnostic_session_id"])
    _ok(
        diagnostic_begin(
            context,
            operation_id="b2-diagnostic-begin",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            context,
            operation_id="b2-hypothesis-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=2,
            statement="the physical fixed run changes the observed counter",
        )
    )["hypothesis"]
    assert isinstance(hypothesis, Mapping)
    hypothesis_id = str(hypothesis["hypothesis_id"])
    declaration = SourceChangeDeclaration.new(
        before_source_sha256=declaration.before_source_sha256,
        after_source_sha256=declaration.after_source_sha256,
        before_build_id=declaration.before_build_id,
        before_elf_sha256=declaration.before_elf_sha256,
        after_build_id=declaration.after_build_id,
        after_elf_sha256=declaration.after_elf_sha256,
        changed_paths=declaration.changed_paths,
        diff_evidence_id=declaration.diff_evidence_id,
        diff_artifact=declaration.diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id=declaration.validation_plan_id,
    )
    _ok(
        diagnostic_declare_source_change(
            context,
            operation_id="b2-source-change",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=3,
            source_change_declaration=declaration,
        )
    )

    request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=before_ref,
        after_run=after_ref,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    )
    monkeypatch.setattr(
        "stm32_monitor.analysis_workflows.HistoryStore",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("physical B2 flow must not query History")
        ),
    )
    publication = compare_monitor_runs(
        paths,
        evidence,
        request,
        diagnostic_session_id,
        hypothesis_id,
        "supports",
        "the physical fixed run changes the observed counter",
        declaration,
    )
    assert isinstance(publication, AnalysisPublication)
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.conclusion == "COMPLETED"
    assert publication.analysis_result.changed is True
    bundle, bundle_ref = export_analysis_bundle(
        paths,
        evidence,
        request,
        publication,
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    retry_bundle, retry_ref = export_analysis_bundle(
        paths,
        EvidenceStore(paths.workspace_root / "evidence"),
        request,
        AnalysisPublication.from_value(publication.to_dict()),
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    assert (retry_bundle, retry_ref) == (bundle, bundle_ref)
    assert b"probe/serial/01" not in bundle

    plan = VerificationPlan.new(
        verification_plan_id=declaration.validation_plan_id,
        diagnostic_session_id=diagnostic_session_id,
        failed_before_run_id=failed_test_run_id,
        failed_before_evidence_id=str(failed.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=fixed_test_run_id,
        fixed_after_evidence_id=str(fixed.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    _ok(
        diagnostic_add_verification_plan(
            context,
            operation_id="b2-plan-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=4,
            verification_plan=plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            context,
            operation_id="b2-verification-start",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=5,
            verification_plan_id=plan.verification_plan_id,
        )
    )
    _ok(
        diagnostic_attach_marker(
            context,
            operation_id="b2-marker-attach",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=6,
            diagnostic_marker_ref=publication.diagnostic_marker_ref,
        )
    )
    completed = _ok(
        diagnostic_complete_verification(
            context,
            operation_id="b2-verification-complete",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=7,
            executed_operation_ids=[
                "physical-failed",
                "physical-fixed",
                "monitor.analysis.compare",
                "monitor.analysis.bundle",
            ],
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == "PASSED"
    assert verification["reason_code"] == "VERIFICATION_PASSED"
    assert completed["session"]["state"] == "RESOLVED"

    assert json.loads(bundle.decode("utf-8"))["before_run"]["schema"] == "stm32-monitor-run-ref/2"

    fresh_evidence = EvidenceStore(paths.workspace_root / "evidence")
    fresh_repository = TestRunRepository(fresh_evidence)
    assert fresh_repository.load(failed_test_run_id).manifest.run_id == failed_test_run_id
    assert fresh_repository.load(fixed_test_run_id).manifest.run_id == fixed_test_run_id
    assert load_monitor_run_reference(paths, fresh_evidence, str(failed_run_id)) == before_ref
    assert load_monitor_run_reference(paths, fresh_evidence, str(fixed_run_id)) == after_ref
    fresh_context = DiagnosticWorkflowContext(
        paths.project_root, paths.data_root, paths.session_id
    )
    shown = _ok(
        diagnostic_show(
            fresh_context,
            diagnostic_session_id=diagnostic_session_id,
        )
    )
    assert shown["session"]["state"] == "RESOLVED"
    shown_verification = _ok(
        diagnostic_show_verification(
            fresh_context,
            diagnostic_session_id=diagnostic_session_id,
        )
    )
    assert shown_verification["fix_verifications"][0]["reason_code"] == "VERIFICATION_PASSED"
