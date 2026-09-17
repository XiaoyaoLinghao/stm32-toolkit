from __future__ import annotations

import asyncio
from copy import deepcopy
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
RUN_STATE_STEP = {
    "step_id": "run-state",
    "selector": {"kind": "run-state"},
    "expected_value": "failed",
    "purpose": "confirm the published run failed",
}
CASE_STATE_STEP = {
    "step_id": "case-state",
    "selector": {"kind": "case-state", "case_id": "case-1"},
    "expected_value": "error",
    "purpose": "confirm the affected case errored",
}
CASE_COUNT_STEP = {
    "step_id": "case-count",
    "selector": {"kind": "case-count", "state": "failed"},
    "expected_value": 1,
    "purpose": "count failed cases in the run",
}
PLAN_STEPS = [RUN_STATE_STEP]
PHYSICAL_MONITOR_REF = {
    "schema": "stm32-monitor-run-ref/2",
    "operation_id": "11111111-1111-4111-8111-111111111111",
    "scenario_role": "failed-before",
    "execution_source": "physical",
    "physical_transport_evidence": True,
    "origin_workspace_id": "a" * 64,
    "import_workspace_id": "a" * 64,
    "logical_project_id": "12345678-1234-5678-1234-567812345678",
    "origin_session_id": "session-a",
    "projected_session_id": "session-a",
    "origin_run_id": "11111111-1111-4111-8111-111111111111",
    "projected_run_id": "11111111-1111-4111-8111-111111111111",
    "target_device": "target",
    "probe_id": "probe",
    "physical_target": "board:t10",
    "build_id": "b" * 64,
    "elf_sha256": "c" * 64,
    "input_snapshot_sha256": "d" * 64,
    "git_head": "e" * 40,
    "git_dirty": False,
    "flash_session_id": "flash",
    "lease_id": "lease",
    "dwarf_sha256": "f" * 64,
    "svd_sha256": None,
    "group_id": "22222222-2222-4222-8222-222222222222",
    "group_revision": 1,
    "start_sequence": 0,
    "end_sequence_exclusive": 2,
    "start_captured_unix_ns": 100,
    "end_captured_unix_ns_exclusive": 102,
    "projected_batch_sha256s": ["0" * 64],
    "transcript_evidence_id": "1" * 64,
    "run_ref_sha256": "2" * 64,
    "source_record_sha256": "3" * 64,
}
PHYSICAL_FACT_STEP = {
    "step_id": "physical-fact",
    "selector": {
        "kind": "physical-monitor-fact/1",
        "continuation_evidence_id": "4" * 64,
        "monitor_ref_evidence_id": "5" * 64,
        "monitor_run_ref": PHYSICAL_MONITOR_REF,
        "selector_kind": "register",
        "selector": "r0",
        "fact": "bit-values-mask",
        "minimum_valid_samples": 2,
        "bit_index": 0,
    },
    "expected_value": 3,
    "purpose": "verify the physical register bit",
}
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
    assert set(start["properties"]) == {
        "operationId",
        "failedTestRunId",
        "actor",
        "failedRunMode",
    }
    assert start["required"] == ["operationId", "failedTestRunId"]
    assert start["properties"]["actor"]["default"] == "user"
    assert start["properties"]["actor"]["enum"] == ACTORS
    assert start["properties"]["failedRunMode"]["default"] == "host"
    assert start["properties"]["failedRunMode"]["enum"] == ["host", "target"]

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


PLAN_TOOLS = {
    "stm32_diagnostic_plan_add",
    "stm32_diagnostic_plan_run",
}


def _resolve_schema(schema: dict[str, object], root: dict[str, object]) -> dict[str, object]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    assert isinstance(reference, str)
    prefix = "#/$defs/"
    assert reference.startswith(prefix)
    definitions = root.get("$defs")
    assert isinstance(definitions, dict)
    resolved = definitions.get(reference[len(prefix) :])
    assert isinstance(resolved, dict)
    return resolved


