from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.result import OperationResult


DIAGNOSTIC_SESSION_ID = "a" * 32
OPERATION_ID = "diagnostic-operation-1"
RUN_ID = "failed-run-1"
HYPOTHESIS_ID = "b" * 32
PLAN_ID = "c" * 64
STEP_ID = "step-1"
STATEMENT = "clock configuration is inconsistent"
RATIONALE = "the observation matches the hypothesis"
ACTORS = ["user", "tool", "ai-client"]
LIFECYCLE_TOOLS = {
    "stm32_diagnostic_start",
    "stm32_diagnostic_show",
    "stm32_diagnostic_begin",
}
FORBIDDEN_ROOT_FIELDS = {
    "projectRoot",
    "project_root",
    "dataRoot",
    "data_root",
    "sessionId",
    "session_id",
    "workspace",
    "resultsRoot",
    "results_root",
    "evidenceRoot",
}


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


def _schemas(tmp_path: Path) -> dict[str, dict[str, object]]:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    return {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}


def _helper(name: str):
    helper = getattr(mcp_mod, name, None)
    assert callable(helper), f"missing lifecycle request helper: {name}"
    return helper


def test_lifecycle_tools_have_exact_closed_project_bound_schemas(tmp_path: Path):
    schemas = _schemas(tmp_path)

    assert LIFECYCLE_TOOLS <= set(schemas)

    start = schemas["stm32_diagnostic_start"]
    assert set(start["properties"]) == {"operationId", "failedTestRunId", "actor"}
    assert start["required"] == ["operationId", "failedTestRunId"]
    assert start["properties"]["actor"]["default"] == "user"
    assert start["properties"]["actor"]["enum"] == ACTORS

    operation_schema = start["properties"]["operationId"]
    assert operation_schema["pattern"] == r"^[a-z0-9][a-z0-9._-]{0,127}$"
    assert operation_schema["minLength"] == 1
    assert operation_schema["maxLength"] == 128

    run_schema = start["properties"]["failedTestRunId"]
    assert run_schema["pattern"] == r"^[a-z0-9][a-z0-9._-]*$"
    assert run_schema["minLength"] == 1
    assert run_schema["maxLength"] == 65_536

    show = schemas["stm32_diagnostic_show"]
    assert set(show["properties"]) == {"diagnosticSessionId"}
    assert show["required"] == ["diagnosticSessionId"]

    session_schema = show["properties"]["diagnosticSessionId"]
    assert session_schema["pattern"] == r"^[0-9a-f]{32}$"
    assert session_schema["minLength"] == 32
    assert session_schema["maxLength"] == 32

    begin = schemas["stm32_diagnostic_begin"]
    assert set(begin["properties"]) == {
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "actor",
    }
    assert begin["required"] == [
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
    ]
    assert begin["properties"]["actor"]["default"] == "user"
    revision_schema = begin["properties"]["expectedRevision"]
    assert revision_schema["type"] == "integer"
    assert revision_schema["minimum"] == 0
    assert revision_schema["maximum"] == 10_000

    for name in LIFECYCLE_TOOLS:
        assert schemas[name]["additionalProperties"] is False
        assert not (FORBIDDEN_ROOT_FIELDS & set(schemas[name]["properties"]))


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_start_for_request",
            "diagnostic_start",
            "diagnostic.start",
            {
                "operation_id": OPERATION_ID,
                "failed_test_run_id": RUN_ID,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_show_for_request",
            "diagnostic_show",
            "diagnostic.show",
            {"diagnostic_session_id": DIAGNOSTIC_SESSION_ID},
        ),
        (
            "tool_diagnostic_begin_for_request",
            "diagnostic_begin",
            "diagnostic.begin",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "actor": "tool",
            },
        ),
    ],
)
def test_lifecycle_request_helpers_short_circuit_on_root_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    calls: list[str] = []
    failure = OperationResult.failure(
        operation,
        "MCP_ROOTS_UNAVAILABLE",
        "MCP client roots are unavailable",
        {},
    ).to_dict()

    async def roots(*_args: object) -> dict[str, object]:
        calls.append("roots")
        return failure

    def workflow(*_args: object, **_kwargs: object) -> object:
        calls.append("workflow")
        raise AssertionError("workflow must not run after root failure")

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow, raising=False)

    result = asyncio.run(helper(runtime, SimpleNamespace(), **arguments))

    assert result == failure
    assert calls == ["roots"]


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_start_for_request",
            "diagnostic_start",
            "diagnostic.start",
            {
                "operation_id": OPERATION_ID,
                "failed_test_run_id": RUN_ID,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_show_for_request",
            "diagnostic_show",
            "diagnostic.show",
            {"diagnostic_session_id": DIAGNOSTIC_SESSION_ID},
        ),
        (
            "tool_diagnostic_begin_for_request",
            "diagnostic_begin",
            "diagnostic.begin",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "actor": "tool",
            },
        ),
    ],
)
def test_lifecycle_request_helpers_call_one_workflow_with_bound_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    calls: list[object] = []

    async def roots(*_args: object) -> None:
        calls.append("roots")
        return None

    def workflow(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return OperationResult.success(operation, {"received": arguments})

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow, raising=False)

    result = asyncio.run(helper(runtime, None, **arguments))

    assert result == OperationResult.success(
        operation, {"received": arguments}
    ).to_dict()
    assert len(calls) == 2
    assert calls[0] == "roots"
    workflow_args, workflow_kwargs = calls[1]
    assert len(workflow_args) == 1
    assert workflow_args[0].project_root == runtime.project_root
    assert workflow_args[0].data_root == runtime.data_root
    assert workflow_args[0].session_id == runtime.session_id
    assert workflow_kwargs == arguments
    assert workflow_kwargs is not arguments


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_start_for_request",
            "diagnostic_start",
            "diagnostic.start",
            {
                "operation_id": OPERATION_ID,
                "failed_test_run_id": RUN_ID,
            },
        ),
        (
            "tool_diagnostic_show_for_request",
            "diagnostic_show",
            "diagnostic.show",
            {"diagnostic_session_id": DIAGNOSTIC_SESSION_ID},
        ),
        (
            "tool_diagnostic_begin_for_request",
            "diagnostic_begin",
            "diagnostic.begin",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
            },
        ),
    ],
)
def test_lifecycle_request_helpers_preserve_domain_failure_dictionary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    failure = OperationResult.failure(
        operation,
        "DIAGNOSTIC_INVALID_TRANSITION",
        "stable domain message",
        {"revision": 4},
    )

    async def roots(*_args: object) -> None:
        return None

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(
        mcp_mod,
        workflow_name,
        lambda *_args, **_kwargs: failure,
        raising=False,
    )

    assert asyncio.run(helper(runtime, None, **arguments)) == failure.to_dict()


