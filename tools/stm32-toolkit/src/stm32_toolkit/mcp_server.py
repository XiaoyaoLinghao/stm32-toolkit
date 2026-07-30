from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

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


def create_server(
    project_root: Path, data_root: Path, session_id: str | None = None
) -> FastMCP:
    """Create a FastMCP server permanently bound to one project runtime."""
    runtime = ServerRuntime.create(project_root, data_root, session_id)
    mcp = FastMCP(_SERVER_NAME, instructions=_SERVER_INSTRUCTIONS)

    @mcp.tool(name="stm32_doctor")
    def stm32_doctor() -> dict[str, object]:
        return tool_doctor(runtime)

    @mcp.tool(name="stm32_project_detect")
    def stm32_project_detect() -> dict[str, object]:
        return tool_project_detect(runtime)

    @mcp.tool(name="stm32_project_context")
    def stm32_project_context() -> dict[str, object]:
        return tool_project_context(runtime)

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
