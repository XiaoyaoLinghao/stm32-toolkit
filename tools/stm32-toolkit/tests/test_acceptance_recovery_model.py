from __future__ import annotations

import hashlib

import pytest

from stm32_toolkit.acceptance.model import REQUIRED_STAGES
from stm32_toolkit.acceptance.recovery import (
    AcceptanceAttempt,
    AcceptanceRecoveryValidationError,
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_RECOVERY_POLICY_DIGEST,
    PHYSICAL_SCENARIO_DIGEST,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_STAGE_OUTPUT_KEYS,
    PHYSICAL_STAGES,
    PhysicalAcceptanceAttempt,
    SourceChangeIntent,
    acceptance_recovery_policy,
    physical_acceptance_recovery_policy,
)
from stm32_toolkit.evidence import canonical_json_bytes


def _revision_zero(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "stm32-acceptance-attempt/1",
        "attemptId": "00000000-0000-4000-8000-000000000001",
        "revision": 0,
        "checkpointId": "0" * 64,
        "previousCheckpointId": None,
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "recoveryPolicyDigest": "af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c",
        "workspaceId": "a" * 64,
        "logicalProjectId": "00000000-0000-4000-8000-000000000002",
        "projectOrigin": "keil",
        "executionSource": "replay",
        "physicalTransportEvidence": False,
        "status": "ACTIVE",
        "completedStages": [],
        "stageOutputs": {
            "projectModelDigest": None,
            "beforeBuildId": None,
            "beforeElfSha256": None,
            "beforeInputSnapshotSha256": None,
            "failedBeforeTestRunId": None,
            "failedBeforeEvidenceId": None,
            "diagnosticSessionId": None,
            "diagnosticRevision": None,
            "diagnosticEventHead": None,
            "afterBuildId": None,
            "afterElfSha256": None,
            "afterInputSnapshotSha256": None,
            "sourceChangeDeclarationId": None,
            "acceptanceRecordId": None,
        },
        "sourceChangeAuthorization": None,
        "openedAtUtc": "2026-08-24T00:00:00.000000Z",
        "deadlineAtUtc": "2026-08-24T00:01:00.000000Z",
        "updatedAtUtc": "2026-08-24T00:00:00.000000Z",
    }
    value.update(overrides)
    return value


def _with_checkpoint(payload: dict[str, object]) -> dict[str, object]:
    unsigned = dict(payload)
    unsigned.pop("checkpointId")
    unsigned["checkpointId"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    return unsigned


def test_recovery_policy_is_frozen_software_only_and_flash_inapplicable():
    policy = acceptance_recovery_policy()
    assert policy.to_dict() == {
        "schema": "stm32-acceptance-recovery-policy/1",
        "attemptSchema": "stm32-acceptance-attempt/1",
        "stageTimeoutSeconds": {
            "project-materialized": 60,
            "firmware-built-before": 900,
            "target-failure-replayed": 300,
            "diagnosis-completed": 900,
            "firmware-built-after": 900,
            "target-fix-verified": 300,
        },
        "intrusiveActions": {
            "source-change": {
                "afterStage": "diagnosis-completed",
                "applicable": True,
                "authorization": "explicit-single-use",
                "beforeStage": "firmware-built-after",
            },
            "flash": {
                "applicable": False,
                "authorization": "existing-probe-action-digest",
                "reason": "software-replay",
            },
        },
        "physicalTransportEvidence": False,
    }
    assert policy.digest == "af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c"


def test_revision_zero_round_trips_with_hand_derived_checkpoint_digest():
    payload = _with_checkpoint(_revision_zero())
    attempt = AcceptanceAttempt.from_value(payload)
    assert attempt.to_dict() == payload
    assert attempt.checkpoint_id == payload["checkpointId"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"revision": True},
        {"revision": 8},
        {"physicalTransportEvidence": True},
        {"status": "COMPLETED"},
        {"extra": None},
        {"completedStages": ("project-materialized",)},
    ],
)
def test_attempt_rejects_noncontract_mutations(mutation: dict[str, object]):
    payload = _with_checkpoint(_revision_zero(**mutation))
    with pytest.raises(AcceptanceRecoveryValidationError):
        AcceptanceAttempt.from_value(payload)


def test_attempt_rejects_invalid_digest_domain_links_and_timestamps():
    payload = _with_checkpoint(_revision_zero())
    for mutation in (
        {"checkpointId": "1" * 64},
        {"previousCheckpointId": "2" * 64},
        {"attemptId": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"workspaceId": "A" * 64},
        {"openedAtUtc": "2026-08-24T00:00:00Z"},
        {"updatedAtUtc": "2026-08-23T23:59:59.000000Z"},
    ):
        changed = dict(payload)
        changed.update(mutation)
        with pytest.raises(AcceptanceRecoveryValidationError):
            AcceptanceAttempt.from_value(changed)


