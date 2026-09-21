"""Offline qualification of native Diagnostic evidence authority and recovery."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_continuation_monitor as monitor_fixture
from stm32_monitor.analysis import DiagnosticMarker
from stm32_monitor.replay import MonitorRunRefV2, canonical_replay_json_bytes
from stm32_toolkit.acceptance.recovery_workflows import begin_acceptance_attempt
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_verification_plan,
    diagnostic_attach_marker,
    diagnostic_complete_verification,
    diagnostic_show_verification,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import DiagnosticMarkerRef
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes, get_root
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.monitor_replay_contract import (
    canonical_physical_json_bytes,
    decode_canonical_json_bytes,
    decode_physical_transcript_bytes,
)
from test_acceptance_continuation import CONTINUATION_ATTEMPT_ID, _ok, prepare_pair

_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_PLAN_OPERATION = "diagnostic.verification-plan.add"
_MARKER_OPERATION = "diagnostic.marker.attach"
_SHOW_OPERATION = "diagnostic.verification.show"
_EVIDENCE_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
_IDENTITY_FAILURE = "INCOMPATIBLE_IDENTITY"
_EVIDENCE_MESSAGE = "Target replay evidence failed integrity validation."
_IDENTITY_MESSAGE = "Target replay identity is incompatible."

_PHYSICAL_VARIANTS = (
    ("1691-project-session", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1709-empty-operation", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1717-run-relation", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1757-transcript-kind", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1787-test-run", "INCOMPATIBLE_IDENTITY"),
    ("1794-batch-run", "INCOMPATIBLE_IDENTITY"),
    ("1846-reference-kind", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1865-reference-source", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1906-reference-target", "EVIDENCE_INTEGRITY_FAILURE"),
    ("1912-reference-batch-digest", "EVIDENCE_INTEGRITY_FAILURE"),
)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Return a byte snapshot for one run-owned tree."""

    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_tree_unchanged(root: Path, original: Mapping[str, bytes]) -> None:
    current = _tree_bytes(root)
    for relative, raw in original.items():
        assert current.get(relative) == raw
    assert set(original).issubset(current)


def _root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    key = canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    digest = sha256(key).hexdigest()
    return evidence.root / "roots" / root_type / f"{digest}.json"


def _assert_failure(result: object, *, operation: str, code: str, message: str) -> None:
    to_dict = getattr(result, "to_dict", None)
    assert callable(to_dict)
    assert to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": message,
        "data": None,
        "details": {},
    }


def _different_digest(previous: object) -> str:
    assert isinstance(previous, str)
    for candidate in ("0" * 64, "1" * 64, "2" * 64, "f" * 64):
        if candidate != previous:
            return candidate
    raise AssertionError("no alternate digest available")


def _read_artifact(evidence: EvidenceStore, envelope: EvidenceEnvelope) -> bytes:
    assert len(envelope.artifacts) == 1
    return evidence.read_artifact(
        envelope.artifacts[0],
        maximum_bytes=_MAX_EVIDENCE_BYTES,
    )


