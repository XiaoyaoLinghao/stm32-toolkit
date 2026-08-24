from __future__ import annotations

import asyncio
import json
import sys
import tomllib
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.public_inventory import (
    MCP_TOOL_NAMES,
    REQUIRED_PYTHON,
    SKILL_NAMES,
    SUPPORTED_PYTHON,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_release_python_and_static_package_versions_are_one_contract(tmp_path: Path) -> None:
    toolkit = tomllib.loads(
        (REPO_ROOT / "tools/stm32-toolkit/pyproject.toml").read_text("utf-8")
    )
    monitor = tomllib.loads(
        (REPO_ROOT / "tools/stm32-monitor/pyproject.toml").read_text("utf-8")
    )
    plugin = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text("utf-8"))
    ui = json.loads(
        (REPO_ROOT / "tools/stm32-monitor/ui/package.json").read_text("utf-8")
    )
    assert __version__ == "0.9.0"
    assert REQUIRED_PYTHON == ">=3.12,<3.13"
    assert SUPPORTED_PYTHON == (3, 12)
    assert toolkit["project"]["version"] == __version__
    assert toolkit["project"]["requires-python"] == REQUIRED_PYTHON
    assert monitor["project"]["version"] == __version__
    assert monitor["project"]["requires-python"] == REQUIRED_PYTHON
    assert monitor["project"]["dependencies"][0] == f"stm32-toolkit=={__version__}"
    assert plugin["version"] == ui["version"] == __version__


def test_actual_mcp_and_skill_inventory_matches_the_closed_public_inventory(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    actual = {
        tool.name
        for tool in asyncio.run(
            create_server(project, tmp_path / "data", "session-a").list_tools()
        )
    }
    discovered = {
        path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")
    }
    assert len(MCP_TOOL_NAMES) == 48
    assert actual == set(MCP_TOOL_NAMES.values())
    assert len(SKILL_NAMES) == 8
    assert discovered == set(SKILL_NAMES)