def test_registered_lifecycle_tools_are_thin_delegates_with_actor_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[str, tuple[object, ...]]] = []

    async def start(*args: object) -> dict[str, object]:
        calls.append(("start", args))
        return {"tool": "start"}

    async def show(*args: object) -> dict[str, object]:
        calls.append(("show", args))
        return {"tool": "show"}

    async def begin(*args: object) -> dict[str, object]:
        calls.append(("begin", args))
        return {"tool": "begin"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_start_for_request", start)
    monkeypatch.setattr(mcp_mod, "tool_diagnostic_show_for_request", show)
    monkeypatch.setattr(mcp_mod, "tool_diagnostic_begin_for_request", begin)

    _content, start_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_start",
            {"operationId": OPERATION_ID, "failedTestRunId": RUN_ID},
        )
    )
    _content, show_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_show",
            {"diagnosticSessionId": DIAGNOSTIC_SESSION_ID},
        )
    )
    _content, begin_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "actor": "ai-client",
            },
        )
    )

    assert start_result == {"tool": "start"}
    assert show_result == {"tool": "show"}
    assert begin_result == {"tool": "begin"}
    assert [name for name, _args in calls] == ["start", "show", "begin"]
    assert calls[0][1][0] == runtime
    assert calls[0][1][2:] == (OPERATION_ID, RUN_ID, "user")
    assert calls[1][1][0] == runtime
    assert calls[1][1][2:] == (DIAGNOSTIC_SESSION_ID,)
    assert calls[2][1][0] == runtime
    assert calls[2][1][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        4,
        "ai-client",
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments", "helper_name"),
    [
        (
            "stm32_diagnostic_start",
            {"operationId": "Bad", "failedTestRunId": RUN_ID},
            "tool_diagnostic_start_for_request",
        ),
        (
            "stm32_diagnostic_start",
            {"operationId": OPERATION_ID, "failedTestRunId": "A"},
            "tool_diagnostic_start_for_request",
        ),
        (
            "stm32_diagnostic_start",
            {"operationId": OPERATION_ID, "failedTestRunId": "a" * 65_537},
            "tool_diagnostic_start_for_request",
        ),
        (
            "stm32_diagnostic_start",
            {
                "operationId": OPERATION_ID,
                "failedTestRunId": RUN_ID,
                "actor": "robot",
            },
            "tool_diagnostic_start_for_request",
        ),
        (
            "stm32_diagnostic_show",
            {"diagnosticSessionId": "A" * 32},
            "tool_diagnostic_show_for_request",
        ),
        (
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": -1,
            },
            "tool_diagnostic_begin_for_request",
        ),
        (
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 10_001,
            },
            "tool_diagnostic_begin_for_request",
        ),
        (
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": True,
            },
            "tool_diagnostic_begin_for_request",
        ),
        (
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "actor": "robot",
            },
            "tool_diagnostic_begin_for_request",
        ),
        (
            "stm32_diagnostic_begin",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "unknown": True,
            },
            "tool_diagnostic_begin_for_request",
        ),
        (
            "stm32_diagnostic_show",
            {"diagnosticSessionId": DIAGNOSTIC_SESSION_ID, "projectRoot": "C:/escape"},
            "tool_diagnostic_show_for_request",
        ),
    ],
)
def test_registered_lifecycle_tools_reject_invalid_input_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, object],
    helper_name: str,
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(True)
        return {"unexpected": True}

    monkeypatch.setattr(mcp_mod, helper_name, forbidden, raising=False)

    with pytest.raises(Exception):
        asyncio.run(server.call_tool(tool_name, arguments))
    assert calls == []


