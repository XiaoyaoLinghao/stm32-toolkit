"""VSCODE-TASKS generation and binding tests.

Every project is a disposable synthetic tree below ``tmp_path``.  Generated
executables are inert placeholder files: validation is static and never
launches or version-attests them.  No probe, hardware, network, original
project or installed runtime is touched.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.mcp_server as mcp_mod
import stm32_toolkit.vscode_configuration as vscode_config_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.generation import (
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.generation.managed_files import plan_id_for
from stm32_toolkit.mcp_server import ServerRuntime
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.vscode_configuration import (
    VSCodeConfiguration,
    VSCodeConfigurationError,
    normalize_vscode_configuration,
)
from stm32_toolkit.workflows import configure_project_workflow

from test_generation import (
    fail_replace_at,
    plan_for,
    standard_payload,
    tree_snapshot,
    write_project,
)
from test_mcp_roots import _RootSession, _context

INVALID = "VSCODE_CONFIGURATION_INVALID"


def _native_executable(directory: Path, name: str = "stm32-toolkit.exe") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"MZ placeholder native executable\n")
    return path


def _bound_plan(root: Path, toolkit: Path, gcc: Path):
    return plan_project_configuration(
        load_project_model(root),
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )


def _rendered(plan, path: str) -> dict:
    entry = next(entry for entry in plan.files if entry.path == path)
    return json.loads(entry.after_bytes.decode("utf-8"))


def _double(root: Path, tmp_path: Path):
    toolkit = _native_executable(tmp_path / "Tools 工具", "stm32-toolkit.exe")
    gcc = _native_executable(tmp_path / "Tools 工具", "arm-none-eabi-gcc.exe")
    return toolkit, gcc


# ---------------------------------------------------------------------------
# deterministic defaults
# ---------------------------------------------------------------------------


def test_default_plan_keeps_portable_user_setting_defaults(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)

    assert plan.vscode_configuration is None
    assert "vscode_configuration" not in plan.to_dict()

    tasks = _rendered(plan, ".vscode/tasks.json")["tasks"]
    for task in tasks:
        assert task["command"] == "${config:stm32-toolkit.executablePath}"
    c_cpp = _rendered(plan, ".vscode/c_cpp_properties.json")
    assert c_cpp["configurations"][0]["compilerPath"] == (
        "${config:stm32-toolkit.compilerPath}"
    )
    # Generation never writes empty (or any) workspace overrides for the two
    # user-scope settings.
    settings = _rendered(plan, ".vscode/settings.json")
    assert set(settings) == {"cmake.configureOnOpen", "cmake.useCMakePresets"}
    assert "stm32-toolkit.executablePath" not in json.dumps(settings)
    assert "stm32-toolkit.compilerPath" not in json.dumps(settings)


def test_default_plan_is_deterministic_and_still_leaves_launch_empty(tmp_path):
    root = write_project(tmp_path / "proj")
    first = plan_for(root)
    second = plan_for(root)
    assert first.plan_id == second.plan_id
    assert _rendered(first, ".vscode/launch.json") == {
        "version": "0.2.0",
        "configurations": [],
    }


# ---------------------------------------------------------------------------
# explicit immutable binding
# ---------------------------------------------------------------------------


def test_explicit_binding_renders_exact_paths_and_binds_identity(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)

    plan = _bound_plan(root, toolkit, gcc)

    assert plan.vscode_configuration == VSCodeConfiguration(str(toolkit), str(gcc))
    payload = plan.to_dict()
    assert payload["vscode_configuration"] == {
        "toolkitPath": str(toolkit),
        "gccPath": str(gcc),
    }
    assert plan.plan_id == plan_id_for(plan)
    assert plan.plan_id != plan_for(root).plan_id

    tasks = _rendered(plan, ".vscode/tasks.json")["tasks"]
    assert [task["label"] for task in tasks] == [
        "STM32 Toolkit: Build Debug",
        "STM32 Toolkit: Build Release",
        "STM32 Toolkit: Flash Debug",
        "STM32 Toolkit: Handoff Begin Debug",
        "STM32 Toolkit: Handoff End Debug",
    ]
    for task in tasks:
        assert task["command"] == str(toolkit)
        assert task["args"][0:2] == ["--project-root", "${workspaceFolder}"]
        assert task["options"] == {"cwd": "${workspaceFolder}"}
        assert "dependsOn" not in task and "group" not in task
    c_cpp = _rendered(plan, ".vscode/c_cpp_properties.json")
    assert c_cpp["configurations"][0]["compilerPath"] == str(gcc)
    # The compiler binding is IntelliSense-only; the toolchain file and CMake
    # preset still select the build toolchain through the normal contract.
    toolchain = next(
        entry
        for entry in plan.files
        if entry.path == "cmake/arm-none-eabi-gcc.cmake"
    )
    assert b"set(CMAKE_C_COMPILER arm-none-eabi-gcc)" in toolchain.after_bytes

    applied = apply_project_configuration(plan)
    assert applied.ok is True, applied
    on_disk = json.loads((root / ".vscode" / "tasks.json").read_text("utf-8"))
    assert {task["command"] for task in on_disk["tasks"]} == {str(toolkit)}
    disk_c_cpp = json.loads(
        (root / ".vscode" / "c_cpp_properties.json").read_text("utf-8")
    )
    assert disk_c_cpp["configurations"][0]["compilerPath"] == str(gcc)


def test_binding_participates_in_plan_identity_and_replay(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)

    plan = _bound_plan(root, toolkit, gcc)
    again = _bound_plan(root, toolkit, gcc)
    assert again.plan_id == plan.plan_id

    other_toolkit = _native_executable(
        tmp_path / "Other", "stm32-toolkit.exe"
    )
    changed = _bound_plan(root, other_toolkit, gcc)
    assert changed.plan_id != plan.plan_id

    unbound = plan_for(root)
    assert unbound.plan_id != plan.plan_id
    assert "vscode_configuration" not in unbound.to_dict()


def test_apply_rejects_changed_or_omitted_binding_as_a_different_plan(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    other = _native_executable(tmp_path / "Other", "stm32-toolkit.exe")

    planned = configure_project_workflow(
        root,
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )
    assert planned.ok is True
    plan_id = planned.data["plan_id"]
    assert planned.data["vscode_configuration"] == {
        "toolkitPath": str(toolkit),
        "gccPath": str(gcc),
    }
    before = tree_snapshot(root)

    omitted = configure_project_workflow(
        root, plan_id=plan_id, authorized=True
    )
    assert omitted.ok is False and omitted.code == "PLAN_CHANGED"
    changed = configure_project_workflow(
        root,
        plan_id=plan_id,
        authorized=True,
        vscode_toolkit_path=str(other),
        vscode_gcc_path=str(gcc),
    )
    assert changed.ok is False and changed.code == "PLAN_CHANGED"
    assert tree_snapshot(root) == before

    applied = configure_project_workflow(
        root,
        plan_id=plan_id,
        authorized=True,
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )
    assert applied.ok is True, applied
    assert applied.operation == "project-configuration-apply"


def test_new_omitted_plan_after_accepted_binding_returns_portable_defaults(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    bound = _bound_plan(root, toolkit, gcc)
    applied = apply_project_configuration(bound)
    assert applied.ok is True, applied

    bound_tasks = json.loads(
        (root / ".vscode" / "tasks.json").read_text("utf-8")
    )["tasks"]
    assert {task["command"] for task in bound_tasks} == {str(toolkit)}
    project_model = (root / ".stm32-project.json").read_bytes()

    portable = plan_for(root)
    assert portable.vscode_configuration is None
    assert "vscode_configuration" not in portable.to_dict()
    assert portable.plan_id != bound.plan_id
    tasks = next(
        entry for entry in portable.files if entry.path == ".vscode/tasks.json"
    )
    c_cpp = next(
        entry
        for entry in portable.files
        if entry.path == ".vscode/c_cpp_properties.json"
    )
    assert tasks.status == "update-managed"
    assert c_cpp.status == "update-managed"
    portable_tasks = json.loads(tasks.after_bytes.decode("utf-8"))["tasks"]
    assert {task["command"] for task in portable_tasks} == {
        "${config:stm32-toolkit.executablePath}"
    }
    portable_c_cpp = json.loads(c_cpp.after_bytes.decode("utf-8"))
    assert portable_c_cpp["configurations"][0]["compilerPath"] == (
        "${config:stm32-toolkit.compilerPath}"
    )
    # The reviewed diff shows the binding being returned to portable defaults.
    assert "${config:stm32-toolkit.executablePath}" in tasks.unified_diff
    assert "${config:stm32-toolkit.compilerPath}" in c_cpp.unified_diff
    # Omission never persists the invocation-scoped local paths into the model.
    assert (root / ".stm32-project.json").read_bytes() == project_model

    restored = apply_project_configuration(portable)
    assert restored.ok is True, restored
    disk_tasks = json.loads(
        (root / ".vscode" / "tasks.json").read_text("utf-8")
    )["tasks"]
    assert {task["command"] for task in disk_tasks} == {
        "${config:stm32-toolkit.executablePath}"
    }
    disk_c_cpp = json.loads(
        (root / ".vscode" / "c_cpp_properties.json").read_text("utf-8")
    )
    assert disk_c_cpp["configurations"][0]["compilerPath"] == (
        "${config:stm32-toolkit.compilerPath}"
    )
    assert (root / ".stm32-project.json").read_bytes() == project_model


def test_forged_or_removed_binding_is_refused_before_write(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    other = _native_executable(tmp_path / "Other", "stm32-toolkit.exe")
    plan = _bound_plan(root, toolkit, gcc)
    before = tree_snapshot(root)

    forged = replace(
        plan, vscode_configuration=VSCodeConfiguration(str(other), str(gcc))
    )
    result = apply_project_configuration(forged)
    assert result.ok is False
    assert result.code == "GENERATION_PLAN_INVALID"
    assert tree_snapshot(root) == before

    removed_binding = replace(plan, vscode_configuration=None)
    result = apply_project_configuration(removed_binding)
    assert result.ok is False
    assert result.code == "GENERATION_PLAN_INVALID"
    assert tree_snapshot(root) == before

    # Removing the bound executable invalidates exact replay too.
    toolkit.unlink()
    result = apply_project_configuration(plan)
    assert result.ok is False
    assert result.code == "GENERATION_PLAN_INVALID"
    assert tree_snapshot(root) == before


def test_binding_plan_reuses_the_atomic_transaction_and_rolls_back(tmp_path, monkeypatch):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    plan = _bound_plan(root, toolkit, gcc)
    original_manifest = (root / ".stm32-project.json").read_bytes()

    fail_replace_at(monkeypatch, {2})
    result = apply_project_configuration(plan)
    assert result.ok is False
    assert result.code == "GENERATION_APPLY_FAILED"
    assert dict(result.details) == {"phase": "replace"}
    # Every destination is a first-time create, so rollback removes the
    # partial outputs and the directories it created.
    assert not (root / "CMakeLists.txt").exists()
    assert not (root / ".vscode").exists()
    assert not (root / ".stm32-toolkit" / "configuration-staging").exists()
    assert (root / ".stm32-project.json").read_bytes() == original_manifest


# ---------------------------------------------------------------------------
# static validation
# ---------------------------------------------------------------------------


def _direct_error(toolkit, gcc) -> VSCodeConfigurationError:
    with pytest.raises(VSCodeConfigurationError) as info:
        normalize_vscode_configuration(toolkit, gcc)
    return info.value


def test_normalize_omits_the_pair_only_when_both_are_none():
    assert normalize_vscode_configuration(None, None) is None


def test_partial_pair_names_the_missing_field(tmp_path):
    toolkit, gcc = _double(tmp_path / "proj", tmp_path)

    only_toolkit = _direct_error(str(toolkit), None)
    assert only_toolkit.details["field"] == "vscode.gccPath"
    assert only_toolkit.details["rule"] == "missing"
    assert only_toolkit.details["missingFields"] == ["vscode.gccPath"]

    only_gcc = _direct_error(None, str(gcc))
    assert only_gcc.details["field"] == "vscode.toolkitPath"
    assert only_gcc.details["rule"] == "missing"
    assert only_gcc.details["missingFields"] == ["vscode.toolkitPath"]

    for error in (only_toolkit, only_gcc):
        entry = error.details["diagnostics"][0]
        assert entry["code"] == INVALID
        assert "vscode-toolkit-path" in entry["remediation"]
        assert "vscodeToolkitPath" in entry["remediation"]


@pytest.mark.parametrize(
    ("toolkit_factory", "rule"),
    [
        (lambda _tmp: 7, "type"),
        (lambda _tmp: ["path"], "type"),
        (lambda _tmp: True, "type"),
        (lambda _tmp: "", "empty"),
        (lambda _tmp: "   ", "empty"),
        (lambda _tmp: "relative.exe", "relative"),
        (lambda _tmp: "${workspaceFolder}/stm32-toolkit.exe", "variable"),
        (lambda _tmp: "%TOOLKIT%/stm32-toolkit.exe", "variable"),
    ],
)
def test_unsafe_values_are_refused_with_stable_rules(tmp_path, toolkit_factory, rule):
    _toolkit, gcc = _double(tmp_path / "proj", tmp_path)
    value = toolkit_factory(tmp_path)
    error = _direct_error(value, str(gcc))
    assert error.details["field"] == "vscode.toolkitPath"
    assert error.details["rule"] == rule


def test_control_characters_are_refused(tmp_path):
    _toolkit, gcc = _double(tmp_path / "proj", tmp_path)
    value = str(tmp_path / "bad\x01tool.exe")
    error = _direct_error(value, str(gcc))
    assert error.details["rule"] == "control"


def test_filesystem_rules_are_static_and_closed(tmp_path):
    _toolkit, gcc = _double(tmp_path / "proj", tmp_path)

    missing = _direct_error(str(tmp_path / "missing.exe"), str(gcc))
    assert missing.details["rule"] == "notFound"

    fake_directory = tmp_path / "directory.exe"
    fake_directory.mkdir()
    directory = _direct_error(str(fake_directory), str(gcc))
    assert directory.details["rule"] == "directory"

    if os.name == "nt":
        script = tmp_path / "stm32-toolkit.cmd"
        script.write_text("@echo off\n", encoding="utf-8")
        extension = _direct_error(str(script), str(gcc))
        assert extension.details["rule"] == "extension"
        assert extension.details["field"] == "vscode.toolkitPath"


def test_redirect_targets_are_refused(tmp_path):
    toolkit, gcc = _double(tmp_path / "proj", tmp_path)
    link = tmp_path / "linked-toolkit.exe"
    try:
        os.symlink(toolkit, link)
    except (OSError, NotImplementedError):
        pytest.skip("host cannot create a file symlink for this check")
    error = _direct_error(str(link), str(gcc))
    assert error.details["rule"] == "redirect"


def _reparse(real) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=real.st_mode,
        st_file_attributes=(
            getattr(real, "st_file_attributes", 0) | 0x400
        ),
    )


def _patch_reparse(monkeypatch, target: Path) -> None:
    real_lstat = os.lstat

    def fake_lstat(path):
        metadata = real_lstat(path)
        if Path(path) == target:
            return _reparse(metadata)
        return metadata

    monkeypatch.setattr(vscode_config_mod, "_LSTAT", fake_lstat)


def test_redirected_parent_component_is_refused_without_resolving(tmp_path, monkeypatch):
    toolkit, gcc = _double(tmp_path / "proj", tmp_path)
    junction = toolkit.parent
    _patch_reparse(monkeypatch, junction)

    error = _direct_error(str(toolkit), str(gcc))

    assert error.details["field"] == "vscode.toolkitPath"
    assert error.details["rule"] == "redirect"


def test_redirected_leaf_is_refused_without_resolving(tmp_path, monkeypatch):
    toolkit, gcc = _double(tmp_path / "proj", tmp_path)
    _patch_reparse(monkeypatch, toolkit)

    error = _direct_error(str(toolkit), str(gcc))

    assert error.details["field"] == "vscode.toolkitPath"
    assert error.details["rule"] == "redirect"


def test_missing_and_non_directory_parents_are_refused(tmp_path):
    _toolkit, gcc = _double(tmp_path / "proj", tmp_path)

    missing_parent = tmp_path / "missing-parent" / "stm32-toolkit.exe"
    missing = _direct_error(str(missing_parent), str(gcc))
    assert missing.details["rule"] == "notFound"

    plain_parent = tmp_path / "plain-parent"
    plain_parent.write_bytes(b"not a directory\n")
    file_parent = plain_parent / "stm32-toolkit.exe"
    parent = _direct_error(str(file_parent), str(gcc))
    assert parent.details["rule"] == "parent"


def test_spaces_and_unicode_paths_remain_valid(tmp_path):
    directory = tmp_path / "Tool 工具 dir"
    toolkit = _native_executable(directory, "stm32-toolkit.exe")
    gcc = _native_executable(directory, "arm-none-eabi-gcc.exe")

    config = normalize_vscode_configuration(str(toolkit), str(gcc))

    assert config == VSCodeConfiguration(str(toolkit), str(gcc))


def test_plan_and_apply_reject_a_redirected_parent_without_writes(tmp_path, monkeypatch):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    junction = toolkit.parent
    before = tree_snapshot(root)

    _patch_reparse(monkeypatch, junction)
    planned = configure_project_workflow(
        root, vscode_toolkit_path=str(toolkit), vscode_gcc_path=str(gcc)
    )
    assert planned.ok is False
    assert planned.code == INVALID
    assert dict(planned.details)["rule"] == "redirect"
    assert tree_snapshot(root) == before

    monkeypatch.undo()
    plan = _bound_plan(root, toolkit, gcc)
    before = tree_snapshot(root)
    _patch_reparse(monkeypatch, junction)
    applied = apply_project_configuration(plan)
    assert applied.ok is False
    assert applied.code == "GENERATION_PLAN_INVALID"
    assert tree_snapshot(root) == before


def test_configure_workflow_refuses_invalid_pair_before_planning(tmp_path):
    root = write_project(tmp_path / "proj")
    _toolkit, gcc = _double(root, tmp_path)
    before = tree_snapshot(root)

    result = configure_project_workflow(
        root, vscode_toolkit_path="stm32-toolkit", vscode_gcc_path=str(gcc)
    )
    assert result.ok is False
    assert result.code == INVALID
    assert dict(result.details)["field"] == "vscode.toolkitPath"
    assert tree_snapshot(root) == before


# ---------------------------------------------------------------------------
# combined routes and user-owned files
# ---------------------------------------------------------------------------


def test_debug_pair_and_binding_share_one_plan_and_preserve_unowned_files(tmp_path):
    payload = standard_payload(debug={})
    root = write_project(tmp_path / "proj", payload)
    tasks_path = root / ".vscode" / "tasks.json"
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    user_bytes = b'{"version": "2.0.0", "tasks": []}\n'
    tasks_path.write_bytes(user_bytes)
    toolkit, gcc = _double(root, tmp_path)
    before_manifest = (root / ".stm32-project.json").read_bytes()

    planned = configure_project_workflow(
        root,
        debug_backend="pyocd",
        debug_target="stm32f407vg",
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )
    assert planned.ok is True, planned
    data = planned.data
    assert data["debug_configuration"] == {
        "backend": "pyocd",
        "target": "stm32f407vg",
    }
    assert data["manifest_edit"]["status"] == "update"
    assert data["vscode_configuration"] == {
        "toolkitPath": str(toolkit),
        "gccPath": str(gcc),
    }
    tasks_entry = next(
        entry for entry in data["files"] if entry["path"] == ".vscode/tasks.json"
    )
    assert tasks_entry["status"] == "preserved-unowned"
    assert (root / ".stm32-project.json").read_bytes() == before_manifest

    applied = configure_project_workflow(
        root,
        plan_id=data["plan_id"],
        authorized=True,
        debug_backend="pyocd",
        debug_target="stm32f407vg",
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )
    assert applied.ok is True, applied
    assert applied.data["manifestEditStatus"] == "update"
    assert ".vscode/tasks.json" in applied.data["preservedPaths"]
    # The user-owned editor file is never rewritten or adopted.
    assert tasks_path.read_bytes() == user_bytes
    assert json.loads((root / ".stm32-project.json").read_text("utf-8"))["debug"] == {
        "backend": "pyocd",
        "target": "stm32f407vg",
    }
    c_cpp = json.loads(
        (root / ".vscode" / "c_cpp_properties.json").read_text("utf-8")
    )
    assert c_cpp["configurations"][0]["compilerPath"] == str(gcc)


# ---------------------------------------------------------------------------
# CLI and MCP propagation (no new MCP tool)
# ---------------------------------------------------------------------------


def test_cli_propagates_binding_and_refuses_omitted_apply(tmp_path, capsys):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--dry-run",
                "--json",
                "--vscode-toolkit-path",
                str(toolkit),
                "--vscode-gcc-path",
                str(gcc),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["vscode_configuration"] == {
        "toolkitPath": str(toolkit),
        "gccPath": str(gcc),
    }
    plan_id = payload["data"]["plan_id"]

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--apply",
                "--plan-id",
                plan_id,
                "--authorized",
                "--json",
            ]
        )
        == 2
    )
    omitted = json.loads(capsys.readouterr().out)
    assert omitted["code"] == "PLAN_CHANGED"

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--apply",
                "--plan-id",
                plan_id,
                "--authorized",
                "--json",
                "--vscode-toolkit-path",
                str(toolkit),
                "--vscode-gcc-path",
                str(gcc),
            ]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    assert applied["operation"] == "project-configuration-apply"


def test_mcp_wrapper_propagates_binding_and_keeps_root_boundary(tmp_path):
    root = write_project(tmp_path / "proj")
    toolkit, gcc = _double(root, tmp_path)
    runtime = ServerRuntime.create(root, tmp_path / "data", "session-a")

    planned = asyncio.run(
        mcp_mod.tool_project_configure_for_request(
            runtime,
            None,
            vscode_toolkit_path=str(toolkit),
            vscode_gcc_path=str(gcc),
        )
    )
    assert planned["ok"] is True
    assert planned["data"]["vscode_configuration"] == {
        "toolkitPath": str(toolkit),
        "gccPath": str(gcc),
    }
    applied = mcp_mod.tool_project_configure(
        runtime,
        plan_id=planned["data"]["plan_id"],
        authorized=True,
        vscode_toolkit_path=str(toolkit),
        vscode_gcc_path=str(gcc),
    )
    assert applied["ok"] is True
    assert applied["operation"] == "project-configuration-apply"

    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[root, other]])
    guarded = asyncio.run(
        mcp_mod.tool_project_configure_for_request(
            runtime,
            _context(session),
            vscode_toolkit_path=str(toolkit),
            vscode_gcc_path=str(gcc),
        )
    )
    assert guarded["ok"] is False
    assert guarded["code"] == "UNSUPPORTED_MULTIROOT"
