from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from stm32_toolkit.acceptance.model import REQUIRED_STAGES
from stm32_toolkit.acceptance.recovery import (
    AcceptanceAttempt,
    AcceptanceRecoveryPolicy,
    AcceptanceRecoveryValidationError,
    CUBEMX_PHYSICAL_ATTEMPT_SCHEMA,
    CUBEMX_PHYSICAL_RECOVERY_POLICY_DIGEST,
    CUBEMX_PHYSICAL_RECOVERY_POLICY_SCHEMA,
    CUBEMX_PHYSICAL_SCENARIO_DIGEST,
    CUBEMX_PHYSICAL_SCENARIO_ID,
    CUBEMX_PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_RECOVERY_POLICY_DIGEST,
    PHYSICAL_SCENARIO_DIGEST,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_STAGE_OUTPUT_KEYS,
    PHYSICAL_STAGES,
    PhysicalAcceptanceAttempt,
    PhysicalAcceptanceRecoveryPolicy,
    SourceChangeIntent,
    acceptance_recovery_policy,
    cubemx_physical_acceptance_recovery_policy,
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


def _v1_revision(revision: int) -> dict[str, object]:
    payload = _revision_zero(
        revision=revision,
        previousCheckpointId="f" * 64,
        completedStages=list(REQUIRED_STAGES[:revision]),
    )
    outputs = dict(payload["stageOutputs"])
    if revision >= 1:
        outputs["projectModelDigest"] = "1" * 64
    if revision >= 2:
        outputs.update(
            {
                "beforeBuildId": "2" * 64,
                "beforeElfSha256": "3" * 64,
                "beforeInputSnapshotSha256": "4" * 64,
            }
        )
    if revision >= 3:
        outputs.update(
            {
                "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000003",
                "failedBeforeEvidenceId": "5" * 64,
            }
        )
    payload["stageOutputs"] = outputs
    return _with_checkpoint(payload)


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


@pytest.mark.parametrize("mutation", ["stages-object", "stages-string", "missing-output"])
def test_v1_attempt_decode_rejects_non_json_stage_shapes_without_mutation(mutation: str):
    payload = _revision_zero()
    if mutation == "stages-object":
        payload["completedStages"] = {"project-materialized": True}
    elif mutation == "stages-string":
        payload["completedStages"] = "project-materialized"
    else:
        payload["stageOutputs"].pop("projectModelDigest")
    payload = _with_checkpoint(payload)
    before = deepcopy(payload)

    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        AcceptanceAttempt.from_value(payload)

    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert payload == before


@pytest.mark.parametrize(
    ("revision", "field", "value"),
    [
        (2, "failedBeforeTestRunId", "00000000-0000-4000-8000-000000000003"),
        (3, "beforeBuildId", None),
    ],
)
def test_v1_attempt_decode_rejects_stage_outputs_outside_exact_prefix(
    revision: int, field: str, value: object,
):
    payload = _v1_revision(revision)
    payload["stageOutputs"][field] = value
    payload = _with_checkpoint(payload)
    before = deepcopy(payload)

    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        AcceptanceAttempt.from_value(payload)

    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert payload == before


def test_v1_attempt_accepts_arbitrary_diagnostic_bits_only_in_grouped_wire_form():
    grouped = "b9e8a8ae-0a2f-a22d-66d7-d85946bf9eaf"
    payload = _software_revision_wire(4)
    payload["stageOutputs"]["diagnosticSessionId"] = grouped
    payload = _with_checkpoint(payload)
    assert AcceptanceAttempt.from_value(payload).to_dict() == payload

    compact = deepcopy(payload)
    compact["stageOutputs"]["diagnosticSessionId"] = grouped.replace("-", "")
    compact = _with_checkpoint(compact)
    with pytest.raises(AcceptanceRecoveryValidationError):
        AcceptanceAttempt.from_value(compact)


def test_physical_policy_and_source_intent_are_frozen_and_round_trip():
    policy = physical_acceptance_recovery_policy()
    assert policy.schema == "stm32-acceptance-recovery-policy/2"
    assert policy.attempt_schema == PHYSICAL_ATTEMPT_SCHEMA
    assert policy.scenario_id == PHYSICAL_SCENARIO_ID
    assert policy.scenario_version == PHYSICAL_SCENARIO_VERSION
    assert policy.scenario_digest == PHYSICAL_SCENARIO_DIGEST
    assert policy.digest == PHYSICAL_RECOVERY_POLICY_DIGEST
    assert PHYSICAL_SCENARIO_DIGEST == "a66a134d230814752fe006e68fd64c2e6a75ab7680b3e1001269465c30fc325a"
    assert PHYSICAL_RECOVERY_POLICY_DIGEST == "46ffe12c4d0ccd3012b9861b68289a16853272c43557bf2cb0ae0e13ae20c6c7"
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


def test_cubemx_physical_policy_and_revision_zero_round_trip_without_rewriting_a():
    policy = cubemx_physical_acceptance_recovery_policy()
    assert policy.to_dict() == {
        "schema": CUBEMX_PHYSICAL_RECOVERY_POLICY_SCHEMA,
        "attemptSchema": CUBEMX_PHYSICAL_ATTEMPT_SCHEMA,
        "scenarioId": CUBEMX_PHYSICAL_SCENARIO_ID,
        "scenarioVersion": CUBEMX_PHYSICAL_SCENARIO_VERSION,
        "scenarioDigest": CUBEMX_PHYSICAL_SCENARIO_DIGEST,
        "stageTimeoutSeconds": {
            "project-materialized": 60,
            "firmware-built-before": 900,
            "target-failure-observed": 300,
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
                "reason": "recovery-adapter-no-hardware",
            },
        },
        "physicalTransportEvidence": True,
    }
    assert policy.digest == CUBEMX_PHYSICAL_RECOVERY_POLICY_DIGEST

    payload: dict[str, object] = {
        "schema": CUBEMX_PHYSICAL_ATTEMPT_SCHEMA,
        "attemptId": "00000000-0000-4000-8000-000000000011",
        "revision": 0,
        "checkpointId": "0" * 64,
        "previousCheckpointId": None,
        "scenarioId": CUBEMX_PHYSICAL_SCENARIO_ID,
        "scenarioVersion": CUBEMX_PHYSICAL_SCENARIO_VERSION,
        "scenarioDigest": CUBEMX_PHYSICAL_SCENARIO_DIGEST,
        "recoveryPolicyDigest": CUBEMX_PHYSICAL_RECOVERY_POLICY_DIGEST,
        "workspaceId": "d" * 64,
        "logicalProjectId": "00000000-0000-4000-8000-000000000012",
        "projectOrigin": "cubemx",
        "executionSource": "physical",
        "physicalTransportEvidence": False,
        "status": "ACTIVE",
        "completedStages": [],
        "stageOutputs": {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS},
        "sourceChangeAuthorization": None,
        "sourceChangeIntent": None,
        "openedAtUtc": "2026-08-24T00:00:00.000000Z",
        "deadlineAtUtc": "2026-08-24T00:01:00.000000Z",
        "updatedAtUtc": "2026-08-24T00:00:00.000000Z",
    }
    payload = _with_checkpoint(payload)
    parsed = PhysicalAcceptanceAttempt.from_value(payload)
    assert parsed.to_dict() == payload

    for mutation in (
        {"projectOrigin": "keil"},
        {"scenarioId": PHYSICAL_SCENARIO_ID},
        {"schema": "stm32-acceptance-attempt/2"},
    ):
        changed = dict(payload)
        changed.update(mutation)
        with pytest.raises(AcceptanceRecoveryValidationError):
            PhysicalAcceptanceAttempt.from_value(_with_checkpoint(changed))


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


