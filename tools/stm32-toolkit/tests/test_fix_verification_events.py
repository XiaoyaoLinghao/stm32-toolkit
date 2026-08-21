from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_INVALID_TRANSITION,
    DIAGNOSTIC_PLAN_INVALID,
    DiagnosticEvent,
    DiagnosticMarkerRef,
    DiagnosticSession,
    DiagnosticValidationError,
    FixVerification,
    Hypothesis,
    ObservationPlan,
    ObservationResult,
    ObservationStep,
    SourceChangeDeclaration,
    VerificationPlan,
    calculate_plan_digest,
    canonical_diagnostic_json_bytes,
    create_event,
    reduce_event,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.store import EvidenceStore


IDENTITY = EvidenceIdentity(
    workspace_id="a" * 64,
    project_id="12345678-1234-5678-1234-567812345678",
    session_id="toolkit-session",
    build_id="b" * 64,
    elf_sha256="c" * 64,
    target_device="host:windows/amd64",
    input_snapshot_sha256="d" * 64,
    git_commit="e" * 40,
    git_dirty=False,
)
SID = "f" * 32
HYPOTHESIS_ID = "1" * 32
PLAN_ID = "2" * 64
RETRY_PLAN_ID = "9" * 64
ANALYSIS_IDS = ("3" * 64, "4" * 64)
ANALYSIS_EVIDENCE_IDS = ("5" * 64, "6" * 64)
RETRY_ANALYSIS_IDS = ("a" * 64, "b" * 64)
RETRY_ANALYSIS_EVIDENCE_IDS = ("c" * 64, "d" * 64)
UTC = "2026-08-21T12:00:00.000000Z"


def _event(
    *,
    sequence: int,
    event_type: str,
    request: dict[str, object],
    result: dict[str, object],
    previous_digest: str | None = None,
) -> DiagnosticEvent:
    return create_event(
        diagnostic_session_id=SID,
        operation_id=f"op-{sequence}",
        sequence=sequence,
        revision_before=sequence,
        event_type=event_type,
        occurred_at_utc=UTC,
        actor="user",
        previous_digest=previous_digest,
        payload={"request": request, "result": result},
    )


def _source(plan_id: str = PLAN_ID, *, diff_artifact: ArtifactRef | None = None, diff_evidence_id: str | None = None) -> SourceChangeDeclaration:
    return SourceChangeDeclaration.new(
        before_source_sha256="7" * 64,
        after_source_sha256="8" * 64,
        before_build_id="9" * 64,
        before_elf_sha256="a" * 64,
        after_build_id="b" * 64,
        after_elf_sha256="c" * 64,
        changed_paths=("src/main.c",),
        diff_evidence_id="d" * 64 if diff_evidence_id is None else diff_evidence_id,
        diff_artifact=(
            ArtifactRef(
                sha256="e" * 64,
                size_bytes=12,
                relative_path="changes.diff",
                kind="source-diff",
                media_type="text/x-diff",
            )
            if diff_artifact is None
            else diff_artifact
        ),
        claimed_hypothesis_ids=(HYPOTHESIS_ID,),
        validation_plan_id=plan_id,
    )


def _plan(
    source: SourceChangeDeclaration | None = None,
    plan_id: str = PLAN_ID,
    *,
    failed_before_evidence_id: str = "0" * 64,
    fixed_after_evidence_id: str = "1" * 64,
    required_analysis_ids: tuple[str, ...] = ANALYSIS_IDS,
    required_analysis_evidence_ids: tuple[str, ...] = ANALYSIS_EVIDENCE_IDS,
) -> VerificationPlan:
    declaration = _source(plan_id) if source is None else source
    return VerificationPlan.new(
        verification_plan_id=plan_id,
        diagnostic_session_id=SID,
        failed_before_run_id="run-1",
        failed_before_evidence_id=failed_before_evidence_id,
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id=fixed_after_evidence_id,
        required_analysis_ids=required_analysis_ids,
        required_analysis_evidence_ids=required_analysis_evidence_ids,
        required_monitor_quality="VALID",
        expected_changed=True,
    )


def _marker(
    plan: VerificationPlan | None = None,
    *,
    marker_id: str = "6" * 64,
    marker_evidence_id: str = "7" * 64,
    analysis_id: str = ANALYSIS_IDS[0],
    analysis_evidence_id: str = ANALYSIS_EVIDENCE_IDS[0],
) -> DiagnosticMarkerRef:
    _ = plan
    return DiagnosticMarkerRef.new(
        marker_id=marker_id,
        marker_evidence_id=marker_evidence_id,
        analysis_id=analysis_id,
        analysis_evidence_id=analysis_evidence_id,
        diagnostic_session_id=SID,
        hypothesis_id=HYPOTHESIS_ID,
        polarity="supports",
        label="change-observed",
        rationale="the fixed result changed the selected value",
    )


