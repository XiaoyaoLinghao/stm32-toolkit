from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import pytest
import stm32_toolkit.mcp_server as server_module
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError as PydanticValidationError
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
    describe_scenario = tools["stm32_acceptance_scenario_describe"].inputSchema
    record_scenario = tools["stm32_acceptance_scenario_record"].inputSchema
    attempt_begin = tools["stm32_acceptance_attempt_begin"].inputSchema
    assert "legacy-keil-physical-repair" not in describe_scenario["properties"]["scenarioId"]["enum"]
    assert "legacy-keil-physical-repair" not in record_scenario["properties"]["scenarioId"]["enum"]
    assert "legacy-keil-physical-repair" in attempt_begin["properties"]["scenarioId"]["enum"]
    assert "new-cubemx-physical-repair" not in describe_scenario["properties"]["scenarioId"]["enum"]
    assert "new-cubemx-physical-repair" not in record_scenario["properties"]["scenarioId"]["enum"]
    assert "new-cubemx-physical-repair" in attempt_begin["properties"]["scenarioId"]["enum"]


def test_recovery_mcp_tools_translate_exact_values_once(monkeypatch, tmp_path: Path):
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
    begin_values = {
        "attemptId": ATTEMPT_ID,
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
    }
    (tmp_path / "project2").mkdir()
    server = create_server(tmp_path / "project2", tmp_path / "data2", "session-a")
    _, result = asyncio.run(
        server.call_tool("stm32_acceptance_attempt_begin", begin_values)
    )
    assert result["operation"] == "acceptance.attempt.begin"
    compact_values = {
        "attemptId": ATTEMPT_ID,
        "expectedRevision": 2,
        "stage": "target-failure-replayed",
        "testRunId": "00000000-0000-4000-8000-000000000002",
        "diagnosticSessionId": "b9e8a8ae0a2fa22d66d7d85946bf9eaf",
        "acceptanceRecordId": None,
    }
    _, result = asyncio.run(
        server.call_tool("stm32_acceptance_attempt_checkpoint", compact_values)
    )
    assert result["operation"] == "acceptance.attempt.checkpoint"
    grouped_values = dict(compact_values)
    grouped_values["diagnosticSessionId"] = (
        "b9e8a8ae-0a2f-a22d-66d7-d85946bf9eaf"
    )
    _, result = asyncio.run(
        server.call_tool("stm32_acceptance_attempt_checkpoint", grouped_values)
    )
    assert result["operation"] == "acceptance.attempt.checkpoint"
    assert calls[0][2] == {
        "attempt_id": ATTEMPT_ID,
        "scenario_id": begin_values["scenarioId"],
        "scenario_version": begin_values["scenarioVersion"],
    }
    assert calls[1][2] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 2,
        "stage": "target-failure-replayed",
        "test_run_id": compact_values["testRunId"],
        "diagnostic_session_id": compact_values["diagnosticSessionId"],
        "acceptance_record_id": None,
    }
    assert calls[2][2] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 2,
        "stage": "target-failure-replayed",
        "test_run_id": grouped_values["testRunId"],
        "diagnostic_session_id": grouped_values["diagnosticSessionId"],
        "acceptance_record_id": None,
    }


def _checkpoint_wire() -> dict[str, object]:
    return {
        "attemptId": ATTEMPT_ID,
        "expectedRevision": 2,
        "stage": "target-failure-replayed",
        "testRunId": "00000000-0000-4000-8000-000000000002",
        "diagnosticSessionId": None,
        "acceptanceRecordId": None,
    }


