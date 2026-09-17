from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest

import test_acceptance_physical_recovery as physical_fixture
from stm32_toolkit.acceptance.continuation import (
    CONTINUATION_ATTEMPT_SCHEMA,
    CONTINUATION_REQUEST_SCHEMA,
    CONTINUATION_SCHEMA,
    ContinuationRequest,
    ContinuationValidationError,
    authenticate_continuation,
    prepare_continuation,
)
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PhysicalAcceptanceAttempt,
    SourceChangeIntent,
)
import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_plan,
    diagnostic_assess_hypothesis,
    diagnostic_begin,
    diagnostic_declare_source_change,
    diagnostic_run_plan,
    diagnostic_start,
)
from stm32_toolkit.diagnostics import DiagnosticSession, SourceChangeDeclaration
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity, canonical_json_bytes, get_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunPublisher, TestRunRepository
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run


LEGACY_ATTEMPT_ID = physical_fixture.ATTEMPT_ID
CONTINUATION_ATTEMPT_ID = "00000000-0000-4000-8000-000000000011"
CONTINUATION_REUSE_ID = "00000000-0000-4000-8000-000000000012"
CONTINUATION_RACE_ID = "00000000-0000-4000-8000-000000000013"
CONTINUATION_EXPIRED_ID = "00000000-0000-4000-8000-000000000014"
CONTINUATION_STALE_ID = "00000000-0000-4000-8000-000000000015"
CONTINUATION_REV7_ID = "00000000-0000-4000-8000-000000000016"
CONTINUATION_REPLAY_ID = "00000000-0000-4000-8000-000000000023"
PROJECT_ID = physical_fixture.PROJECT_ID
LEGACY_TIME = "2026-09-10T00:00:00.000000Z"
CONTINUATION_TIME = "2026-09-11T00:00:00.000000Z"
CONTINUATION_AFTER_DEADLINE = "2026-09-11T00:15:00.000001Z"


def _ok(result: object) -> dict[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return dict(data)


def _attempt_root_path(evidence: EvidenceStore, attempt_id: str, revision: int) -> Path:
    return recovery_workflows._typed_root_path(
        evidence, recovery_workflows._root_id(attempt_id, revision)
    )


def _continuation_request(
    *,
    predecessor_attempt_id: str,
    predecessor_checkpoint_id: str,
    predecessor_evidence_id: str,
    fixed_after_test_run_id: str,
    fixed_after_evidence_id: str,
    diagnostic_revision: int,
    diagnostic_event_head: str,
) -> dict[str, object]:
    return {
        "schema": CONTINUATION_REQUEST_SCHEMA,
        "kind": "bind",
        "predecessorAttemptId": predecessor_attempt_id,
        "predecessorCheckpointId": predecessor_checkpoint_id,
        "predecessorEvidenceId": predecessor_evidence_id,
        "fixedAfterTestRunId": fixed_after_test_run_id,
        "fixedAfterEvidenceId": fixed_after_evidence_id,
        "diagnosticRevision": diagnostic_revision,
        "diagnosticEventHead": diagnostic_event_head,
    }


def _write_root_document(path: Path, document: Mapping[str, object]) -> bytes:
    original = path.read_bytes()
    path.write_bytes(canonical_json_bytes(dict(document)))
    return original


def _publish_after_variant(
    fixture: SimpleNamespace,
    tmp_path: Path,
    field: str,
) -> object:
    """Publish a readable physical TestRun whose one binding field is wrong."""

    loaded = fixture.repository.load(fixture.fixed_run_id)
    identity = loaded.manifest.identity
    probe_id = str(loaded.envelope.metadata["probe_id"])
    transport_config_digest = str(loaded.envelope.metadata["transport_config_digest"])
    if field == "probe_id":
        probe_id = "1" * 64
    elif field == "transport_config_digest":
        transport_config_digest = "2" * 64
    elif field == "target_id":
        identity = replace(identity, target_device="STM32F103C8Tx")
    elif field == "build_id":
        identity = replace(identity, build_id="3" * 64)
    elif field == "elf_sha256":
        identity = replace(identity, elf_sha256="4" * 64)
    elif field == "input_snapshot_sha256":
        identity = replace(identity, input_snapshot_sha256="5" * 64)
    else:
        raise AssertionError(f"unsupported variant field: {field}")

    run_id = f"target-v2-fixed-t10-bad-{field.replace('_', '-')}"
    manifest = replace(
        loaded.manifest,
        run_id=run_id,
        identity=identity,
        transport="mailbox",
    )
    manifest_path = tmp_path / f"{run_id}-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = fixture.evidence.ingest_file(
        manifest_path, kind="test-manifest", media_type="application/json"
    )
    action_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    metadata = {
        "action_digest": action_digest,
        "execution_source": "physical",
        "flash_session_id": f"flash-{run_id}",
        "import_session_id": identity.session_id,
        "import_workspace_id": identity.workspace_id,
        "intent_digest": action_digest,
        "inventory_digest": calculate_inventory_digest(
            "target", identity, tuple(case.case_id for case in manifest.cases)
        ),
        "lease_id": f"lease-{run_id}",
        "origin_session_id": identity.session_id,
        "origin_workspace_id": identity.workspace_id,
        "physical_transport_evidence": True,
        "probe_id": probe_id,
        "target_id": identity.target_device,
        "transport_config_digest": transport_config_digest,
    }
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-physical",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, manifest.raw_events),
        metadata=metadata,
    )
    fixture.evidence.put_envelope(envelope)
    return TestRunPublisher(
        fixture.evidence,
        fixture.project_root,
        tmp_path / f"{run_id}-results",
    ).publish_target_physical(manifest, envelope)