@pytest.mark.parametrize(
    ("tool_name", "arguments", "helper_name"),
    [
        (
            "stm32_diagnostic_start",
            {"operationId": OPERATION_ID, "failedTestRunId": RUN_ID, "unknown": True},
            "tool_diagnostic_start_for_request",
        ),
        (
            "stm32_diagnostic_show",
            {"diagnosticSessionId": DIAGNOSTIC_SESSION_ID, "unknown": True},
            "tool_diagnostic_show_for_request",
        ),
    ],
)
def test_registered_lifecycle_tools_reject_unknown_fields_without_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, object],
    helper_name: str,
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(True)
        return {"unexpected": True}

    monkeypatch.setattr(mcp_mod, helper_name, forbidden, raising=False)

    with pytest.raises(Exception):
        asyncio.run(server.call_tool(tool_name, arguments))
    assert calls == []


def test_hypothesis_tools_have_exact_closed_project_bound_schemas(tmp_path: Path):
    schemas = _schemas(tmp_path)
    hypothesis_tools = {
        "stm32_diagnostic_hypothesis_add",
        "stm32_diagnostic_hypothesis_assess",
    }

    assert hypothesis_tools <= set(schemas)

    add = schemas["stm32_diagnostic_hypothesis_add"]
    assert set(add["properties"]) == {
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "statement",
        "actor",
    }
    assert add["required"] == [
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "statement",
    ]
    assert add["properties"]["actor"]["default"] == "user"
    assert add["properties"]["actor"]["enum"] == ACTORS
    assert add["properties"]["statement"]["minLength"] == 1
    assert add["properties"]["statement"]["maxLength"] == 65_536

    assess = schemas["stm32_diagnostic_hypothesis_assess"]
    assert set(assess["properties"]) == {
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "hypothesisId",
        "planId",
        "stepId",
        "polarity",
        "rationale",
        "actor",
    }
    assert assess["required"] == [
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "hypothesisId",
        "planId",
        "stepId",
        "polarity",
        "rationale",
    ]
    assert assess["properties"]["actor"]["default"] == "user"
    assert assess["properties"]["actor"]["enum"] == ACTORS
    assert assess["properties"]["hypothesisId"]["pattern"] == r"^[0-9a-f]{32}$"
    assert assess["properties"]["hypothesisId"]["minLength"] == 32
    assert assess["properties"]["hypothesisId"]["maxLength"] == 32
    assert assess["properties"]["planId"]["pattern"] == r"^[0-9a-f]{64}$"
    assert assess["properties"]["planId"]["minLength"] == 64
    assert assess["properties"]["planId"]["maxLength"] == 64
    assert assess["properties"]["stepId"]["pattern"] == (
        r"^[a-z0-9][a-z0-9._-]{0,127}$"
    )
    assert assess["properties"]["polarity"]["enum"] == ["supports", "refutes"]
    assert assess["properties"]["rationale"]["minLength"] == 1
    assert assess["properties"]["rationale"]["maxLength"] == 65_536

    for name in hypothesis_tools:
        assert schemas[name]["additionalProperties"] is False
        assert not (FORBIDDEN_ROOT_FIELDS & set(schemas[name]["properties"]))


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_add_hypothesis_for_request",
            "diagnostic_add_hypothesis",
            "diagnostic.hypothesis.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "statement": STATEMENT,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_assess_hypothesis_for_request",
            "diagnostic_assess_hypothesis",
            "diagnostic.hypothesis.assess",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 7,
                "hypothesis_id": HYPOTHESIS_ID,
                "plan_id": PLAN_ID,
                "step_id": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
                "actor": "tool",
            },
        ),
    ],
)
def test_hypothesis_request_helpers_short_circuit_on_root_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    calls: list[str] = []
    failure = OperationResult.failure(
        operation,
        "MCP_ROOTS_UNAVAILABLE",
        "MCP client roots are unavailable",
        {},
    ).to_dict()

    async def roots(*_args: object) -> dict[str, object]:
        calls.append("roots")
        return failure

    def workflow(*_args: object, **_kwargs: object) -> object:
        calls.append("workflow")
        raise AssertionError("workflow must not run after root failure")

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow, raising=False)

    result = asyncio.run(helper(runtime, SimpleNamespace(), **arguments))

    assert result == failure
    assert calls == ["roots"]


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_add_hypothesis_for_request",
            "diagnostic_add_hypothesis",
            "diagnostic.hypothesis.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "statement": STATEMENT,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_assess_hypothesis_for_request",
            "diagnostic_assess_hypothesis",
            "diagnostic.hypothesis.assess",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 7,
                "hypothesis_id": HYPOTHESIS_ID,
                "plan_id": PLAN_ID,
                "step_id": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
                "actor": "tool",
            },
        ),
    ],
)
def test_hypothesis_request_helpers_call_one_workflow_with_bound_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    calls: list[object] = []

    async def roots(*_args: object) -> None:
        calls.append("roots")
        return None

    def workflow(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return OperationResult.success(operation, {"received": arguments})

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, workflow_name, workflow, raising=False)

    result = asyncio.run(helper(runtime, None, **arguments))

    assert result == OperationResult.success(
        operation, {"received": arguments}
    ).to_dict()
    assert len(calls) == 2
    assert calls[0] == "roots"
    workflow_args, workflow_kwargs = calls[1]
    assert len(workflow_args) == 1
    assert workflow_args[0].project_root == runtime.project_root
    assert workflow_args[0].data_root == runtime.data_root
    assert workflow_args[0].session_id == runtime.session_id
    assert workflow_kwargs == arguments
    assert workflow_kwargs is not arguments


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_add_hypothesis_for_request",
            "diagnostic_add_hypothesis",
            "diagnostic.hypothesis.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "statement": STATEMENT,
            },
        ),
        (
            "tool_diagnostic_assess_hypothesis_for_request",
            "diagnostic_assess_hypothesis",
            "diagnostic.hypothesis.assess",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 7,
                "hypothesis_id": HYPOTHESIS_ID,
                "plan_id": PLAN_ID,
                "step_id": STEP_ID,
                "polarity": "refutes",
                "rationale": RATIONALE,
            },
        ),
    ],
)
def test_hypothesis_request_helpers_preserve_domain_failure_dictionary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    helper_name: str,
    workflow_name: str,
    operation: str,
    arguments: dict[str, object],
):
    runtime = _runtime(tmp_path)
    helper = _helper(helper_name)
    failure = OperationResult.failure(
        operation,
        "DIAGNOSTIC_PLAN_INVALID",
        "stable domain message",
        {"revision": 7},
    )

    async def roots(*_args: object) -> None:
        return None

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(
        mcp_mod,
        workflow_name,
        lambda *_args, **_kwargs: failure,
        raising=False,
    )

    assert asyncio.run(helper(runtime, None, **arguments)) == failure.to_dict()


