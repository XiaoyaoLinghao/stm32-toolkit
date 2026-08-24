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

EXPECTED_MCP_TOOL_MAP = {
    "doctor": "stm32_doctor",
    "project_detect": "stm32_project_detect",
    "project_context": "stm32_project_context",
    "project_create_plan": "stm32_project_create_plan",
    "project_create_prepare": "stm32_project_create_prepare",
    "project_create_apply": "stm32_project_create_apply",
    "project_regenerate_plan": "stm32_project_regenerate_plan",
    "project_regenerate_prepare": "stm32_project_regenerate_prepare",
    "project_regenerate_apply": "stm32_project_regenerate_apply",
    "keil_inspect": "stm32_keil_inspect",
    "keil_convert": "stm32_keil_convert",
    "project_configure": "stm32_project_configure",
    "build": "stm32_build",
    "probe_list": "stm32_probe_list",
    "flash": "stm32_flash",
    "debug_handoff_begin": "stm32_debug_handoff_begin",
    "debug_handoff_end": "stm32_debug_handoff_end",
    "variable_read": "stm32_variable_read",
    "variable_sample": "stm32_variable_sample",
    "register_read": "stm32_register_read",
    "fault_analyze": "stm32_fault_analyze",
    "diagnostic_start": "stm32_diagnostic_start",
    "diagnostic_show": "stm32_diagnostic_show",
    "diagnostic_begin": "stm32_diagnostic_begin",
    "diagnostic_hypothesis_add": "stm32_diagnostic_hypothesis_add",
    "diagnostic_hypothesis_assess": "stm32_diagnostic_hypothesis_assess",
    "diagnostic_plan_add": "stm32_diagnostic_plan_add",
    "diagnostic_plan_run": "stm32_diagnostic_plan_run",
    "test_target_replay": "stm32_test_target_replay",
    "diagnostic_source_change_declare": "stm32_diagnostic_source_change_declare",
    "diagnostic_verification_plan_add": "stm32_diagnostic_verification_plan_add",
    "diagnostic_verification_start": "stm32_diagnostic_verification_start",
    "diagnostic_marker_attach": "stm32_diagnostic_marker_attach",
    "diagnostic_verification_complete": "stm32_diagnostic_verification_complete",
    "diagnostic_verification_show": "stm32_diagnostic_verification_show",
    "test_host_discover": "stm32_test_host_discover",
    "test_host_run": "stm32_test_host_run",
    "test_show": "stm32_test_show",
    "test_target_prepare": "stm32_test_target_prepare",
    "test_target_execute": "stm32_test_target_execute",
    "acceptance_scenario_describe": "stm32_acceptance_scenario_describe",
    "acceptance_scenario_record": "stm32_acceptance_scenario_record",
    "acceptance_scenario_show": "stm32_acceptance_scenario_show",
    "acceptance_attempt_begin": "stm32_acceptance_attempt_begin",
    "acceptance_attempt_checkpoint": "stm32_acceptance_attempt_checkpoint",
    "acceptance_attempt_authorize_source_change": "stm32_acceptance_attempt_authorize_source_change",
    "acceptance_attempt_show": "stm32_acceptance_attempt_show",
    "acceptance_attempt_resume": "stm32_acceptance_attempt_resume",
}
EXPECTED_SKILLS = (
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor",
)


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


def test_current_monitor_ui_lock_and_fixtures_match_the_release_identity() -> None:
    lock = json.loads(
        (REPO_ROOT / "tools/stm32-monitor/ui/package-lock.json").read_text("utf-8")
    )
    assert lock["version"] == __version__
    assert lock["packages"][""]["version"] == __version__
    for path in (
        REPO_ROOT / "tools/stm32-monitor/ui/e2e/fake_runtime.py",
        REPO_ROOT / "tools/stm32-monitor/ui/tests/main.test.tsx",
        REPO_ROOT / "tools/stm32-monitor/ui/tests/bootstrap.test.ts",
    ):
        content = path.read_text("utf-8")
        assert "0.9.0" in content
        assert "0.5.0" not in content


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


def test_production_inventory_and_server_registration_match_an_independent_oracle(
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
    assert dict(MCP_TOOL_NAMES) == EXPECTED_MCP_TOOL_MAP
    assert set(MCP_TOOL_NAMES.values()) == set(EXPECTED_MCP_TOOL_MAP.values())
    assert actual == set(EXPECTED_MCP_TOOL_MAP.values())
    assert tuple(SKILL_NAMES) == EXPECTED_SKILLS