def prepare_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Create the persisted v2 predecessor and a distinct-session physical pair.

    The fixture uses the repository's real replay seeds only to create the
    published P3/P4 records.  The continuation proof reads the resulting
    EvidenceStore, TestRunRepository, and rooted Diagnostic events directly.
    No reader or authorization provider is replaced.
    """

    project_root = tmp_path / "project"
    physical_fixture._write_physical_project(project_root)
    data_root = tmp_path / "data"
    before_session_id = "t10-cont-before"
    after_session_id = "t10-cont-after"
    testing = TestingWorkflowContext(project_root, data_root, before_session_id)
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, before_session_id)

    model = load_project_model(project_root)
    source_path = project_root / "App" / "main.c"
    before_source = source_path.read_bytes()
    before_snapshot = snapshot_project_inputs(model)
    after_source = b"int main(void) { return 1; }\n"
    source_path.write_bytes(after_source)
    after_snapshot = snapshot_project_inputs(load_project_model(project_root))
    source_path.write_bytes(before_source)
    before_source_sha256 = hashlib.sha256(before_source).hexdigest()
    after_source_sha256 = hashlib.sha256(after_source).hexdigest()

    before_workspace = WorkspacePaths.from_roots(
        data_root, project_root, UUID(PROJECT_ID), before_session_id
    )
    after_workspace = WorkspacePaths.from_roots(
        data_root, project_root, UUID(PROJECT_ID), after_session_id
    )
    before_identity = EvidenceIdentity(
        workspace_id=before_workspace.workspace_id,
        project_id=PROJECT_ID,
        session_id=before_session_id,
        build_id=physical_fixture.PHYSICAL_BEFORE_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        target_device=model.target.device,
        input_snapshot_sha256=before_snapshot.sha256,
        git_commit="b" * 40,
        git_dirty=False,
    )
    after_identity = EvidenceIdentity(
        workspace_id=after_workspace.workspace_id,
        project_id=PROJECT_ID,
        session_id=after_session_id,
        build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        elf_sha256=physical_fixture.PHYSICAL_AFTER_ELF,
        target_device=model.target.device,
        input_snapshot_sha256=after_snapshot.sha256,
        git_commit="c" * 40,
        git_dirty=False,
    )

    failed_seed_id = "seed-failed-t10-cont"
    fixed_seed_id = "seed-fixed-t10-cont"
    failed_run_id = "target-v2-failed-t10-cont"
    fixed_run_id = "target-v2-fixed-t10-cont"
    failed_descriptor, failed_stream = physical_fixture.vs08a_fixtures._canonical_replay_inputs(
        tmp_path, "failed-before", failed_seed_id
    )
    fixed_descriptor, fixed_stream = physical_fixture.vs08a_fixtures._canonical_replay_inputs(
        tmp_path, "fixed-after", fixed_seed_id
    )
    _ok(target_replay_run(testing, failed_seed_id, failed_descriptor, failed_stream))
    _ok(target_replay_run(testing, fixed_seed_id, fixed_descriptor, fixed_stream))
    failed_physical = physical_fixture._publish_physical_from_seed(
        tmp_path,
        project_root,
        data_root,
        before_session_id,
        failed_seed_id,
        failed_run_id,
        before_identity,
    )
    fixed_physical = physical_fixture._publish_physical_from_seed(
        tmp_path,
        project_root,
        data_root,
        after_session_id,
        fixed_seed_id,
        fixed_run_id,
        after_identity,
    )
    evidence = EvidenceStore(before_workspace.workspace_root / "evidence")
    repository = TestRunRepository(evidence)
    assert repository.load(failed_run_id).envelope == failed_physical.envelope
    assert repository.load(fixed_run_id).envelope == fixed_physical.envelope

    build_after = {"value": False}

    def fresh_firmware_facts(_project: Path):
        current_model = load_project_model(project_root)
        current_snapshot = snapshot_project_inputs(current_model)
        if build_after["value"]:
            build_id, elf_sha = (
                physical_fixture.PHYSICAL_AFTER_BUILD,
                physical_fixture.PHYSICAL_AFTER_ELF,
            )
        else:
            build_id, elf_sha = (
                physical_fixture.PHYSICAL_BEFORE_BUILD,
                physical_fixture.PHYSICAL_BEFORE_ELF,
            )
        return SimpleNamespace(
            model=current_model,
            elf_path="build/arm-debug/firmware.elf",
            elf_sha256=elf_sha,
            build_id=build_id,
            input_snapshot_sha256=current_snapshot.sha256,
            git_commit="b" * 40,
            git_dirty=False,
            target_device=current_model.target.device,
        )

    monkeypatch.setattr(
        recovery_workflows, "_load_fresh_firmware_facts", fresh_firmware_facts
    )
    monkeypatch.setattr(diagnostic_workflows, "_session_id_factory", lambda: "9" * 32)

    started = _ok(
        diagnostic_start(
            diagnostic,
            operation_id="t10-cont-diagnostic-start",
            failed_test_run_id=failed_run_id,
            failed_run_mode="target",
        )
    )
    diagnostic_id = str(started["session"]["diagnostic_session_id"])
    _ok(
        diagnostic_begin(
            diagnostic,
            operation_id="t10-cont-diagnostic-begin",
            diagnostic_session_id=diagnostic_id,
            expected_revision=1,
        )
    )
    hypothesis = _ok(
        diagnostic_add_hypothesis(
            diagnostic,
            operation_id="t10-cont-hypothesis-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=2,
            statement="the failed physical run identifies the faulty behavior",
        )
    )["hypothesis"]
    assert isinstance(hypothesis, Mapping)
    hypothesis_id = str(hypothesis["hypothesis_id"])
    plan = _ok(
        diagnostic_add_plan(
            diagnostic,
            operation_id="t10-cont-observation-plan-add",
            diagnostic_session_id=diagnostic_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "physical-failed-run",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "confirm the physical failure",
                }
            ],
        )
    )["observation_plan"]
    assert isinstance(plan, Mapping)
    plan_id = str(plan["plan_id"])
    _ok(
        diagnostic_run_plan(
            diagnostic,
            operation_id="t10-cont-observation-plan-run",
            diagnostic_session_id=diagnostic_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    _ok(
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="t10-cont-hypothesis-assess",
            diagnostic_session_id=diagnostic_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="physical-failed-run",
            polarity="supports",
            rationale="the failed physical run supports the hypothesis",
        )
    )

    legacy_context = AcceptanceRecoveryContext(
        project_root, data_root, before_session_id, clock=lambda: LEGACY_TIME
    )
    _ok(
        begin_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=0,
            stage="project-materialized",
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=1,
            stage="firmware-built-before",
        )
    )
    _ok(
        checkpoint_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=2,
            stage="target-failure-observed",
            test_run_id=failed_run_id,
        )
    )
    intent_input = {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "App/main.c",
                "beforeSha256": before_source_sha256,
                "afterSha256": after_source_sha256,
                "afterSize": len(after_source),
            }
        ],
    }
    diagnosis = _ok(
        checkpoint_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=3,
            stage="diagnosis-completed",
            diagnostic_session_id=diagnostic_id,
            source_change_intent=intent_input,
        )
    )["attempt"]
    assert isinstance(diagnosis, Mapping)
    assert diagnosis["revision"] == 4
    resume = _ok(resume_acceptance_attempt(legacy_context, attempt_id=LEGACY_ATTEMPT_ID))
    action_digest = str(resume["actionDigest"])
    _ok(
        recovery_workflows.authorize_acceptance_source_change(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=4,
            action_digest=action_digest,
            authorized=True,
        )
    )

    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(
        b"--- a/App/main.c\n+++ b/App/main.c\n@@ -1 +1 @@\n"
        b"-int main(void) { return 0; }\n+int main(void) { return 1; }\n"
    )
    diff_artifact = evidence.ingest_file(
        diff_path, kind="source-diff", media_type="text/x-diff"
    )
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc=LEGACY_TIME,
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    source_declaration = SourceChangeDeclaration.new(
        before_source_sha256=before_snapshot.sha256,
        after_source_sha256=after_snapshot.sha256,
        before_build_id=physical_fixture.PHYSICAL_BEFORE_BUILD,
        before_elf_sha256=physical_fixture.PHYSICAL_BEFORE_ELF,
        after_build_id=physical_fixture.PHYSICAL_AFTER_BUILD,
        after_elf_sha256=physical_fixture.PHYSICAL_AFTER_ELF,
        changed_paths=("App/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )
    declared = _ok(
        diagnostic_declare_source_change(
            diagnostic,
            operation_id="t10-cont-source-change-declare",
            diagnostic_session_id=diagnostic_id,
            expected_revision=6,
            source_change_declaration=source_declaration,
        )
    )
    diagnostic_session = DiagnosticSession.from_value(
        json.loads(canonical_json_bytes(declared["session"]).decode("utf-8"))
    )
    declaration = diagnostic_session.source_change_declarations[0]
    diagnostic_revision = diagnostic_session.revision
    diagnostic_event_head = diagnostic_session.event_head

    source_path.write_bytes(after_source)
    build_after["value"] = True
    after_build = _ok(
        checkpoint_acceptance_attempt(
            legacy_context,
            attempt_id=LEGACY_ATTEMPT_ID,
            expected_revision=5,
            stage="firmware-built-after",
        )
    )["attempt"]
    assert isinstance(after_build, Mapping)
    assert after_build["revision"] == 6
    predecessor_root_id = recovery_workflows._root_id(LEGACY_ATTEMPT_ID, 6)
    predecessor_root = get_root(evidence, "acceptance-attempt", predecessor_root_id)
    predecessor_envelope = evidence.get_envelope(predecessor_root.manifest_id)
    predecessor = PhysicalAcceptanceAttempt.from_value(
        json.loads(
            canonical_json_bytes(predecessor_envelope.metadata["attempt"]).decode("utf-8")
        )
    )
    assert predecessor.revision == 6
    assert predecessor.source_change_authorization is not None
    auth_revision = int(predecessor.source_change_authorization["diagnosticRevision"])
    assert diagnostic_revision > auth_revision
    assert predecessor.deadline_at_utc is not None
    assert predecessor.deadline_at_utc < CONTINUATION_TIME

    bind_request = _continuation_request(
        predecessor_attempt_id=LEGACY_ATTEMPT_ID,
        predecessor_checkpoint_id=predecessor.checkpoint_id,
        predecessor_evidence_id=str(predecessor_envelope.evidence_id),
        fixed_after_test_run_id=fixed_run_id,
        fixed_after_evidence_id=str(fixed_physical.envelope.evidence_id),
        diagnostic_revision=diagnostic_revision,
        diagnostic_event_head=diagnostic_event_head,
    )
    context = AcceptanceRecoveryContext(
        project_root, data_root, before_session_id, clock=lambda: CONTINUATION_TIME
    )
    return SimpleNamespace(
        project_root=project_root,
        data_root=data_root,
        model=model,
        source_path=source_path,
        before_source=before_source,
        after_source=after_source,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        before_session_id=before_session_id,
        after_session_id=after_session_id,
        testing=testing,
        diagnostic=diagnostic,
        legacy_context=legacy_context,
        context=context,
        before_workspace=before_workspace,
        after_workspace=after_workspace,
        workspace=before_workspace,
        evidence=evidence,
        repository=repository,
        before_identity=before_identity,
        after_identity=after_identity,
        failed_run_id=failed_run_id,
        fixed_run_id=fixed_run_id,
        failed_physical=failed_physical,
        fixed_physical=fixed_physical,
        diagnostic_session_id=diagnostic_id,
        diagnostic_session=diagnostic_session,
        diagnostic_revision=diagnostic_revision,
        diagnostic_event_head=diagnostic_event_head,
        hypothesis_id=hypothesis_id,
        declaration=declaration,
        predecessor=predecessor,
        predecessor_root_id=predecessor_root_id,
        predecessor_evidence_id=str(predecessor_envelope.evidence_id),
        predecessor_checkpoint_id=predecessor.checkpoint_id,
        source_authorization_revision=auth_revision,
        bind_request=bind_request,
    )


def test_continuation_request_accepts_mapping_and_is_closed() -> None:
    request = ContinuationRequest.from_value(
        MappingProxyType(
            {
                "schema": CONTINUATION_REQUEST_SCHEMA,
                "kind": "bind",
                "predecessorAttemptId": LEGACY_ATTEMPT_ID,
                "predecessorCheckpointId": "a" * 64,
                "predecessorEvidenceId": "b" * 64,
                "fixedAfterTestRunId": "target-v2-fixed-t10",
                "fixedAfterEvidenceId": "c" * 64,
                "diagnosticRevision": 7,
                "diagnosticEventHead": "d" * 64,
            }
        )
    )
    assert request.schema == CONTINUATION_REQUEST_SCHEMA
    assert request.kind == "bind"
    assert request.predecessor_attempt_id == LEGACY_ATTEMPT_ID
    assert request.diagnostic_revision == 7

    reuse = ContinuationRequest.from_value(
        MappingProxyType(
            {
                "schema": CONTINUATION_REQUEST_SCHEMA,
                "kind": "reuse",
                "continuationEvidenceId": "e" * 64,
            }
        )
    )
    assert reuse.kind == "reuse"
    assert reuse.continuation_evidence_id == "e" * 64

    with pytest.raises(ContinuationValidationError):
        ContinuationRequest.from_value(
            {
                "schema": CONTINUATION_REQUEST_SCHEMA,
                "kind": "bind",
                "predecessorAttemptId": LEGACY_ATTEMPT_ID,
                "predecessorCheckpointId": "a" * 64,
                "predecessorEvidenceId": "b" * 64,
                "fixedAfterTestRunId": "target-v2-fixed-t10",
                "fixedAfterEvidenceId": "c" * 64,
                "diagnosticRevision": 7,
                "diagnosticEventHead": "d" * 64,
                "extra": True,
            }
        )
    with pytest.raises(ContinuationValidationError):
        ContinuationRequest.from_value(tuple({"kind": "bind"}.items()))


def test_continuation_bind_reuse_show_resume_preserves_v2_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    old_root_path = _attempt_root_path(fixture.evidence, LEGACY_ATTEMPT_ID, 6)
    old_root_bytes = old_root_path.read_bytes()
    old_authorization = dict(fixture.predecessor.source_change_authorization or {})

    first = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    assert isinstance(first, Mapping)
    assert first["schema"] == CONTINUATION_ATTEMPT_SCHEMA
    assert first["revision"] == 0
    assert first["status"] == "IN_PROGRESS"
    assert first["stage"] == "verification-pending"
    continuation_id = str(first["continuationEvidenceId"])

    shown = _ok(
        show_acceptance_attempt(
            fixture.context, attempt_id=CONTINUATION_ATTEMPT_ID
        )
    )["attempt"]
    resumed = _ok(
        resume_acceptance_attempt(
            fixture.context, attempt_id=CONTINUATION_ATTEMPT_ID
        )
    )
    assert shown == first
    assert resumed["attempt"] == first
    assert resumed["nextStage"] == "target-fix-verified"
    assert resumed["timedOut"] is False

    association = authenticate_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        continuation_id,
        expected_workspace_id=fixture.workspace.workspace_id,
        expected_project_id=PROJECT_ID,
        expected_session_id=fixture.before_session_id,
    )
    assert association.proof.schema == CONTINUATION_SCHEMA
    assert association.proof.diagnostic_revision == fixture.diagnostic_revision
    assert association.proof.diagnostic_revision > fixture.source_authorization_revision
    assert association.proof.fixed_after_test_run_id == fixture.fixed_run_id
    assert association.proof.fixed_after_evidence_id == str(
        fixture.fixed_physical.envelope.evidence_id
    )
    assert association.diagnostic.session.revision == fixture.diagnostic_revision

    reuse_request = {
        "schema": CONTINUATION_REQUEST_SCHEMA,
        "kind": "reuse",
        "continuationEvidenceId": continuation_id,
    }
    reused = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_REUSE_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=reuse_request,
        )
    )["attempt"]
    assert reused["revision"] == 0
    assert reused["continuationEvidenceId"] == continuation_id
    assert reused["fixedAfterTestRunId"] == fixture.fixed_run_id

    retried = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    assert retried == first
    assert old_root_path.read_bytes() == old_root_bytes
    assert dict(fixture.predecessor.source_change_authorization or {}) == old_authorization
    assert fixture.predecessor.deadline_at_utc is not None
    assert fixture.predecessor.deadline_at_utc < first["openedAtUtc"]


def test_authenticated_continuation_rejects_tampered_parent_run_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    first = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    continuation_id = str(first["continuationEvidenceId"])

    association = authenticate_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        continuation_id,
        expected_workspace_id=fixture.workspace.workspace_id,
        expected_project_id=PROJECT_ID,
        expected_session_id=fixture.before_session_id,
    )
    continuation_root_id = association.proof.continuation_id
    continuation_root = get_root(
        fixture.evidence, "physical-continuation", continuation_root_id
    )
    continuation_root_path = recovery_workflows._typed_root_path(
        fixture.evidence, continuation_root_id, "physical-continuation"
    )
    root_document = json.loads(continuation_root_path.read_bytes().decode("utf-8"))
    root_document["manifest_id"] = "0" * 64
    original_root_bytes = _write_root_document(
        continuation_root_path, root_document
    )
    try:
        with pytest.raises(ContinuationValidationError):
            authenticate_continuation(
                fixture.evidence,
                fixture.workspace.diagnostics_root,
                continuation_id,
                expected_workspace_id=fixture.workspace.workspace_id,
                expected_project_id=PROJECT_ID,
                expected_session_id=fixture.before_session_id,
            )
    finally:
        continuation_root_path.write_bytes(original_root_bytes)
    assert continuation_root.root_id == continuation_root_id

    fixed_root = get_root(fixture.evidence, "test-run", fixture.fixed_run_id)
    fixed_root_path = recovery_workflows._typed_root_path(
        fixture.evidence, fixture.fixed_run_id, "test-run"
    )
    fixed_root_document = json.loads(fixed_root_path.read_bytes().decode("utf-8"))
    fixed_root_document["manifest_id"] = "0" * 64
    original_fixed_root_bytes = _write_root_document(
        fixed_root_path, fixed_root_document
    )
    try:
        with pytest.raises(ContinuationValidationError):
            authenticate_continuation(
                fixture.evidence,
                fixture.workspace.diagnostics_root,
                continuation_id,
                expected_workspace_id=fixture.workspace.workspace_id,
                expected_project_id=PROJECT_ID,
                expected_session_id=fixture.before_session_id,
            )
    finally:
        fixed_root_path.write_bytes(original_fixed_root_bytes)
    assert fixed_root.root_id == fixture.fixed_run_id

    with pytest.raises(ContinuationValidationError):
        authenticate_continuation(
            fixture.evidence,
            fixture.workspace.diagnostics_root,
            continuation_id,
            expected_workspace_id=fixture.workspace.workspace_id,
            expected_project_id=PROJECT_ID,
            expected_session_id="t10-cont-wrong-session",
        )


def test_continuation_deadline_cas_and_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    first = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    continuation_id = str(first["continuationEvidenceId"])

    same_intent = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    assert same_intent == first

    conflict = begin_acceptance_attempt(
        fixture.context,
        attempt_id=CONTINUATION_ATTEMPT_ID,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        continuation={
            "schema": CONTINUATION_REQUEST_SCHEMA,
            "kind": "reuse",
            "continuationEvidenceId": "f" * 64,
        },
    )
    assert conflict.ok is False
    assert conflict.code == "ACCEPTANCE_ATTEMPT_CONFLICT"

    race_barrier = __import__("threading").Barrier(2)

    def begin_at_barrier() -> object:
        race_barrier.wait()
        return begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_RACE_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation={
                "schema": CONTINUATION_REQUEST_SCHEMA,
                "kind": "reuse",
                "continuationEvidenceId": continuation_id,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced = list(pool.map(lambda _unused: begin_at_barrier(), (0, 1)))
    assert all(result.ok for result in raced), [result.to_dict() for result in raced]
    assert raced[0].data == raced[1].data
    assert _attempt_root_path(fixture.evidence, CONTINUATION_RACE_ID, 0).exists()

    expired_context = replace(
        fixture.context, clock=lambda: CONTINUATION_AFTER_DEADLINE
    )
    timed_out = _ok(
        resume_acceptance_attempt(
            expired_context, attempt_id=CONTINUATION_ATTEMPT_ID
        )
    )
    assert timed_out["timedOut"] is True
    assert timed_out["attempt"] == first

    expired_begin = _ok(
        begin_acceptance_attempt(
        expired_context,
        attempt_id=CONTINUATION_EXPIRED_ID,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        continuation={
            "schema": CONTINUATION_REQUEST_SCHEMA,
            "kind": "reuse",
            "continuationEvidenceId": continuation_id,
        },
        )
    )["attempt"]
    assert expired_begin["revision"] == 0
    assert expired_begin["openedAtUtc"] == CONTINUATION_AFTER_DEADLINE
    assert expired_begin["deadlineAtUtc"] == "2026-09-11T00:30:00.000001Z"
    assert _attempt_root_path(fixture.evidence, CONTINUATION_EXPIRED_ID, 0).exists()

    original = _ok(
        resume_acceptance_attempt(fixture.context, attempt_id=CONTINUATION_ATTEMPT_ID)
    )
    assert original["attempt"]["deadlineAtUtc"] == first["deadlineAtUtc"]


def test_fresh_bind_rejects_stale_diagnostic_and_existing_predecessor_terminal_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    continuation_root_dir = fixture.evidence.root / "roots" / "physical-continuation"
    roots_before = tuple(sorted(path.name for path in continuation_root_dir.glob("*.json")))

    stale_request = dict(fixture.bind_request)
    current_head = str(stale_request["diagnosticEventHead"])
    stale_request["diagnosticEventHead"] = (
        current_head[:-1] + ("0" if current_head[-1] != "0" else "1")
    )
    stale = begin_acceptance_attempt(
        fixture.context,
        attempt_id=CONTINUATION_STALE_ID,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        continuation=stale_request,
    )
    assert stale.ok is False
    assert tuple(sorted(path.name for path in continuation_root_dir.glob("*.json"))) == roots_before
    assert not _attempt_root_path(fixture.evidence, CONTINUATION_STALE_ID, 0).exists()

    proof, *_ = prepare_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        ContinuationRequest.from_value(fixture.bind_request),
        workspace_id=fixture.workspace.workspace_id,
        project_id=PROJECT_ID,
        expected_session_id=fixture.before_session_id,
    )
    continuation_root_path = recovery_workflows._typed_root_path(
        fixture.evidence, proof.continuation_id, "physical-continuation"
    )
    assert not continuation_root_path.exists()

    # A damaged predecessor terminal root is still a terminal predecessor
    # publication.  Fresh binding must fail before it can publish the proof
    # root, even though the root's manifest target is absent.
    predecessor_rev7_path = _attempt_root_path(
        fixture.evidence, LEGACY_ATTEMPT_ID, 7
    )
    predecessor_rev7_path.write_bytes(
        canonical_json_bytes(
            {
                "root_type": "acceptance-attempt",
                "root_id": f"{LEGACY_ATTEMPT_ID}.00000007",
                "manifest_id": "0" * 64,
                "metadata": {},
            }
        )
    )
    try:
        existing_terminal = begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_REV7_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
        assert existing_terminal.ok is False
        assert not continuation_root_path.exists()
        assert not _attempt_root_path(
            fixture.evidence, CONTINUATION_REV7_ID, 0
        ).exists()
    finally:
        predecessor_rev7_path.unlink(missing_ok=True)


def test_continuation_parent_order_swap_is_rejected_after_rehashing_envelope_and_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    first = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=fixture.bind_request,
        )
    )["attempt"]
    continuation_id = str(first["continuationEvidenceId"])
    association = authenticate_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        continuation_id,
        expected_workspace_id=fixture.workspace.workspace_id,
        expected_project_id=PROJECT_ID,
        expected_session_id=fixture.before_session_id,
    )
    assert len(association.envelope.parents) == 5
    assert len(set(association.envelope.parents)) == 5

    swapped_parents = (
        association.envelope.parents[1],
        association.envelope.parents[0],
        *association.envelope.parents[2:],
    )
    swapped_envelope = EvidenceEnvelope(
        identity=association.envelope.identity,
        operation=association.envelope.operation,
        produced_at_utc=association.envelope.produced_at_utc,
        parents=swapped_parents,
        artifacts=association.envelope.artifacts,
        metadata=association.envelope.metadata,
    )
    fixture.evidence.put_envelope(swapped_envelope)

    root_path = recovery_workflows._typed_root_path(
        fixture.evidence, association.proof.continuation_id, "physical-continuation"
    )
    original_root_bytes = root_path.read_bytes()
    original_root = get_root(
        fixture.evidence, "physical-continuation", association.proof.continuation_id
    )
    swapped_root = original_root.to_dict()
    swapped_root["manifest_id"] = str(swapped_envelope.evidence_id)
    root_path.write_bytes(canonical_json_bytes(swapped_root))
    try:
        with pytest.raises(ContinuationValidationError):
            authenticate_continuation(
                fixture.evidence,
                fixture.workspace.diagnostics_root,
                str(swapped_envelope.evidence_id),
                expected_workspace_id=fixture.workspace.workspace_id,
                expected_project_id=PROJECT_ID,
                expected_session_id=fixture.before_session_id,
            )
    finally:
        root_path.write_bytes(original_root_bytes)

    # The valid root and its original envelope remain usable after the
    # rehashed alternate parent ordering is removed.
    restored = authenticate_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        continuation_id,
        expected_workspace_id=fixture.workspace.workspace_id,
        expected_project_id=PROJECT_ID,
        expected_session_id=fixture.before_session_id,
    )
    assert restored.proof.continuation_id == association.proof.continuation_id


def test_continuation_rejects_readable_after_run_binding_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    variants = (
        "probe_id",
        "target_id",
        "transport_config_digest",
        "build_id",
        "elf_sha256",
        "input_snapshot_sha256",
    )
    attempt_ids = (
        "00000000-0000-4000-8000-000000000017",
        "00000000-0000-4000-8000-000000000018",
        "00000000-0000-4000-8000-000000000019",
        "00000000-0000-4000-8000-000000000020",
        "00000000-0000-4000-8000-000000000021",
        "00000000-0000-4000-8000-000000000022",
    )
    for field, attempt_id in zip(variants, attempt_ids):
        variant = _publish_after_variant(fixture, tmp_path, field)
        loaded = fixture.repository.load(variant.manifest.run_id)
        assert loaded.manifest.run_id == variant.manifest.run_id
        assert loaded.envelope == variant.envelope
        assert loaded.root == variant.root
        if field == "probe_id":
            assert loaded.envelope.metadata["probe_id"] == "1" * 64
        elif field == "target_id":
            assert loaded.manifest.identity.target_device == "STM32F103C8Tx"
            assert loaded.envelope.metadata["target_id"] == "STM32F103C8Tx"
        elif field == "transport_config_digest":
            assert loaded.envelope.metadata["transport_config_digest"] == "2" * 64
        elif field == "build_id":
            assert loaded.manifest.identity.build_id == "3" * 64
        elif field == "elf_sha256":
            assert loaded.manifest.identity.elf_sha256 == "4" * 64
        elif field == "input_snapshot_sha256":
            assert loaded.manifest.identity.input_snapshot_sha256 == "5" * 64

        request = dict(fixture.bind_request)
        request["fixedAfterTestRunId"] = variant.manifest.run_id
        request["fixedAfterEvidenceId"] = str(variant.envelope.evidence_id)
        rejected = begin_acceptance_attempt(
            fixture.context,
            attempt_id=attempt_id,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=request,
        )
        assert rejected.ok is False, {
            "field": field,
            "result": rejected.to_dict(),
        }
        assert not _attempt_root_path(fixture.evidence, attempt_id, 0).exists()


def test_continuation_rejects_readable_replay_after_test_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare_pair(tmp_path, monkeypatch)
    replay = fixture.repository.load("seed-fixed-t10-cont")
    assert replay.manifest.run_id == "seed-fixed-t10-cont"
    assert replay.manifest.transport == "replay"
    assert replay.envelope.metadata["execution_source"] == "replay"
    assert replay.envelope.metadata["physical_transport_evidence"] is False

    request = dict(fixture.bind_request)
    request["fixedAfterTestRunId"] = replay.manifest.run_id
    request["fixedAfterEvidenceId"] = str(replay.envelope.evidence_id)
    rejected = begin_acceptance_attempt(
        fixture.context,
        attempt_id=CONTINUATION_REPLAY_ID,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
        continuation=request,
    )
    assert rejected.ok is False, rejected.to_dict()
    assert not _attempt_root_path(
        fixture.evidence, CONTINUATION_REPLAY_ID, 0
    ).exists()