@pytest.mark.parametrize("mutation", ["partial-intent", "missing-after-output"])
def test_physical_attempt_decode_rejects_partial_intent_and_unavailable_outputs(
    mutation: str,
):
    payload = _physical_attempt_payload(revision=6)
    if mutation == "partial-intent":
        intent = dict(payload["sourceChangeIntent"])
        intent.pop("intentDigest")
        payload["sourceChangeIntent"] = intent
    else:
        payload["stageOutputs"]["afterInputSnapshotSha256"] = None
    payload = _with_checkpoint(payload)
    before = deepcopy(payload)

    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        PhysicalAcceptanceAttempt.from_value(payload)

    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert payload == before


@pytest.mark.parametrize("case_name", ["duplicate-paths", "non-lexical-paths", "size-limit", "tampered-digest"])
def test_source_change_intent_decode_rejects_unpublished_wire_conditions(case_name: str):
    change = {
        "path": "src/main.c",
        "beforeSha256": "a" * 64,
        "afterSha256": "b" * 64,
        "afterSize": 12,
    }
    if case_name == "duplicate-paths":
        value: dict[str, object] = {
            "schema": "stm32-source-change-intent/1",
            "changes": [change, {**change, "beforeSha256": "c" * 64, "afterSha256": "d" * 64}],
        }
    elif case_name == "non-lexical-paths":
        value = {
            "schema": "stm32-source-change-intent/1",
            "changes": [change, {**change, "path": "src/z.c", "beforeSha256": "c" * 64, "afterSha256": "d" * 64}],
        }
        value["changes"] = [{**value["changes"][1]}, {**value["changes"][0]}]
    elif case_name == "size-limit":
        value = {
            "schema": "stm32-source-change-intent/1",
            "changes": [{**change, "afterSize": 8 * 1024 * 1024 + 1}],
        }
    else:
        value = SourceChangeIntent.expanded(
            changes=[change],
            before_input_snapshot_sha256="c" * 64,
            expected_after_input_snapshot_sha256="d" * 64,
        ).to_dict()
        value["intentDigest"] = "0" * 64
    before = deepcopy(value)

    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        SourceChangeIntent.from_value(value)

    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert value == before


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


