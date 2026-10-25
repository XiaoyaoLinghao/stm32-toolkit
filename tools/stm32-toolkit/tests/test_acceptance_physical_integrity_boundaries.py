"""Offline authority boundaries for persisted physical acceptance recovery.

Every physical-marked record built here is a synthetic offline fixture.  The
real project model, EvidenceStore, TestRun publication, Diagnostic store,
snapshot and chain validators remain the authority; only the existing
fresh-firmware-facts producer seam is used by the shared fixture.  These cases
record what the public readers, checkpoints and source authorization actually
refuse, including where an earlier real guard makes a later one unreachable.

Two design expectations are not reachable with real model-valid inputs and are
recorded as the actual public contract instead:

* A no-op source intent (after state equals before state) is rejected by the
  closed ``SourceChangeIntent`` model as typed input-invalid before either
  snapshot comparison runs; ``beforeSha256 == afterSha256`` is structurally
  invalid, so the adapter's later no-op clause cannot be reached.
* The stored-output continuity check compares a revision against its
  predecessor's non-null outputs.  ``projectModelDigest`` first appears at
  revision 1, and a latest revision has no successor to compare it against, so
  the guard is exercised at revision 2 (whose predecessor publishes it) rather
  than by mutating a latest revision 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

import test_acceptance_physical_recovery as physical_fixture
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery import (
    SourceChangeIntent,
    physical_acceptance_recovery_policy_for_schema,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    authorize_acceptance_source_change,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.evidence import (
    EvidenceEnvelope,
    EvidenceIdentity,
    canonical_json_bytes,
    get_root,
)
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run


ATTEMPT_ID = physical_fixture.ATTEMPT_ID
PROJECT_ID = physical_fixture.PROJECT_ID
FAILED_RUN = physical_fixture.PHYSICAL_FAILED_RUN
FIXED_RUN = physical_fixture.PHYSICAL_FIXED_RUN
AFTER_SOURCE = b"int main(void) { return 1; }\n"
UNKNOWN_RUN = "target-v2-missing-integrity-t10"
MISMATCH_BUILD_RUN = "target-v2-mismatch-build-t10"
MISMATCH_SNAPSHOT_RUN = "target-v2-mismatch-snapshot-t10"
FIXED_SEED_RUN = "seed-physical-integrity-fixed"

MESSAGE_INPUT_INVALID = "Acceptance attempt input is invalid."
MESSAGE_REVISION_CONFLICT = "Acceptance attempt revision conflicts with the current chain."
MESSAGE_OUTPUT_INVALID = "Acceptance attempt public output is invalid."
MESSAGE_IDENTITY_MISMATCH = "Acceptance attempt identity does not match."
MESSAGE_INTEGRITY = "Acceptance attempt evidence failed integrity validation."

_ENTRY_OPERATIONS = {
    "show": "acceptance.attempt.show",
    "resume": "acceptance.attempt.resume",
    "checkpoint": "acceptance.attempt.checkpoint",
    "authorize": "acceptance.attempt.authorize-source-change",
}


def _ok(result: object) -> Mapping[str, object]:
    return physical_fixture._ok(result)


def _assert_failure(result: object, operation: str, code: str, message: str) -> None:
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": message,
        "data": None,
        "details": {},
    }


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _evidence(context: object) -> EvidenceStore:
    workspace = WorkspacePaths.from_roots(
        context.data_root,
        context.project_root,
        UUID(PROJECT_ID),
        context.session_id,
    )
    return EvidenceStore(workspace.workspace_root / "evidence")


def _attempt_root_path(evidence: EvidenceStore, revision: int) -> Path:
    return recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(ATTEMPT_ID, revision)
    )


def _root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    name = hashlib.sha256(
        canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    ).hexdigest() + ".json"
    return evidence.root / "roots" / root_type / name


def _attempt_document(
    evidence: EvidenceStore, revision: int
) -> tuple[RootRecord, EvidenceEnvelope, dict[str, object]]:
    root = get_root(
        evidence, "acceptance-attempt", recovery_workflows._root_id(ATTEMPT_ID, revision)
    )
    envelope = evidence.get_envelope(root.manifest_id)
    raw = json.loads(canonical_json_bytes(envelope.metadata["attempt"]).decode("utf-8"))
    assert isinstance(raw, dict)
    return root, envelope, raw


def _recheckpoint(value: Mapping[str, object]) -> dict[str, object]:
    candidate = dict(value)
    candidate.pop("checkpointId", None)
    candidate["checkpointId"] = hashlib.sha256(
        canonical_json_bytes(candidate)
    ).hexdigest()
    return candidate


def _replace_attempt_root(
    evidence: EvidenceStore, revision: int, wire: Mapping[str, object]
) -> None:
    """Publish model-valid replacement attempt bytes through the real store."""
    attempt = recovery_workflows.PhysicalAcceptanceAttempt.from_value(dict(wire))
    root, envelope, _ = _attempt_document(evidence, revision)
    changed = EvidenceEnvelope(
        identity=envelope.identity,
        operation=envelope.operation,
        produced_at_utc=attempt.updated_at_utc,
        parents=envelope.parents,
        artifacts=envelope.artifacts,
        metadata={
            "attempt": attempt.to_dict(),
            "attempt_sha256": attempt.checkpoint_id,
        },
    )
    evidence.put_envelope(changed)
    metadata = dict(root.metadata)
    metadata["attempt_sha256"] = attempt.checkpoint_id
    replacement = RootRecord(
        root_type=root.root_type,
        root_id=root.root_id,
        manifest_id=str(changed.evidence_id),
        metadata=metadata,
    )
    _root_path(evidence, root.root_type, root.root_id).write_bytes(
        canonical_json_bytes(replacement.to_dict())
    )


def _replace_attempt_envelope_metadata(
    evidence: EvidenceStore, revision: int, metadata: Mapping[str, object]
) -> None:
    """Replace one attempt envelope payload without reinterpreting the attempt."""
    root, envelope, _ = _attempt_document(evidence, revision)
    changed = EvidenceEnvelope(
        identity=envelope.identity,
        operation=envelope.operation,
        produced_at_utc=envelope.produced_at_utc,
        parents=envelope.parents,
        artifacts=envelope.artifacts,
        metadata=metadata,
    )
    evidence.put_envelope(changed)
    replacement = RootRecord(
        root_type=root.root_type,
        root_id=root.root_id,
        manifest_id=str(changed.evidence_id),
        metadata=dict(root.metadata),
    )
    _root_path(evidence, root.root_type, root.root_id).write_bytes(
        canonical_json_bytes(replacement.to_dict())
    )


def _plus_microseconds(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return (parsed + timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _policy_deadline(schema: object, updated_at_utc: str, stage: str) -> str:
    seconds = physical_acceptance_recovery_policy_for_schema(
        schema
    ).stage_timeout_seconds[stage]
    updated = datetime.strptime(updated_at_utc, "%Y-%m-%dT%H:%M:%S.%fZ")
    return (updated + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _different_hash(value: object) -> str:
    candidate = "0" * 64
    return "1" * 64 if value == candidate else candidate


def _source_path(context: object) -> Path:
    return context.project_root / "App" / "main.c"


def _before_snapshot(context: object) -> str:
    return snapshot_project_inputs(load_project_model(context.project_root)).sha256


def _after_snapshot(context: object) -> str:
    source_path = _source_path(context)
    before_source = source_path.read_bytes()
    source_path.write_bytes(AFTER_SOURCE)
    try:
        return snapshot_project_inputs(
            load_project_model(context.project_root)
        ).sha256
    finally:
        source_path.write_bytes(before_source)


def _identity(
    context: object,
    *,
    build_id: str,
    elf_sha256: str,
    input_snapshot_sha256: str,
    git_commit: str,
) -> EvidenceIdentity:
    workspace = WorkspacePaths.from_roots(
        context.data_root,
        context.project_root,
        UUID(PROJECT_ID),
        context.session_id,
    )
    model = load_project_model(context.project_root)
    return EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=PROJECT_ID,
        session_id=context.session_id,
        build_id=build_id,
        elf_sha256=elf_sha256,
        target_device=model.target.device,
        input_snapshot_sha256=input_snapshot_sha256,
        git_commit=git_commit,
        git_dirty=False,
    )


def _publish_passed_physical_run(context: object, tmp_path: Path) -> object:
    """Publish a genuinely passed synthetic physical TestRun graph."""
    testing = TestingWorkflowContext(
        context.project_root, context.data_root, context.session_id
    )
    descriptor, stream = physical_fixture.vs08a_fixtures._canonical_replay_inputs(
        tmp_path, "fixed-after", FIXED_SEED_RUN
    )
    physical_fixture._ok(
        target_replay_run(testing, FIXED_SEED_RUN, descriptor, stream)
    )
    identity = _identity(
        context,
        build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_AFTER_ELF,
        input_snapshot_sha256=_after_snapshot(context),
        git_commit="c" * 40,
    )
    return physical_fixture._publish_physical_from_seed(
        tmp_path,
        context.project_root,
        context.data_root,
        context.session_id,
        FIXED_SEED_RUN,
        FIXED_RUN,
        identity,
    )


def _publish_failed_physical_run(
    context: object, tmp_path: Path, run_id: str, identity: EvidenceIdentity
) -> object:
    return physical_fixture._publish_physical_from_seed(
        tmp_path,
        context.project_root,
        context.data_root,
        context.session_id,
        "seed-physical-boundary",
        run_id,
        identity,
    )


def _show_head(context: object, revision: int) -> Mapping[str, object]:
    shown = _ok(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    attempt = shown["attempt"]
    assert isinstance(attempt, Mapping)
    assert attempt["revision"] == revision, attempt
    resumed = _ok(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    assert resumed["attempt"] == attempt
    return attempt


def _invoke_entry(context: object, entry: str) -> object:
    if entry == "show":
        return show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    if entry == "resume":
        return resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    if entry == "checkpoint":
        return checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=0,
            stage="project-materialized",
        )
    return authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest="a" * 64,
        authorized=True,
    )


# ---------------------------------------------------------------------------
# Group E: untrusted revision-0 envelope attempt metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", tuple(_ENTRY_OPERATIONS))
def test_non_mapping_rev0_attempt_metadata_refused_by_every_public_entry(
    entry: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=0
        )
    )
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 0)
    original_root = root_path.read_bytes()
    original_wire = _attempt_document(evidence, 0)[2]
    try:
        _replace_attempt_envelope_metadata(
            evidence,
            0,
            {
                "attempt": [],
                "attempt_sha256": str(original_wire["checkpointId"]),
            },
        )
        # The snapshot is taken after the intentional untrusted envelope was
        # added, so a byte-identical result proves the reader added nothing.
        before = _tree_bytes(context.data_root)
        _assert_failure(
            _invoke_entry(context, entry),
            _ENTRY_OPERATIONS[entry],
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 0) == original_wire


@pytest.mark.parametrize("entry", tuple(_ENTRY_OPERATIONS))
def test_non_string_rev0_attempt_schema_refused_by_every_public_entry(
    entry: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=0
        )
    )
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 0)
    original_root = root_path.read_bytes()
    original_wire = _attempt_document(evidence, 0)[2]
    try:
        _replace_attempt_envelope_metadata(
            evidence,
            0,
            {
                "attempt": {"schema": 7},
                "attempt_sha256": str(original_wire["checkpointId"]),
            },
        )
        before = _tree_bytes(context.data_root)
        _assert_failure(
            _invoke_entry(context, entry),
            _ENTRY_OPERATIONS[entry],
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 0) == original_wire


# ---------------------------------------------------------------------------
# Group A: target-failure-observed TestRun binding (revision 2 -> 3)
# ---------------------------------------------------------------------------


def test_missing_native_target_run_is_evidence_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=UNKNOWN_RUN,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        MESSAGE_INTEGRITY,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 3).exists()
    _show_head(context, 2)


def test_replay_operation_run_is_public_output_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    before = _tree_bytes(context.data_root)
    # The replay run reaches the physical-run envelope operation guard; the
    # later physical transport check is not claimed as proven here.
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id="seed-physical-boundary",
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
        MESSAGE_OUTPUT_INVALID,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 3).exists()
    _show_head(context, 2)


def test_passed_physical_run_is_output_invalid_for_failed_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    _publish_passed_physical_run(context, tmp_path)
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=FIXED_RUN,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
        MESSAGE_OUTPUT_INVALID,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 3).exists()
    _show_head(context, 2)


def test_failed_run_with_wrong_build_identity_is_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    before_snapshot = _before_snapshot(context)
    # Keep the ELF bytes, snapshot and Git state identical so only the build
    # identity differs; identical ELF bytes across build identities are
    # permitted, and the build guard is checked before the ELF guard.
    identity = _identity(
        context,
        build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        input_snapshot_sha256=before_snapshot,
        git_commit="b" * 40,
    )
    _publish_failed_physical_run(context, tmp_path, MISMATCH_BUILD_RUN, identity)
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=MISMATCH_BUILD_RUN,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        MESSAGE_IDENTITY_MISMATCH,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 3).exists()
    _show_head(context, 2)


def test_failed_run_with_wrong_input_snapshot_is_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    identity = _identity(
        context,
        build_id=physical_fixture.PHYSICAL_BEFORE_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        input_snapshot_sha256=_after_snapshot(context),
        git_commit="b" * 40,
    )
    _publish_failed_physical_run(context, tmp_path, MISMATCH_SNAPSHOT_RUN, identity)
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=MISMATCH_SNAPSHOT_RUN,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        MESSAGE_IDENTITY_MISMATCH,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 3).exists()
    _show_head(context, 2)


# ---------------------------------------------------------------------------
# Group B: diagnosis-completed source intent (revision 3 -> 4)
# ---------------------------------------------------------------------------


def _prepare_diagnosis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, str]:
    context, diagnostic, diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=3
        )
    )
    assert diagnostic is not None and diagnostic_id is not None
    return context, diagnostic_id


def _intent_for(
    before_sha256: str, after_sha256: str, after_size: int
) -> dict[str, object]:
    return {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "App/main.c",
                "beforeSha256": before_sha256,
                "afterSha256": after_sha256,
                "afterSize": after_size,
            }
        ],
    }


def test_diagnosis_wrong_before_source_digest_is_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, diagnostic_id = _prepare_diagnosis(tmp_path, monkeypatch)
    before = _tree_bytes(context.data_root)
    intent = _intent_for(
        "0" * 64,
        hashlib.sha256(AFTER_SOURCE).hexdigest(),
        len(AFTER_SOURCE),
    )
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=diagnostic_id,
        source_change_intent=intent,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
        MESSAGE_IDENTITY_MISMATCH,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 4).exists()
    _show_head(context, 3)


def test_noop_source_intent_is_refused_by_the_closed_input_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, diagnostic_id = _prepare_diagnosis(tmp_path, monkeypatch)
    source_path = _source_path(context)
    before_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    # A change whose after state equals its before state is rejected by the
    # closed SourceChangeIntent model, so the later snapshot-identity guard in
    # the adapter cannot be reached with a real model-valid intent.
    intent = _intent_for(
        before_sha256,
        before_sha256,
        len(source_path.read_bytes()),
    )
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=diagnostic_id,
        source_change_intent=intent,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
        MESSAGE_INPUT_INVALID,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 4).exists()
    _show_head(context, 3)


def test_diagnosis_after_source_already_changed_is_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, diagnostic_id = _prepare_diagnosis(tmp_path, monkeypatch)
    source_path = _source_path(context)
    original_source = source_path.read_bytes()
    source_path.write_bytes(AFTER_SOURCE)
    project_before = _tree_bytes(context.project_root)
    data_before = _tree_bytes(context.data_root)
    intent = _intent_for(
        hashlib.sha256(original_source).hexdigest(),
        hashlib.sha256(AFTER_SOURCE).hexdigest(),
        len(AFTER_SOURCE),
    )
    try:
        # The fresh before-build recheck compares the mutated working snapshot
        # with the revision-3 identity before any intent expansion happens.
        result = checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=3,
            stage="diagnosis-completed",
            diagnostic_session_id=diagnostic_id,
            source_change_intent=intent,
        )
        _assert_failure(
            result,
            "acceptance.attempt.checkpoint",
            "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
            MESSAGE_IDENTITY_MISMATCH,
        )
        assert _tree_bytes(context.data_root) == data_before
        assert _tree_bytes(context.project_root) == project_before
        assert not _attempt_root_path(_evidence(context), 4).exists()
    finally:
        source_path.write_bytes(original_source)
    _show_head(context, 3)


# ---------------------------------------------------------------------------
# Group C: stale checkpoint beyond one transition
# ---------------------------------------------------------------------------


def test_stale_checkpoint_two_transitions_behind_is_revision_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=4
        )
    )
    before = _tree_bytes(context.data_root)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-observed",
        test_run_id=FAILED_RUN,
    )
    _assert_failure(
        result,
        "acceptance.attempt.checkpoint",
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT",
        MESSAGE_REVISION_CONFLICT,
    )
    assert _tree_bytes(context.data_root) == before
    assert not _attempt_root_path(_evidence(context), 5).exists()
    _show_head(context, 4)


# ---------------------------------------------------------------------------
# Group D: model-valid persisted chain tampering
# ---------------------------------------------------------------------------


def test_rev0_opened_updated_mismatch_is_rejected_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=0
        )
    )
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 0)
    original_root = root_path.read_bytes()
    _, _, wire = _attempt_document(evidence, 0)
    original_wire = json.loads(json.dumps(wire))
    updated = _plus_microseconds(str(wire["openedAtUtc"]))
    wire["updatedAtUtc"] = updated
    wire["deadlineAtUtc"] = _policy_deadline(
        wire["schema"], updated, "project-materialized"
    )
    try:
        _replace_attempt_root(evidence, 0, _recheckpoint(wire))
        before = _tree_bytes(context.data_root)
        _assert_failure(
            show_acceptance_attempt(context, attempt_id=ATTEMPT_ID),
            "acceptance.attempt.show",
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 0) == original_wire


def test_rev1_updated_beyond_predecessor_deadline_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=1
        )
    )
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 1)
    original_root = root_path.read_bytes()
    first = recovery_workflows.PhysicalAcceptanceAttempt.from_value(
        _attempt_document(evidence, 0)[2]
    )
    assert first.deadline_at_utc is not None
    _, _, wire = _attempt_document(evidence, 1)
    original_wire = json.loads(json.dumps(wire))
    updated = _plus_microseconds(first.deadline_at_utc)
    wire["updatedAtUtc"] = updated
    wire["deadlineAtUtc"] = _policy_deadline(
        wire["schema"], updated, "firmware-built-before"
    )
    try:
        _replace_attempt_root(evidence, 1, _recheckpoint(wire))
        before = _tree_bytes(context.data_root)
        _assert_failure(
            show_acceptance_attempt(context, attempt_id=ATTEMPT_ID),
            "acceptance.attempt.show",
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 1) == original_wire


def test_rev2_rewriting_prior_published_digest_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=2
        )
    )
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 2)
    original_root = root_path.read_bytes()
    _, _, wire = _attempt_document(evidence, 2)
    original_wire = json.loads(json.dumps(wire))
    outputs = wire["stageOutputs"]
    assert isinstance(outputs, dict)
    # Revision 1 is the first revision that publishes projectModelDigest; the
    # latest revision must keep that published predecessor output unchanged.
    outputs["projectModelDigest"] = _different_hash(outputs["projectModelDigest"])
    try:
        _replace_attempt_root(evidence, 2, _recheckpoint(wire))
        before = _tree_bytes(context.data_root)
        _assert_failure(
            show_acceptance_attempt(context, attempt_id=ATTEMPT_ID),
            "acceptance.attempt.show",
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 2) == original_wire


def test_authorized_rev5_changing_expanded_intent_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=4
        )
    )
    resumed = _ok(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    action_digest = resumed["actionDigest"]
    assert isinstance(action_digest, str)
    authorized = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert authorized.ok is True, authorized.to_dict()
    evidence = _evidence(context)
    root_path = _attempt_root_path(evidence, 5)
    original_root = root_path.read_bytes()
    _, _, wire = _attempt_document(evidence, 5)
    original_wire = json.loads(json.dumps(wire))
    intent = SourceChangeIntent.from_value(wire["sourceChangeIntent"])
    assert intent.before_input_snapshot_sha256 is not None
    assert intent.expected_after_input_snapshot_sha256 is not None
    changes = [dict(item) for item in intent.changes]
    changes[0]["afterSha256"] = _different_hash(changes[0]["afterSha256"])
    wire["sourceChangeIntent"] = SourceChangeIntent.expanded(
        changes=changes,
        before_input_snapshot_sha256=intent.before_input_snapshot_sha256,
        expected_after_input_snapshot_sha256=intent.expected_after_input_snapshot_sha256,
    ).to_dict()
    try:
        _replace_attempt_root(evidence, 5, _recheckpoint(wire))
        before = _tree_bytes(context.data_root)
        _assert_failure(
            show_acceptance_attempt(context, attempt_id=ATTEMPT_ID),
            "acceptance.attempt.show",
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            MESSAGE_INTEGRITY,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        root_path.write_bytes(original_root)
    assert _show_head(context, 5) == original_wire


def test_project_origin_drift_is_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _diagnostic, _diagnostic_id = (
        physical_fixture._prepare_public_physical_attempt(
            tmp_path, monkeypatch, through_revision=1
        )
    )
    manifest_path = context.project_root / ".stm32-project.json"
    original_manifest = manifest_path.read_bytes()
    document = json.loads(original_manifest.decode("utf-8"))
    document["memory"]["source"] = "cubemx"
    try:
        manifest_path.write_bytes(canonical_json_bytes(document))
        assert load_project_model(context.project_root).memory.source == "cubemx"
        before = _tree_bytes(context.data_root)
        _assert_failure(
            show_acceptance_attempt(context, attempt_id=ATTEMPT_ID),
            "acceptance.attempt.show",
            "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
            MESSAGE_IDENTITY_MISMATCH,
        )
        assert _tree_bytes(context.data_root) == before
    finally:
        manifest_path.write_bytes(original_manifest)
    _show_head(context, 1)
