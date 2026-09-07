from __future__ import annotations

import json
import hashlib
import os
import re
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
FAKE_MCP_TOOLS = (
    "stm32_doctor",
    "stm32_project_detect",
    "stm32_project_context",
    "stm32_project_create_plan",
    "stm32_project_create_prepare",
    "stm32_project_create_apply",
    "stm32_project_regenerate_plan",
    "stm32_project_regenerate_prepare",
    "stm32_project_regenerate_apply",
    "stm32_keil_inspect",
    "stm32_keil_convert",
    "stm32_project_configure",
    "stm32_build",
    "stm32_probe_list",
    "stm32_flash",
    "stm32_debug_handoff_begin",
    "stm32_debug_handoff_end",
    "stm32_variable_read",
    "stm32_variable_sample",
    "stm32_register_read",
    "stm32_fault_analyze",
    "stm32_diagnostic_start",
    "stm32_diagnostic_show",
    "stm32_diagnostic_begin",
    "stm32_diagnostic_hypothesis_add",
    "stm32_diagnostic_hypothesis_assess",
    "stm32_diagnostic_plan_add",
    "stm32_diagnostic_plan_run",
    "stm32_test_target_replay",
    "stm32_diagnostic_source_change_declare",
    "stm32_diagnostic_verification_plan_add",
    "stm32_diagnostic_verification_start",
    "stm32_diagnostic_marker_attach",
    "stm32_diagnostic_verification_complete",
    "stm32_diagnostic_verification_show",
    "stm32_test_host_discover",
    "stm32_test_host_run",
    "stm32_test_show",
    "stm32_test_target_prepare",
    "stm32_test_target_execute",
    "stm32_acceptance_scenario_describe",
    "stm32_acceptance_scenario_record",
    "stm32_acceptance_scenario_show",
    "stm32_acceptance_attempt_begin",
    "stm32_acceptance_attempt_checkpoint",
    "stm32_acceptance_attempt_authorize_source_change",
    "stm32_acceptance_attempt_show",
    "stm32_acceptance_attempt_resume",
)
FAKE_SKILLS = (
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor",
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="PowerShell runtime setup")