def _publish_physical_variant(
    pair: SimpleNamespace,
    baseline: SimpleNamespace,
    tmp_path: Path,
    variant: str,
) -> SimpleNamespace:
    """Publish a fresh producer-shaped failed-before graph for one first guard."""

    evidence = pair.evidence
    before_reference = baseline.request.before_run
    assert isinstance(before_reference, MonitorRunRefV2)
    transcript_envelope = evidence.get_envelope(before_reference.transcript_evidence_id)
    transcript = decode_physical_transcript_bytes(
        _read_artifact(evidence, transcript_envelope)
    )
    operation_id = str(uuid4())
    mismatched_operation_id = str(uuid4())
    assert operation_id != mismatched_operation_id

    batches = deepcopy(transcript["batches"])
    assert isinstance(batches, list) and batches
    assert all(isinstance(batch, dict) for batch in batches)
    for batch in batches:
        batch["runId"] = (
            mismatched_operation_id if variant == "1794-batch-run" else operation_id
        )
    transcript["batches"] = batches

    transcript_test_run_id = str(transcript["test_run_id"])
    if variant == "1787-test-run":
        transcript_test_run_id = pair.fixed_run_id
        transcript["test_run_id"] = transcript_test_run_id

    projected_session_id = str(transcript_envelope.metadata["projected_session_id"])
    if variant == "1691-project-session":
        projected_session_id = pair.after_session_id

    operation_metadata = operation_id
    origin_run_id = operation_id
    projected_run_id = operation_id
    if variant == "1709-empty-operation":
        operation_metadata = ""
    elif variant == "1717-run-relation":
        origin_run_id = str(uuid4())
        projected_run_id = str(uuid4())
        assert origin_run_id != operation_id
        assert projected_run_id != operation_id

    transcript_raw = canonical_physical_json_bytes(transcript)
    source_record_sha256 = sha256(transcript_raw).hexdigest()
    transcript_path = tmp_path / f"{variant}-transcript.json"
    transcript_path.write_bytes(transcript_raw)
    transcript_kind = (
        "wrong-kind"
        if variant == "1757-transcript-kind"
        else "monitor-physical-transcript"
    )
    transcript_artifact = evidence.ingest_file(
        transcript_path,
        kind=transcript_kind,
        media_type="application/json",
    )
    transcript_metadata = dict(transcript_envelope.metadata)
    transcript_metadata.update(
        {
            "operation_id": operation_metadata,
            "test_run_id": transcript_test_run_id,
            "origin_run_id": origin_run_id,
            "projected_run_id": projected_run_id,
            "projected_session_id": projected_session_id,
            "source_record_sha256": source_record_sha256,
        }
    )
    variant_transcript = EvidenceEnvelope(
        identity=transcript_envelope.identity,
        operation=transcript_envelope.operation,
        produced_at_utc=transcript_envelope.produced_at_utc,
        parents=(),
        artifacts=(transcript_artifact,),
        metadata=transcript_metadata,
    )
    evidence.put_envelope(variant_transcript)

    reference_payload = before_reference.to_dict()
    reference_payload.update(
        {
            "operation_id": operation_id,
            "origin_run_id": operation_id,
            "projected_run_id": operation_id,
            "source_record_sha256": source_record_sha256,
            "transcript_evidence_id": str(variant_transcript.evidence_id),
            "projected_batch_sha256s": [
                sha256(canonical_physical_json_bytes(batch)).hexdigest()
                for batch in batches
            ],
            "run_ref_sha256": "0" * 64,
        }
    )
    if variant == "1865-reference-source":
        reference_payload["source_record_sha256"] = _different_digest(
            source_record_sha256
        )
    elif variant == "1906-reference-target":
        reference_payload["target_device"] = "STM32F429ZITx-alt"
    elif variant == "1912-reference-batch-digest":
        projected = list(reference_payload["projected_batch_sha256s"])
        projected[0] = _different_digest(projected[0])
        reference_payload["projected_batch_sha256s"] = projected
    unsigned_reference = {
        key: value
        for key, value in reference_payload.items()
        if key != "run_ref_sha256"
    }
    reference_payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned_reference)
    ).hexdigest()
    reference = MonitorRunRefV2.from_value(reference_payload)
    assert reference.to_dict() == reference_payload

    reference_raw = canonical_replay_json_bytes(reference_payload)
    reference_path = tmp_path / f"{variant}-reference.json"
    reference_path.write_bytes(reference_raw)
    reference_kind = (
        "wrong-kind" if variant == "1846-reference-kind" else "monitor-run-ref"
    )
    reference_artifact = evidence.ingest_file(
        reference_path,
        kind=reference_kind,
        media_type="application/json",
    )
    reference_source_digest = (
        source_record_sha256
        if variant == "1865-reference-source"
        else reference.source_record_sha256
    )
    original_reference_root = get_root(
        evidence,
        "monitor-run-ref",
        before_reference.operation_id,
    )
    original_reference_envelope = evidence.get_envelope(
        original_reference_root.manifest_id
    )
    reference_metadata = dict(original_reference_envelope.metadata)
    reference_metadata.update(
        {
            "operation_id": reference.operation_id,
            "run_ref_sha256": reference.run_ref_sha256,
            "source_record_sha256": reference_source_digest,
            "scenario_role": reference.scenario_role,
            "origin_workspace_id": reference.origin_workspace_id,
            "import_workspace_id": reference.import_workspace_id,
            "execution_source": reference.execution_source,
            "physical_transport_evidence": reference.physical_transport_evidence,
        }
    )
    variant_reference = EvidenceEnvelope(
        identity=variant_transcript.identity,
        operation="monitor-run-ref",
        produced_at_utc=variant_transcript.produced_at_utc,
        parents=(str(variant_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(variant_reference)

    transcript_root_metadata = {
        "source_record_sha256": source_record_sha256,
        "run_ref_sha256": reference.run_ref_sha256,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }
    reference_root_metadata = {
        "operation_id": reference.operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "source_record_sha256": reference_source_digest,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run",
            root_id=operation_id,
            manifest_id=str(variant_transcript.evidence_id),
            metadata=transcript_root_metadata,
        ),
    )
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run-ref",
            root_id=operation_id,
            manifest_id=str(variant_reference.evidence_id),
            metadata=reference_root_metadata,
        ),
    )
    return SimpleNamespace(
        reference=reference,
        transcript_evidence_id=str(variant_transcript.evidence_id),
        reference_evidence_id=str(variant_reference.evidence_id),
        operation_id=operation_id,
    )


