"""Public Acceptance lifecycle checks over the genuine VS10-A archive.

The archived graph is historical input.  These tests copy it into a run-owned
data root, keep the original project read-only, and create only new public
Acceptance bookkeeping revisions through the production API.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import test_risk_acceptance_archive_readers as reader_fixture
import test_risk_continuation_archive_reader as archive_fixture
from stm32_toolkit.acceptance.continuation import (
    CONTINUATION_REQUEST_SCHEMA,
)
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import get_root

_OP_BEGIN = "acceptance.attempt.begin"
_OP_CHECKPOINT = "acceptance.attempt.checkpoint"
_OP_RESUME = "acceptance.attempt.resume"
_MESSAGES = {
    "ACCEPTANCE_ATTEMPT_CONFLICT": "Acceptance attempt content conflicts with an immutable revision.",
    "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID": "Acceptance attempt public output is invalid.",
    "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT": "Acceptance attempt revision conflicts with the current chain.",
    "ACCEPTANCE_ATTEMPT_STAGE_INVALID": "Acceptance attempt stage is invalid.",
    "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH": "Acceptance attempt identity does not match.",
}


TreeDigest = tuple[tuple[str, int, str], ...]


@dataclass(frozen=True)
class LifecycleCase:
    reader: reader_fixture.ReaderCase
    association: object
    request: dict[str, object]
    bind_request: dict[str, object]
    proof: object
    fix_verification_id: str
    project_digest: TreeDigest


def _tree_digest(root: Path) -> TreeDigest:
    return tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _load_case(tmp_path: Path) -> LifecycleCase:
    reader = reader_fixture._load_case(tmp_path)
    diagnostics_root = reader.evidence.root.parent / "diagnostics"
    association = archive_fixture._authenticate(
        reader.evidence,
        diagnostics_root,
        archive_fixture._CONTINUATION_EVIDENCE_ID,
    )
    proof = association.proof
    session = DiagnosticStore(diagnostics_root, reader.evidence).load_durable(
        proof.diagnostic_session_id
    )
    verifications = [
        verification
        for verification in session.fix_verifications
        if (
            verification.status == "PASSED"
            and verification.reason_code == "VERIFICATION_PASSED"
            and verification.diagnostic_session_id == proof.diagnostic_session_id
            and verification.fixed_after_run_id == proof.fixed_after_test_run_id
            and verification.fixed_after_evidence_id == proof.fixed_after_evidence_id
        )
    ]
    assert len(verifications) == 1
    request = {
        "schema": CONTINUATION_REQUEST_SCHEMA,
        "kind": "reuse",
        "continuationEvidenceId": archive_fixture._CONTINUATION_EVIDENCE_ID,
    }
    bind_request = {
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
    assert reader.context.session_id == association.before.manifest.identity.session_id
    assert reader.evidence.root.parent.name == archive_fixture._ARCHIVE_PROJECT_KEY
    return LifecycleCase(
        reader=reader,
        association=association,
        request=request,
        bind_request=bind_request,
        proof=proof,
        fix_verification_id=verifications[0].fix_verification_id,
        project_digest=_tree_digest(reader.project_root),
    )


def _wire(result: object) -> dict[str, object]:
    wire = getattr(result, "to_dict", lambda: None)()
    assert isinstance(wire, dict)
    assert wire.get("protocol") == "stm32-toolkit/1"
    return wire


def _success(result: object, operation: str) -> dict[str, object]:
    wire = _wire(result)
    assert wire["ok"] is True
    assert wire["operation"] == operation
    assert wire["code"] == "OK"
    assert wire["message"] == ""
    assert wire["details"] == {}
    data = wire["data"]
    assert isinstance(data, dict)
    return data


def _failure(result: object, operation: str, code: str) -> None:
    assert code in _MESSAGES
    assert _wire(result) == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": _MESSAGES[code],
        "data": None,
        "details": {},
    }


def _snapshot(case: LifecycleCase) -> archive_fixture.TreeSnapshot:
    return archive_fixture._snapshot(case.reader.public_data)


def _assert_no_write(case: LifecycleCase, before: archive_fixture.TreeSnapshot) -> None:
    assert _snapshot(case) == before


def _expected_attempt_public_paths(
    case: LifecycleCase,
    *,
    attempt_id: str,
    revision: int,
) -> set[str]:
    """Return the exact public files one attempt revision may publish."""

    root_id = f"{attempt_id}.{revision:08d}"
    root = get_root(case.reader.evidence, "acceptance-attempt", root_id)
    evidence_prefix = case.reader.evidence.root.relative_to(
        case.reader.public_data
    ).as_posix()
    root_path = archive_fixture._public_root_path(
        case.reader.evidence, "acceptance-attempt", root_id
    ).relative_to(case.reader.public_data)
    envelope = case.reader.evidence.get_envelope(str(root.manifest_id))
    expected = {
        root_path.as_posix(),
        f"{evidence_prefix}/manifests/{root.manifest_id}.json",
    }
    expected.update(
        f"{evidence_prefix}/{artifact.relative_path}" for artifact in envelope.artifacts
    )
    return expected


def _assert_publication_delta(
    case: LifecycleCase,
    before: archive_fixture.TreeSnapshot,
    after: archive_fixture.TreeSnapshot,
    *,
    attempt_id: str,
    revision: int,
) -> None:
    """Require one revision's exact root/envelope delta and no other writes."""

    before_map = dict(before)
    after_map = dict(after)
    assert set(before_map).issubset(after_map)
    assert all(after_map[path] == raw for path, raw in before_map.items())
    assert set(after_map) - set(before_map) == _expected_attempt_public_paths(
        case, attempt_id=attempt_id, revision=revision
    )


