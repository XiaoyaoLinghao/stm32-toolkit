import asyncio
from pathlib import Path

import pytest

from stm32_toolkit.mcp_server import (
    ServerRuntime,
    create_server,
    main,
    tool_project_context,
    tool_project_detect,
)


def test_tool_project_detect_uses_the_runtime_bound_project_root(tmp_path: Path):
    """Catches a tool accepting or using a caller-supplied project root."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    runtime = ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")

    assert tool_project_detect(runtime)["data"]["kind"] == "keil"


def test_runtime_rejects_a_missing_project_root_without_creating_data(tmp_path: Path):
    """Catches starting an unbound server that creates state for no project."""
    data_root = tmp_path / "plugin-data"

    with pytest.raises(ValueError, match="project root does not exist"):
        ServerRuntime.create(tmp_path / "missing", data_root, "session-a")

    assert not data_root.exists()


@pytest.mark.parametrize("data_root_name", ["", "plugin-data"])
def test_runtime_rejects_data_at_or_below_project_without_writing(
    configured_project: Path, data_root_name: str
):
    """Catches the MCP runtime recreating Task 5's project-write escape."""
    data_root = configured_project / data_root_name
    before = {path.relative_to(configured_project) for path in configured_project.rglob("*")}

    with pytest.raises(ValueError, match="data root must be outside project root"):
        ServerRuntime.create(configured_project, data_root, "session-a")

    assert {path.relative_to(configured_project) for path in configured_project.rglob("*")} == before


def test_runtime_reuses_one_generated_session_for_every_context_call(
    configured_project: Path, tmp_path: Path
):
    """Catches generating a fresh session directory for each context request."""
    runtime = ServerRuntime.create(configured_project, tmp_path.parent / "plugin-data")

    first = tool_project_context(runtime)
    second = tool_project_context(runtime)

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["workspace"]["sessionId"] == runtime.session_id
    assert second["data"]["workspace"]["sessionId"] == runtime.session_id


def test_runtime_uses_the_shared_safe_session_id_validation(tmp_path: Path):
    """Catches MCP startup accepting session IDs Task 2 rejects as unsafe paths."""
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(ValueError, match="invalid session id"):
        ServerRuntime.create(project, tmp_path / "plugin-data", "Session-A")


def test_server_registers_exactly_the_project_bound_zero_argument_tools(tmp_path: Path):
    """Catches an MCP registration exposing a root override or an extra tool."""
    project = tmp_path / "project"
    project.mkdir()

    server = create_server(project, tmp_path / "plugin-data", "session-a")
    tools = asyncio.run(server.list_tools())

    assert server.name == "STM32 Toolkit"
    assert "permanently bound" in server.instructions
    assert {tool.name for tool in tools} == {
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
    }
    assert all(tool.inputSchema.get("properties", {}) == {} for tool in tools)
    assert all(not tool.inputSchema.get("required", []) for tool in tools)


def test_main_runs_the_server_over_stdio(monkeypatch, tmp_path: Path):
    """Catches MCP startup selecting a non-stdio transport."""
    project = tmp_path / "project"
    project.mkdir()
    received: dict[str, object] = {}

    class FakeServer:
        def run(self, *, transport: str) -> None:
            received["transport"] = transport

    def fake_create_server(
        project_root: Path, data_root: Path, session_id: str | None
    ) -> FakeServer:
        received["project_root"] = project_root
        received["data_root"] = data_root
        received["session_id"] = session_id
        return FakeServer()

    monkeypatch.setattr("stm32_toolkit.mcp_server.create_server", fake_create_server)

    assert main([
        "--project-root", str(project),
        "--data-root", str(tmp_path / "plugin-data"),
        "--session-id", "session-a",
    ]) == 0

    assert received["transport"] == "stdio"
    assert received["project_root"] == project
    assert received["data_root"] == tmp_path / "plugin-data"
    assert received["session_id"] == "session-a"


def test_main_reports_startup_failures_on_stderr_without_stdout(tmp_path: Path, capsys):
    """Catches startup errors corrupting the stdio MCP protocol stream."""
    missing_project = tmp_path / "missing"

    assert main([
        "--project-root", str(missing_project),
        "--data-root", str(tmp_path / "plugin-data"),
    ]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "startup failed" in captured.err
