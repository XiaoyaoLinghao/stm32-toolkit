from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.mcp_server import (
    ServerRuntime,
    create_server,
    tool_test_host_discover_for_request,
    tool_test_host_run_for_request,
    tool_test_show_for_request,
)
from stm32_toolkit.result import OperationResult


TEST_TOOLS = {
    "stm32_test_host_discover",
    "stm32_test_host_run",
    "stm32_test_show",
}


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


def _schemas(tmp_path: Path) -> dict[str, dict[str, object]]:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    return {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}


def test_testing_tools_have_closed_project_bound_schemas(tmp_path: Path):
    schemas = _schemas(tmp_path)

    assert TEST_TOOLS <= set(schemas)
    assert schemas["stm32_test_host_discover"]["properties"] == {}
    assert schemas["stm32_test_host_discover"].get("required", []) == []
    assert schemas["stm32_test_host_discover"]["additionalProperties"] is False

    run_schema = schemas["stm32_test_host_run"]
    assert set(run_schema["properties"]) == {"inventoryDigest", "caseIds"}
    assert run_schema["required"] == ["inventoryDigest"]
    assert run_schema["properties"]["caseIds"]["default"] == []
    assert run_schema["additionalProperties"] is False

    show_schema = schemas["stm32_test_show"]
    assert set(show_schema["properties"]) == {"runId"}
    assert show_schema["required"] == ["runId"]
    assert show_schema["additionalProperties"] is False

    forbidden = {
        "projectRoot", "project_root", "dataRoot", "data_root", "sessionId",
        "session_id", "workspace", "resultsRoot", "results_root", "evidenceRoot",
    }
    for name in TEST_TOOLS:
        assert not (forbidden & set(schemas[name].get("properties", {})))


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("stm32_test_host_discover", {"unknown": True}),
        ("stm32_test_host_run", {"inventoryDigest": "a" * 64, "unknown": True}),
        ("stm32_test_show", {"runId": "run-1", "unknown": True}),
        ("stm32_test_host_discover", {"projectRoot": "C:/escape"}),
    ],
)
def test_testing_tools_reject_unknown_and_caller_root_fields(
    tmp_path: Path, tool_name: str, arguments: dict[str, object]
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)

    with pytest.raises(Exception):
        asyncio.run(server.call_tool(tool_name, arguments))


@pytest.mark.parametrize(
    ("helper", "workflow_name", "operation", "arguments"),
    [
        (
            tool_test_host_discover_for_request,
            "host_test_discover",
            "test.host.discover",
            {},
        ),
        (
            tool_test_host_run_for_request,
            "host_test_run",
            "test.host.run",
            {"inventory_digest": "a" * 64, "case_ids": ("fails",)},
        ),
        (
            tool_test_show_for_request,
            "test_show",
            "test.show",
            {"run_id": "run-1"},
        ),
    ],
)
def test_testing_request_helpers_check_roots_before_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    calls: list[str] = []
    failure = OperationResult.failure(
        operation, "MCP_ROOTS_UNAVAILABLE", "MCP client roots are unavailable", {}
    ).to_dict()

    async def roots(*_args: object) -> dict[str, object]:
        calls.append("roots")
        return failure

    def workflow(*_args: object, **_kwargs: object) -> object:
        calls.append("workflow")
        raise AssertionError("workflow must not run when roots are rejected")

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow)

    result = asyncio.run(helper(runtime, SimpleNamespace(), **arguments))

    assert result == failure
    assert calls == ["roots"]


@pytest.mark.parametrize(
    ("helper", "workflow_name", "arguments", "expected"),
    [
        (
            tool_test_host_discover_for_request,
            "host_test_discover",
            {},
            {},
        ),
        (
            tool_test_host_run_for_request,
            "host_test_run",
            {"inventory_digest": "a" * 64, "case_ids": ("fails",)},
            {"inventory_digest": "a" * 64, "case_ids": ("fails",)},
        ),
        (
            tool_test_show_for_request,
            "test_show",
            {"run_id": "run-1"},
            {"run_id": "run-1"},
        ),
    ],
)
def test_testing_request_helpers_return_workflow_operation_result_verbatim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper,
    workflow_name: str,
    arguments: dict[str, object],
    expected: dict[str, object],
):
    runtime = _runtime(tmp_path)
    calls: list[dict[str, object]] = []

    async def roots(*_args: object) -> None:
        return None

    def workflow(*args: object, **kwargs: object) -> OperationResult[dict[str, object]]:
        calls.append({"args": args, "kwargs": kwargs})
        return OperationResult.success("test.operation", {"received": expected})

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow)

    result = asyncio.run(helper(runtime, None, **arguments))

    assert result == OperationResult.success(
        "test.operation", {"received": expected}
    ).to_dict()
    assert len(calls) == 1
    assert calls[0]["args"][0].project_root == runtime.project_root
    assert calls[0]["args"][0].data_root == runtime.data_root


def test_registered_testing_tools_are_thin_delegates_and_run_defaults_case_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[str, object]] = []

    async def discover(runtime_arg: object, context: object) -> dict[str, object]:
        calls.append(("discover", (runtime_arg, context)))
        return {"tool": "discover"}

    async def run(
        runtime_arg: object,
        context: object,
        inventory_digest: str,
        case_ids: list[str],
    ) -> dict[str, object]:
        calls.append(("run", (runtime_arg, context, inventory_digest, case_ids)))
        return {"tool": "run"}

    async def show(runtime_arg: object, context: object, run_id: str) -> dict[str, object]:
        calls.append(("show", (runtime_arg, context, run_id)))
        return {"tool": "show"}

    monkeypatch.setattr(mcp_mod, "tool_test_host_discover_for_request", discover)
    monkeypatch.setattr(mcp_mod, "tool_test_host_run_for_request", run)
    monkeypatch.setattr(mcp_mod, "tool_test_show_for_request", show)

    _content, discover_result = asyncio.run(
        server.call_tool("stm32_test_host_discover", {})
    )
    _content, run_result = asyncio.run(
        server.call_tool("stm32_test_host_run", {"inventoryDigest": "a" * 64})
    )
    _content, show_result = asyncio.run(
        server.call_tool("stm32_test_show", {"runId": "run-1"})
    )

    assert discover_result == {"tool": "discover"}
    assert run_result == {"tool": "run"}
    assert show_result == {"tool": "show"}
    assert [name for name, _ in calls] == ["discover", "run", "show"]
    assert calls[1][1][2:] == ("a" * 64, [])


def test_registered_host_run_rejects_repeated_case_ids_before_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)

    async def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("duplicate case IDs must fail schema validation first")

    monkeypatch.setattr(mcp_mod, "tool_test_host_run_for_request", forbidden)

    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_test_host_run",
                {"inventoryDigest": "a" * 64, "caseIds": ["fails", "fails"]},
            )
        )
