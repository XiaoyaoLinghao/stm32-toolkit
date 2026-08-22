from __future__ import annotations

from pathlib import Path

from stm32_toolkit.creation_workflows import CreationPlanWorkflowRequest, plan_creation_workflow


def test_plan_workflow_reports_missing_cubemx_as_plan_blocker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("stm32_toolkit.creation_workflows.discover_tool_support", lambda request: __import__("stm32_toolkit.tool_support", fromlist=["ToolSupportProfile"]).ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ()))
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "mcu", "STM32F429ZITx", "generated", "hal", "c", None))
    assert result.ok is True
    assert result.data["blockers"][0]["code"] == "CUBEMX_MISSING"
    assert result.data["mutated"] is False


def test_workflow_rejects_malformed_input_without_exception_text(tmp_path: Path):
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "bad", "value", "generated", "hal", "c", None))
    assert result.ok is False
    assert result.code == "CREATION_INPUT_INVALID"
    assert "CreationInputError" not in result.message
