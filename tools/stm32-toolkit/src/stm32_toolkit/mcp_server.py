from __future__ import annotations

import asyncio
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from urllib.request import url2pathname

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from stm32_toolkit.context import build_project_context
from stm32_toolkit.detection import detect_project
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.identity import canonical_project_root, new_session_id
from stm32_toolkit.paths import require_safe_session_id
from stm32_toolkit.result import OperationResult
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    inspect_keil_workflow,
)


_SERVER_NAME = "STM32 Toolkit"
_SERVER_INSTRUCTIONS = (
    "This server is permanently bound to one project root and exposes "
    "read-only Keil inspection and planning plus explicitly authorized "
    "conversion, configuration, and build operations."
)
_CLIENT_ROOTS_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ServerRuntime:
    """Immutable, canonical project and data roots for one MCP process."""

    project_root: Path
    data_root: Path
    session_id: str

    @classmethod
    def create(
        cls,
        project_root: Path,
        data_root: Path,
        session_id: str | None = None,
    ) -> "ServerRuntime":
        try:
            canonical_project = canonical_project_root(project_root)
        except (OSError, ValueError) as error:
            raise ValueError("project root does not exist") from error
        if not canonical_project.is_dir():
            raise ValueError("project root is not a directory")

        resolved_session_id = require_safe_session_id(
            session_id if session_id is not None else new_session_id()
        )

        try:
            canonical_data = data_root.expanduser().resolve(strict=False)
        except (OSError, ValueError) as error:
            raise ValueError("data root is not available") from error
        _require_external_data_root(canonical_data, canonical_project)

        try:
            canonical_data.mkdir(exist_ok=True)
            canonical_data = canonical_data.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise ValueError("data root is not available") from error
        if not canonical_data.is_dir():
            raise ValueError("data root is not a directory")
        _require_external_data_root(canonical_data, canonical_project)

        return cls(canonical_project, canonical_data, resolved_session_id)


def _require_external_data_root(data_root: Path, project_root: Path) -> None:
    try:
        data_root.relative_to(project_root)
    except ValueError:
        return
    raise ValueError("data root must be outside project root")


def tool_doctor(runtime: ServerRuntime) -> dict[str, object]:
    """Return the read-only environment diagnosis for the bound project."""
    return run_doctor(runtime.project_root).to_dict()


def tool_project_detect(runtime: ServerRuntime) -> dict[str, object]:
    """Return project markers for the bound project."""
    try:
        detection = detect_project(runtime.project_root)
    except (OSError, ValueError):
        return OperationResult.failure(
            "project.detect",
            "PROJECT_DETECTION_UNAVAILABLE",
            "Project detection is not available",
            {"path": str(runtime.project_root)},
        ).to_dict()
    return OperationResult.success("project.detect", detection.to_dict()).to_dict()


def tool_project_context(runtime: ServerRuntime) -> dict[str, object]:
    """Return context evidence using the runtime's stable session identifier."""
    return build_project_context(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
    ).to_dict()


def tool_keil_inspect(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> dict[str, object]:
    """Read-only Keil inspection and baseline for the bound project."""
    return inspect_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        include_baseline=include_baseline,
    ).to_dict()


def tool_keil_convert(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    """Read-only conversion plan, or apply with the exact plan ID plus
    ``authorized=true``."""
    return convert_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        plan_id=plan_id,
        authorized=authorized,
    ).to_dict()


def tool_project_configure(
    runtime: ServerRuntime,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    """Read-only configuration plan, or apply with the exact plan ID plus
    ``authorized=true``."""
    return configure_project_workflow(
        runtime.project_root,
        plan_id=plan_id,
        authorized=authorized,
    ).to_dict()


def tool_build(
    runtime: ServerRuntime,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool = False,
) -> dict[str, object]:
    """Run the guarded build for the bound project with explicit
    ``authorized=true``."""
    return build_firmware_workflow(
        runtime.project_root,
        preset=preset,
        clean=clean,
        timeout_seconds=timeout_seconds,
        authorized=authorized,
    ).to_dict()


async def tool_doctor_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "doctor")
    return failure if failure is not None else tool_doctor(runtime)


async def tool_project_detect_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project.detect")
    return failure if failure is not None else tool_project_detect(runtime)


async def tool_project_context_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project.context")
    return failure if failure is not None else tool_project_context(runtime)


async def tool_keil_inspect_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "keil-inspect")
    if failure is not None:
        return failure
    return tool_keil_inspect(runtime, uvprojx, target_name, include_baseline)


