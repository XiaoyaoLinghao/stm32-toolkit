from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from mcp.server.fastmcp import Context, FastMCP

from stm32_toolkit.context import build_project_context
from stm32_toolkit.detection import detect_project
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.identity import canonical_project_root, new_session_id
from stm32_toolkit.paths import require_safe_session_id
from stm32_toolkit.result import OperationResult


_SERVER_NAME = "STM32 Toolkit"
_SERVER_INSTRUCTIONS = (
    "This server is permanently bound to one project root and exposes only "
    "read-only STM32 Toolkit foundation tools."
)


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

    try:
        result = await session.list_roots()
        roots = result.roots
        if not roots:
            raise ValueError("client advertised roots but returned none")
        canonical_roots = tuple(_canonical_client_root(root.uri) for root in roots)
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
