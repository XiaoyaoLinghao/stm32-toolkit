"""Persisted software fixtures only: these tests never access physical hardware."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
from uuid import UUID

import pytest

from test_acceptance_continuation import prepare_pair, _ok, CONTINUATION_ATTEMPT_ID
import test_acceptance_physical_recovery as physical_fixture
from stm32_monitor.history import HistoryStore
from stm32_monitor.analysis import AnalysisRequest, AnalysisResult
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.analysis_workflows import (
    ANALYSIS_WORKFLOW_INVALID, EVIDENCE_INTEGRITY_FAILURE,
    AnalysisPublication, AnalysisWorkflowError, compare_monitor_runs, export_analysis_bundle,
)
from stm32_monitor.replay import canonical_replay_json_bytes, publish_physical_monitor_run
from stm32_toolkit.acceptance.continuation import authenticate_continuation
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    begin_acceptance_attempt, checkpoint_acceptance_attempt, resume_acceptance_attempt,
)
from stm32_toolkit.diagnostic_workflows import (
    diagnostic_add_verification_plan, diagnostic_start_verification, diagnostic_attach_marker,
    diagnostic_complete_verification, diagnostic_show,
)
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DiagnosticValidationError,
    VerificationPlan,
    create_event,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes, get_root
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.gc import plan_gc
from stm32_toolkit.evidence.store import EvidenceStore


def _append_native_physical_monitor_history(
    workspace,
    identity,
    raw_probe: str,
    flash_session_id: str,
    lease_id: str,
    run_id: str,
    *,
    value_offset: int,
) -> tuple[SampleBatch, ...]:
    """Create a persisted software transcript with the exact native wire shape."""

    binding = ObservationBinding(
        workspace_id=identity.workspace_id,
        logical_project_id=str(identity.project_id),
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
    group_id = "11111111-1111-4111-8111-111111111111"
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=UUID(group_id),
            group_revision=1,
            run_id=UUID(run_id),
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
                    WatchItem.register("r0"),
                    "OK",
                    typed_value={
                        "expression": "r0",
                        "typeName": "uint32_register",
                        "value": sequence + value_offset,
                        "rawHex": f"0x{sequence + value_offset:08x}",
                        "bitWidth": 32,
                    },
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(workspace)
    try:
        result = history.append_batches(batches)
        assert result.ok, result.to_dict()
    finally:
        history.close()
    return batches


def _monitor_baseline(pair: SimpleNamespace, tmp_path: Path) -> SimpleNamespace:
    """Publish one real physical Monitor pair and its valid continuation analysis."""

    attempt = _ok(
        begin_acceptance_attempt(
            pair.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id="legacy-keil-physical-repair",
            scenario_version="1",
            continuation=pair.bind_request,
        )
    )["attempt"]
    continuation_id = str(attempt["continuationEvidenceId"])
    refs = []
    for role, workspace, identity, test_run_id, value_offset in (
        ("failed-before", pair.before_workspace, pair.before_identity, pair.failed_run_id, 0),
        ("fixed-after", pair.after_workspace, pair.after_identity, pair.fixed_run_id, 10),
    ):
        operation_id = physical_fixture.vs08a_fixtures.MONITOR_OPERATION_IDS[role]
        batches = physical_fixture._append_physical_monitor_history(
            workspace,
            identity,
            physical_fixture.PHYSICAL_RAW_PROBE,
            f"flash-{test_run_id}",
            f"lease-{test_run_id}",
            operation_id,
            value_offset=value_offset,
        )
        refs.append(
            publish_physical_monitor_run(
                workspace,
                pair.evidence,
                scenario_role=role,
                test_run_id=test_run_id,
                run_id=operation_id,
                group_id=str(batches[0].group_id),
                start_sequence=batches[0].sequence,
                end_sequence_exclusive=batches[-1].sequence + 1,
                start_captured_unix_ns=batches[0].captured_unix_ns,
                end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
                probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
            )
        )
    request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=refs[0],
        after_run=refs[1],
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    )
    compare_args = (
        pair.before_workspace,
        pair.evidence,
        request,
        pair.diagnostic_session_id,
        pair.hypothesis_id,
        "supports",
        "the fixed fixture changes the counter",
        pair.declaration,
    )
    publication = compare_monitor_runs(
        *compare_args, continuation_evidence_id=continuation_id
    )
    analysis_evidence_id = str(publication.analysis_evidence_ref.evidence_id)
    analysis_envelope = pair.evidence.get_envelope(analysis_evidence_id)
    analysis_root = get_root(
        pair.evidence, "monitor-analysis", publication.analysis_result.analysis_id
    )
    raw = pair.evidence.read_artifact(
        analysis_envelope.artifacts[0], maximum_bytes=1024 * 1024
    )
    assert AnalysisResult.from_value(json.loads(raw.decode("utf-8"))) == publication.analysis_result
    assert analysis_root.manifest_id == analysis_evidence_id
    return SimpleNamespace(
        continuation_id=continuation_id,
        refs=tuple(refs),
        request=request,
        compare_args=compare_args,
        publication=publication,
        analysis_envelope=analysis_envelope,
        analysis_root=analysis_root,
    )


def _same_session_native_baseline(
    pair: SimpleNamespace,
    tmp_path: Path,
    *,
    continuation_id: str | None = None,
) -> SimpleNamespace:
    """Publish a v3 native analysis for a same-session or continuation pair."""

    if continuation_id is None:
        after_identity = replace(pair.after_identity, session_id=pair.before_session_id)
        fixed_run_id = "target-v2-fixed-t10-native"
        fixed = physical_fixture._publish_physical_from_seed(
            tmp_path,
            pair.project_root,
            pair.data_root,
            pair.before_session_id,
            "seed-fixed-t10-cont",
            fixed_run_id,
            after_identity,
        )
    else:
        after_identity = pair.after_identity
        fixed_run_id = pair.fixed_run_id
        fixed = pair.fixed_physical
    refs = []
    for role, identity, test_run_id, run_id, value_offset in (
        (
            "failed-before",
            pair.before_identity,
            pair.failed_run_id,
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            0,
        ),
        (
            "fixed-after",
            after_identity,
            fixed_run_id,
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            10,
        ),
    ):
        workspace = (
            pair.before_workspace
            if role == "failed-before" or continuation_id is None
            else pair.after_workspace
        )
        batches = _append_native_physical_monitor_history(
            workspace,
            identity,
            physical_fixture.PHYSICAL_RAW_PROBE,
            f"flash-{test_run_id}",
            f"lease-{test_run_id}",
            run_id,
            value_offset=value_offset,
        )
        refs.append(
            publish_physical_monitor_run(
                workspace,
                pair.evidence,
                scenario_role=role,
                test_run_id=test_run_id,
                run_id=run_id,
                group_id=str(batches[0].group_id),
                start_sequence=batches[0].sequence,
                end_sequence_exclusive=batches[-1].sequence + 1,
                start_captured_unix_ns=batches[0].captured_unix_ns,
                end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
                probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
            )
        )
    request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/2",
        before_run=refs[0],
        after_run=refs[1],
        selector_kind="register",
        selector="r0",
        alignment="bounded-run-relative",
        minimum_valid_pairs=2,
        scalar_policy="native-uint-register/1",
        max_pairing_skew_ns=1,
    )
    compare_args = (
        pair.before_workspace,
        pair.evidence,
        request,
        pair.diagnostic_session_id,
        pair.hypothesis_id,
        "supports",
        "the fixed fixture changes the native register",
        pair.declaration,
    )
    publication = compare_monitor_runs(
        *compare_args,
        **({} if continuation_id is None else {"continuation_evidence_id": continuation_id}),
    )
    assert publication.analysis_result.schema == "stm32-monitor-analysis/3"
    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.changed is True
    assert publication.analysis_result.request == request
    return SimpleNamespace(
        request=request,
        compare_args=compare_args,
        publication=publication,
        analysis_envelope=pair.evidence.get_envelope(
            publication.analysis_evidence_ref.evidence_id
        ),
        fixed_run_id=fixed_run_id,
        fixed=fixed,
        after_identity=after_identity,
        continuation_id=continuation_id,
    )


def _rehash_analysis_payload(payload: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in payload.items() if key != "analysis_id"}
    payload["analysis_id"] = hashlib.sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    assert AnalysisResult.from_value(payload).analysis_id == payload["analysis_id"]
    return payload


def _publish_analysis_variant(
    pair: SimpleNamespace,
    tmp_path: Path,
    baseline: SimpleNamespace,
    payload: dict[str, object],
    parents: tuple[str, ...],
    label: str,
) -> EvidenceEnvelope:
    raw = canonical_replay_json_bytes(payload)
    path = tmp_path / f"{label}-analysis.json"
    path.write_bytes(raw)
    artifact = pair.evidence.ingest_file(
        path, kind="monitor-analysis", media_type="application/json"
    )
    metadata = dict(baseline.analysis_envelope.metadata)
    metadata.update(
        analysis_id=payload["analysis_id"],
        before_run_id=payload["before_run_id"],
        after_run_id=payload["after_run_id"],
        source_change_declaration_id=payload["identity"]["source_change_declaration_id"],
    )
    envelope = EvidenceEnvelope(
        identity=baseline.analysis_envelope.identity,
        operation=baseline.analysis_envelope.operation,
        produced_at_utc=baseline.analysis_envelope.produced_at_utc,
        parents=parents,
        artifacts=(artifact,),
        metadata=metadata,
    )
    pair.evidence.put_envelope(envelope)
    put_root(
        pair.evidence,
        RootRecord(
            root_type="monitor-analysis",
            root_id=str(payload["analysis_id"]),
            manifest_id=str(envelope.evidence_id),
            metadata=metadata,
        ),
    )
    assert get_root(pair.evidence, "monitor-analysis", str(payload["analysis_id"])).manifest_id == str(envelope.evidence_id)
    return envelope


def _publish_raw_analysis_variant(
    pair: SimpleNamespace,
    tmp_path: Path,
    baseline: SimpleNamespace,
    raw: bytes,
    *,
    analysis_id: str,
    label: str,
) -> EvidenceEnvelope:
    path = tmp_path / f"{label}-analysis.json"
    path.write_bytes(raw)
    artifact = pair.evidence.ingest_file(
        path, kind="monitor-analysis", media_type="application/json"
    )
    metadata = dict(baseline.analysis_envelope.metadata)
    metadata.update(
        analysis_id=analysis_id,
        before_run_id=baseline.publication.analysis_result.before_run_id,
        after_run_id=baseline.publication.analysis_result.after_run_id,
        source_change_declaration_id=pair.declaration.declaration_id,
    )
    envelope = EvidenceEnvelope(
        identity=baseline.analysis_envelope.identity,
        operation=baseline.analysis_envelope.operation,
        produced_at_utc=baseline.analysis_envelope.produced_at_utc,
        parents=tuple(baseline.analysis_envelope.parents),
        artifacts=(artifact,),
        metadata=metadata,
    )
    pair.evidence.put_envelope(envelope)
    put_root(
        pair.evidence,
        RootRecord(
            root_type="monitor-analysis",
            root_id=analysis_id,
            manifest_id=str(envelope.evidence_id),
            metadata=metadata,
        ),
    )
    return envelope


def _verification_plan_event(
    pair: SimpleNamespace, plan: VerificationPlan, operation_id: str
) -> object:
    return create_event(
        diagnostic_session_id=pair.diagnostic_session_id,
        operation_id=operation_id,
        sequence=pair.diagnostic_revision,
        revision_before=pair.diagnostic_revision,
        event_type="verification.plan_added",
        occurred_at_utc="2026-09-11T00:00:00.000000Z",
        actor="tool",
        previous_digest=pair.diagnostic_event_head,
        payload={
            "request": {"verification_plan": plan.to_dict()},
            "result": {
                "verification_plan_id": plan.verification_plan_id,
                "plan_digest": plan.plan_digest,
            },
        },
    )


def _same_session_native_plan(
    pair: SimpleNamespace,
    baseline: SimpleNamespace,
    *,
    analysis_id: str | None = None,
    analysis_evidence_id: str | None = None,
) -> VerificationPlan:
    resolved_analysis_id = (
        baseline.publication.analysis_result.analysis_id
        if analysis_id is None
        else analysis_id
    )
    resolved_analysis_evidence_id = (
        str(baseline.analysis_envelope.evidence_id)
        if analysis_evidence_id is None
        else analysis_evidence_id
    )
    return VerificationPlan.new(
        verification_plan_id=pair.declaration.validation_plan_id,
        diagnostic_session_id=pair.diagnostic_session_id,
        failed_before_run_id=pair.failed_run_id,
        failed_before_evidence_id=str(pair.failed_physical.envelope.evidence_id),
        source_change_declaration_id=pair.declaration.declaration_id,
        fixed_after_run_id=baseline.fixed_run_id,
        fixed_after_evidence_id=str(baseline.fixed.envelope.evidence_id),
        required_analysis_ids=(resolved_analysis_id,),
        required_analysis_evidence_ids=(resolved_analysis_evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
        continuation_evidence_id=None,
    )


def _continuation_plan(
    pair: SimpleNamespace,
    baseline: SimpleNamespace,
    *,
    continuation_evidence_id: str | None = None,
    fixed_after_evidence_id: str | None = None,
    analysis_id: str | None = None,
    analysis_evidence_id: str | None = None,
) -> VerificationPlan:
    resolved_analysis_id = (
        baseline.publication.analysis_result.analysis_id
        if analysis_id is None
        else analysis_id
    )
    resolved_analysis_evidence_id = (
        str(baseline.analysis_envelope.evidence_id)
        if analysis_evidence_id is None
        else analysis_evidence_id
    )
    return VerificationPlan.new(
        verification_plan_id=pair.declaration.validation_plan_id,
        diagnostic_session_id=pair.diagnostic_session_id,
        failed_before_run_id=pair.failed_run_id,
        failed_before_evidence_id=str(pair.failed_physical.envelope.evidence_id),
        source_change_declaration_id=pair.declaration.declaration_id,
        fixed_after_run_id=pair.fixed_run_id,
        fixed_after_evidence_id=(
            str(pair.fixed_physical.envelope.evidence_id)
            if fixed_after_evidence_id is None
            else fixed_after_evidence_id
        ),
        required_analysis_ids=(resolved_analysis_id,),
        required_analysis_evidence_ids=(resolved_analysis_evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
        continuation_evidence_id=(
            baseline.continuation_id
            if continuation_evidence_id is None
            else continuation_evidence_id
        ),
    )


def _damage_root_manifest(
    evidence: EvidenceStore, root_type: str, root_id: str
) -> tuple[Path, bytes]:
    path = recovery_workflows._typed_root_path(evidence, root_id, root_type)
    original = path.read_bytes()
    document = json.loads(original.decode("utf-8"))
    assert isinstance(document, dict)
    document["manifest_id"] = "0" * 64
    path.write_bytes(canonical_json_bytes(document))
    return path, original


def test_diagnostic_store_reads_authenticated_same_session_native_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _same_session_native_baseline(pair, tmp_path)
    plan = _same_session_native_plan(pair, baseline)
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)

    accepted = store.append(
        pair.diagnostic_session_id,
        _verification_plan_event(pair, plan, "same-session-native-plan"),
        expected_revision=pair.diagnostic_revision,
    )
    assert accepted.session.revision == pair.diagnostic_revision + 1

    # A fresh Store must authenticate the same complete native graph when it
    # reads the newly persisted diagnostic record.
    fresh_store = DiagnosticStore(
        pair.workspace.diagnostics_root,
        EvidenceStore(pair.evidence.root),
    )
    loaded = fresh_store.load(pair.diagnostic_session_id)
    assert loaded.revision == pair.diagnostic_revision + 1


def test_diagnostic_store_rejects_missing_same_session_native_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _same_session_native_baseline(pair, tmp_path)
    plan = _same_session_native_plan(pair, baseline)
    revision = pair.diagnostic_revision
    _ok(
        diagnostic_add_verification_plan(
            pair.diagnostic,
            operation_id="same-session-native-missing-plan",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=revision,
            verification_plan=plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            pair.diagnostic,
            operation_id="same-session-native-missing-start",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=revision + 1,
            verification_plan_id=plan.verification_plan_id,
        )
    )
    _ok(
        diagnostic_attach_marker(
            pair.diagnostic,
            operation_id="same-session-native-missing-marker",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=revision + 2,
            diagnostic_marker_ref=baseline.publication.diagnostic_marker_ref,
        )
    )
    completed = _ok(
        diagnostic_complete_verification(
            pair.diagnostic,
            operation_id="same-session-native-missing-complete",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=revision + 3,
            executed_operation_ids=["same-session-native-compare"],
        )
    )
    assert completed["fix_verification"]["status"] == "PASSED"
    artifact_path = pair.evidence.root / baseline.analysis_envelope.artifacts[0].relative_path
    artifact_path.unlink()
    # The record is already complete. A fresh reader must fail closed while
    # revalidating the persisted result/3 graph after its artifact disappears.
    store = DiagnosticStore(
        pair.workspace.diagnostics_root,
        EvidenceStore(pair.evidence.root),
    )

    with pytest.raises(DiagnosticValidationError) as raised:
        store.load(pair.diagnostic_session_id)
    assert raised.value.code in {DIAGNOSTIC_CHAIN_CORRUPT, DIAGNOSTIC_EVIDENCE_MISSING}
    assert store.load_durable(pair.diagnostic_session_id).revision == revision + 4


@pytest.mark.parametrize(
    ("label", "field", "value", "delta"),
    (
        ("float-stat", "before_first", 0.0, 10),
        ("bool-stat", "before_first", True, 9),
    ),
)
def test_diagnostic_store_rejects_rehashed_native_type_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    field: str,
    value: object,
    delta: int,
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _same_session_native_baseline(pair, tmp_path)
    raw = pair.evidence.read_artifact(
        baseline.analysis_envelope.artifacts[0], maximum_bytes=1024 * 1024
    )
    payload = json.loads(raw.decode("utf-8"))
    assert isinstance(payload, dict)
    payload[field] = value
    payload["delta_first"] = delta
    unsigned = {key: item for key, item in payload.items() if key != "analysis_id"}
    payload["analysis_id"] = hashlib.sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    variant = _publish_analysis_variant(
        pair,
        tmp_path,
        baseline,
        payload,
        tuple(baseline.analysis_envelope.parents),
        f"same-session-{label}",
    )
    plan = _same_session_native_plan(
        pair,
        baseline,
        analysis_id=str(payload["analysis_id"]),
        analysis_evidence_id=str(variant.evidence_id),
    )
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)
    event = _verification_plan_event(pair, plan, f"same-session-forged-{label}")

    with pytest.raises(DiagnosticValidationError) as raised:
        store.append(
            pair.diagnostic_session_id,
            event,
            expected_revision=pair.diagnostic_revision,
        )
    assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision


@pytest.mark.parametrize(
    ("label", "raw"),
    (
        ("unrecognized", b"{}"),
        ("noncanonical", b'{"schema":"stm32-monitor-analysis/3"}\n'),
    ),
)
def test_diagnostic_store_rejects_unreadable_or_unrecognized_native_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    raw: bytes,
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _same_session_native_baseline(pair, tmp_path)
    analysis_id = ("c" * 64) if label == "unrecognized" else ("d" * 64)
    variant = _publish_raw_analysis_variant(
        pair,
        tmp_path,
        baseline,
        raw,
        analysis_id=analysis_id,
        label=f"same-session-{label}",
    )
    plan = _same_session_native_plan(
        pair,
        baseline,
        analysis_id=analysis_id,
        analysis_evidence_id=str(variant.evidence_id),
    )
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)

    with pytest.raises(DiagnosticValidationError) as raised:
        store.append(
            pair.diagnostic_session_id,
            _verification_plan_event(pair, plan, f"same-session-bad-{label}"),
            expected_revision=pair.diagnostic_revision,
        )
    assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision


@pytest.mark.parametrize("tamper", ("statistics", "embedded-request"))
def test_diagnostic_continuation_validation_rejects_native_result3_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    attempt = _ok(
        begin_acceptance_attempt(
            pair.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id="legacy-keil-physical-repair",
            scenario_version="1",
            continuation=pair.bind_request,
        )
    )["attempt"]
    baseline = _same_session_native_baseline(
        pair,
        tmp_path,
        continuation_id=str(attempt["continuationEvidenceId"]),
    )
    raw = pair.evidence.read_artifact(
        baseline.analysis_envelope.artifacts[0], maximum_bytes=1024 * 1024
    )
    payload = json.loads(raw.decode("utf-8"))
    assert isinstance(payload, dict)
    if tamper == "statistics":
        payload["before_first"] = 0.0
        payload["delta_first"] = 10
    else:
        request = dict(payload["request"])
        after_run = dict(request["after_run"])
        forged_operation = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        after_run.update(
            operation_id=forged_operation,
            origin_run_id=forged_operation,
            projected_run_id=forged_operation,
        )
        after_run["run_ref_sha256"] = hashlib.sha256(
            canonical_replay_json_bytes(
                {key: value for key, value in after_run.items() if key != "run_ref_sha256"}
            )
        ).hexdigest()
        request["after_run"] = after_run
        payload["request"] = request
        payload["after_run_id"] = after_run["run_ref_sha256"]
        payload["request_digest"] = hashlib.sha256(
            canonical_replay_json_bytes(request)
        ).hexdigest()
    payload = _rehash_analysis_payload(payload)
    variant = _publish_analysis_variant(
        pair,
        tmp_path,
        baseline,
        payload,
        tuple(baseline.analysis_envelope.parents),
        f"continuation-native-{tamper}",
    )
    plan = _continuation_plan(
        pair,
        baseline,
        analysis_id=str(payload["analysis_id"]),
        analysis_evidence_id=str(variant.evidence_id),
    )

    rejected = diagnostic_add_verification_plan(
        pair.diagnostic,
        operation_id=f"continuation-native-{tamper}-plan",
        diagnostic_session_id=pair.diagnostic_session_id,
        expected_revision=pair.diagnostic_revision,
        verification_plan=plan,
    )
    assert not rejected.ok
    assert rejected.code in {EVIDENCE_INTEGRITY_FAILURE, DIAGNOSTIC_CHAIN_CORRUPT}
    assert DiagnosticStore(
        pair.workspace.diagnostics_root, pair.evidence
    ).load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision


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


def test_diagnostic_store_rejects_self_consistent_forged_continuation_analysis_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _monitor_baseline(pair, tmp_path)

    # The public Monitor boundary must classify malformed and absent proof
    # references before it reaches the low-level evidence graph.
    for continuation_id, expected_code in (
        ("malformed-proof", ANALYSIS_WORKFLOW_INVALID),
        ("f" * 64, EVIDENCE_INTEGRITY_FAILURE),
    ):
        with pytest.raises(AnalysisWorkflowError) as raised:
            compare_monitor_runs(
                *baseline.compare_args,
                continuation_evidence_id=continuation_id,
            )
        assert raised.value.code == expected_code

    base_raw = pair.evidence.read_artifact(
        baseline.analysis_envelope.artifacts[0], maximum_bytes=1024 * 1024
    )
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)
    variants = (
        "wrong-run-reference",
        "wrong-declaration-lineage",
        "wrong-full-lineage",
        "wrong-window-test-run",
    )
    for label in variants:
        payload = json.loads(base_raw.decode("utf-8"))
        assert isinstance(payload, dict)
        lineage = payload["identity"]
        assert isinstance(lineage, dict)
        parents = tuple(baseline.analysis_envelope.parents)
        if label == "wrong-run-reference":
            # This is an existing, readable Monitor ref, but it belongs to the
            # after window rather than the before parent.
            payload["before_run_id"] = baseline.refs[1].run_ref_sha256
        elif label == "wrong-declaration-lineage":
            payload_lineage = dict(lineage)
            payload_lineage["source_change_declaration_id"] = "a" * 64
            payload["identity"] = payload_lineage
        elif label == "wrong-full-lineage":
            payload_lineage = dict(lineage)
            payload_lineage["after_build_id"] = "b" * 64
            payload["identity"] = payload_lineage
        else:
            alt_test_run_id = "target-v2-fixed-t10-alt-monitor"
            alt_operation_id = "55555555-5555-4555-8555-555555555555"
            alternate = physical_fixture._publish_physical_from_seed(
                tmp_path,
                pair.project_root,
                pair.data_root,
                pair.after_session_id,
                "seed-fixed-t10-cont",
                alt_test_run_id,
                pair.after_identity,
            )
            alt_batches = physical_fixture._append_physical_monitor_history(
                pair.after_workspace,
                pair.after_identity,
                physical_fixture.PHYSICAL_RAW_PROBE,
                f"flash-{alt_test_run_id}",
                f"lease-{alt_test_run_id}",
                alt_operation_id,
                value_offset=10,
            )
            alt_reference = publish_physical_monitor_run(
                pair.after_workspace,
                pair.evidence,
                scenario_role="fixed-after",
                test_run_id=alt_test_run_id,
                run_id=alt_operation_id,
                group_id=str(alt_batches[0].group_id),
                start_sequence=alt_batches[0].sequence,
                end_sequence_exclusive=alt_batches[-1].sequence + 1,
                start_captured_unix_ns=alt_batches[0].captured_unix_ns,
                end_captured_unix_ns_exclusive=alt_batches[-1].captured_unix_ns + 1,
                probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
            )
            assert pair.repository.load(alt_test_run_id).envelope == alternate.envelope
            payload["after_run_id"] = alt_reference.run_ref_sha256
            parents = (
                baseline.analysis_envelope.parents[0],
                alt_reference.transcript_evidence_id,
                *baseline.analysis_envelope.parents[2:],
            )
        payload = _rehash_analysis_payload(payload)
        variant_envelope = _publish_analysis_variant(
            pair,
            tmp_path,
            baseline,
            payload,
            parents,
            label,
        )
        plan = VerificationPlan.new(
            verification_plan_id=pair.declaration.validation_plan_id,
            diagnostic_session_id=pair.diagnostic_session_id,
            failed_before_run_id=pair.failed_run_id,
            failed_before_evidence_id=str(pair.failed_physical.envelope.evidence_id),
            source_change_declaration_id=pair.declaration.declaration_id,
            fixed_after_run_id=pair.fixed_run_id,
            fixed_after_evidence_id=str(pair.fixed_physical.envelope.evidence_id),
            required_analysis_ids=(str(payload["analysis_id"]),),
            required_analysis_evidence_ids=(str(variant_envelope.evidence_id),),
            required_monitor_quality="VALID",
            expected_changed=True,
            continuation_evidence_id=baseline.continuation_id,
        )
        event = create_event(
            diagnostic_session_id=pair.diagnostic_session_id,
            operation_id=f"t10-invalid-analysis-{label}",
            sequence=pair.diagnostic_revision,
            revision_before=pair.diagnostic_revision,
            event_type="verification.plan_added",
            occurred_at_utc="2026-09-11T00:00:00.000000Z",
            actor="tool",
            previous_digest=pair.diagnostic_event_head,
            payload={
                "request": {"verification_plan": plan.to_dict()},
                "result": {
                    "verification_plan_id": plan.verification_plan_id,
                    "plan_digest": plan.plan_digest,
                },
            },
        )
        with pytest.raises(DiagnosticValidationError) as raised:
            store.append(
                pair.diagnostic_session_id,
                event,
                expected_revision=pair.diagnostic_revision,
            )
        assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
        assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision


def test_diagnostic_continuation_error_mapping_for_public_plan_and_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _monitor_baseline(pair, tmp_path)
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)

    # The real proof and analysis are readable before each negative mutation.
    association = authenticate_continuation(
        pair.evidence,
        pair.workspace.diagnostics_root,
        baseline.continuation_id,
        expected_workspace_id=pair.workspace.workspace_id,
        expected_project_id=str(pair.model.logical_project_id),
        expected_session_id=pair.before_session_id,
        expected_diagnostic_session_id=pair.diagnostic_session_id,
        expected_fixed_after_test_run_id=pair.fixed_run_id,
        expected_fixed_after_evidence_id=str(pair.fixed_physical.envelope.evidence_id),
    )
    assert association.continuation_evidence_id == baseline.continuation_id
    assert association.proof.continuation_id != baseline.continuation_id
    assert AnalysisResult.from_value(
        json.loads(
            pair.evidence.read_artifact(
                baseline.analysis_envelope.artifacts[0], maximum_bytes=1024 * 1024
            ).decode("utf-8")
        )
    ) == baseline.publication.analysis_result

    missing_proof_plan = _continuation_plan(
        pair, baseline, continuation_evidence_id="f" * 64
    )
    missing_proof = diagnostic_add_verification_plan(
        pair.diagnostic,
        operation_id="continuation-plan-missing-proof",
        diagnostic_session_id=pair.diagnostic_session_id,
        expected_revision=pair.diagnostic_revision,
        verification_plan=missing_proof_plan,
    )
    assert not missing_proof.ok
    assert missing_proof.code == EVIDENCE_INTEGRITY_FAILURE
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision

    # A rooted continuation whose manifest link is damaged is an existing
    # proof graph, so the low-level append boundary reports chain corruption.
    proof_root_path, proof_root_bytes = _damage_root_manifest(
        pair.evidence, "physical-continuation", association.proof.continuation_id
    )
    try:
        proof_event = _verification_plan_event(
            pair,
            _continuation_plan(pair, baseline),
            "continuation-plan-damaged-proof",
        )
        with pytest.raises(DiagnosticValidationError) as raised:
            store.append(
                pair.diagnostic_session_id,
                proof_event,
                expected_revision=pair.diagnostic_revision,
            )
        assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    finally:
        proof_root_path.write_bytes(proof_root_bytes)
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision

    # The analysis root is also authoritative.  Damaging only its manifest
    # link must not be accepted as a new plan or downgraded to identity.
    analysis_root_path, analysis_root_bytes = _damage_root_manifest(
        pair.evidence,
        "monitor-analysis",
        baseline.publication.analysis_result.analysis_id,
    )
    try:
        analysis_event = _verification_plan_event(
            pair,
            _continuation_plan(pair, baseline),
            "continuation-plan-damaged-analysis",
        )
        with pytest.raises(DiagnosticValidationError) as raised:
            store.append(
                pair.diagnostic_session_id,
                analysis_event,
                expected_revision=pair.diagnostic_revision,
            )
        assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    finally:
        analysis_root_path.write_bytes(analysis_root_bytes)
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision

    # A well-formed, readable proof can still reject a plan whose fixed
    # evidence reference is different from the proof's bound TestRun.
    mismatched_plan = _continuation_plan(
        pair,
        baseline,
        fixed_after_evidence_id=str(baseline.analysis_envelope.evidence_id),
    )
    assert mismatched_plan.fixed_after_evidence_id != str(
        pair.fixed_physical.envelope.evidence_id
    )
    mismatch_event = _verification_plan_event(
        pair, mismatched_plan, "continuation-plan-external-mismatch"
    )
    with pytest.raises(DiagnosticValidationError) as raised:
        store.append(
            pair.diagnostic_session_id,
            mismatch_event,
            expected_revision=pair.diagnostic_revision,
        )
    assert raised.value.code == DIAGNOSTIC_IDENTITY_MISMATCH
    assert store.load_durable(pair.diagnostic_session_id).revision == pair.diagnostic_revision
