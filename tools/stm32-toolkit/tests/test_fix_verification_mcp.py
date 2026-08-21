from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.result import OperationResult


SESSION = "0123456789abcdef0123456789abcdef"
OPERATION = "operation-1"
DIGEST = "a" * 64


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    (project / "descriptor.json").write_text("{}", encoding="utf-8")
    (project / "stream.bin").write_bytes(b"stream")
    return ServerRuntime.create(project, tmp_path / "data", "tool-session")


def test_toolkit_task8a_tools_are_registered_with_closed_top_level_schemas(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    schemas = {
        tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())
    }
    expected = {
        "stm32_test_target_replay",
        "stm32_diagnostic_source_change_declare",
        "stm32_diagnostic_verification_plan_add",
        "stm32_diagnostic_verification_start",
        "stm32_diagnostic_marker_attach",
        "stm32_diagnostic_verification_complete",
        "stm32_diagnostic_verification_show",
    }
    assert expected <= set(schemas)
    for name in expected:
        assert schemas[name]["additionalProperties"] is False
    assert set(schemas["stm32_test_target_replay"]["properties"]) == {
        "operationId",
        "descriptorPath",
        "streamPath",
    }
    assert set(schemas["stm32_diagnostic_verification_show"]["properties"]) == {
        "diagnosticSessionId"
    }


@pytest.mark.parametrize(
    "bad_path",
    ["", "/etc/passwd", "../escape.json", "a\\b.json", "C:/escape.json", "//server/share"],
)
def test_target_replay_rejects_nonportable_paths_before_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_path: str,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(mcp_mod, "tool_test_target_replay_for_request", forbidden)
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_test_target_replay",
                {"operationId": OPERATION, "descriptorPath": bad_path, "streamPath": "stream.bin"},
            )
        )
    assert calls == []


def test_target_replay_resolves_project_relative_paths_and_calls_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[object, dict[str, object]]] = []

    async def roots(*args: object, **kwargs: object) -> None:
        return None

    def replay(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return OperationResult.success("test.target.replay", {"ok": True})

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, "target_replay_run", replay)
    _content, result = asyncio.run(
        server.call_tool(
            "stm32_test_target_replay",
            {"operationId": OPERATION, "descriptorPath": "descriptor.json", "streamPath": "stream.bin"},
        )
    )
    assert result == OperationResult.success("test.target.replay", {"ok": True}).to_dict()
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context.project_root == runtime.project_root
    assert context.data_root == runtime.data_root
    assert kwargs == {
        "operation_id": OPERATION,
        "descriptor_file": runtime.project_root / "descriptor.json",
        "stream_file": runtime.project_root / "stream.bin",
    }


@pytest.mark.parametrize(
    "tool_name, helper_name, arguments",
    [
        (
            "stm32_diagnostic_source_change_declare",
            "tool_diagnostic_declare_source_change_for_request",
            {
                "operationId": OPERATION,
                "diagnosticSessionId": SESSION,
                "expectedRevision": 1,
                "sourceChangeDeclaration": {
                    "schema": "bad",
                    "declaration_id": DIGEST,
                    "extra": True,
                },
            },
        ),
        (
            "stm32_diagnostic_verification_plan_add",
            "tool_diagnostic_add_verification_plan_for_request",
            {
                "operationId": OPERATION,
                "diagnosticSessionId": SESSION,
                "expectedRevision": 1,
                "verificationPlan": {"schema": "bad", "extra": True},
            },
        ),
        (
            "stm32_diagnostic_marker_attach",
            "tool_diagnostic_attach_marker_for_request",
            {
                "operationId": OPERATION,
                "diagnosticSessionId": SESSION,
                "expectedRevision": 1,
                "diagnosticMarkerRef": {"schema": "bad", "extra": True},
            },
        ),
    ],
)
def test_nested_diagnostic_inputs_are_closed_before_helper_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    helper_name: str,
    arguments: dict[str, object],
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(mcp_mod, helper_name, forbidden)
    with pytest.raises(Exception):
        asyncio.run(server.call_tool(tool_name, arguments))
    assert calls == []


def test_each_diagnostic_helper_checks_roots_once_and_projects_result_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path)
    calls: list[str] = []
    result = OperationResult.success("diagnostic.verification.start", {"ok": True})

    async def roots(*args: object, **kwargs: object) -> None:
        calls.append("roots")
        return None

    def workflow(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append("workflow")
        return result

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots)
    monkeypatch.setattr(mcp_mod, "diagnostic_start_verification", workflow)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    _content, projected = asyncio.run(
        server.call_tool(
            "stm32_diagnostic_verification_start",
            {
                "operationId": OPERATION,
                "diagnosticSessionId": SESSION,
                "expectedRevision": 1,
                "verificationPlanId": DIGEST,
            },
        )
    )
    assert projected == result.to_dict()
    assert calls == ["roots", "workflow"]


def test_all_new_mcp_tools_reject_caller_roots_and_unknown_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[object] = []

    async def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_show_verification_for_request", forbidden)
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "stm32_diagnostic_verification_show",
                {"diagnosticSessionId": SESSION, "projectRoot": "escape"},
            )
        )
    assert calls == []
