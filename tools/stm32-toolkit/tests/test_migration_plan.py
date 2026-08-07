"""Tests for read-only ARMCC conversion planning (STM32TK-0303).

Every repository used here is a disposable Git repository created below a
pytest temporary directory; tests invoke only a local Git executable and the
inspection APIs.  No network, compiler, Keil, or hardware is required.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from stm32_toolkit.keil import KeilInputDigest, KeilInspection, inspect_keil

import stm32_toolkit.migration.model as model_mod
import stm32_toolkit.migration.planner as planner_mod
from stm32_toolkit.migration import (
    FilePatch,
    MigrationPlan,
    MigrationPlanError,
    apply_keil_conversion,
    plan_keil_conversion,
)

CORE_CPU = 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4") FPU2'
FRAMEWORK_INCLUDE = "Libraries/STM32F4xx_StdPeriph_Driver"
UUID_NAMESPACE = uuid.UUID("a2e9f523-3c9e-5cb2-bf50-5cf9ff5d16a8")

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

# Expected transformed bytes of COMMON_C under the supported rules.
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


# ---------------------------------------------------------------------------
# disposable-repository helpers
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
    fpu: str = "1",
    pcc: str = "5060750::V5.06 update 7 (build 750)::ARMCC",
) -> Path:
    """Write a minimal namespace-qualified Keil MDK5 project file."""
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
        f"      <pCCUsed>{pcc}</pCCUsed>\n"
        f"      <uAC6>{uac6}</uAC6>\n"
        "      <TargetOption>\n"
        "        <TargetCommonOption>\n"
        f"          <Device>{device}</Device>\n"
        "          <Vendor>STMicroelectronics</Vendor>\n"
        f"          <PackID>{pack}</PackID>\n"
        f"          <Cpu>{cpu}</Cpu>\n"
        + (f"          <uFloatingPoint>{fpu}</uFloatingPoint>\n" if fpu is not None else "")
        + "        </TargetCommonOption>\n"
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


def git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Migration Test", "-c", "user.email=migration@test.local", "add", "-A"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=Migration Test", "-c", "user.email=migration@test.local", "commit", "-q", "-m", "init"],
        cwd=root,
        check=True,
    )


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
    commit: bool = True,
) -> Path:
    """Create a disposable repository: uvprojx + sources, then commit."""
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
        path.write_bytes(content.encode("utf-8"))
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    if gitignore is not None:
        (root / ".gitignore").write_bytes(gitignore.encode("utf-8"))
    if commit:
        git_init(root)
    return root


def standard_repo(tmp_path: Path) -> Path:
    return build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
    )


def fixture_inspection(root: Path) -> KeilInspection:
    return inspect_keil(root)


def _inject_reparse(monkeypatch, link: Path, target: Path) -> None:
    """Deterministically simulate a reparse point at ``link`` whose canonical
    target is ``target``, without requiring OS privileges.

    Windows fallback used when a real junction cannot be created (file
    targets, missing ``mklink``, restricted policy): ``Path.resolve()`` is
    made to behave exactly as if ``link`` were a reparse point, so the
    product defense observes the redirect without any skip or xfail.
    """
    link_canon = os.path.realpath(os.fspath(link))
    target_canon = os.path.realpath(os.fspath(target))
    real_resolve = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        self_canon = os.path.realpath(os.fspath(self))
        if self_canon == link_canon or self_canon.startswith(link_canon + os.sep):
            rel = Path(self_canon).relative_to(link_canon)
            resolved = (
                Path(target_canon)
                if rel == Path(".")
                else Path(target_canon) / rel
            )
            return real_resolve(resolved, strict=strict)
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)


def _make_redirect(monkeypatch, link: Path, target: Path) -> None:
    """Create a real directory redirect without administrator rights.

    POSIX uses a real symlink.  Windows prefers a real NTFS directory
    junction (``mklink /J``, no admin rights); when a junction cannot be
    created (file target, missing tooling, restricted policy) a deterministic
    reparse-point simulation is injected instead, so every test still
    exercises the defense with no skip.
    """
    if os.name == "nt":
        if target.is_dir():
            try:
                created = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", os.fspath(link), os.fspath(target)],
                    capture_output=True,
                )
            except OSError:
                created = None
            if created is not None and created.returncode == 0:
                return
        _inject_reparse(monkeypatch, link, target)
        return
    os.symlink(target, link)


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


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def manifest_json(patch: FilePatch) -> dict:
    return json.loads(patch.after_bytes.decode("utf-8"))


# ---------------------------------------------------------------------------
# root / inspection validation
# ---------------------------------------------------------------------------


def test_root_must_be_path_and_directory(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion("not-a-path", inspection)  # type: ignore[arg-type]
    assert error.value.code == "MIGRATION_ROOT_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "type"}

    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(tmp_path / "missing", inspection)
    assert error.value.code == "MIGRATION_ROOT_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "directory"}

    file_root = repo / "Main" / "main.c"
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(file_root, inspection)
    assert error.value.code == "MIGRATION_ROOT_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "directory"}


def test_inspection_must_be_keil_inspection(tmp_path):
    repo = standard_repo(tmp_path)
    fixture_inspection(repo)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, None)  # type: ignore[arg-type]
    assert error.value.code == "MIGRATION_INSPECTION_INVALID"
    assert error.value.details == {"field": "inspection", "rule": "type"}

    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, {"device": "x"})  # type: ignore[arg-type]
    assert error.value.code == "MIGRATION_INSPECTION_INVALID"
    assert error.value.details == {"field": "inspection", "rule": "type"}


def test_root_mismatch_with_inspection_project_root(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(other, inspection)
    assert error.value.code == "MIGRATION_INSPECTION_INVALID"
    assert error.value.details == {"field": "inspection", "rule": "rootMatch"}


def test_root_must_equal_git_toplevel(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    subdir = repo / "Nested"
    subdir.mkdir()
    subdir_inspection = replace(inspection, project_root=subdir)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(subdir, subdir_inspection)
    assert error.value.code == "MIGRATION_ROOT_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "canonicalRoot"}


def test_non_repository_root_raises_git_unavailable(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    bare = tmp_path / "bare"
    bare.mkdir()
    shutil.copytree(repo / "Main", bare / "Main")
    shutil.copytree(repo / "Common", bare / "Common")
    shutil.copy2(repo / "app.uvprojx", bare / "app.uvprojx")
    (bare / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    bare_inspection = fixture_inspection(bare)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(bare, bare_inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "repository"}


def test_unborn_head_raises_git_unavailable(tmp_path):
    root = tmp_path / "unborn"
    root.mkdir()
    write_uvprojx(root)
    (root / "Main").mkdir()
    (root / "Main" / "main.c").write_bytes(MAIN_C.encode("utf-8"))
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    inspection = fixture_inspection(root)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(root, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "head"}


def test_git_missing_binary_timeout_and_malformed_output(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    git_guard = planner_mod.git_guard
    real_run = git_guard._run_git

    def missing(*args, **kwargs):
        raise git_guard._GitError("missing")

    monkeypatch.setattr(git_guard, "_run_git", missing)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "repository"}

    def timed_out(*args, **kwargs):
        raise git_guard._GitError("timeout")

    monkeypatch.setattr(git_guard, "_run_git", timed_out)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"

    def bad_head(*args, **kwargs):
        if args[0] == ["rev-parse", "HEAD"]:
            raise git_guard._GitError("nonzero")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", bad_head)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "head"}

    def short_head(*args, **kwargs):
        if args[0] == ["rev-parse", "HEAD"]:
            return b"abc\n"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", short_head)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "head"}

    def huge_head(*args, **kwargs):
        if args[0] == ["rev-parse", "HEAD"]:
            raise git_guard._GitError("overflow")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", huge_head)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "head"}

    def undecodable_status(*args, **kwargs):
        if args[0][0] == "status":
            raise git_guard._GitError("undecodable")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", undecodable_status)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_GIT_UNAVAILABLE"
    assert error.value.details == {"rule": "status"}


def test_git_output_shape_validation(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    git_guard = planner_mod.git_guard
    real_run = git_guard._run_git

    def undecodable_toplevel(*args, **kwargs):
        if args[0] == ["rev-parse", "--show-toplevel"]:
            return b"\xff\xfe"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", undecodable_toplevel)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "repository"}

    def empty_toplevel(*args, **kwargs):
        if args[0] == ["rev-parse", "--show-toplevel"]:
            return b"\n"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", empty_toplevel)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "repository"}

    def relative_toplevel(*args, **kwargs):
        if args[0] == ["rev-parse", "--show-toplevel"]:
            return b"relative/path\n"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", relative_toplevel)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "repository"}

    def undecodable_head(*args, **kwargs):
        if args[0] == ["rev-parse", "HEAD"]:
            return b"\xff\xfe"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", undecodable_head)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "head"}

    def empty_head(*args, **kwargs):
        if args[0] == ["rev-parse", "HEAD"]:
            return b"\n"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", empty_head)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "head"}

    def overflow_status(*args, **kwargs):
        if args[0][0] == "status":
            raise git_guard._GitError("overflow")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_guard, "_run_git", overflow_status)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.details == {"rule": "status"}


def test_dirty_tracked_untracked_and_staged_produce_blocker(tmp_path):
    repo = standard_repo(tmp_path)
    (repo / "README.md").write_bytes(b"readme\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "readme"],
        cwd=repo,
        check=True,
    )
    inspection = fixture_inspection(repo)
    (repo / "README.md").write_bytes(b"readme changed\n")
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "MIGRATION_GIT_DIRTY" for b in plan.blockers)

    repo2 = standard_repo(tmp_path)
    inspection2 = fixture_inspection(repo2)
    (repo2 / "scratch.txt").write_bytes(b"x")
    plan2 = plan_keil_conversion(repo2, inspection2)
    assert any(b.code == "MIGRATION_GIT_DIRTY" for b in plan2.blockers)

    repo3 = standard_repo(tmp_path)
    inspection3 = fixture_inspection(repo3)
    (repo3 / "note.txt").write_bytes(b"n")
    subprocess.run(["git", "add", "-A"], cwd=repo3, check=True)
    plan3 = plan_keil_conversion(repo3, inspection3)
    assert any(b.code == "MIGRATION_GIT_DIRTY" for b in plan3.blockers)


def test_ignored_files_do_not_dirty_the_baseline(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        gitignore=".stm32-toolkit/\n",
    )
    inspection = fixture_inspection(repo)
    (repo / ".stm32-toolkit").mkdir()
    (repo / ".stm32-toolkit" / "scratch").write_bytes(b"ignored")
    plan = plan_keil_conversion(repo, inspection)
    assert not any(b.code == "MIGRATION_GIT_DIRTY" for b in plan.blockers)


# ---------------------------------------------------------------------------
# input revalidation
# ---------------------------------------------------------------------------


def test_input_missing_changed_oversized_and_non_regular(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    (repo / "Common" / "common.c").unlink()
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_INSPECTION_CHANGED"
    assert error.value.details == {"path": "Common/common.c"}

    repo2 = standard_repo(tmp_path)
    inspection2 = fixture_inspection(repo2)
    (repo2 / "Common" / "common.c").write_bytes(COMMON_C.replace("common_work", "other_work").encode("utf-8"))
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo2, inspection2)
    assert error.value.code == "MIGRATION_INSPECTION_CHANGED"
    assert error.value.details == {"path": "Common/common.c"}

    repo3 = standard_repo(tmp_path)
    inspection3 = fixture_inspection(repo3)
    with (repo3 / "Common" / "common.c").open("ab") as handle:
        handle.write(b"/* grown */")
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo3, inspection3)
    assert error.value.code == "MIGRATION_INPUT_INVALID"
    assert error.value.details == {"path": "Common/common.c", "rule": "size"}

    repo4 = standard_repo(tmp_path)
    inspection4 = fixture_inspection(repo4)
    (repo4 / "Common" / "common.c").unlink()
    (repo4 / "Common" / "common.c").mkdir()
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo4, inspection4)
    assert error.value.code == "MIGRATION_INPUT_INVALID"
    assert error.value.details == {"path": "Common/common.c", "rule": "regularFile"}


def test_input_unreadable_rejects_conservatively(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    real_open = Path.open

    def deny(self, mode="r", *args, **kwargs):
        if mode == "rb" and self == repo / "Main" / "main.c":
            raise PermissionError(13, "denied")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_INPUT_INVALID"
    assert error.value.details == {"path": "Main/main.c", "rule": "regularFile"}


def test_input_redirect_handling_in_revalidation(tmp_path, monkeypatch):
    """The input revalidation defense accepts in-root redirects and rejects
    redirects that escape the canonical root (real symlinks on Linux, real
    junctions or deterministic reparse simulation on Windows)."""
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    common = next(d for d in inspection.inputs if d.path == "Common/common.c")

    (repo / "Common" / "common.c").unlink()
    (repo / "Common" / "real_common.c").write_bytes(COMMON_C.encode("utf-8"))
    _make_redirect(monkeypatch, repo / "Common" / "common.c", repo / "Common" / "real_common.c")
    data = planner_mod._revalidate_inputs(repo, (common,))
    assert data["Common/common.c"] == COMMON_C.encode("utf-8")

    outside = tmp_path / "outside.c"
    outside.write_bytes(COMMON_C.encode("utf-8"))
    (repo / "Common" / "common.c").unlink(missing_ok=True)
    _make_redirect(monkeypatch, repo / "Common" / "common.c", outside)
    with pytest.raises(MigrationPlanError) as error:
        planner_mod._revalidate_inputs(repo, (common,))
    assert error.value.code == "MIGRATION_INPUT_INVALID"
    assert error.value.details == {"path": "Common/common.c", "rule": "withinProjectRoot"}


def test_input_redirect_handling_with_injected_reparse(tmp_path, monkeypatch):
    """The deterministic reparse simulation (the Windows fallback for
    unprivileged file redirects) must itself be exercised on Linux too: the
    planner accepts an injected in-root reparse point and rejects an injected
    escape exactly like the real-redirect test."""
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    common = next(d for d in inspection.inputs if d.path == "Common/common.c")

    (repo / "Common" / "common.c").unlink()
    (repo / "Common" / "real_common.c").write_bytes(COMMON_C.encode("utf-8"))
    _inject_reparse(monkeypatch, repo / "Common" / "common.c", repo / "Common" / "real_common.c")
    data = planner_mod._revalidate_inputs(repo, (common,))
    assert data["Common/common.c"] == COMMON_C.encode("utf-8")

    outside = tmp_path / "outside.c"
    outside.write_bytes(COMMON_C.encode("utf-8"))
    _inject_reparse(monkeypatch, repo / "Common" / "common.c", outside)
    with pytest.raises(MigrationPlanError) as error:
        planner_mod._revalidate_inputs(repo, (common,))
    assert error.value.code == "MIGRATION_INPUT_INVALID"
    assert error.value.details == {"path": "Common/common.c", "rule": "withinProjectRoot"}


def test_forged_input_path_forms_are_rejected(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    original = inspection.inputs
    for bad in ("/etc/passwd", "C:\\evil.c", "C:evil.c", "\\\\server\\share", "a/../b.c", ".", "a/b/../../c.c", "bad\x00name"):
        forged = replace(
            inspection,
            inputs=tuple(
                [KeilInputDigest(bad, digest.sha256, digest.size) for digest in original[:1]]
            ),
        )
        with pytest.raises(MigrationPlanError) as error:
            plan_keil_conversion(repo, forged)
        assert error.value.code == "MIGRATION_INPUT_INVALID"
        assert error.value.details["rule"] == "withinProjectRoot"


def test_input_revalidation_matches_recorded_digests(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    original = inspection.inputs
    common = next(d for d in original if d.path == "Common/common.c")
    forged = replace(
        inspection,
        inputs=tuple(
            [
                KeilInputDigest(common.path, "0" * 64, common.size)
                if digest is common
                else digest
                for digest in original
            ]
        ),
    )
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, forged)
    assert error.value.code == "MIGRATION_INSPECTION_CHANGED"
    assert error.value.details == {"path": "Common/common.c"}


def test_limit_exceeded_file_and_aggregate(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    original = inspection.inputs
    common = next(d for d in original if d.path == "Common/common.c")
    forged = replace(
        inspection,
        inputs=tuple(
            [
                KeilInputDigest(common.path, common.sha256, 9 * 1024 * 1024)
                if digest is common
                else digest
                for digest in original
            ]
        ),
    )
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, forged)
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "file", "limitBytes": 8 * 1024 * 1024}

    monkeypatch.setattr(planner_mod, "_AGGREGATE_LIMIT_BYTES", 64)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "aggregate", "limitBytes": 64}


# ---------------------------------------------------------------------------
# fresh-inspection guard
# ---------------------------------------------------------------------------


def test_stale_or_forged_inspection_rejected(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    stale = replace(inspection, device="STM32F407VGTx")
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, stale)
    assert error.value.code == "MIGRATION_INSPECTION_INVALID"
    assert error.value.details == {"field": "inspection", "rule": "freshInspection"}

    stale2 = replace(inspection, project_file="missing.uvprojx")
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, stale2)
    assert error.value.code == "MIGRATION_INSPECTION_INVALID"
    assert error.value.details == {"field": "inspection", "rule": "freshInspection"}


def test_inspection_with_missing_source_not_in_inputs_is_not_scanned(tmp_path):
    """A source that vanished before inspection is not an input and is not transformed."""
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": MAIN_C,
            "Common/common.c": COMMON_C.replace("__irq void", "void"),
        },
        commit=False,
    )
    (repo / "Common" / "common.c").unlink()
    git_init(repo)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    assert all(patch.path != "Common/common.c" for patch in plan.patches)


# ---------------------------------------------------------------------------
# determinism, ordering, serialization
# ---------------------------------------------------------------------------


def test_repeated_planning_is_deterministic_and_read_only(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    before = snapshot_tree(repo)
    status_before = git_status(repo)
    head_before = git_head(repo)
    first = plan_keil_conversion(repo, inspection)
    second = plan_keil_conversion(repo, inspection)
    assert first.plan_id == second.plan_id
    assert first.to_dict() == second.to_dict()
    assert first.inspection_sha256 == second.inspection_sha256
    assert snapshot_tree(repo) == before
    assert git_status(repo) == status_before
    assert git_head(repo) == head_before


def test_plan_serialization_is_json_safe_and_omits_host_data(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    data = plan.to_dict()
    json.dumps(data)
    assert "project_root" not in data
    assert "inspection" not in data
    assert "before_bytes" not in data
    assert "after_bytes" not in data
    text = json.dumps(data)
    assert str(repo) not in text
    assert plan.plan_version == 1
    assert plan.git.root_marker == "."
    assert len(plan.plan_id) == 64
    assert plan.plan_id == plan.plan_id.lower()


def test_plan_models_are_frozen(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    with pytest.raises(FrozenInstanceError):
        plan.patches = ()  # type: ignore[misc]
    patch = plan.patches[0]
    with pytest.raises(FrozenInstanceError):
        patch.rule_ids = ()  # type: ignore[misc]


def test_inspection_sha256_is_canonical(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    expected = hashlib.sha256(
        canonical_json_bytes(inspection.to_dict())
    ).hexdigest()
    assert plan.inspection_sha256 == expected


def test_inputs_and_patches_sorted_unique(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    paths = [entry.path for entry in plan.inputs]
    assert paths == sorted(paths)
    assert len(set(paths)) == len(paths)
    patch_paths = [patch.path for patch in plan.patches]
    assert patch_paths == sorted(patch_paths)
    assert len(set(patch_paths)) == len(patch_paths)
    assert patch_paths[0] == ".stm32-project.json"


def test_plan_id_includes_expected_payload(tmp_path):
    repo = standard_repo(tmp_path)
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    payload = model_mod._plan_id_payload(plan)
    assert payload["plan_version"] == 1
    assert payload["inspection_sha256"] == plan.inspection_sha256
    assert payload["git"]["head"] == plan.git.head
    assert payload["toolkit_version"] == "0.3.0"
    assert payload["patch_content_sha256"] == hashlib.sha256(
        b"".join(patch.unified_diff.encode("utf-8") for patch in plan.patches)
    ).hexdigest()
    assert "plan_id" not in payload
    assert "unified_diff" not in payload
    expected = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    assert plan.plan_id == expected


def test_plan_limit_exceeded(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    monkeypatch.setattr(planner_mod, "_PLAN_LIMIT_BYTES", 64)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "plan", "limitBytes": 64}


# ---------------------------------------------------------------------------
# rules: supported transforms
# ---------------------------------------------------------------------------


def test_irq_nop_wfi_transforms_exact_spans(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__irq void a(void) { __nop(); __wfi(); }\n"
                "__irq   void b(void) { __nop (); __wfi (); }\n"
                "__WFI();\n"
                "__irq\n"
                "void c(void) { }\n"
                "int d = __nop;\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    assert patch.after_bytes == (
        "void a(void) { __NOP(); __WFI(); }\n"
        "void b(void) { __NOP (); __WFI (); }\n"
        "__WFI();\n"
        "\n"
        "void c(void) { }\n"
        "int d = __nop;\n"
    ).encode("utf-8")
    assert set(patch.rule_ids) == {"ARMCC_IRQ_QUALIFIER", "ARMCC_INTRINSIC_NOP", "ARMCC_INTRINSIC_WFI"}


def test_comments_strings_chars_raw_strings_and_substrings_untouched(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "// __irq __nop() __wfi() __at(0) __asm { \n"
                "/* __irq __nop() __wfi() __at(0) */\n"
                'const char *s = "__irq __nop() __wfi()";\n'
                "char ch = 'x';\n"
                "int my__irq_var, __nop_suffix, sub__wfi;\n"
                "const char *t = \"__asm { __at(0x20000000) }\";\n"
                "int main(void) { return 0; }\n"
            ),
            "App/code.cpp": (
                'const char *r = R"tag(__irq __nop() __wfi() __at(0x20000000))tag";\n'
                "int cxx_fn() { return 0; }\n"
            ),
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("App", (("code.cpp", "0", "App/code.cpp"),)),
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patches = {patch.path: patch for patch in plan.patches}
    assert "Main/main.c" not in patches
    assert "App/code.cpp" not in patches
    assert not any(patch.rule_ids for patch in plan.patches if patch.path.endswith(".cpp"))


def test_compatible_asm_and_gcc_section_attribute_ignored(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                '__asm("nop");\n'
                '__asm("cpsie i");\n'
                '__attribute__((section(".my.data"))) int x;\n'
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    assert not any(patch.path == "Main/main.c" for patch in plan.patches)
    ignored = sorted((obs.rule_id, obs.path, obs.line) for obs in plan._ignored)
    assert ignored == [
        ("ARMCC_COMPATIBLE_ASM", "Main/main.c", 1),
        ("ARMCC_COMPATIBLE_ASM", "Main/main.c", 2),
        ("ARMCC_GCC_SECTION_ATTRIBUTE", "Main/main.c", 3),
    ]


def test_absolute_placement_attribute_and_at_forms(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__attribute__((at(0x20000000))) int pinned;\n"
                "__at(0x20000400) volatile uint32_t buf[64];\n"
                "__at(536875008) static int decimal_pinned;\n"
                "__at(0x08000000) const char vector[4];\n"
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    assert patch.after_bytes == (
        '__attribute__((section(".stm32tk.abs.20000000"), used)) int pinned;\n'
        '__attribute__((section(".stm32tk.abs.20000400"), used)) volatile uint32_t buf[64];\n'
        '__attribute__((section(".stm32tk.abs.20001000"), used)) static int decimal_pinned;\n'
        '__attribute__((section(".stm32tk.abs.08000000"), used)) const char vector[4];\n'
        "int main(void) { return 0; }\n"
    ).encode("utf-8")
    sections = {s.symbol: s for s in plan.fixed_sections}
    assert sections["pinned"].section == ".stm32tk.abs.20000000"
    assert sections["pinned"].address == 0x20000000
    assert sections["pinned"].source_path == "Main/main.c"
    assert sections["pinned"].line == 1
    assert sections["decimal_pinned"].section == ".stm32tk.abs.20001000"
    assert sections["vector"].section == ".stm32tk.abs.08000000"
    # sorted by (address, section, source_path, line, symbol)
    assert [s.address for s in plan.fixed_sections] == sorted(s.address for s in plan.fixed_sections)


def test_absolute_placement_unsupported_grammar_blockers(tmp_path):
    cases = [
        "__at(0x20000000) int x = 5;\n",  # initializer
        "__at(0x20000000) int *p;\n",  # pointer
        "__at(0x20000000) int a, b;\n",  # comma / two declarators
        "__at(0x20000000) int f(void);\n",  # function
        "__at(SOME_MACRO) int x;\n",  # macro-expanded address
        "__at(0x20000000) int arr[0x40];\n",  # hex array bound
        "__at(0x100000000) int x;\n",  # out of range
        "__at(-1) int x;\n",  # negative
        "__at(0x20000000) int x; trailing_code();\n",  # trailing code
        "__at(0x20000000)\nint x;\n",  # multi-line declaration
        "__at(0x20000000) int bit: 3;\n",  # bit-field
        "__attribute__((at(0x20000000), used)) int x;\n",  # mixed attributes
    ]
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__irq void isr(void) { __nop(); }\n"
                + "".join(cases)
                + "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    placement = [b for b in plan.blockers if b.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"]
    assert len(placement) == len(cases)
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    # Supported edits still apply; no placement is rewritten.
    assert patch.after_bytes.startswith(b"void isr(void) { __NOP(); }\n")
    for case in cases:
        assert case.encode("utf-8") in patch.after_bytes
    assert plan.fixed_sections == ()


def test_absolute_placement_duplicate_address_and_symbol_blockers(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__irq void isr(void) { __nop(); }\n"
                "__at(0x20000000) int first;\n"
                "__at(0x20000000) int second;\n"  # same address, different symbol
                "__at(0x20000000) int first;\n"  # duplicate (address, symbol)
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    placement = [b for b in plan.blockers if b.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"]
    assert len(placement) == 2
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    assert b"__at(0x20000000)" in patch.after_bytes  # no placement rewrite
    assert b"void isr(void) { __NOP(); }" in patch.after_bytes  # other rules still apply
    assert plan.fixed_sections == ()


def test_duplicate_address_across_files_is_blocked(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__irq void m(void) { __nop(); }\n"
                "__at(0x20000000) int a;\nint main(void) { return 0; }\n"
            ),
            "Common/common.c": "__at(0x20000000) int b;\n",
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    placement = [b for b in plan.blockers if b.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"]
    # The later declaration (Main/main.c sorts after Common/common.c) is the
    # offender: its file keeps no placement rewrite; the earlier one is kept.
    assert [b.path for b in placement] == ["Main/main.c"]
    main_patch = next(p for p in plan.patches if p.path == "Main/main.c")
    assert b"__at(0x20000000) int a;" in main_patch.after_bytes
    assert b"void m(void) { __NOP(); }" in main_patch.after_bytes
    common_patch = next(p for p in plan.patches if p.path == "Common/common.c")
    assert b'__attribute__((section(".stm32tk.abs.20000000"), used)) int b;' in common_patch.after_bytes


def test_encoding_bom_crlf_and_mixed_newlines_preserved(tmp_path):
    bom = b"\xef\xbb\xbf"
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": None,  # placeholder, replaced below
        },
    )
    (repo / "Common").mkdir(exist_ok=True)
    (repo / "Common" / "common.c").write_bytes(bom + b"__irq void a(void) { __nop(); }\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "bom"], cwd=repo, check=True)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == "Common/common.c")
    assert patch.after_bytes == bom + b"void a(void) { __NOP(); }\n"

    repo2 = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\r\n",
            "Common/common.c": "__irq void a(void) { __nop(); }\r\n__wfi();\r\n",
        },
    )
    inspection2 = fixture_inspection(repo2)
    plan2 = plan_keil_conversion(repo2, inspection2)
    patch2 = next(p for p in plan2.patches if p.path == "Common/common.c")
    assert patch2.after_bytes == b"void a(void) { __NOP(); }\r\n__WFI();\r\n"

    repo3 = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\r\n",
            "Common/common.c": "__irq void a(void) { __nop(); }\r\n__wfi();\n",
        },
    )
    inspection3 = fixture_inspection(repo3)
    plan3 = plan_keil_conversion(repo3, inspection3)
    patch3 = next(p for p in plan3.patches if p.path == "Common/common.c")
    assert patch3.after_bytes == b"void a(void) { __NOP(); }\r\n__WFI();\n"


def test_invalid_encoding_adds_blocker(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": None,
        },
    )
    (repo / "Common").mkdir(exist_ok=True)
    (repo / "Common" / "common.c").write_bytes(b"\xff\xfe\x00__irq void broken() { }\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "bin"], cwd=repo, check=True)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert any(
        b.code == "ARMCC_SOURCE_ENCODING_UNSUPPORTED" and b.path == "Common/common.c"
        for b in plan.blockers
    )
    assert not any(patch.path == "Common/common.c" for patch in plan.patches)


def test_evidence_is_capped(tmp_path):
    long_line = "__asm { " + "x" * 5000 + "\n"
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": long_line + "int main(void) { return 0; }\n"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers
    for blocker in plan.blockers:
        assert len(blocker.evidence) <= 200


def test_raw_string_edge_cases(tmp_path):
    # Unterminated raw string: the remainder is swallowed and never rewritten.
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "App/code.cpp": (
                'const char *r = R"tag(__irq __nop()\n'
                "__wfi();\n"
                "int untouched(void) { return 0; }\n"
            ),
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("App", (("code.cpp", "0", "App/code.cpp"),)),
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert not any(patch.path == "App/code.cpp" for patch in plan.patches)

    # R" not followed by a delimiter/paren is not a raw string; the ordinary
    # string state still protects its content.
    repo2 = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "App/code.cpp": 'const char *s = R"x __irq __nop() y";\nint f() { return 0; }\n',
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("App", (("code.cpp", "0", "App/code.cpp"),)),
            )
        },
    )
    inspection2 = fixture_inspection(repo2)
    plan2 = plan_keil_conversion(repo2, inspection2)
    assert not any(patch.path == "App/code.cpp" for patch in plan2.patches)


def test_asm_char_form_is_blocker(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "__asm('x');\nint main(void) { return 0; }\n"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    # The work order sanctions only __asm("...") statement expressions;
    # a char-literal operand is not a supported compatible form.
    assert any(b.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED" for b in plan.blockers)


def test_placement_token_edge_cases(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__at(0x10\n"  # unterminated call: no candidate
                "__at x;\n"  # no paren: not a placement
                "__attribute__\n"  # no parens: ignored
                "__attribute__((at(0x20)\n"  # unbalanced: no candidate
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert not any(b.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED" for b in plan.blockers)
    assert plan.fixed_sections == ()


def test_rule_scan_limits_direct(monkeypatch):
    import stm32_toolkit.migration.rules as rules_mod

    with pytest.raises(MigrationPlanError) as error:
        rules_mod.scan_sources([("big.c", b"x" * (8 * 1024 * 1024 + 1), "c")])
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "file", "limitBytes": 8 * 1024 * 1024}

    monkeypatch.setattr(rules_mod, "SCAN_TOTAL_LIMIT", 8)
    with pytest.raises(MigrationPlanError) as error:
        rules_mod.scan_sources([("a.c", b"aaaaa", "c"), ("b.c", b"bbbb", "c")])
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "aggregate", "limitBytes": 8}


# ---------------------------------------------------------------------------
# blocker classes
# ---------------------------------------------------------------------------


def test_inline_assembly_blockers(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                "__asm void legacy_func(void) { }\n"
                "void brace_form(void) { __asm { mov r0, r0 } }\n"
                '__asm("nop");\n'
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    asm = [b for b in plan.blockers if b.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"]
    assert len(asm) == 2
    assert asm[0].line == 1
    assert asm[1].line == 2


def test_assembly_source_blocker(tmp_path):
    startup = "; startup\n    AREA RESET, DATA, READONLY\n    END\n"
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Startup/startup.s": startup,
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup.s", "2", "Startup/startup.s"),)),
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert any(
        b.code == "ARMCC_ASSEMBLY_UNSUPPORTED" and b.path == "Startup/startup.s"
        for b in plan.blockers
    )


def test_pragma_blockers(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": (
                '#pragma arm section code=".mycode"\n'
                "#pragma import(__use_no_semihosting)\n"
                "#pragma O3\n"
                "#pragma pack(1)\n"
                "int main(void) { return 0; }\n"
            )
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    pragma = [b for b in plan.blockers if b.code == "ARMCC_PRAGMA_UNSUPPORTED"]
    # arm section, import, O3 each produce one blocker; pack(1) is not flagged.
    assert len(pragma) == 3


def test_linker_configuration_blockers(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"scatter": ".\\Objects\\app.sct"},
    )
    (repo / "Objects").mkdir()
    (repo / "Objects" / "app.sct").write_bytes(b"LR_IROM1 0x08000000 0x100000 {\n}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "sct"], cwd=repo, check=True)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED" for b in plan.blockers)

    repo2 = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"linker_misc": "--keep section(.my)"},
    )
    inspection2 = fixture_inspection(repo2)
    plan2 = plan_keil_conversion(repo2, inspection2)
    assert any(
        b.code == "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED"
        for b in plan2.blockers
    )


def test_option_unsupported_blocker(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"compiler_misc": "--c99 --gnu"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "ARMCC_OPTION_UNSUPPORTED" for b in plan.blockers)


def test_compiler_unsupported_blocker(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"pcc": "6190000::V6.19::ARMCLANG"},
    )
    inspection = fixture_inspection(repo)
    assert inspection.compiler == "armclang"
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "MIGRATION_COMPILER_UNSUPPORTED" for b in plan.blockers)


def test_framework_selection_required_blocker_and_no_manifest(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"defines": "STM32F429xx", "includes": "Main"},
    )
    inspection = fixture_inspection(repo)
    assert inspection.framework is None
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "MIGRATION_FRAMEWORK_SELECTION_REQUIRED" for b in plan.blockers)
    assert not any(patch.path == ".stm32-project.json" for patch in plan.patches)


def test_memory_incomplete_blocker(tmp_path):
    cpu = 'IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")'
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"cpu": cpu},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert any(b.code == "MIGRATION_MEMORY_INCOMPLETE" for b in plan.blockers)


def test_blockers_aggregate_across_files_without_early_return(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": "#pragma O3\n__asm { }\n",
            "Common/common.c": "#pragma import(__x)\n__irq void f(void) { __nop(); }\n",
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    codes = sorted({b.code for b in plan.blockers})
    assert codes == [
        "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
        "ARMCC_PRAGMA_UNSUPPORTED",
    ]
    # Patches are still proposed for the supported edits.
    common = next(p for p in plan.patches if p.path == "Common/common.c")
    assert b"__irq " not in common.after_bytes
    assert b"__NOP();" in common.after_bytes


def test_finding_unsupported_mapping_unit(tmp_path):
    from stm32_toolkit.keil import KeilFinding

    finding = KeilFinding("ARMCC_UNKNOWN_FUTURE", "blocker", "Main/main.c", 3, 4, "x", "m")
    blockers = planner_mod._finding_blockers((finding,))
    assert len(blockers) == 1
    assert blockers[0].code == "ARMCC_FINDING_UNSUPPORTED"
    assert blockers[0].rule_id == "ARMCC_FINDING_UNSUPPORTED"
    assert blockers[0].path == "Main/main.c"
    assert blockers[0].line == 3
    assert blockers[0].column == 4

    resolved = [
        KeilFinding("ARMCC_SOURCE_ENCODING_UNSUPPORTED", "blocker", "a.c", 0, 0, "", "m"),
        KeilFinding("ARMCC_UNSUPPORTED_PRAGMA", "blocker", "a.c", 1, 1, "p", "m"),
        KeilFinding("ARMCC_ABSOLUTE_PLACEMENT", "blocker", "a.c", 2, 2, "p", "m"),
        KeilFinding("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", "a.c", 3, 3, "p", "m"),
    ]
    mapped = planner_mod._finding_blockers(resolved)
    assert [b.code for b in mapped] == ["ARMCC_PRAGMA_UNSUPPORTED"]


def test_git_dirty_blocker_sorting(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    (repo / "note.txt").write_bytes(b"x")
    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers[0].code == "MIGRATION_GIT_DIRTY"
    keys = [(b.path, b.line, b.column, b.code, b.rule_id) for b in plan.blockers]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# manifest proposal
# ---------------------------------------------------------------------------


def test_manifest_mapping_and_deterministic_uuid(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        uvprojx_kwargs={"output": "my app v1"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == ".stm32-project.json")
    assert patch.before_bytes is None
    assert patch.before_sha256 is None
    payload = manifest_json(patch)
    assert payload["schemaVersion"] == 2
    expected_uuid = str(uuid.uuid5(UUID_NAMESPACE, "app.uvprojx\nLegacy\nSTM32F429ZGTx"))
    assert payload["logicalProjectId"] == expected_uuid
    assert payload["generatedBy"] == {"tool": "stm32-toolkit", "version": "0.3.0"}
    assert payload["project"] == {"name": "my app v1", "origin": "keil-migration"}
    assert payload["target"] == {
        "device": "STM32F429ZGTx",
        "core": "cortex-m4",
        "fpu": "FPU2",
        "floatAbi": "softfp",
        "devicePack": "Keil.STM32F4xx_DFP.2.16.1",
    }
    assert payload["framework"] == {"type": "spl", "version": None}
    assert payload["build"]["sources"] == ["Main/main.c", "Common/common.c"]
    assert payload["build"]["includePaths"] == ["Main", "Common", FRAMEWORK_INCLUDE]
    assert payload["build"]["defines"] == ["USE_STDPERIPH_DRIVER", "STM32F429xx"]
    assert payload["build"]["compileOptions"] == []
    assert payload["build"]["assemblySources"] == []
    assert payload["build"]["presets"] == ["arm-debug", "arm-release"]
    assert payload["build"]["elf"] == "build/arm-debug/my_app_v1.elf"
    assert payload["memory"]["source"] == "keil"
    assert payload["memory"]["regions"] == [
        {"name": "IROM1", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "IRAM1", "origin": 0x20000000, "length": 0x30000, "attributes": "rwx"},
    ]
    assert payload["debug"] == {}
    assert payload["generation"] == {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    }


def test_manifest_canonical_bytes(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == ".stm32-project.json")
    text = patch.after_bytes.decode("utf-8")
    assert not text.startswith("\ufeff")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")  # exactly one trailing LF
    payload = json.loads(text)
    assert list(payload.keys()) == [
        "schemaVersion",
        "logicalProjectId",
        "generatedBy",
        "project",
        "target",
        "framework",
        "build",
        "memory",
        "debug",
        "generation",
    ]
    assert json.dumps(payload, indent=2, ensure_ascii=False) + "\n" == text
    assert patch.after_sha256 == hashlib.sha256(patch.after_bytes).hexdigest()
    assert patch.after_size == len(patch.after_bytes)


# ---------------------------------------------------------------------------
# Keil float ABI normalization (STM32TK-0306 revision 1)
# ---------------------------------------------------------------------------


def _plan_target_for_fpu(tmp_path, fpu: str | None):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"fpu": fpu},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == ".stm32-project.json")
    return plan, manifest_json(patch)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", "soft"),  # Keil "Not Used": no FPU instructions -> soft ABI
        ("1", "softfp"),  # Keil "Single precision" (ARMCC softfp ABI)
        ("2", "softfp"),  # Keil "Double precision" (ARMCC softfp ABI)
        ("soft", "soft"),
        ("softfp", "softfp"),
        ("hard", "hard"),
    ],
)
def test_known_keil_float_abi_values_are_normalized(tmp_path, raw: str, expected: str):
    """Regression: raw Keil numbers or GCC spellings are normalized to
    soft/softfp/hard only on verifiable Keil-format evidence."""
    plan, payload = _plan_target_for_fpu(tmp_path, raw)

    assert payload["target"]["floatAbi"] == expected
    assert not any(b.code == "MIGRATION_FLOAT_ABI_UNSUPPORTED" for b in plan.blockers)


@pytest.mark.parametrize("raw", ["3", "Single", "Double", "FPU2", "weird", "SoftFP"])
def test_unknown_or_ambiguous_float_abi_produces_a_stable_blocker(
    tmp_path, raw: str
):
    """Regression: unknown or ambiguous float ABI text never enters the
    manifest and always produces a stable blocker."""
    plan, payload = _plan_target_for_fpu(tmp_path, raw)

    assert "floatAbi" not in payload["target"]
    blocker = [b for b in plan.blockers if b.code == "MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    assert len(blocker) == 1
    assert blocker[0].message == "unsupported or ambiguous Keil float ABI"


def test_absent_float_abi_stays_absent(tmp_path):
    """No uFloatingPoint evidence means no floatAbi in the proposal."""
    _, payload = _plan_target_for_fpu(tmp_path, None)

    assert "floatAbi" not in payload["target"]


def test_float_abi_blocker_is_deterministic_across_calls(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"fpu": "weird"},
    )
    inspection = fixture_inspection(repo)

    first = plan_keil_conversion(repo, inspection)
    second = plan_keil_conversion(repo, inspection)

    codes = [b.code for b in first.blockers if b.code == "MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    assert codes == ["MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    assert first.plan_id == second.plan_id


def test_float_abi_blocker_blocks_apply(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"fpu": "weird"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)

    result = apply_keil_conversion(plan)

    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert list(result.details["blockerCodes"]) == ["MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    assert not (repo / ".stm32-project.json").exists()


def test_elf_name_sanitization(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"output": "..--__weird name__.."},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == ".stm32-project.json")
    assert manifest_json(patch)["build"]["elf"] == "build/arm-debug/weird_name.elf"


def test_existing_identical_manifest_is_noop_input(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    first = plan_keil_conversion(repo, inspection)
    proposal = next(p for p in first.patches if p.path == ".stm32-project.json").after_bytes
    (repo / ".stm32-project.json").write_bytes(proposal)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "manifest"], cwd=repo, check=True)
    inspection2 = fixture_inspection(repo)
    second = plan_keil_conversion(repo, inspection2)
    assert not any(patch.path == ".stm32-project.json" for patch in second.patches)
    assert any(entry.path == ".stm32-project.json" for entry in second.inputs)
    assert not any(b.code == "MIGRATION_MANIFEST_EXISTS" for b in second.blockers)


def test_existing_different_manifest_adds_blocker(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    (repo / ".stm32-project.json").write_bytes(b'{"schemaVersion": 2}\n')
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "manifest"], cwd=repo, check=True)
    inspection2 = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection2)
    assert any(b.code == "MIGRATION_MANIFEST_EXISTS" for b in plan.blockers)
    assert not any(patch.path == ".stm32-project.json" for patch in plan.patches)
    assert any(entry.path == ".stm32-project.json" for entry in plan.inputs)


def test_manifest_validation_failure_is_stable(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    bad = {
        "schemaVersion": 2,
        "logicalProjectId": "not-a-uuid",
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.3.0"},
        "project": {"name": "x", "origin": "keil-migration"},
        "target": {"device": "d", "core": "c"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": [],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build/arm-debug/x.elf",
        },
        "memory": {"source": "keil", "regions": []},
        "debug": {},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }
    with pytest.raises(MigrationPlanError) as error:
        planner_mod._validate_manifest_payload(repo, bad)
    assert error.value.code == "MIGRATION_MANIFEST_INVALID"
    assert error.value.details["field"] == "logicalProjectId"

    escaping = dict(bad)
    escaping["logicalProjectId"] = str(uuid.uuid5(UUID_NAMESPACE, "x"))
    escaping["build"] = dict(escaping["build"])
    escaping["build"]["elf"] = "/etc/passwd"
    with pytest.raises(MigrationPlanError) as error:
        planner_mod._validate_manifest_payload(repo, escaping)
    assert error.value.code == "MIGRATION_MANIFEST_INVALID"


def test_framework_blocked_means_no_manifest_even_when_clean(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={"defines": "STM32F429xx", "includes": "Main"},
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    assert not any(patch.path == ".stm32-project.json" for patch in plan.patches)


# ---------------------------------------------------------------------------
# unified diff and patch shape
# ---------------------------------------------------------------------------


def test_unified_diff_shape(tmp_path):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    patch = next(p for p in plan.patches if p.path == "Common/common.c")
    lines = patch.unified_diff.splitlines(keepends=True)
    assert lines[0] == "--- a/Common/common.c\n"
    assert lines[1] == "+++ b/Common/common.c\n"
    assert any(line.startswith("@@ -") for line in lines)
    manifest = next(p for p in plan.patches if p.path == ".stm32-project.json")
    mlines = manifest.unified_diff.splitlines(keepends=True)
    assert mlines[0] == "--- a/.stm32-project.json\n"
    assert mlines[1] == "+++ b/.stm32-project.json\n"
    assert mlines[2].startswith("@@ -0,0 +1,")


def test_patch_limit_exceeded(tmp_path, monkeypatch):
    repo = standard_repo(tmp_path)
    inspection = fixture_inspection(repo)
    monkeypatch.setattr(planner_mod, "_PATCH_LIMIT_BYTES", 32)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(repo, inspection)
    assert error.value.code == "MIGRATION_LIMIT_EXCEEDED"
    assert error.value.details == {"scope": "patch", "limitBytes": 32}


# ---------------------------------------------------------------------------
# git worktree with .git as a file
# ---------------------------------------------------------------------------


def test_git_worktree_repo_is_supported(tmp_path):
    main = standard_repo(tmp_path)
    worktree = tmp_path / "worktree"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "wt", str(worktree)], cwd=main, check=True)
    assert (worktree / ".git").is_file()
    inspection = fixture_inspection(worktree)
    plan = plan_keil_conversion(worktree, inspection)
    assert plan.git.head == git_head(main)


# ---------------------------------------------------------------------------
# cross-module guard: apply is refused for any blocker
# ---------------------------------------------------------------------------


def test_apply_refuses_blocked_plan_before_any_write(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "#pragma O3\nint main(void) { return 0; }\n"},
        uvprojx_kwargs={"defines": "USE_STDPERIPH_DRIVER,STM32F429xx", "includes": f"Main;{FRAMEWORK_INCLUDE}"},
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
