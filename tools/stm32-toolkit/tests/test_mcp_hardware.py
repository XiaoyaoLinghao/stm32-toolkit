"""Project-bound MCP hardware tools and their concurrency boundary (0405)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.hardware_workflows import (
    FaultWorkflowRequest,
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    ProbeListWorkflowRequest,
    RegisterReadWorkflowRequest,
    VariableReadWorkflowRequest,
    VariableSampleWorkflowRequest,
)
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.result import OperationResult


HARDWARE_TOOLS = {
    "stm32_probe_list",
    "stm32_flash",
    "stm32_debug_handoff_begin",
    "stm32_debug_handoff_end",
    "stm32_variable_read",
    "stm32_variable_sample",
    "stm32_register_read",
    "stm32_fault_analyze",
}


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


def _schemas(tmp_path: Path) -> dict[str, dict[str, object]]:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    return {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}


def test_server_registers_exactly_fifteen_tools_including_hardware(tmp_path: Path):
    """Catches a missing, duplicate, or accidentally exposed MCP operation."""
    schemas = _schemas(tmp_path)

    assert len(schemas) == 15
    assert HARDWARE_TOOLS <= set(schemas)


def test_hardware_schemas_expose_only_project_bound_arguments(tmp_path: Path):
    """Catches a target, SVD, address, runtime, or process override in MCP."""
    schemas = _schemas(tmp_path)
    properties = {
        name: set(schemas[name].get("properties", {})) for name in HARDWARE_TOOLS
    }

    assert properties == {
        "stm32_probe_list": set(),
        "stm32_flash": {
            "probeId", "expectedBuildId", "expectedElfSha256", "authorized"
        },
        "stm32_debug_handoff_begin": {
            "probeId", "expectedBuildId", "expectedElfSha256", "authorized",
            "previousWatchSelection",
        },
        "stm32_debug_handoff_end": {"probeId", "ticket"},
        "stm32_variable_read": {
            "probeId", "expectedBuildId", "expectedElfSha256", "expressions"
        },
        "stm32_variable_sample": {
            "probeId", "expectedBuildId", "expectedElfSha256", "expressions",
            "intervalMs", "count", "durationMs",
        },
        "stm32_register_read": {
            "probeId", "expectedBuildId", "expectedElfSha256", "paths",
            "acknowledgeAccessRisk",
        },
        "stm32_fault_analyze": {
            "probeId", "expectedBuildId", "expectedElfSha256"
        },
    }
    forbidden = {
        "projectRoot", "project_root", "dataRoot", "data_root", "sessionId",
        "session_id", "workspace", "lease", "leaseId", "endpoint", "token",
        "target", "svd", "svdPath", "elf", "elfPath", "address", "size",
        "command", "argv", "environment", "process",
    }
    for fields in properties.values():
        assert not (fields & forbidden)


@pytest.mark.parametrize(
    ("wrapper_name", "workflow_name", "request_type", "arguments"),
    [
        ("tool_probe_list_for_request", "probe_list_workflow", ProbeListWorkflowRequest, {}),
        (
            "tool_flash_for_request", "flash_workflow", FlashWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64, "authorized": True},
        ),
        (
            "tool_handoff_begin_for_request", "handoff_begin_workflow",
            HandoffBeginWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64, "authorized": True,
             "previous_watch_selection": ["counter"]},
        ),
        (
            "tool_handoff_end_for_request", "handoff_end_workflow",
            HandoffEndWorkflowRequest,
            {"probe_id": "probe-a", "ticket": "c" * 64},
        ),
        (
            "tool_variable_read_for_request", "variable_read_workflow",
            VariableReadWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64, "expressions": ["counter"]},
        ),
        (
            "tool_variable_sample_for_request", "variable_sample_workflow",
            VariableSampleWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64, "expressions": ["counter"],
             "interval_ms": 10, "count": 2, "duration_ms": None},
        ),
        (
            "tool_register_read_for_request", "register_read_workflow",
            RegisterReadWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64, "paths": ["SCB.CFSR"],
             "acknowledge_access_risk": False},
        ),
        (
            "tool_fault_analyze_for_request", "fault_workflow", FaultWorkflowRequest,
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64},
        ),
    ],
)
def test_wrappers_build_requests_only_from_runtime_and_declared_fields(
    monkeypatch, tmp_path: Path, wrapper_name: str, workflow_name: str,
    request_type: type[object], arguments: dict[str, object],
):
    """Catches wrappers forwarding caller-controlled runtime or hidden inputs."""
    runtime = _runtime(tmp_path)
    received: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        received.append(request)
        return OperationResult.success("accepted", {"complete": True})

    monkeypatch.setattr(mcp_mod, workflow_name, accepted)
    result = asyncio.run(getattr(mcp_mod, wrapper_name)(runtime, None, **arguments))

    assert result == OperationResult.success(
        "accepted", {"complete": True}
    ).to_dict()
    assert len(received) == 1
    request = received[0]
    assert type(request) is request_type
    assert request.project_root == runtime.project_root
    assert request.data_root == runtime.data_root
    assert request.session_id == runtime.session_id


@pytest.mark.parametrize(
    ("tool_name", "workflow_name", "arguments"),
    [
        ("stm32_probe_list", "probe_list_workflow", {}),
        (
            "stm32_flash", "flash_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "authorized": True},
        ),
        (
            "stm32_debug_handoff_begin", "handoff_begin_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "authorized": True,
             "previousWatchSelection": ["counter"]},
        ),
        (
            "stm32_debug_handoff_end", "handoff_end_workflow",
            {"probeId": "probe-a", "ticket": "c" * 64},
        ),
        (
            "stm32_variable_read", "variable_read_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "expressions": ["counter"]},
        ),
        (
            "stm32_variable_sample", "variable_sample_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "expressions": ["counter"],
             "intervalMs": 10, "count": 2},
        ),
        (
            "stm32_register_read", "register_read_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "paths": ["SCB.CFSR"],
             "acknowledgeAccessRisk": False},
        ),
        (
            "stm32_fault_analyze", "fault_workflow",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64},
        ),
    ],
)
def test_registered_hardware_tools_dispatch_to_the_matching_workflow(
    monkeypatch, tmp_path: Path, tool_name: str, workflow_name: str,
    arguments: dict[str, object],
):
    """Catches a registered tool invoking a different hardware operation."""
    runtime = _runtime(tmp_path)
    received: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        received.append(request)
        return OperationResult.success(tool_name, {"tool": tool_name})

    monkeypatch.setattr(mcp_mod, workflow_name, accepted)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    _content, result = asyncio.run(server.call_tool(tool_name, arguments))

    assert result == OperationResult.success(
        tool_name, {"tool": tool_name}
    ).to_dict()
    assert len(received) == 1


@pytest.mark.parametrize("value", ["true", "false", 1, 0])
def test_registered_intrusive_tools_reject_non_boolean_authorization(
    monkeypatch, tmp_path: Path, value: object
):
    """Catches FastMCP coercing strings or integers into authorization."""
    runtime = _runtime(tmp_path)
    calls = 0

    async def forbidden(_request: object) -> OperationResult[object]:
        nonlocal calls
        calls += 1
        return OperationResult.success("forbidden", {})

    monkeypatch.setattr(mcp_mod, "flash_workflow", forbidden)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    with pytest.raises(Exception):
        asyncio.run(server.call_tool(
            "stm32_flash",
            {"probeId": "probe-a", "expectedBuildId": "a" * 64,
             "expectedElfSha256": "b" * 64, "authorized": value},
        ))
    assert calls == 0


@pytest.mark.parametrize("value", [False, "true", "false", 1, 0, None, [], {}])
@pytest.mark.parametrize(
    ("wrapper_name", "workflow_name", "extra"),
    [
        (
            "tool_flash_for_request", "flash_workflow",
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64},
        ),
        (
            "tool_handoff_begin_for_request", "handoff_begin_workflow",
            {"probe_id": "probe-a", "expected_build_id": "a" * 64,
             "expected_elf_sha256": "b" * 64,
             "previous_watch_selection": []},
        ),
    ],
)
def test_intrusive_wrappers_require_exact_true_before_workflow(
    monkeypatch, tmp_path: Path, value: object, wrapper_name: str,
    workflow_name: str, extra: dict[str, object],
):
    """Catches Python truthiness entering flash or ownership release."""
    runtime = _runtime(tmp_path)
    calls = 0

    async def forbidden(_request: object) -> OperationResult[object]:
        nonlocal calls
        calls += 1
        return OperationResult.success("forbidden", {})

    monkeypatch.setattr(mcp_mod, workflow_name, forbidden)
    result = asyncio.run(
        getattr(mcp_mod, wrapper_name)(runtime, None, authorized=value, **extra)
    )

    assert result["ok"] is False
    assert result["code"] == "AUTHORIZATION_REQUIRED"
    assert calls == 0


def test_roots_guard_runs_before_hardware_workflow(monkeypatch, tmp_path: Path):
    """Catches backend creation before MCP client-root validation."""
    runtime = _runtime(tmp_path)
    calls = 0

    async def forbidden(_request: object) -> OperationResult[object]:
        nonlocal calls
        calls += 1
        return OperationResult.success("forbidden", {})

    async def mismatched(*_args: object, **_kwargs: object) -> dict[str, object]:
        return OperationResult.failure(
            "stm32_probe_list", "UNSUPPORTED_MULTIROOT", "mismatch", {}
        ).to_dict()

    monkeypatch.setattr(mcp_mod, "probe_list_workflow", forbidden)
    monkeypatch.setattr(mcp_mod, "_client_roots_failure", mismatched)

    result = asyncio.run(mcp_mod.tool_probe_list_for_request(runtime, object()))

    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert calls == 0


def test_workflow_failures_and_partial_data_are_returned_without_truncation(
    monkeypatch, tmp_path: Path
):
    """Catches MCP replacing accepted stable workflow evidence."""
    runtime = _runtime(tmp_path)
    expected = OperationResult.failure(
        "stm32_variable_read",
        "VARIABLE_PARTIAL_FAILURE",
        "Some variables could not be read",
        {"items": [{"expression": "ok", "ok": True},
                   {"expression": "bad", "ok": False, "code": "SYMBOL_NOT_FOUND"}]},
    )

    async def partial(_request: object) -> OperationResult[object]:
        return expected

    monkeypatch.setattr(mcp_mod, "variable_read_workflow", partial)
    result = asyncio.run(mcp_mod.tool_variable_read_for_request(
        runtime, None, "probe-a", "a" * 64, "b" * 64, ["ok", "bad"]
    ))

    assert result == expected.to_dict()


@pytest.mark.parametrize(
    ("code", "operation"),
    [
        ("PROBE_BUSY", "stm32_variable_read"),
        ("PROBE_LEASE_LOST", "stm32_variable_read"),
        ("FIRMWARE_STALE", "stm32_variable_read"),
        ("HANDOFF_REPLAYED", "stm32_debug_handoff_end"),
    ],
)
def test_stable_hardware_failures_pass_through(monkeypatch, tmp_path: Path, code: str, operation: str):
    """Catches the MCP layer hiding actionable accepted hardware failures."""
    runtime = _runtime(tmp_path)
    workflow_name = (
        "handoff_end_workflow" if operation.endswith("handoff_end")
        else "variable_read_workflow"
    )

    async def failed(_request: object) -> OperationResult[object]:
        return OperationResult.failure(operation, code, "stable", {"probeId": "probe-a"})

    monkeypatch.setattr(mcp_mod, workflow_name, failed)
    if workflow_name == "handoff_end_workflow":
        result = asyncio.run(mcp_mod.tool_handoff_end_for_request(
            runtime, None, "probe-a", "c" * 64
        ))
    else:
        result = asyncio.run(mcp_mod.tool_variable_read_for_request(
            runtime, None, "probe-a", "a" * 64, "b" * 64, ["counter"]
        ))

    assert result["code"] == code
    assert result["details"] == {"probeId": "probe-a"}


def test_unexpected_workflow_exception_is_sanitized(monkeypatch, tmp_path: Path):
    """Catches raw tokens, paths, and backend messages escaping over MCP."""
    runtime = _runtime(tmp_path)

    async def broken(_request: object) -> OperationResult[object]:
        raise RuntimeError(f"token=secret at {runtime.data_root} backend exploded")

    monkeypatch.setattr(mcp_mod, "probe_list_workflow", broken)
    result = asyncio.run(mcp_mod.tool_probe_list_for_request(runtime, None))

    assert result == OperationResult.failure(
        "stm32_probe_list", "HARDWARE_INTERNAL_ERROR", "Hardware workflow failed", {}
    ).to_dict()
    assert "secret" not in str(result)
    assert str(runtime.data_root) not in str(result)


def test_workflow_cancellation_propagates(monkeypatch, tmp_path: Path):
    """Catches MCP converting cancellation into a successful or stable failure result."""
    runtime = _runtime(tmp_path)

    async def cancelled(_request: object) -> OperationResult[object]:
        raise asyncio.CancelledError

    monkeypatch.setattr(mcp_mod, "probe_list_workflow", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(mcp_mod.tool_probe_list_for_request(runtime, None))


def test_same_probe_busy_is_immediate_and_different_probes_run_in_parallel(
    monkeypatch, tmp_path: Path
):
    """Catches a global MCP hardware lock or swallowed per-probe busy result."""
    runtime = _runtime(tmp_path)
    entered = {"probe-a": asyncio.Event(), "probe-b": asyncio.Event()}
    active: set[str] = set()
    release = asyncio.Event()

    async def per_probe(request: VariableReadWorkflowRequest) -> OperationResult[object]:
        if request.probe_id in active:
            return OperationResult.failure(
                "stm32_variable_read", "PROBE_BUSY", "Probe is busy",
                {"probeId": request.probe_id},
            )
        active.add(request.probe_id)
        entered[request.probe_id].set()
        await release.wait()
        return OperationResult.success(
            "stm32_variable_read", {"probeId": request.probe_id}
        )

    monkeypatch.setattr(mcp_mod, "variable_read_workflow", per_probe)

    async def scenario() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        arguments = (runtime, None, "probe-a", "a" * 64, "b" * 64, ["counter"])
        first = asyncio.create_task(mcp_mod.tool_variable_read_for_request(*arguments))
        await entered["probe-a"].wait()
        same = await asyncio.wait_for(
            mcp_mod.tool_variable_read_for_request(*arguments), timeout=0.2
        )
        other = asyncio.create_task(mcp_mod.tool_variable_read_for_request(
            runtime, None, "probe-b", "a" * 64, "b" * 64, ["counter"]
        ))
        await asyncio.wait_for(entered["probe-b"].wait(), timeout=0.2)
        release.set()
        return await first, same, await other

    first, same, other = asyncio.run(scenario())

    assert first["ok"] is True
    assert same["code"] == "PROBE_BUSY"
    assert other["ok"] is True