def _source_change_intent_wire() -> dict[str, object]:
    return {
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


def _assert_recovery_context(context: object, project: Path, data: Path) -> None:
    assert isinstance(context, server_module.AcceptanceRecoveryContext)
    assert context.project_root == project
    assert context.data_root == data
    assert context.session_id == "session-a"


def _tree_snapshot(root: Path) -> tuple[tuple[str, bool, bytes | None], ...]:
    return tuple(
        (
            str(path.relative_to(root)),
            path.is_dir(),
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    )


@pytest.mark.parametrize(
    ("case_id", "optional_field"),
    [
        ("checkpoint-source-intent-present", "sourceChangeIntent"),
        ("checkpoint-fix-verification-present", "fixVerificationId"),
    ],
)
def test_checkpoint_optional_public_fields_forward_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_id: str,
    optional_field: str,
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    server = create_server(project, data, "session-a")
    calls: list[tuple[object, dict[str, object]]] = []

    def recorder(context: object, **kwargs: object) -> object:
        calls.append((context, kwargs))
        return server_module.OperationResult.success(
            "acceptance.attempt.checkpoint", {"case": case_id}
        )

    monkeypatch.setattr(server_module, "checkpoint_acceptance_attempt", recorder)
    assert server_module.checkpoint_acceptance_attempt is recorder
    values = _checkpoint_wire()
    if optional_field == "sourceChangeIntent":
        values[optional_field] = _source_change_intent_wire()
    else:
        values[optional_field] = "d" * 64
    before = deepcopy(values)
    project_before = _tree_snapshot(project)
    data_before = _tree_snapshot(data)

    _content, result = asyncio.run(
        server.call_tool("stm32_acceptance_attempt_checkpoint", values)
    )

    assert result == server_module.OperationResult.success(
        "acceptance.attempt.checkpoint", {"case": case_id}
    ).to_dict()
    assert values == before
    assert len(calls) == 1
    context, kwargs = calls[0]
    _assert_recovery_context(context, project, data)
    expected = {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 2,
        "stage": "target-failure-replayed",
        "test_run_id": "00000000-0000-4000-8000-000000000002",
        "diagnostic_session_id": None,
        "acceptance_record_id": None,
    }
    if optional_field == "sourceChangeIntent":
        expected["source_change_intent"] = _source_change_intent_wire()
    else:
        expected["fix_verification_id"] = "d" * 64
    assert kwargs == expected
    assert _tree_snapshot(project) == project_before
    assert _tree_snapshot(data) == data_before


def test_checkpoint_rejects_utf8_path_before_service_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    server = create_server(project, data, "session-a")
    calls: list[tuple[object, dict[str, object]]] = []

    def recorder(context: object, **kwargs: object) -> object:
        calls.append((context, kwargs))
        return server_module.OperationResult.success(
            "acceptance.attempt.checkpoint", {"case": "control"}
        )

    monkeypatch.setattr(server_module, "checkpoint_acceptance_attempt", recorder)
    assert server_module.checkpoint_acceptance_attempt is recorder
    valid = _checkpoint_wire()
    valid["sourceChangeIntent"] = _source_change_intent_wire()
    valid_before = deepcopy(valid)
    project_before = _tree_snapshot(project)
    data_before = _tree_snapshot(data)

    _content, result = asyncio.run(
        server.call_tool("stm32_acceptance_attempt_checkpoint", valid)
    )
    assert result == server_module.OperationResult.success(
        "acceptance.attempt.checkpoint", {"case": "control"}
    ).to_dict()
    assert valid == valid_before
    assert len(calls) == 1

    invalid = deepcopy(valid)
    intent = invalid["sourceChangeIntent"]
    assert isinstance(intent, dict)
    changes = intent["changes"]
    assert isinstance(changes, list)
    changes[0]["path"] = "é" * 4096
    invalid_before = deepcopy(invalid)
    with pytest.raises(
        ToolError,
        match=r"^Error executing tool stm32_acceptance_attempt_checkpoint:",
    ) as error:
        asyncio.run(
            server.call_tool("stm32_acceptance_attempt_checkpoint", invalid)
        )

    assert str(error.value).startswith(
        "Error executing tool stm32_acceptance_attempt_checkpoint:"
    )
    cause = error.value.__cause__
    assert isinstance(cause, PydanticValidationError)
    validation_errors = cause.errors()
    assert len(validation_errors) == 1
    validation_error = validation_errors[0]
    assert validation_error["type"] == "value_error"
    assert validation_error["msg"] == (
        "Value error, path must be a portable project-relative path"
    )
    assert tuple(validation_error["loc"]) == (
        "sourceChangeIntent",
        "changes",
        0,
        "path",
    )

    assert len(calls) == 1
    assert invalid == invalid_before
    assert _tree_snapshot(project) == project_before
    assert _tree_snapshot(data) == data_before
