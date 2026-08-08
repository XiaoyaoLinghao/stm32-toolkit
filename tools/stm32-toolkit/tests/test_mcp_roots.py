import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp.types import FileUrl, ListRootsResult, Root

from stm32_toolkit.mcp_server import (
    ServerRuntime,
    create_server,
    tool_doctor_for_request,
    tool_project_context_for_request,
    tool_project_detect,
    tool_project_detect_for_request,
)


class _RootSession:
    def __init__(self, root_batches: list[list[Path]], *, error: Exception | None = None):
        self.client_params = SimpleNamespace(
            capabilities=SimpleNamespace(roots=object())
        )
        self._root_batches = iter(root_batches)
        self._error = error
        self.list_roots_calls = 0

    async def list_roots(self) -> ListRootsResult:
        self.list_roots_calls += 1
        if self._error is not None:
            raise self._error
        paths = next(self._root_batches)
        return ListRootsResult(
            roots=[Root(uri=FileUrl(path.resolve().as_uri())) for path in paths]
        )


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


def _context(session: object) -> SimpleNamespace:
    return SimpleNamespace(session=session)


def test_direct_and_no_roots_capability_calls_remain_bound_to_the_runtime(tmp_path: Path):
    runtime = _runtime(tmp_path)
    no_capability = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=SimpleNamespace(roots=None))
    )

    direct = tool_project_detect(runtime)
    through_request = asyncio.run(
        tool_project_detect_for_request(runtime, _context(no_capability))
    )

    assert direct["data"]["kind"] == "keil"
    assert through_request == direct


def test_one_matching_client_root_is_accepted(tmp_path: Path):
    runtime = _runtime(tmp_path)
    session = _RootSession([[runtime.project_root]])

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is True
    assert result["data"]["kind"] == "keil"
    assert session.list_roots_calls == 1


@pytest.mark.parametrize(
    ("request_tool", "operation"),
    [
        (tool_doctor_for_request, "doctor"),
        (tool_project_detect_for_request, "project.detect"),
        (tool_project_context_for_request, "project.context"),
    ],
)
def test_every_registered_wrapper_rejects_multiple_client_roots(
    tmp_path: Path,
    request_tool,
    operation: str,
):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[runtime.project_root, other]])

    result = asyncio.run(
        request_tool(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["operation"] == operation
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_one_mismatched_client_root_is_rejected(tmp_path: Path):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[other]])

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_client_roots_inspection_failure_has_a_stable_error(tmp_path: Path):
    runtime = _runtime(tmp_path)
    session = _RootSession([], error=RuntimeError("roots unavailable"))

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["message"] == "MCP client roots are unavailable"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}


def test_client_roots_timeout_cancels_request_and_returns_stable_error(
    monkeypatch,
    tmp_path: Path,
):
    runtime = _runtime(tmp_path)

    class NeverReturningSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )
            self.cancelled = False

        async def list_roots(self):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    session = NeverReturningSession()
    monkeypatch.setattr(
        "stm32_toolkit.mcp_server._CLIENT_ROOTS_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    async def bounded_call():
        try:
            return await asyncio.wait_for(
                tool_project_detect_for_request(runtime, _context(session)),
                timeout=0.2,
            )
        except TimeoutError:
            return {"code": "HUNG"}

    result = asyncio.run(bounded_call())

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["message"] == "MCP client roots are unavailable"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}
    assert session.cancelled is True


def test_inner_roots_cancellation_returns_stable_unavailable(tmp_path: Path):
    runtime = _runtime(tmp_path)

    class CancelledSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )

        async def list_roots(self):
            raise asyncio.CancelledError

    async def bounded_call():
        try:
            return await tool_project_detect_for_request(
                runtime, _context(CancelledSession())
            )
        except asyncio.CancelledError:
            return {"code": "CANCELLED"}

    result = asyncio.run(bounded_call())

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"


def test_external_tool_cancellation_is_not_swallowed(tmp_path: Path):
    runtime = _runtime(tmp_path)

    class BlockingSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )
            self.started = asyncio.Event()

        async def list_roots(self):
            self.started.set()
            await asyncio.Event().wait()

    async def cancel_call():
        session = BlockingSession()
        call = asyncio.create_task(
            tool_project_detect_for_request(runtime, _context(session))
        )
        await session.started.wait()
        call.cancel()
        await call

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel_call())


def test_client_capability_inspection_failure_has_the_same_stable_error(
    tmp_path: Path,
):
    runtime = _runtime(tmp_path)

    class BrokenCapabilitySession:
        @property
        def client_params(self):
            raise RuntimeError("client parameters unavailable")

    result = asyncio.run(
        tool_project_detect_for_request(
            runtime, _context(BrokenCapabilitySession())
        )
    )

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}

def test_client_roots_are_checked_again_for_every_call(tmp_path: Path):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession(
        [[runtime.project_root], [runtime.project_root, other]]
    )
    context = _context(session)

    first = asyncio.run(tool_project_detect_for_request(runtime, context))
    second = asyncio.run(tool_project_detect_for_request(runtime, context))

    assert first["ok"] is True
    assert second["code"] == "UNSUPPORTED_MULTIROOT"
    assert session.list_roots_calls == 2


def test_injected_context_does_not_add_arguments_to_tool_schemas(tmp_path: Path):
    runtime = _runtime(tmp_path)

    server = create_server(
        runtime.project_root, runtime.data_root, runtime.session_id
    )
    tools = asyncio.run(server.list_tools())

    # The injected ``ctx`` parameter must never surface as a schema property.
    assert all("ctx" not in tool.inputSchema.get("properties", {}) for tool in tools)
    zero_argument_tools = {
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
        "stm32_probe_list",
    }
    for tool in tools:
        if tool.name in zero_argument_tools:
            assert tool.inputSchema.get("properties", {}) == {}
            assert not tool.inputSchema.get("required", [])
        else:
            assert tool.inputSchema.get("properties", {})
