"""Read-only Keil migration preflight (2026-10-23 Keil readiness slice).

Preflight reuses the conversion planner's technical analysis but must not
depend on Git, must never create an applicable plan ID, and must never write.
Every repository here is disposable and below pytest's temporary root.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
import stm32_toolkit.migration.preflight as preflight_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.keil import KeilInspectionError, inspect_keil
from stm32_toolkit.mcp_server import ServerRuntime
from stm32_toolkit.migration import MigrationPlanError, plan_keil_conversion
from stm32_toolkit.migration.preflight import preflight_keil_conversion
from stm32_toolkit.workflows import (
    convert_keil_workflow,
    preflight_keil_workflow,
)

from test_migration_plan import (
    COMMON_C,
    FRAMEWORK_INCLUDE,
    MAIN_C,
    _add_group_scoped_controls,
    build_repo,
    fixture_inspection,
    git_init,
    snapshot_tree,
    standard_repo,
    write_uvprojx,
)


def _blocker_codes(blockers: list[dict[str, object]]) -> set[str]:
    return {str(blocker["code"]) for blocker in blockers}


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for item in value.values():
            keys |= _all_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys |= _all_keys(item)
    return keys


def _assert_no_applicable_plan(data: dict[str, object]) -> None:
    """Preflight exposes no usable identifier and never claims apply readiness."""
    # Delivery PLAN responses use data.planId; preflight carries only a null
    # planReadiness/applyReadiness planId and must not construct a usable one.
    assert "plan_id" not in _all_keys(data)
    json.dumps(data)  # remains JSON-safe for public envelopes
    assert data["planReadiness"]["planId"] is None
    assert data["planReadiness"]["requiresReviewedPlan"] is True
    assert data["applyReadiness"]["ready"] is False
    assert data["applyReadiness"]["status"] == "requires-reviewed-plan"
    assert data["applyReadiness"]["planId"] is None
    assert (
        data["applyReadiness"]["planReadinessStatus"]
        == data["planReadiness"]["status"]
    )
    assert "authorization" in data["applyReadiness"]["reason"].lower()


def test_preflight_completes_without_git_and_never_writes(tmp_path: Path) -> None:
    root = build_repo(
        tmp_path,
        gitignore="build/\n",
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        commit=False,
    )
    inspection = fixture_inspection(root)
    before = snapshot_tree(root)

    data = preflight_keil_conversion(root, inspection)

    assert data["analysis"]["complete"] is True
    assert data["analysis"]["status"] == "complete"
    assert data["analysis"]["requiresGit"] is False
    assert data["analysis"]["mutating"] is False
    assert data["analysis"]["selection"]["projectFile"] == "app.uvprojx"
    assert data["analysis"]["selection"]["targetName"] == "Legacy"
    assert data["analysis"]["selection"]["projectSha256"] == (
        inspection.project_sha256
    )
    input_paths = {entry["path"] for entry in data["analysis"]["inputs"]}
    assert {"app.uvprojx", "Main/main.c", "Common/common.c"} <= input_paths
    for entry in data["analysis"]["inputs"]:
        assert len(entry["sha256"]) == 64
        assert entry["size"] >= 0
    assert data["analysis"]["blockers"] == []
    assert data["git"]["analysisRequiresGit"] is False
    assert data["git"]["repository"]["available"] is False
    assert data["git"]["head"] == {
        "available": False,
        "commit": None,
        "status": "not-evaluated",
        "reason": "HEAD is not inspected because no readable Git repository is available.",
        "error": None,
    }
    assert data["git"]["worktree"]["status"] == "not-evaluated"
    assert data["git"]["worktree"]["dirtyPaths"] == []
    # Git is optional evidence: no blockers means the delivery plan may be
    # requested.  The destination is a required input whose state preflight
    # has not evaluated.
    assert data["planReadiness"]["ready"] is True
    assert data["planReadiness"]["status"] == "ready-for-plan"
    assert data["planReadiness"]["planId"] is None
    prerequisites = {
        item["id"]: item for item in data["planReadiness"]["prerequisites"]
    }
    assert set(prerequisites) == {"technical-blockers"}
    assert prerequisites["technical-blockers"]["satisfied"] is True
    required = {
        item["id"]: item for item in data["planReadiness"]["requiredInputs"]
    }
    assert required["delivery-destination"]["required"] is True
    assert required["delivery-destination"]["state"] == "not-evaluated"
    steps = " ".join(data["planReadiness"]["nextSteps"])
    assert "absolute new output directory" in steps
    assert "data.planId" in steps
    assert "git init" not in steps
    assert "commit" not in steps.lower()
    _assert_no_applicable_plan(data)
    assert snapshot_tree(root) == before


def test_preflight_handles_unborn_head_and_dirty_worktree(tmp_path: Path) -> None:
    root = tmp_path / "unborn"
    root.mkdir()
    write_uvprojx(root)
    (root / "Main").mkdir()
    (root / "Main" / "main.c").write_bytes(MAIN_C.encode("utf-8"))
    (root / "Common").mkdir()
    (root / "Common" / "common.c").write_bytes(COMMON_C.encode("utf-8"))
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    import subprocess

    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)

    unborn = preflight_keil_conversion(root, fixture_inspection(root))
    assert unborn["analysis"]["complete"] is True
    assert unborn["git"]["repository"]["available"] is True
    assert unborn["git"]["repository"]["projectRootIsToplevel"] is True
    assert unborn["git"]["head"]["available"] is False
    assert unborn["git"]["head"]["error"]["rule"] == "head"
    assert unborn["git"]["head"]["status"] == "unavailable"
    # An unborn HEAD is optional evidence, not a plan prerequisite.
    assert unborn["planReadiness"]["ready"] is True
    assert unborn["planReadiness"]["status"] == "ready-for-plan"
    assert unborn["applyReadiness"]["ready"] is False

    git_init(root)
    (root / "Main" / "main.c").write_text(
        MAIN_C + "/* local edit */\n", encoding="utf-8"
    )
    (root / "untracked.txt").write_text("keep me\n", encoding="utf-8")
    dirty = preflight_keil_conversion(root, fixture_inspection(root))

    assert dirty["analysis"]["complete"] is True
    assert dirty["git"]["head"]["available"] is True
    worktree = dirty["git"]["worktree"]
    assert worktree["status"] == "dirty"
    entries = {(entry["category"], entry["path"]) for entry in worktree["dirtyPaths"]}
    assert ("tracked", "Main/main.c") in entries
    assert ("untracked", "untracked.txt") in entries
    assert dirty["analysis"]["blockers"] == []
    # A dirty worktree is reported as optional evidence and never blocks the
    # delivery plan or instructs the owner to commit/stash/clean.
    assert dirty["planReadiness"]["ready"] is True
    assert dirty["planReadiness"]["status"] == "ready-for-plan"
    assert dirty["applyReadiness"]["ready"] is False
    steps = " ".join(dirty["planReadiness"]["nextSteps"]).lower()
    assert "commit" not in steps
    assert "stash" not in steps
    assert "clean" not in steps


def test_preflight_reuses_every_planner_technical_rule(tmp_path: Path) -> None:
    root = tmp_path / "blocked"
    root.mkdir()
    write_uvprojx(
        root,
        cpu='IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4") FPU2',
        groups=(
            ("Main", (("main.c", "1", "Main/main.c"), ("bad.c", "1", "Main/bad.c"))),
            ("Startup", (("startup.s", "2", "Startup/startup.s"),)),
        ),
        scatter="link.sct",
    )
    (root / "Main").mkdir()
    (root / "Main" / "main.c").write_bytes(MAIN_C.encode("utf-8"))
    (root / "Main" / "bad.c").write_bytes(b"\xff\xfe not utf-8\n")
    (root / "Startup").mkdir()
    (root / "Startup" / "startup.s").write_bytes(b"Reset_Handler PROC\n")
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    _add_group_scoped_controls(root, "Main", defines="GROUP_ONLY=1")
    (root / ".stm32-project.json").write_text(
        json.dumps({"schemaVersion": 2, "different": True}) + "\n",
        encoding="utf-8",
    )

    data = preflight_keil_conversion(root, fixture_inspection(root))
    codes = _blocker_codes(data["analysis"]["blockers"])
    assert {
        "ARMCC_SOURCE_ENCODING_UNSUPPORTED",
        "ARMCC_ASSEMBLY_UNSUPPORTED",
        "ARMCC_OPTION_UNSUPPORTED",
        "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED",
        "MIGRATION_MEMORY_INCOMPLETE",
        "MIGRATION_MANIFEST_EXISTS",
    } <= codes
    assert data["analysis"]["complete"] is True
    assert data["planReadiness"]["ready"] is False
    assert data["planReadiness"]["status"] == "blocked"
    assert data["applyReadiness"]["ready"] is False
    assert data["applyReadiness"]["nextSteps"][0].startswith(
        "Resolve these unmet planReadiness prerequisites first:"
    )
    assert "technical-blockers" in data["applyReadiness"]["nextSteps"][0]
    assert data["analysis"]["blockerSummary"]["total"] == len(
        data["analysis"]["blockers"]
    )

    git_init(root)
    plan = plan_keil_conversion(root, fixture_inspection(root))
    # Preflight adds only presentation metadata.  Project it away and require
    # every original blocker field, order, count, and identity to be unchanged.
    projected = [
        {key: value for key, value in blocker.items() if key != "remediation"}
        for blocker in data["analysis"]["blockers"]
    ]
    plan_blockers = list(plan.to_dict()["blockers"])
    assert projected == plan_blockers
    assert all("remediation" not in blocker for blocker in plan_blockers)


def test_technical_blockers_fail_delivery_planning_with_complete_diagnostics(
    tmp_path: Path,
) -> None:
    """Public delivery has no diagnostic-plan fallback: blockers stop planning."""
    root = build_repo(
        tmp_path,
        name="diagnostic",
        uvprojx_kwargs={"scatter": "link.sct"},
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
    )
    before = snapshot_tree(root)
    destination = tmp_path / "delivered" / "project"
    destination.parent.mkdir()

    preflight = preflight_keil_workflow(root)
    assert preflight.ok is True, preflight
    assert preflight.data["analysis"]["blockers"]
    readiness = preflight.data["planReadiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    prerequisites = {item["id"]: item for item in readiness["prerequisites"]}
    assert prerequisites["technical-blockers"]["satisfied"] is False
    assert preflight.data["applyReadiness"]["ready"] is False

    plan = convert_keil_workflow(root, destination=destination)
    assert plan.ok is False
    assert plan.operation == "keil-conversion-plan"
    assert plan.code == "DELIVERY_BLOCKED"
    assert "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED" in plan.details["blockerCodes"]
    assert plan.details["blockerCount"] >= 1
    assert plan.details["blockers"]
    assert not destination.exists()
    assert snapshot_tree(root) == before


def test_preflight_rejects_stale_inputs_and_ambiguous_selection(tmp_path: Path) -> None:
    root = standard_repo(tmp_path)
    inspection = fixture_inspection(root)
    (root / "Main" / "main.c").write_bytes(
        MAIN_C.replace("return 0", "return 1").encode("utf-8")
    )
    with pytest.raises(MigrationPlanError) as error:
        preflight_keil_conversion(root, inspection)
    assert error.value.code == "MIGRATION_INSPECTION_CHANGED"

    other = build_repo(tmp_path, name="multi", commit=False)
    write_uvprojx(other, name="second.uvprojx")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(other)
    assert error.value.code == "KEIL_PROJECT_SELECTION_REQUIRED"
    result = preflight_keil_workflow(other)
    assert result.ok is False
    assert result.code == "KEIL_PROJECT_SELECTION_REQUIRED"


def test_preflight_workflow_cli_and_mcp_share_selection_without_git(
    tmp_path: Path, capsys
) -> None:
    root = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        commit=False,
    )

    workflow = preflight_keil_workflow(
        root, uvprojx="app.uvprojx", target_name="Legacy"
    ).to_dict()
    assert workflow["ok"] is True
    assert workflow["operation"] == "keil-preflight"
    assert workflow["details"] == {
        "analysisOnly": True,
        "grantsApplyAuthorization": False,
        "hardwareDiscovery": "not-performed",
    }
    assert workflow["data"]["analysis"]["selection"]["projectFile"] == "app.uvprojx"
    _assert_no_applicable_plan(workflow["data"])

    assert cli_main([
        "keil", "preflight", "--project", str(root),
        "--uvprojx", "app.uvprojx", "--target-name", "Legacy", "--json",
    ]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["ok"] is True
    assert cli["operation"] == "keil-preflight"
    assert cli["data"]["analysis"]["selection"] == (
        workflow["data"]["analysis"]["selection"]
    )
    assert cli["data"]["applyReadiness"]["ready"] is False
    assert cli["data"]["planReadiness"]["status"] == "ready-for-plan"
    assert "plan_id" not in _all_keys(cli)

    runtime = ServerRuntime.create(root, tmp_path / "plugin-data", "session-a")
    mcp = mcp_mod.tool_keil_preflight(runtime, "app.uvprojx", "Legacy")
    assert mcp["ok"] is True
    assert mcp["operation"] == "keil-preflight"
    assert mcp["data"]["analysis"]["selection"] == (
        workflow["data"]["analysis"]["selection"]
    )

    # Planning needs no Git; it needs an explicit independent destination.
    missing = convert_keil_workflow(
        root, uvprojx="app.uvprojx", target_name="Legacy"
    )
    assert missing.ok is False
    assert missing.code == "DELIVERY_DESTINATION_REQUIRED"

    destination = tmp_path / "delivered" / "app"
    destination.parent.mkdir()
    conversion = convert_keil_workflow(
        root,
        destination=destination,
        uvprojx="app.uvprojx",
        target_name="Legacy",
    )
    assert conversion.ok is True, conversion
    assert conversion.operation == "keil-conversion-plan"
    assert len(conversion.data["planId"]) == 64
    assert not (root / ".stm32-project.json").exists()

    assert cli_main([
        "keil", "convert", "--project", str(root),
        "--uvprojx", "app.uvprojx", "--target-name", "Legacy",
        "--destination", str(destination),
        "--dry-run", "--json",
    ]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["ok"] is True
    assert planned["data"]["planId"] == conversion.data["planId"]


def test_preflight_nested_project_below_git_toplevel_keeps_complete_shape(
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    outer.mkdir()
    project = outer / "Project"
    project.mkdir()
    write_uvprojx(project)
    (project / "Main").mkdir()
    (project / "Main" / "main.c").write_bytes(MAIN_C.encode("utf-8"))
    (project / "Common").mkdir()
    (project / "Common" / "common.c").write_bytes(COMMON_C.encode("utf-8"))
    (project / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    git_init(outer)

    data = preflight_keil_conversion(project, fixture_inspection(project))

    assert data["analysis"]["complete"] is True
    assert data["git"]["repository"]["available"] is True
    assert data["git"]["repository"]["projectRootIsToplevel"] is False
    assert data["git"]["head"]["available"] is False
    assert data["git"]["head"]["status"] == "not-evaluated"
    assert data["git"]["head"]["commit"] is None
    assert data["git"]["worktree"]["status"] == "not-evaluated"
    assert data["git"]["worktree"]["dirtyPaths"] == []
    # A nested project root is optional Git evidence only; it does not block
    # the delivery plan.
    assert data["planReadiness"]["ready"] is True
    assert data["planReadiness"]["status"] == "ready-for-plan"
    assert data["applyReadiness"]["nextSteps"][0].startswith(
        "Choose an absolute new output directory"
    )
    _assert_no_applicable_plan(data)


def test_preflight_missing_git_executable_is_reported_not_raised(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        commit=False,
    )
    inspection = fixture_inspection(root)

    def missing_git(_root: Path) -> Path:
        raise MigrationPlanError(
            "MIGRATION_GIT_UNAVAILABLE",
            "Git evidence is unavailable",
            {"rule": "repository"},
        )

    monkeypatch.setattr(preflight_mod.git_guard, "git_toplevel", missing_git)
    data = preflight_keil_conversion(root, inspection)

    assert data["analysis"]["complete"] is True
    assert data["git"]["repository"] == {
        "available": False,
        "projectRootIsToplevel": None,
        "error": {"code": "MIGRATION_GIT_UNAVAILABLE", "rule": "repository"},
    }
    assert data["git"]["head"]["status"] == "not-evaluated"
    assert data["git"]["worktree"]["status"] == "not-evaluated"
    assert data["planReadiness"]["status"] == "ready-for-plan"
    assert data["planReadiness"]["ready"] is True
    steps = " ".join(data["planReadiness"]["nextSteps"])
    assert "delivery-destination" not in steps  # requiredInputs, not a step id
    assert "data.planId" in steps
    _assert_no_applicable_plan(data)


_GIT_PHASE_ATTRS = {
    "repository": "git_toplevel",
    "head": "git_head",
    "status": "porcelain_status",
}
_SENSITIVE_GIT_ERROR = "denied-sensitive-token C:/private/secret"


@pytest.mark.parametrize("phase", ["repository", "head", "status"])
@pytest.mark.parametrize(
    "error_type", [PermissionError, OSError], ids=["permission-error", "os-error"]
)
def test_preflight_public_workflow_survives_os_level_git_failures(
    tmp_path: Path,
    monkeypatch,
    phase: str,
    error_type: type[OSError],
) -> None:
    root = standard_repo(tmp_path)
    before = snapshot_tree(root)

    def failing_git(*_args: object, **_kwargs: object) -> object:
        raise error_type(_SENSITIVE_GIT_ERROR)

    monkeypatch.setattr(
        preflight_mod.git_guard, _GIT_PHASE_ATTRS[phase], failing_git
    )
    result = preflight_keil_workflow(
        root, uvprojx="app.uvprojx", target_name="Legacy"
    )

    assert result.ok is True
    payload = result.to_dict()
    data = payload["data"]
    assert data["analysis"]["complete"] is True
    assert data["analysis"]["blockers"] == []
    git = data["git"]
    expected_error = {"code": "MIGRATION_GIT_UNAVAILABLE", "rule": phase}
    if phase == "repository":
        assert git["repository"] == {
            "available": False,
            "projectRootIsToplevel": None,
            "error": expected_error,
        }
        assert git["head"]["status"] == "not-evaluated"
        assert git["worktree"]["status"] == "not-evaluated"
    elif phase == "head":
        assert git["repository"]["available"] is True
        assert git["repository"]["projectRootIsToplevel"] is True
        assert git["head"]["available"] is False
        assert git["head"]["status"] == "unavailable"
        assert git["head"]["error"] == expected_error
        assert git["worktree"]["status"] == "clean"
    else:
        assert git["head"]["available"] is True
        assert git["worktree"]["status"] == "unavailable"
        assert git["worktree"]["error"] == expected_error
    # Git evidence failures never change technical readiness.
    assert data["planReadiness"]["status"] == "ready-for-plan"
    assert data["planReadiness"]["ready"] is True
    assert data["applyReadiness"]["ready"] is False
    assert data["applyReadiness"]["status"] == "requires-reviewed-plan"
    _assert_no_applicable_plan(data)
    serialized = json.dumps(payload)
    assert _SENSITIVE_GIT_ERROR not in serialized
    assert "C:/private/secret" not in serialized
    assert snapshot_tree(root) == before


def test_preflight_git_status_os_error_preserves_technical_blockers(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        uvprojx_kwargs={"scatter": "link.sct"},
    )
    before = snapshot_tree(root)

    def failing_status(_root: Path) -> bytes:
        raise PermissionError(_SENSITIVE_GIT_ERROR)

    monkeypatch.setattr(
        preflight_mod.git_guard, "porcelain_status", failing_status
    )
    result = preflight_keil_workflow(
        root, uvprojx="app.uvprojx", target_name="Legacy"
    )

    assert result.ok is True
    payload = result.to_dict()
    data = payload["data"]
    assert data["analysis"]["complete"] is True
    codes = {blocker["code"] for blocker in data["analysis"]["blockers"]}
    assert "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED" in codes
    assert data["git"]["worktree"] == {
        "status": "unavailable",
        "dirtyPaths": [],
        "reason": "Git worktree status is unavailable.",
        "error": {"code": "MIGRATION_GIT_UNAVAILABLE", "rule": "status"},
    }
    assert data["planReadiness"]["status"] == "blocked"
    assert data["applyReadiness"]["ready"] is False
    _assert_no_applicable_plan(data)
    assert _SENSITIVE_GIT_ERROR not in json.dumps(payload)
    assert snapshot_tree(root) == before


def test_preflight_git_os_error_does_not_mask_technical_input_failure(
    tmp_path: Path, monkeypatch
) -> None:
    root = standard_repo(tmp_path)
    inspection = fixture_inspection(root)
    (root / "Main" / "main.c").write_bytes(
        MAIN_C.replace("return 0", "return 1").encode("utf-8")
    )

    def failing_status(_root: Path) -> bytes:
        raise PermissionError(_SENSITIVE_GIT_ERROR)

    monkeypatch.setattr(
        preflight_mod.git_guard, "porcelain_status", failing_status
    )
    with pytest.raises(MigrationPlanError) as error:
        preflight_keil_conversion(root, inspection)
    assert error.value.code == "MIGRATION_INSPECTION_CHANGED"


def test_preflight_git_os_error_does_not_swallow_base_exception(
    tmp_path: Path, monkeypatch
) -> None:
    root = standard_repo(tmp_path)
    inspection = fixture_inspection(root)

    def interrupted(_root: Path) -> Path:
        raise KeyboardInterrupt("operator stop")

    monkeypatch.setattr(preflight_mod.git_guard, "git_toplevel", interrupted)
    with pytest.raises(KeyboardInterrupt):
        preflight_keil_conversion(root, inspection)


def test_preflight_unreadable_head_and_status_do_not_assert_root_causes(
    tmp_path: Path, monkeypatch
) -> None:
    root = standard_repo(tmp_path)
    inspection = fixture_inspection(root)

    def fail_head(_root: Path) -> str:
        raise MigrationPlanError(
            "MIGRATION_GIT_UNAVAILABLE",
            "Git evidence is unavailable",
            {"rule": "head"},
        )

    monkeypatch.setattr(preflight_mod.git_guard, "git_head", fail_head)
    head_data = preflight_keil_conversion(root, inspection)
    # The Git failure stays in optional evidence and generates no readiness
    # instruction to commit or initialize anything.
    assert head_data["git"]["head"]["error"]["rule"] == "head"
    assert head_data["planReadiness"]["ready"] is True
    head_steps = " ".join(head_data["planReadiness"]["nextSteps"]).lower()
    assert "inspect data.git" not in head_steps
    assert "unborn" not in head_steps
    assert "commit" not in head_steps
    assert "git init" not in head_steps

    def fail_status(_root: Path) -> bytes:
        raise MigrationPlanError(
            "MIGRATION_GIT_UNAVAILABLE",
            "Git evidence is unavailable",
            {"rule": "status"},
        )

    monkeypatch.setattr(preflight_mod.git_guard, "porcelain_status", fail_status)
    status_data = preflight_keil_conversion(root, inspection)
    assert status_data["git"]["worktree"]["status"] == "unavailable"
    assert status_data["planReadiness"]["ready"] is True
    status_steps = " ".join(status_data["planReadiness"]["nextSteps"]).lower()
    assert "git status" not in status_steps
    assert "dirty or clean" not in status_steps
    assert "commit" not in status_steps


def test_preflight_clean_eligible_input_is_ready_for_plan_not_apply(
    tmp_path: Path,
) -> None:
    root = standard_repo(tmp_path)
    data = preflight_keil_conversion(root, fixture_inspection(root))

    assert data["analysis"]["blockers"] == []
    assert data["git"]["repository"]["available"] is True
    assert data["git"]["repository"]["projectRootIsToplevel"] is True
    assert data["git"]["head"]["available"] is True
    assert data["git"]["worktree"]["status"] == "clean"
    assert data["planReadiness"]["ready"] is True
    assert data["planReadiness"]["status"] == "ready-for-plan"
    assert data["applyReadiness"]["ready"] is False
    assert data["applyReadiness"]["status"] == "requires-reviewed-plan"
    assert data["applyReadiness"]["planId"] is None
    next_steps = " ".join(data["planReadiness"]["nextSteps"])
    assert "data.planId" in next_steps
    assert "destination <absolute-new-output>" in next_steps
    assert "authorized=true" in next_steps
    assert data["applyReadiness"]["nextSteps"][0].startswith(
        "Choose an absolute new output directory"
    )
    assert "planReadiness.status becomes ready-for-plan" not in " ".join(
        data["applyReadiness"]["nextSteps"]
    )
    _assert_no_applicable_plan(data)


def test_preflight_output_size_bound_matches_the_plan_bound(
    tmp_path: Path, monkeypatch
) -> None:
    root = standard_repo(tmp_path)
    inspection = fixture_inspection(root)
    monkeypatch.setattr(preflight_mod, "_PREFLIGHT_OUTPUT_LIMIT_BYTES", 64)

    with pytest.raises(MigrationPlanError) as error:
        preflight_keil_conversion(root, inspection)

    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {
        "scope": "preflight",
        "limitBytes": 64,
    }


def test_preflight_rejects_unsafe_selection_and_does_not_change_apply_guards(
    tmp_path: Path,
) -> None:
    root = standard_repo(tmp_path)
    destination = tmp_path / "delivered" / "project"
    destination.parent.mkdir()

    unsafe = preflight_keil_workflow(
        root, uvprojx="../outside.uvprojx", target_name="Legacy"
    )
    assert unsafe.ok is False
    assert unsafe.code == "WORKFLOW_INPUT_INVALID"
    assert unsafe.details == {"field": "uvprojx", "rule": "portablePath"}

    stale = convert_keil_workflow(
        root, destination=destination, plan_id="0" * 64, authorized=True
    )
    assert stale.ok is False
    assert stale.code == "PLAN_CHANGED"
    no_auth = convert_keil_workflow(
        root, destination=destination, plan_id="0" * 64, authorized=False
    )
    assert no_auth.ok is False
    assert no_auth.code == "AUTHORIZATION_REQUIRED"
    assert not destination.exists()
