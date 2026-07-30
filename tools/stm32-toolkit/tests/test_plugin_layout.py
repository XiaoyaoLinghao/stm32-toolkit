from __future__ import annotations

import json
import os
import subprocess
import venv
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.context import build_project_context


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MCP_CONFIG = REPO_ROOT / ".mcp.json"
LAUNCHER = REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd"
SETUP_SKILL = REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md"
README = REPO_ROOT / "README.md"
LOGICAL_PROJECT_ID = "12345678-1234-5678-1234-567812345678"


def test_plugin_manifest_uses_standard_skill_discovery_and_version():
    plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

    assert plugin == {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": "stm32-toolkit",
        "version": "0.2.0",
        "description": (
            "AI-assisted STM32 migration, development, test, debug, and live "
            "monitoring toolkit"
        ),
        "author": {"name": "STM32 Toolkit Team"},
    }
    assert plugin["version"] == __version__ == "0.2.0"


def test_mcp_config_binds_only_the_plugin_launcher_to_claude_roots():
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))

    assert list(config) == ["mcpServers"]
    assert list(config["mcpServers"]) == ["stm32-toolkit"]
    server = config["mcpServers"]["stm32-toolkit"]
    assert server == {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/stm32-toolkit-mcp.cmd",
        "args": [
            "--project-root",
            "${CLAUDE_PROJECT_DIR}",
            "--data-root",
            "${CLAUDE_PLUGIN_DATA}",
        ],
        "env": {
            "STM32_TOOLKIT_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
            "STM32_TOOLKIT_DATA_ROOT": "${CLAUDE_PLUGIN_DATA}",
            "STM32_TOOLKIT_PROJECT_ROOT": "${CLAUDE_PROJECT_DIR}",
        },
    }

    joined = " ".join([server["command"], *server["args"], *server["env"].values()])
    assert "D:/" not in joined
    assert "C:/" not in joined
    assert "python" not in server["command"].lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_launcher_reports_missing_environment_without_interpreter_fallback(tmp_path: Path):
    fake_path = tmp_path / "fake-path"
    fake_path.mkdir()
    marker = tmp_path / "fallback-used.txt"
    for name in ("python.cmd", "py.cmd", "uv.cmd"):
        (fake_path / name).write_text(
            f'@echo fallback>"{marker}"\r\n@exit /b 0\r\n',
            encoding="utf-8",
        )

    environment = os.environ.copy()
    environment.pop("CLAUDE_PLUGIN_DATA", None)
    environment["PATH"] = str(fake_path)
    result = _run_launcher(environment, "--sentinel")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "/setup-stm32-env" in result.stderr
    assert "CLAUDE_PLUGIN_DATA" in result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_launcher_reports_missing_versioned_runtime_without_interpreter_fallback(
    tmp_path: Path,
):
    plugin_data = tmp_path / "plugin data"
    fake_path = tmp_path / "fake-path"
    fake_path.mkdir()
    marker = tmp_path / "fallback-used.txt"
    for name in ("python.cmd", "py.cmd", "uv.cmd"):
        (fake_path / name).write_text(
            f'@echo fallback>"{marker}"\r\n@exit /b 0\r\n',
            encoding="utf-8",
        )

    environment = os.environ.copy()
    environment["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    environment["PATH"] = str(fake_path)
    result = _run_launcher(environment, "--sentinel")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "/setup-stm32-env" in result.stderr
    assert "runtime/0.2.0/Scripts/python.exe" in result.stderr.replace("\\", "/")
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_launcher_forwards_arguments_and_preserves_runtime_exit_code(tmp_path: Path):
    plugin_data = tmp_path / "plugin data"
    runtime = plugin_data / "runtime" / "0.2.0"
    venv.EnvBuilder(with_pip=False).create(runtime)
    module_root = tmp_path / "stub module"
    package = module_root / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "mcp_server.py").write_text(
        "import json, sys\n"
        "print(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(23)\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    environment["PYTHONPATH"] = str(module_root)
    result = _run_launcher(
        environment,
        "--project-root",
        str(tmp_path / "project with spaces"),
        "--data-root",
        str(plugin_data),
        "--session-id",
        "session-a",
    )

    assert result.returncode == 23
    assert json.loads(result.stdout) == [
        "--project-root",
        str(tmp_path / "project with spaces"),
        "--data-root",
        str(plugin_data),
        "--session-id",
        "session-a",
    ]
    assert result.stderr == ""


def test_setup_skill_has_an_explicit_read_only_check_and_authorized_mutation_contract():
    skill = SETUP_SKILL.read_text(encoding="utf-8")
    normalized = skill.replace("\\", "/")
    command_blocks = "\n".join(_fenced_blocks(skill))

    assert skill.startswith(
        "---\n"
        "name: setup-stm32-env\n"
        "description: Use when"
    )
    assert "## CHECK" in skill
    assert "## MUTATE" in skill
    assert skill.index("## CHECK") < skill.index("## MUTATE")
    for phrase in (
        "read-only",
        "offline",
        "explicit authorization",
        "${CLAUDE_PLUGIN_DATA}/runtime/0.2.0",
        "${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit",
        "Host Python 3.10+",
        "ARM GCC",
        "ARM GDB",
        "CMake",
        "Ninja",
        "PyOCD",
        "CubeMX",
        "VS Code",
        "CMSIS-Pack",
        "user-created",
    ):
        assert phrase in skill
    assert "-m stm32_toolkit.cli" in skill
    assert "doctor --json" in skill
    assert "plugin-bundled `.mcp.json`" in skill

    for prohibited_command in (
        "pyocd list",
        "pyocd pack install",
        "claude mcp add",
        "code --install-extension",
    ):
        assert prohibited_command not in command_blocks
    for forbidden_hardcoding in ("STM32F4", "STM32F429", "DAP-Link", "motor_status", "can_bus"):
        assert forbidden_hardcoding not in skill
    assert "pip install cmake" not in normalized
    assert "pip install ninja" not in normalized
    assert "pip install pyocd" not in normalized


def test_readme_documents_the_foundation_contract_without_follow_on_claims():
    readme = README.read_text(encoding="utf-8")

    assert "AI-assisted STM32 coding, debugging, testing, and monitoring" in readme
    for phrase in (
        "user scope",
        "/setup-stm32-env",
        "automatically",
        "${CLAUDE_PROJECT_DIR}",
        ".stm32-project.json",
        "${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>",
        "doctor --json",
        "Keil-to-GCC",
        "one-way",
        "user-created monitor groups",
        "Foundation",
        "Follow-on",
    ):
        assert phrase in readme
    for stale_claim in (
        "motor_status",
        "can_bus",
        "localhost:8888",
        "pyocd-debug-mcp",
        "cp -r stm32-toolkit/skills",
    ):
        assert stale_claim not in readme


def test_two_configured_clones_use_distinct_workspaces_without_project_mutation(
    tmp_path: Path,
):
    first = tmp_path / "clone-a"
    second = tmp_path / "clone-b"
    for root in (first, second):
        _write_configured_project(root)
    data_root = tmp_path / "plugin-data"
    first_before = _project_snapshot(first)
    second_before = _project_snapshot(second)

    first_result = build_project_context(first, data_root, "session-a")
    second_result = build_project_context(second, data_root, "session-b")

    assert first_result.ok is True
    assert second_result.ok is True
    first_workspace = first_result.data["workspace"]
    second_workspace = second_result.data["workspace"]
    assert first_workspace["workspaceId"] != second_workspace["workspaceId"]
    assert first_workspace["sessionId"] == "session-a"
    assert second_workspace["sessionId"] == "session-b"
    first_root = data_root / "projects" / first_workspace["workspaceId"]
    second_root = data_root / "projects" / second_workspace["workspaceId"]
    assert first_root != second_root
    assert (first_root / "sessions" / "session-a").is_dir()
    assert (second_root / "sessions" / "session-b").is_dir()
    assert _project_snapshot(first) == first_before
    assert _project_snapshot(second) == second_before


def _run_launcher(environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    command_processor = os.environ.get("COMSPEC", "cmd.exe")
    return subprocess.run(
        [command_processor, "/d", "/c", str(LAUNCHER), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _fenced_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    parts = markdown.split("```")
    for index in range(1, len(parts), 2):
        block = parts[index]
        blocks.append(block.split("\n", 1)[1] if "\n" in block else "")
    return blocks


def _write_configured_project(root: Path) -> None:
    root.mkdir()
    (root / "App").mkdir()
    (root / "App" / "main.c").write_text(
        "int main(void) { return 0; }\n", encoding="utf-8"
    )
    (root / ".stm32-project.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "logicalProjectId": LOGICAL_PROJECT_ID,
                "project": {"name": "fixture", "origin": "manual"},
                "target": {"device": "STM32H743ZI", "core": "cortex-m7"},
                "framework": {"type": "hal", "version": None},
                "build": {
                    "sources": ["App/main.c"],
                    "includePaths": [],
                    "defines": [],
                    "compileOptions": [],
                    "assemblySources": [],
                },
                "debug": {"backend": "pyocd", "target": "stm32h743zi", "svd": None},
            }
        ),
        encoding="utf-8",
    )


def _project_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
