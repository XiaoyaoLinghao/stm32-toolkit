"""Shared workflow adapter tests (STM32TK-0306).

The adapter layer owns input validation, exception translation, fresh
replanning, and plan-ID comparison; the accepted core modules own every
mutation.  These tests prove the adapter never calls a core apply seam
without the exact current plan ID plus JSON boolean ``true`` authorization,
that plan calls never change bytes, names, mtimes, modes, or Git state, and
that the CLI and MCP layers observe identical operation/code/data envelopes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import stm32_toolkit.workflows as workflows_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.workflows import (
    AUTHORIZATION_REQUIRED,
    CONFIGURATION_PLAN_UNAVAILABLE,
    KEIL_INSPECTION_UNAVAILABLE,
    MIGRATION_PLAN_UNAVAILABLE,
    PLAN_CHANGED,
    WORKFLOW_INPUT_INVALID,
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    inspect_keil_workflow,
)

from test_build_runner import install_fake_cmake, prepare_project
from test_migration_apply import build_repo, git_init, snapshot_tree

MAIN_C = (
    "/* main.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void early_init(void) { __nop(); }\n"
    "\n"
    "int main(void) { return 0; }\n"
)

COMMON_C = (
    "/* common.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void systick_isr(void)\n"
    "{\n"
    "    __nop();\n"
    "    __wfi();\n"
    "}\n"
    "\n"
    '__asm("nop");\n'
    "\n"
    '__attribute__((section(".common.data"))) int shared_value;\n'
    "__attribute__((at(0x20000000))) int pinned_value;\n"
    "\n"
    "int common_work(void) { return 0; }\n"
)

GITIGNORE = "build/\n.stm32-toolkit/build.lock\n__pycache__/\n*.pyc\n"


def keil_repo(tmp_path: Path) -> Path:
    """Disposable clean-Git Keil repository with the standard convertible sources."""
    return build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        gitignore=GITIGNORE,
    )


def git_porcelain(root: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _count_apply_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count how many times the real core apply seam is invoked."""
    calls = {"n": 0}
    real_convert = workflows_mod.apply_keil_conversion
    real_configure = workflows_mod.apply_project_configuration

    def counting_convert(plan):
        calls["n"] += 1
        return real_convert(plan)

    def counting_configure(plan):
        calls["n"] += 1
        return real_configure(plan)

    monkeypatch.setattr(workflows_mod, "apply_keil_conversion", counting_convert)
    monkeypatch.setattr(
        workflows_mod, "apply_project_configuration", counting_configure
    )
    return calls


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def test_inspect_workflow_returns_inspection_and_baseline_in_order(tmp_path: Path):
    root = keil_repo(tmp_path)

    result = inspect_keil_workflow(root)

    assert result.ok is True
    assert result.operation == "keil-inspect"
    data = result.to_dict()["data"]
    assert list(data) == ["inspection", "baseline"]
    assert data["inspection"]["device"] == "STM32F429ZGTx"
    assert data["inspection"]["target_name"] == "Legacy"
    assert isinstance(data["baseline"], dict)


def test_inspect_workflow_without_baseline_returns_null_baseline(tmp_path: Path):
    root = keil_repo(tmp_path)

    result = inspect_keil_workflow(root, include_baseline=False)

    assert result.ok is True
    data = result.to_dict()["data"]
    assert data["inspection"]["device"] == "STM32F429ZGTx"
    assert data["baseline"] is None


def test_inspect_and_plan_calls_preserve_complete_tree_and_git_state(tmp_path: Path):
    """Regression: read-only plan calls never change bytes/names/mtimes/modes/Git."""
    root = keil_repo(tmp_path)
    before_tree = snapshot_tree(root)
    before_git = git_porcelain(root)

    assert inspect_keil_workflow(root).ok is True
    plan = convert_keil_workflow(root)
    assert plan.ok is True

    assert snapshot_tree(root) == before_tree
    assert git_porcelain(root) == before_git


def test_inspect_workflow_accepts_explicit_uvprojx_and_target(tmp_path: Path):
    root = keil_repo(tmp_path)

    result = inspect_keil_workflow(
        root, uvprojx="app.uvprojx", target_name="Legacy"
    )

    assert result.ok is True
    assert result.to_dict()["data"]["inspection"]["project_file"] == "app.uvprojx"


def test_inspect_workflow_bad_project_root_is_input_invalid(tmp_path: Path):
    result = inspect_keil_workflow(tmp_path / "missing")

    assert result.ok is False
    assert result.code == WORKFLOW_INPUT_INVALID
    assert result.operation == "keil-inspect"
    assert dict(result.details) == {"field": "projectRoot", "rule": "value"}


