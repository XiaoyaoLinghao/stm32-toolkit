from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from stm32_toolkit.mcp_server import (
    ServerRuntime,
    create_server,
    tool_doctor,
    tool_project_create_plan,
    tool_project_create_plan_for_request,
    tool_project_create_prepare,
    tool_project_create_apply,
)
from stm32_toolkit.tool_support import ToolFact, ToolSupportProfile


def _fixed_support(tmp_path: Path) -> ToolSupportProfile:
    def fact(name: str, version: str) -> ToolFact:
        path = tmp_path / f"{name}.exe"
        path.write_bytes(name.encode())
        return ToolFact(name, path, version, "explicit", hashlib.sha256(path.read_bytes()).hexdigest())

    return ToolSupportProfile(
        "3.12.10",
        fact("cubeMx", "6.18.1"),
        tmp_path,
        fact("gcc", "14.3.1"),
        fact("cmake", "4.3.1"),
        fact("ninja", "1.13.2"),
        fact("vsCode", "1.133.0"),
        (),
        (),
    )


def test_mcp_creation_plan_has_closed_agent_neutral_arguments(tmp_path: Path):
    server = create_server(tmp_path, tmp_path.parent / "data", "session")
    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "stm32_project_create_plan")
    assert set(tool.inputSchema.get("properties", {})) == {"sourceKind", "source", "destination", "framework", "language"}
    assert "projectRoot" not in tool.inputSchema.get("properties", {})
    assert "supportProfile" not in tool.inputSchema.get("properties", {})


def test_mcp_runtime_pins_support_profile_at_startup(tmp_path: Path, monkeypatch):
    calls = []
    real = __import__("stm32_toolkit.mcp_server", fromlist=["discover_tool_support"])
    original = real.discover_tool_support
    def counted(request, **kwargs):
        calls.append(1)
        return original(request, **kwargs)
    monkeypatch.setattr(real, "discover_tool_support", counted)
    create_server(tmp_path, tmp_path.parent / "data-pinned", "session")
    assert len(calls) == 1


def test_mcp_doctor_reuses_frozen_profile_after_ambient_change(tmp_path: Path, monkeypatch):
    runtime = ServerRuntime.create(tmp_path, tmp_path.parent / "data-frozen", "session")
    import stm32_toolkit.mcp_server as mcp
    def fail(*args, **kwargs):
        raise AssertionError("ambient discovery must not rerun")
    monkeypatch.setattr(mcp, "discover_tool_support", fail)
    first = tool_doctor(runtime)
    second = tool_doctor(runtime)
    assert first["data"]["creationSupport"] == second["data"]["creationSupport"]


def test_mcp_create_plan_reuses_frozen_profile_after_ambient_change(tmp_path: Path, monkeypatch):
    runtime = ServerRuntime.create(tmp_path, tmp_path.parent / "data-frozen-create", "session")
    import stm32_toolkit.mcp_server as mcp
    import stm32_toolkit.creation_workflows as workflows

    monkeypatch.setattr(
        workflows,
        "_now_factory",
        lambda: datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )

    def fail(*args, **kwargs):
        raise AssertionError("ambient discovery must not rerun")

    monkeypatch.setattr(mcp, "discover_tool_support", fail)
    first = tool_project_create_plan(runtime, "mcu", "STM32F429ZITx", "generated", "hal", "c")
    second = tool_project_create_plan(runtime, "mcu", "STM32F429ZITx", "generated", "hal", "c")
    assert first["data"]["toolProfileDigest"] == second["data"]["toolProfileDigest"]
    assert first["data"]["expiresAt"] == second["data"]["expiresAt"]


def test_mcp_create_plan_enforces_client_root_binding(tmp_path: Path):
    from mcp.types import FileUrl, ListRootsResult, Root

    class RootSession:
        client_params = SimpleNamespace(capabilities=SimpleNamespace(roots=object()))

        def __init__(self, root: Path):
            self.root = root

        async def list_roots(self):
            return ListRootsResult(roots=[Root(uri=FileUrl(self.root.resolve().as_uri()))])

    runtime = ServerRuntime.create(tmp_path, tmp_path.parent / "data-create-roots", "session")
    other = tmp_path.parent / "other-create-root"
    other.mkdir()
    context = SimpleNamespace(session=RootSession(other))
    result = asyncio.run(
        tool_project_create_plan_for_request(
            runtime,
            context,
            "mcu",
            "STM32F429ZITx",
            "generated",
            "hal",
            "c",
        )
    )
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_cli_and_mcp_creation_plan_parity_uses_fixed_clock_and_profile(tmp_path: Path, monkeypatch, capsys):
    import stm32_toolkit.cli as cli
    import stm32_toolkit.creation_workflows as workflows

    fixed = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(workflows, "_now_factory", lambda: fixed)
    support = _fixed_support(tmp_path)
    monkeypatch.setattr(cli, "discover_tool_support", lambda request, **kwargs: support)
    runtime = ServerRuntime(tmp_path.resolve(), (tmp_path.parent / "mcp-data-parity").resolve(), "session", support)

    exit_code = cli.main(
        [
            "project",
            "create-plan",
            "--project-root",
            str(tmp_path),
            "--source-kind",
            "mcu",
            "--source",
            "STM32F429ZITx",
            "--destination",
            "generated",
            "--framework",
            "hal",
            "--language",
            "c",
            "--json",
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    mcp_payload = tool_project_create_plan(
        runtime, "mcu", "STM32F429ZITx", "generated", "hal", "c"
    )
    assert exit_code == 0
    assert cli_payload["data"] == mcp_payload["data"]


def test_mcp_registers_prepare_and_apply_with_closed_schemas(tmp_path: Path):
    server = create_server(tmp_path, tmp_path.parent / "data-public", "session")
    tools = asyncio.run(server.list_tools())
    prepare = next(item for item in tools if item.name == "stm32_project_create_prepare")
    apply = next(item for item in tools if item.name == "stm32_project_create_apply")
    assert set(prepare.inputSchema["properties"]) == {"sourceKind", "source", "destination", "framework", "language", "planId", "actionDigest"}
    assert set(apply.inputSchema["properties"]) == {"authorizationDigest", "authorized"}


def test_mcp_prepare_and_apply_adapters_share_typed_workflows(tmp_path: Path, monkeypatch):
    runtime = ServerRuntime.create(tmp_path, tmp_path.parent / "data-public-adapters", "session")
    from stm32_toolkit.result import OperationResult
    import stm32_toolkit.mcp_server as mcp
    monkeypatch.setattr(mcp, "prepare_creation_workflow", lambda request, **kwargs: OperationResult.success("project-create-prepare", {"mutated": False}).to_dict())
    monkeypatch.setattr(mcp, "apply_creation_workflow", lambda request, **kwargs: OperationResult.success("project-create-apply", {"mutated": True}).to_dict())
    prepared = tool_project_create_prepare(runtime, "mcu", "STM32F429ZITx", "generated", "hal", "c", "a" * 64, "b" * 64)
    applied = tool_project_create_apply(runtime, "c" * 64, True)
    assert prepared["data"]["mutated"] is False
    assert applied["data"]["mutated"] is True
