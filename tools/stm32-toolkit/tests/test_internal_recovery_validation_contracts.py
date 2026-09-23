"""Internal-pure validation coverage for the frozen Toolkit boundary.

These tests intentionally call the eight approved read-only validators directly.
Every mutated wire object is rebuilt through its ordinary public constructor so
its content address is real.  The physical-shaped values are in-memory,
untrusted unit inputs only; they are never persisted, authenticated, or treated
as physical evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from stm32_toolkit import diagnostic_workflows
from stm32_toolkit.acceptance import recovery_workflows
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_RECOVERY_POLICY_DIGEST,
    PHYSICAL_SCENARIO_DIGEST,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_STAGES,
    AcceptanceAttempt,
    PhysicalAcceptanceAttempt,
    SourceChangeIntent,
)
from stm32_toolkit.diagnostics import DiagnosticSession, SourceChangeDeclaration
from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing.publication import PublishedTestRun, TestRunRepository
from test_risk_recovery_public_producers import (
    ATTEMPT_ID,
    FAILED_RUN_ID,
    PROJECT_ID,
    SESSION_ID,
    _prepare_chain_prefix,
    _revision_root,
)

_UTC_BASE = "2026-09-23T00:00:00.000000Z"
_PHYSICAL_ATTEMPT_ID = "00000000-0000-4000-8000-000000000004"


def _thawed(value: object) -> object:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _rebuild_envelope(
    envelope: EvidenceEnvelope,
    *,
    parents: tuple[str, ...] | None = None,
    metadata: object | None = None,
) -> EvidenceEnvelope:
    """Build a new envelope and let its public constructor recalculate its ID."""
    return EvidenceEnvelope(
        identity=envelope.identity,
        operation=envelope.operation,
        produced_at_utc=envelope.produced_at_utc,
        parents=envelope.parents if parents is None else parents,
        artifacts=envelope.artifacts,
        metadata=_thawed(envelope.metadata) if metadata is None else metadata,
    )


def _rebuild_published(
    published: PublishedTestRun, envelope: EvidenceEnvelope
) -> PublishedTestRun:
    """Keep genuine manifest/identity data while pointing an untrusted root at ``envelope``."""
    root = RootRecord(
        root_type=published.root.root_type,
        root_id=published.root.root_id,
        manifest_id=str(envelope.evidence_id),
        metadata=_thawed(published.root.metadata),
    )
    return PublishedTestRun(
        published.manifest,
        published.manifest_artifact,
        envelope,
        root,
    )


def _published_snapshot(published: PublishedTestRun) -> bytes:
    return canonical_json_bytes(
        {
            "manifest": published.manifest.to_dict(),
            "manifest_artifact": published.manifest_artifact.to_dict(),
            "envelope": published.envelope.to_dict(),
            "root": published.root.to_dict(),
        }
    )


def _generic_chain(
    prefix: object, evidence: object
) -> list[tuple[AcceptanceAttempt, EvidenceEnvelope]]:
    del prefix
    chain: list[tuple[AcceptanceAttempt, EvidenceEnvelope]] = []
    for revision in range(4):
        _root_path, root = _revision_root(evidence, revision)
        envelope = evidence.get_envelope(root.manifest_id)
        raw_attempt = _thawed(envelope.metadata["attempt"])
        assert isinstance(raw_attempt, dict)
        attempt = AcceptanceAttempt.from_value(raw_attempt)
        decoded = recovery_workflows._decode_attempt_envelope(
            evidence,
            root=root,
            envelope=envelope,
            expected_attempt_id=ATTEMPT_ID,
            expected_revision=revision,
            workspace_id=attempt.workspace_id,
            logical_project_id=attempt.logical_project_id,
        )
        assert decoded == attempt
        chain.append((attempt, envelope))
    return chain


def _checkpointed_attempt_payload(
    *,
    cls: type[AcceptanceAttempt | PhysicalAcceptanceAttempt],
    values: dict[str, object],
) -> AcceptanceAttempt | PhysicalAcceptanceAttempt:
    without_checkpoint = {
        key: value for key, value in values.items() if key != "checkpointId"
    }
    values["checkpointId"] = hashlib.sha256(
        canonical_json_bytes(without_checkpoint)
    ).hexdigest()
    return cls.from_value(values)  # type: ignore[return-value]


def _physical_chain(
    identity: object, workspace: WorkspacePaths
) -> list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]]:
    attempts: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]] = []
    identity_type = type(identity)
    previous_checkpoint: str | None = None
    previous_evidence_id: str | None = None
    stage_timeouts = (60, 900, 300, 900)
    for revision in range(4):
        updated = (
            datetime.strptime(_UTC_BASE, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=timezone.utc
            )
            + timedelta(seconds=revision)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        outputs = {key: None for key in recovery_workflows.PHYSICAL_STAGE_OUTPUT_KEYS}
        if revision >= 1:
            outputs["projectModelDigest"] = "1" * 64
        if revision >= 2:
            outputs.update(
                {
                    "beforeBuildId": identity.build_id,
                    "beforeElfSha256": identity.elf_sha256,
                    "beforeInputSnapshotSha256": identity.input_snapshot_sha256,
                }
            )
        if revision >= 3:
            outputs.update(
                {
                    "failedBeforeTestRunId": FAILED_RUN_ID,
                    "failedBeforeEvidenceId": "2" * 64,
                }
            )
        payload = {
            "schema": PHYSICAL_ATTEMPT_SCHEMA,
            "attemptId": _PHYSICAL_ATTEMPT_ID,
            "revision": revision,
            "checkpointId": "0" * 64,
            "previousCheckpointId": previous_checkpoint,
            "scenarioId": PHYSICAL_SCENARIO_ID,
            "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
            "scenarioDigest": PHYSICAL_SCENARIO_DIGEST,
            "recoveryPolicyDigest": PHYSICAL_RECOVERY_POLICY_DIGEST,
            "workspaceId": workspace.workspace_id,
            "logicalProjectId": str(identity.project_id),
            "projectOrigin": "keil",
            "executionSource": "physical",
            "physicalTransportEvidence": revision >= 3,
            "status": "ACTIVE",
            "completedStages": list(PHYSICAL_STAGES[:revision]),
            "stageOutputs": outputs,
            "sourceChangeAuthorization": None,
            "sourceChangeIntent": None,
            "openedAtUtc": _UTC_BASE,
            "deadlineAtUtc": (
                datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=timezone.utc
                )
                + timedelta(seconds=stage_timeouts[revision])
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "updatedAtUtc": updated,
        }
        attempt = _checkpointed_attempt_payload(
            cls=PhysicalAcceptanceAttempt, values=payload
        )
        assert isinstance(attempt, PhysicalAcceptanceAttempt)
        envelope = EvidenceEnvelope(
            identity=identity_type(**identity.to_dict()),
            operation="acceptance-attempt",
            produced_at_utc=updated,
            parents=() if previous_evidence_id is None else (previous_evidence_id,),
            artifacts=(),
            metadata={
                "attempt": attempt.to_dict(),
                "attempt_sha256": attempt.checkpoint_id,
            },
        )
        attempts.append((attempt, envelope))
        previous_checkpoint = attempt.checkpoint_id
        previous_evidence_id = str(envelope.evidence_id)
    return attempts


def _generic_session(
    prefix: object,
    before: PublishedTestRun,
    attempt: AcceptanceAttempt,
    *,
    state: str,
    failed_test_run_id: str = FAILED_RUN_ID,
) -> DiagnosticSession:
    return DiagnosticSession(
        diagnostic_session_id=prefix.diagnostic_compact_id,
        revision=1,
        state=state,
        identity=before.manifest.identity,
        failed_test_run_id=failed_test_run_id,
        failed_evidence_id=attempt.stage_outputs["failedBeforeEvidenceId"],
        event_head="3" * 64,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
        failed_run_mode="target",
    )


def _physical_session(
    prefix: object,
    before: PublishedTestRun,
    attempt: PhysicalAcceptanceAttempt,
    *,
    state: str,
    failed_evidence_id: str | None = None,
) -> DiagnosticSession:
    return DiagnosticSession(
        diagnostic_session_id=prefix.diagnostic_compact_id,
        revision=1,
        state=state,
        identity=before.manifest.identity,
        failed_test_run_id=FAILED_RUN_ID,
        failed_evidence_id=(
            attempt.stage_outputs["failedBeforeEvidenceId"]
            if failed_evidence_id is None
            else failed_evidence_id
        ),
        event_head="4" * 64,
        hypotheses=(),
        observation_plans=(),
        observation_results=(),
        failed_run_mode="target",
    )


def _declaration_fixture(
    chain: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]],
    hypothesis_id: str,
) -> tuple[SourceChangeIntent, SourceChangeDeclaration]:
    before_input = chain[3][0].stage_outputs["beforeInputSnapshotSha256"]
    before_build = chain[3][0].stage_outputs["beforeBuildId"]
    before_elf = chain[3][0].stage_outputs["beforeElfSha256"]
    assert isinstance(before_input, str)
    assert isinstance(before_build, str)
    assert isinstance(before_elf, str)
    intent = SourceChangeIntent.expanded(
        changes=[
            {
                "path": "App/main.c",
                "beforeSha256": "a" * 64,
                "afterSha256": "b" * 64,
                "afterSize": 20,
            }
        ],
        before_input_snapshot_sha256=before_input,
        expected_after_input_snapshot_sha256="d" * 64,
    )
    declaration = SourceChangeDeclaration.new(
        before_source_sha256=before_input,
        after_source_sha256="d" * 64,
        before_build_id=before_build,
        before_elf_sha256=before_elf,
        after_build_id="c" * 64,
        after_elf_sha256="f" * 64,
        changed_paths=("App/main.c",),
        diff_evidence_id="e" * 64,
        diff_artifact=ArtifactRef(
            sha256="7" * 64,
            size_bytes=1,
            relative_path="change.diff",
            kind="source-diff",
            media_type="text/x-diff",
        ),
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="8" * 64,
    )
    return intent, declaration


def test_internal_generic_envelope_chain_and_diagnostic_contracts(
    tmp_path: Path,
) -> None:
    prefix, evidence = _prepare_chain_prefix(tmp_path, latest_revision=3)
    chain = _generic_chain(prefix, evidence)
    model = load_project_model(prefix.project_root)
    workspace = WorkspacePaths.from_roots(
        prefix.data_root, prefix.project_root, PROJECT_ID, SESSION_ID
    )

    chain_snapshot = canonical_json_bytes(
        [(attempt.to_dict(), envelope.to_dict()) for attempt, envelope in chain]
    )
    recovery_workflows._validate_chain_semantics(
        chain, model=model, workspace=workspace
    )
    assert chain_snapshot == canonical_json_bytes(
        [(attempt.to_dict(), envelope.to_dict()) for attempt, envelope in chain]
    )

    _root_path, original_root = _revision_root(evidence, 0)
    bad_revision_root = RootRecord(
        root_type=original_root.root_type,
        root_id=original_root.root_id,
        manifest_id=original_root.manifest_id,
        metadata={**dict(original_root.metadata), "revision": 99},
    )
    bad_revision_snapshot = bad_revision_root.to_dict()
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._decode_attempt_envelope(
            evidence,
            root=bad_revision_root,
            envelope=chain[0][1],
            expected_attempt_id=ATTEMPT_ID,
            expected_revision=0,
            workspace_id=chain[0][0].workspace_id,
            logical_project_id=chain[0][0].logical_project_id,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    assert bad_revision_root.to_dict() == bad_revision_snapshot

    wrong_manifest_root = RootRecord(
        root_type=original_root.root_type,
        root_id=original_root.root_id,
        manifest_id=str(chain[1][1].evidence_id),
        metadata=original_root.metadata,
    )
    wrong_manifest_snapshot = wrong_manifest_root.to_dict()
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._decode_attempt_envelope(
            evidence,
            root=wrong_manifest_root,
            envelope=chain[0][1],
            expected_attempt_id=ATTEMPT_ID,
            expected_revision=0,
            workspace_id=chain[0][0].workspace_id,
            logical_project_id=chain[0][0].logical_project_id,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
    assert wrong_manifest_root.to_dict() == wrong_manifest_snapshot

    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_chain_semantics([])
    assert error.value.code == "ACCEPTANCE_ATTEMPT_NOT_FOUND"

    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_chain_semantics(
            chain[1:], model=model, workspace=workspace
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"

    before = TestRunRepository(evidence).load(FAILED_RUN_ID)
    session = _generic_session(prefix, before, chain[-1][0], state="INVESTIGATING")
    recovery_workflows._validate_diagnostic_session(
        session,
        chain[-1][0],
        model,
        workspace,
        expected_session_id=prefix.diagnostic_compact_id,
        allow_source_change=False,
    )
    identity_bad = _generic_session(
        prefix,
        before,
        chain[-1][0],
        state="INVESTIGATING",
        failed_test_run_id="00000000-0000-4000-8000-000000000099",
    )
    identity_snapshot = identity_bad.to_dict()
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_diagnostic_session(
            identity_bad,
            chain[-1][0],
            model,
            workspace,
            expected_session_id=prefix.diagnostic_compact_id,
            allow_source_change=False,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert identity_bad.to_dict() == identity_snapshot

    for allow_source_change in (False, True):
        abandoned = _generic_session(prefix, before, chain[-1][0], state="ABANDONED")
        abandoned_snapshot = abandoned.to_dict()
        with pytest.raises(recovery_workflows._RecoveryFailure) as error:
            recovery_workflows._validate_diagnostic_session(
                abandoned,
                chain[-1][0],
                model,
                workspace,
                expected_session_id=prefix.diagnostic_compact_id,
                allow_source_change=allow_source_change,
            )
        assert error.value.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"
        assert abandoned.to_dict() == abandoned_snapshot


def test_internal_physical_chain_diagnostic_and_declaration_contracts(
    tmp_path: Path,
) -> None:
    prefix, evidence = _prepare_chain_prefix(tmp_path, latest_revision=3)
    model = load_project_model(prefix.project_root)
    workspace = WorkspacePaths.from_roots(
        prefix.data_root, prefix.project_root, PROJECT_ID, SESSION_ID
    )
    before = TestRunRepository(evidence).load(FAILED_RUN_ID)
    chain = _physical_chain(before.manifest.identity, workspace)
    chain_snapshot = canonical_json_bytes(
        [(attempt.to_dict(), envelope.to_dict()) for attempt, envelope in chain]
    )
    recovery_workflows._validate_physical_chain_semantics(
        chain,
        model=model,
        workspace=workspace,
        session_id=SESSION_ID,
    )
    assert chain_snapshot == canonical_json_bytes(
        [(attempt.to_dict(), envelope.to_dict()) for attempt, envelope in chain]
    )

    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_physical_chain_semantics([])
    assert error.value.code == "ACCEPTANCE_ATTEMPT_NOT_FOUND"

    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_physical_chain_semantics(
            chain[1:], model=model, workspace=workspace, session_id=SESSION_ID
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"

    recovery_workflows._validate_physical_chain_semantics(
        chain, model=None, workspace=None, session_id=None
    )

    session = _physical_session(prefix, before, chain[3][0], state="INVESTIGATING")
    recovery_workflows._validate_physical_diagnostic_session(
        session,
        chain[3][0],
        model,
        workspace,
        prefix.context,
        expected_session_id=prefix.diagnostic_compact_id,
        allow_source_change=False,
    )
    identity_bad = _physical_session(
        prefix, before, chain[3][0], state="INVESTIGATING", failed_evidence_id="3" * 64
    )
    identity_snapshot = identity_bad.to_dict()
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._validate_physical_diagnostic_session(
            identity_bad,
            chain[3][0],
            model,
            workspace,
            prefix.context,
            expected_session_id=prefix.diagnostic_compact_id,
            allow_source_change=False,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert identity_bad.to_dict() == identity_snapshot

    for allow_source_change in (False, True):
        abandoned = _physical_session(prefix, before, chain[3][0], state="ABANDONED")
        abandoned_snapshot = abandoned.to_dict()
        with pytest.raises(recovery_workflows._RecoveryFailure) as error:
            recovery_workflows._validate_physical_diagnostic_session(
                abandoned,
                chain[3][0],
                model,
                workspace,
                prefix.context,
                expected_session_id=prefix.diagnostic_compact_id,
                allow_source_change=allow_source_change,
            )
        assert error.value.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"
        assert abandoned.to_dict() == abandoned_snapshot

    intent, declaration = _declaration_fixture(chain, prefix.hypothesis_id)
    valid_build = {
        "inputSnapshotSha256": "d" * 64,
        "buildId": "c" * 64,
        "elfSha256": "f" * 64,
    }
    recovery_workflows._physical_validate_declaration(
        declaration, chain[3][0], intent, after_build=valid_build
    )

    conflict_intent = SourceChangeIntent.expanded(
        changes=[
            {
                "path": "App/other.c",
                "beforeSha256": "a" * 64,
                "afterSha256": "b" * 64,
                "afterSize": 20,
            }
        ],
        before_input_snapshot_sha256=chain[3][0].stage_outputs[
            "beforeInputSnapshotSha256"
        ],
        expected_after_input_snapshot_sha256="d" * 64,
    )
    declaration_snapshot = declaration.to_dict()
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._physical_validate_declaration(
            declaration, chain[3][0], conflict_intent, after_build=valid_build
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert declaration.to_dict() == declaration_snapshot

    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._physical_validate_declaration(
            declaration,
            chain[3][0],
            intent,
            after_build={
                "inputSnapshotSha256": "e" * 64,
                "buildId": "c" * 64,
                "elfSha256": "f" * 64,
            },
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert declaration.to_dict() == declaration_snapshot


def test_internal_diagnostic_execution_policy_contracts(tmp_path: Path) -> None:
    _prefix, evidence = _prepare_chain_prefix(tmp_path, latest_revision=1)
    published = TestRunRepository(evidence).load(FAILED_RUN_ID)
    assert diagnostic_workflows._execution_policy(published) == ("replay", False)
    assert diagnostic_workflows._validate_pair_execution_policy(
        published, published
    ) == ("replay", False)

    malformed_envelope = _rebuild_envelope(
        published.envelope, metadata={"execution_source": "replay"}
    )
    malformed_published = _rebuild_published(published, malformed_envelope)
    malformed_snapshot = _published_snapshot(malformed_published)
    with pytest.raises(diagnostic_workflows._WorkflowFailure) as error:
        diagnostic_workflows._execution_policy(malformed_published)
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert _published_snapshot(malformed_published) == malformed_snapshot

    physical_label = _rebuild_envelope(
        published.envelope,
        metadata={
            **dict(published.envelope.metadata),
            "execution_source": "physical",
            "physical_transport_evidence": True,
        },
    )
    physical_published = _rebuild_published(published, physical_label)
    published_snapshot = _published_snapshot(published)
    physical_snapshot = _published_snapshot(physical_published)
    with pytest.raises(diagnostic_workflows._WorkflowFailure) as error:
        diagnostic_workflows._validate_pair_execution_policy(
            published, physical_published
        )
    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _published_snapshot(published) == published_snapshot
    assert _published_snapshot(physical_published) == physical_snapshot