async def tool_keil_convert_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    operation = (
        "keil-conversion-apply"
        if plan_id is not None or authorized is not False
        else "keil-conversion-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_keil_convert(runtime, uvprojx, target_name, plan_id, authorized)


async def tool_project_configure_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    operation = (
        "project-configuration-apply"
        if plan_id is not None or authorized is not False
        else "project-configuration-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_project_configure(runtime, plan_id, authorized)


async def tool_build_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool = False,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "build")
    if failure is not None:
        return failure
    return tool_build(runtime, preset, clean, timeout_seconds, authorized)


async def _client_roots_failure(
    runtime: ServerRuntime,
    context: Context | None,
    operation: str,
) -> dict[str, object] | None:
    if context is None:
        return None
    try:
        session = context.session
    except ValueError:
        # FastMCP's direct in-memory call path has no client request context.
        return None

    try:
        client_params = getattr(session, "client_params", None)
        capabilities = getattr(client_params, "capabilities", None)
        if getattr(capabilities, "roots", None) is None:
            return None
    except Exception:
        return _roots_unavailable(runtime, operation)

    inner_task: asyncio.Task | None = None
    try:
        inner_task = asyncio.ensure_future(session.list_roots())
        done, _pending = await asyncio.wait(
            {inner_task}, timeout=_CLIENT_ROOTS_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        # Only cancellation of the current tool task can surface here: cancel
        # the in-flight request so it cannot outlive the caller, then
        # propagate. This uses only public asyncio APIs and therefore also
        # behaves correctly on Python 3.10, where Task.cancelling() is not
        # available.
        if inner_task is not None:
            inner_task.cancel()
            try:
                await inner_task
            except BaseException:
                pass
        raise
    except Exception:
        return _roots_unavailable(runtime, operation)

    if not done:
        # Timeout: cancel and await the in-flight request before returning the
        # stable unavailable result.
        inner_task.cancel()
        try:
            await inner_task
        except asyncio.CancelledError:
            pass
        return _roots_unavailable(runtime, operation)

    try:
        result = inner_task.result()
        roots = result.roots
        if not roots:
            raise ValueError("client advertised roots but returned none")
        canonical_roots = tuple(_canonical_client_root(root.uri) for root in roots)
    except asyncio.CancelledError:
        # The client-roots request cancelled itself; report the stable result.
        return _roots_unavailable(runtime, operation)
    except Exception:
        return _roots_unavailable(runtime, operation)

    if len(canonical_roots) != 1 or canonical_roots[0] != runtime.project_root:
        return OperationResult.failure(
            operation,
            "UNSUPPORTED_MULTIROOT",
            "MCP client roots must contain only the bound project root",
            {
                "boundProjectRoot": str(runtime.project_root),
                "roots": [str(root) for root in canonical_roots],
            },
        ).to_dict()
    return None


def _canonical_client_root(uri: object) -> Path:
    parsed = urlsplit(str(uri))
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        raise ValueError("client root is not a plain file URI")
    uri_path = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
    return canonical_project_root(Path(url2pathname(uri_path)))


def _roots_unavailable(
    runtime: ServerRuntime, operation: str
) -> dict[str, object]:
    return OperationResult.failure(
        operation,
        "MCP_ROOTS_UNAVAILABLE",
        "MCP client roots are unavailable",
        {"boundProjectRoot": str(runtime.project_root)},
    ).to_dict()


def create_server(
    project_root: Path, data_root: Path, session_id: str | None = None
) -> FastMCP:
    """Create a FastMCP server permanently bound to one project runtime."""
    runtime = ServerRuntime.create(project_root, data_root, session_id)
    mcp = FastMCP(_SERVER_NAME, instructions=_SERVER_INSTRUCTIONS)

    @mcp.tool(name="stm32_doctor")
    async def stm32_doctor(ctx: Context) -> dict[str, object]:
        return await tool_doctor_for_request(runtime, ctx)

    @mcp.tool(name="stm32_project_detect")
    async def stm32_project_detect(ctx: Context) -> dict[str, object]:
        return await tool_project_detect_for_request(runtime, ctx)

    @mcp.tool(name="stm32_project_context")
    async def stm32_project_context(ctx: Context) -> dict[str, object]:
        return await tool_project_context_for_request(runtime, ctx)

    @mcp.tool(name="stm32_keil_inspect")
    async def stm32_keil_inspect(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        includeBaseline: bool = True,
    ) -> dict[str, object]:
        return await tool_keil_inspect_for_request(
            runtime, ctx, uvprojx, targetName, includeBaseline
        )

    @mcp.tool(name="stm32_keil_convert")
    async def stm32_keil_convert(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        planId: str | None = None,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_keil_convert_for_request(
            runtime, ctx, uvprojx, targetName, planId, authorized
        )

    @mcp.tool(name="stm32_project_configure")
    async def stm32_project_configure(
        ctx: Context,
        planId: str | None = None,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_project_configure_for_request(runtime, ctx, planId, authorized)

    @mcp.tool(name="stm32_build")
    async def stm32_build(
        ctx: Context,
        preset: Literal["arm-debug", "arm-release"],
        clean: bool = False,
        timeoutSeconds: Annotated[int, Field(ge=1, le=3600)] = 300,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_build_for_request(
            runtime, ctx, preset, clean, timeoutSeconds, authorized
        )

    return mcp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stm32-toolkit-mcp")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--session-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the project-bound MCP server on the stdio protocol transport."""
    args = _build_parser().parse_args(argv)
    try:
        mcp = create_server(args.project_root, args.data_root, args.session_id)
        mcp.run(transport="stdio")
    except Exception as error:
        print(f"stm32-toolkit-mcp: startup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
