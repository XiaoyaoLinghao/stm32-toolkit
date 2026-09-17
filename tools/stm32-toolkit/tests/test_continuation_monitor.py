"""Persisted software fixtures only: these tests never access physical hardware."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from test_acceptance_continuation import prepare_pair, _ok, CONTINUATION_ATTEMPT_ID
import test_acceptance_physical_recovery as physical_fixture
from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import (
    AnalysisPublication, AnalysisWorkflowError, compare_monitor_runs, export_analysis_bundle,
)
from stm32_monitor.replay import publish_physical_monitor_run
from stm32_toolkit.acceptance.continuation import authenticate_continuation
from stm32_toolkit.acceptance.recovery_workflows import (
    begin_acceptance_attempt, checkpoint_acceptance_attempt, resume_acceptance_attempt,
)
from stm32_toolkit.diagnostic_workflows import (
    diagnostic_add_verification_plan, diagnostic_start_verification, diagnostic_attach_marker,
    diagnostic_complete_verification, diagnostic_show,
)
from stm32_toolkit.diagnostics import VerificationPlan
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import get_root
from stm32_toolkit.evidence.gc import plan_gc
from stm32_toolkit.evidence.store import EvidenceStore


def test_persisted_continuation_monitor_diagnostic_and_expired_attempt_reuse(tmp_path, monkeypatch):
    pair = prepare_pair(tmp_path, monkeypatch)
    original_roots = {p: p.read_bytes() for p in (pair.evidence.root / "roots" / "acceptance-attempt").glob("*.json")}
    attempt = _ok(begin_acceptance_attempt(pair.context, attempt_id=CONTINUATION_ATTEMPT_ID,
        scenario_id="legacy-keil-physical-repair", scenario_version="1", continuation=pair.bind_request))["attempt"]
    continuation_id = attempt["continuationEvidenceId"]

    # A new process loads the same accepted roots without inheriting any test
    # reader monkeypatch or in-memory proof object.
    process = subprocess.run([sys.executable, "-B", "-m", "stm32_toolkit.cli", "scenario", "attempt", "show",
        "--project-root", str(pair.project_root), "--data-root", str(pair.data_root),
        "--session-id", pair.before_session_id, "--attempt-id", CONTINUATION_ATTEMPT_ID, "--json"],
        capture_output=True, text=True, encoding="utf-8", check=False, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout)["data"]["attempt"] == attempt

    refs = []
    for role, workspace, identity, run_id, offset in (
        ("failed-before", pair.before_workspace, pair.before_identity, pair.failed_run_id, 0),
        ("fixed-after", pair.after_workspace, pair.after_identity, pair.fixed_run_id, 10),
    ):
        monitor_id = physical_fixture.vs08a_fixtures.MONITOR_OPERATION_IDS[role]
        batches = physical_fixture._append_physical_monitor_history(workspace, identity,
            physical_fixture.PHYSICAL_RAW_PROBE, f"flash-{run_id}", f"lease-{run_id}", monitor_id,
            value_offset=offset)
        refs.append(publish_physical_monitor_run(workspace, pair.evidence,
            scenario_role=role, test_run_id=run_id, run_id=monitor_id, group_id=str(batches[0].group_id),
            start_sequence=batches[0].sequence, end_sequence_exclusive=batches[-1].sequence + 1,
            start_captured_unix_ns=batches[0].captured_unix_ns,
            end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
            probe_id=physical_fixture.PHYSICAL_RAW_PROBE))
    request = AnalysisRequest(schema="stm32-monitor-analysis-request/1", before_run=refs[0], after_run=refs[1],
        selector_kind="variable", selector="counter", alignment="run-relative", minimum_valid_pairs=2)
    compare_args = (pair.before_workspace, pair.evidence, request, pair.diagnostic_session_id,
        pair.hypothesis_id, "supports", "the fixed fixture changes the counter", pair.declaration)
    with pytest.raises(AnalysisWorkflowError):
        compare_monitor_runs(*compare_args)
    assert not (pair.evidence.root / "roots" / "monitor-analysis").exists()
    publication = compare_monitor_runs(*compare_args, continuation_evidence_id=continuation_id)
    assert publication.analysis_result.schema == "stm32-monitor-analysis/2"
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.changed is True
    assert publication.analysis_result.identity.before_session_id == pair.before_session_id
    assert publication.analysis_result.identity.after_session_id == pair.after_session_id
    fresh_evidence = EvidenceStore(pair.evidence.root)
    bundle_args = (pair.before_workspace, fresh_evidence, request,
        AnalysisPublication.from_value(publication.to_dict()), pair.failed_run_id, pair.fixed_run_id, pair.declaration)
    bundle, bundle_ref = export_analysis_bundle(*bundle_args, continuation_evidence_id=continuation_id)
    assert export_analysis_bundle(*bundle_args, continuation_evidence_id=continuation_id) == (bundle, bundle_ref)
    with pytest.raises(AnalysisWorkflowError):
        export_analysis_bundle(*bundle_args)
    assert json.loads(bundle)["analysis_result"]["identity"]["continuation_evidence_id"] == continuation_id
    analysis_envelope = fresh_evidence.get_envelope(publication.analysis_evidence_ref.evidence_id)
    assert analysis_envelope.identity == pair.after_identity
    assert analysis_envelope.parents[-1] == continuation_id

    plan = VerificationPlan.new(verification_plan_id=pair.declaration.validation_plan_id,
        diagnostic_session_id=pair.diagnostic_session_id, failed_before_run_id=pair.failed_run_id,
        failed_before_evidence_id=str(pair.failed_physical.envelope.evidence_id),
        source_change_declaration_id=pair.declaration.declaration_id, fixed_after_run_id=pair.fixed_run_id,
        fixed_after_evidence_id=str(pair.fixed_physical.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID", expected_changed=True, continuation_evidence_id=continuation_id)
    revision = pair.diagnostic_revision
    _ok(diagnostic_add_verification_plan(pair.diagnostic, operation_id="continuation-plan",
        diagnostic_session_id=pair.diagnostic_session_id, expected_revision=revision, verification_plan=plan))
    _ok(diagnostic_start_verification(pair.diagnostic, operation_id="continuation-start",
        diagnostic_session_id=pair.diagnostic_session_id, expected_revision=revision + 1,
        verification_plan_id=plan.verification_plan_id))
    _ok(diagnostic_attach_marker(pair.diagnostic, operation_id="continuation-marker",
        diagnostic_session_id=pair.diagnostic_session_id, expected_revision=revision + 2,
        diagnostic_marker_ref=publication.diagnostic_marker_ref))
    completed = _ok(diagnostic_complete_verification(pair.diagnostic, operation_id="continuation-complete",
        diagnostic_session_id=pair.diagnostic_session_id, expected_revision=revision + 3,
        executed_operation_ids=["fixture-before", "fixture-after", "continuation-compare", "continuation-bundle"]))
    verification = completed["fix_verification"]
    assert verification["status"] == "PASSED"
    assert verification["verification_plan_digest"] == plan.plan_digest
    assert _ok(diagnostic_show(pair.diagnostic, diagnostic_session_id=pair.diagnostic_session_id))["session"]["state"] == "RESOLVED"

    # A later Diagnostic event now references the proof. Reading that proof
    # must still stop at the pinned pre-verification prefix, even if every
    # high-level Diagnostic reader is unavailable.
    with monkeypatch.context() as patch:
        def forbidden(*args, **kwargs):
            raise AssertionError("proof reader must not re-enter DiagnosticStore")
        for method in ("load", "load_durable", "_load_chain_locked", "_validate_referenced_evidence"):
            patch.setattr(DiagnosticStore, method, forbidden)
        loaded = authenticate_continuation(fresh_evidence, pair.workspace.diagnostics_root, continuation_id)
        assert loaded.proof.diagnostic_revision == pair.diagnostic_revision
        assert loaded.before.manifest.identity.session_id == pair.before_session_id
        assert loaded.after.manifest.identity.session_id == pair.after_session_id

    checkpoint = dict(attempt_id=CONTINUATION_ATTEMPT_ID, expected_revision=0, stage="target-fix-verified",
        test_run_id=pair.fixed_run_id, fix_verification_id=verification["fix_verification_id"])
    expired = {"value": False}
    timed_context = replace(pair.context, clock=lambda: "2026-09-11T00:15:00.000001Z"
        if expired["value"] else "2026-09-11T00:00:01.000000Z")
    original_put = EvidenceStore._put_envelope_locked

    def expire_after_envelope(store, envelope, *args, **kwargs):
        result = original_put(store, envelope, *args, **kwargs)
        value = envelope.metadata.get("attempt", {})
        if value.get("schema") == "stm32-acceptance-attempt/3" and value.get("revision") == 1:
            expired["value"] = True
        return result

    with monkeypatch.context() as patch:
        patch.setattr(EvidenceStore, "_put_envelope_locked", expire_after_envelope)
        result = checkpoint_acceptance_attempt(timed_context, **checkpoint)
    assert not result.ok and result.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT", result.to_dict()
    from stm32_toolkit.acceptance.recovery_workflows import _typed_root_path, _root_id
    assert not _typed_root_path(pair.evidence, _root_id(CONTINUATION_ATTEMPT_ID, 1)).exists()

    successor_id = "00000000-0000-4000-8000-000000000099"
    successor_context = replace(pair.context, clock=lambda: "2026-09-12T00:00:00.000000Z")
    successor = _ok(begin_acceptance_attempt(successor_context, attempt_id=successor_id,
        scenario_id="legacy-keil-physical-repair", scenario_version="1",
        continuation={"schema": "stm32-physical-continuation-request/1", "kind": "reuse",
                      "continuationEvidenceId": continuation_id}))["attempt"]
    assert successor["continuationEvidenceId"] == continuation_id
    checkpoint["attempt_id"] = successor_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: checkpoint_acceptance_attempt(successor_context, **checkpoint), range(2)))
    assert all(result.ok for result in results), [result.to_dict() for result in results]
    assert results[0].data == results[1].data
    final = _ok(results[0])["attempt"]
    assert final["status"] == "COMPLETED" and final["deadlineAtUtc"] == successor["deadlineAtUtc"]
    much_later = replace(pair.context, clock=lambda: "2027-01-01T00:00:00.000000Z")
    assert _ok(checkpoint_acceptance_attempt(much_later, **checkpoint))["attempt"] == final
    assert _ok(resume_acceptance_attempt(much_later, attempt_id=successor_id))["timedOut"] is False
    assert _ok(resume_acceptance_attempt(much_later, attempt_id=CONTINUATION_ATTEMPT_ID))["timedOut"] is True
    assert all(path.read_bytes() == raw for path, raw in original_roots.items())
    gc = plan_gc(fresh_evidence)
    assert f"manifests/{continuation_id}.json" in gc.reachable_manifests
    assert all(f"manifests/{parent}.json" in gc.reachable_manifests for parent in loaded.envelope.parents)
