from __future__ import annotations

import hashlib

import pytest

from stm32_toolkit.acceptance.model import REQUIRED_STAGES
from stm32_toolkit.acceptance.recovery import (
    AcceptanceAttempt,
    AcceptanceRecoveryValidationError,
    acceptance_recovery_policy,
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