def _publish_analysis_variant(
    pair: SimpleNamespace,
    baseline: SimpleNamespace,
    tmp_path: Path,
    variant: str,
    physical: SimpleNamespace | None,
) -> SimpleNamespace:
    """Point a fresh analysis envelope at the selected physical graph."""

    evidence = pair.evidence
    analysis_envelope = baseline.analysis_envelope
    payload = decode_canonical_json_bytes(_read_artifact(evidence, analysis_envelope))
    assert isinstance(payload, dict)
    payload = deepcopy(payload)
    if physical is None:
        payload["request_digest"] = _different_digest(payload["request_digest"])
        parents = tuple(analysis_envelope.parents)
    else:
        before_reference = physical.reference
        if variant != "1906-reference-target":
            request = deepcopy(payload["request"])
            assert isinstance(request, dict)
            request["before_run"] = before_reference.to_dict()
            request["after_run"] = baseline.request.after_run.to_dict()
            payload["request"] = request
            payload["request_digest"] = sha256(
                canonical_replay_json_bytes(request)
            ).hexdigest()
            payload["before_run_id"] = before_reference.run_ref_sha256
        parents = (
            physical.transcript_evidence_id,
            baseline.request.after_run.transcript_evidence_id,
            pair.declaration.diff_evidence_id,
            baseline.continuation_id,
        )
    payload = monitor_fixture._rehash_analysis_payload(payload)
    analysis_variant_envelope = monitor_fixture._publish_analysis_variant(
        pair,
        tmp_path,
        baseline,
        payload,
        tuple(str(parent) for parent in parents),
        variant,
    )
    return SimpleNamespace(
        analysis_id=str(payload["analysis_id"]),
        analysis_evidence_id=str(analysis_variant_envelope.evidence_id),
    )


