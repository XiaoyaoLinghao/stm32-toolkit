from __future__ import annotations

import asyncio
from pathlib import Path

from stm32_toolkit.mcp_server import create_server


def _tools(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    server = create_server(project, tmp_path / "data", "session-a")
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def test_acceptance_tools_are_project_bound_and_closed(tmp_path: Path):
    tools = _tools(tmp_path)
    assert {
        "stm32_acceptance_scenario_describe",
        "stm32_acceptance_scenario_record",
        "stm32_acceptance_scenario_show",
    } <= set(tools)
    schema = tools["stm32_acceptance_scenario_record"].inputSchema
    assert set(schema["properties"]) == {
        "recordId", "scenarioId", "scenarioVersion",
        "failedBeforeTestRunId", "fixedAfterTestRunId",
        "diagnosticSessionId",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert not ({"projectRoot", "dataRoot", "command", "environment"} & set(schema["properties"]))


def test_acceptance_mcp_tools_translate_exact_values_once(monkeypatch, tmp_path: Path):
    import stm32_toolkit.mcp_server as server_module

    calls = []
    monkeypatch.setattr(
        server_module,
        "record_acceptance_scenario",
        lambda context, **kwargs: calls.append((context, kwargs))
        or server_module.OperationResult.success("acceptance.scenario.record", {"record": {}}),
    )
    project = tmp_path / "project2"
    project.mkdir()
    record_id = "00000000-0000-4000-8000-000000000001"
    values = {
        "recordId": record_id,
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000002",
        "fixedAfterTestRunId": "00000000-0000-4000-8000-000000000003",
        "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
    }
    _, structured = asyncio.run(
        server_module.create_server(tmp_path / "project2", tmp_path / "data2", "session-a").call_tool(
            "stm32_acceptance_scenario_record", values
        )
    )
    assert structured["operation"] == "acceptance.scenario.record"
    assert len(calls) == 1
    assert calls[0][1] == {
        "record_id": record_id,
        "scenario_id": "legacy-keil-migration",
        "scenario_version": "1",
        "failed_before_test_run_id": values["failedBeforeTestRunId"],
        "fixed_after_test_run_id": values["fixedAfterTestRunId"],
        "diagnostic_session_id": values["diagnosticSessionId"],
    }
