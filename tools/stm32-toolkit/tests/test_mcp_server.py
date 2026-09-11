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
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES


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
    """Catches invalid supplied session IDs creating plugin state before rejection."""
    project = tmp_path / "project"
    data_root = tmp_path / "plugin-data"
    project.mkdir()

    with pytest.raises(ValueError, match="invalid session id"):
        ServerRuntime.create(project, data_root, "Session-A")

    assert not data_root.exists()


def test_runtime_validates_a_generated_session_before_creating_data(
    monkeypatch, tmp_path: Path
):
    """Catches generated session validation occurring after the data-root write."""
    project = tmp_path / "project"
    data_root = tmp_path / "plugin-data"
    project.mkdir()

    monkeypatch.setattr("stm32_toolkit.mcp_server.new_session_id", lambda: "Session-A")

    with pytest.raises(ValueError, match="invalid session id"):
        ServerRuntime.create(project, data_root)

    assert not data_root.exists()


def test_server_registers_exactly_the_project_bound_tools(tmp_path: Path):
    """Catches a registration exposing a root override or an extra tool."""
    project = tmp_path / "project"
    project.mkdir()

    server = create_server(project, tmp_path / "plugin-data", "session-a")
    tools = asyncio.run(server.list_tools())

    assert server.name == "STM32 Toolkit"
    assert "permanently bound" in server.instructions
    assert "explicitly authorized" in server.instructions
    assert "only read-only foundation tools" not in server.instructions
    assert {tool.name for tool in tools} == set(MCP_TOOL_NAMES.values())
    zero_argument_tools = {
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
        "stm32_test_host_discover",
    }
    for tool in tools:
        if tool.name in zero_argument_tools:
            assert tool.inputSchema.get("properties", {}) == {}
            assert not tool.inputSchema.get("required", [])
        else:
            assert "projectRoot" not in tool.inputSchema.get("properties", {})
            assert "dataRoot" not in tool.inputSchema.get("properties", {})


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


def test_real_stdio_mcp_starts_and_closes_an_offline_worker_without_protocol_pollution(
    tmp_path: Path,
):
    """Exercise the real FastMCP stdio path through worker construction and close."""
    import json
    import os
    import sys
    import tempfile
    from datetime import timedelta

    if sys.platform != "win32":
        pytest.skip("Windows child-stdio integration")

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "plugin-data"
    marker = tmp_path / "worker-result.json"
    source_root = Path(__file__).parents[1] / "src"
    child_code = f"""
import __main__, importlib.util, json, pathlib, time
import stm32_toolkit.mcp_server as server
from stm32_toolkit.probe.worker import ProbeBackendWorker, ProbeWorkerConfig
from stm32_toolkit.result import OperationResult

__main__.__spec__ = importlib.util.find_spec('stm32_toolkit.mcp_server')
marker = pathlib.Path({str(marker)!r})

async def offline_only(request):
    started = time.monotonic()
    worker = None
    try:
        worker = ProbeBackendWorker(config=ProbeWorkerConfig())
        pid = worker.owned_pid
        worker.close()
        data = {{
            'scope': 'constructor/close only; no hardware',
            'workerPid': pid,
            'aliveAfterClose': worker.is_alive,
            'hardwareOperations': [],
            'readySeconds': time.monotonic() - started,
        }}
        marker.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
        return OperationResult.success('offline_worker_startup', data)
    except Exception as error:
        data = {{'scope': 'constructor/close only; no hardware', 'hardwareOperations': []}}
        marker.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
        return OperationResult.failure(
            'offline_worker_startup',
            getattr(error, 'code', 'OFFLINE_FAILURE'),
            str(error),
            {{'seconds': time.monotonic() - started}},
        )

server.variable_read_workflow = offline_only
raise SystemExit(server.main())
"""
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(source_root), environment.get("PYTHONPATH", "")) if value
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            child_code,
            "--project-root",
            str(project),
            "--data-root",
            str(data_root),
            "--session-id",
            "session-stdio-worker",
        ],
        env=environment,
        cwd=str(source_root.parent),
    )

    async def exercise_stdio():
        with tempfile.TemporaryFile() as errlog:
            async with stdio_client(
                parameters, errlog=errlog
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    result = await session.call_tool(
                        "stm32_variable_read",
                        {
                            "probeId": "probe-a",
                            "expectedBuildId": "a" * 64,
                            "expectedElfSha256": "b" * 64,
                            "expressions": ["counter"],
                        },
                        read_timeout_seconds=timedelta(seconds=20),
                    )
        return initialized, result

    initialized, result = asyncio.run(exercise_stdio())
    assert initialized.serverInfo.name == "STM32 Toolkit"
    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["code"] == "OK"
    assert result.structuredContent["data"]["scope"] == (
        "constructor/close only; no hardware"
    )
    assert result.structuredContent["data"]["aliveAfterClose"] is False
    assert result.structuredContent["data"]["hardwareOperations"] == []
    assert json.loads(marker.read_text(encoding="utf-8"))["aliveAfterClose"] is False


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--project-root",
            "C:/one",
            "--project-root",
            "C:/two",
            "--data-root",
            "C:/data",
        ],
        [
            "--project-root",
            "C:/project",
            "--data-root",
            "C:/one",
            "--data-root",
            "C:/two",
        ],
    ],
)
def test_mcp_parser_rejects_duplicate_project_or_data_roots(argv):
    from stm32_toolkit.mcp_server import _build_parser

    with pytest.raises(SystemExit) as raised:
        _build_parser().parse_args(argv)
    assert raised.value.code == 2