def _fix(plan: VerificationPlan | None = None, *, status: str = "PASSED", reason: str = "VERIFICATION_PASSED") -> FixVerification:
    value = _plan() if plan is None else plan
    return FixVerification.new(
        diagnostic_session_id=SID,
        failed_before_run_id=value.failed_before_run_id,
        failed_before_evidence_id=value.failed_before_evidence_id,
        source_change_declaration_id=value.source_change_declaration_id,
        fixed_after_run_id=value.fixed_after_run_id,
        fixed_after_evidence_id=value.fixed_after_evidence_id,
        verification_plan_id=value.verification_plan_id,
        verification_plan_digest=value.plan_digest,
        analysis_ids=value.required_analysis_ids,
        analysis_evidence_ids=value.required_analysis_evidence_ids,
        executed_operation_ids=("verification.start", "verification.complete"),
        status=status,
        reason_code=reason,
        completed_at_utc="2026-08-21T12:34:56.000000Z",
    )


def _created(failed_evidence_id: str = "0" * 64) -> tuple[DiagnosticSession, DiagnosticEvent]:
    event = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": failed_evidence_id, "identity": IDENTITY.to_dict()},
    )
    return reduce_event(None, event), event


def _investigating_with_hypothesis() -> tuple[DiagnosticSession, DiagnosticEvent]:
    session, previous = _created()
    started = _event(
        sequence=session.revision,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, started)
    hypothesis = _event(
        sequence=session.revision,
        event_type="hypothesis.added",
        request={"statement": "the source fix changes the monitor value"},
        result={
            "hypothesis": {
                "hypothesis_id": HYPOTHESIS_ID,
                "statement": "the source fix changes the monitor value",
                "status": "open",
                "confidence_basis": "unrated",
                "supporting": [],
                "refuting": [],
            }
        },
        previous_digest=started.digest,
    )
    return reduce_event(session, hypothesis), hypothesis


def _proposed() -> tuple[DiagnosticSession, SourceChangeDeclaration, VerificationPlan, DiagnosticEvent]:
    session, previous = _investigating_with_hypothesis()
    source = _source()
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, declared)
    plan = _plan(source)
    added = _event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": plan.to_dict()},
        result={"verification_plan_id": plan.verification_plan_id, "plan_digest": plan.plan_digest},
        previous_digest=declared.digest,
    )
    return reduce_event(session, added), source, plan, added


def _verifying() -> tuple[DiagnosticSession, SourceChangeDeclaration, VerificationPlan, DiagnosticEvent]:
    session, source, plan, previous = _proposed()
    started = _event(
        sequence=session.revision,
        event_type="verification.started",
        request={"verification_plan_id": plan.verification_plan_id},
        result={"verification_plan_id": plan.verification_plan_id},
        previous_digest=previous.digest,
    )
    return reduce_event(session, started), source, plan, started


def _publish_fixture_envelope(
    store: EvidenceStore,
    root: Path,
    *,
    identity: EvidenceIdentity,
    label: str,
    artifact: bool = False,
) -> tuple[str, ArtifactRef | None]:
    artifacts: tuple[ArtifactRef, ...] = ()
    artifact_ref: ArtifactRef | None = None
    if artifact:
        path = root / f"{label}.diff"
        path.write_bytes(f"fixture-{label}".encode("ascii"))
        artifact_ref = store.ingest_file(path, kind="source-diff", media_type="text/x-diff")
        artifacts = (artifact_ref,)
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="diagnostic-fixture",
        produced_at_utc=UTC,
        parents=(),
        artifacts=artifacts,
        metadata={"fixture": label},
    )
    store.put_envelope(envelope)
    return str(envelope.evidence_id), artifact_ref