def _software_revision_wire(revision: int) -> dict[str, object]:
    payload = _revision_zero(
        revision=revision,
        previousCheckpointId=None if revision == 0 else "f" * 64,
        completedStages=list(REQUIRED_STAGES[: revision if revision <= 4 else revision - 1]),
        status="COMPLETED" if revision == 7 else "ACTIVE",
        deadlineAtUtc=None if revision == 7 else "2026-08-24T00:15:00.000000Z",
    )
    outputs = dict(payload["stageOutputs"])
    if revision >= 1:
        outputs["projectModelDigest"] = "1" * 64
    if revision >= 2:
        outputs.update(
            {
                "beforeBuildId": "2" * 64,
                "beforeElfSha256": "3" * 64,
                "beforeInputSnapshotSha256": "4" * 64,
            }
        )
    if revision >= 3:
        outputs.update(
            {
                "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000003",
                "failedBeforeEvidenceId": "5" * 64,
            }
        )
    if revision >= 4:
        outputs.update(
            {
                "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
                "diagnosticRevision": 7,
                "diagnosticEventHead": "7" * 64,
            }
        )
    if revision >= 6:
        outputs.update(
            {
                "afterBuildId": "8" * 64,
                "afterElfSha256": "9" * 64,
                "afterInputSnapshotSha256": "a" * 64,
                "sourceChangeDeclarationId": "b" * 64,
            }
        )
    if revision >= 7:
        outputs["acceptanceRecordId"] = "00000000-0000-4000-8000-000000000005"
    payload["stageOutputs"] = outputs
    payload["sourceChangeAuthorization"] = None
    if revision >= 5:
        payload["sourceChangeAuthorization"] = {
            "action": "source-change",
            "actionDigest": "c" * 64,
            "authorized": True,
            "authorizedAtUtc": "2026-08-24T00:00:00.000000Z",
            "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
            "diagnosticRevision": 7,
            "diagnosticEventHead": "7" * 64,
        }
    return _with_checkpoint(payload)