def test_runtime_rejects_project_root_file_without_creating_data(tmp_path: Path):
    """Catches binding an MCP process to a non-directory project path."""
    project_file = tmp_path / "project.bin"
    data_root = tmp_path / "plugin-data"
    project_file.write_bytes(b"project")

    with pytest.raises(ValueError, match="project root is not a directory"):
        ServerRuntime.create(project_file, data_root, "session-a")

    assert not data_root.exists()


def test_runtime_rejects_data_root_file(tmp_path: Path):
    """Catches accepting a mutable-state file where a directory is required."""
    project = tmp_path / "project"
    data_file = tmp_path / "plugin-data"
    project.mkdir()
    data_file.write_bytes(b"state")

    with pytest.raises(ValueError, match="data root is not available"):
        ServerRuntime.create(project, data_file, "session-a")

    assert data_file.read_bytes() == b"state"


def test_runtime_resolution_error_fails_before_data_creation(monkeypatch, tmp_path: Path):
    """Catches root canonicalization failures creating unbound plugin state."""
    project = tmp_path / "project"
    data_root = tmp_path / "plugin-data"
    project.mkdir()

    def unavailable(path: Path) -> Path:
        raise OSError("root unavailable")

    monkeypatch.setattr("stm32_toolkit.mcp_server.canonical_project_root", unavailable)

    with pytest.raises(ValueError, match="project root does not exist"):
        ServerRuntime.create(project, data_root, "session-a")

    assert not data_root.exists()


def test_detect_tool_translates_bound_project_filesystem_errors(
    monkeypatch, tmp_path: Path
):
    """Catches an MCP detection failure escaping its protocol envelope."""
    project = tmp_path / "project"
    project.mkdir()
    runtime = ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")

    def unavailable(path: Path):
        raise OSError("directory unavailable")

    monkeypatch.setattr("stm32_toolkit.mcp_server.detect_project", unavailable)

    result = tool_project_detect(runtime)

    assert result["code"] == "PROJECT_DETECTION_UNAVAILABLE"
    assert result["details"] == {"path": str(project)}


def test_registered_tools_return_bound_runtime_results(monkeypatch, tmp_path: Path):
    """Catches registered MCP wrappers drifting from the three bound operations."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)
    server = create_server(project, tmp_path / "plugin-data", "session-a")

    results = {}
    for tool_name in (
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
    ):
        _, structured = asyncio.run(server.call_tool(tool_name, {}))
        results[tool_name] = structured

    assert results["stm32_doctor"]["operation"] == "doctor"
    assert results["stm32_doctor"]["data"]["project"]["files"] == ["legacy.uvprojx"]
    assert results["stm32_project_detect"]["operation"] == "project.detect"
    assert results["stm32_project_detect"]["data"]["kind"] == "keil"
    assert results["stm32_project_context"]["operation"] == "project.context"
    assert results["stm32_project_context"]["data"]["workspace"] is None
    assert results["stm32_project_context"]["data"]["project"]["root"] == str(
        project.resolve()
    )
