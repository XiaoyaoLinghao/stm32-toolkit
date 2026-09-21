from __future__ import annotations

import hashlib
from collections.abc import Mapping

import pytest
from stm32_toolkit.acceptance.finalization import PhysicalFinalizationAttempt
from stm32_toolkit.acceptance.recovery_workflows import show_acceptance_attempt
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.evidence.gc import RootRecord, get_root
from test_acceptance_finalization import (
    _begin,
    _checkpoint,
    _context,
    _journey_failure,
    _journey_public_root_path,
    _journey_root_id,
    _journey_success,
    _journey_wire,
    _persisted_snapshot,
    _proof,
)

pytest_plugins = ("test_acceptance_finalization",)


ATTEMPT_ROOT_TYPE = "acceptance-attempt"
CHECKPOINT_OPERATION = "acceptance.attempt.checkpoint"
BEGIN_OPERATION = "acceptance.attempt.begin"
SHOW_OPERATION = "acceptance.attempt.show"
EVIDENCE_FAILURE = "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
IDENTITY_FAILURE = "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


def _replace_rev0_binding(
    case: object,
    attempt_id: str,
    field: str,
    replacement: str,
) -> tuple[bytes, dict[str, object], str]:
    """Replace only rev0's public root with a constructor-valid binding variant."""

    evidence = case.evidence
    root_id = _journey_root_id(attempt_id, 0)
    root = get_root(evidence, ATTEMPT_ROOT_TYPE, root_id)
    root_path = _journey_public_root_path(evidence, ATTEMPT_ROOT_TYPE, root_id)
    original_root_bytes = root_path.read_bytes()
    original_envelope = evidence.get_envelope(root.manifest_id)
    persisted_attempt = PhysicalFinalizationAttempt.from_value(
        original_envelope.metadata["attempt"]
    )
    payload = persisted_attempt.to_dict()
    assert payload[field] != replacement
    payload[field] = replacement
    payload.pop("checkpointId")
    payload["checkpointId"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    candidate = PhysicalFinalizationAttempt.from_value(payload)
    assert candidate.to_dict() == payload

    replacement_envelope = EvidenceEnvelope(
        identity=original_envelope.identity,
        operation=original_envelope.operation,
        produced_at_utc=original_envelope.produced_at_utc,
        parents=original_envelope.parents,
        artifacts=original_envelope.artifacts,
        metadata={
            "attempt": candidate.to_dict(),
            "attempt_sha256": candidate.checkpoint_id,
        },
    )
    evidence.put_envelope(replacement_envelope)
    replacement_root = RootRecord(
        root_type=root.root_type,
        root_id=root.root_id,
        manifest_id=str(replacement_envelope.evidence_id),
        metadata={
            "attempt_sha256": candidate.checkpoint_id,
            "revision": candidate.revision,
            "workspace_id": candidate.workspace_id,
            "logical_project_id": candidate.logical_project_id,
        },
    )
    root_path.write_bytes(canonical_json_bytes(replacement_root.to_dict()))

    # Re-read through the public root and envelope APIs before exercising the
    # workflow.  This keeps the corruption inside the accepted decoder gates.
    reread_root = get_root(evidence, ATTEMPT_ROOT_TYPE, root_id)
    reread_envelope = evidence.get_envelope(reread_root.manifest_id)
    assert reread_root.to_dict() == replacement_root.to_dict()
    assert reread_envelope.to_dict() == replacement_envelope.to_dict()
    return original_root_bytes, persisted_attempt.to_dict(), root_id


def _run_route(case: object, attempt_id: str, proof: object, route: str) -> object:
    if route == "show":
        return show_acceptance_attempt(_context(case), attempt_id=attempt_id)
    if route == "begin":
        return _begin(case, attempt_id)
    if route == "checkpoint":
        return _checkpoint(case, attempt_id, proof)
    raise AssertionError(f"unsupported finalization route: {route}")


def test_finalization_binding_public_control(persisted_case: object) -> None:
    """The authenticated public begin/show/checkpoint path remains writable."""

    attempt_id = "00000000-0000-4000-8000-000000000701"
    started_wire = _journey_wire(_begin(persisted_case, attempt_id))
    started_data = started_wire.get("data")
    assert isinstance(started_data, Mapping), started_wire
    started_attempt = started_data.get("attempt")
    assert isinstance(started_attempt, Mapping), started_wire
    started_attempt_wire = dict(started_attempt)
    _journey_success(started_wire, BEGIN_OPERATION, started_data)
    proof = _proof(persisted_case, started_attempt_wire)

    before_show = _persisted_snapshot(persisted_case)
    show_wire = _journey_wire(
        show_acceptance_attempt(_context(persisted_case), attempt_id=attempt_id)
    )
    _journey_success(
        show_wire,
        SHOW_OPERATION,
        {"authoritative": True, "attempt": started_attempt_wire},
    )
    assert _persisted_snapshot(persisted_case) == before_show

    checkpoint_wire = _journey_wire(_checkpoint(persisted_case, attempt_id, proof))
    checkpoint_data = checkpoint_wire.get("data")
    assert isinstance(checkpoint_data, Mapping), checkpoint_wire
    completed_attempt = checkpoint_data.get("attempt")
    assert isinstance(completed_attempt, Mapping), checkpoint_wire
    _journey_success(checkpoint_wire, CHECKPOINT_OPERATION, checkpoint_data)
    completed_attempt_wire = dict(completed_attempt)
    assert completed_attempt_wire["revision"] == 1
    assert completed_attempt_wire["status"] == "COMPLETED"
    assert (
        completed_attempt_wire["continuationEvidenceId"]
        == proof.continuation_evidence_id
    )
    assert (
        completed_attempt_wire["fixedAfterTestRunId"] == proof.fixed_after_test_run_id
    )
    assert (
        completed_attempt_wire["fixedAfterEvidenceId"] == proof.fixed_after_evidence_id
    )

    root1 = get_root(
        persisted_case.evidence,
        ATTEMPT_ROOT_TYPE,
        _journey_root_id(attempt_id, 1),
    )
    envelope1 = persisted_case.evidence.get_envelope(root1.manifest_id)
    persisted_attempt = PhysicalFinalizationAttempt.from_value(
        envelope1.metadata["attempt"]
    )
    assert completed_attempt_wire == persisted_attempt.to_dict()


@pytest.mark.parametrize(
    ("case_name", "field", "proof_field", "expected_code"),
    (
        pytest.param(
            "continuation-evidence",
            "continuationEvidenceId",
            "failed_before_evidence_id",
            EVIDENCE_FAILURE,
            id="continuation-evidence-parent-binding",
        ),
        pytest.param(
            "fixed-after-run",
            "fixedAfterTestRunId",
            "failed_before_test_run_id",
            IDENTITY_FAILURE,
            id="fixed-after-test-run-identity",
        ),
        pytest.param(
            "fixed-after-evidence",
            "fixedAfterEvidenceId",
            "failed_before_evidence_id",
            IDENTITY_FAILURE,
            id="fixed-after-evidence-identity",
        ),
    ),
)
def test_finalization_binding_corruption_refuses_and_restores(
    persisted_case: object,
    case_name: str,
    field: str,
    proof_field: str,
    expected_code: str,
) -> None:
    """Stored binding corruption is read-only rejected, then publicly recoverable."""

    attempt_id = "00000000-0000-4000-8000-000000000702"
    started_wire = _journey_wire(_begin(persisted_case, attempt_id))
    started_data = started_wire.get("data")
    assert isinstance(started_data, Mapping), started_wire
    started_attempt = started_data.get("attempt")
    assert isinstance(started_attempt, Mapping), started_wire
    original_attempt_wire = dict(started_attempt)
    _journey_success(started_wire, BEGIN_OPERATION, started_data)
    proof = _proof(persisted_case, original_attempt_wire)
    replacement = getattr(proof, proof_field)
    assert isinstance(replacement, str)
    if field != "fixedAfterTestRunId":
        assert (
            persisted_case.evidence.get_envelope(replacement).evidence_id == replacement
        )

    original_root_bytes, persisted_attempt_wire, root_id = _replace_rev0_binding(
        persisted_case,
        attempt_id,
        field,
        replacement,
    )
    assert persisted_attempt_wire == original_attempt_wire
    corrupted_before_routes = _persisted_snapshot(persisted_case)

    for route, operation in (
        ("show", SHOW_OPERATION),
        ("begin", BEGIN_OPERATION),
        ("checkpoint", CHECKPOINT_OPERATION),
    ):
        before_route = _persisted_snapshot(persisted_case)
        result = _run_route(persisted_case, attempt_id, proof, route)
        failure_wire = _journey_wire(result)
        _journey_failure(
            failure_wire,
            operation,
            expected_code,
            context=f"{case_name}-{route}",
        )
        assert _persisted_snapshot(persisted_case) == before_route
        assert before_route == corrupted_before_routes
        assert not _journey_public_root_path(
            persisted_case.evidence,
            ATTEMPT_ROOT_TYPE,
            _journey_root_id(attempt_id, 1),
        ).exists()
        assert not _journey_public_root_path(
            persisted_case.evidence,
            ATTEMPT_ROOT_TYPE,
            _journey_root_id(attempt_id, 2),
        ).exists()

    root0_path = _journey_public_root_path(
        persisted_case.evidence,
        ATTEMPT_ROOT_TYPE,
        root_id,
    )
    root0_path.write_bytes(original_root_bytes)
    restored_before_read = _persisted_snapshot(persisted_case)
    restored_show_wire = _journey_wire(
        show_acceptance_attempt(_context(persisted_case), attempt_id=attempt_id)
    )
    _journey_success(
        restored_show_wire,
        SHOW_OPERATION,
        {"authoritative": True, "attempt": original_attempt_wire},
    )
    assert _persisted_snapshot(persisted_case) == restored_before_read

    checkpoint_wire = _journey_wire(_checkpoint(persisted_case, attempt_id, proof))
    checkpoint_data = checkpoint_wire.get("data")
    assert isinstance(checkpoint_data, Mapping), checkpoint_wire
    completed_attempt = checkpoint_data.get("attempt")
    assert isinstance(completed_attempt, Mapping), checkpoint_wire
    _journey_success(checkpoint_wire, CHECKPOINT_OPERATION, checkpoint_data)
    completed_attempt_wire = dict(completed_attempt)
    assert completed_attempt_wire["revision"] == 1
    assert completed_attempt_wire["status"] == "COMPLETED"
    assert (
        completed_attempt_wire["continuationEvidenceId"]
        == original_attempt_wire["continuationEvidenceId"]
    )
    assert (
        completed_attempt_wire["fixedAfterTestRunId"] == proof.fixed_after_test_run_id
    )
    assert (
        completed_attempt_wire["fixedAfterEvidenceId"] == proof.fixed_after_evidence_id
    )
    assert _journey_public_root_path(
        persisted_case.evidence,
        ATTEMPT_ROOT_TYPE,
        _journey_root_id(attempt_id, 1),
    ).exists()
    assert not _journey_public_root_path(
        persisted_case.evidence,
        ATTEMPT_ROOT_TYPE,
        _journey_root_id(attempt_id, 2),
    ).exists()