def _persisted_fixture(tmp_path: Path, **identity_overrides: EvidenceIdentity) -> dict[str, object]:
    evidence = EvidenceStore(tmp_path / "evidence")
    after_identity = replace(IDENTITY, input_snapshot_sha256="8" * 64)
    identities = {
        "diff": IDENTITY,
        "fixed": after_identity,
        "analysis": after_identity,
        "marker": after_identity,
    }
    identities.update(identity_overrides)
    failed_id, _ = _publish_fixture_envelope(evidence, tmp_path, identity=IDENTITY, label="failed")
    diff_id, diff_artifact = _publish_fixture_envelope(
        evidence,
        tmp_path,
        identity=identities["diff"],
        label="diff",
        artifact=True,
    )
    assert diff_artifact is not None
    fixed_id, _ = _publish_fixture_envelope(evidence, tmp_path, identity=identities["fixed"], label="fixed")
    analysis_one_id, _ = _publish_fixture_envelope(
        evidence,
        tmp_path,
        identity=identities["analysis"],
        label="analysis-one",
    )
    analysis_two_id, _ = _publish_fixture_envelope(
        evidence,
        tmp_path,
        identity=identities["analysis"],
        label="analysis-two",
    )
    marker_id, _ = _publish_fixture_envelope(
        evidence,
        tmp_path,
        identity=identities["marker"],
        label="marker",
    )
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created_session, created = _created(failed_id)
    store.create(created)
    started = _event(
        sequence=created_session.revision,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
    )
    store.append(SID, started, expected_revision=1)
    hypothesis = _event(
        sequence=2,
        event_type="hypothesis.added",
        request={"statement": "the source fix changes the monitor value"},
        result={
            "hypothesis": {
                "hypothesis_id": HYPOTHESIS_ID,
                "statement": "the source fix changes the monitor value",
                "status": "open",
                "confidence_basis": "unrated",
                "supporting": [],
                "refuting": [],
            }
        },
        previous_digest=started.digest,
    )
    store.append(SID, hypothesis, expected_revision=2)
    source = _source(diff_artifact=diff_artifact, diff_evidence_id=diff_id)
    plan = _plan(
        source,
        failed_before_evidence_id=failed_id,
        fixed_after_evidence_id=fixed_id,
        required_analysis_evidence_ids=(analysis_one_id, analysis_two_id),
    )
    marker = _marker(plan, marker_evidence_id=marker_id, analysis_evidence_id=analysis_one_id)
    verification = _fix(plan)
    return {
        "evidence": evidence,
        "store": store,
        "failed_id": failed_id,
        "diff_id": diff_id,
        "fixed_id": fixed_id,
        "analysis_ids": (analysis_one_id, analysis_two_id),
        "marker_id": marker_id,
        "source": source,
        "plan": plan,
        "marker": marker,
        "verification": verification,
        "session": store.load(SID),
    }


def _append_new_lifecycle(fixture: dict[str, object]) -> DiagnosticSession:
    store = fixture["store"]
    assert isinstance(store, DiagnosticStore)
    session = fixture["session"]
    assert isinstance(session, DiagnosticSession)
    source = fixture["source"]
    plan = fixture["plan"]
    marker = fixture["marker"]
    verification = fixture["verification"]
    assert isinstance(source, SourceChangeDeclaration)
    assert isinstance(plan, VerificationPlan)
    assert isinstance(marker, DiagnosticMarkerRef)
    assert isinstance(verification, FixVerification)
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    session = store.append(SID, declared, expected_revision=session.revision).session
    added = _event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": plan.to_dict()},
        result={"verification_plan_id": plan.verification_plan_id, "plan_digest": plan.plan_digest},
        previous_digest=session.event_head,
    )
    session = store.append(SID, added, expected_revision=session.revision).session
    started = _event(
        sequence=session.revision,
        event_type="verification.started",
        request={"verification_plan_id": plan.verification_plan_id},
        result={"verification_plan_id": plan.verification_plan_id},
        previous_digest=session.event_head,
    )
    session = store.append(SID, started, expected_revision=session.revision).session
    attached = _event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=session.event_head,
    )
    session = store.append(SID, attached, expected_revision=session.revision).session
    completed = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=session.event_head,
    )
    return store.append(SID, completed, expected_revision=session.revision).session


def _checkpoint_parents(evidence: EvidenceStore, revision: int) -> tuple[str, ...]:
    root = get_root(evidence, "diagnostic-session", f"{SID}.{revision:08d}")
    return evidence.get_envelope(root.manifest_id).parents


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _storage_snapshot(fixture: dict[str, object]) -> tuple[dict[str, bytes], dict[str, bytes]]:
    store = fixture["store"]
    evidence = fixture["evidence"]
    assert isinstance(store, DiagnosticStore)
    assert isinstance(evidence, EvidenceStore)
    return _tree_bytes(store.diagnostics_root), _tree_bytes(evidence.root)