def test_plan_tools_have_exact_closed_nested_selector_schemas(tmp_path: Path):
    schemas = _schemas(tmp_path)
    assert PLAN_TOOLS <= set(schemas)

    add = schemas["stm32_diagnostic_plan_add"]
    assert set(add["properties"]) == {
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "steps",
        "actor",
    }
    assert add["required"] == [
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "steps",
    ]
    assert add["additionalProperties"] is False
    assert add["properties"]["actor"]["default"] == "user"
    assert add["properties"]["actor"]["enum"] == ACTORS

    run = schemas["stm32_diagnostic_plan_run"]
    assert set(run["properties"]) == {
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "planId",
        "actor",
    }
    assert run["required"] == [
        "operationId",
        "diagnosticSessionId",
        "expectedRevision",
        "planId",
    ]
    assert run["additionalProperties"] is False
    assert run["properties"]["actor"]["default"] == "tool"
    assert run["properties"]["actor"]["enum"] == ACTORS
    assert run["properties"]["planId"]["pattern"] == r"^[0-9a-f]{64}$"
    assert run["properties"]["planId"]["minLength"] == 64
    assert run["properties"]["planId"]["maxLength"] == 64

    steps = _resolve_schema(add["properties"]["steps"]["items"], add)
    assert steps["additionalProperties"] is False
    assert set(steps["properties"]) == {
        "step_id",
        "selector",
        "expected_value",
        "purpose",
    }
    assert steps["required"] == [
        "step_id",
        "selector",
        "expected_value",
        "purpose",
    ]
    assert add["properties"]["steps"]["minItems"] == 1
    assert add["properties"]["steps"]["maxItems"] == 64
    assert steps["properties"]["step_id"]["pattern"] == (
        r"^[a-z0-9][a-z0-9._-]{0,127}$"
    )
    assert steps["properties"]["step_id"]["minLength"] == 1
    assert steps["properties"]["step_id"]["maxLength"] == 128
    assert steps["properties"]["purpose"]["minLength"] == 1
    assert steps["properties"]["purpose"]["maxLength"] == 65_536

    selector = _resolve_schema(steps["properties"]["selector"], add)
    variants = selector.get("oneOf") or selector.get("anyOf")
    assert isinstance(variants, list)
    assert len(variants) == 4
    variant_schemas = [_resolve_schema(item, add) for item in variants]
    assert all(item["additionalProperties"] is False for item in variant_schemas)
    assert {
        tuple(sorted(item["properties"])) for item in variant_schemas
    } == {
        ("kind",),
        ("case_id", "kind"),
        ("kind", "state"),
        (
            "bit_index",
            "continuation_evidence_id",
            "fact",
            "kind",
            "minimum_valid_samples",
            "monitor_ref_evidence_id",
            "monitor_run_ref",
            "selector",
            "selector_kind",
        ),
    }
    run_state = next(item for item in variant_schemas if set(item["properties"]) == {"kind"})
    case_state = next(
        item for item in variant_schemas if set(item["properties"]) == {"kind", "case_id"}
    )
    case_count = next(
        item for item in variant_schemas if set(item["properties"]) == {"kind", "state"}
    )
    physical = next(
        item
        for item in variant_schemas
        if "monitor_run_ref" in item["properties"]
    )
    assert run_state["properties"]["kind"]["const"] == "run-state"
    assert case_state["properties"]["kind"]["const"] == "case-state"
    assert case_state["properties"]["case_id"]["minLength"] == 1
    assert case_state["properties"]["case_id"]["maxLength"] == 65_536
    assert case_count["properties"]["kind"]["const"] == "case-count"
    assert case_count["properties"]["state"]["enum"] == [
        "passed",
        "failed",
        "skipped",
        "error",
        "timeout",
    ]
    assert physical["properties"]["kind"]["const"] == "physical-monitor-fact/1"
    assert physical["properties"]["fact"]["enum"] == [
        "value-varies",
        "bit-values-mask",
    ]
    assert physical["properties"]["selector_kind"]["enum"] == [
        "variable",
        "register",
    ]
    assert physical["properties"]["minimum_valid_samples"]["minimum"] == 1
    assert physical["properties"]["minimum_valid_samples"]["maximum"] == 1024
    bit_index = physical["properties"]["bit_index"]
    bit_index_variants = bit_index.get("anyOf") or bit_index.get("oneOf")
    assert isinstance(bit_index_variants, list)
    bit_index_integer = next(item for item in bit_index_variants if item.get("type") == "integer")
    assert bit_index_integer["minimum"] == 0
    assert bit_index_integer["maximum"] == 31
    assert set(physical["required"]) == {
        "kind",
        "continuation_evidence_id",
        "monitor_ref_evidence_id",
        "monitor_run_ref",
        "selector_kind",
        "selector",
        "fact",
        "minimum_valid_samples",
    }

    expected = steps["properties"]["expected_value"]
    expected_variants = expected.get("anyOf") or expected.get("oneOf")
    assert isinstance(expected_variants, list)
    assert any(item.get("type") == "integer" for item in expected_variants)
    integer = next(item for item in expected_variants if item.get("type") == "integer")
    assert integer["minimum"] == 0
    assert integer["maximum"] == 100_000


