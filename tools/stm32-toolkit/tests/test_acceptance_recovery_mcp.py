from __future__ import annotations

import asyncio
from pathlib import Path

from stm32_toolkit.mcp_server import create_server


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def _tools(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    server = create_server(project, tmp_path / "data", "session-a")
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}, server


def test_recovery_tools_are_five_project_bound_closed_tools(tmp_path: Path):
    tools, _ = _tools(tmp_path)
    names = {
        "stm32_acceptance_attempt_begin",
        "stm32_acceptance_attempt_checkpoint",
        "stm32_acceptance_attempt_authorize_source_change",
        "stm32_acceptance_attempt_show",
        "stm32_acceptance_attempt_resume",
    }
    assert names <= set(tools)
    checkpoint = tools["stm32_acceptance_attempt_checkpoint"].inputSchema
    assert set(checkpoint["properties"]) == {
        "attemptId", "expectedRevision", "stage", "testRunId",
        "diagnosticSessionId", "acceptanceRecordId", "sourceChangeIntent",
        "fixVerificationId",
    }
    assert checkpoint["additionalProperties"] is False
    assert not ({"projectRoot", "dataRoot", "command", "environment", "transport"} & set(checkpoint["properties"]))


def test_recovery_mcp_tools_translate_exact_values_once(monkeypatch, tmp_path: Path):
    import stm32_toolkit.mcp_server as server_module

    calls = []
    monkeypatch.setattr(
        server_module,
        "begin_acceptance_attempt",
        lambda context, **kwargs: calls.append(("begin", context, kwargs))
        or server_module.OperationResult.success("acceptance.attempt.begin", {"attempt": {}}),
    )
    monkeypatch.setattr(
        server_module,
        "checkpoint_acceptance_attempt",
        lambda context, **kwargs: calls.append(("checkpoint", context, kwargs))
        or server_module.OperationResult.success("acceptance.attempt.checkpoint", {"attempt": {}}),
    )
    values = {
        "attemptId": ATTEMPT_ID,
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
    }
    (tmp_path / "project2").mkdir()
    server = create_server(tmp_path / "project2", tmp_path / "data2", "session-a")
    _, result = asyncio.run(server.call_tool("stm32_acceptance_attempt_begin", values))
    assert result["operation"] == "acceptance.attempt.begin"
    values = {
        "attemptId": ATTEMPT_ID,
        "expectedRevision": 2,
        "stage": "target-failure-replayed",
        "testRunId": "00000000-0000-4000-8000-000000000002",
        "diagnosticSessionId": None,
        "acceptanceRecordId": None,
    }
    _, result = asyncio.run(server.call_tool("stm32_acceptance_attempt_checkpoint", values))
    assert result["operation"] == "acceptance.attempt.checkpoint"
    assert calls[0][2] == {
        "attempt_id": ATTEMPT_ID,
        "scenario_id": "legacy-keil-migration",
        "scenario_version": "1",
    }
    assert calls[1][2] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 2,
        "stage": "target-failure-replayed",
        "test_run_id": values["testRunId"],
        "diagnostic_session_id": None,
        "acceptance_record_id": None,
    }
