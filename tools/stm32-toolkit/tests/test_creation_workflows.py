from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import pytest

from stm32_toolkit.creation_workflows import CreationPlanWorkflowRequest, plan_creation_workflow
from stm32_toolkit.tool_support import SupportProfileError, SupportProfileRequest, discover_tool_support


def test_plan_workflow_reports_missing_cubemx_as_plan_blocker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("stm32_toolkit.creation_workflows.discover_tool_support", lambda request: __import__("stm32_toolkit.tool_support", fromlist=["ToolSupportProfile"]).ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ()))
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "mcu", "STM32F429ZITx", "generated", "hal", "c"))
    assert result.ok is True
    assert result.data["blockers"][0]["code"] == "CUBEMX_MISSING"
    assert result.data["mutated"] is False


def test_workflow_rejects_malformed_input_without_exception_text(tmp_path: Path):
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "bad", "value", "generated", "hal", "c"))
    assert result.ok is False
    assert result.code == "CREATION_INPUT_INVALID"
    assert "CreationInputError" not in result.message


def test_support_profile_rejects_path_outside_data_root(tmp_path: Path):
    outside = tmp_path.parent / "bad-profile.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(SupportProfileError):
        discover_tool_support(
            SupportProfileRequest(profile_path=outside, data_root=tmp_path / "data")
        )


def test_workflow_uses_injected_fixed_clock_for_reproducible_plan(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows
    from stm32_toolkit.tool_support import ToolSupportProfile

    fixed = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(workflows, "_now_factory", lambda: fixed)
    support = ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ())
    monkeypatch.setattr(workflows, "discover_tool_support", lambda request: support)
    request = CreationPlanWorkflowRequest(
        tmp_path,
        tmp_path / "data",
        "session",
        "mcu",
        "STM32F429ZITx",
        "generated",
        "hal",
        "c",
    )
    result = plan_creation_workflow(request)
    assert result.ok is True
    assert result.data["expiresAt"] == "2026-08-23T13:00:00Z"


def test_workflow_environment_failure_is_closed_and_has_no_host_path(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows

    leaked = str(tmp_path / "secret-tool.exe")
    def fail(_request):
        raise SupportProfileError(f"invalid candidate {leaked}")

    monkeypatch.setattr(workflows, "discover_tool_support", fail)
    result = plan_creation_workflow(
        CreationPlanWorkflowRequest(
            tmp_path,
            tmp_path / "data",
            "session",
            "mcu",
            "STM32F429ZITx",
            "generated",
            "hal",
            "c",
        )
    )
    assert result.ok is False
    assert result.code == "CREATION_ENVIRONMENT_INVALID"
    assert leaked not in result.message
    assert leaked not in str(result.details)