def _valid_physical_wire(revision: int) -> dict[str, object]:
    if revision < 0 or revision > 7:
        raise ValueError("revision must be in the physical range")
    outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    if revision >= 1:
        outputs["projectModelDigest"] = "1" * 64
    if revision >= 2:
        outputs.update(
            {
                "beforeBuildId": "2" * 64,
                "beforeElfSha256": "3" * 64,
                "beforeInputSnapshotSha256": "4" * 64,
            }
        )
    if revision >= 3:
        outputs.update(
            {
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
                "afterInputSnapshotSha256": "a" * 64,
                "sourceChangeDeclarationId": "b" * 64,
            }
        )
    if revision >= 7:
        outputs.update(
            {
                "fixedAfterTestRunId": "target-v2-fixed",
                "fixedAfterEvidenceId": "c" * 64,
                "fixVerificationId": "d" * 64,
            }
        )
    intent: dict[str, object] | None = None
    if revision >= 4:
        intent = SourceChangeIntent.expanded(
            changes=[
                {
                    "path": "src/main.c",
                    "beforeSha256": "e" * 64,
                    "afterSha256": "f" * 64,
                    "afterSize": 12,
                }
            ],
            before_input_snapshot_sha256="4" * 64,
            expected_after_input_snapshot_sha256="a" * 64,
        ).to_dict()
    authorization: dict[str, object] | None = None
    if revision >= 5:
        authorization = {
            "action": "source-change",
            "actionDigest": "1" * 64,
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
        "previousCheckpointId": None if revision == 0 else "2" * 64,
        "scenarioId": PHYSICAL_SCENARIO_ID,
        "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
        "scenarioDigest": PHYSICAL_SCENARIO_DIGEST,
        "recoveryPolicyDigest": PHYSICAL_RECOVERY_POLICY_DIGEST,
        "workspaceId": "3" * 64,
        "logicalProjectId": "00000000-0000-4000-8000-000000000002",
        "projectOrigin": "keil",
        "executionSource": "physical",
        "physicalTransportEvidence": revision >= 3,
        "status": "COMPLETED" if revision == 7 else "ACTIVE",
        "completedStages": list(PHYSICAL_STAGES[: revision if revision <= 4 else revision - 1]),
        "stageOutputs": outputs,
        "sourceChangeAuthorization": authorization,
        "sourceChangeIntent": intent,
        "openedAtUtc": "2026-08-24T00:00:00.000000Z",
        "deadlineAtUtc": None if revision == 7 else "2026-08-24T00:15:00.000000Z",
        "updatedAtUtc": "2026-08-24T00:00:00.000000Z",
    }
    return _with_checkpoint(payload)


