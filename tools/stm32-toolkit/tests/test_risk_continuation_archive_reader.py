"""Bounded readers-only checks for the archived VS10-A continuation graph.

The archive is an input fixture, not a source of current physical evidence.  The
tests authenticate the immutable graph through the public continuation readers,
then mutate only run-owned copies of public root records for refusal checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from stm32_toolkit.acceptance.continuation import (
    CONTINUATION_REQUEST_SCHEMA,
    ContinuationIdentityError,
    ContinuationRequest,
    ContinuationValidationError,
    authenticate_continuation,
    authenticate_plan_continuation,
    prepare_continuation,
    validate_continuation_reference,
)
from stm32_toolkit.diagnostics.model import VerificationPlan
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import canonical_json_bytes, get_root
from stm32_toolkit.evidence.store import EvidenceStore

_ARCHIVE_ENV = "STM32TK_VS10A_PUBLIC_DATA_ARCHIVE"
_CHECKSUMS_SHA256 = "509a7db2c51cc89704a6d35cf591f619223f01af7293b7aae0307364bb3e43f0"
_PUBLIC_FILE_COUNT = 174
_PUBLIC_BYTE_COUNT = 2_512_425
_CONTINUATION_OPERATION = "physical-continuation"
_ARCHIVE_PROJECT_KEY = "d7b137149685154d159f2f0d"
_CONTINUATION_EVIDENCE_ID = (
    "6af4ea4fddebe07a0a2899ce1adf142c869ddd10d5d8645f5254ca61f9d4e4be"
)


TreeSnapshot = tuple[tuple[str, bytes], ...]


@dataclass(frozen=True)
class ArchiveCase:
    source_public_data: Path
    source_snapshot: TreeSnapshot
    public_data: Path
    project_root: Path
    evidence: EvidenceStore
    diagnostics_root: Path
    continuation_evidence_id: str
    association: object


def _snapshot(root: Path) -> TreeSnapshot:
    return tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _archive_paths() -> tuple[Path, Path]:
    configured = os.environ.get(_ARCHIVE_ENV)
    if not configured:
        pytest.skip(f"set {_ARCHIVE_ENV} for the selected archived public-data batch")

    configured_path = Path(configured)
    if configured_path.name.casefold() == "public-data":
        bundle_root = configured_path.parent
        public_data = configured_path
    else:
        bundle_root = configured_path
        public_data = configured_path / "public-data"
    checksums = bundle_root / "CHECKSUMS.sha256"
    if not public_data.is_dir() or not checksums.is_file():
        pytest.fail(f"configured archive is incomplete: {configured_path}")
    if hashlib.sha256(checksums.read_bytes()).hexdigest() != _CHECKSUMS_SHA256:
        pytest.fail(
            "configured VS10-A archive checksum manifest does not match the pinned input"
        )

    snapshot = _snapshot(public_data)
    if (
        len(snapshot) != _PUBLIC_FILE_COUNT
        or sum(len(raw) for _, raw in snapshot) != _PUBLIC_BYTE_COUNT
    ):
        pytest.fail(
            "configured VS10-A public-data file set does not match the pinned archive"
        )
    return bundle_root, public_data


def _project_root(public_data: Path) -> Path:
    candidates = []
    for candidate in sorted((public_data / "projects").iterdir()):
        if not candidate.is_dir():
            continue
        if (candidate / "evidence" / "roots" / "physical-continuation").is_dir() and (
            candidate / "diagnostics"
        ).is_dir():
            candidates.append(candidate)
    if len(candidates) != 1:
        pytest.fail(
            f"expected one archived continuation project, found {len(candidates)}"
        )
    if candidates[0].name != _ARCHIVE_PROJECT_KEY:
        pytest.fail(
            "the archived continuation project is not the pinned VS10-A public-data project"
        )
    return candidates[0]


def _load_case(tmp_path: Path) -> ArchiveCase:
    _, source_public_data = _archive_paths()
    source_snapshot = _snapshot(source_public_data)
    public_data = tmp_path / "public-data"
    shutil.copytree(source_public_data, public_data)
    if _snapshot(public_data) != source_snapshot:
        pytest.fail("archived public-data copy is not byte-exact")

    project_root = _project_root(public_data)
    evidence = EvidenceStore(project_root / "evidence")
    continuation_manifests = sorted(
        path
        for path in (evidence.root / "manifests").glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("operation")
        == _CONTINUATION_OPERATION
    )
    if len(continuation_manifests) != 1:
        pytest.fail(
            f"expected one archived continuation manifest, found {len(continuation_manifests)}"
        )
    continuation_evidence_id = continuation_manifests[0].stem
    if continuation_evidence_id != _CONTINUATION_EVIDENCE_ID:
        pytest.fail(
            "the archived continuation evidence ID is not the pinned VS10-A proof"
        )
    association = _authenticate(
        evidence, project_root / "diagnostics", continuation_evidence_id
    )
    return ArchiveCase(
        source_public_data=source_public_data,
        source_snapshot=source_snapshot,
        public_data=public_data,
        project_root=project_root,
        evidence=evidence,
        diagnostics_root=project_root / "diagnostics",
        continuation_evidence_id=continuation_evidence_id,
        association=association,
    )


def _authenticate(
    evidence: EvidenceStore, diagnostics_root: Path, continuation_evidence_id: str
):
    """Read the proof with every available public consumer-context binding."""
    # Importing the association's IDs from the archive is intentionally done in
    # two steps: the first call proves the historical proof is genuine, and the
    # second call exercises the public expected-context checks using those IDs.
    association = authenticate_continuation(
        evidence, diagnostics_root, continuation_evidence_id
    )
    proof = association.proof
    identity = association.envelope.identity
    return authenticate_continuation(
        evidence,
        diagnostics_root,
        continuation_evidence_id,
        expected_workspace_id=identity.workspace_id,
        expected_project_id=identity.project_id,
        expected_session_id=identity.session_id,
        expected_diagnostic_session_id=proof.diagnostic_session_id,
        expected_fixed_after_test_run_id=proof.fixed_after_test_run_id,
        expected_fixed_after_evidence_id=proof.fixed_after_evidence_id,
        expected_diagnostic_revision=proof.diagnostic_revision,
        expected_diagnostic_event_head=proof.diagnostic_event_head,
    )


def _bind_request(association: object) -> ContinuationRequest:
    proof = association.proof
    return ContinuationRequest.from_value(
        {
            "schema": CONTINUATION_REQUEST_SCHEMA,
            "kind": "bind",
            "predecessorAttemptId": proof.predecessor_attempt_id,
            "predecessorCheckpointId": proof.predecessor_checkpoint_id,
            "predecessorEvidenceId": proof.predecessor_evidence_id,
            "fixedAfterTestRunId": proof.fixed_after_test_run_id,
            "fixedAfterEvidenceId": proof.fixed_after_evidence_id,
            "diagnosticRevision": proof.diagnostic_revision,
            "diagnosticEventHead": proof.diagnostic_event_head,
        }
    )


def _prepare(
    evidence: EvidenceStore,
    diagnostics_root: Path,
    association: object,
    request: ContinuationRequest,
    *,
    session_id: str,
):
    identity = association.envelope.identity
    return prepare_continuation(
        evidence,
        diagnostics_root,
        request,
        workspace_id=identity.workspace_id,
        project_id=identity.project_id,
        expected_session_id=session_id,
    )


def _assert_snapshot_unchanged(root: Path, before: TreeSnapshot) -> None:
    assert _snapshot(root) == before


def _public_root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    name = (
        hashlib.sha256(
            canonical_json_bytes({"root_type": root_type, "root_id": root_id})
        ).hexdigest()
        + ".json"
    )
    return evidence.root / "roots" / root_type / name


def _mutate_root(path: Path, mutation: Callable[[dict[str, object]], None]) -> bytes:
    original = path.read_bytes()
    value = json.loads(original.decode("utf-8"))
    assert isinstance(value, dict)
    mutation(value)
    path.write_bytes(canonical_json_bytes(value))
    return original


def _analysis_candidate(evidence: EvidenceStore, association: object):
    for path in sorted((evidence.root / "manifests").glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("operation") != "monitor-analysis":
            continue
        candidate = evidence.get_envelope(path.stem)
        try:
            validate_continuation_reference(evidence, association, candidate)
        except ContinuationValidationError:
            continue
        return candidate
    pytest.fail("the archived public-data copy has no valid monitor-analysis reference")


def _monitor_root_paths(
    evidence: EvidenceStore, analysis: object
) -> tuple[Path, Path, str]:
    parent = evidence.get_envelope(analysis.parents[0])
    assert parent.operation == "monitor-physical-window"
    assert len(parent.artifacts) == 1
    source_record_sha256 = parent.artifacts[0].sha256
    run_path = None
    operation_id = None
    for path in sorted((evidence.root / "roots" / "monitor-run").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("root_type") == "monitor-run"
            and value.get("manifest_id") == str(parent.evidence_id)
            and value.get("metadata", {}).get("source_record_sha256")
            == source_record_sha256
        ):
            run_path = path
            operation_id = value.get("root_id")
            break
    if run_path is None or not isinstance(operation_id, str):
        pytest.fail("the archived monitor transcript has no matching monitor-run root")

    ref_path = None
    for path in sorted((evidence.root / "roots" / "monitor-run-ref").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("root_type") == "monitor-run-ref"
            and value.get("root_id") == operation_id
        ):
            ref_path = path
            break
    if ref_path is None:
        pytest.fail(
            "the archived monitor transcript has no matching monitor-run-ref root"
        )
    return run_path, ref_path, operation_id


def _assert_restored_case(case: ArchiveCase) -> object:
    fresh_evidence = EvidenceStore(case.project_root / "evidence")
    restored = _authenticate(
        fresh_evidence, case.diagnostics_root, case.continuation_evidence_id
    )
    assert restored.proof == case.association.proof
    return restored


def test_archived_continuation_authenticate_and_prepare_public_context_variants(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = _snapshot(case.public_data)
    request = _bind_request(case.association)
    proof = case.association.proof
    identity = case.association.envelope.identity

    # The durable session is read through the public DiagnosticStore.  Its
    # verification plan is the actual archived ``verification.plan_added``
    # payload, so this exercises the plan-binding reader without reconstructing
    # a plan or changing the archived session.
    session = DiagnosticStore(case.diagnostics_root, case.evidence).load_durable(
        proof.diagnostic_session_id
    )
    assert session.verification_plans
    plan = session.verification_plans[0]
    before_plan_auth = _snapshot(case.public_data)
    plan_association = authenticate_plan_continuation(
        case.evidence, case.diagnostics_root, plan, session
    )
    assert plan_association.proof == proof
    _assert_snapshot_unchanged(case.public_data, before_plan_auth)

    wrong_plan_id = (
        "0" if plan.verification_plan_id[0] != "0" else "1"
    ) + plan.verification_plan_id[1:]
    wrong_plan = VerificationPlan.new(
        verification_plan_id=wrong_plan_id,
        diagnostic_session_id=plan.diagnostic_session_id,
        failed_before_run_id=plan.failed_before_run_id,
        failed_before_evidence_id=plan.failed_before_evidence_id,
        source_change_declaration_id=plan.source_change_declaration_id,
        fixed_after_run_id=plan.fixed_after_run_id,
        fixed_after_evidence_id=plan.fixed_after_evidence_id,
        required_analysis_ids=plan.required_analysis_ids,
        required_analysis_evidence_ids=plan.required_analysis_evidence_ids,
        required_monitor_quality=plan.required_monitor_quality,
        expected_changed=plan.expected_changed,
        continuation_evidence_id=plan.continuation_evidence_id,
    )
    assert wrong_plan.verification_plan_id != plan.verification_plan_id
    assert wrong_plan.diagnostic_session_id == plan.diagnostic_session_id
    assert wrong_plan.failed_before_run_id == plan.failed_before_run_id
    assert wrong_plan.failed_before_evidence_id == plan.failed_before_evidence_id
    assert wrong_plan.source_change_declaration_id == plan.source_change_declaration_id
    assert wrong_plan.fixed_after_run_id == plan.fixed_after_run_id
    assert wrong_plan.fixed_after_evidence_id == plan.fixed_after_evidence_id
    assert wrong_plan.required_analysis_ids == plan.required_analysis_ids
    assert (
        wrong_plan.required_analysis_evidence_ids == plan.required_analysis_evidence_ids
    )
    assert wrong_plan.required_monitor_quality == plan.required_monitor_quality
    assert wrong_plan.expected_changed == plan.expected_changed
    assert wrong_plan.continuation_evidence_id == plan.continuation_evidence_id
    before_wrong_plan = _snapshot(case.public_data)
    with pytest.raises(ContinuationIdentityError) as raised:
        authenticate_plan_continuation(
            case.evidence, case.diagnostics_root, wrong_plan, session
        )
    assert str(raised.value) == "verification plan differs from continuation"
    _assert_snapshot_unchanged(case.public_data, before_wrong_plan)
    restored_session = DiagnosticStore(
        case.diagnostics_root, case.evidence
    ).load_durable(proof.diagnostic_session_id)
    assert plan in restored_session.verification_plans

    reuse_request = ContinuationRequest.from_value(
        {
            "schema": CONTINUATION_REQUEST_SCHEMA,
            "kind": "reuse",
            # This is the genuine archived P3 evidence, deliberately supplied
            # to the bind-only preparer as the wrong public request kind.
            "continuationEvidenceId": proof.failed_before_evidence_id,
        }
    )
    before = _snapshot(case.public_data)
    with pytest.raises(ContinuationValidationError) as raised:
        _prepare(
            case.evidence,
            case.diagnostics_root,
            case.association,
            reuse_request,
            session_id=identity.session_id,
        )
    assert str(raised.value) == "a bind request is required"
    assert before == baseline
    _assert_snapshot_unchanged(case.public_data, before)

    before = _snapshot(case.public_data)
    with pytest.raises(ContinuationIdentityError) as raised:
        _prepare(
            case.evidence,
            case.diagnostics_root,
            case.association,
            request,
            session_id=case.association.after.manifest.identity.session_id,
        )
    assert str(raised.value) == "continuation caller session differs"
    _assert_snapshot_unchanged(case.public_data, before)

    prepared = _prepare(
        case.evidence,
        case.diagnostics_root,
        case.association,
        request,
        session_id=case.association.before.manifest.identity.session_id,
    )
    (
        prepared_proof,
        _predecessor,
        _predecessor_envelope,
        before_run,
        after_run,
        _diagnostic,
    ) = prepared
    assert prepared_proof == proof
    assert before_run.manifest.identity == case.association.before.manifest.identity
    assert after_run.manifest.identity == case.association.after.manifest.identity
    _assert_snapshot_unchanged(case.public_data, baseline)
    restored = _assert_restored_case(case)
    assert restored.envelope.evidence_id == case.association.envelope.evidence_id
    _assert_snapshot_unchanged(case.public_data, baseline)
    assert _snapshot(case.source_public_data) == case.source_snapshot


def test_archived_continuation_public_root_refusal_restores_authentication_and_reference(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = _snapshot(case.public_data)
    proof = case.association.proof
    genuine_wrong_manifest = proof.failed_before_evidence_id

    before_wrong_continuation = _snapshot(case.public_data)
    with pytest.raises(ContinuationValidationError) as raised:
        authenticate_continuation(
            case.evidence,
            case.diagnostics_root,
            proof.failed_before_evidence_id,
        )
    assert str(raised.value) == "continuation envelope differs"
    _assert_snapshot_unchanged(case.public_data, before_wrong_continuation)

    diagnostic_root_id = (
        f"{proof.diagnostic_session_id}.{proof.diagnostic_revision:08d}"
    )
    diagnostic_root_path = _public_root_path(
        case.evidence, "diagnostic-session", diagnostic_root_id
    )
    diagnostic_root = get_root(case.evidence, "diagnostic-session", diagnostic_root_id)
    assert diagnostic_root.manifest_id == proof.diagnostic_evidence_id
    original_diagnostic_root = _mutate_root(
        diagnostic_root_path,
        lambda value: value.__setitem__("manifest_id", genuine_wrong_manifest),
    )
    mutated = _snapshot(case.public_data)
    with pytest.raises(ContinuationValidationError) as raised:
        _authenticate(
            case.evidence, case.diagnostics_root, case.continuation_evidence_id
        )
    assert str(raised.value) == "Diagnostic event envelope differs"
    _assert_snapshot_unchanged(case.public_data, mutated)
    diagnostic_root_path.write_bytes(original_diagnostic_root)
    _assert_snapshot_unchanged(case.public_data, baseline)
    _assert_restored_case(case)

    analysis = _analysis_candidate(case.evidence, case.association)
    assert (
        validate_continuation_reference(case.evidence, case.association, analysis)
        is None
    )
    run_root_path, ref_root_path, _ = _monitor_root_paths(case.evidence, analysis)

    original_run_root = _mutate_root(
        run_root_path,
        lambda value: value.__setitem__("manifest_id", genuine_wrong_manifest),
    )
    mutated = _snapshot(case.public_data)
    with pytest.raises(ContinuationValidationError) as raised:
        validate_continuation_reference(case.evidence, case.association, analysis)
    assert str(raised.value) == "continuation Monitor reference root differs"
    _assert_snapshot_unchanged(case.public_data, mutated)
    run_root_path.write_bytes(original_run_root)
    _assert_snapshot_unchanged(case.public_data, baseline)
    assert (
        validate_continuation_reference(case.evidence, case.association, analysis)
        is None
    )

    original_ref_root = _mutate_root(
        ref_root_path,
        lambda value: value["metadata"].__setitem__("source_record_sha256", "0" * 64),
    )
    mutated = _snapshot(case.public_data)
    with pytest.raises(ContinuationValidationError) as raised:
        validate_continuation_reference(case.evidence, case.association, analysis)
    assert str(raised.value) == "continuation Monitor reference metadata differs"
    _assert_snapshot_unchanged(case.public_data, mutated)
    ref_root_path.write_bytes(original_ref_root)
    _assert_snapshot_unchanged(case.public_data, baseline)

    restored = _assert_restored_case(case)
    fresh_analysis = case.evidence.get_envelope(str(analysis.evidence_id))
    assert (
        validate_continuation_reference(case.evidence, restored, fresh_analysis) is None
    )
    _assert_snapshot_unchanged(case.public_data, baseline)
    assert _snapshot(case.source_public_data) == case.source_snapshot