def test_check_reports_broken_runtime_as_structured_evidence(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime_python = plugin_data / "runtime" / "0.9.0" / "Scripts" / "python.exe"
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


def test_bootstrap_rejects_unsupported_python_before_runtime_mutation(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    (plugin_root / "tools" / "stm32-monitor").mkdir(parents=True)
    plugin_data = tmp_path / "plugin-data"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "py.cmd").write_text(
        '@echo off\r\necho {"version":"3.11.9","supported":false}\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    environment = _clean_environment()
    environment["PATH"] = os.pathsep.join(
        [str(fake_bin), str(Path(os.environ["SystemRoot"]) / "System32")]
    )

    result = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project, environment=environment
    )

    assert result.returncode == 2
    assert "CPython >=3.12,<3.13 is required" in result.stderr
    assert not (plugin_data / "runtime").exists()


@pytest.mark.parametrize("mode", ["Check", "Bootstrap"])
def test_setup_rejects_replaced_release_utility_before_execution(tmp_path: Path, mode: str):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    _write_fake_monitor_package(plugin_root)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    utility = plugin_root / "tools" / "release" / "build_0900_artifacts.py"
    marker = plugin_root / "SOL-UNVERIFIED-UTILITY-EXECUTED.txt"
    _write_attacker_release_utility(utility, marker)
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper(mode, plugin_root, plugin_data, project, environment=environment, timeout=180, helper=HELPER)

    if mode == "Check":
        assert result.returncode == 0
        assert json.loads(result.stdout)["bundle"]["status"] == "invalid"
    else:
        assert result.returncode == 2
    assert not marker.exists()
    assert not (plugin_data / "runtime" / ".staging").exists()


def test_setup_rejects_policy_swap_at_bootstrap_boundary(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    _write_fake_monitor_package(plugin_root)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    policy = plugin_root / "tools" / "release" / "release_0900_policy.json"
    policy.write_text('{"version":"attacker"}\n', encoding="utf-8")
    utility = plugin_root / "tools" / "release" / "build_0900_artifacts.py"
    marker = plugin_root / "SOL-POLICY-SWAP-UTILITY-EXECUTED.txt"
    _write_attacker_release_utility(utility, marker)
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper("Bootstrap", plugin_root, plugin_data, project, environment=environment, timeout=180, helper=HELPER)

    assert result.returncode == 2
    assert not marker.exists()
    assert not (plugin_data / "runtime" / ".staging").exists()


def test_setup_rejects_changed_after_read_utility_before_staging(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    _write_fake_monitor_package(plugin_root)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    utility = plugin_root / "tools" / "release" / "build_0900_artifacts.py"
    marker = plugin_root / "SOL-CHANGED-AFTER-READ-UTILITY-EXECUTED.txt"
    _write_attacker_release_utility(utility, marker, mutate_self=True)
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper("Bootstrap", plugin_root, plugin_data, project, environment=environment, timeout=180, helper=HELPER)

    assert result.returncode == 2
    assert not marker.exists()
    assert not (plugin_data / "runtime" / ".staging").exists()


def test_partial_runtime_directory_is_broken_and_recommends_repair(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    (plugin_data / "runtime" / "0.9.0").mkdir(parents=True)

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
    runtime_path = plugin_data / "runtime" / "0.9.0"
    runtime_path.parent.mkdir(parents=True)
    runtime_path.write_text("partial", encoding="utf-8")

    result = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["runtime"]["present"] is True
    assert payload["runtime"]["directoryPresent"] is False
    assert payload["recommendedMode"] == "Repair"


def test_check_rejects_current_runtime_without_probe_extra(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=False).create(runtime)
    package = runtime / "Lib" / "site-packages" / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '0.9.0'\n", encoding="utf-8")
    (package / "cli.py").write_text(
        "import json,sys\n"
        "if sys.argv[1:]==['version']: print('0.9.0')\n"
        "elif 'doctor' in sys.argv: print(json.dumps({'ok':True,'data':{}}))\n"
        "else: raise SystemExit(2)\n",
        encoding="utf-8",
    )

    checked = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["recommendedMode"] == "Repair"
    assert "pyocd" in payload["runtime"]["error"].lower()
    assert "traceback" not in payload["runtime"]["error"].lower()
    assert "modulenotfounderror" not in payload["runtime"]["error"].lower()
    assert str(tmp_path) not in payload["runtime"]["error"]


def test_check_rejects_ok_doctor_without_exact_runtime_inventory(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=True).create(runtime)
    site_packages = runtime / "Lib" / "site-packages"
    _install_fake_toolkit(site_packages)
    _install_fake_monitor(site_packages)
    _install_fake_probe(site_packages, "0.45.1")
    (site_packages / "stm32_toolkit" / "cli.py").write_text(
        "import json,sys\n"
        "if sys.argv[1:]==['version']: print('0.9.0')\n"
        "elif 'doctor' in sys.argv: print(json.dumps({'ok':True,'data':{}}))\n"
        "else: raise SystemExit(2)\n",
        encoding="utf-8",
    )

    checked = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["recommendedMode"] == "Repair"
    assert "doctor runtime evidence" in payload["runtime"]["error"]


def test_bootstrap_rejects_ok_doctor_without_exact_runtime_inventory_before_promotion(
    tmp_path: Path,
):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse, complete_doctor=False)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse, complete_doctor=False)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )

    assert result.returncode == 2
    assert "doctor runtime evidence" in result.stderr
    assert not (plugin_data / "runtime" / "0.9.0").exists()


@pytest.mark.parametrize(
    "probe_version", ["0.44.9", "0.45rc1", "0.45.0", "0.45.1rc1", "0.46.0"]
)
def test_check_rejects_out_of_range_probe_distribution_without_leaking_details(
    tmp_path: Path,
    probe_version: str,
):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=True).create(runtime)
    site_packages = runtime / "Lib" / "site-packages"
    package = site_packages / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '0.9.0'\n", encoding="utf-8")
    (package / "cli.py").write_text(
        "import json,sys\n"
        "if sys.argv[1:]==['version']: print('0.9.0')\n"
        "elif 'doctor' in sys.argv: print(json.dumps({'ok':True,'data':{}}))\n"
        "else: raise SystemExit(2)\n",
        encoding="utf-8",
    )
    probe = site_packages / "pyocd"
    probe.mkdir()
    (probe / "__init__.py").write_text(
        f"__version__ = {probe_version!r}\n", encoding="utf-8"
    )
    metadata = site_packages / f"pyocd-{probe_version}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: pyocd\nVersion: {probe_version}\n",
        encoding="utf-8",
    )

    checked = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["recommendedMode"] == "Repair"
    error = payload["runtime"]["error"].lower()
    assert "pyocd runtime validation failed" in error
    assert probe_version not in error
    assert "traceback" not in error
    assert str(tmp_path).lower() not in error


@pytest.mark.parametrize("probe_version", ["0.45.1", "0.45.1.post1"])
def test_check_accepts_probe_distribution_in_declared_pep440_range(
    tmp_path: Path,
    probe_version: str,
):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=True).create(runtime)
    site_packages = runtime / "Lib" / "site-packages"
    _install_fake_toolkit(site_packages)
    _install_fake_monitor(site_packages)
    _install_fake_probe(site_packages, probe_version)
    _write_fake_public_launchers(runtime)

    checked = _run_helper("Check", REPO_ROOT, plugin_data, project)

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "healthy"
    assert payload["runtime"]["version"] == "0.9.0"
    assert payload["recommendedMode"] is None