def test_new_lifecycle_reduces_and_extended_session_round_trips() -> None:
    session, source, plan, previous = _verifying()
    marker = _marker(plan)
    attached = _event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=previous.digest,
    )
    session = reduce_event(session, attached)
    assert session.state == "VERIFYING"
    assert session.active_verification_plan_id == plan.verification_plan_id
    assert session.diagnostic_marker_refs == (marker,)

    verification = _fix(plan)
    completed = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=attached.digest,
    )
    session = reduce_event(session, completed)
    assert session.state == "RESOLVED"
    assert session.active_verification_plan_id is None
    assert session.source_change_declarations == (source,)
    assert session.verification_plans == (plan,)
    assert session.fix_verifications == (verification,)
    encoded = session.to_dict()
    assert set(encoded) == {
        "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id",
        "failed_evidence_id", "event_head", "hypotheses", "observation_plans", "observation_results",
        "source_change_declarations", "verification_plans", "diagnostic_marker_refs",
        "fix_verifications", "active_verification_plan_id",
    }
    assert DiagnosticSession.from_value(encoded) == session


def test_legacy_session_shape_and_constructor_remain_unchanged() -> None:
    session, _ = _created()
    assert set(session.to_dict()) == {
        "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id",
        "failed_evidence_id", "event_head", "hypotheses", "observation_plans", "observation_results",
    }
    assert DiagnosticSession.from_value(session.to_dict()) == session
    assert canonical_diagnostic_json_bytes(session.to_dict()) == canonical_diagnostic_json_bytes(
        {
            "diagnostic_session_id": SID,
            "revision": 1,
            "state": "OPEN",
            "identity": IDENTITY.to_dict(),
            "failed_test_run_id": "run-1",
            "failed_evidence_id": "0" * 64,
            "event_head": session.event_head,
            "hypotheses": [],
            "observation_plans": [],
            "observation_results": [],
        }
    )
    positional = DiagnosticSession(
        SID, 1, "OPEN", IDENTITY, "run-1", "0" * 64, session.event_head, (), (), ()
    )
    assert positional.to_dict() == session.to_dict()


@pytest.mark.parametrize(
    "status,reason,expected_state",
    [
        ("FAILED", "FIXED_TEST_FAILED", "INVESTIGATING"),
        ("INCONCLUSIVE", "ANALYSIS_NOT_VALID", "INVESTIGATING"),
        ("CANCELLED", "CALLER_CANCELLED", "INVESTIGATING"),
    ],
)
def test_non_passed_completion_keeps_attempt_and_returns_to_investigating(
    status: str, reason: str, expected_state: str,
) -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan, status=status, reason=reason)
    event = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": status,
            "reason_code": reason,
        },
        previous_digest=previous.digest,
    )
    reduced = reduce_event(session, event)
    assert reduced.state == expected_state
    assert reduced.active_verification_plan_id is None
    assert reduced.fix_verifications == (verification,)


