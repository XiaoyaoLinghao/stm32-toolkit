"""Tests for guarded atomic conversion apply and rollback (STM32TK-0303).

Every repository used here is a disposable Git repository created below a
pytest temporary directory; tests invoke only a local Git executable.  No
network, compiler, Keil, or hardware is required.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.keil import KeilInspection, inspect_keil

import stm32_toolkit.migration.apply as apply_mod
import stm32_toolkit.migration.model as model_mod
import stm32_toolkit.migration.planner as planner_mod
from stm32_toolkit.migration import (
    FilePatch,
    FixedSectionRequirement,
    GitBaseline,
    MigrationInput,
    apply_keil_conversion,
    plan_keil_conversion,
)

CORE_CPU = 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")'
FRAMEWORK_INCLUDE = "Libraries/STM32F4xx_StdPeriph_Driver"

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

MAIN_C = (
    "/* main.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void early_init(void) { __nop(); }\n"
    "\n"
    "int main(void) { return 0; }\n"
)

COMMON_C_AFTER = (
    "/* common.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "void systick_isr(void)\n"
    "{\n"
    "    __NOP();\n"
    "    __WFI();\n"
    "}\n"
    "\n"
    '__asm("nop");\n'
    "\n"
    '__attribute__((section(".common.data"))) int shared_value;\n'
    '__attribute__((section(".stm32tk.abs.20000000"), used)) int pinned_value;\n'
    "\n"
    "int common_work(void) { return 0; }\n"
)

MAIN_C_AFTER = (
    "/* main.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "void early_init(void) { __NOP(); }\n"
    "\n"
    "int main(void) { return 0; }\n"
)

FIXED_GIT_TIME = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# disposable-repository helpers (duplicated from test_migration_plan so each
# test module is self-contained; no new tracked path is introduced)
# ---------------------------------------------------------------------------


def write_uvprojx(
    root: Path,
    *,
    name: str = "app.uvprojx",
    target: str = "Legacy",
    device: str = "STM32F429ZGTx",
    cpu: str = CORE_CPU,
    output: str = "app",
    groups: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
        ("Main", (("main.c", "1", "Main/main.c"),)),
        ("Common", (("common.c", "1", "Common/common.c"),)),
    ),
    defines: str = "USE_STDPERIPH_DRIVER,STM32F429xx",
    includes: str = f"Main;Common;{FRAMEWORK_INCLUDE}",
    compiler_misc: str = "",
    linker_misc: str = "",
    scatter: str = "",
    uac6: str = "0",
    pack: str = "Keil.STM32F4xx_DFP.2.16.1",
) -> Path:
    group_xml = []
    for group_name, files in groups:
        file_xml = []
        for file_name, file_type, file_path in files:
            file_xml.append(
                "            <File>\n"
                f"              <FileName>{file_name}</FileName>\n"
                f"              <FileType>{file_type}</FileType>\n"
                f"              <FilePath>.\\{file_path}</FilePath>\n"
                "            </File>\n"
            )
        group_xml.append(
            "          <Group>\n"
            f"            <GroupName>{group_name}</GroupName>\n"
            "            <Files>\n"
            + "".join(file_xml)
            + "            </Files>\n"
            "          </Group>\n"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<Project xmlns="http://www.keil.com/project">\n'
        "  <Targets>\n"
        "    <Target>\n"
        f"      <TargetName>{target}</TargetName>\n"
        "      <ToolsetNumber>0x4</ToolsetNumber>\n"
        "      <ToolsetName>ARM-ADS</ToolsetName>\n"
        "      <pCCUsed>5060750::V5.06 update 7 (build 750)::ARMCC</pCCUsed>\n"
        f"      <uAC6>{uac6}</uAC6>\n"
        "      <TargetOption>\n"
        "        <TargetCommonOption>\n"
        f"          <Device>{device}</Device>\n"
        "          <Vendor>STMicroelectronics</Vendor>\n"
        f"          <PackID>{pack}</PackID>\n"
        f"          <Cpu>{cpu}</Cpu>\n"
        "          <uFloatingPoint>1</uFloatingPoint>\n"
        "        </TargetCommonOption>\n"
        "        <OutputDirectory>.\\Objects\\</OutputDirectory>\n"
        f"        <OutputName>{output}</OutputName>\n"
        "        <ListingPath>.\\Listing\\</ListingPath>\n"
        "        <TargetArmAds>\n"
        "          <Cads>\n"
        "            <VariousControls>\n"
        f"              <MiscControls>{compiler_misc}</MiscControls>\n"
        f"              <Define>{defines}</Define>\n"
        "              <Undefine></Undefine>\n"
        f"              <IncludePath>{includes}</IncludePath>\n"
        "            </VariousControls>\n"
        "          </Cads>\n"
        "          <LDads>\n"
        "            <VariousControls>\n"
        f"              <MiscControls>{linker_misc}</MiscControls>\n"
        "              <ImageEntryPoint></ImageEntryPoint>\n"
        f"              <ScatterFile>{scatter}</ScatterFile>\n"
        "            </VariousControls>\n"
        "          </LDads>\n"
        "        </TargetArmAds>\n"
        "      </TargetOption>\n"
        "      <Groups>\n"
        + "".join(group_xml)
        + "      </Groups>\n"
        "    </Target>\n"
        "  </Targets>\n"
        "</Project>\n"
    )
    project = root / name
    project.write_bytes(xml.encode("utf-8"))
    return project


def git_env():
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = FIXED_GIT_TIME
    env["GIT_COMMITTER_DATE"] = FIXED_GIT_TIME
    env["GIT_AUTHOR_NAME"] = "Migration Test"
    env["GIT_AUTHOR_EMAIL"] = "migration@test.local"
    env["GIT_COMMITTER_NAME"] = "Migration Test"
    env["GIT_COMMITTER_EMAIL"] = "migration@test.local"
    return env


def git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, env=git_env())


def git_status(root: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def build_repo(
    tmp_path: Path,
    name: str = "proj",
    *,
    files: dict[str, str | None] | None = None,
    uvprojx_kwargs: dict | None = None,
    gitignore: str | None = None,
) -> Path:
    root = tmp_path / name
    counter = 1
    while root.exists():
        root = tmp_path / f"{name}_{counter}"
        counter += 1
    root.mkdir()
    write_uvprojx(root, **(uvprojx_kwargs or {}))
    for rel, content in (files or {}).items():
        if content is None:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    if gitignore is not None:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    git_init(root)
    return root


def standard_repo(tmp_path: Path) -> Path:
    return build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
    )


def fixture_inspection(root: Path) -> KeilInspection:
    return inspect_keil(root)


def snapshot_tree(root: Path) -> dict[str, tuple]:
    entries: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        rel = str(path.relative_to(root))
        lst = os.lstat(path)
        if stat.S_ISDIR(lst.st_mode):
            entries[rel] = ("dir", lst.st_mode)
        else:
            data = path.read_bytes()
            entries[rel] = (
                "file",
                hashlib.sha256(data).hexdigest(),
                len(data),
                lst.st_mode,
                lst.st_mtime_ns,
            )
    return entries


def forge(plan, **changes) -> object:
    """Rebuild a plan with the given fields replaced and a consistent plan_id.

    This simulates a caller forging a plan whose digest metadata matches its
    own payload; every remaining defense must still reject it.
    """
    changed = replace(plan, **changes)
    return replace(changed, plan_id=model_mod.plan_id_for(changed))


# ---------------------------------------------------------------------------
# success path
# ---------------------------------------------------------------------------


def test_apply_success_exact_bytes_modes_artifacts_and_status(tmp_path):
    repo = standard_repo(tmp_path)
    # A non-default mode on a tracked file is not recorded by Git (only the
    # executable bit is), so the working-tree mode must survive the apply.
    os.chmod(repo / "Common" / "common.c", 0o640)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    head_before = git_head(repo)
    uvprojx_before = (repo / "app.uvprojx").read_bytes()
    result = apply_keil_conversion(plan)
    assert result.ok is True
    assert result.operation == "keil-conversion-apply"
    assert result.code == "OK"
    data = result.to_dict()["data"]
    assert data["planId"] == plan.plan_id
    assert data["gitHead"] == head_before
    assert data["changedPaths"] == ["Common/common.c", "Main/main.c"]
    assert data["createdPaths"] == [
        ".stm32-project.json",
        "artifacts/migration/conversion.patch",
        "artifacts/migration/conversion-report.json",
    ]
    assert data["patchPath"] == "artifacts/migration/conversion.patch"
    assert data["reportPath"] == "artifacts/migration/conversion-report.json"
    assert data["fixedSections"] == [
        {
            "section": ".stm32tk.abs.20000000",
            "address": 0x20000000,
            "sourcePath": "Common/common.c",
            "line": 13,
            "symbol": "pinned_value",
        }
    ]

    assert (repo / "Common" / "common.c").read_bytes() == COMMON_C_AFTER.encode("utf-8")
    assert (repo / "Main" / "main.c").read_bytes() == MAIN_C_AFTER.encode("utf-8")
    assert stat.S_IMODE((repo / "Common" / "common.c").stat().st_mode) == 0o640

    manifest = json.loads((repo / ".stm32-project.json").read_bytes())
    proposal = next(p for p in plan.patches if p.path == ".stm32-project.json")
    assert json.loads(proposal.after_bytes) == manifest

    patch_bytes = (repo / "artifacts" / "migration" / "conversion.patch").read_bytes()
    assert patch_bytes == b"".join(p.unified_diff.encode("utf-8") for p in plan.patches)
    assert data["patchSha256"] == hashlib.sha256(patch_bytes).hexdigest()

    report = json.loads(
        (repo / "artifacts" / "migration" / "conversion-report.json").read_bytes()
    )
    assert report["schemaVersion"] == 1
    assert report["planId"] == plan.plan_id
    assert report["gitHead"] == head_before
    assert report["inspectionSha256"] == plan.inspection_sha256
    assert {entry["path"] for entry in report["inputs"]} == {
        entry.path for entry in plan.inputs
    }
    assert {entry["path"] for entry in report["patches"]} == {
        entry.path for entry in plan.patches
    }
    assert report["fixedSections"] == data["fixedSections"]
    assert report["ignoredCompatible"] == [
        {"ruleId": "ARMCC_COMPATIBLE_ASM", "path": "Common/common.c", "line": 10, "column": 1, "evidence": '__asm("nop");'},
        {"ruleId": "ARMCC_GCC_SECTION_ATTRIBUTE", "path": "Common/common.c", "line": 12, "column": 1, "evidence": '__attribute__((section(".common.data"))) int shared_value;'},
    ]
    assert report["blockers"] == []
    assert report["artifacts"]["patchSha256"] == data["patchSha256"]
    assert report["artifacts"]["patch"] == "artifacts/migration/conversion.patch"
    assert "reportSha256" not in report
    assert data["reportSha256"] == hashlib.sha256(
        (repo / "artifacts" / "migration" / "conversion-report.json").read_bytes()
    ).hexdigest()
    report_text = json.dumps(report)
    assert str(repo) not in report_text

    # Staging is fully removed; the empty .stm32-toolkit state dir remains per
    # the success protocol (never removed), but empty dirs are invisible to Git.
    assert not (repo / ".stm32-toolkit" / "migration-staging").exists()
    assert (repo / ".stm32-toolkit").is_dir()

    # Expected dirty status: only the planned paths plus artifacts.
    status_lines = set(git_status(repo).splitlines())
    assert status_lines == {
        " M Common/common.c",
        " M Main/main.c",
        "?? .stm32-project.json",
        "?? artifacts/",
    }
    assert git_head(repo) == head_before
    assert (repo / "app.uvprojx").read_bytes() == uvprojx_before
    assert subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repo, check=False
    ).returncode == 0
    result.to_dict()
    json.dumps(result.to_dict())


def test_apply_deterministic_patch_and_report(tmp_path):
    repo_a = standard_repo(tmp_path)
    repo_b = standard_repo(tmp_path)
    assert git_head(repo_a) == git_head(repo_b)
    plan_a = plan_keil_conversion(repo_a, fixture_inspection(repo_a))
    plan_b = plan_keil_conversion(repo_b, fixture_inspection(repo_b))
    assert plan_a.plan_id == plan_b.plan_id
    result_a = apply_keil_conversion(plan_a)
    result_b = apply_keil_conversion(plan_b)
    assert (repo_a / "artifacts" / "migration" / "conversion.patch").read_bytes() == (
        repo_b / "artifacts" / "migration" / "conversion.patch"
    ).read_bytes()
    assert (repo_a / "artifacts" / "migration" / "conversion-report.json").read_bytes() == (
        repo_b / "artifacts" / "migration" / "conversion-report.json"
    ).read_bytes()
    assert result_a.to_dict()["data"]["patchSha256"] == result_b.to_dict()["data"]["patchSha256"]


def test_apply_manifest_only_project(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    result = apply_keil_conversion(plan)
    assert result.ok is True
    assert result.to_dict()["data"]["changedPaths"] == []
    assert result.to_dict()["data"]["createdPaths"] == [
        ".stm32-project.json",
        "artifacts/migration/conversion.patch",
        "artifacts/migration/conversion-report.json",
    ]
    assert (repo / ".stm32-project.json").exists()


# ---------------------------------------------------------------------------
# refusals before any write
# ---------------------------------------------------------------------------


def test_apply_blocked_plan_refuses_without_writes(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "#pragma O3\nint main(void) { return 0; }\n"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers
    before = snapshot_tree(repo)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert list(result.details["blockerCodes"]) == sorted({b.code for b in plan.blockers})
    assert snapshot_tree(repo) == before
    assert not (repo / ".stm32-toolkit").exists()


def test_apply_head_changed(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / "note.txt").write_text("new", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=repo, check=True, env=git_env())
    before = snapshot_tree(repo)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_GIT_HEAD_CHANGED"
    assert result.details == {"expected": plan.git.head, "actual": git_head(repo)}
    assert snapshot_tree(repo) == before


def test_apply_dirty_untracked_staged_and_unstaged(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / "scratch.txt").write_text("x", encoding="utf-8")
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_GIT_DIRTY"
    assert result.details == {"rule": "cleanWorktree"}

    repo2 = standard_repo(tmp_path)
    plan2 = plan_keil_conversion(repo2, fixture_inspection(repo2))
    (repo2 / "note.txt").write_text("y", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo2, check=True)
    result2 = apply_keil_conversion(plan2)
    assert result2.code == "MIGRATION_GIT_DIRTY"
    assert result2.details == {"rule": "cleanWorktree"}

    repo3 = standard_repo(tmp_path)
    (repo3 / "note.txt").write_text("z", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo3, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", "note"], cwd=repo3, check=True, env=git_env())
    plan3 = plan_keil_conversion(repo3, fixture_inspection(repo3))
    (repo3 / "note.txt").write_text("z2", encoding="utf-8")
    result3 = apply_keil_conversion(plan3)
    assert result3.code == "MIGRATION_GIT_DIRTY"
    assert result3.details == {"rule": "cleanWorktree"}


def test_apply_git_status_unavailable(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    git_guard = planner_mod.git_guard
    real_run = git_guard._run_git

    def fail_status(*args, **kwargs):
        if args[0][0] == "status":
            raise git_guard._GitError("nonzero")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", fail_status)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_GIT_UNAVAILABLE"
    assert result.details == {"rule": "status"}


def test_apply_changed_deleted_and_replaced_input(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / "Main" / "main.c").write_text(MAIN_C.replace("__irq", "__irq "), encoding="utf-8")
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_INPUT_CHANGED"
    assert result.details == {"path": "Main/main.c"}

    repo2 = standard_repo(tmp_path)
    plan2 = plan_keil_conversion(repo2, fixture_inspection(repo2))
    (repo2 / "Common" / "common.c").unlink()
    result2 = apply_keil_conversion(plan2)
    assert result2.code == "MIGRATION_INPUT_CHANGED"
    assert result2.details == {"path": "Common/common.c"}

    repo3 = standard_repo(tmp_path)
    plan3 = plan_keil_conversion(repo3, fixture_inspection(repo3))
    (repo3 / "Common" / "common.c").unlink()
    (repo3 / "Common" / "common.c").mkdir()
    result3 = apply_keil_conversion(plan3)
    assert result3.code == "MIGRATION_INPUT_CHANGED"
    assert result3.details == {"path": "Common/common.c"}

    for repo_used in (repo, repo2, repo3):
        assert not (repo_used / ".stm32-toolkit").exists()


def test_apply_input_symlink_escape(tmp_path):
    outside = tmp_path / "outside.c"
    outside.write_text(COMMON_C, encoding="utf-8")
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / "Common" / "common.c").unlink()
    os.symlink(outside, repo / "Common" / "common.c")
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_INPUT_CHANGED"
    assert result.details == {"path": "Common/common.c"}


def test_apply_patch_target_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    os.symlink(outside, repo / "artifacts")
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_PATH_INVALID"
    assert result.details["rule"] == "withinProjectRoot"
    assert result.details["path"] == "artifacts/migration/conversion.patch"
    assert not (repo / ".stm32-toolkit").exists()


def test_apply_target_collision_manifest_and_artifacts(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / ".stm32-project.json").write_text("{}", encoding="utf-8")
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_TARGET_EXISTS"
    assert result.details == {"path": ".stm32-project.json"}

    repo2 = standard_repo(tmp_path)
    plan2 = plan_keil_conversion(repo2, fixture_inspection(repo2))
    (repo2 / "artifacts" / "migration").mkdir(parents=True)
    (repo2 / "artifacts" / "migration" / "conversion.patch").write_bytes(b"x")
    result2 = apply_keil_conversion(plan2)
    assert result2.code == "MIGRATION_TARGET_EXISTS"
    assert result2.details == {"path": "artifacts/migration/conversion.patch"}


def test_apply_staging_collision(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        gitignore=".stm32-toolkit/\n",
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    staging = repo / ".stm32-toolkit" / "migration-staging" / plan.plan_id
    staging.mkdir(parents=True)
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_TARGET_EXISTS"
    assert result.details == {"path": f".stm32-toolkit/migration-staging/{plan.plan_id}"}
    assert (repo / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")


def test_apply_inspection_failure(tmp_path, monkeypatch):
    from stm32_toolkit.keil import KeilInspectionError

    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    def broken(*args, **kwargs):
        raise KeilInspectionError("KEIL_PROJECT_NOT_FOUND", "gone", {})

    monkeypatch.setattr(planner_mod, "inspect_keil", broken)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details == {"rule": "freshInspection"}
    assert not (repo / ".stm32-toolkit").exists()


# ---------------------------------------------------------------------------
# forged-plan defense
# ---------------------------------------------------------------------------


def test_apply_forged_plan_metadata(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    cases = [
        (replace(plan, plan_version=2), "planVersion"),
        (replace(plan, plan_id="0" * 64), "planId"),
        (replace(plan, git=GitBaseline("0" * 40, ".")), "planId"),
        (
            replace(
                plan,
                inputs=((MigrationInput("Main/main.c", "0" * 64, 5),),),
            ),
            "planId",
        ),
        (
            replace(
                plan,
                patches=(
                    replace(plan.patches[1], path="Other/renamed.c"),
                    *plan.patches[:1],
                    *plan.patches[2:],
                ),
            ),
            "planId",
        ),
    ]
    for forged, _rule in cases:
        before = snapshot_tree(repo)
        result = apply_keil_conversion(forged)
        assert result.ok is False, forged
        assert result.code == "MIGRATION_PLAN_INVALID"
        assert snapshot_tree(repo) == before
        assert not (repo / ".stm32-toolkit").exists()


def test_apply_forged_after_bytes_with_consistent_plan_id(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    common = next(p for p in plan.patches if p.path == "Common/common.c")
    forged = forge(plan, patches=tuple(replace(p, after_bytes=p.after_bytes + b"//x\n") if p is common else p for p in plan.patches))
    before = snapshot_tree(repo)
    result = apply_keil_conversion(forged)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] in ("patchDigest",)
    assert snapshot_tree(repo) == before


def test_apply_forged_plan_with_consistent_plan_id_fails_fresh_replan(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    common = next(p for p in plan.patches if p.path == "Common/common.c")
    main = next(p for p in plan.patches if p.path == "Main/main.c")
    manifest = next(p for p in plan.patches if p.path == ".stm32-project.json")

    # Blockers removed from a genuinely blocked plan.
    repo_b = build_repo(
        tmp_path,
        files={"Main/main.c": "#pragma O3\nint main(void) { return 0; }\n"},
    )
    plan_b = plan_keil_conversion(repo_b, fixture_inspection(repo_b))
    assert plan_b.blockers
    forged_b = forge(plan_b, blockers=())
    result_b = apply_keil_conversion(forged_b)
    assert result_b.ok is False
    assert result_b.code == "MIGRATION_PLAN_INVALID"
    assert result_b.details == {"rule": "freshPlan"}

    # Fixed sections forged with a consistent plan id.
    forged_fixed = forge(
        plan,
        fixed_sections=(
            FixedSectionRequirement(".stm32tk.abs.deadbeef", 0xDEADBEEF, "Common/common.c", 12, "x"),
        ),
    )
    result_fixed = apply_keil_conversion(forged_fixed)
    assert result_fixed.code == "MIGRATION_PLAN_INVALID"
    assert result_fixed.details == {"rule": "freshPlan"}

    # Patch path forged with a consistent plan id (tuple kept sorted so the
    # fresh-replan equality, not an ordering check, is the failing defense).
    forged_path = forge(
        plan,
        patches=(
            manifest,
            main,
            replace(common, path="Other/common.c"),
        ),
    )
    result_path = apply_keil_conversion(forged_path)
    assert result_path.code == "MIGRATION_PLAN_INVALID"
    assert result_path.details == {"rule": "freshPlan"}

    assert not (repo / ".stm32-toolkit").exists()
    assert not (repo_b / ".stm32-toolkit").exists()


def test_apply_forged_duplicate_unsorted_and_bad_paths(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    common = next(p for p in plan.patches if p.path == "Common/common.c")
    main = next(p for p in plan.patches if p.path == "Main/main.c")
    manifest = next(p for p in plan.patches if p.path == ".stm32-project.json")

    duplicates = replace(plan, patches=(common, common, main, manifest))
    result = apply_keil_conversion(duplicates)
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] in ("uniquePath", "planId")

    unsorted = replace(plan, patches=(main, common, manifest))
    result = apply_keil_conversion(unsorted)
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] in ("sortedOrder", "planId")

    for bad in ("../evil.c", "/abs.c", "C:\\evil.c", "a/../../evil.c", "bad\x00name", "a//b.c", ".stm32-toolkit/x", ".git/config", "artifacts/migration/conversion.patch", "other.uvprojx"):
        forged = replace(plan, patches=(replace(common, path=bad), main, manifest))
        result = apply_keil_conversion(forged)
        assert result.code == "MIGRATION_PLAN_INVALID", bad
        assert result.details["rule"] == "portablePath", bad

    assert not (repo / ".stm32-toolkit").exists()


def test_apply_casefold_collision(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    common = next(p for p in plan.patches if p.path == "Common/common.c")
    main = next(p for p in plan.patches if p.path == "Main/main.c")
    manifest = next(p for p in plan.patches if p.path == ".stm32-project.json")
    forged = forge(
        plan,
        patches=(
            replace(common, path="Main/a.c"),
            replace(main, path="main/a.c"),
            manifest,
        ),
    )
    result = apply_keil_conversion(forged)
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] == "casefoldCollision"


def test_apply_forged_before_bytes_digest_mismatch(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    common = next(p for p in plan.patches if p.path == "Common/common.c")
    forged = replace(
        plan,
        patches=(
            replace(common, before_bytes=common.before_bytes + b"#x\n"),
            *plan.patches[1:],
        ),
    )
    result = apply_keil_conversion(forged)
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] == "patchDigest"


def test_apply_report_limit(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    monkeypatch.setattr(apply_mod, "_REPORT_LIMIT_BYTES", 64)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details == {"rule": "reportLimit"}
    assert not (repo / ".stm32-toolkit").exists()


# ---------------------------------------------------------------------------
# failure injection: staging, replace, fsync, rollback
# ---------------------------------------------------------------------------


def test_apply_stage_failure_removes_staging(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    def broken_stage(*args, **kwargs):
        raise OSError(5, "stage failed")

    monkeypatch.setattr(apply_mod, "_stage_write", broken_stage)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_APPLY_FAILED"
    assert result.details == {"phase": "stage"}
    assert (repo / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")
    assert (repo / "Common" / "common.c").read_bytes() == COMMON_C.encode("utf-8")
    assert not (repo / ".stm32-toolkit").exists()
    assert git_status(repo) == ""


def test_apply_replace_failure_rolls_back_exactly(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    mode_before = stat.S_IMODE((repo / "Common" / "common.c").stat().st_mode)
    state_before = snapshot_tree(repo)

    real_replace = os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(28, "replace failed")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_APPLY_FAILED"
    assert result.details == {"phase": "replace"}

    # Every pre-apply byte and mode is restored; staging is gone; status clean.
    assert (repo / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")
    assert (repo / "Common" / "common.c").read_bytes() == COMMON_C.encode("utf-8")
    assert stat.S_IMODE((repo / "Common" / "common.c").stat().st_mode) == mode_before
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts").exists()
    assert not (repo / ".stm32-toolkit").exists()
    assert git_status(repo) == ""
    # Content digest of every pre-existing file matches the pre-apply state.
    for rel, entry in state_before.items():
        if entry[0] == "file":
            assert hashlib.sha256((repo / rel).read_bytes()).hexdigest() == entry[1]


def test_apply_replace_failure_after_all_destinations_rolls_back_created(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    real_replace = os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 5:
            raise OSError(28, "replace failed")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_APPLY_FAILED"
    assert result.details == {"phase": "replace"}
    assert (repo / "Common" / "common.c").read_bytes() == COMMON_C.encode("utf-8")
    assert (repo / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts").exists()
    assert not (repo / ".stm32-toolkit").exists()
    assert git_status(repo) == ""


def test_apply_fsync_failure_rolls_back(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    def broken_fsync_dir(path):
        raise OSError(5, "fsync failed")

    monkeypatch.setattr(apply_mod, "_fsync_dir", broken_fsync_dir)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_APPLY_FAILED"
    assert result.details == {"phase": "fsync"}
    assert (repo / "Common" / "common.c").read_bytes() == COMMON_C.encode("utf-8")
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / ".stm32-toolkit").exists()
    assert git_status(repo) == ""


def test_apply_rollback_failure_retains_staging(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    real_replace = os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        calls["n"] += 1
        # Fail the first rollback restore call (destination #5 = conversion-report
        # replace succeeded; rollback restores in reverse: Main/main.c first).
        if calls["n"] == 6:
            raise OSError(28, "rollback replace failed")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_ROLLBACK_FAILED"
    assert result.details["paths"] == ["Main/main.c"]
    # Staging with backups is retained for manual recovery.
    staging = repo / ".stm32-toolkit" / "migration-staging" / plan.plan_id
    assert staging.exists()
    backups = staging / "backup"
    assert backups.exists()
    assert (backups / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")


def test_apply_no_writes_on_any_preflight_failure(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    (repo / "Main" / "main.c").unlink()
    result = apply_keil_conversion(plan)
    assert result.code == "MIGRATION_INPUT_CHANGED"
    assert not (repo / ".stm32-toolkit").exists()
    assert not (repo / "artifacts").exists()


# ---------------------------------------------------------------------------
# unrelated-state protection
# ---------------------------------------------------------------------------


def test_apply_leaves_unrelated_state_untouched(tmp_path):
    repo = standard_repo(tmp_path)
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    (repo / "Objects").mkdir()
    (repo / "Objects" / "legacy.map").write_text("map\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", "extra"], cwd=repo, check=True, env=git_env())
    head_before = git_head(repo)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    result = apply_keil_conversion(plan)
    assert result.ok is True
    assert (repo / "README.md").read_bytes() == b"readme\n"
    assert (repo / "Objects" / "legacy.map").read_bytes() == b"map\n"
    assert (repo / "app.uvprojx").read_bytes().startswith(b"<?xml")
    assert git_head(repo) == head_before
    assert subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=False).returncode == 0


def test_apply_existing_identical_manifest_is_not_rewritten(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
    )
    first = plan_keil_conversion(repo, fixture_inspection(repo))
    proposal = next(p for p in first.patches if p.path == ".stm32-project.json").after_bytes
    (repo / ".stm32-project.json").write_bytes(proposal)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", "manifest"], cwd=repo, check=True, env=git_env())
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert not any(p.path == ".stm32-project.json" for p in plan.patches)
    result = apply_keil_conversion(plan)
    assert result.ok is True
    assert ".stm32-project.json" not in result.to_dict()["data"]["createdPaths"]
    assert ".stm32-project.json" not in result.to_dict()["data"]["changedPaths"]
    assert (repo / ".stm32-project.json").read_bytes() == proposal
    assert subprocess.run(["git", "diff", "--quiet"], cwd=repo, check=False).returncode == 0
    assert subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=False).returncode == 0


def test_apply_worktree_repo(tmp_path):
    main = standard_repo(tmp_path)
    worktree = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "wt", str(worktree)], cwd=main, check=True)
    plan = plan_keil_conversion(worktree, fixture_inspection(worktree))
    result = apply_keil_conversion(plan)
    assert result.ok is True
    assert (worktree / "Main" / "main.c").read_bytes() == MAIN_C_AFTER.encode("utf-8")
    # The main worktree is untouched.
    assert (main / "Main" / "main.c").read_bytes() == MAIN_C.encode("utf-8")