def _assert_recovery_refusal(callable_input, value: object, expected: str) -> None:
    before = deepcopy(value)
    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        callable_input()
    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert str(error.value) == expected
    assert value == before


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param("closed", "recovery policy fields are not closed", id="closed-fields"),
        pytest.param("objects", "recovery policy objects are invalid", id="nonmapping-objects"),
        pytest.param("schema", "recovery policy schema is unsupported", id="schema"),
        pytest.param("transport", "physical transport evidence is forbidden", id="transport"),
        pytest.param("timeout", "recovery timeouts are not frozen", id="timeout"),
        pytest.param("actions", "intrusive action policy is not frozen", id="intrusive-actions"),
    ],
)
def test_public_recovery_policy_from_value_boundaries(case_name: str, expected: str) -> None:
    value = acceptance_recovery_policy().to_dict()
    assert AcceptanceRecoveryPolicy.from_value(deepcopy(value)).to_dict() == value
    changed = deepcopy(value)
    if case_name == "closed":
        changed["extra"] = None
    elif case_name == "objects":
        changed["stageTimeoutSeconds"] = None
    elif case_name == "schema":
        changed["schema"] = "other-policy/1"
    elif case_name == "transport":
        changed["physicalTransportEvidence"] = True
    elif case_name == "timeout":
        changed["stageTimeoutSeconds"]["project-materialized"] = 61
    else:
        actions = dict(changed["intrusiveActions"])
        source_change = dict(actions["source-change"])
        source_change["applicable"] = False
        actions["source-change"] = source_change
        changed["intrusiveActions"] = actions
    _assert_recovery_refusal(lambda: AcceptanceRecoveryPolicy.from_value(changed), changed, expected)


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param("nested", "JSON nesting exceeds the recovery limit", id="nested-depth"),
        pytest.param("string-type", "attemptId must be a string", id="string-type"),
        pytest.param("nfc", "attemptId must use NFC", id="non-nfc"),
        pytest.param("size", "attemptId exceeds the string limit", id="string-size"),
        pytest.param("control", "attemptId contains a control character", id="control"),
        pytest.param("diagnostic-revision", "diagnosticRevision must be a non-negative integer or null", id="stage-diagnostic-revision"),
        pytest.param("schema", "attempt schema is unsupported", id="attempt-schema"),
        pytest.param("previous", "revision must link its previous checkpoint", id="missing-previous-checkpoint"),
        pytest.param("scenario", "scenario digest does not match VS08-A definition", id="scenario-digest"),
        pytest.param("policy", "recovery policy digest is not frozen", id="policy-digest"),
        pytest.param("origin", "project origin does not match scenario", id="project-origin"),
        pytest.param("execution", "execution source must be replay", id="execution-source"),
        pytest.param("status", "attempt status is unsupported", id="status"),
        pytest.param("prefix", "completed stages are not the exact ordered prefix", id="stage-prefix"),
        pytest.param("pre-authorization", "source authorization is only valid at revision five or later", id="pre-revision-authorization"),
        pytest.param("missing-authorization", "source authorization is required at revision five or later", id="missing-revision-authorization"),
        pytest.param("authorization-binding", "source authorization must bind the diagnostic checkpoint", id="authorization-binding"),
        pytest.param("completed", "completed revision must be COMPLETED with no deadline", id="completed-revision-shape"),
        pytest.param("deadline", "deadlineAtUtc cannot precede updatedAtUtc", id="deadline-before-update"),
        pytest.param("authorization-time", "authorization cannot follow the revision update", id="authorization-after-update"),
        pytest.param("authorization-closed", "sourceChangeAuthorization fields are not closed", id="authorization-closed"),
        pytest.param("authorization-action", "source change action is unsupported", id="authorization-action"),
        pytest.param("authorization-false", "source change authorization must be true", id="authorization-false"),
        pytest.param("authorization-revision", "diagnosticRevision must be a non-negative integer", id="authorization-revision"),
    ],
)
def test_public_recovery_attempt_from_value_boundaries(case_name: str, expected: str) -> None:
    revision = 0
    if case_name in {"previous", "prefix"}:
        revision = 1
    elif case_name in {"pre-authorization", "diagnostic-revision"}:
        revision = 4 if case_name == "pre-authorization" else 0
    elif case_name in {"missing-authorization", "authorization-binding", "authorization-time", "authorization-closed", "authorization-action", "authorization-false", "authorization-revision"}:
        revision = 5
    elif case_name == "deadline":
        revision = 6
    elif case_name == "completed":
        revision = 7
    payload = _software_revision_wire(revision)
    assert AcceptanceAttempt.from_value(deepcopy(payload)).to_dict() == payload
    if case_name == "nested":
        nested: object = None
        for _ in range(34):
            nested = [nested]
        payload["sourceChangeAuthorization"] = nested
    elif case_name == "string-type":
        payload["attemptId"] = None
    elif case_name == "nfc":
        payload["attemptId"] = "e\u0301"
    elif case_name == "size":
        payload["attemptId"] = "a" * (64 * 1024 + 1)
    elif case_name == "control":
        payload["attemptId"] = "bad\nidentifier"
    elif case_name == "diagnostic-revision":
        outputs = dict(payload["stageOutputs"])
        outputs["diagnosticRevision"] = False
        payload["stageOutputs"] = outputs
    elif case_name == "schema":
        payload["schema"] = "stm32-acceptance-attempt/999"
    elif case_name == "previous":
        payload["previousCheckpointId"] = None
    elif case_name == "scenario":
        payload["scenarioDigest"] = "f" * 64
    elif case_name == "policy":
        payload["recoveryPolicyDigest"] = "f" * 64
    elif case_name == "origin":
        payload["projectOrigin"] = "cubemx"
    elif case_name == "execution":
        payload["executionSource"] = "physical"
    elif case_name == "status":
        payload["status"] = "BROKEN"
    elif case_name == "prefix":
        payload["completedStages"] = ["firmware-built-before"]
    elif case_name == "pre-authorization":
        payload["sourceChangeAuthorization"] = deepcopy(_software_revision_wire(5)["sourceChangeAuthorization"])
    elif case_name == "missing-authorization":
        payload["sourceChangeAuthorization"] = None
    elif case_name == "authorization-binding":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["diagnosticRevision"] = 8
        payload["sourceChangeAuthorization"] = authorization
    elif case_name == "completed":
        payload["status"] = "ACTIVE"
    elif case_name == "deadline":
        payload["deadlineAtUtc"] = "2026-08-23T23:59:59.000000Z"
    elif case_name == "authorization-time":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["authorizedAtUtc"] = "2026-08-24T00:00:01.000000Z"
        payload["sourceChangeAuthorization"] = authorization
    elif case_name == "authorization-closed":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["extra"] = None
        payload["sourceChangeAuthorization"] = authorization
    elif case_name == "authorization-action":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["action"] = "other"
        payload["sourceChangeAuthorization"] = authorization
    elif case_name == "authorization-false":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["authorized"] = False
        payload["sourceChangeAuthorization"] = authorization
    else:
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["diagnosticRevision"] = -1
        payload["sourceChangeAuthorization"] = authorization
    _assert_recovery_refusal(lambda: AcceptanceAttempt.from_value(payload), payload, expected)


