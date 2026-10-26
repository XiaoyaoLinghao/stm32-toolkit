"""M2 public independent Keil-to-GCC migration workflow.

Every fixture is disposable and below pytest's temporary root.  The source
project is either outside Git or inside a Git repository whose HEAD/worktree
state is deliberately unrelated to delivery, proving that Git is optional
traceability rather than an eligibility gate.  The same public contract is
exercised directly, through a fresh CLI subprocess and through the registered
MCP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import stm32_toolkit
import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import preflight_keil_conversion
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.workflows import (
    convert_keil_workflow,
    preflight_keil_workflow,
)

from test_memory_layout_migration import ALL_MAIN
from test_migration_plan import (
    COMMON_C,
    FRAMEWORK_INCLUDE,
    MAIN_C,
    build_repo,
    write_uvprojx,
)
from test_migration_apply import git_init, snapshot_tree

_REPO_SRC = Path(stm32_toolkit.__file__).resolve().parents[1]
_SHA_KEYS = ("planId", "contentId", "sourceSnapshotSha256", "outputSnapshotSha256")


def _source(tmp_path: Path, name: str = "source", *, commit: bool = False) -> Path:
    return build_repo(
        tmp_path,
        name=name,
        files={
            "Main/main.c": MAIN_C,
            "Common/common.c": COMMON_C,
            "LICENSE": "Synthetic fixture license.\n",
            "README.md": "Synthetic independent delivery fixture.\n",
        },
        commit=commit,
    )


def _destination(tmp_path: Path, name: str = "gcc-project") -> Path:
    parent = tmp_path / "outputs"
    parent.mkdir(parents=True, exist_ok=True)
    return parent / name


def _fresh_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PYTHONPATH": str(_REPO_SRC)
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-B", "-m", "stm32_toolkit.cli", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=180,
    )


def _registered_call(
    project: Path, data_root: Path, tool: str, arguments: dict[str, object]
) -> dict[str, object]:
    server = mcp_mod.create_server(project, data_root, "session-independent")
    _content, structured = asyncio.run(server.call_tool(tool, arguments))
    assert structured is not None
    return structured


# ---------------------------------------------------------------------------
# destination requirement and new/occupied destination behavior
# ---------------------------------------------------------------------------


def test_missing_destination_is_structured_with_example_and_rationale(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    before = snapshot_tree(source)

    direct = convert_keil_workflow(source)
    assert direct.ok is False
    assert direct.operation == "keil-conversion-plan"
    assert direct.code == "DELIVERY_DESTINATION_REQUIRED"
    assert direct.details["field"] == "destination"
    assert direct.details["rule"] == "required"
    assert "C:/work/" in direct.details["example"]
    assert "read-only" in direct.details["rationale"]
    assert "independent" in direct.details["rationale"]
    assert direct.details["rationale"].count("GCC") >= 1

    assert cli_main([
        "keil", "convert", "--project", str(source), "--dry-run", "--json",
    ]) == 2
    cli = json.loads(capsys.readouterr().out)
    assert cli["code"] == direct.code
    assert cli["details"] == direct.details
    assert snapshot_tree(source) == before

    mcp = _registered_call(
        source,
        tmp_path / "plugin-data",
        "stm32_keil_convert",
        {"authorized": False},
    )
    assert mcp["ok"] is False
    assert mcp["code"] == direct.code
    assert mcp["details"]["field"] == "destination"
    assert snapshot_tree(source) == before


def test_occupied_destination_is_refused_and_untouched(tmp_path: Path) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    destination.mkdir()
    (destination / "keep.txt").write_text("owner content\n", encoding="utf-8")

    result = convert_keil_workflow(source, destination=destination)
    assert result.ok is False
    assert result.code == "DELIVERY_DESTINATION_EXISTS"
    assert (destination / "keep.txt").read_text(encoding="utf-8") == (
        "owner content\n"
    )
    assert sorted(entry.name for entry in destination.iterdir()) == ["keep.txt"]


def test_verified_empty_destination_is_accepted(tmp_path: Path) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    destination.mkdir()

    planned = convert_keil_workflow(source, destination=destination)
    assert planned.ok is True
    assert planned.data["destinationState"] == "empty"
    assert not any(destination.iterdir())

    applied = convert_keil_workflow(
        source,
        destination=destination,
        plan_id=planned.data["planId"],
        authorized=True,
    )
    assert applied.ok is True, applied.to_dict()
    assert (destination / ".stm32-project.json").is_file()


# ---------------------------------------------------------------------------
# direct no-Git plan/apply and output-only evidence
# ---------------------------------------------------------------------------


def test_no_git_plan_apply_preserves_source_and_publishes_complete_output(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    assert not (source / ".git").exists()
    source_before = snapshot_tree(source)

    planned = convert_keil_workflow(source, destination=destination)
    assert planned.ok is True, planned.to_dict()
    data = planned.data
    assert planned.operation == "keil-conversion-plan"
    for key in _SHA_KEYS:
        assert isinstance(data[key], str) and len(data[key]) == 64
    assert data["sourceRoot"] == str(source.resolve())
    assert data["destination"] == str(destination)
    assert data["configured"] is False
    assert data["built"] is False
    assert data["flashed"] is False
    assert "plan_id" not in data
    assert "blockers" not in data
    outputs = {entry["path"]: entry for entry in data["outputs"]}
    assert outputs[".stm32-project.json"]["kind"] == "generated"
    assert outputs["CMakeLists.txt"]["kind"] == "generated"
    assert outputs["Common/common.c"]["kind"] == "replaced"
    assert outputs["Common/common.c"]["beforeSha256"]
    assert outputs["Common/common.c"]["unifiedDiff"]
    assert outputs["LICENSE"]["kind"] == "copied"
    assert data["sourcePatches"]
    assert all("content" not in entry for entry in data["outputs"])
    # Plan-only: no staging or destination directory appears.
    assert not destination.exists()
    assert not list(destination.parent.glob(".*.stm32tk-staging-*"))
    assert snapshot_tree(source) == source_before

    applied = convert_keil_workflow(
        source,
        destination=destination,
        plan_id=data["planId"],
        authorized=True,
    )
    assert applied.ok is True, applied.to_dict()
    assert applied.operation == "keil-conversion-apply"
    result = applied.data
    assert result["outputRoot"] == str(destination)
    assert result["planId"] == data["planId"]
    assert result["contentId"] == data["contentId"]
    assert result["sourceSnapshotSha256"] == data["sourceSnapshotSha256"]
    assert result["outputSnapshotSha256"] == data["outputSnapshotSha256"]
    assert result["configured"] is True
    assert result["built"] is False
    assert result["flashed"] is False

    # The complete planned output exists, and the source is byte-identical.
    for output in data["outputs"]:
        path = destination.joinpath(*output["path"].split("/"))
        assert path.is_file(), output["path"]
    assert snapshot_tree(source) == source_before
    assert not (destination / ".git").exists()
    assert not list(destination.parent.glob(".*.stm32tk-staging-*"))

    # The delivered project is immediately usable by the normal configure
    # route; this is configuration evidence, not a build or flash.  The
    # delivered model has no debug pair, so the derived editor guidance asks
    # for explicit user settings instead of inventing a backend or paths.
    configuration = plan_project_configuration(load_project_model(destination))
    assert configuration.blockers == ()
    configuration_data = configuration.to_dict()
    guidance = configuration_data["vscodeGuidance"]
    assert guidance["bindingMode"] == "user-settings"
    assert guidance["userSettingsChecked"] is False
    assert guidance["requiredUserSettings"]
    assert configuration.managed_manifest_bytes == (
        destination / ".stm32-toolkit" / "generated-files.json"
    ).read_bytes()
    report = json.loads(
        (
            destination / "artifacts" / "migration" / "conversion-report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["schemaVersion"] == 2
    assert report["contentId"] == data["contentId"]
    assert report["sourceSnapshotSha256"] == data["sourceSnapshotSha256"]
    assert "planId" not in report
    assert "gitHead" not in report


def test_output_build_inputs_do_not_reference_the_source_directory(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    planned = convert_keil_workflow(source, destination=destination)
    assert planned.ok is True
    applied = convert_keil_workflow(
        source,
        destination=destination,
        plan_id=planned.data["planId"],
        authorized=True,
    )
    assert applied.ok is True

    source_text = os.path.normcase(str(source))
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if b"\x00" in payload[:2048]:
            continue
        text = os.path.normcase(payload.decode("utf-8", "replace"))
        assert source_text not in text, path


# ---------------------------------------------------------------------------
# authorization and option/plan drift
# ---------------------------------------------------------------------------


def test_authorization_and_plan_drift_fail_before_any_write(tmp_path: Path) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    reviewed = convert_keil_workflow(source, destination=destination)
    assert reviewed.ok is True
    plan_id = reviewed.data["planId"]
    source_before = snapshot_tree(source)

    for authorized in ("true", 1, None, [], {}):
        denied = convert_keil_workflow(
            source,
            destination=destination,
            plan_id=plan_id,
            authorized=authorized,
        )
        assert denied.ok is False
        assert denied.code == "AUTHORIZATION_REQUIRED"
        assert denied.operation == "keil-conversion-apply"

    missing_id = convert_keil_workflow(
        source, destination=destination, authorized=True
    )
    assert missing_id.ok is False
    assert missing_id.code == "AUTHORIZATION_REQUIRED"
    assert missing_id.details["field"] == "planId"

    stale = convert_keil_workflow(
        source, destination=destination, plan_id="0" * 64, authorized=True
    )
    assert stale.ok is False
    assert stale.code == "PLAN_CHANGED"
    assert stale.details["field"] == "planId"

    moved = convert_keil_workflow(
        source,
        destination=_destination(tmp_path, "other"),
        plan_id=plan_id,
        authorized=True,
    )
    assert moved.ok is False
    assert moved.code == "PLAN_CHANGED"

    changed_option = convert_keil_workflow(
        source,
        destination=destination,
        plan_id=plan_id,
        authorized=True,
        memory_layout=ALL_MAIN,
    )
    assert changed_option.ok is False
    assert changed_option.code == "PLAN_CHANGED"

    assert not destination.exists()
    assert not _destination(tmp_path, "other").exists()
    assert snapshot_tree(source) == source_before


# ---------------------------------------------------------------------------
# Git is optional traceability, never a plan prerequisite
# ---------------------------------------------------------------------------


def _prepare_without_git(root: Path) -> None:
    write_uvprojx(root)
    (root / "Main").mkdir()
    (root / "Main" / "main.c").write_bytes(MAIN_C.encode("utf-8"))
    (root / "Common").mkdir()
    (root / "Common" / "common.c").write_bytes(COMMON_C.encode("utf-8"))
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)


def test_readiness_is_independent_of_missing_unborn_dirty_and_nested_git(
    tmp_path: Path,
) -> None:
    cases: dict[str, Path] = {}

    missing = _source(tmp_path, "no-git")
    assert not (missing / ".git").exists()
    cases["missing"] = missing

    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _prepare_without_git(unborn)
    subprocess.run(
        ["git", "init", "-q", "-b", "master"], cwd=unborn, check=True
    )
    subprocess.run(["git", "add", "-A"], cwd=unborn, check=True)
    cases["unborn"] = unborn

    # A genuine committed Git repository with a tracked edit and an untracked
    # file: the HEAD exists, and the dirty worktree is optional evidence.
    dirty = _source(tmp_path, "dirty", commit=True)
    assert (dirty / ".git").exists()
    (dirty / "Main" / "main.c").write_text(
        MAIN_C + "/* local, uncommitted edit */\n", encoding="utf-8"
    )
    (dirty / "untracked.txt").write_text("keep me\n", encoding="utf-8")
    cases["dirty"] = dirty

    outer = tmp_path / "outer"
    nested = outer / "Project"
    nested.mkdir(parents=True)
    _prepare_without_git(nested)
    git_init(outer)
    cases["nested"] = nested

    for label, root in cases.items():
        preflight = preflight_keil_workflow(root)
        assert preflight.ok is True, label
        # OperationResult freezes JSON lists into tuples; compare the native
        # immutable empty result rather than a JSON list.
        assert preflight.data["analysis"]["blockers"] == (), label
        readiness = preflight.data["planReadiness"]
        assert readiness["ready"] is True, label
        assert readiness["status"] == "ready-for-plan", label
        assert {item["id"] for item in readiness["prerequisites"]} == {
            "technical-blockers"
        }, label
        assert readiness["requiredInputs"][0]["id"] == "delivery-destination"
        assert readiness["requiredInputs"][0]["state"] == "not-evaluated"
        assert preflight.data["applyReadiness"]["ready"] is False, label
        # Missing debug configuration is post-migration guidance, never a
        # technical blocker or an apply prerequisite.
        debug_guidance = preflight.data["debugConfiguration"]
        assert debug_guidance["status"] == "needs-user-input", label
        assert debug_guidance["blocking"] is False, label
        assert debug_guidance["hardwareVerified"] is False, label
        steps = " ".join(readiness["nextSteps"]).lower()
        assert "git init" not in steps, label
        assert "commit" not in steps, label
        assert "stash" not in steps, label
        # Git evidence is still optional, truthful information.
        assert preflight.data["git"]["analysisRequiresGit"] is False, label
        assert "available" in preflight.data["git"]["repository"], label

        destination = _destination(tmp_path, f"{label}-gcc")
        planned = convert_keil_workflow(root, destination=destination)
        assert planned.ok is True, (label, planned.to_dict())
        assert planned.data["planId"] == convert_keil_workflow(
            root, destination=destination
        ).data["planId"], label
        assert not destination.exists(), label


def test_complete_blocker_diagnostics_reach_direct_cli_and_mcp(
    tmp_path: Path, capsys
) -> None:
    source = build_repo(
        tmp_path,
        name="blocked-source",
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        uvprojx_kwargs={"scatter": "link.sct"},
        commit=False,
    )
    destination = _destination(tmp_path)

    direct = convert_keil_workflow(source, destination=destination)
    assert direct.ok is False
    assert direct.code == "DELIVERY_BLOCKED"
    assert "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED" in direct.to_dict()[
        "details"
    ]["blockerCodes"]
    assert direct.details["blockerCount"] >= 1
    assert direct.details["blockers"]
    assert not destination.exists()

    # The native result freezes lists into tuples; to_dict() is the JSON form
    # the CLI subprocess and registered MCP server actually return.
    direct_json = direct.to_dict()

    assert cli_main([
        "keil", "convert", "--project", str(source),
        "--destination", str(destination), "--dry-run", "--json",
    ]) == 2
    cli = json.loads(capsys.readouterr().out)
    assert cli["code"] == "DELIVERY_BLOCKED"
    assert cli["details"]["blockerCodes"] == direct_json["details"]["blockerCodes"]
    assert cli["details"]["blockers"] == direct_json["details"]["blockers"]

    mcp = _registered_call(
        source,
        tmp_path / "plugin-data",
        "stm32_keil_convert",
        {"destination": str(destination), "authorized": False},
    )
    assert mcp["ok"] is False
    assert mcp["code"] == "DELIVERY_BLOCKED"
    assert mcp["details"]["blockerCodes"] == direct_json["details"]["blockerCodes"]
    assert mcp["details"]["blockers"] == direct_json["details"]["blockers"]

    # Preflight keeps the complete technical/remediation diagnostics.
    analysis = preflight_keil_conversion(source, inspect_keil(source))
    blocker = next(
        item
        for item in analysis["analysis"]["blockers"]
        if item["code"] == "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED"
    )
    assert blocker["remediation"]["category"] == "unsupported"
    assert analysis["applyReadiness"]["ready"] is False
    assert not destination.exists()


# ---------------------------------------------------------------------------
# fresh CLI subprocess
# ---------------------------------------------------------------------------


def test_fresh_cli_subprocess_plans_and_applies_independently(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    source_before = snapshot_tree(source)

    planned = _fresh_cli(
        "keil",
        "convert",
        "--project",
        str(source),
        "--destination",
        str(destination),
        "--dry-run",
        "--json",
    )
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    assert plan["ok"] is True
    assert plan["operation"] == "keil-conversion-plan"
    plan_id = plan["data"]["planId"]
    assert len(plan_id) == 64
    assert plan["data"]["built"] is False
    assert not destination.exists()

    applied = _fresh_cli(
        "keil",
        "convert",
        "--project",
        str(source),
        "--destination",
        str(destination),
        "--apply",
        "--plan-id",
        plan_id,
        "--authorized",
        "--json",
    )
    assert applied.returncode == 0, applied.stderr
    result = json.loads(applied.stdout)
    assert result["ok"] is True
    assert result["operation"] == "keil-conversion-apply"
    assert result["data"]["outputRoot"] == str(destination)
    assert result["data"]["configured"] is True
    assert result["data"]["built"] is False
    assert result["data"]["flashed"] is False
    assert snapshot_tree(source) == source_before
    assert (destination / ".stm32-project.json").is_file()

    missing = _fresh_cli(
        "keil",
        "convert",
        "--project",
        str(source),
        "--dry-run",
        "--json",
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["code"] == "DELIVERY_DESTINATION_REQUIRED"


# ---------------------------------------------------------------------------
# registered MCP parameter/call path
# ---------------------------------------------------------------------------


def test_registered_mcp_plan_apply_and_option_drift(tmp_path: Path) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    assert not (source / ".git").exists()
    source_before = snapshot_tree(source)
    data_root = tmp_path / "plugin-data"

    plan = _registered_call(
        source,
        data_root,
        "stm32_keil_convert",
        {"destination": str(destination), "authorized": False},
    )
    assert plan["ok"] is True
    assert plan["data"]["planId"] == convert_keil_workflow(
        source, destination=destination
    ).data["planId"]
    assert plan["data"]["outputs"]
    assert plan["data"]["sourcePatches"]
    assert not destination.exists()

    changed = _registered_call(
        source,
        data_root,
        "stm32_keil_convert",
        {
            "destination": str(destination),
            "planId": plan["data"]["planId"],
            "authorized": True,
            "memoryLayout": ALL_MAIN.to_dict(),
        },
    )
    assert changed["ok"] is False
    assert changed["code"] == "PLAN_CHANGED"
    assert not destination.exists()

    applied = _registered_call(
        source,
        data_root,
        "stm32_keil_convert",
        {
            "destination": str(destination),
            "planId": plan["data"]["planId"],
            "authorized": True,
        },
    )
    assert applied["ok"] is True
    assert applied["operation"] == "keil-conversion-apply"
    assert applied["data"]["outputRoot"] == str(destination)
    assert applied["data"]["built"] is False
    assert applied["data"]["flashed"] is False
    assert snapshot_tree(source) == source_before
    assert (destination / ".stm32-project.json").is_file()
    assert not (source / ".stm32-project.json").exists()