def test_revision_zero_has_exact_stage_output_nulls_and_fixed_prefix():
    payload = _with_checkpoint(_revision_zero())
    attempt = AcceptanceAttempt.from_value(payload)
    assert tuple(attempt.completed_stages) == ()
    assert set(attempt.stage_outputs) == {
        "projectModelDigest",
        "beforeBuildId",
        "beforeElfSha256",
        "beforeInputSnapshotSha256",
        "failedBeforeTestRunId",
        "failedBeforeEvidenceId",
        "diagnosticSessionId",
        "diagnosticRevision",
        "diagnosticEventHead",
        "afterBuildId",
        "afterElfSha256",
        "afterInputSnapshotSha256",
        "sourceChangeDeclarationId",
        "acceptanceRecordId",
    }
    assert all(value is None for value in attempt.stage_outputs.values())


def test_physical_policy_and_source_intent_are_frozen_and_round_trip():
    policy = physical_acceptance_recovery_policy()
    assert policy.schema == "stm32-acceptance-recovery-policy/2"
    assert policy.attempt_schema == PHYSICAL_ATTEMPT_SCHEMA
    assert policy.scenario_id == PHYSICAL_SCENARIO_ID
    assert policy.scenario_version == PHYSICAL_SCENARIO_VERSION
    assert policy.scenario_digest == PHYSICAL_SCENARIO_DIGEST
    assert policy.digest == PHYSICAL_RECOVERY_POLICY_DIGEST
    assert policy.physical_transport_evidence is True

    input_value = {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "src/main.c",
                "beforeSha256": "a" * 64,
                "afterSha256": "b" * 64,
                "afterSize": 12,
            }
        ],
    }
    intent = SourceChangeIntent.new(changes=input_value["changes"])
    assert intent.to_dict() == input_value
    expanded = SourceChangeIntent.expanded(
        changes=input_value["changes"],
        before_input_snapshot_sha256="c" * 64,
        expected_after_input_snapshot_sha256="d" * 64,
    )
    assert SourceChangeIntent.from_value(expanded.to_dict()) == expanded
    assert expanded.intent_digest is not None
    assert set(expanded.to_dict()) == {
        "schema", "changes", "beforeInputSnapshotSha256",
        "expectedAfterInputSnapshotSha256", "intentDigest",
    }


@pytest.mark.parametrize("schema", [
    "stm32-source-change-intent/0",
    "stm32-source-change-intent/999",
    "other-schema/1",
])
def test_source_change_intent_rejects_unknown_input_schema(schema: str):
    with pytest.raises(AcceptanceRecoveryValidationError):
        SourceChangeIntent.from_value(
            {
                "schema": schema,
                "changes": [{
                    "path": "src/main.c",
                    "beforeSha256": "a" * 64,
                    "afterSha256": "b" * 64,
                    "afterSize": 12,
                }],
            }
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"beforeSha256": "a" * 64, "afterSha256": "a" * 64},
        {"path": "../main.c"},
        {"path": "src\\main.c"},
        {"afterSize": -1},
    ],
)
def test_source_change_intent_rejects_unchanged_or_nonportable_input(mutation):
    change = {
        "path": "src/main.c",
        "beforeSha256": "a" * 64,
        "afterSha256": "b" * 64,
        "afterSize": 12,
    }
    change.update(mutation)
    with pytest.raises(AcceptanceRecoveryValidationError):
        SourceChangeIntent.new(changes=[change])


def test_physical_stage_outputs_replace_v1_acceptance_record_and_keep_native_run_ids():
    assert "acceptanceRecordId" not in PHYSICAL_STAGE_OUTPUT_KEYS
    assert {
        "fixedAfterTestRunId", "fixedAfterEvidenceId", "fixVerificationId",
    } <= set(PHYSICAL_STAGE_OUTPUT_KEYS)