def _publish_marker_variant(
    pair: SimpleNamespace,
    baseline: SimpleNamespace,
    tmp_path: Path,
) -> DiagnosticMarkerRef:
    """Publish a valid alternate marker whose identity is intentionally foreign."""

    original = baseline.publication.diagnostic_marker
    alternate_label = (
        "no-change-observed"
        if original.label == "change-observed"
        else "change-observed"
    )
    marker = DiagnosticMarker.new(
        analysis_id=original.analysis_id,
        analysis_evidence_id=original.analysis_evidence_id,
        diagnostic_session_id=original.diagnostic_session_id,
        hypothesis_id=original.hypothesis_id,
        polarity=original.polarity,
        label=alternate_label,
        rationale=original.rationale,
    )
    raw = canonical_replay_json_bytes(marker.to_dict())
    marker_path = tmp_path / "alternate-marker.json"
    marker_path.write_bytes(raw)
    artifact = pair.evidence.ingest_file(
        marker_path,
        kind="diagnostic-marker",
        media_type="application/json",
    )
    original_root = get_root(pair.evidence, "diagnostic-marker", original.marker_id)
    original_envelope = pair.evidence.get_envelope(original_root.manifest_id)
    alternate_identity = replace(
        original_envelope.identity,
        session_id=f"{original_envelope.identity.session_id}-alt",
    )
    metadata = {
        "marker_id": marker.marker_id,
        "analysis_id": marker.analysis_id,
        "analysis_evidence_id": marker.analysis_evidence_id,
        "origin_workspace_id": alternate_identity.workspace_id,
        "import_workspace_id": pair.workspace.workspace_id,
        "origin_session_id": alternate_identity.session_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }
    envelope = EvidenceEnvelope(
        identity=alternate_identity,
        operation=original_envelope.operation,
        produced_at_utc=original_envelope.produced_at_utc,
        parents=(original.analysis_evidence_id,),
        artifacts=(artifact,),
        metadata=metadata,
    )
    pair.evidence.put_envelope(envelope)
    put_root(
        pair.evidence,
        RootRecord(
            root_type="diagnostic-marker",
            root_id=marker.marker_id,
            manifest_id=str(envelope.evidence_id),
            metadata=metadata,
        ),
    )
    marker_ref = DiagnosticMarkerRef.new(
        marker_id=marker.marker_id,
        marker_evidence_id=str(envelope.evidence_id),
        analysis_id=marker.analysis_id,
        analysis_evidence_id=marker.analysis_evidence_id,
        diagnostic_session_id=marker.diagnostic_session_id,
        hypothesis_id=marker.hypothesis_id,
        polarity=marker.polarity,
        label=marker.label,
        rationale=marker.rationale,
    )
    assert marker_ref.to_dict()["marker_id"] == marker.marker_id
    return marker_ref


