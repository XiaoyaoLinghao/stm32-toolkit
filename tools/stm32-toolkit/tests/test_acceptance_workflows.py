from __future__ import annotations

from pathlib import Path

import pytest

from stm32_toolkit.acceptance.model import REQUIRED_STAGES
import stm32_toolkit.acceptance.workflows as acceptance_workflows
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    describe_acceptance_scenario,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
from stm32_toolkit.result import OperationResult


def test_describe_is_state_free_and_returns_the_fixed_definition(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    before = tuple(tmp_path.rglob("*"))
    result = describe_acceptance_scenario(context, scenario_id="legacy-keil-migration", scenario_version="1")
    assert result.ok is True
    assert result.operation == "acceptance.scenario.describe"
    assert tuple(result.data["scenario"]["requiredStages"]) == REQUIRED_STAGES
    assert tuple(tmp_path.rglob("*")) == before


@pytest.mark.parametrize(
    ("scenario_id", "scenario_version", "code"),
    [
        ("unknown", "1", "ACCEPTANCE_SCENARIO_UNKNOWN"),
        ("legacy-keil-migration", "2", "ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED"),
    ],
)
def test_describe_rejects_unknown_definition_without_state(
    tmp_path: Path, scenario_id: str, scenario_version: str, code: str
):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = describe_acceptance_scenario(
        context, scenario_id=scenario_id, scenario_version=scenario_version
    )
    assert result.ok is False
    assert result.code == code
    assert not (tmp_path / "data").exists()


def test_record_rejects_malformed_uuid_before_loading_project(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = record_acceptance_scenario(
        context,
        record_id="not-a-uuid",
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id="00000000-0000-4000-8000-000000000002",
        fixed_after_test_run_id="00000000-0000-4000-8000-000000000003",
        diagnostic_session_id="00000000-0000-4000-8000-000000000004",
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_INPUT_INVALID"


def test_show_missing_root_is_typed_and_does_not_create_state(tmp_path: Path):
    context = AcceptanceWorkflowContext(tmp_path / "project", tmp_path / "data", "session-a")
    result = show_acceptance_scenario(
        context, record_id="00000000-0000-4000-8000-000000000001"
    )
    assert result.ok is False
    assert result.code == "ACCEPTANCE_REFERENCE_INVALID"


@pytest.mark.parametrize(
    ("reader_kind", "reader_code", "expected"),
    [
        ("diagnostic", "INCOMPATIBLE_IDENTITY", "ACCEPTANCE_IDENTITY_MISMATCH"),
        ("diagnostic", "DIAGNOSTIC_IDENTITY_MISMATCH", "ACCEPTANCE_IDENTITY_MISMATCH"),
        ("diagnostic", "DIAGNOSTIC_EVIDENCE_MISSING", "ACCEPTANCE_REFERENCE_INVALID"),
        ("diagnostic", "EVIDENCE_INTEGRITY_FAILURE", "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"),
        ("diagnostic_verification", "INCOMPATIBLE_IDENTITY", "ACCEPTANCE_IDENTITY_MISMATCH"),
        ("diagnostic_verification", "DIAGNOSTIC_EVIDENCE_MISSING", "ACCEPTANCE_REFERENCE_INVALID"),
        ("diagnostic_verification", "EVIDENCE_INTEGRITY_FAILURE", "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"),
    ],
    ids=[
        "diagnostic-identity",
        "diagnostic-identity-alias",
        "diagnostic-evidence-missing",
        "diagnostic-integrity",
        "verification-identity",
        "verification-evidence-missing",
        "verification-integrity",
    ],
)
def test_actual_diagnostic_reader_failures_map_to_closed_acceptance_codes(
    reader_kind: str, reader_code: str, expected: str
):
    result = OperationResult.failure(
        "diagnostic.reader", reader_code, "diagnostic reader failure", {}
    )
    assert (
        acceptance_workflows._reader_failure_code(result, reader_kind=reader_kind)
        == expected
    )