def test_public_recovery_constructor_rejects_non_tuple_stages() -> None:
    payload = _software_revision_wire(0)
    attempt = AcceptanceAttempt.from_value(deepcopy(payload))
    before = attempt.to_dict()
    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        replace(attempt, completed_stages=["project-materialized"])
    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert str(error.value) == "completedStages must be a JSON array"
    assert attempt.to_dict() == before


def _source_change_input() -> list[dict[str, object]]:
    return [
        {
            "path": "src/main.c",
            "beforeSha256": "a" * 64,
            "afterSha256": "b" * 64,
            "afterSize": 12,
        }
    ]


def _expanded_source_intent_wire() -> dict[str, object]:
    return SourceChangeIntent.expanded(
        changes=_source_change_input(),
        before_input_snapshot_sha256="c" * 64,
        expected_after_input_snapshot_sha256="d" * 64,
    ).to_dict()


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param("closed-change", "source change fields are not closed", id="closed-change"),
        pytest.param("empty-changes", "source change intent changes are invalid", id="empty-changes"),
        pytest.param("incomplete", "expanded source change intent fields are incomplete", id="incomplete-expansion"),
        pytest.param("new-non-array", "changes must be a JSON array", id="new-non-array"),
        pytest.param("non-object", "source change intent must be an object", id="non-object"),
        pytest.param("expanded-non-array", "changes must be a JSON array", id="expanded-non-array"),
    ],
)
def test_public_source_change_intent_wire_boundaries(case_name: str, expected: str) -> None:
    valid_changes = _source_change_input()
    assert SourceChangeIntent.new(changes=deepcopy(valid_changes)).to_dict() == {
        "schema": "stm32-source-change-intent/1",
        "changes": valid_changes,
    }
    valid_expanded = _expanded_source_intent_wire()
    assert SourceChangeIntent.from_value(deepcopy(valid_expanded)).to_dict() == valid_expanded
    if case_name == "closed-change":
        candidate: object = [{"path": "src/main.c"}]
        callable_input = lambda: SourceChangeIntent.new(changes=candidate)
    elif case_name == "empty-changes":
        candidate = {"schema": "stm32-source-change-intent/1", "changes": []}
        callable_input = lambda: SourceChangeIntent.from_value(candidate)
    elif case_name == "incomplete":
        candidate = deepcopy(valid_expanded)
        candidate["expectedAfterInputSnapshotSha256"] = None
        callable_input = lambda: SourceChangeIntent.from_value(candidate)
    elif case_name == "new-non-array":
        candidate = {"path": "src/main.c"}
        callable_input = lambda: SourceChangeIntent.new(changes=candidate)
    elif case_name == "non-object":
        candidate = None
        callable_input = lambda: SourceChangeIntent.from_value(candidate)
    else:
        candidate = deepcopy(valid_expanded)
        candidate["changes"] = {"path": "src/main.c"}
        callable_input = lambda: SourceChangeIntent.from_value(candidate)
    _assert_recovery_refusal(callable_input, candidate, expected)