@pytest.mark.parametrize(
    "unsafe",
    [
        "../escape.uvprojx",
        "/absolute.uvprojx",
        "sub\\..\\escape.uvprojx",
        "C:/drive.uvprojx",
        "D:drive-relative.uvprojx",
        "bad\x00nul.uvprojx",
        "",
        "sub\\\\backslash.uvprojx",
        "a/../b.uvprojx",
        "./dot.uvprojx",
        "//unc.uvprojx",
    ],
)
def test_inspect_workflow_rejects_unsafe_uvprojx_paths(tmp_path: Path, unsafe: str):
    root = keil_repo(tmp_path)
    before_tree = snapshot_tree(root)

    result = inspect_keil_workflow(root, uvprojx=unsafe)

    assert result.ok is False
    assert result.code == WORKFLOW_INPUT_INVALID
    assert dict(result.details) == {"field": "uvprojx", "rule": "portablePath"}
    assert snapshot_tree(root) == before_tree


def test_inspect_workflow_rejects_non_string_uvprojx_and_target(tmp_path: Path):
    root = keil_repo(tmp_path)

    for kwargs in ({"uvprojx": 7}, {"target_name": 7}):
        result = inspect_keil_workflow(root, **kwargs)
        assert result.ok is False
        assert result.code == WORKFLOW_INPUT_INVALID


