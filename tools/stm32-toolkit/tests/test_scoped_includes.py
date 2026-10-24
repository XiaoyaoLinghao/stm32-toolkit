"""Group/file include-only scope analysis (KEIL-SCOPED-INCLUDES).

Every repository is a disposable local Git repository below pytest's
temporary root.  Tests exercise the public preflight and the real
transactional apply; no network, compiler, Keil installation, or hardware is
required.  Git-ignored header changes are intentional: they prove that the
directory inventory digest, not the Git dirty check, protects the reviewed
conflict decision.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import stm32_toolkit.migration.model as model_mod
import stm32_toolkit.migration.scoped_includes as scoped_mod
from stm32_toolkit.keil import KeilInspectionError, inspect_keil
from stm32_toolkit.migration import apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.migration.preflight import preflight_keil_conversion
from stm32_toolkit.migration.scoped_includes import analyze_scoped_includes

from test_migration_plan import (
    FRAMEWORK_INCLUDE,
    _add_file_scoped_controls,
    _add_group_scoped_controls,
    _scoped_controls_xml,
    build_repo,
    fixture_inspection,
    git_init,
    manifest_json,
    snapshot_tree,
    standard_repo,
    write_uvprojx,
)

MAIN_C = "int main(void) { return 0; }\n"


def _commit(repo: Path, message: str = "scoped includes") -> None:
    """Initialize the disposable repository on first use, then commit."""
    if not (repo / ".git").exists():
        git_init(repo)
        return
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Scope Test", "-c", "user.email=scope@test.local", "commit", "-q", "-m", message],
        cwd=repo,
        check=True,
    )


def _scope_repo(
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
    group_scopes: tuple[tuple[str, str], ...] = (),
    file_scopes: tuple[tuple[str, str, bool], ...] = (),
    uvprojx_kwargs: dict | None = None,
    gitignore: str | None = None,
    name: str = "scoped",
) -> Path:
    """Build a disposable repository with optional include-only scopes."""
    base_files = {"Main/main.c": MAIN_C}
    base_files.update(files or {})
    kwargs: dict = {
        "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        "includes": f"Main;{FRAMEWORK_INCLUDE}",
    }
    kwargs.update(uvprojx_kwargs or {})
    repo = build_repo(
        tmp_path,
        name=name,
        files=base_files,
        uvprojx_kwargs=kwargs,
        gitignore=gitignore,
        commit=False,
    )
    for group_name, include_paths in group_scopes:
        _add_group_scoped_controls(repo, group_name, include_paths=include_paths)
    for file_path, include_paths, excluded in file_scopes:
        _add_file_scoped_controls(
            repo, file_path, include_paths=include_paths, excluded=excluded
        )
    _commit(repo)
    return repo


def _manifest(plan) -> dict:
    return manifest_json(next(patch for patch in plan.patches if patch.path == ".stm32-project.json"))


def _codes(plan) -> list[str]:
    return [blocker.code for blocker in plan.blockers]


# ---------------------------------------------------------------------------
# supported merges
# ---------------------------------------------------------------------------


def test_group_scope_evidence_is_shared_by_preflight_plan_and_manifest(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    inspection = fixture_inspection(repo)
    before = snapshot_tree(repo)

    preflight = preflight_keil_conversion(repo, inspection)

    assert preflight["analysis"]["blockers"] == []
    evidence = preflight["analysis"]["includeMerges"]
    assert [
        (entry["scope"], entry["owner"], entry["path"], entry["decision"])
        for entry in evidence
    ] == [("group", "Main", "GroupOnly", "added")]
    assert evidence[0]["inventoryFiles"] == 1
    assert len(evidence[0]["inventorySha256"]) == 64
    # Preflight is read-only: no plan, no manifest, no staging.
    assert snapshot_tree(repo) == before

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == []
    assert [
        (
            merge.scope,
            merge.owner,
            merge.path,
            merge.decision,
            merge.inventory_sha256,
            merge.inventory_files,
        )
        for merge in plan.include_merges
    ] == [
        (
            entry["scope"],
            entry["owner"],
            entry["path"],
            entry["decision"],
            entry["inventorySha256"],
            entry["inventoryFiles"],
        )
        for entry in evidence
    ]
    assert plan.to_dict()["include_merges"] == [
        merge.to_dict() for merge in plan.include_merges
    ]
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "GroupOnly",
    ]
    assert snapshot_tree(repo) == before


def test_target_order_is_preserved_and_exposed_directories_are_deduplicated(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={"Extra/extra.h": "#pragma once\n"},
        group_scopes=(("Main", "Main;Extra"),),
        file_scopes=(("Main/main.c", "Extra", False),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == []
    assert [
        (merge.scope, merge.owner, merge.path, merge.decision)
        for merge in plan.include_merges
    ] == [
        ("group", "Main", "Main", "already-present"),
        ("group", "Main", "Extra", "added"),
        ("file", "Main/main.c", "Extra", "already-present"),
    ]
    # One appended directory, original target order untouched.
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "Extra",
    ]


def test_already_present_scope_requires_no_filesystem_scan(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        group_scopes=(("Main", "Main"),),
    )

    def explode(directory):
        raise AssertionError(f"unexpected inventory scan: {directory}")

    monkeypatch.setattr(scoped_mod, "_list_entries", explode)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == []
    assert [(merge.path, merge.decision) for merge in plan.include_merges] == [
        ("Main", "already-present")
    ]
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_normalized_scope_path_is_not_resolved_again_against_uvprojx_directory(
    tmp_path,
):
    root = tmp_path / "nested"
    (root / "Project").mkdir(parents=True)
    (root / "Main").mkdir()
    (root / "Main" / "main.c").write_text(MAIN_C, encoding="utf-8")
    (root / "Inc").mkdir()
    (root / "Inc" / "inc.h").write_text("#pragma once\n", encoding="utf-8")
    (root / FRAMEWORK_INCLUDE).mkdir(parents=True)
    framework_windows = FRAMEWORK_INCLUDE.replace("/", "\\")
    write_uvprojx(
        root / "Project",
        includes=f"..\\Main;..\\{framework_windows}",
        groups=(("Main", (("main.c", "1", "..\\Main\\main.c"),)),),
    )
    project = root / "Project" / "app.uvprojx"
    text = project.read_text(encoding="utf-8")
    marker = "            <GroupName>Main</GroupName>\n"
    option = _scoped_controls_xml(
        option_tag="GroupOption", include_paths="..\\Inc"
    )
    project.write_text(text.replace(marker, marker + option, 1), encoding="utf-8")
    git_init(root)

    inspection = inspect_keil(root)
    assert inspection.project_file == "Project/app.uvprojx"
    # Inspection already resolved every path against the uvprojx directory.
    assert inspection.include_paths == ("Main", FRAMEWORK_INCLUDE)
    group_options = [
        option for option in inspection.scoped_options if option.scope == "group"
    ]
    assert group_options[0].include_paths == ("Inc",)

    plan = plan_keil_conversion(root, inspection)

    assert _codes(plan) == []
    assert [(merge.path, merge.decision) for merge in plan.include_merges] == [
        ("Inc", "added")
    ]
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "Inc",
    ]


# ---------------------------------------------------------------------------
# invalid scopes
# ---------------------------------------------------------------------------


def test_invalid_scopes_block_without_partial_merge(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Good/good.h": "#pragma once\n",
            "Other/other.c": "int other(void) { return 0; }\n",
            "NotDir.txt": "not a directory\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Other", (("other.c", "1", "Other/other.c"),)),
            )
        },
        group_scopes=(("Main", "Good;Missing"), ("Other", "NotDir.txt")),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == [
        "MIGRATION_INCLUDE_PATH_MISSING",
        "MIGRATION_INCLUDE_PATH_NOT_DIRECTORY",
    ]
    by_code = {blocker.code: blocker for blocker in plan.blockers}
    assert by_code["MIGRATION_INCLUDE_PATH_MISSING"].path == "Missing"
    assert by_code["MIGRATION_INCLUDE_PATH_MISSING"].evidence == "group:Main|Missing"
    assert by_code["MIGRATION_INCLUDE_PATH_NOT_DIRECTORY"].path == "NotDir.txt"
    # The valid "Good" directory is not partially merged while blocked.
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]

    preflight = preflight_keil_conversion(repo, fixture_inspection(repo))
    assert "includeMerges" not in preflight["analysis"]
    remediation = {
        blocker["code"]: blocker["remediation"]
        for blocker in preflight["analysis"]["blockers"]
    }
    assert remediation["MIGRATION_INCLUDE_PATH_MISSING"]["category"] == "unsupported"
    assert "tool" not in remediation["MIGRATION_INCLUDE_PATH_MISSING"]
    assert "skill" not in remediation["MIGRATION_INCLUDE_PATH_MISSING"]


def test_escaping_scope_path_is_rejected_by_inspection_before_analysis(tmp_path):
    repo = _scope_repo(tmp_path, group_scopes=(("Main", "..\\outside"),))

    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(repo)

    # Earlier Keil path safety remains authoritative.
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"


def test_scope_with_defines_is_blocked_without_merging_its_directory(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": MAIN_C,
            "GroupOnly/group.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
        commit=False,
    )
    _add_group_scoped_controls(
        repo, "Main", defines="GROUP_ONLY=1", include_paths="GroupOnly"
    )
    _commit(repo)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["ARMCC_OPTION_UNSUPPORTED"]
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_excluded_file_scope_is_inactive_and_not_validated(tmp_path):
    repo = _scope_repo(
        tmp_path,
        file_scopes=(("Main/main.c", "DoesNotExist", True),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert plan.blockers == ()
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_group_scope_without_included_sources_is_ignored(tmp_path):
    repo = build_repo(
        tmp_path,
        files={
            "Main/main.c": MAIN_C,
            "GroupOnly/group.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
        commit=False,
    )
    _add_group_scoped_controls(repo, "Main", include_paths="DoesNotExist")
    _add_file_scoped_controls(repo, "Main/main.c", excluded=True)
    _commit(repo)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert plan.blockers == ()
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_group_with_c_source_and_listed_header_still_merges(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Inc/cfg.h": "#pragma once\n",
            "Main/main.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (
                (
                    "Main",
                    (
                        ("main.c", "1", "Main/main.c"),
                        ("main.h", "5", "Main/main.h"),
                    ),
                ),
            )
        },
        group_scopes=(("Main", "Inc"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert plan.blockers == ()
    assert [(merge.path, merge.decision) for merge in plan.include_merges] == [
        ("Inc", "added")
    ]
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "Inc",
    ]


def test_header_and_library_only_scopes_have_no_compile_effect(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Main/main.h": "#pragma once\n",
            "Docs/docs.h": "#pragma once\n",
            "Libs/libfoo.a": "archive\n",
        },
        uvprojx_kwargs={
            "groups": (
                (
                    "Main",
                    (
                        ("main.c", "1", "Main/main.c"),
                        ("main.h", "5", "Main/main.h"),
                    ),
                ),
                ("Docs", (("docs.h", "5", "Docs/docs.h"),)),
                ("Libs", (("libfoo.a", "4", "Libs/libfoo.a"),)),
            )
        },
        group_scopes=(("Docs", "DoesNotExist"), ("Libs", "AlsoMissing")),
        file_scopes=(("Docs/docs.h", "AlsoMissingFile", False),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    # Listed headers and precompiled libraries never invoke the compiler, so
    # these scopes neither block nor contribute a directory.
    assert plan.blockers == ()
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_group_with_c_source_and_included_assembly_stays_blocked(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Mixed/mix.c": "int mix(void) { return 0; }\n",
            "Mixed/startup.s": "; startup\n",
            "MixInc/mix.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                (
                    "Mixed",
                    (
                        ("mix.c", "1", "Mixed/mix.c"),
                        ("startup.s", "2", "Mixed/startup.s"),
                    ),
                ),
            )
        },
        group_scopes=(("Mixed", "MixInc"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert "ARMCC_OPTION_UNSUPPORTED" in _codes(plan)
    assert not any(code.startswith("MIGRATION_INCLUDE_") for code in _codes(plan))
    assert plan.include_merges == ()


def test_include_only_group_scope_affecting_assembly_stays_blocked(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Startup/startup.s": "; startup\n    AREA RESET, DATA, READONLY\n    END\n",
            "AsmInc/asm.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup.s", "2", "Startup/startup.s"),)),
            )
        },
        group_scopes=(("Startup", "AsmInc"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert "ARMCC_OPTION_UNSUPPORTED" in _codes(plan)
    assert not any(code.startswith("MIGRATION_INCLUDE_") for code in _codes(plan))
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_include_only_file_scope_affecting_assembly_stays_blocked(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Startup/startup.s": "; startup\n",
            "AsmInc/asm.h": "#pragma once\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup.s", "2", "Startup/startup.s"),)),
            )
        },
        file_scopes=(("Startup/startup.s", "AsmInc", False),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert "ARMCC_OPTION_UNSUPPORTED" in _codes(plan)
    assert not any(code.startswith("MIGRATION_INCLUDE_") for code in _codes(plan))
    assert plan.include_merges == ()


# ---------------------------------------------------------------------------
# include-relative key conflicts
# ---------------------------------------------------------------------------


def test_same_include_relative_key_across_directories_is_a_conflict(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Main/settings.h": "#pragma once\n",
            "IncA/settings.h": "#pragma once\n",
        },
        group_scopes=(("Main", "IncA"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_COLLISION"]
    blocker = plan.blockers[0]
    assert blocker.path == "IncA/settings.h"
    assert blocker.evidence == "group:Main|key:settings.h|other:Main/settings.h"
    assert plan.include_merges == ()
    assert _manifest(plan)["build"]["includePaths"] == ["Main", FRAMEWORK_INCLUDE]


def test_distinct_include_relative_keys_with_the_same_basename_are_not_a_conflict(
    tmp_path,
):
    repo = _scope_repo(
        tmp_path,
        files={
            "IncA/sub/config.h": "#pragma once\n",
            "IncB/config.h": "#pragma once\n",
            "Other/other.c": "int other(void) { return 0; }\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Other", (("other.c", "1", "Other/other.c"),)),
            )
        },
        group_scopes=(("Main", "IncA"), ("Other", "IncB")),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    # Keys "sub/config.h" and "config.h" differ, so the shared basename alone
    # is not a conflict.
    assert plan.blockers == ()
    assert [(merge.path, merge.decision) for merge in plan.include_merges] == [
        ("IncA", "added"),
        ("IncB", "added"),
    ]
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "IncA",
        "IncB",
    ]


def test_same_name_between_two_new_directories_is_a_conflict(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "IncA/board.h": "#pragma once\n",
            "IncB/BOARD.H": "#pragma once\n",
            "Other/other.c": "int other(void) { return 0; }\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Other", (("other.c", "1", "Other/other.c"),)),
            )
        },
        group_scopes=(("Main", "IncA"), ("Other", "IncB")),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    collisions = [b for b in plan.blockers if b.code == "MIGRATION_INCLUDE_COLLISION"]
    assert {blocker.path for blocker in collisions} == {"IncA/board.h", "IncB/BOARD.H"}
    assert all("key:board.h" in blocker.evidence for blocker in collisions)
    assert plan.include_merges == ()


def test_overlapping_target_and_scoped_directories_are_not_a_conflict(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "USER/config.h": "#pragma once\n",
            "USER/IWDG/iwdg.h": "#pragma once\n",
        },
        uvprojx_kwargs={"includes": f"Main;USER;{FRAMEWORK_INCLUDE}"},
        group_scopes=(("Main", "USER/IWDG"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    # USER and USER/IWDG overlap, but IWDG/iwdg.h and iwdg.h are distinct
    # keys and no key resolves to different files.
    assert plan.blockers == ()
    assert [(merge.path, merge.decision) for merge in plan.include_merges] == [
        ("USER/IWDG", "added")
    ]
    assert _manifest(plan)["build"]["includePaths"] == [
        "Main",
        "USER",
        FRAMEWORK_INCLUDE,
        "USER/IWDG",
    ]


def test_same_key_across_overlapping_roots_is_a_conflict(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "USER/settings.h": "#pragma once\n",
            "USER/IWDG/settings.h": "#pragma once\n",
        },
        uvprojx_kwargs={"includes": f"Main;USER;{FRAMEWORK_INCLUDE}"},
        group_scopes=(("Main", "USER/IWDG"),),
    )

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_COLLISION"]
    assert plan.blockers[0].path == "USER/IWDG/settings.h"
    assert (
        plan.blockers[0].evidence
        == "group:Main|key:settings.h|other:USER/settings.h"
    )
    assert plan.include_merges == ()


# ---------------------------------------------------------------------------
# redirects, unreadable input, and bounded traversal
# ---------------------------------------------------------------------------


def test_reparse_component_is_rejected(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    target = str(repo / "GroupOnly").casefold()
    real = scoped_mod._is_redirect

    def fake(path, entry_stat):
        return str(path).casefold().rstrip("\\/") == target or real(path, entry_stat)

    monkeypatch.setattr(scoped_mod, "_is_redirect", fake)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_REDIRECT_UNSUPPORTED"]
    assert plan.blockers[0].path == "GroupOnly"
    assert plan.include_merges == ()


def test_reparse_inside_inventory_is_rejected(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/sub/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    target = str(repo / "GroupOnly" / "sub" / "group.h").casefold()
    real = scoped_mod._is_redirect

    def fake(path, entry_stat):
        return str(path).casefold() == target or real(path, entry_stat)

    monkeypatch.setattr(scoped_mod, "_is_redirect", fake)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_REDIRECT_UNSUPPORTED"]
    assert plan.include_merges == ()


def test_unreadable_inventory_is_rejected(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    real = scoped_mod._list_entries
    target = str(repo / "GroupOnly").casefold()

    def fake(directory):
        if str(directory).casefold() == target:
            raise PermissionError("denied")
        return real(directory)

    monkeypatch.setattr(scoped_mod, "_list_entries", fake)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_PATH_UNREADABLE"]
    assert plan.include_merges == ()


def test_inventory_bound_is_rejected_instead_of_sampling(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    real = scoped_mod._list_entries
    target = str(repo / "GroupOnly").casefold()

    def fake(directory):
        if str(directory).casefold() == target:
            raise scoped_mod._InventoryLimit
        return real(directory)

    monkeypatch.setattr(scoped_mod, "_list_entries", fake)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_LIMIT_EXCEEDED"]
    assert plan.include_merges == ()


def test_hash_bytes_bound_is_rejected(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    monkeypatch.setattr(scoped_mod, "MAX_HASH_BYTES", 0)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_LIMIT_EXCEEDED"]
    assert plan.include_merges == ()


def test_aggregate_directory_budget_is_shared_across_all_directories(
    tmp_path, monkeypatch
):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    # The existing Main and framework directories consume both slots; the new
    # scope's directory is the third and must be rejected.
    monkeypatch.setattr(scoped_mod, "MAX_TOTAL_DIRECTORIES", 2)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_LIMIT_EXCEEDED"]
    assert plan.blockers[0].path == "GroupOnly"
    assert plan.include_merges == ()


def test_aggregate_file_budget_counts_zero_byte_files(tmp_path, monkeypatch):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/empty.h": ""},
        group_scopes=(("Main", "GroupOnly"),),
    )
    # Main/main.c consumes the single slot; the zero-byte header in the new
    # directory still counts against the same aggregate budget.
    monkeypatch.setattr(scoped_mod, "MAX_TOTAL_FILES", 1)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))

    assert _codes(plan) == ["MIGRATION_INCLUDE_LIMIT_EXCEEDED"]
    assert plan.include_merges == ()


# ---------------------------------------------------------------------------
# transactional apply and stale evidence
# ---------------------------------------------------------------------------


def test_apply_writes_the_merged_manifest_and_reports_the_evidence(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert _codes(plan) == []

    result = apply_keil_conversion(plan)

    assert result.ok is True, result.message
    assert result.data["changedPaths"] == []
    assert result.data["createdPaths"] == [
        ".stm32-project.json",
        "artifacts/migration/conversion-report.json",
        "artifacts/migration/conversion.patch",
    ]
    manifest = json.loads((repo / ".stm32-project.json").read_text(encoding="utf-8"))
    assert manifest["build"]["includePaths"] == [
        "Main",
        FRAMEWORK_INCLUDE,
        "GroupOnly",
    ]
    report = json.loads(
        (repo / "artifacts/migration/conversion-report.json").read_text(encoding="utf-8")
    )
    assert report["includeMerges"] == [
        merge.to_report_dict() for merge in plan.include_merges
    ]
    assert report["planId"] == plan.plan_id


def test_apply_rejects_a_changed_git_ignored_header(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
        gitignore="GroupOnly/\n",
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert _codes(plan) == []

    # Git stays clean because the directory is ignored; only the bounded
    # inventory digest can detect the reviewed-decision drift.
    (repo / "GroupOnly" / "group.h").write_text(
        "#pragma once\n/* changed */\n", encoding="utf-8"
    )

    result = apply_keil_conversion(plan)

    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] == "freshPlan"
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts/migration/conversion-report.json").exists()
    assert not (repo / ".stm32-toolkit").exists()


def test_apply_rejects_a_new_colliding_git_ignored_file(tmp_path):
    repo = _scope_repo(
        tmp_path,
        files={
            "Main/settings.h": "#pragma once\n",
            "GroupOnly/group.h": "#pragma once\n",
        },
        group_scopes=(("Main", "GroupOnly"),),
        gitignore="GroupOnly/\n",
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert _codes(plan) == []

    (repo / "GroupOnly" / "settings.h").write_text("#pragma once\n", encoding="utf-8")

    result = apply_keil_conversion(plan)

    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details["rule"] == "freshPlan"
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts/migration").exists()


def test_merge_evidence_is_bound_to_plan_identity_only_when_present(tmp_path):
    plain = standard_repo(tmp_path)
    plain_plan = plan_keil_conversion(plain, fixture_inspection(plain))
    assert "include_merges" not in plain_plan.to_dict()
    assert "include_merges" not in model_mod._plan_id_payload(plain_plan)

    repo = _scope_repo(
        tmp_path,
        files={"GroupOnly/group.h": "#pragma once\n"},
        group_scopes=(("Main", "GroupOnly"),),
    )
    first = plan_keil_conversion(repo, fixture_inspection(repo))
    assert "include_merges" in first.to_dict()
    assert "include_merges" in model_mod._plan_id_payload(first)
    assert analyze_scoped_includes(repo, fixture_inspection(repo)) == analyze_scoped_includes(
        repo, fixture_inspection(repo)
    )

    (repo / "GroupOnly" / "group.h").write_text(
        "#pragma once\n/* ignored change */\n", encoding="utf-8"
    )
    changed = analyze_scoped_includes(repo, fixture_inspection(repo))

    assert changed.merges[0].inventory_sha256 != first.include_merges[0].inventory_sha256
    assert model_mod.plan_id_for(replace(first, include_merges=changed.merges)) != first.plan_id
    # The include decision itself is unaffected by the header change.
    assert changed.include_paths == ("Main", FRAMEWORK_INCLUDE, "GroupOnly")