def test_reducer_rejects_missing_reference_plan_mismatch_and_wrong_marker_pair() -> None:
    session, previous = _investigating_with_hypothesis()
    source = _source("f" * 64)
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=previous.digest,
    )
    proposed = reduce_event(session, declared)
    wrong_plan = _plan(source, "e" * 64)
    mismatch = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": wrong_plan.to_dict()},
        result={"verification_plan_id": wrong_plan.verification_plan_id, "plan_digest": wrong_plan.plan_digest},
        previous_digest=declared.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(proposed, mismatch)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID

    valid_plan = _plan(source, "f" * 64)
    added = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": valid_plan.to_dict()},
        result={"verification_plan_id": valid_plan.verification_plan_id, "plan_digest": valid_plan.plan_digest},
        previous_digest=declared.digest,
    )
    proposed = reduce_event(proposed, added)
    started = _event(
        sequence=proposed.revision,
        event_type="verification.started",
        request={"verification_plan_id": valid_plan.verification_plan_id},
        result={"verification_plan_id": valid_plan.verification_plan_id},
        previous_digest=added.digest,
    )
    verifying = reduce_event(proposed, started)
    wrong_marker = DiagnosticMarkerRef.new(
        marker_id="8" * 64,
        marker_evidence_id="9" * 64,
        analysis_id="a" * 64,
        analysis_evidence_id="b" * 64,
        diagnostic_session_id=SID,
        hypothesis_id=HYPOTHESIS_ID,
        polarity="supports",
        label="change-observed",
        rationale="wrong analysis pair",
    )
    marker_event = _event(
        sequence=verifying.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": wrong_marker.to_dict()},
        result={"marker_id": wrong_marker.marker_id},
        previous_digest=started.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(verifying, marker_event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


def test_new_payloads_are_closed_and_transitions_are_rejected() -> None:
    session, previous = _investigating_with_hypothesis()
    source = _source()
    # The payload validator runs while the event is created.
    with pytest.raises(DiagnosticValidationError) as error:
        _event(
            sequence=session.revision,
            event_type="source_change.declared",
            request={"source_change_declaration": source.to_dict(), "extra": True},
            result={"declaration_id": source.declaration_id},
            previous_digest=previous.digest,
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    created, created_event = _created()
    source_event = _event(
        sequence=created.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=created_event.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(created, source_event)
    assert error.value.code == DIAGNOSTIC_INVALID_TRANSITION


def test_completion_must_bind_active_plan_and_all_identity_fields() -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan)
    tampered = verification.to_dict()
    tampered["fixed_after_run_id"] = "run-other"
    with pytest.raises(DiagnosticValidationError):
        # The fixed verification ID still belongs to the original content, so event
        # construction must fail closed before reduction.
        _event(
            sequence=session.revision,
            event_type="verification.completed",
            request={"fix_verification": tampered},
            result={
                "fix_verification_id": verification.fix_verification_id,
                "status": verification.status,
                "reason_code": verification.reason_code,
            },
            previous_digest=previous.digest,
        )

    separately_valid = _fix(plan)
    separately_valid = FixVerification.new(
        diagnostic_session_id="0" * 32,
        failed_before_run_id=separately_valid.failed_before_run_id,
        failed_before_evidence_id=separately_valid.failed_before_evidence_id,
        source_change_declaration_id=separately_valid.source_change_declaration_id,
        fixed_after_run_id=separately_valid.fixed_after_run_id,
        fixed_after_evidence_id=separately_valid.fixed_after_evidence_id,
        verification_plan_id=separately_valid.verification_plan_id,
        verification_plan_digest=separately_valid.verification_plan_digest,
        analysis_ids=separately_valid.analysis_ids,
        analysis_evidence_ids=separately_valid.analysis_evidence_ids,
        executed_operation_ids=separately_valid.executed_operation_ids,
        status=separately_valid.status,
        reason_code=separately_valid.reason_code,
        completed_at_utc=separately_valid.completed_at_utc,
    )
    valid_binding_event = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": separately_valid.to_dict()},
        result={
            "fix_verification_id": separately_valid.fix_verification_id,
            "status": separately_valid.status,
            "reason_code": separately_valid.reason_code,
        },
        previous_digest=previous.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(session, valid_binding_event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID


def test_failed_attempt_allows_new_plan_while_retaining_historical_marker() -> None:
    session, source, plan, previous = _verifying()
    marker = _marker(plan)
    attached = _event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=previous.digest,
    )
    verifying = reduce_event(session, attached)
    failed = _fix(plan, status="FAILED", reason="FIXED_TEST_FAILED")
    completed = _event(
        sequence=verifying.revision,
        event_type="verification.completed",
        request={"fix_verification": failed.to_dict()},
        result={
            "fix_verification_id": failed.fix_verification_id,
            "status": failed.status,
            "reason_code": failed.reason_code,
        },
        previous_digest=attached.digest,
    )
    investigating = reduce_event(verifying, completed)

    retry_source = _source(RETRY_PLAN_ID)
    declared = _event(
        sequence=investigating.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": retry_source.to_dict()},
        result={"declaration_id": retry_source.declaration_id},
        previous_digest=completed.digest,
    )
    proposed = reduce_event(investigating, declared)
    retry_plan = VerificationPlan.new(
        verification_plan_id=RETRY_PLAN_ID,
        diagnostic_session_id=SID,
        failed_before_run_id="run-1",
        failed_before_evidence_id="0" * 64,
        source_change_declaration_id=retry_source.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id="1" * 64,
        required_analysis_ids=RETRY_ANALYSIS_IDS,
        required_analysis_evidence_ids=RETRY_ANALYSIS_EVIDENCE_IDS,
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    added = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": retry_plan.to_dict()},
        result={"verification_plan_id": retry_plan.verification_plan_id, "plan_digest": retry_plan.plan_digest},
        previous_digest=declared.digest,
    )
    proposed = reduce_event(proposed, added)
    started = _event(
        sequence=proposed.revision,
        event_type="verification.started",
        request={"verification_plan_id": retry_plan.verification_plan_id},
        result={"verification_plan_id": retry_plan.verification_plan_id},
        previous_digest=added.digest,
    )
    retrying = reduce_event(proposed, started)
    assert retrying.state == "VERIFYING"
    assert retrying.active_verification_plan_id == RETRY_PLAN_ID
    assert retrying.diagnostic_marker_refs == (marker,)
    assert retrying.fix_verifications == (failed,)
    assert retrying.source_change_declarations == (source, retry_source)
    assert retrying.verification_plans == (plan, retry_plan)


def test_plan_add_requires_session_failed_run_and_evidence_pair_before_mutation() -> None:
    session, previous = _investigating_with_hypothesis()
    source = _source()
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=previous.digest,
    )
    proposed = reduce_event(session, declared)
    wrong_pair = VerificationPlan.new(
        verification_plan_id=PLAN_ID,
        diagnostic_session_id=SID,
        failed_before_run_id="run-other",
        failed_before_evidence_id="2" * 64,
        source_change_declaration_id=source.declaration_id,
        fixed_after_run_id="run-2",
        fixed_after_evidence_id="1" * 64,
        required_analysis_ids=ANALYSIS_IDS,
        required_analysis_evidence_ids=ANALYSIS_EVIDENCE_IDS,
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    event = _event(
        sequence=proposed.revision,
        event_type="verification.plan_added",
        request={"verification_plan": wrong_pair.to_dict()},
        result={"verification_plan_id": wrong_pair.verification_plan_id, "plan_digest": wrong_pair.plan_digest},
        previous_digest=declared.digest,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        reduce_event(proposed, event)
    assert error.value.code == DIAGNOSTIC_PLAN_INVALID
    assert proposed.verification_plans == ()


def test_legacy_subclasses_and_tuple_subclasses_remain_constructor_compatible() -> None:
    class LegacyHypothesis(Hypothesis):
        pass

    class LegacyObservationPlan(ObservationPlan):
        pass

    class LegacyObservationResult(ObservationResult):
        pass

    class LegacyTuple(tuple):
        pass

    step = ObservationStep(
        step_id="failed-state",
        selector={"kind": "run-state"},
        expected_value="failed",
        purpose="bind the original failed run",
    )
    plan_fields = {"diagnostic_session_id": SID, "created_revision": 3, "steps": [step.to_dict()]}
    plan_id = calculate_plan_digest(plan_fields)
    plan = LegacyObservationPlan(
        plan_id=plan_id,
        diagnostic_session_id=SID,
        created_revision=3,
        steps=(step,),
        digest=plan_id,
    )
    result = LegacyObservationResult(
        plan_id=plan_id,
        step_id=step.step_id,
        evidence_id="0" * 64,
        selector=step.selector,
        observed_value="failed",
        expected_value="failed",
        matched=True,
    )
    hypothesis = LegacyHypothesis(
        hypothesis_id=HYPOTHESIS_ID,
        statement="the source fix changes the monitor value",
        status="open",
        confidence_basis="unrated",
        supporting=(),
        refuting=(),
    )
    session = DiagnosticSession(
        diagnostic_session_id=SID,
        revision=1,
        state="INVESTIGATING",
        identity=IDENTITY,
        failed_test_run_id="run-1",
        failed_evidence_id="0" * 64,
        event_head="a" * 64,
        hypotheses=LegacyTuple((hypothesis,)),
        observation_plans=LegacyTuple((plan,)),
        observation_results=LegacyTuple((result,)),
    )
    assert session.hypotheses == (hypothesis,)


def test_completion_result_status_and_reason_are_closed_and_terminal_states_reject_events() -> None:
    session, _, plan, previous = _verifying()
    verification = _fix(plan)
    with pytest.raises(DiagnosticValidationError) as error:
        _event(
            sequence=session.revision,
            event_type="verification.completed",
            request={"fix_verification": verification.to_dict()},
            result={
                "fix_verification_id": verification.fix_verification_id,
                "status": "FAILED",
                "reason_code": "FIXED_TEST_FAILED",
            },
            previous_digest=previous.digest,
        )
    assert error.value.code == DIAGNOSTIC_INVALID_EVENT

    completed = _event(
        sequence=session.revision,
        event_type="verification.completed",
        request={"fix_verification": verification.to_dict()},
        result={
            "fix_verification_id": verification.fix_verification_id,
            "status": verification.status,
            "reason_code": verification.reason_code,
        },
        previous_digest=previous.digest,
    )
    resolved = reduce_event(session, completed)
    for terminal in (resolved, replace(resolved, state="ABANDONED")):
        later = _event(
            sequence=terminal.revision,
            event_type="investigation.started",
            request={},
            result={},
            previous_digest=terminal.event_head,
        )
        with pytest.raises(DiagnosticValidationError) as error:
            reduce_event(terminal, later)
        assert error.value.code == DIAGNOSTIC_INVALID_TRANSITION


def test_store_checkpoints_all_new_parent_orders_and_reloads(tmp_path: Path) -> None:
    fixture = _persisted_fixture(tmp_path)
    store = fixture["store"]
    evidence = fixture["evidence"]
    assert isinstance(store, DiagnosticStore)
    assert isinstance(evidence, EvidenceStore)
    final = _append_new_lifecycle(fixture)
    assert final.state == "RESOLVED"
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000003").manifest_id
    failed_id = fixture["failed_id"]
    diff_id = fixture["diff_id"]
    fixed_id = fixture["fixed_id"]
    analysis_ids = fixture["analysis_ids"]
    marker_id = fixture["marker_id"]
    assert isinstance(failed_id, str)
    assert isinstance(diff_id, str)
    assert isinstance(fixed_id, str)
    assert isinstance(analysis_ids, tuple)
    assert isinstance(marker_id, str)
    assert _checkpoint_parents(evidence, 4) == (previous, diff_id)
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000004").manifest_id
    assert _checkpoint_parents(evidence, 5) == (previous, failed_id, fixed_id, *analysis_ids)
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000005").manifest_id
    assert _checkpoint_parents(evidence, 6) == (previous,)
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000006").manifest_id
    assert _checkpoint_parents(evidence, 7) == (previous, marker_id, analysis_ids[0])
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000007").manifest_id
    assert _checkpoint_parents(evidence, 8) == (previous, failed_id, fixed_id, *analysis_ids)
    reloaded = DiagnosticStore(tmp_path / "diagnostics", EvidenceStore(evidence.root)).load(SID)
    assert reloaded.to_dict() == final.to_dict()


@pytest.mark.parametrize("role", ["diff", "fixed", "analysis", "marker"])
def test_store_rejects_new_parent_wrong_scope_before_append(tmp_path: Path, role: str) -> None:
    wrong = replace(IDENTITY, workspace_id="f" * 64)
    fixture = _persisted_fixture(tmp_path, **{role: wrong})
    store = fixture["store"]
    assert isinstance(store, DiagnosticStore)
    session = fixture["session"]
    assert isinstance(session, DiagnosticSession)
    source = fixture["source"]
    plan = fixture["plan"]
    marker = fixture["marker"]
    assert isinstance(source, SourceChangeDeclaration)
    assert isinstance(plan, VerificationPlan)
    assert isinstance(marker, DiagnosticMarkerRef)
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    if role == "diff":
        before_tree = _storage_snapshot(fixture)
        with pytest.raises(DiagnosticValidationError) as error:
            store.append(SID, declared, expected_revision=session.revision)
        assert error.value.code == DIAGNOSTIC_IDENTITY_MISMATCH
        assert _storage_snapshot(fixture) == before_tree
        assert store.load(SID).revision == session.revision
        return
    session = store.append(SID, declared, expected_revision=session.revision).session
    added = _event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": plan.to_dict()},
        result={"verification_plan_id": plan.verification_plan_id, "plan_digest": plan.plan_digest},
        previous_digest=session.event_head,
    )
    if role in {"fixed", "analysis"}:
        with pytest.raises(DiagnosticValidationError) as error:
            store.append(SID, added, expected_revision=session.revision)
        assert error.value.code == DIAGNOSTIC_IDENTITY_MISMATCH
        assert store.load(SID).revision == session.revision
        return
    session = store.append(SID, added, expected_revision=session.revision).session
    started = _event(
        sequence=session.revision,
        event_type="verification.started",
        request={"verification_plan_id": plan.verification_plan_id},
        result={"verification_plan_id": plan.verification_plan_id},
        previous_digest=session.event_head,
    )
    session = store.append(SID, started, expected_revision=session.revision).session
    attached = _event(
        sequence=session.revision,
        event_type="analysis.marker_attached",
        request={"diagnostic_marker_ref": marker.to_dict()},
        result={"marker_id": marker.marker_id},
        previous_digest=session.event_head,
    )
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, attached, expected_revision=session.revision)
    assert error.value.code == DIAGNOSTIC_IDENTITY_MISMATCH
    assert store.load(SID).revision == session.revision


def test_store_requires_exact_declared_diff_artifact_before_append(tmp_path: Path) -> None:
    fixture = _persisted_fixture(tmp_path)
    store = fixture["store"]
    session = fixture["session"]
    source = fixture["source"]
    diff_id = fixture["diff_id"]
    assert isinstance(store, DiagnosticStore)
    assert isinstance(session, DiagnosticSession)
    assert isinstance(source, SourceChangeDeclaration)
    assert isinstance(diff_id, str)
    wrong_artifact = ArtifactRef(
        sha256="f" * 64,
        size_bytes=7,
        relative_path="other.diff",
        kind="source-diff",
        media_type="text/x-diff",
    )
    wrong_source = _source(diff_artifact=wrong_artifact, diff_evidence_id=diff_id)
    event = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": wrong_source.to_dict()},
        result={"declaration_id": wrong_source.declaration_id},
        previous_digest=session.event_head,
    )
    before_tree = _storage_snapshot(fixture)
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, event, expected_revision=session.revision)
    assert error.value.code == DIAGNOSTIC_EVIDENCE_MISSING
    assert _storage_snapshot(fixture) == before_tree
    assert store.load(SID).revision == session.revision