def _physical_attempt_payload(
    *,
    revision: int = 4,
    source_change_intent: object | None = None,
    expected_after_snapshot: str = "5" * 64,
) -> dict[str, object]:
    outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    outputs.update(
        {
            "projectModelDigest": "1" * 64,
            "beforeBuildId": "2" * 64,
            "beforeElfSha256": "3" * 64,
            "beforeInputSnapshotSha256": "4" * 64,
            "failedBeforeTestRunId": "target-v2-failed",
            "failedBeforeEvidenceId": "5" * 64,
        }
    )
    if revision >= 4:
        outputs.update(
            {
                "diagnosticSessionId": "6" * 32,
                "diagnosticRevision": 7,
                "diagnosticEventHead": "7" * 64,
            }
        )
    if revision >= 6:
        outputs.update(
            {
                "afterBuildId": "8" * 64,
                "afterElfSha256": "9" * 64,
                "afterInputSnapshotSha256": expected_after_snapshot,
                "sourceChangeDeclarationId": "a" * 64,
            }
        )
    intent = source_change_intent
    if intent is None:
        intent = SourceChangeIntent.expanded(
            changes=[
                {
                    "path": "src/main.c",
                    "beforeSha256": "b" * 64,
                    "afterSha256": "c" * 64,
                    "afterSize": 12,
                }
            ],
            before_input_snapshot_sha256="4" * 64,
            expected_after_input_snapshot_sha256=expected_after_snapshot,
        ).to_dict()
    authorization = None
    if revision >= 5:
        authorization = {
            "action": "source-change",
            "actionDigest": "b" * 64,
            "authorized": True,
            "authorizedAtUtc": "2026-08-24T00:00:00.000000Z",
            "diagnosticSessionId": "6" * 32,
            "diagnosticRevision": 7,
            "diagnosticEventHead": "7" * 64,
        }
    payload: dict[str, object] = {
        "schema": PHYSICAL_ATTEMPT_SCHEMA,
        "attemptId": "00000000-0000-4000-8000-000000000001",
        "revision": revision,
        "checkpointId": "0" * 64,
        "previousCheckpointId": None if revision == 0 else "c" * 64,
        "scenarioId": PHYSICAL_SCENARIO_ID,
        "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
        "scenarioDigest": PHYSICAL_SCENARIO_DIGEST,
        "recoveryPolicyDigest": PHYSICAL_RECOVERY_POLICY_DIGEST,
        "workspaceId": "d" * 64,
        "logicalProjectId": "00000000-0000-4000-8000-000000000002",
        "projectOrigin": "keil",
        "executionSource": "physical",
        "physicalTransportEvidence": revision >= 3,
        "status": "COMPLETED" if revision == 7 else "ACTIVE",
        "completedStages": list(PHYSICAL_STAGES[: (revision if revision <= 4 else revision - 1)]),
        "stageOutputs": outputs,
        "sourceChangeAuthorization": authorization,
        "sourceChangeIntent": intent if revision >= 4 else None,
        "openedAtUtc": "2026-08-24T00:00:00.000000Z",
        "deadlineAtUtc": None if revision == 7 else "2026-08-24T00:15:00.000000Z",
        "updatedAtUtc": "2026-08-24T00:00:00.000000Z",
    }
    return _with_checkpoint(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        {"sourceChangeIntent": {
            "schema": "stm32-source-change-intent/1",
            "changes": [{
                "path": "src/main.c",
                "beforeSha256": "b" * 64,
                "afterSha256": "c" * 64,
                "afterSize": 12,
            }],
        }},
        {"sourceChangeIntent": SourceChangeIntent.expanded(
            changes=[{
                "path": "src/main.c",
                "beforeSha256": "b" * 64,
                "afterSha256": "c" * 64,
                "afterSize": 12,
            }],
            before_input_snapshot_sha256="e" * 64,
            expected_after_input_snapshot_sha256="5" * 64,
        ).to_dict()},
    ],
)
def test_physical_attempt_rejects_unexpanded_or_misbound_before_intent(mutation):
    payload = _physical_attempt_payload()
    payload.update(mutation)
    with pytest.raises(AcceptanceRecoveryValidationError):
        PhysicalAcceptanceAttempt.from_value(_with_checkpoint(payload))


def test_physical_attempt_rejects_intent_misbound_to_after_snapshot():
    payload = _physical_attempt_payload(revision=6, expected_after_snapshot="5" * 64)
    payload["sourceChangeIntent"] = SourceChangeIntent.expanded(
        changes=[{
            "path": "src/main.c",
            "beforeSha256": "b" * 64,
            "afterSha256": "c" * 64,
            "afterSize": 12,
        }],
        before_input_snapshot_sha256="4" * 64,
        expected_after_input_snapshot_sha256="e" * 64,
    ).to_dict()
    with pytest.raises(AcceptanceRecoveryValidationError):
        PhysicalAcceptanceAttempt.from_value(_with_checkpoint(payload))


def test_physical_attempt_uses_the_native_run_id_bound():
    payload = _physical_attempt_payload(revision=3)
    payload["stageOutputs"]["failedBeforeTestRunId"] = "target-v2-" + "a" * 300
    parsed = PhysicalAcceptanceAttempt.from_value(_with_checkpoint(payload))
    assert parsed.stage_outputs["failedBeforeTestRunId"] == "target-v2-" + "a" * 300
