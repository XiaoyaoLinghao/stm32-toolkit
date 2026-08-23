from __future__ import annotations

import asyncio
from pathlib import Path

from stm32_toolkit.mcp_server import create_server


def test_regeneration_mcp_tools_are_registered_with_strict_input_schemas(tmp_path: Path):
    (tmp_path / "project").mkdir()
    server = create_server(tmp_path / "project", tmp_path / "data", "session")
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"stm32_project_regenerate_plan", "stm32_project_regenerate_prepare", "stm32_project_regenerate_apply"} <= set(tools)
    assert "destination" in tools["stm32_project_regenerate_plan"].inputSchema["properties"]
    assert tools["stm32_project_regenerate_prepare"].inputSchema["additionalProperties"] is False