def test_public_native_diagnostic_evidence_refusals_restore_and_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    continuation_id = str(attempt["continuationEvidenceId"])
    baseline = monitor_fixture._same_session_native_baseline(
        pair,
        tmp_path,
        continuation_id=continuation_id,
    )
    assert baseline.continuation_id == continuation_id
    before_reference = baseline.request.before_run
    after_reference = baseline.request.after_run
    assert isinstance(before_reference, MonitorRunRefV2)
    assert isinstance(after_reference, MonitorRunRefV2)

    original_evidence = _tree_bytes(pair.evidence.root)
    original_diagnostics = _tree_bytes(pair.workspace.diagnostics_root)
    for root_type, root_id in (
        ("monitor-run", before_reference.operation_id),
        ("monitor-run-ref", before_reference.operation_id),
        ("monitor-run", after_reference.operation_id),
        ("monitor-run-ref", after_reference.operation_id),
        ("monitor-analysis", baseline.publication.analysis_result.analysis_id),
        ("diagnostic-marker", baseline.publication.diagnostic_marker.marker_id),
    ):
        assert _root_path(pair.evidence, root_type, root_id).read_bytes()
    for variant, expected in _PHYSICAL_VARIANTS:
        physical = _publish_physical_variant(pair, baseline, tmp_path, variant)
        analysis = _publish_analysis_variant(
            pair,
            baseline,
            tmp_path,
            variant,
            physical,
        )
        plan = monitor_fixture._continuation_plan(
            pair,
            baseline,
            analysis_id=analysis.analysis_id,
            analysis_evidence_id=analysis.analysis_evidence_id,
        )
        result = diagnostic_add_verification_plan(
            pair.diagnostic,
            operation_id=f"wave10-{variant}",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=pair.diagnostic_revision,
            verification_plan=plan,
        )
        _assert_failure(
            result,
            operation=_PLAN_OPERATION,
            code=_IDENTITY_FAILURE
            if expected == _IDENTITY_FAILURE
            else _EVIDENCE_FAILURE,
            message=_IDENTITY_MESSAGE
            if expected == _IDENTITY_FAILURE
            else _EVIDENCE_MESSAGE,
        )
        _assert_tree_unchanged(pair.workspace.diagnostics_root, original_diagnostics)
        _assert_tree_unchanged(pair.evidence.root, original_evidence)

    invalid_request_analysis = _publish_analysis_variant(
        pair,
        baseline,
        tmp_path,
        "2361-request-digest",
        None,
    )
    invalid_plan = monitor_fixture._continuation_plan(
        pair,
        baseline,
        analysis_id=invalid_request_analysis.analysis_id,
        analysis_evidence_id=invalid_request_analysis.analysis_evidence_id,
    )
    invalid_result = diagnostic_add_verification_plan(
        pair.diagnostic,
        operation_id="wave10-2361-request-digest",
        diagnostic_session_id=pair.diagnostic_session_id,
        expected_revision=pair.diagnostic_revision,
        verification_plan=invalid_plan,
    )
    _assert_failure(
        invalid_result,
        operation=_PLAN_OPERATION,
        code=_EVIDENCE_FAILURE,
        message=_EVIDENCE_MESSAGE,
    )
    _assert_tree_unchanged(pair.workspace.diagnostics_root, original_diagnostics)
    _assert_tree_unchanged(pair.evidence.root, original_evidence)

    valid_plan = monitor_fixture._continuation_plan(pair, baseline)
    _ok(
        diagnostic_add_verification_plan(
            pair.diagnostic,
            operation_id="wave10-valid-plan",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=pair.diagnostic_revision,
            verification_plan=valid_plan,
        )
    )
    _ok(
        diagnostic_start_verification(
            pair.diagnostic,
            operation_id="wave10-valid-start",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=pair.diagnostic_revision + 1,
            verification_plan_id=valid_plan.verification_plan_id,
        )
    )
    after_start = _tree_bytes(pair.workspace.diagnostics_root)
    alternate_marker = _publish_marker_variant(pair, baseline, tmp_path)
    marker_result = diagnostic_attach_marker(
        pair.diagnostic,
        operation_id="wave10-alternate-marker",
        diagnostic_session_id=pair.diagnostic_session_id,
        expected_revision=pair.diagnostic_revision + 2,
        diagnostic_marker_ref=alternate_marker,
    )
    _assert_failure(
        marker_result,
        operation=_MARKER_OPERATION,
        code=_IDENTITY_FAILURE,
        message=_IDENTITY_MESSAGE,
    )
    _assert_tree_unchanged(pair.workspace.diagnostics_root, after_start)
    _assert_tree_unchanged(pair.evidence.root, original_evidence)

    _ok(
        diagnostic_attach_marker(
            pair.diagnostic,
            operation_id="wave10-valid-marker",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=pair.diagnostic_revision + 2,
            diagnostic_marker_ref=baseline.publication.diagnostic_marker_ref,
        )
    )
    completed = _ok(
        diagnostic_complete_verification(
            pair.diagnostic,
            operation_id="wave10-valid-complete",
            diagnostic_session_id=pair.diagnostic_session_id,
            expected_revision=pair.diagnostic_revision + 3,
            executed_operation_ids=[
                "wave10-before",
                "wave10-after",
                "wave10-analysis",
            ],
        )
    )
    verification = completed["fix_verification"]
    assert isinstance(verification, Mapping)
    assert verification["status"] == "PASSED"
    assert verification["reason_code"] == "VERIFICATION_PASSED"

    fresh_context = DiagnosticWorkflowContext(
        pair.project_root,
        pair.data_root,
        pair.before_session_id,
    )
    shown = diagnostic_show_verification(
        fresh_context,
        diagnostic_session_id=pair.diagnostic_session_id,
    )
    assert shown.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "operation": _SHOW_OPERATION,
        "code": "OK",
        "message": "",
        "data": {
            "session": completed["session"],
            "fix_verifications": [verification],
            "authoritative": True,
        },
        "details": {},
    }
