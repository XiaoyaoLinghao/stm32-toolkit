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
MARKETPLACE_MANIFEST = REPO_ROOT / ".claude-plugin" / "marketplace.json"
MCP_CONFIG = REPO_ROOT / ".mcp.json"
LAUNCHER = REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd"
MONITOR_LAUNCHER = REPO_ROOT / "bin" / "stm32-monitor.cmd"
SETUP_SKILL = REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md"
SETUP_HELPER = REPO_ROOT / "bin" / "setup-stm32-env.ps1"
FOLLOW_ON_SKILLS = REPO_ROOT / "requirements" / "follow-on-skills"
README = REPO_ROOT / "README.md"
LOGICAL_PROJECT_ID = "12345678-1234-5678-1234-567812345678"
LEGACY_SKILLS = {
    "init-stm32-project",
    "migrate-keil",
    "read-var",
    "stm32-monitor",
}


def test_plugin_manifest_uses_standard_skill_discovery_and_version():
    plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

    assert plugin == {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": "stm32-toolkit",
        "version": "0.9.0",
        "description": (
            "AI-assisted STM32 development with read-only Keil inspection, "
            "guarded ARMCC-to-GCC conversion, managed GCC/CMake configuration, "
            "reproducible builds, probe flashing, and typed debugging"
        ),
        "author": {"name": "STM32 Toolkit Team"},
    }
    assert plugin["version"] == __version__ == "0.9.0"


def test_marketplace_manifest_uses_a_supported_plugin_source():
    """Regression (STM32TK-0306 revision 1): Claude Code 2.1.140 rejects the
    bare ``.`` plugin source; the repo-relative ``./`` form is the supported
    structure for a marketplace whose plugin is its own repository root."""
    marketplace = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )

    assert list(marketplace) == ["name", "owner", "description", "plugins"]
    assert marketplace["name"] == "stm32-toolkit"
    entry = marketplace["plugins"][0]
    assert entry["name"] == "stm32-toolkit"
    assert entry["source"] == "./"
    assert "repository" in entry


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
            "STM32_TOOLKIT_DATA_ROOT": "${CLAUDE_PLUGIN_DATA}",
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
    environment.pop("STM32_TOOLKIT_DATA_ROOT", None)
    environment["PATH"] = str(fake_path)
    result = _run_launcher(environment, "--sentinel")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "STM32_TOOLKIT_DATA_ROOT" in result.stderr
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
    environment["STM32_TOOLKIT_DATA_ROOT"] = str(plugin_data)
    environment["PATH"] = str(fake_path)
    result = _run_launcher(environment, "--sentinel")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "STM32_TOOLKIT_DATA_ROOT" in result.stderr
    assert "runtime/0.9.0/Scripts/python.exe" in result.stderr.replace("\\", "/")
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_launcher_forwards_arguments_and_preserves_runtime_exit_code(tmp_path: Path):
    plugin_data = tmp_path / "plugin data"
    runtime = plugin_data / "runtime" / "0.9.0"
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
    environment["STM32_TOOLKIT_DATA_ROOT"] = str(plugin_data)
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


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_monitor_launcher_reports_missing_environment_without_interpreter_fallback(
    tmp_path: Path,
):
    fake_path = tmp_path / "fake-path"
    fake_path.mkdir()
    marker = tmp_path / "fallback-used.txt"
    for name in ("python.cmd", "py.cmd", "uv.cmd"):
        (fake_path / name).write_text(
            f'@echo fallback>"{marker}"\r\n@exit /b 0\r\n',
            encoding="utf-8",
        )

    environment = os.environ.copy()
    environment.pop("STM32_TOOLKIT_DATA_ROOT", None)
    environment["PATH"] = str(fake_path)
    result = _run_monitor_launcher(environment, "open", "--help")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "stm32-monitor" in result.stderr
    assert "STM32_TOOLKIT_DATA_ROOT" in result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_monitor_launcher_reports_missing_versioned_runtime_without_interpreter_fallback(
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
    environment["STM32_TOOLKIT_DATA_ROOT"] = str(plugin_data)
    environment["PATH"] = str(fake_path)
    result = _run_monitor_launcher(environment, "open", "--help")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "stm32-monitor" in result.stderr
    assert "runtime/0.9.0/Scripts/python.exe" in result.stderr.replace("\\", "/")
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd.exe launcher")
def test_monitor_launcher_forwards_arguments_and_preserves_runtime_exit_code(
    tmp_path: Path,
):
    plugin_data = tmp_path / "plugin data"
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=False).create(runtime)
    module_root = tmp_path / "stub module"
    package = module_root / "stm32_monitor"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, sys\n"
        "print(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(19)\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["STM32_TOOLKIT_DATA_ROOT"] = str(plugin_data)
    environment["PYTHONPATH"] = str(module_root)
    result = _run_monitor_launcher(
        environment,
        "open",
        "--project",
        str(tmp_path / "project with spaces"),
        "--data-root",
        str(plugin_data),
    )

    assert result.returncode == 19
    assert json.loads(result.stdout) == [
        "open",
        "--project",
        str(tmp_path / "project with spaces"),
        "--data-root",
        str(plugin_data),
    ]


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
        "${CLAUDE_PLUGIN_DATA}/runtime/0.9.0",
        "${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit",
        "CPython >=3.12,<3.13",
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