def test_public_source_change_intent_constructor_rejects_schema() -> None:
    intent = SourceChangeIntent.expanded(
        changes=_source_change_input(),
        before_input_snapshot_sha256="c" * 64,
        expected_after_input_snapshot_sha256="d" * 64,
    )
    before = intent.to_dict()
    with pytest.raises(AcceptanceRecoveryValidationError) as error:
        replace(intent, schema="stm32-source-change-intent/999")
    assert error.value.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert str(error.value) == "source change intent schema is unsupported"
    assert intent.to_dict() == before


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param("policy-frozen", "physical recovery policy is not frozen", id="policy-frozen"),
        pytest.param("policy-closed", "physical recovery policy fields are not closed", id="policy-closed"),
        pytest.param("policy-objects", "physical recovery policy objects are invalid", id="policy-objects"),
        pytest.param("run-id", "failedBeforeTestRunId must be a native Target run identifier", id="native-run-id"),
        pytest.param("diagnostic-id", "diagnosticSessionId must be a 32-hex Diagnostic session identifier", id="diagnostic-id"),
        pytest.param("stage-closed", "stageOutputs fields are not closed", id="stage-outputs-closed"),
        pytest.param("stage-revision", "diagnosticRevision must be a non-negative integer or null", id="stage-diagnostic-revision"),
        pytest.param("stage-unavailable", "afterBuildId is unavailable at this revision", id="stage-unavailable"),
        pytest.param("authorization-closed", "sourceChangeAuthorization fields are not closed", id="physical-authorization-closed"),
        pytest.param("authorization-action", "source change action is unsupported", id="physical-authorization-action"),
        pytest.param("authorization-false", "source change authorization must be true", id="physical-authorization-false"),
        pytest.param("authorization-revision", "diagnosticRevision must be a non-negative integer", id="physical-authorization-revision"),
        pytest.param("attempt-object", "physical attempt fields are not closed", id="physical-attempt-object"),
        pytest.param("attempt-stages", "completedStages must be a JSON array of strings", id="physical-attempt-stages"),
    ],
)
def test_public_physical_policy_and_wire_boundaries(case_name: str, expected: str) -> None:
    if case_name.startswith("policy-"):
        value = physical_acceptance_recovery_policy().to_dict()
        assert PhysicalAcceptanceRecoveryPolicy.from_value(deepcopy(value)).to_dict() == value
        changed = deepcopy(value)
        if case_name == "policy-frozen":
            changed["scenarioDigest"] = "0" * 64
        elif case_name == "policy-closed":
            changed["extra"] = None
        else:
            changed["stageTimeoutSeconds"] = None
        _assert_recovery_refusal(
            lambda: PhysicalAcceptanceRecoveryPolicy.from_value(changed), changed, expected,
        )
        return

    revision = 5 if case_name.startswith("authorization-") else 4
    if case_name in {"run-id", "stage-unavailable"}:
        revision = 4 if case_name == "stage-unavailable" else 3
    payload = _valid_physical_wire(revision)
    assert PhysicalAcceptanceAttempt.from_value(deepcopy(payload)).to_dict() == payload
    candidate: object = payload
    if case_name == "run-id":
        payload["stageOutputs"]["failedBeforeTestRunId"] = "not a native run"
    elif case_name == "diagnostic-id":
        payload["stageOutputs"]["diagnosticSessionId"] = "g" * 32
    elif case_name == "stage-closed":
        payload["stageOutputs"] = None
    elif case_name == "stage-revision":
        payload["stageOutputs"]["diagnosticRevision"] = False
    elif case_name == "stage-unavailable":
        payload["stageOutputs"]["afterBuildId"] = "8" * 64
    elif case_name == "authorization-closed":
        payload["sourceChangeAuthorization"]["extra"] = None
    elif case_name == "authorization-action":
        payload["sourceChangeAuthorization"]["action"] = "other"
    elif case_name == "authorization-false":
        payload["sourceChangeAuthorization"]["authorized"] = False
    elif case_name == "authorization-revision":
        payload["sourceChangeAuthorization"]["diagnosticRevision"] = -1
    elif case_name == "attempt-object":
        candidate = None
    else:
        payload["completedStages"] = "not-an-array"
    _assert_recovery_refusal(lambda: PhysicalAcceptanceAttempt.from_value(candidate), candidate, expected)


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        pytest.param("range", "revision must be an integer from 0 through 7", id="revision-range"),
        pytest.param("rev0-predecessor", "revision zero cannot link a previous checkpoint", id="rev0-predecessor"),
        pytest.param("rev1-predecessor", "revision must link its previous checkpoint", id="rev1-predecessor"),
        pytest.param("execution", "physical recovery execution source is frozen", id="execution-source"),
        pytest.param("transport", "physical transport evidence has an invalid revision profile", id="transport-profile"),
        pytest.param("status", "attempt status is unsupported", id="status"),
        pytest.param("prefix", "completed stages are not the exact ordered prefix", id="stage-prefix"),
        pytest.param("pre-intent", "source change intent is only valid at revision four or later", id="pre-revision-intent"),
        pytest.param("missing-intent", "source change intent is required at revision four or later", id="missing-revision-intent"),
        pytest.param("pre-authorization", "source authorization is only valid at revision five or later", id="pre-revision-authorization"),
        pytest.param("missing-authorization", "source authorization is required at revision five or later", id="missing-revision-authorization"),
        pytest.param("authorization-binding", "source authorization must bind the diagnostic checkpoint", id="authorization-binding"),
        pytest.param("updated-before-opened", "updatedAtUtc cannot precede openedAtUtc", id="updated-before-opened"),
        pytest.param("completed-shape", "completed revision must be COMPLETED with no deadline", id="completed-revision-shape"),
        pytest.param("incomplete-shape", "incomplete revision must be ACTIVE with a deadline", id="incomplete-revision-shape"),
        pytest.param("deadline", "deadlineAtUtc cannot precede updatedAtUtc", id="deadline-before-update"),
        pytest.param("authorization-time", "authorization cannot follow the revision update", id="authorization-after-update"),
        pytest.param("checkpoint", "checkpointId does not match canonical snapshot", id="checkpoint-mismatch"),
    ],
)
def test_public_physical_attempt_semantic_boundaries(case_name: str, expected: str) -> None:
    revision = 4
    if case_name == "rev0-predecessor":
        revision = 0
    elif case_name == "rev1-predecessor":
        revision = 1
    elif case_name == "pre-intent":
        revision = 3
    elif case_name in {"missing-authorization", "authorization-binding", "authorization-time"}:
        revision = 5
    elif case_name == "completed-shape":
        revision = 7
    payload = _valid_physical_wire(revision)
    assert PhysicalAcceptanceAttempt.from_value(deepcopy(payload)).to_dict() == payload
    if case_name == "range":
        payload["revision"] = 8
    elif case_name == "rev0-predecessor":
        payload["previousCheckpointId"] = "1" * 64
    elif case_name == "rev1-predecessor":
        payload["previousCheckpointId"] = None
    elif case_name == "execution":
        payload["executionSource"] = "replay"
    elif case_name == "transport":
        payload["physicalTransportEvidence"] = False
    elif case_name == "status":
        payload["status"] = "BROKEN"
    elif case_name == "prefix":
        payload["completedStages"] = ["firmware-built-before"]
    elif case_name == "pre-intent":
        payload["sourceChangeIntent"] = _valid_physical_wire(4)["sourceChangeIntent"]
    elif case_name == "missing-intent":
        payload["sourceChangeIntent"] = None
    elif case_name == "pre-authorization":
        payload = _valid_physical_wire(4)
        payload["sourceChangeAuthorization"] = deepcopy(_valid_physical_wire(5)["sourceChangeAuthorization"])
        candidate = payload
    elif case_name == "missing-authorization":
        payload["sourceChangeAuthorization"] = None
    elif case_name == "authorization-binding":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["diagnosticRevision"] = 8
        payload["sourceChangeAuthorization"] = authorization
    elif case_name == "updated-before-opened":
        payload["updatedAtUtc"] = "2026-08-23T23:59:59.000000Z"
    elif case_name == "completed-shape":
        payload["status"] = "ACTIVE"
    elif case_name == "incomplete-shape":
        payload["status"] = "COMPLETED"
    elif case_name == "deadline":
        payload["updatedAtUtc"] = "2026-08-24T00:05:00.000000Z"
        payload["deadlineAtUtc"] = "2026-08-24T00:04:00.000000Z"
    elif case_name == "authorization-time":
        authorization = dict(payload["sourceChangeAuthorization"])
        authorization["authorizedAtUtc"] = "2026-08-24T00:00:01.000000Z"
        payload["sourceChangeAuthorization"] = authorization
    else:
        payload["checkpointId"] = "0" * 64
    _assert_recovery_refusal(lambda: PhysicalAcceptanceAttempt.from_value(payload), payload, expected)