@pytest.mark.parametrize("step", [RUN_STATE_STEP, CASE_STATE_STEP, CASE_COUNT_STEP])
def test_registered_plan_add_accepts_selector_variants_and_converts_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: dict[str, object],
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[object, ...]] = []

    async def helper(*args: object) -> dict[str, object]:
        calls.append(args)
        return {"tool": "plan-add"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_plan_for_request", helper, raising=False)

    _content, result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_plan_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "steps": [step],
            },
        )
    )

    assert result == {"tool": "plan-add"}
    assert len(calls) == 1
    assert calls[0][0] == runtime
    assert calls[0][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        4,
        [step],
        "user",
    )


def test_registered_plan_add_preserves_physical_reference_null_and_bit_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[object, ...]] = []

    async def helper(*args: object) -> dict[str, object]:
        calls.append(args)
        return {"tool": "plan-add"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_plan_for_request", helper, raising=False)

    _content, result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_plan_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "steps": [PHYSICAL_FACT_STEP],
            },
        )
    )
    assert result == {"tool": "plan-add"}
    physical_step = calls[-1][5][0]
    assert physical_step["selector"]["monitor_run_ref"]["svd_sha256"] is None
    assert physical_step["selector"]["monitor_run_ref"]["schema"] == (
        "stm32-monitor-run-ref/2"
    )
    assert physical_step["selector"]["bit_index"] == 0

    value_varies_step = deepcopy(PHYSICAL_FACT_STEP)
    value_varies_selector = value_varies_step["selector"]
    assert isinstance(value_varies_selector, dict)
    value_varies_selector["fact"] = "value-varies"
    value_varies_selector.pop("bit_index")
    value_varies_step["expected_value"] = 1
    _content, result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_plan_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "steps": [value_varies_step],
            },
        )
    )
    assert result == {"tool": "plan-add"}
    value_varies_selector_data = calls[-1][5][0]["selector"]
    assert "bit_index" not in value_varies_selector_data
    assert value_varies_selector_data["monitor_run_ref"]["svd_sha256"] is None

    explicit_null_bit_index = deepcopy(value_varies_step)
    explicit_null_selector = explicit_null_bit_index["selector"]
    assert isinstance(explicit_null_selector, dict)
    explicit_null_selector["bit_index"] = None
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_diagnostic_plan_add",
                {
                    "operationId": OPERATION_ID,
                    "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                    "expectedRevision": 4,
                    "steps": [explicit_null_bit_index],
                },
            )
        )
    assert len(calls) == 2

    missing_bit_index = deepcopy(PHYSICAL_FACT_STEP)
    missing_selector = missing_bit_index["selector"]
    assert isinstance(missing_selector, dict)
    missing_selector.pop("bit_index")
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_diagnostic_plan_add",
                {
                    "operationId": OPERATION_ID,
                    "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                    "expectedRevision": 4,
                    "steps": [missing_bit_index],
                },
            )
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("helper_name", "workflow_name", "operation", "arguments"),
    [
        (
            "tool_diagnostic_add_plan_for_request",
            "diagnostic_add_plan",
            "diagnostic.plan.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "steps": PLAN_STEPS,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_run_plan_for_request",
            "diagnostic_run_plan",
            "diagnostic.plan.run",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 5,
                "plan_id": PLAN_ID,
                "actor": "tool",
            },
        ),
    ],
)
def test_plan_request_helpers_short_circuit_on_root_failure(
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
            "tool_diagnostic_add_plan_for_request",
            "diagnostic_add_plan",
            "diagnostic.plan.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "steps": PLAN_STEPS,
                "actor": "ai-client",
            },
        ),
        (
            "tool_diagnostic_run_plan_for_request",
            "diagnostic_run_plan",
            "diagnostic.plan.run",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 5,
                "plan_id": PLAN_ID,
                "actor": "tool",
            },
        ),
    ],
)
def test_plan_request_helpers_call_one_workflow_with_bound_context(
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
            "tool_diagnostic_add_plan_for_request",
            "diagnostic_add_plan",
            "diagnostic.plan.add",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 4,
                "steps": PLAN_STEPS,
            },
        ),
        (
            "tool_diagnostic_run_plan_for_request",
            "diagnostic_run_plan",
            "diagnostic.plan.run",
            {
                "operation_id": OPERATION_ID,
                "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
                "expected_revision": 5,
                "plan_id": PLAN_ID,
            },
        ),
    ],
)
def test_plan_request_helpers_preserve_domain_failure_dictionary(
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


def test_registered_plan_tools_are_thin_delegates_with_application_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[str, tuple[object, ...]]] = []

    async def add(*args: object) -> dict[str, object]:
        calls.append(("add", args))
        return {"tool": "add"}

    async def run(*args: object) -> dict[str, object]:
        calls.append(("run", args))
        return {"tool": "run"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_plan_for_request", add)
    monkeypatch.setattr(mcp_mod, "tool_diagnostic_run_plan_for_request", run)

    _content, add_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_plan_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "steps": PLAN_STEPS,
            },
        )
    )
    _content, run_result = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_plan_run",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 5,
                "planId": PLAN_ID,
            },
        )
    )

    assert add_result == {"tool": "add"}
    assert run_result == {"tool": "run"}
    assert [name for name, _args in calls] == ["add", "run"]
    assert calls[0][1][0] == runtime
    assert calls[0][1][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        4,
        PLAN_STEPS,
        "user",
    )
    assert calls[1][1][0] == runtime
    assert calls[1][1][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        5,
        PLAN_ID,
        "tool",
    )