def _assert_original_inputs(case: LifecycleCase) -> None:
    reader_fixture._assert_project_and_archive_unchanged(case.reader)
    assert _tree_digest(case.reader.project_root) == case.project_digest


def _begin(case: LifecycleCase, attempt_id: str, request: object):
    return begin_acceptance_attempt(
        case.reader.context,
        attempt_id=attempt_id,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        continuation=request,
    )


def _checkpoint(
    case: LifecycleCase,
    attempt_id: str,
    *,
    expected_revision: int,
    stage: str = "target-fix-verified",
    test_run_id: str | None = None,
    diagnostic_session_id: str | None = None,
    fix_verification_id: str | None = None,
):
    return checkpoint_acceptance_attempt(
        case.reader.context,
        attempt_id=attempt_id,
        expected_revision=expected_revision,
        stage=stage,
        test_run_id=test_run_id,
        diagnostic_session_id=diagnostic_session_id,
        fix_verification_id=fix_verification_id,
    )


def _assert_attempt(
    attempt: Mapping[str, object],
    *,
    attempt_id: str,
    revision: int,
    status: str,
    stage: str,
    case: LifecycleCase,
) -> None:
    assert attempt["schema"] == "stm32-acceptance-attempt/3"
    assert attempt["attemptId"] == attempt_id
    assert attempt["revision"] == revision
    assert attempt["status"] == status
    assert attempt["stage"] == stage
    assert attempt["scenarioId"] == PHYSICAL_SCENARIO_ID
    assert attempt["scenarioVersion"] == PHYSICAL_SCENARIO_VERSION
    assert attempt["workspaceId"] == case.association.envelope.identity.workspace_id
    assert attempt["logicalProjectId"] == case.association.envelope.identity.project_id
    assert attempt["sessionId"] == case.reader.context.session_id
    assert attempt["projectOrigin"] == "keil"
    assert attempt["executionSource"] == "physical"
    assert attempt["physicalTransportEvidence"] is True
    assert (
        attempt["continuationEvidenceId"] == archive_fixture._CONTINUATION_EVIDENCE_ID
    )
    assert attempt["fixedAfterTestRunId"] == case.proof.fixed_after_test_run_id
    assert attempt["fixedAfterEvidenceId"] == case.proof.fixed_after_evidence_id
    assert isinstance(attempt["openedAtUtc"], str)
    assert isinstance(attempt["updatedAtUtc"], str)
    assert isinstance(attempt["deadlineAtUtc"], str)
    opened = datetime.fromisoformat(attempt["openedAtUtc"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(attempt["updatedAtUtc"].replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(attempt["deadlineAtUtc"].replace("Z", "+00:00"))
    assert updated >= opened
    assert deadline - opened == timedelta(seconds=900)
    if revision == 0:
        assert attempt["fixVerificationId"] is None
    else:
        assert attempt["fixVerificationId"] == case.fix_verification_id


def test_archived_acceptance_begin_checkpoint_retry_and_completed_reader(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = _snapshot(case)
    attempt_id = str(uuid4())

    first_data = _success(_begin(case, attempt_id, case.request), _OP_BEGIN)
    first = first_data["attempt"]
    assert isinstance(first, dict)
    _assert_attempt(
        first,
        attempt_id=attempt_id,
        revision=0,
        status="IN_PROGRESS",
        stage="verification-pending",
        case=case,
    )
    after_begin = _snapshot(case)
    _assert_publication_delta(
        case,
        baseline,
        after_begin,
        attempt_id=attempt_id,
        revision=0,
    )

    retry_before = _snapshot(case)
    retry_data = _success(_begin(case, attempt_id, case.request), _OP_BEGIN)
    assert retry_data["attempt"] == first
    _assert_no_write(case, retry_before)

    bind_before = _snapshot(case)
    bind_data = _success(_begin(case, attempt_id, case.bind_request), _OP_BEGIN)
    assert bind_data["attempt"] == first
    _assert_no_write(case, bind_before)

    completed_data = _success(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=case.fix_verification_id,
        ),
        _OP_CHECKPOINT,
    )
    completed = completed_data["attempt"]
    assert isinstance(completed, dict)
    _assert_attempt(
        completed,
        attempt_id=attempt_id,
        revision=1,
        status="COMPLETED",
        stage="target-fix-verified",
        case=case,
    )
    assert completed["previousCheckpointId"] == first["checkpointId"]
    assert completed["updatedAtUtc"] >= first["updatedAtUtc"]
    after_complete = _snapshot(case)
    _assert_publication_delta(
        case,
        after_begin,
        after_complete,
        attempt_id=attempt_id,
        revision=1,
    )

    checkpoint_retry_before = _snapshot(case)
    checkpoint_retry = _success(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=case.fix_verification_id,
        ),
        _OP_CHECKPOINT,
    )
    assert checkpoint_retry["attempt"] == completed
    _assert_no_write(case, checkpoint_retry_before)

    begin_completed_before = _snapshot(case)
    begin_completed = _success(_begin(case, attempt_id, case.request), _OP_BEGIN)
    assert begin_completed["attempt"] == completed
    _assert_no_write(case, begin_completed_before)

    reader_before = _snapshot(case)
    resumed = _success(
        resume_acceptance_attempt(case.reader.context, attempt_id=attempt_id),
        _OP_RESUME,
    )
    assert resumed["authoritative"] is True
    assert resumed["attempt"] == completed
    assert resumed["nextStage"] is None
    assert resumed["authorizationRequired"] is False
    assert resumed["actionDigest"] is None
    assert resumed["timedOut"] is False
    _assert_no_write(case, reader_before)
    _assert_original_inputs(case)


def test_archived_acceptance_refusals_preserve_data_then_complete_and_reject_completed_retry(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    attempt_id = str(uuid4())
    baseline = _snapshot(case)
    first_data = _success(_begin(case, attempt_id, case.request), _OP_BEGIN)
    first = first_data["attempt"]
    assert isinstance(first, dict)
    _assert_attempt(
        first,
        attempt_id=attempt_id,
        revision=0,
        status="IN_PROGRESS",
        stage="verification-pending",
        case=case,
    )
    after_begin = _snapshot(case)
    _assert_publication_delta(
        case,
        baseline,
        after_begin,
        attempt_id=attempt_id,
        revision=0,
    )

    different_hash = "0" * 64
    if different_hash == case.proof.fixed_after_evidence_id:
        different_hash = "1" * 64
    conflict_request = {
        "schema": CONTINUATION_REQUEST_SCHEMA,
        "kind": "reuse",
        "continuationEvidenceId": different_hash,
    }
    before = _snapshot(case)
    _failure(
        _begin(case, attempt_id, conflict_request),
        _OP_BEGIN,
        "ACCEPTANCE_ATTEMPT_CONFLICT",
    )
    _assert_no_write(case, before)

    wrong_fix = "0" * 64
    if wrong_fix == case.fix_verification_id:
        wrong_fix = "1" * 64
    before = _snapshot(case)
    _failure(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=wrong_fix,
        ),
        _OP_CHECKPOINT,
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
    )
    _assert_no_write(case, before)

    before = _snapshot(case)
    _failure(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=1,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=case.fix_verification_id,
        ),
        _OP_CHECKPOINT,
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT",
    )
    _assert_no_write(case, before)

    before = _snapshot(case)
    _failure(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            stage="firmware-built-before",
        ),
        _OP_CHECKPOINT,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
    )
    _assert_no_write(case, before)

    before = _snapshot(case)
    _failure(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id="target-v2-wrong-run",
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=case.fix_verification_id,
        ),
        _OP_CHECKPOINT,
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
    )
    _assert_no_write(case, before)

    completed_data = _success(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=case.fix_verification_id,
        ),
        _OP_CHECKPOINT,
    )
    completed = completed_data["attempt"]
    assert isinstance(completed, dict)
    _assert_attempt(
        completed,
        attempt_id=attempt_id,
        revision=1,
        status="COMPLETED",
        stage="target-fix-verified",
        case=case,
    )
    assert completed["updatedAtUtc"] >= first["updatedAtUtc"]
    after_complete = _snapshot(case)
    _assert_publication_delta(
        case,
        after_begin,
        after_complete,
        attempt_id=attempt_id,
        revision=1,
    )

    before = _snapshot(case)
    _failure(
        _checkpoint(
            case,
            attempt_id,
            expected_revision=0,
            test_run_id=case.proof.fixed_after_test_run_id,
            diagnostic_session_id=case.proof.diagnostic_session_id,
            fix_verification_id=wrong_fix,
        ),
        _OP_CHECKPOINT,
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT",
    )
    _assert_no_write(case, before)
    _assert_original_inputs(case)