@pytest.mark.parametrize("corrupt", [False, True])
def test_store_rejects_missing_or_corrupt_new_parent_without_append(tmp_path: Path, corrupt: bool) -> None:
    fixture = _persisted_fixture(tmp_path)
    store = fixture["store"]
    evidence = fixture["evidence"]
    session = fixture["session"]
    source = fixture["source"]
    plan = fixture["plan"]
    fixed_id = fixture["fixed_id"]
    assert isinstance(store, DiagnosticStore)
    assert isinstance(evidence, EvidenceStore)
    assert isinstance(session, DiagnosticSession)
    assert isinstance(source, SourceChangeDeclaration)
    assert isinstance(plan, VerificationPlan)
    assert isinstance(fixed_id, str)
    manifest = evidence.root / "manifests" / f"{fixed_id}.json"
    if corrupt:
        manifest.write_bytes(b"{}")
    else:
        manifest.unlink()
    declared = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    session = store.append(SID, declared, expected_revision=session.revision).session
    added = _event(
        sequence=session.revision,
        event_type="verification.plan_added",
        request={"verification_plan": plan.to_dict()},
        result={"verification_plan_id": plan.verification_plan_id, "plan_digest": plan.plan_digest},
        previous_digest=session.event_head,
    )
    before_tree = _storage_snapshot(fixture)
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, added, expected_revision=session.revision)
    assert error.value.code == DIAGNOSTIC_EVIDENCE_MISSING
    assert _storage_snapshot(fixture) == before_tree
    assert store.load(SID).revision == session.revision