@pytest.mark.parametrize(
    "bad_steps",
    [
        tuple(PLAN_STEPS),
        [dict(RUN_STATE_STEP, expected_value=1)],
        [dict(CASE_STATE_STEP, expected_value="running")],
        [dict(CASE_COUNT_STEP, expected_value=True)],
        [dict(CASE_COUNT_STEP, expected_value=100_001)],
        [dict(CASE_COUNT_STEP, expected_value=1.0)],
        [dict(RUN_STATE_STEP, selector={"kind": "run-state", "extra": True})],
        [dict(CASE_STATE_STEP, selector={"kind": "case-state", "case_id": ""})],
        [dict(CASE_STATE_STEP, selector={"kind": "case-state", "case_id": "e\u0301"})],
        [dict(CASE_COUNT_STEP, selector={"kind": "case-count", "state": "running"})],
        [dict(RUN_STATE_STEP, purpose="a" * 65_537)],
        [dict(RUN_STATE_STEP, unknown="reject")],
        [
            dict(RUN_STATE_STEP),
            dict(RUN_STATE_STEP),
        ],
    ],
)
def test_registered_plan_add_rejects_invalid_nested_input_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_steps: object,
):
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(True)
        return {"unexpected": True}

    monkeypatch.setattr(
        mcp_mod,
        "tool_diagnostic_add_plan_for_request",
        forbidden,
        raising=False,
    )

    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_diagnostic_plan_add",
                {
                    "operationId": OPERATION_ID,
                    "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                    "expectedRevision": 4,
                    "steps": bad_steps,
                },
            )
        )
    assert calls == []


@pytest.mark.parametrize(
    ("tool_name", "arguments", "helper_name"),
    [
        (
            "stm32_diagnostic_plan_add",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 4,
                "steps": PLAN_STEPS,
                "projectRoot": "C:/escape",
            },
            "tool_diagnostic_add_plan_for_request",
        ),
        (
            "stm32_diagnostic_plan_run",
            {
                "operationId": OPERATION_ID,
                "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
                "expectedRevision": 5,
                "planId": PLAN_ID,
                "workspace": "C:/escape",
            },
            "tool_diagnostic_run_plan_for_request",
        ),
    ],
)
def test_registered_plan_tools_reject_forbidden_outer_fields_before_dispatch(
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
