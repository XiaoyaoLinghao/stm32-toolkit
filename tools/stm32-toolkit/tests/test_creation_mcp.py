from __future__ import annotations

import asyncio
from pathlib import Path

from stm32_toolkit.mcp_server import create_server


def test_mcp_creation_plan_has_closed_agent_neutral_arguments(tmp_path: Path):
    server = create_server(tmp_path, tmp_path.parent / "data", "session")
    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "stm32_project_create_plan")
    assert set(tool.inputSchema.get("properties", {})) == {"sourceKind", "source", "destination", "framework", "language"}
    assert "projectRoot" not in tool.inputSchema.get("properties", {})
    assert "supportProfile" not in tool.inputSchema.get("properties", {})