def test_new_event_checkpoint_repairs_after_interrupted_event_publication(tmp_path: Path) -> None:
    fixture = _persisted_fixture(tmp_path)
    evidence = fixture["evidence"]
    session = fixture["session"]
    source = fixture["source"]
    assert isinstance(evidence, EvidenceStore)
    assert isinstance(session, DiagnosticSession)
    assert isinstance(source, SourceChangeDeclaration)
    event = _event(
        sequence=session.revision,
        event_type="source_change.declared",
        request={"source_change_declaration": source.to_dict()},
        result={"declaration_id": source.declaration_id},
        previous_digest=session.event_head,
    )
    fired = False

    def inject(point: str) -> None:
        nonlocal fired
        if point == "event.after_publish" and not fired:
            fired = True
            raise RuntimeError("interrupted")

    crashing = DiagnosticStore(tmp_path / "diagnostics", evidence, fault_injector=inject)
    event_path = tmp_path / "diagnostics" / "sessions" / SID / "events" / "00000003.json"
    with pytest.raises(RuntimeError, match="interrupted"):
        crashing.append(SID, event, expected_revision=session.revision)
    event_bytes = event_path.read_bytes()
    recovered = DiagnosticStore(tmp_path / "diagnostics", EvidenceStore(evidence.root))
    assert recovered.load(SID).revision == 4
    assert event_path.read_bytes() == event_bytes
    assert _checkpoint_parents(evidence, 4)[-1] == fixture["diff_id"]


def test_store_deduplicates_duplicate_new_parent_ids_in_first_seen_order(tmp_path: Path) -> None:
    fixture = _persisted_fixture(tmp_path)
    evidence = fixture["evidence"]
    plan = fixture["plan"]
    analysis_ids = fixture["analysis_ids"]
    assert isinstance(evidence, EvidenceStore)
    assert isinstance(plan, VerificationPlan)
    assert isinstance(analysis_ids, tuple)
    assert isinstance(analysis_ids[0], str)
    fixture["marker"] = _marker(
        plan,
        marker_evidence_id=analysis_ids[0],
        analysis_evidence_id=analysis_ids[0],
    )
    assert _append_new_lifecycle(fixture).state == "RESOLVED"
    previous = get_root(evidence, "diagnostic-session", f"{SID}.00000006").manifest_id
    assert _checkpoint_parents(evidence, 7) == (previous, analysis_ids[0])