def test_exactly_eight_release_skills_are_discovered_and_follow_on_sources_are_preserved():
    discovered = {
        path.parent.name
        for path in (REPO_ROOT / "skills").glob("*/SKILL.md")
    }
    preserved = {
        path.parent.name
        for path in FOLLOW_ON_SKILLS.glob("*/SKILL.md")
    }

    assert discovered == {
        "setup-stm32-env",
        "migrate-keil",
        "configure-stm32-project",
        "build-firmware",
        "flash-firmware",
        "debug-firmware",
        "read-var",
        "stm32-monitor",
    }
    assert preserved == LEGACY_SKILLS


def test_monitor_skill_is_thin_explicit_and_launcher_bound():
    skill = (
        REPO_ROOT / "skills" / "stm32-monitor" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert skill.startswith("---\nname: stm32-monitor\n")
    assert "stm32_project_context" in skill
    assert "observation-only" in skill
    assert "zero presets" in skill
    assert "never connects a probe or starts sampling automatically" in skill
    assert "explicit request to open" in skill
    assert "bin/stm32-monitor.cmd" in skill
    assert "open --project" in skill
    assert "--data-root" in skill
    assert "${CLAUDE_PLUGIN_ROOT}" in skill
    assert "${CLAUDE_PLUGIN_DATA}" in skill
    assert "${CLAUDE_PROJECT_DIR}" in skill
    assert "Never print, persist, copy, or log the fragment URL" in skill
    assert "explicit page actions" in skill


def test_hardware_skills_are_thin_project_bound_mcp_workflows():
    expected_tools = {
        "flash-firmware": {"stm32_project_context", "stm32_probe_list", "stm32_flash"},
        "debug-firmware": {
            "stm32_project_context",
            "stm32_probe_list",
            "stm32_debug_handoff_begin",
            "stm32_debug_handoff_end",
            "stm32_register_read",
            "stm32_fault_analyze",
        },
        "read-var": {
            "stm32_project_context",
            "stm32_probe_list",
            "stm32_variable_read",
            "stm32_variable_sample",
        },
    }
    forbidden = ("raw address", "target override", "SVD override", "physical gate passed")

    for skill_name, tools in expected_tools.items():
        skill = (REPO_ROOT / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert skill.startswith(f"---\nname: {skill_name}\n")
        for tool in tools:
            assert tool in skill
        assert "exact probe" in skill.lower()
        assert "buildId" in skill
        assert "ELF SHA-256" in skill
        assert "never fabricate" in skill.lower()
        for phrase in forbidden:
            assert phrase.lower() not in skill.lower()

    assert "explicit authorization" in (
        REPO_ROOT / "skills" / "flash-firmware" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "explicit authorization" in (
        REPO_ROOT / "skills" / "debug-firmware" / "SKILL.md"
    ).read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="PowerShell setup helper")
def test_setup_helper_uses_explicit_paths_without_ambient_environment(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    environment = _environment_without_claude_plugin_paths()
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SETUP_HELPER),
            "-Mode",
            "Check",
            "-ToolkitRoot",
            str(REPO_ROOT),
            "-DataRoot",
            str(plugin_data),
            "-ProjectRoot",
            str(project),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "CHECK"
    assert payload["runtime"]["path"].endswith("/runtime/0.9.0")
    assert payload["project"] == project.as_posix()
    assert payload["mutated"] is False
    assert not plugin_data.exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell setup helper")
def test_setup_helper_rejects_unresolved_inline_paths_before_mutation(tmp_path: Path):
    environment = _environment_without_claude_plugin_paths()
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SETUP_HELPER),
            "-Mode",
            "Bootstrap",
            "-ToolkitRoot",
            "${CLAUDE_PLUGIN_ROOT}",
            "-DataRoot",
            str(tmp_path / "${CLAUDE_PLUGIN_DATA}"),
            "-ProjectRoot",
            "${CLAUDE_PROJECT_DIR}",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode != 0
    assert "unresolved path placeholder" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_setup_skill_passes_inline_claude_paths_explicitly_without_ambient_variables():
    skill = SETUP_SKILL.read_text(encoding="utf-8")
    command_blocks = "\n".join(_fenced_blocks(skill))

    assert "$env:CLAUDE_PLUGIN_" not in skill
    assert "powershell.exe" in command_blocks
    assert "-File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1'" in command_blocks
    for argument in (
        "-ToolkitRoot '${CLAUDE_PLUGIN_ROOT}'",
        "-DataRoot '${CLAUDE_PLUGIN_DATA}'",
        "-ProjectRoot '${CLAUDE_PROJECT_DIR}'",
    ):
        assert argument in command_blocks
    assert "PowerShell" in skill
    assert "Git Bash" in skill

def test_readme_documents_the_vs09a_contract_and_vs09b_boundary():
    readme = README.read_text(encoding="utf-8")
    readme_zh = (REPO_ROOT / "README_zh-CN.md").read_text(encoding="utf-8")

    assert "local 0.9.0 VS09-A candidate" in readme
    assert "CPython `>=3.12,<3.13`" in readme
    assert "DATA_ROOT/runtime/0.9.0" in readme
    assert '"STM32_TOOLKIT_DATA_ROOT"' in readme
    assert "absolute launcher" in readme
    assert "all 48" in readme
    assert "VS09-B" in readme
    expected_build = "stm32-toolkit --project-root C:\\work\\blinky build --preset arm-debug --json"
    assert expected_build in readme
    assert expected_build in readme_zh
    for phrase in (
        "/stm32-toolkit:setup-stm32-env",
        "automatically",
        "${CLAUDE_PROJECT_DIR}",
        ".stm32-project.json",
        "${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>",
        "doctor --json",
        "Keil-to-GCC",
        "one-way",
        "user-created monitor groups",
    ):
        assert phrase in readme
    for stale_claim in (
        "motor_status",
        "can_bus",
        "localhost:8888",
        "pyocd-debug-mcp",
        "cp -r stm32-toolkit/skills",
        "exactly 15",
        "runtime/0.5.0",
        "Host Python 3.10",
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
    assert first_result.data["project"]["root"] == str(first.resolve())
    assert second_result.data["project"]["root"] == str(second.resolve())
    first_workspace = first_result.data["workspace"]
    second_workspace = second_result.data["workspace"]
    assert first_workspace["workspaceId"] != second_workspace["workspaceId"]
    assert first_workspace["sessionId"] == "session-a"
    assert second_workspace["sessionId"] == "session-b"
    # WorkspacePaths keeps the full identity in evidence but uses its stable
    # 24-character storage key on disk.
    first_root = data_root / "projects" / first_workspace["workspaceId"][:24]
    second_root = data_root / "projects" / second_workspace["workspaceId"][:24]
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


def _run_monitor_launcher(
    environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    command_processor = os.environ.get("COMSPEC", "cmd.exe")
    return subprocess.run(
        [command_processor, "/d", "/c", str(MONITOR_LAUNCHER), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _environment_without_claude_plugin_paths() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_PLUGIN_DATA",
        "CLAUDE_PROJECT_DIR",
        "STM32_TOOLKIT_DATA_ROOT",
    ):
        environment.pop(name, None)
    return environment

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
                "schemaVersion": 2,
                "logicalProjectId": LOGICAL_PROJECT_ID,
                "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
                "project": {"name": "fixture", "origin": "manual"},
                "target": {"device": "STM32H743ZI", "core": "cortex-m7"},
                "framework": {"type": "hal", "version": None},
                "build": {
                    "sources": ["App/main.c"],
                    "includePaths": [],
                    "defines": [],
                    "compileOptions": [],
                    "assemblySources": [],
                    "presets": [],
                    "elf": "build/firmware.elf",
                },
                "memory": {"source": "manual", "regions": []},
                "debug": {"backend": "pyocd", "target": "stm32h743zi", "svd": None},
                "generation": {
                    "cubeMxIoc": None,
                    "managedManifest": ".stm32-toolkit/generated-files.json",
                    "generatedDirectories": [],
                    "userDirectories": [],
                },
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


def test_unified_0_9_0_runtime_version_across_launcher_setup_and_skill():
    """No launcher/helper/Skill selects a legacy runtime."""
    launcher = LAUNCHER.read_text(encoding="utf-8")
    monitor_launcher = MONITOR_LAUNCHER.read_text(encoding="utf-8")
    helper = SETUP_HELPER.read_text(encoding="utf-8")
    skill = SETUP_SKILL.read_text(encoding="utf-8")
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["version"] == __version__ == "0.9.0"
    assert "runtime\\0.9.0\\Scripts\\python.exe" in launcher
    assert "runtime/0.9.0/Scripts/python.exe" in launcher.replace("\\", "/")
    assert "0.3.0" not in launcher
    assert "runtime\\0.9.0\\Scripts\\python.exe" in monitor_launcher
    assert "runtime/0.9.0/Scripts/python.exe" in monitor_launcher.replace("\\", "/")
    assert "0.3.0" not in monitor_launcher
    assert " -m stm32_monitor " in monitor_launcher
    assert '$RuntimeVersion = "0.9.0"' in helper
    assert "0.3.0" in helper  # legacy-upgrade detection, never current selection
    assert '"${package}[probe]"' in helper
    assert "$monitorPackage" in helper
    assert "MonitorValidationScript" in helper
    assert "stm32-monitor" in helper
    assert "ui_dist" in helper
    assert "import pyocd" in helper
    assert '"-I", "-c"' in helper
    assert "${CLAUDE_PLUGIN_DATA}/runtime/0.9.0" in skill
    assert "${CLAUDE_PLUGIN_DATA}/runtime/.staging/0.9.0-<id>" in skill
    assert "tools/stm32-toolkit[probe]" in skill
    assert "isolated PEP 440 `pyocd` distribution check" in skill
    assert ">=0.45.1,<0.46" in skill
    assert "existing 0.3.0 runtime reports broken" in skill
    assert skill.count("0.3.0") == 1