def test_registered_hypothesis_tools_are_thin_delegates_with_actor_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[str, tuple[object, ...]]] = []

    async def add(*args: object) -> dict[str, object]:
        calls.append(("add", args))
        return {"tool": "add"}

    async def assess(*args: object) -> dict[str, object]:
        calls.append(("assess", args))
        return {"tool": "assess"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_hypothesis_for_request", add)
    monkeypatch.setattr(
        mcp_mod, "tool_diagnostic_assess_hypothesis_for_request", assess
    )

    _content, add_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": STATEMENT,
            },
        )
    )
    _content, assess_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "refutes",
                "rationale": RATIONALE,
                "actor": "ai-client",
            },
        )
    )

    assert add_result == {"tool": "add"}
    assert assess_result == {"tool": "assess"}
    assert [name for name, _args in calls] == ["add", "assess"]
    assert calls[0][1][0] == runtime
    assert calls[0][1][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        4,
        STATEMENT,
        "user",
    )
    assert calls[1][1][0] == runtime
    assert calls[1][1][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        7,
        HYPOTHESIS_ID,
        PLAN_ID,
        STEP_ID,
        "refutes",
        RATIONALE,
        "ai-client",
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments", "helper_name"),
    [
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": "Bad",
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": STATEMENT,
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": "A" * 32,
                "expectedRevision": 4,
                "statement": STATEMENT,
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": True,
                "statement": STATEMENT,
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": "",
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": "e\u0301",
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": "a" * 65_537,
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "statement": STATEMENT,
                "actor": "robot",
            },
            "tool_diagnostic_add_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": "A" * 32,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": "b" * 31,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": "C" * 64,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": "Bad",
                "polarity": "supports",
                "rationale": RATIONALE,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "neutral",
                "rationale": RATIONALE,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": "e\u0301",
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": "a" * 65_537,
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
                "actor": "robot",
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
        (
            "stm32_diagnostic_hypothesis_assess",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 7,
                "hypothesisId": HYPOTHESIS_ID,
                "planId": PLAN_ID,
                "stepId": STEP_ID,
                "polarity": "supports",
                "rationale": RATIONALE,
                "projectRoot": "C:/escape",
            },
            "tool_diagnostic_assess_hypothesis_for_request",
        ),
    ],
)
def test_registered_hypothesis_tools_reject_invalid_input_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, object],
    helper_name: str,
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(True)
        return {"unexpected": True}

    monkeypatch.setattr(mcp_mod, helper_name, forbidden, raising=False)

    with pytest.raises(Exception):
        asyncio.run(server.call_tool(tool_name, arguments))
    assert calls == []
