from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
import venv
from pathlib import Path

import pytest


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


def test_partial_runtime_directory_is_broken_and_recommends_repair(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    (plugin_data / "runtime" / "0.2.0").mkdir(parents=True)

    result = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["runtime"]["present"] is True
    assert payload["runtime"]["interpreterPresent"] is False
    assert payload["recommendedMode"] == "Repair"

def test_runtime_version_path_file_is_broken_and_recommends_repair(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime_path = plugin_data / "runtime" / "0.2.0"
    runtime_path.parent.mkdir(parents=True)
    runtime_path.write_text("partial", encoding="utf-8")

    result = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["runtime"]["present"] is True
    assert payload["runtime"]["directoryPresent"] is False
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
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\nbuild-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

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


def test_bounded_process_drains_both_streams_without_unbounded_retention(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime = plugin_data / "runtime" / "0.2.0"
    venv.EnvBuilder(with_pip=False).create(runtime)
    module_root = tmp_path / "module"
    package = module_root / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import sys\nsys.stdout.write('o' * 200000)\nsys.stderr.write('e' * 200000)\nraise SystemExit(7)\n",
        encoding="utf-8",
    )
    environment = _clean_environment()
    environment["PYTHONPATH"] = str(module_root)

    result = _run_helper(
        "Check", REPO_ROOT, plugin_data, project, environment=environment, timeout=30
    )

    assert result.returncode == 0, result.stderr
    runtime_evidence = json.loads(result.stdout)["runtime"]
    assert runtime_evidence["status"] == "broken"
    assert len(runtime_evidence["error"]) <= 66000
    helper_source = HELPER.read_text(encoding="utf-8")
    assert "ReadToEndAsync" not in helper_source
    assert "ReadAsync" in helper_source

def test_bootstrap_installs_declared_build_requirements_in_fresh_venv(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project, environment=environment, timeout=180
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "healthy"
    assert payload["runtime"]["version"] == "0.2.0"


def test_healthy_check_preserves_drive_root_argument_and_following_doctor_args(tmp_path: Path):
    bootstrap_project = tmp_path / "project"
    bootstrap_project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\nbuild-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)
    bootstrap = _run_helper(
        "Bootstrap", plugin_root, plugin_data, bootstrap_project,
        environment=environment, timeout=180,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr

    drive_root = Path(tmp_path.anchor)
    checked = _run_helper(
        "Check", plugin_root, plugin_data, drive_root, environment=environment, timeout=30
    )

    assert checked.returncode == 0, checked.stderr
    runtime = json.loads(checked.stdout)["runtime"]
    assert runtime["status"] == "healthy"
    assert runtime["doctor"]["data"]["projectRoot"] == str(drive_root)
    assert runtime["doctor"]["data"]["argv"][-2:] == ["doctor", "--json"]

def test_check_rejects_redirected_plugin_data_ancestor(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "target"
    plugin_data_target = target / "nested"
    plugin_data_target.mkdir(parents=True)
    redirect = tmp_path / "redirect"
    junction = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(redirect), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if junction.returncode != 0:
        pytest.skip("directory junctions unavailable")

    result = _run_helper("Check", REPO_ROOT, redirect / "nested", project)

    assert result.returncode != 0
    assert "redirect" in result.stderr.lower() or "reparse" in result.stderr.lower()
    assert not (plugin_data_target / "runtime").exists()

def test_setup_contract_uses_namespaced_skill_and_ignores_coverage_data():
    launcher = (REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md").read_text(encoding="utf-8")
    plan = (REPO_ROOT / "docs" / "superpowers" / "plans" / "2026-07-29-stm32-toolkit-plugin-foundation.md").read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert EXPECTED_SKILL in launcher
    assert EXPECTED_SKILL in readme
    assert "/setup-stm32-env" not in launcher.replace(EXPECTED_SKILL, "")
    assert "`/setup-stm32-env`" not in readme
    assert "Run /setup-stm32-env" not in readme
    assert "${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1" in readme
    assert "skills/setup-stm32-env/SKILL.md" in plan
    assert "stm32-toolkit:setup-stm32-env.ps1" not in readme
    assert "skills/stm32-toolkit:setup-stm32-env" not in plan
    assert "Repair" in skill
    assert "staging" in skill
    assert "quarantine" in skill
    assert ".coverage" in gitignore
    assert ".coverage.*" in gitignore


def _write_test_build_backend(wheelhouse: Path) -> None:
    backend_source = """from pathlib import Path
import zipfile
import venv


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist = Path(metadata_directory) / 'stm32_toolkit-0.2.0.dist-info'
    dist.mkdir()
    (dist / 'METADATA').write_text('Metadata-Version: 2.1\\nName: stm32-toolkit\\nVersion: 0.2.0\\n')
    (dist / 'WHEEL').write_text('Wheel-Version: 1.0\\nGenerator: test-backend\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n')
    return dist.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = 'stm32_toolkit-0.2.0-py3-none-any.whl'
    files = {
        'stm32_toolkit/__init__.py': "__version__ = '0.2.0'\\n",
        'stm32_toolkit/cli.py': "import json,sys\\nif sys.argv[1:]==['version']: print('0.2.0')\\nelif 'doctor' in sys.argv:\\n i=sys.argv.index('--project-root'); print(json.dumps({'protocol':'stm32-toolkit/1','ok':True,'data':{'projectRoot':sys.argv[i+1],'argv':sys.argv[1:]}}))\\nelse: raise SystemExit(2)\\n",
        'stm32_toolkit-0.2.0.dist-info/METADATA': 'Metadata-Version: 2.1\\nName: stm32-toolkit\\nVersion: 0.2.0\\n',
        'stm32_toolkit-0.2.0.dist-info/WHEEL': 'Wheel-Version: 1.0\\nGenerator: test-backend\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n',
        'stm32_toolkit-0.2.0.dist-info/RECORD': '',
    }
    with zipfile.ZipFile(Path(wheel_directory) / name, 'w') as archive:
        for path, content in files.items(): archive.writestr(path, content)
    return name
"""
    wheel = wheelhouse / "test_build_backend-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("test_backend.py", backend_source)
        archive.writestr(
            "test_build_backend-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: test-build-backend\nVersion: 1.0\n",
        )
        archive.writestr(
            "test_build_backend-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("test_build_backend-1.0.dist-info/RECORD", "")

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