def test_inspect_workflow_translates_stable_inspection_errors(tmp_path: Path):
    """KeilInspectionError stable fields pass through; no exception text leaks."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "other.txt").write_text("not a project", encoding="utf-8")

    result = inspect_keil_workflow(root)

    assert result.ok is False
    assert result.code == "KEIL_PROJECT_NOT_FOUND"
    assert "Traceback" not in json.dumps(result.to_dict())


def test_inspect_workflow_maps_unexpected_failures_to_unavailable(
    monkeypatch, tmp_path: Path
):
    root = keil_repo(tmp_path)
    monkeypatch.setattr(
        workflows_mod, "inspect_keil", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    )

    result = inspect_keil_workflow(root)

    assert result.ok is False
    assert result.code == KEIL_INSPECTION_UNAVAILABLE
    assert "boom" not in json.dumps(result.to_dict())


# ---------------------------------------------------------------------------
# conversion plan/apply
# ---------------------------------------------------------------------------


def test_convert_plan_mode_returns_deterministic_plan(tmp_path: Path):
    root = keil_repo(tmp_path)

    first = convert_keil_workflow(root)
    second = convert_keil_workflow(root)

    assert first.ok is True
    assert first.operation == "keil-conversion-plan"
    first_data = first.to_dict()["data"]
    assert first_data["plan_id"] == second.to_dict()["data"]["plan_id"]
    assert len(first_data["plan_id"]) == 64
    assert first_data["blockers"] == []


def test_convert_apply_without_authorization_fails_closed_without_writes(
    monkeypatch, tmp_path: Path
):
    """Regression: apply intent without boolean-true authorization never applies."""
    root = keil_repo(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    plan_id = convert_keil_workflow(root).to_dict()["data"]["plan_id"]
    before_tree = snapshot_tree(root)
    before_git = git_porcelain(root)

    for authorized in (False, "true", 1, None, [], {}):
        result = convert_keil_workflow(root, plan_id=plan_id, authorized=authorized)
        assert result.ok is False
        assert result.code == AUTHORIZATION_REQUIRED
        assert result.operation == "keil-conversion-apply"

    assert calls["n"] == 0
    assert snapshot_tree(root) == before_tree
    assert git_porcelain(root) == before_git


def test_convert_apply_without_plan_id_or_malformed_plan_id_fails_closed(
    monkeypatch, tmp_path: Path
):
    root = keil_repo(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    before_tree = snapshot_tree(root)

    missing = convert_keil_workflow(root, authorized=True)
    assert missing.ok is False
    assert missing.code == AUTHORIZATION_REQUIRED
    assert dict(missing.details) == {"field": "planId", "rule": "required"}

    malformed = convert_keil_workflow(root, authorized=True, plan_id="not-a-plan-id")
    assert malformed.ok is False
    assert malformed.code == AUTHORIZATION_REQUIRED
    assert malformed.details["field"] == "planId"

    stale = convert_keil_workflow(root, authorized=True, plan_id="0" * 64)
    assert stale.ok is False
    assert stale.code == PLAN_CHANGED
    assert dict(stale.details) == {
        "field": "planId",
        "rule": "stale",
        "currentPlanId": convert_keil_workflow(root).to_dict()["data"]["plan_id"],
    }

    assert calls["n"] == 0
    assert snapshot_tree(root) == before_tree


def test_convert_apply_success_applies_exactly_once(monkeypatch, tmp_path: Path):
    """Exact current plan ID plus boolean true calls the apply seam once."""
    root = keil_repo(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    plan_id = convert_keil_workflow(root).to_dict()["data"]["plan_id"]
    uvprojx_before = (root / "app.uvprojx").read_bytes()

    result = convert_keil_workflow(root, plan_id=plan_id, authorized=True)

    assert result.ok is True
    assert result.operation == "keil-conversion-apply"
    assert calls["n"] == 1
    assert (root / "artifacts" / "migration" / "conversion-report.json").is_file()
    assert (root / ".stm32-project.json").is_file()
    assert "void systick_isr" in (root / "Common" / "common.c").read_text(encoding="utf-8")
    assert (root / "app.uvprojx").read_bytes() == uvprojx_before


def test_convert_apply_disk_change_between_plan_and_apply_is_plan_changed(
    monkeypatch, tmp_path: Path
):
    """Regression: a disk change after planning makes the fresh plan ID differ."""
    root = keil_repo(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    plan_id = convert_keil_workflow(root).to_dict()["data"]["plan_id"]
    main_c = root / "Main" / "main.c"
    main_c.write_text(main_c.read_text(encoding="utf-8") + "/* user edit */\n", encoding="utf-8")

    result = convert_keil_workflow(root, plan_id=plan_id, authorized=True)

    assert result.ok is False
    assert result.code == PLAN_CHANGED
    assert calls["n"] == 0
    assert "/* user edit */" in main_c.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# configuration plan/apply
# ---------------------------------------------------------------------------


def test_configure_plan_mode_is_read_only_and_deterministic(
    tmp_path: Path, monkeypatch
):
    root = prepare_project(tmp_path)
    before_tree = snapshot_tree(root)

    first = configure_project_workflow(root)
    second = configure_project_workflow(root)

    assert first.ok is True
    assert first.operation == "project-configuration-plan"
    assert first.to_dict()["data"]["plan_id"] == second.to_dict()["data"]["plan_id"]
    assert len(first.to_dict()["data"]["plan_id"]) == 64
    assert snapshot_tree(root) == before_tree


def test_configure_apply_requires_authorization_and_exact_plan(
    monkeypatch, tmp_path: Path
):
    root = prepare_project(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    plan_id = configure_project_workflow(root).to_dict()["data"]["plan_id"]
    before_tree = snapshot_tree(root)

    for authorized in (False, "true", 1):
        result = configure_project_workflow(root, plan_id=plan_id, authorized=authorized)
        assert result.ok is False
        assert result.code == AUTHORIZATION_REQUIRED
        assert result.operation == "project-configuration-apply"

    missing = configure_project_workflow(root, authorized=True)
    assert missing.code == AUTHORIZATION_REQUIRED
    assert dict(missing.details) == {"field": "planId", "rule": "required"}

    stale = configure_project_workflow(root, authorized=True, plan_id="0" * 64)
    assert stale.code == PLAN_CHANGED

    assert calls["n"] == 0
    assert snapshot_tree(root) == before_tree


def test_configure_apply_disk_change_between_plan_and_apply_is_plan_changed(
    monkeypatch, tmp_path: Path
):
    root = prepare_project(tmp_path)
    calls = _count_apply_calls(monkeypatch)
    plan_id = configure_project_workflow(root).to_dict()["data"]["plan_id"]
    source = root / "Src" / "main.c"
    source.write_text(source.read_text(encoding="utf-8") + "/* drift */\n", encoding="utf-8")

    result = configure_project_workflow(root, plan_id=plan_id, authorized=True)

    assert result.ok is False
    assert result.code == PLAN_CHANGED
    assert calls["n"] == 0


def test_configure_apply_success_applies_exactly_once(monkeypatch, tmp_path: Path):
    root = prepare_project(tmp_path, overrides={"project": {"name": "renamed", "origin": "manual"}})
    calls = _count_apply_calls(monkeypatch)
    plan_id = configure_project_workflow(root).to_dict()["data"]["plan_id"]

    result = configure_project_workflow(root, plan_id=plan_id, authorized=True)

    assert result.ok is True
    assert result.operation == "project-configuration-apply"
    assert calls["n"] == 1


def test_configure_workflow_missing_manifest_returns_stable_core_error(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    result = configure_project_workflow(root)

    assert result.ok is False
    assert result.code == "PROJECT_NOT_CONFIGURED"
    assert result.operation == "project-configuration-plan"


def test_configure_workflow_maps_unexpected_failures_to_unavailable(
    monkeypatch, tmp_path: Path
):
    root = prepare_project(tmp_path)
    monkeypatch.setattr(
        workflows_mod, "load_project_model", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    )

    result = configure_project_workflow(root)

    assert result.ok is False
    assert result.code == CONFIGURATION_PLAN_UNAVAILABLE
    assert "boom" not in json.dumps(result.to_dict())


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_build_workflow_requires_authorization_before_process_launch(
    tmp_path: Path, monkeypatch
):
    root = prepare_project(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    before_tree = snapshot_tree(root)

    result = build_firmware_workflow(
        root, preset="arm-debug", authorized=False
    )

    assert result.ok is False
    assert result.code == AUTHORIZATION_REQUIRED
    assert result.operation == "build"
    assert not hit_file.exists() or hit_file.read_text(encoding="utf-8") == ""
    assert snapshot_tree(root) == before_tree


def test_build_workflow_validates_preset_clean_and_timeout(tmp_path: Path):
    root = prepare_project(tmp_path)

    bad_preset = build_firmware_workflow(root, preset="arm-fast", authorized=True)
    assert bad_preset.code == WORKFLOW_INPUT_INVALID
    assert dict(bad_preset.details) == {"field": "preset", "rule": "value", "allowed": "arm-debug|arm-release"}

    bad_clean = build_firmware_workflow(root, preset="arm-debug", clean="yes", authorized=True)
    assert bad_clean.code == WORKFLOW_INPUT_INVALID
    assert dict(bad_clean.details) == {"field": "clean", "rule": "type"}

    for timeout in (0, 3601, "300", 3.5, None):
        bad_timeout = build_firmware_workflow(
            root, preset="arm-debug", timeout_seconds=timeout, authorized=True
        )
        assert bad_timeout.code == WORKFLOW_INPUT_INVALID
        assert bad_timeout.details["field"] == "timeoutSeconds"


def test_build_workflow_runs_the_guarded_build_when_authorized(
    tmp_path: Path, monkeypatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)

    result = build_firmware_workflow(
        root, preset="arm-debug", authorized=True
    )

    assert result.ok is True
    assert result.operation == "build"
    identity = result.to_dict()["data"]["identity"]
    assert identity["preset"] == "arm-debug"
    assert identity["elfPath"] == "build/arm-debug/firmware.elf"


# ---------------------------------------------------------------------------
# CLI / MCP envelope identity
# ---------------------------------------------------------------------------


def test_cli_and_workflow_return_identical_envelopes_for_equivalent_requests(
    tmp_path: Path, capsys
):
    """Regression: CLI and direct adapter calls share operation/code/data."""
    root = keil_repo(tmp_path)

    assert cli_main(["keil", "inspect", "--project", str(root), "--json"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["operation"] == "keil-inspect"
    assert cli_payload["ok"] is True

    direct = inspect_keil_workflow(root).to_dict()
    assert cli_payload["operation"] == direct["operation"]
    assert cli_payload["code"] == direct["code"]
    assert cli_payload["data"] == direct["data"]

    assert cli_main(["keil", "convert", "--project", str(root), "--dry-run", "--json"]) == 0
    cli_plan = json.loads(capsys.readouterr().out)
    direct_plan = convert_keil_workflow(root).to_dict()
    assert cli_plan["operation"] == direct_plan["operation"]
    assert cli_plan["data"] == direct_plan["data"]

    # A failing apply is an expected domain failure: exit 2, one JSON document
    # on stdout, and nothing on stderr.
    assert cli_main([
        "keil", "convert", "--project", str(root),
        "--apply", "--plan-id", "0" * 64, "--authorized", "--json",
    ]) == 2
    captured = capsys.readouterr()
    cli_failure = json.loads(captured.out)
    direct_failure = convert_keil_workflow(root, plan_id="0" * 64, authorized=True).to_dict()
    assert cli_failure["operation"] == direct_failure["operation"]
    assert cli_failure["code"] == direct_failure["code"]
    assert cli_failure["data"] == direct_failure["data"]
    assert captured.err == ""


def test_cli_build_and_workflow_share_operation_and_identity(
    tmp_path: Path, monkeypatch, capsys
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)

    assert cli_main(["build", "--project", str(root), "--preset", "arm-debug"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    direct = build_firmware_workflow(root, preset="arm-debug", authorized=True).to_dict()

    assert cli_payload["operation"] == direct["operation"] == "build"
    assert cli_payload["code"] == direct["code"] == "OK"
    assert cli_payload["data"]["identity"]["buildId"] == direct["data"]["identity"]["buildId"]
    assert cli_payload["data"]["identity"]["elfSha256"] == direct["data"]["identity"]["elfSha256"]