def test_existing_0_3_runtime_requires_repair_and_is_quarantined_before_0_9_promotion(
    tmp_path: Path,
):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    legacy = plugin_data / "runtime" / "0.3.0"
    legacy.mkdir(parents=True)
    marker = legacy / "legacy-marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    checked = _run_helper("Check", plugin_root, plugin_data, project, environment=environment)

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["runtime"]["path"].endswith("/runtime/0.3.0")
    assert payload["recommendedMode"] == "Repair"
    assert not (plugin_data / "runtime" / "0.9.0").exists()

    repaired = _run_helper(
        "Repair", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )

    assert repaired.returncode == 0, repaired.stderr
    repaired_payload = json.loads(repaired.stdout)
    assert repaired_payload["runtime"]["status"] == "healthy"
    assert repaired_payload["runtime"]["version"] == "0.9.0"
    assert not legacy.exists()
    quarantines = list((plugin_data / "runtime" / ".quarantine").glob("0.3.0-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / marker.name).read_text(encoding="utf-8") == "preserve"


def test_post_promotion_validation_failure_restores_previous_runtime_and_state(
    tmp_path: Path,
):
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
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    bootstrap = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    runtime = plugin_data / "runtime" / "0.9.0"
    state_path = plugin_data / "runtime" / "runtime-state.json"
    prior_runtime = _snapshot_files(runtime)
    prior_project = _snapshot_files(project)

    toolkit_wheel = plugin_root / "release" / "wheels" / "stm32_toolkit-0.9.0-py3-none-any.whl"
    mutated_wheel = tmp_path / "mutated-toolkit.whl"
    with zipfile.ZipFile(toolkit_wheel) as source, zipfile.ZipFile(
        mutated_wheel, "w", compression=zipfile.ZIP_STORED
    ) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename.endswith(".dist-info/entry_points.txt"):
                content = content.replace(
                    b"stm32-toolkit = stm32_toolkit.cli:main",
                    b"stm32-toolkit = stm32_toolkit.cli:missing_main",
                )
            target.writestr(info.filename, content)
    shutil.move(mutated_wheel, toolkit_wheel)

    manifest_path = plugin_root / "release" / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    toolkit_entry = next(
        entry for entry in manifest["wheels"] if entry["name"] == "stm32-toolkit"
    )
    toolkit_entry["sha256"] = hashlib.sha256(toolkit_wheel.read_bytes()).hexdigest()
    toolkit_entry["size"] = toolkit_wheel.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["releaseManifestSha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    state_path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    prior_state = state_path.read_bytes()

    repair = _run_helper(
        "Repair", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )

    assert repair.returncode != 0
    assert "launcher" in repair.stderr.lower() or "version" in repair.stderr.lower()
    assert _snapshot_files(runtime) == prior_runtime
    assert state_path.read_bytes() == prior_state
    assert _snapshot_files(project) == prior_project
    staging = plugin_data / "runtime" / ".staging"
    assert not staging.exists() or not any(staging.iterdir())


def test_repair_rejects_multiple_legacy_runtimes_before_mutation(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    runtime_root = plugin_data / "runtime"
    for version in ("0.5.0", "0.3.0"):
        (runtime_root / version).mkdir(parents=True)
        (runtime_root / version / "marker.txt").write_text(version, encoding="utf-8")

    result = _run_helper("Repair", REPO_ROOT, plugin_data, project)

    assert result.returncode == 2
    assert "multiple legacy runtimes" in result.stderr.lower()
    assert not (runtime_root / ".quarantine").exists()
    assert (runtime_root / "0.5.0" / "marker.txt").read_text(encoding="utf-8") == "0.5.0"
    assert (runtime_root / "0.3.0" / "marker.txt").read_text(encoding="utf-8") == "0.3.0"

def test_failed_bootstrap_removes_staging_and_never_promotes(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    (plugin_root / "tools" / "stm32-monitor").mkdir(parents=True)
    plugin_data = tmp_path / "plugin-data"

    result = _run_helper("Bootstrap", plugin_root, plugin_data, project, timeout=90)

    assert result.returncode != 0
    assert not (plugin_data / "runtime" / "0.9.0").exists()
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
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
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
    runtime = plugin_data / "runtime" / "0.9.0"
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
    assert any(path.name.startswith("0.9.0-") for path in quarantine.iterdir())
    assert project_marker.read_text(encoding="utf-8") == "unchanged"


def test_bootstrap_promotes_public_console_launchers_with_final_runtime_binding(
    tmp_path: Path,
):
    """A real pip/distlib install must leave public launchers usable after promotion."""
    roots = tmp_path / "x y"
    project = roots / "project q"
    project.mkdir(parents=True)
    plugin_root = roots / "plugin q"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = roots / "wheel h"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = roots / "data q"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    result = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )

    assert result.returncode == 0, result.stderr
    runtime = plugin_data / "runtime" / "0.9.0"
    runtime_python = runtime / "Scripts" / "python.exe"
    assert runtime_python.is_file()
    for launcher_name in (
        "stm32-toolkit.exe",
        "stm32-toolkit-mcp.exe",
        "stm32-monitor.exe",
    ):
        launcher = runtime / "Scripts" / launcher_name
        assert launcher.is_file()
        launcher_bytes = launcher.read_bytes().lower()
        assert _launcher_contains(launcher_bytes, runtime_python)
        assert not _launcher_contains(launcher_bytes, plugin_data / "runtime" / ".staging")

    toolkit = subprocess.run(
        [str(runtime / "Scripts" / "stm32-toolkit.exe"), "version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    monitor = subprocess.run(
        [str(runtime / "Scripts" / "stm32-monitor.exe"), "version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert toolkit.returncode == 0, toolkit.stderr
    assert toolkit.stdout.strip() == "0.9.0"
    assert monitor.returncode == 0, monitor.stderr
    assert monitor.stdout.strip() == "0.9.0"


def test_check_reports_staging_bound_public_console_launcher_as_broken(tmp_path: Path):
    roots = tmp_path / "x y"
    project = roots / "project q"
    project.mkdir(parents=True)
    plugin_root = roots / "plugin q"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = roots / "wheel h"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\n"
        "build-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    plugin_data = roots / "data q"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)

    bootstrap = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    runtime = plugin_data / "runtime" / "0.9.0"
    runtime_python = runtime / "Scripts" / "python.exe"
    _write_fake_public_launchers(runtime)
    _replace_launcher_binding(
        runtime / "Scripts" / "stm32-toolkit.exe",
        runtime_python,
        plugin_data / "runtime" / ".staging",
    )
    before_data = _snapshot_files(plugin_data)
    before_project = _snapshot_files(project)

    checked = _run_helper(
        "Check", plugin_root, plugin_data, project,
        environment=environment, timeout=60,
    )

    assert checked.returncode == 0, checked.stderr
    payload = json.loads(checked.stdout)
    assert payload["runtime"]["status"] == "broken"
    assert payload["authorizationRequired"] is True
    assert payload["recommendedMode"] == "Repair"
    assert _snapshot_files(plugin_data) == before_data
    assert _snapshot_files(project) == before_project
    assert not (plugin_data / "runtime" / ".staging").exists() or not any(
        (plugin_data / "runtime" / ".staging").iterdir()
    )


def test_check_bounds_a_hanging_bootstrap_python(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_data = tmp_path / "plugin-data"
    probe_runtime = tmp_path / "probe-runtime"
    venv.EnvBuilder(with_pip=False).create(probe_runtime)
    (probe_runtime / "Lib" / "site-packages" / "sitecustomize.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    environment = _clean_environment()
    environment["PATH"] = os.pathsep.join(
        [str(probe_runtime / "Scripts"), str(Path(os.environ["SystemRoot"]) / "System32")]
    )

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
    runtime = plugin_data / "runtime" / "0.9.0"
    venv.EnvBuilder(with_pip=False).create(runtime)
    package = runtime / "Lib" / "site-packages" / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import sys\nsys.stdout.write('o' * 200000)\nsys.stderr.write('e' * 200000)\nraise SystemExit(7)\n",
        encoding="utf-8",
    )
    environment = _clean_environment()

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
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
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
    assert payload["runtime"]["version"] == "0.9.0"
    runtime_python = plugin_data / "runtime" / "0.9.0" / "Scripts" / "python.exe"
    probe_import = subprocess.run(
        [str(runtime_python), "-I", "-c", "import pyocd; print(pyocd.__version__)"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_clean_environment(),
    )
    assert probe_import.returncode == 0, probe_import.stderr
    assert probe_import.stdout.strip() == "0.45.1"


def test_bootstrap_ignores_hostile_python_path_and_home(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
    (package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\nbuild-backend = 'test_backend'\n",
        encoding="utf-8",
    )
    poison = tmp_path / "poison"
    poisoned_package = poison / "stm32_toolkit"
    poisoned_package.mkdir(parents=True)
    (poisoned_package / "__init__.py").write_text("", encoding="utf-8")
    (poisoned_package / "cli.py").write_text(
        "raise RuntimeError('ambient workspace package imported')\n", encoding="utf-8"
    )
    poisoned_probe = poison / "pyocd"
    poisoned_probe.mkdir()
    (poisoned_probe / "__init__.py").write_text(
        "raise RuntimeError('ambient pyocd imported')\n", encoding="utf-8"
    )
    plugin_data = tmp_path / "plugin-data"
    environment = _clean_environment()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_FIND_LINKS"] = str(wheelhouse)
    environment["PYTHONPATH"] = str(poison)
    environment["PYTHONHOME"] = str(tmp_path / "invalid-python-home")

    result = _run_helper(
        "Bootstrap", plugin_root, plugin_data, project,
        environment=environment, timeout=180,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"]["status"] == "healthy"
    assert payload["runtime"]["version"] == "0.9.0"
    runtime_python = plugin_data / "runtime" / "0.9.0" / "Scripts" / "python.exe"
    installed_probe = subprocess.run(
        [str(runtime_python), "-I", "-c", "import pyocd; print(pyocd.__version__)"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert installed_probe.returncode == 0, installed_probe.stderr
    assert installed_probe.stdout.strip() == "0.45.1"

def test_healthy_check_preserves_drive_root_argument_and_following_doctor_args(tmp_path: Path):
    bootstrap_project = tmp_path / "project"
    bootstrap_project.mkdir()
    plugin_root = tmp_path / "plugin"
    package = plugin_root / "tools" / "stm32-toolkit"
    package.mkdir(parents=True)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_test_build_backend(wheelhouse)
    _write_fake_monitor_package(plugin_root)
    _write_fake_release_bundle(plugin_root, wheelhouse)
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


def test_check_reports_missing_release_bundle_and_runtime_state(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    (plugin_root / "tools" / "stm32-monitor").mkdir(parents=True)
    data = tmp_path / "data"

    result = _run_helper("Check", plugin_root, data, project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["bundle"]["status"] == "missing"
    assert payload["runtimeState"]["status"] == "missing"
    assert payload["mutated"] is False
    assert not (data / "runtime" / "runtime-state.json").exists()


def test_bootstrap_rejects_missing_bundle_before_creating_staging(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    (plugin_root / "tools" / "stm32-monitor").mkdir(parents=True)
    data = tmp_path / "data"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "py.cmd").write_text(
        '@echo off\r\necho {"version":"3.12.10","supported":true}\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    environment = _clean_environment()
    environment["PATH"] = os.pathsep.join(
        [str(fake_bin), str(Path(os.environ["SystemRoot"]) / "System32")]
    )

    result = _run_helper("Bootstrap", plugin_root, data, project, environment=environment)

    assert result.returncode == 2
    assert "bundle" in result.stderr.lower()
    assert not (data / "runtime" / ".staging").exists()


def test_bootstrap_rejects_invalid_bundle_hash_before_creating_staging(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    release = plugin_root / "release" / "wheels"
    release.mkdir(parents=True)
    (plugin_root / "tools" / "stm32-toolkit").mkdir(parents=True)
    (plugin_root / "tools" / "stm32-monitor").mkdir(parents=True)
    (release / "example-1.0.0-py3-none-any.whl").write_bytes(b"not-a-wheel")
    (plugin_root / "release" / "release-manifest.json").write_text(
        json.dumps({"schema": "stm32-toolkit-release/1"}) + "\n", encoding="utf-8"
    )
    data = tmp_path / "data"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "py.cmd").write_text(
        '@echo off\r\necho {"version":"3.12.10","supported":true}\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    environment = _clean_environment()
    environment["PATH"] = os.pathsep.join(
        [str(fake_bin), str(Path(os.environ["SystemRoot"]) / "System32")]
    )

    result = _run_helper("Bootstrap", plugin_root, data, project, environment=environment)

    assert result.returncode == 2
    assert "bundle" in result.stderr.lower()
    assert not (data / "runtime" / ".staging").exists()

def test_setup_contract_uses_namespaced_skill_and_ignores_coverage_data():
    launcher = (REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md").read_text(encoding="utf-8")
    plan = (REPO_ROOT / "docs" / "superpowers" / "plans" / "2026-07-29-stm32-toolkit-plugin-foundation.md").read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "STM32_TOOLKIT_DATA_ROOT" in launcher
    assert EXPECTED_SKILL in readme
    assert "CLAUDE_PLUGIN_DATA" not in launcher
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


def _write_test_build_backend(
    wheelhouse: Path, *, complete_doctor: bool = True
) -> None:
    doctor_source = (
        _fake_toolkit_cli_source()
        if complete_doctor
        else _fake_incomplete_toolkit_cli_source()
    )
    monitor_source = _fake_monitor_cli_source()
    backend_source = """from pathlib import Path
import zipfile
import venv


def _project():
    name = Path.cwd().name
    return "stm32-monitor" if name == "stm32-monitor" else "stm32-toolkit"


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    name = _project()
    dist_name = "stm32_monitor" if name == "stm32-monitor" else "stm32_toolkit"
    dist = Path(metadata_directory) / f"{dist_name}-0.9.0.dist-info"
    dist.mkdir()
    (dist / 'METADATA').write_text(f'Metadata-Version: 2.1\\nName: {name}\\nVersion: 0.9.0\\nProvides-Extra: probe\\nRequires-Dist: pyocd==0.45.1; extra == "probe"\\n')
    (dist / 'WHEEL').write_text('Wheel-Version: 1.0\\nGenerator: test-backend\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n')
    return dist.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = _project()
    if name == "stm32-monitor":
        dist_name = 'stm32_monitor-0.9.0-py3-none-any.whl'
        files = {
            'stm32_monitor/__init__.py': "__version__ = '0.9.0'\\n",
            'stm32_monitor/ui_dist/index.html': '<div id="app"></div>\\n',
            'stm32_monitor/ui_dist/.vite/manifest.json': '{"index.html":{"file":"assets/app-aaaaaaaa.js","css":[]}}\\n',
            'stm32_monitor/ui_dist/assets/app-aaaaaaaa.js': 'export {}\\n',
            'stm32_monitor/cli.py': __MONITOR_SOURCE__,
            'stm32_monitor-0.9.0.dist-info/entry_points.txt': '[console_scripts]\\n'
            'stm32-monitor = stm32_monitor.cli:main\\n',
            'stm32_monitor-0.9.0.dist-info/METADATA': 'Metadata-Version: 2.1\\nName: stm32-monitor\\nVersion: 0.9.0\\n',
            'stm32_monitor-0.9.0.dist-info/WHEEL': 'Wheel-Version: 1.0\\nGenerator: test-backend\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n',
            'stm32_monitor-0.9.0.dist-info/RECORD': '',
        }
    else:
        dist_name = 'stm32_toolkit-0.9.0-py3-none-any.whl'
        files = {
            'stm32_toolkit/__init__.py': "__version__ = '0.9.0'\\n",
            'stm32_toolkit/cli.py': __DOCTOR_SOURCE__,
            'stm32_toolkit-0.9.0.dist-info/entry_points.txt': '[console_scripts]\\n'
            'stm32-toolkit = stm32_toolkit.cli:main\\n'
            'stm32-toolkit-mcp = stm32_toolkit.cli:mcp_main\\n',
            'stm32_toolkit-0.9.0.dist-info/METADATA': 'Metadata-Version: 2.1\\nName: stm32-toolkit\\nVersion: 0.9.0\\nProvides-Extra: probe\\nRequires-Dist: pyocd==0.45.1; extra == "probe"\\n',
            'stm32_toolkit-0.9.0.dist-info/WHEEL': 'Wheel-Version: 1.0\\nGenerator: test-backend\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n',
            'stm32_toolkit-0.9.0.dist-info/RECORD': '',
        }
    with zipfile.ZipFile(Path(wheel_directory) / dist_name, 'w') as archive:
        for path, content in files.items(): archive.writestr(path, content)
    return dist_name
"""
    backend_source = backend_source.replace("__DOCTOR_SOURCE__", repr(doctor_source))
    backend_source = backend_source.replace("__MONITOR_SOURCE__", repr(monitor_source))
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
    probe_wheel = wheelhouse / "pyocd-0.45.1-py3-none-any.whl"
    with zipfile.ZipFile(probe_wheel, "w") as archive:
        archive.writestr("pyocd/__init__.py", "__version__ = '0.45.1'\n")
        archive.writestr(
            "pyocd-0.45.1.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: pyocd\nVersion: 0.45.1\n",
        )
        archive.writestr(
            "pyocd-0.45.1.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("pyocd-0.45.1.dist-info/RECORD", "")


def _write_fake_release_bundle(plugin_root: Path, wheelhouse: Path, *, complete_doctor: bool = True) -> None:
    """Create a complete local release tree for setup lifecycle tests."""
    release = plugin_root / "release"
    wheels = release / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    utility = plugin_root / "tools" / "release" / "build_0900_artifacts.py"
    utility.parent.mkdir(parents=True, exist_ok=True)
    utility.write_text(
        """import hashlib, json, sys
from pathlib import Path

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    args = sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / 'release' / 'release-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if 'verify-bundle' in args:
        print(json.dumps({'status': 'ok', 'productVersion': '0.9.0',
            'manifestSha256': digest(manifest_path),
            'utilitySha256': digest(Path(__file__)),
            'sourceCommit': manifest['source']['commit'],
            'wheels': [entry['file'] for entry in manifest['wheels']],
            'wheelEntries': manifest['wheels']}, separators=(',', ':')))
        return 0
    if 'verify-runtime-state' in args:
        state_path = Path(args[args.index('--state') + 1])
        if not state_path.exists():
            print(json.dumps({'status': 'missing'}, separators=(',', ':')))
            return 0
        state = json.loads(state_path.read_text(encoding='utf-8'))
        candidate_hash = digest(manifest_path)
        if state.get('highestInstalledVersion', '0.0.0') > '0.9.0':
            status = 'downgrade-refused'
        elif (state.get('activeVersion') == '0.9.0' and
              (state.get('releaseManifestSha256') != candidate_hash or
               state.get('sourceCommit') != manifest['source']['commit'])):
            status = 'source-conflict'
        elif (state.get('releaseManifestSha256') == candidate_hash and
              state.get('sourceCommit') == manifest['source']['commit']):
            status = 'matching'
        else:
            status = 'repairable'
        payload = {'status': status}
        if 'activeVersion' in state: payload['activeVersion'] = state['activeVersion']
        if 'installGeneration' in state: payload['installGeneration'] = state['installGeneration']
        print(json.dumps(payload, separators=(',', ':')))
        return 2 if status in ('downgrade-refused', 'source-conflict') else 0
    return 2

raise SystemExit(main())
""",
        encoding="utf-8",
    )
    shutil.copy2(
        REPO_ROOT / "tools" / "release" / "release_0900_policy.json",
        utility.with_name("release_0900_policy.json"),
    )

    def write_wheel(path: Path, files: dict[str, bytes]) -> None:
        records = []
        for name, content in files.items():
            if name.endswith("/RECORD"):
                continue
            digest = hashlib.sha256(content).digest()
            import base64

            records.append(
                f"{name},sha256={base64.urlsafe_b64encode(digest).rstrip(b'=').decode()},{len(content)}"
            )
        record_name = next(name for name in files if name.endswith(".dist-info/RECORD"))
        files = dict(files)
        files[record_name] = ("\n".join(records + [f"{record_name},,"]) + "\n").encode()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)

    toolkit_name = "stm32_toolkit-0.9.0-py3-none-any.whl"
    toolkit_dist = "stm32_toolkit-0.9.0.dist-info"
    toolkit_files = {
        "stm32_toolkit/__init__.py": b"__version__ = '0.9.0'\n",
        "stm32_toolkit/cli.py": (_fake_toolkit_cli_source() if complete_doctor else _fake_incomplete_toolkit_cli_source()).encode(),
        f"{toolkit_dist}/entry_points.txt": (
            b"[console_scripts]\n"
            b"stm32-toolkit = stm32_toolkit.cli:main\n"
            b"stm32-toolkit-mcp = stm32_toolkit.cli:mcp_main\n"
        ),
        f"{toolkit_dist}/METADATA": b"Metadata-Version: 2.3\nName: stm32-toolkit\nVersion: 0.9.0\nRequires-Dist: pyocd==0.45.1\nLicense-Expression: MIT\n",
        f"{toolkit_dist}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{toolkit_dist}/RECORD": b"",
    }
    write_wheel(wheels / toolkit_name, toolkit_files)

    monitor_name = "stm32_monitor-0.9.0-py3-none-any.whl"
    monitor_dist = "stm32_monitor-0.9.0.dist-info"
    monitor_files = {
        "stm32_monitor/__init__.py": b"__version__ = '0.9.0'\n",
        "stm32_monitor/cli.py": _fake_monitor_cli_source().encode(),
        "stm32_monitor/ui_dist/index.html": b"<div id='app'></div>\n",
        "stm32_monitor/ui_dist/.vite/manifest.json": b'{"index.html":{"file":"assets/app-aaaaaaaa.js","css":[]}}\n',
        "stm32_monitor/ui_dist/assets/app-aaaaaaaa.js": b"export {}\n",
        f"{monitor_dist}/METADATA": b"Metadata-Version: 2.3\nName: stm32-monitor\nVersion: 0.9.0\nRequires-Dist: stm32-toolkit==0.9.0\nLicense-Expression: MIT\n",
        f"{monitor_dist}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{monitor_dist}/entry_points.txt": (
            b"[console_scripts]\n"
            b"stm32-monitor = stm32_monitor.cli:main\n"
        ),
        f"{monitor_dist}/RECORD": b"",
    }
    write_wheel(wheels / monitor_name, monitor_files)
    pyocd_source = wheelhouse / "pyocd-0.45.1-py3-none-any.whl"
    if pyocd_source.is_file():
        shutil.copy2(pyocd_source, wheels / pyocd_source.name)
    source = plugin_root / "source.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("source.txt", "fixture")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    wheel_entries = []
    for name, dist in ((toolkit_name, "stm32-toolkit"), (monitor_name, "stm32-monitor")):
        path = wheels / name
        wheel_entries.append({"name": dist, "version": "0.9.0", "file": f"release/wheels/{name}", "sha256": digest(path), "size": path.stat().st_size, "direct": True, "license": "MIT"})
    pyocd_path = wheels / "pyocd-0.45.1-py3-none-any.whl"
    if pyocd_path.is_file():
        wheel_entries.append({"name": "pyocd", "version": "0.45.1", "file": "release/wheels/pyocd-0.45.1-py3-none-any.whl", "sha256": digest(pyocd_path), "size": pyocd_path.stat().st_size, "direct": False, "license": "MIT"})
    manifest = {
        "schema": "stm32-toolkit-release/1",
        "productVersion": "0.9.0",
        "requiredPython": ">=3.12,<3.13",
        "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
        "source": {"repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git", "commit": "a" * 40, "archive": "source.zip", "sha256": digest(source)},
        "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
        "wheels": wheel_entries,
        "artifacts": [],
        "publicInventory": {"mcpTools": 48, "skills": 8},
    }
    (release / "release-manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_attacker_release_utility(path: Path, marker: Path, *, mutate_self: bool = False) -> None:
    path.write_text(
        f"""import hashlib, json, sys
from pathlib import Path

MARKER = Path({str(marker)!r})
MUTATE_SELF = {mutate_self!r}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    MARKER.write_text('SOL-UNVERIFIED-UTILITY-EXECUTED', encoding='utf-8')
    if MUTATE_SELF:
        Path(__file__).write_text('# changed-after-read\\n', encoding='utf-8')
    args = sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / 'release' / 'release-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if 'verify-bundle' in args:
        print(json.dumps({{'status': 'ok', 'productVersion': '0.9.0',
            'manifestSha256': digest(manifest_path),
            'utilitySha256': digest(Path(__file__)),
            'sourceCommit': manifest['source']['commit'],
            'wheels': [entry['file'] for entry in manifest['wheels']],
            'wheelEntries': manifest['wheels']}}, separators=(',', ':')))
        return 0
    if 'verify-runtime-state' in args:
        print(json.dumps({{'status': 'missing'}}, separators=(',', ':')))
        return 0
    return 2

raise SystemExit(main())
""",
        encoding="utf-8",
    )


def _write_fake_monitor_package(plugin_root: Path) -> None:
    monitor_package = plugin_root / "tools" / "stm32-monitor"
    monitor_package.mkdir(parents=True)
    (monitor_package / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['test-build-backend==1.0']\nbuild-backend = 'test_backend'\n",
        encoding="utf-8",
    )


def _install_fake_monitor(site_packages: Path) -> None:
    """Install a minimal stm32-monitor 0.9.0 package with readable UI assets."""
    package = site_packages / "stm32_monitor"
    ui_dist = package / "ui_dist"
    (ui_dist / ".vite").mkdir(parents=True)
    (ui_dist / "assets").mkdir()
    (package / "__init__.py").write_text("__version__ = '0.9.0'\n", encoding="utf-8")
    (ui_dist / "index.html").write_text('<div id="app"></div>\n', encoding="utf-8")
    (ui_dist / ".vite" / "manifest.json").write_text(
        '{"index.html":{"file":"assets/app-aaaaaaaa.js","css":[]}}\n', encoding="utf-8"
    )
    (ui_dist / "assets" / "app-aaaaaaaa.js").write_text("export {}\n", encoding="utf-8")
    metadata = site_packages / "stm32_monitor-0.9.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: stm32-monitor\nVersion: 0.9.0\n",
        encoding="utf-8",
    )
    (metadata / "entry_points.txt").write_text(
        "[console_scripts]\n"
        "stm32-monitor = stm32_monitor.cli:main\n",
        encoding="utf-8",
    )
    (package / "cli.py").write_text(_fake_monitor_cli_source(), encoding="utf-8")


def _install_fake_toolkit(site_packages: Path) -> None:
    package = site_packages / "stm32_toolkit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '0.9.0'\n", encoding="utf-8")
    (package / "cli.py").write_text(_fake_toolkit_cli_source(), encoding="utf-8")
    metadata = site_packages / "stm32_toolkit-0.9.0.dist-info"
    metadata.mkdir(exist_ok=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: stm32-toolkit\nVersion: 0.9.0\n",
        encoding="utf-8",
    )
    (metadata / "entry_points.txt").write_text(
        "[console_scripts]\n"
        "stm32-toolkit = stm32_toolkit.cli:main\n"
        "stm32-toolkit-mcp = stm32_toolkit.cli:mcp_main\n",
        encoding="utf-8",
    )


def _write_fake_public_launchers(runtime: Path) -> None:
    from pip._vendor.distlib.scripts import ScriptMaker

    scripts = runtime / "Scripts"
    maker = ScriptMaker(None, str(scripts))
    maker.executable = str(scripts / "python.exe")
    maker.variants = {""}
    maker.clobber = True
    maker.make_multiple(
        [
            "stm32-toolkit = stm32_toolkit.cli:main",
            "stm32-toolkit-mcp = stm32_toolkit.cli:mcp_main",
            "stm32-monitor = stm32_monitor.cli:main",
        ]
    )


def _launcher_contains(launcher_bytes: bytes, path: Path) -> bool:
    haystack = launcher_bytes.lower()
    text = str(path)
    variants = {text, text.replace("\\", "/"), text.replace("/", "\\")}
    return any(
        token in haystack
        for value in variants
        for token in (value.encode("utf-8").lower(), value.encode("utf-16le").lower())
    )


def _replace_launcher_binding(path: Path, old: Path, new: Path) -> None:
    data = bytearray(path.read_bytes())
    old_bytes = str(old).encode("utf-8")
    index = data.lower().find(old_bytes.lower())
    assert index >= 0
    replacement = str(new).encode("utf-8")
    assert len(replacement) <= len(old_bytes)
    data[index : index + len(old_bytes)] = replacement + b"\0" * (len(old_bytes) - len(replacement))
    path.write_bytes(data)


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _fake_monitor_cli_source() -> str:
    return (
        "import sys\n"
        "def main():\n"
        "    if sys.argv[1:] == ['version']:\n"
        "        print('0.9.0')\n"
        "        return 0\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _fake_toolkit_cli_source() -> str:
    payload = {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "data": {
            "runtime": {
                "requiredPython": ">=3.12,<3.13",
                "pythonVersion": "3.12.0",
                "pythonSupported": True,
                "toolkitVersion": "0.9.0",
                "monitorVersion": "0.9.0",
                "versionsCompatible": True,
            },
            "publicInventory": {
                "mcpTools": list(FAKE_MCP_TOOLS),
                "skills": list(FAKE_SKILLS),
            },
        },
    }
    return (
        "import json,sys\n"
        "def main():\n"
        "    if sys.argv[1:] == ['version']:\n"
        "        print('0.9.0')\n"
        "        return 0\n"
        "    if 'doctor' in sys.argv:\n"
        f"        payload={payload!r}\n"
        "        payload['data']['runtime']['pythonVersion']='.'.join(str(part) for part in sys.version_info[:3])\n"
        "        payload['data']['runtime']['pythonSupported']=sys.version_info[:2] == (3,12)\n"
        "        i=sys.argv.index('--project-root'); payload['data']['projectRoot']=sys.argv[i+1]; payload['data']['argv']=sys.argv[1:]\n"
        "        print(json.dumps(payload))\n"
        "        return 0\n"
        "    return 2\n"
        "def mcp_main():\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _fake_incomplete_toolkit_cli_source() -> str:
    return (
        "import json,sys\n"
        "def main():\n"
        "    if sys.argv[1:] == ['version']:\n"
        "        print('0.9.0')\n"
        "        return 0\n"
        "    if 'doctor' in sys.argv:\n"
        "        print(json.dumps({'ok':True,'data':{}}))\n"
        "        return 0\n"
        "    return 2\n"
        "def mcp_main():\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _install_fake_probe(site_packages: Path, probe_version: str) -> None:
    probe = site_packages / "pyocd"
    probe.mkdir()
    (probe / "__init__.py").write_text(
        f"__version__ = {probe_version!r}\n", encoding="utf-8"
    )
    metadata = site_packages / f"pyocd-{probe_version}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: pyocd\nVersion: {probe_version}\n",
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
    helper: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    helper_path = helper or HELPER
    fixture_utility = plugin_root / "tools" / "release" / "build_0900_artifacts.py"
    fixture_policy = plugin_root / "tools" / "release" / "release_0900_policy.json"
    if helper is None and plugin_root != REPO_ROOT and fixture_utility.is_file() and fixture_policy.is_file():
        helper_text = HELPER.read_text(encoding="utf-8")
        utility_hash = hashlib.sha256(fixture_utility.read_bytes()).hexdigest()
        policy_hash = hashlib.sha256(fixture_policy.read_bytes()).hexdigest()
        helper_text = re.sub(r'(?m)^(\$ReleaseUtilitySha256\s*=\s*")[0-9a-f]{64}("\s*)$', rf'\g<1>{utility_hash}\g<2>', helper_text)
        helper_text = re.sub(r'(?m)^(\$ReleasePolicySha256\s*=\s*")[0-9a-f]{64}("\s*)$', rf'\g<1>{policy_hash}\g<2>', helper_text)
        helper_path = plugin_data.parent / "setup-stm32-env-fixture.ps1"
        helper_path.write_text(helper_text, encoding="utf-8", newline="")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper_path),
            "-Mode",
            mode,
            "-ToolkitRoot",
            str(plugin_root),
            "-DataRoot",
            str(plugin_data),
            "-ProjectRoot",
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
    for name in (
        "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR",
        "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP",
    ):
        environment.pop(name, None)
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), str(Path(os.environ["SystemRoot"]) / "System32")]
    )
    return environment
