from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import setuptools
import wheel


REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "bin" / "setup-stm32-env.ps1"
EXPECTED_SKILL = "/stm32-toolkit:setup-stm32-env"


pytestmark = pytest.mark.skipif(os.name != "nt", reason="PowerShell runtime setup")


def test_check_reports_broken_runtime_as_structured_evidence(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime_python = plugin_data / "runtime" / "0.2.0" / "Scripts" / "python.exe"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_bytes(b"not an executable")

    result = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["runtime"]["present"] is True
    assert payload["runtime"]["version"] is None
    assert payload["runtime"]["error"]
    assert payload["authorizationRequired"] is True
    assert payload["recommendedMode"] == "Repair"


def test_failed_bootstrap_removes_staging_and_never_promotes(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    plugin_data = tmp_path / "plugin-data"

    result = _run_helper("Bootstrap", plugin_root, plugin_data, project, timeout=90)

    assert result.returncode != 0
    assert not (plugin_data / "runtime" / "0.2.0").exists()
    staging = plugin_data / "runtime" / ".staging"
    assert not staging.exists() or not any(staging.iterdir())
    assert not any(project.iterdir())


def test_bootstrap_and_repair_are_staged_versioned_and_project_read_only(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    project_marker = project / "keep.txt"
    project_marker.write_text("unchanged", encoding="utf-8")
    plugin_root = tmp_path / "plugin"
    _write_stub_plugin(plugin_root)
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PYTHONPATH"] = _copy_build_support(tmp_path)

    bootstrap = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project, environment=environment, timeout=180
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    runtime = plugin_data / "runtime" / "0.2.0"
    assert (runtime / "Scripts" / "python.exe").is_file()
    assert project_marker.read_text(encoding="utf-8") == "unchanged"
    assert not (plugin_data / "runtime" / ".staging").exists() or not any(
        (plugin_data / "runtime" / ".staging").iterdir()
    )

    installed_package = next((runtime / "Lib" / "site-packages").glob("stm32_toolkit"))
    shutil.rmtree(installed_package)
    broken = _run_helper("Check", plugin_root, plugin_data, project, environment=environment)
    assert json.loads(broken.stdout)["runtime"]["status"] == "broken"

    repair = _run_helper("Repair", plugin_root, plugin_data, project, environment=environment, timeout=180)
    assert repair.returncode == 0, repair.stderr
    healthy = _run_helper("Check", plugin_root, plugin_data, project, environment=environment)
    assert json.loads(healthy.stdout)["runtime"]["status"] == "healthy"
    quarantine = plugin_data / "runtime" / ".quarantine"
    assert any(path.name.startswith("0.2.0-") for path in quarantine.iterdir())
    assert project_marker.read_text(encoding="utf-8") == "unchanged"


def test_check_bounds_a_hanging_bootstrap_python(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    startup = tmp_path / "startup"
    startup.mkdir()
    (startup / "sitecustomize.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    environment = _clean_environment()
    environment["PYTHONPATH"] = str(startup)

    result = _run_helper(
        "Check", REPO_ROOT, plugin_data, project, environment=environment, timeout=15
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["bootstrapPython"]["status"] == "timeout"
    assert not plugin_data.exists()


def test_setup_contract_uses_namespaced_skill_and_ignores_coverage_data():
    launcher = (REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md").read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert EXPECTED_SKILL in launcher
    assert EXPECTED_SKILL in readme
    assert "/setup-stm32-env" not in launcher.replace(EXPECTED_SKILL, "")
    assert "/setup-stm32-env" not in readme.replace(EXPECTED_SKILL, "")
    assert "Repair" in skill
    assert "staging" in skill
    assert "quarantine" in skill
    assert ".coverage" in gitignore
    assert ".coverage.*" in gitignore


def _copy_build_support(tmp_path: Path) -> str:
    support = tmp_path / "build-support"
    support.mkdir()
    site_packages = Path(setuptools.__file__).parent.parent
    names = ["setuptools", "_distutils_hack", "pkg_resources", "wheel"]
    names.extend(path.name for pattern in ("setuptools-*.dist-info", "wheel-*.dist-info") for path in site_packages.glob(pattern))
    for name in names:
        source = site_packages / name
        if source.exists():
            shutil.copytree(source, support / name)
    return str(support)

def _write_stub_plugin(plugin_root: Path) -> None:
    package_root = plugin_root / "tools" / "stm32-toolkit"
    module = package_root / "stm32_toolkit"
    module.mkdir(parents=True)
    (package_root / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(name='stm32-toolkit', version='0.2.0', packages=['stm32_toolkit'])\n",
        encoding="utf-8",
    )
    (module / "__init__.py").write_text("__version__ = '0.2.0'\n", encoding="utf-8")
    (module / "cli.py").write_text(
        "import json, sys\n"
        "if sys.argv[1:] == ['version']:\n"
        "    print('0.2.0')\n"
        "elif 'doctor' in sys.argv:\n"
        "    print(json.dumps({'protocol': 'stm32-toolkit/1', 'ok': True}))\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )

def _run_helper(
    mode: str,
    plugin_root: Path,
    plugin_data: Path,
    project: Path,
    *,
    environment: dict[str, str] | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HELPER),
            "-Mode",
            mode,
            "-PluginRoot",
            str(plugin_root),
            "-PluginData",
            str(plugin_data),
            "-ProjectDir",
            str(project),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment or _clean_environment(),
        timeout=timeout,
    )


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR"):
        environment.pop(name, None)
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), str(Path(os.environ["SystemRoot"]) / "System32")]
    )
    return environment