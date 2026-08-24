from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

from stm32_toolkit.acceptance.model import (
    AcceptanceRecord,
    AcceptanceScenario,
    AcceptanceValidationError,
    REQUIRED_STAGES,
    describe_scenario,
)
from stm32_toolkit.evidence import canonical_json_bytes


def acceptance_scenario(scenario_id: str, scenario_version: str) -> AcceptanceScenario:
    return describe_scenario(scenario_id, scenario_version)


def test_version_one_definitions_are_closed_digest_bound_and_software_only():
    legacy = acceptance_scenario("legacy-keil-migration", "1")
    cubemx = acceptance_scenario("new-cubemx-project", "1")
    assert legacy.to_dict() == {
        "schema": "stm32-acceptance-scenario/1",
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "projectOrigin": "keil",
        "executionProfile": "software-replay",
        "requiredStages": [
            "project-materialized", "firmware-built-before",
            "target-failure-replayed", "diagnosis-completed",
            "firmware-built-after", "target-fix-verified",
        ],
        "physicalTransportEvidence": False,
    }
    assert cubemx.project_origin == "cubemx"
    assert cubemx.scenario_digest == "5650cf942b41f7e6d281cdd836f5ff7320434557998906065c133830701402b3"


@pytest.mark.parametrize("mutation", [
    {"extra": True},
    {"scenarioVersion": "2"},
    {"physicalTransportEvidence": True},
])
def test_scenario_model_rejects_noncontract_input(mutation):
    payload = {
        "schema": "stm32-acceptance-scenario/1",
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "projectOrigin": "keil",
        "executionProfile": "software-replay",
        "requiredStages": list(REQUIRED_STAGES),
        "physicalTransportEvidence": False,
    }
    payload.update(mutation)
    with pytest.raises(AcceptanceValidationError):
        AcceptanceScenario.from_value(payload)


def test_scenario_model_rejects_tuple_json_and_digest_mutation():
    payload = acceptance_scenario("legacy-keil-migration", "1").to_dict()
    payload["requiredStages"] = tuple(payload["requiredStages"])
    with pytest.raises(AcceptanceValidationError):
        AcceptanceScenario.from_value(payload)

    payload = acceptance_scenario("legacy-keil-migration", "1").to_dict()
    payload["scenarioDigest"] = "0" * 64
    with pytest.raises(AcceptanceValidationError):
        AcceptanceScenario.from_value(payload)


def _record_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "stm32-acceptance-record/1",
        "recordId": "00000000-0000-4000-8000-000000000001",
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "workspaceId": "a" * 64,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "projectOrigin": "keil",
        "executionSource": "replay",
        "physicalTransportEvidence": False,
        "completedStages": list(REQUIRED_STAGES),
        "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000002",
        "fixedAfterTestRunId": "00000000-0000-4000-8000-000000000003",
        "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
        "fixVerificationId": "b" * 64,
        "failedBeforeEvidenceId": "c" * 64,
        "fixedAfterEvidenceId": "d" * 64,
        "beforeBuildId": "e" * 64,
        "afterBuildId": "f" * 64,
        "beforeElfSha256": "0" * 64,
        "afterElfSha256": "1" * 64,
        "verdict": "SOFTWARE_PASSED",
        "producedAtUtc": "2026-08-24T00:00:00.000000Z",
    }
    payload.update(overrides)
    return payload


def test_record_model_rejects_physical_source_wrong_stage_and_noncanonical_scalars():
    for mutation in (
        {"executionSource": "physical"},
        {"physicalTransportEvidence": True},
        {"verdict": "PHYSICAL_PASSED"},
        {"completedStages": list(reversed(REQUIRED_STAGES))},
        {"recordId": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"workspaceId": "A" * 64},
        {"producedAtUtc": "2026-08-24T00:00:00Z"},
    ):
        with pytest.raises(AcceptanceValidationError):
            AcceptanceRecord.from_value(_record_payload(**mutation))


def test_record_model_requires_exact_closed_fields_and_canonical_digest():
    payload = _record_payload()
    assert AcceptanceRecord.from_value(payload).to_dict() == payload
    with pytest.raises(AcceptanceValidationError):
        AcceptanceRecord.from_value({**payload, "extra": True})
    with pytest.raises(AcceptanceValidationError):
        AcceptanceRecord.from_value({key: value for key, value in payload.items() if key != "verdict"})
    with pytest.raises(AcceptanceValidationError):
        AcceptanceRecord.from_value({**payload, "recordId": UUID(payload["recordId"])})
    with pytest.raises(AcceptanceValidationError):
        AcceptanceRecord.from_value({**payload, "producedAtUtc": datetime.now(timezone.utc)})


def test_digest_is_over_object_without_digest_field():
    scenario = acceptance_scenario("legacy-keil-migration", "1")
    without_digest = scenario.to_dict()
    digest = without_digest.pop("scenarioDigest")
    assert digest == hashlib.sha256(canonical_json_bytes(without_digest)).hexdigest()
