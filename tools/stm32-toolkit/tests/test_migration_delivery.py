"""Independent, Git-free Keil-to-GCC delivery tests (M1).

Every source tree is a disposable synthetic fixture below pytest's temporary
directory; the real user project is never touched.  Planning/apply tests use
no Git, compiler, or hardware.  The final test performs a real ARM GNU CMake
build of an output-only relocation and therefore requires the coordinator's
offline toolchain; a missing tool is an explicit failure, never a silent skip
and never replaced by a fake binary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.generation import (
    GenerationError,
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.generation.configure import render_new_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.migration import (
    MigrationPlanError,
    StartupOptions,
    apply_keil_delivery,
    plan_keil_delivery,
)
import stm32_toolkit.migration.delivery as delivery
from stm32_toolkit.debug_configuration import post_migration_debug_configuration
from stm32_toolkit.project_model import load_project_model

from startup_gcc_fixture import MAIN_C as STARTUP_MAIN_C
from startup_gcc_fixture import STARTUP_SOURCE, SYNTHETIC_STARTUP
from test_migration_plan import COMMON_C, FRAMEWORK_INCLUDE, MAIN_C, build_repo

REPORT_PATH = "artifacts/migration/conversion-report.json"
MANAGED_MANIFEST_PATH = ".stm32-toolkit/generated-files.json"
GENERATED_TARGETS = (
    "CMakeLists.txt",
    "cmake/arm-none-eabi-gcc.cmake",
    "CMakePresets.json",
    "linker/stm32tk.ld",
    ".vscode/tasks.json",
    ".vscode/launch.json",
    ".vscode/c_cpp_properties.json",
    ".vscode/settings.json",
    ".vscode/extensions.json",
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

GNU_BIN = Path(
    os.environ.get(
        "STM32TK_ARM_GNU_BIN",
        r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin",
    )
)
CMAKE_BIN = Path(
    os.environ.get("STM32TK_CMAKE_BIN", r"C:/ST/STM32CubeCLT_1.22.0/CMake/bin")
)
NINJA_BIN = Path(
    os.environ.get("STM32TK_NINJA_BIN", r"C:/ST/STM32CubeCLT_1.22.0/Ninja/bin")
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_files() -> dict[str, str]:
    return {
        "Main/main.c": MAIN_C,
        "Common/common.c": COMMON_C,
        "LICENSE": "Synthetic fixture license. Not a vendor license.\n",
        "README.md": "Synthetic migrated project fixture.\n",
        f"{FRAMEWORK_INCLUDE}/stm32f4xx.h": "#pragma once\n/* synthetic */\n",
        "Common/private/unlisted_header.h": (
            "#pragma once\n#define PRIVATE_VALUE 3\n"
        ),
    }


def make_repo(
    tmp_path: Path,
    *,
    name: str = "source",
    files: dict[str, str] | None = None,
    uvprojx_kwargs: dict | None = None,
) -> Path:
    base = tmp_path / "fixtures"
    base.mkdir(parents=True, exist_ok=True)
    return build_repo(
        base,
        name=name,
        files=files if files is not None else _default_files(),
        uvprojx_kwargs=uvprojx_kwargs,
        commit=False,
    )


def tree_digest(root: Path) -> tuple[tuple[str, ...], ...]:
    result: list[tuple[str, ...]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result.append(("dir", relative))
        elif path.is_file():
            result.append(("file", relative, sha256(path.read_bytes())))
        else:
            result.append(("other", relative))
    return tuple(result)


def output_parent(tmp_path: Path, name: str = "output") -> Path:
    parent = tmp_path / name
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def edit_manifest(root: Path, mutate) -> None:
    path = root / ".stm32-project.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_authorized(plan):
    return apply_keil_delivery(plan, authorized=True, plan_id=plan.plan_id)


def staging_entries(parent: Path) -> list[Path]:
    return sorted(parent.glob(".*.stm32tk-staging-*"))


def _preview_by_path(plan) -> dict[str, dict[str, object]]:
    return {entry["path"]: entry for entry in plan.to_dict()["outputs"]}


# ---------------------------------------------------------------------------
# successful independent delivery
# ---------------------------------------------------------------------------


def test_no_git_plan_apply_preserves_source_and_configures_output(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    binary = b"\x00\x01\x02synthetic-binary\xff"
    (repo / "Assets").mkdir()
    (repo / "Assets" / "logo.bin").write_bytes(binary)
    assert not (repo / ".git").exists()
    before = tree_digest(repo)
    parent = output_parent(tmp_path)
    destination = parent / "gcc-project"

    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert plan.destination_state == "absent"
    assert SHA_RE.fullmatch(plan.plan_id) is not None
    assert SHA_RE.fullmatch(plan.content_id) is not None
    assert plan.plan_id != plan.content_id
    assert not destination.exists()
    assert staging_entries(parent) == []

    preview = plan.to_dict()
    assert preview["configured"] is False
    assert preview["built"] is False
    assert preview["flashed"] is False
    outputs = _preview_by_path(plan)
    for path in (
        "LICENSE",
        f"{FRAMEWORK_INCLUDE}/stm32f4xx.h",
        "Common/private/unlisted_header.h",
    ):
        assert outputs[path]["kind"] == "copied"
        assert outputs[path]["sha256"] == sha256((repo / path).read_bytes())
    assert outputs["Assets/logo.bin"]["sha256"] == sha256(binary)
    assert outputs["Assets/logo.bin"]["kind"] == "copied"
    assert outputs["Assets/logo.bin"]["binary"] is False
    for generated in GENERATED_TARGETS:
        assert outputs[generated]["kind"] == "generated"
    assert outputs[MANAGED_MANIFEST_PATH]["kind"] == "generated"
    assert outputs[REPORT_PATH]["kind"] == "generated"
    # Reviewed source patches are visible before apply.
    assert outputs["Common/common.c"]["kind"] == "replaced"
    assert outputs["Common/common.c"]["unifiedDiff"]
    assert preview["sourcePatches"]
    assert any(
        "stm32tk.abs.20000000" in patch["unified_diff"]
        for patch in preview["sourcePatches"]
        if patch["path"] == "Common/common.c"
    )
    # Raw binary payloads never enter the preview.
    encoded = json.dumps(preview)
    assert "\\u0000" not in encoded
    assert "synthetic-binary" not in encoded
    assert all("content" not in entry for entry in preview["outputs"])
    assert preview["inventory"]["excludedGitEntries"] == 0

    # Identical input, destination and options produce an identical plan.
    repeat = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert repeat.plan_id == plan.plan_id
    assert repeat.to_dict()["outputs"] == preview["outputs"]

    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    data = result.data
    assert data["built"] is False
    assert data["flashed"] is False
    assert data["configured"] is True
    assert Path(data["outputRoot"]) == destination
    assert data["sourceSnapshotSha256"] == plan.source_snapshot_sha256
    assert data["outputSnapshotSha256"] == plan.output_snapshot_sha256

    # The source is byte-identical and the destination contains every output.
    assert tree_digest(repo) == before
    assert staging_entries(parent) == []
    assert not (destination / ".git").exists()
    for output in plan.outputs:
        target = destination.joinpath(*output.path.split("/"))
        assert target.is_file(), output.path
        assert sha256(target.read_bytes()) == output.sha256
    for path in (
        "LICENSE",
        f"{FRAMEWORK_INCLUDE}/stm32f4xx.h",
        "Common/private/unlisted_header.h",
        "Assets/logo.bin",
    ):
        assert (destination / path).read_bytes() == (repo / path).read_bytes()

    # Schema 2 conversion report: content snapshot and content identity, no
    # mandatory Git and no claim to be the final plan ID.
    report = json.loads((destination / REPORT_PATH).read_text(encoding="utf-8"))
    assert report["schemaVersion"] == 2
    assert report["sourceSnapshotSha256"] == plan.source_snapshot_sha256
    assert report["contentId"] == plan.content_id
    assert SHA_RE.fullmatch(report["contentId"]) is not None
    assert "planId" not in report
    assert "gitHead" not in report

    # The normal configure route accepts the output and agrees on the manifest.
    model = load_project_model(destination)
    configuration = plan_project_configuration(model)
    assert configuration.blockers == ()
    assert sha256(configuration.managed_manifest_bytes) == (
        plan.managed_manifest_sha256
    )
    assert configuration.managed_manifest_bytes == (
        destination / MANAGED_MANIFEST_PATH
    ).read_bytes()
    applied = apply_project_configuration(configuration)
    assert applied.ok is True, applied.to_dict()

    # A second destination binds its own content identity because the report
    # records the destination-bound content ID.  Every other output remains
    # byte-identical; only the report differs.
    other = parent / "second-project"
    second = plan_keil_delivery(repo, other, inspect_keil(repo))
    assert second.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert second.content_id != plan.content_id
    assert second.output_snapshot_sha256 != plan.output_snapshot_sha256
    assert second.plan_id != plan.plan_id
    first_outputs = {
        output.path: output.sha256
        for output in plan.outputs
        if output.path != REPORT_PATH
    }
    second_outputs = {
        output.path: output.sha256
        for output in second.outputs
        if output.path != REPORT_PATH
    }
    assert first_outputs == second_outputs
    second_result = apply_authorized(second)
    assert second_result.ok is True, second_result.to_dict()
    second_report = json.loads((other / REPORT_PATH).read_text(encoding="utf-8"))
    assert second_report["contentId"] == second.content_id
    assert second_report["contentId"] != report["contentId"]


def test_post_migration_debug_guidance_is_shared_and_not_an_identity(
    tmp_path: Path,
) -> None:
    """PLAN and successful APPLY expose the shared derived debug guidance.

    The guidance is additive presentation: it must never enter the hashed
    plan/content inputs, never add a blocker, and never invent a backend,
    target or hardware fact.
    """
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path, "guidance")
    destination = parent / "gcc-project"

    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    preview = plan.to_dict()
    expected = post_migration_debug_configuration()

    debug = preview["debugConfiguration"]
    assert debug == expected
    assert debug["phase"] == "post-migration"
    assert debug["blocking"] is False
    assert debug["status"] == "needs-user-input"
    assert debug["backend"] is None and debug["target"] is None
    assert debug["missingFields"] == ["debug.backend", "debug.target"]
    assert [entry["code"] for entry in debug["diagnostics"]] == [
        "DEBUG_BACKEND_MISSING",
        "DEBUG_TARGET_MISSING",
    ]
    assert debug["targetSupport"] == "not-checked"
    assert debug["hardwareVerified"] is False
    # The readable follow-up keeps its historical string type and is derived
    # from exactly the same next steps.
    assert isinstance(preview["followUp"], str)
    for step in debug["nextSteps"]:
        assert step in preview["followUp"]
    joined = " ".join(debug["nextSteps"])
    # The existing paired configure PLAN command stays an exact substring.
    assert (
        "stm32-toolkit project configure --project <project> "
        "--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json"
    ) in joined
    assert "stm32_project_configure" in joined
    assert "--apply --json --plan-id <data.plan_id> --authorized" in joined
    # Bind the destination root, then configure before establishing build or
    # flash identities.
    assert "outputRoot" in joined
    assert "before establishing build or flash identities" in joined
    # launch.json stays empty by design; the live configuration belongs to an
    # independent external IDE workspace and the original ticket ends it.
    assert "data.cortexDebugLaunch.configuration" in joined
    assert "launch.json" in joined
    assert "handoff-end" in joined
    # The plan still declares build-only state and no inferred target.
    assert preview["configured"] is False
    assert preview["built"] is False
    assert preview["flashed"] is False

    # Deriving guidance changes no identity input: the same source, destination
    # and options produce the same plan ID, content ID and output snapshot.
    repeat = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert repeat.plan_id == plan.plan_id
    assert repeat.content_id == plan.content_id
    assert repeat.output_snapshot_sha256 == plan.output_snapshot_sha256
    assert repeat.to_dict()["debugConfiguration"] == debug

    # The conversion report and delivered manifest carry no derived guidance.
    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    data = result.to_dict()["data"]
    assert data["configured"] is True
    assert data["built"] is False
    assert data["flashed"] is False
    assert data["debugConfiguration"] == expected
    assert isinstance(data["followUp"], str)
    for step in expected["nextSteps"]:
        assert step in data["followUp"]
    report = json.loads(
        (destination / REPORT_PATH).read_text(encoding="utf-8")
    )
    assert "debugConfiguration" not in report
    assert "followUp" not in report
    model = load_project_model(destination)
    assert model.debug.backend is None and model.debug.target is None
    # No launch configuration was written for the delivered project. The
    # generated file is a plain launch document with top-level "configurations",
    # not a workspace settings object wrapping one.
    launch = json.loads(
        (destination / ".vscode" / "launch.json").read_text(encoding="utf-8")
    )
    assert launch["configurations"] == []


EXT_REGION = ExtraRegion("EXT_SRAM", 0x68000000, 0x10000, "rw-")
EXT_LAYOUT = MemoryLayout("IROM1", "IRAM1", "EXT_SRAM", "EXT_SRAM", "EXT_SRAM")


def test_explicit_extra_regions_bind_and_configure_accepts(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    inspection = inspect_keil(repo)
    parent = output_parent(tmp_path, "extras")
    plain = plan_keil_delivery(repo, parent / "plain", inspection)
    with_extras = plan_keil_delivery(
        repo,
        parent / "with-extras",
        inspection,
        memory_layout=EXT_LAYOUT,
        extra_regions=(EXT_REGION,),
    )
    assert plain.plan_id != with_extras.plan_id
    assert with_extras.extra_regions == (EXT_REGION,)
    assert with_extras.memory_layout == EXT_LAYOUT

    result = apply_authorized(with_extras)
    assert result.ok is True, result.to_dict()
    destination = parent / "with-extras"
    report = json.loads((destination / REPORT_PATH).read_text(encoding="utf-8"))
    assert report["extraRegions"] == [EXT_REGION.to_dict()]
    assert report["contentId"] == with_extras.content_id
    configuration = plan_project_configuration(load_project_model(destination))
    assert configuration.blockers == ()


def test_destination_absent_and_empty_states_are_bound(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path, "states")
    destination = parent / "project"

    absent = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert absent.destination_state == "absent"
    destination.mkdir()
    empty = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert empty.destination_state == "empty"
    assert empty.plan_id != absent.plan_id

    result = apply_authorized(empty)
    assert result.ok is True, result.to_dict()
    assert destination.is_dir()
    assert (destination / "CMakeLists.txt").is_file()
    assert staging_entries(parent) == []


# ---------------------------------------------------------------------------
# destination refusals
# ---------------------------------------------------------------------------


def test_nonempty_destination_is_rejected_and_untouched(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "occupied"
    destination.mkdir()
    (destination / "keep.txt").write_text("user content\n", encoding="utf-8")

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert caught.value.code == "DELIVERY_DESTINATION_EXISTS"
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "user content\n"
    assert sorted(entry.name for entry in destination.iterdir()) == ["keep.txt"]


@pytest.mark.parametrize("destination_kind", ["same", "inside-source", "contains-source"])
def test_source_destination_overlap_is_rejected(
    tmp_path: Path, destination_kind: str
) -> None:
    repo = make_repo(tmp_path)
    destination = {
        "same": repo,
        "inside-source": repo / "generated-output",
        "contains-source": repo.parent,
    }[destination_kind]

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert caught.value.code == "DELIVERY_SOURCE_DESTINATION_OVERLAP"
    assert not (repo / "generated-output").exists()


def test_relative_and_missing_parent_destinations_are_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    inspection = inspect_keil(repo)

    with pytest.raises(MigrationPlanError) as relative:
        plan_keil_delivery(repo, Path("relative-output"), inspection)
    assert relative.value.code == "DELIVERY_DESTINATION_INVALID"
    assert relative.value.details["rule"] == "absolute"

    missing = tmp_path / "missing-parent" / "project"
    with pytest.raises(MigrationPlanError) as absent_parent:
        plan_keil_delivery(repo, missing, inspection)
    assert absent_parent.value.code == "DELIVERY_DESTINATION_INVALID"
    assert absent_parent.value.details["rule"] == "parent"
    assert not missing.exists()


# ---------------------------------------------------------------------------
# links/reparse points and casefold collisions
# ---------------------------------------------------------------------------


def _scandir_with_extra(path: Path, extra_name: str, extra_path: str):
    real_scandir = os.scandir

    expected = os.path.normcase(os.path.abspath(os.fspath(path)))

    @contextmanager
    def fake_scandir(directory):
        with real_scandir(directory) as iterator:
            entries = list(iterator)
        if os.path.normcase(os.path.abspath(os.fspath(directory))) == expected:
            entries.append(SimpleNamespace(name=extra_name, path=extra_path))
        yield iter(entries)

    return fake_scandir


def _fake_lstat(monkeypatch, link_path: Path, directory: bool = False) -> None:
    real_lstat = os.lstat
    mode = (stat.S_IFDIR if directory else stat.S_IFLNK) | 0o777
    target = os.path.normcase(os.path.abspath(os.fspath(link_path)))

    def fake_lstat(path, *args, **kwargs):
        if os.path.normcase(os.path.abspath(os.fspath(path))) == target:
            return SimpleNamespace(st_mode=mode, st_file_attributes=0)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", fake_lstat)


def test_source_links_and_reparse_points_are_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    inspection = inspect_keil(repo)
    assets = repo / "Assets"
    assets.mkdir()
    link = assets / "linked.txt"
    monkeypatch.setattr(
        os,
        "scandir",
        _scandir_with_extra(assets, link.name, str(link)),
    )
    _fake_lstat(monkeypatch, link)

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(
            repo, output_parent(tmp_path) / "project", inspection
        )
    assert caught.value.code == "DELIVERY_LINK_UNSUPPORTED"
    assert caught.value.details["path"] == "Assets/linked.txt"


def test_destination_reparse_point_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "redirected"
    _fake_lstat(monkeypatch, destination)

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert caught.value.code == "DELIVERY_DESTINATION_INVALID"
    assert caught.value.details["rule"] == "link"


def test_casefold_colliding_output_names_are_rejected(tmp_path: Path) -> None:
    # A source directory whose spelling case-folds onto a generated target is
    # a real collision on case-insensitive filesystems; it is refused before
    # any write instead of silently merging the two paths.
    repo = make_repo(tmp_path)
    (repo / ".VSCODE").mkdir()
    (repo / ".VSCODE" / "settings.json").write_text(
        "{}\n", encoding="utf-8"
    )
    inspection = inspect_keil(repo)

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(
            repo, output_parent(tmp_path) / "project", inspection
        )
    assert caught.value.code == "DELIVERY_CASEFOLD_COLLISION"
    assert caught.value.details["scope"] == "output"
    assert {
        caught.value.details["path"],
        caught.value.details["collision"],
    } == {".VSCODE/settings.json", ".vscode/settings.json"}


def test_inventory_limits_are_reported_not_silently_truncated(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    inspection = inspect_keil(repo)
    destination = output_parent(tmp_path) / "project"

    monkeypatch.setattr(delivery, "_FILE_LIMIT_BYTES", 8)
    with pytest.raises(MigrationPlanError) as file_limit:
        plan_keil_delivery(repo, destination, inspection)
    assert file_limit.value.code == "DELIVERY_LIMIT_EXCEEDED"
    assert file_limit.value.details["scope"] == "file"

    monkeypatch.setattr(delivery, "_FILE_LIMIT_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(delivery, "_MAX_DEPTH", 1)
    with pytest.raises(MigrationPlanError) as depth_limit:
        plan_keil_delivery(repo, destination, inspection)
    assert depth_limit.value.code == "DELIVERY_LIMIT_EXCEEDED"
    assert depth_limit.value.details["scope"] == "depth"

    monkeypatch.setattr(delivery, "_MAX_DEPTH", 64)
    monkeypatch.setattr(delivery, "_AGGREGATE_LIMIT_BYTES", 32)
    with pytest.raises(MigrationPlanError) as aggregate_limit:
        plan_keil_delivery(repo, destination, inspection)
    assert aggregate_limit.value.code == "DELIVERY_LIMIT_EXCEEDED"
    assert aggregate_limit.value.details["scope"] == "aggregate"
    assert not destination.exists()


# ---------------------------------------------------------------------------
# apply guards, drift, and cleanup
# ---------------------------------------------------------------------------


def test_apply_requires_authorization_and_exact_plan_id(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    unconfirmed = apply_keil_delivery(plan)
    assert unconfirmed.ok is False
    assert unconfirmed.code == "DELIVERY_NOT_AUTHORIZED"
    wrong = apply_keil_delivery(plan, authorized=True, plan_id="0" * 64)
    assert wrong.ok is False
    assert wrong.code == "DELIVERY_PLAN_ID_MISMATCH"
    made_up = apply_keil_delivery(plan, authorized=True, plan_id="not-a-digest")
    assert made_up.ok is False
    assert made_up.code == "DELIVERY_PLAN_ID_MISMATCH"
    assert not destination.exists()
    assert staging_entries(parent) == []


def test_source_change_after_plan_invalidates_apply(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    (repo / "Main" / "main.c").write_text(
        MAIN_C + "\n/* concurrent edit */\n", encoding="utf-8"
    )
    changed = tree_digest(repo)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_SOURCE_CHANGED"
    assert not destination.exists()
    assert staging_entries(parent) == []
    assert tree_digest(repo) == changed


def test_copied_header_change_after_plan_invalidates_apply(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    header = repo / "Common" / "private" / "unlisted_header.h"
    header.write_text(
        "#pragma once\n#define PRIVATE_VALUE 4\n", encoding="utf-8"
    )
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_SOURCE_CHANGED"
    assert not destination.exists()
    assert staging_entries(parent) == []


def test_empty_destination_state_change_is_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    destination.mkdir()
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert plan.destination_state == "empty"

    intruder = destination / "intruder.txt"
    intruder.write_text("keep me\n", encoding="utf-8")
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_DESTINATION_CHANGED"
    assert intruder.read_text(encoding="utf-8") == "keep me\n"
    assert sorted(entry.name for entry in destination.iterdir()) == [
        "intruder.txt"
    ]
    assert staging_entries(parent) == []


def test_publish_failure_cleans_only_owned_staging(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    before = tree_digest(repo)
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    def failing_replace(source, target):
        raise OSError("simulated publish failure")

    monkeypatch.setattr(delivery.os, "replace", failing_replace)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_APPLY_FAILED"
    assert result.details["phase"] == "publish"
    assert result.details["stagingRemoved"] is True
    assert not destination.exists()
    assert staging_entries(parent) == []
    assert tree_digest(repo) == before


def test_publish_failure_restores_originally_empty_destination(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    destination.mkdir()
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    assert plan.destination_state == "empty"

    def failing_replace(source, target):
        raise OSError("simulated publish failure")

    monkeypatch.setattr(delivery.os, "replace", failing_replace)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_APPLY_FAILED"
    assert result.details["phase"] == "publish"
    assert result.details["stagingRemoved"] is True
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert staging_entries(parent) == []


def test_replaced_staging_is_never_deleted_or_published(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    before = tree_digest(repo)
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    real_stage = delivery._stage_outputs
    replacement_marker = "replacement-owner-content\n"

    def stage_then_replace(staging, outputs, directories):
        real_stage(staging, outputs, directories)
        shutil.rmtree(staging)
        staging.mkdir()
        (staging / "replacement.txt").write_text(
            replacement_marker, encoding="utf-8"
        )

    monkeypatch.setattr(delivery, "_stage_outputs", stage_then_replace)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_STAGING_CHANGED"
    assert result.details["stagingRemoved"] is False
    assert result.details["cleanup"] == "skipped-replaced"
    assert not destination.exists()
    assert tree_digest(repo) == before
    remaining = staging_entries(parent)
    assert len(remaining) == 1
    assert (remaining[0] / "replacement.txt").read_text(
        encoding="utf-8"
    ) == replacement_marker


def test_redirected_staging_is_neither_deleted_nor_published(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    staging = parent / f".{destination.name}.stm32tk-staging-{plan.plan_id[:12]}"

    real_stage = delivery._stage_outputs
    real_lstat = os.lstat
    armed = {"value": False}

    def stage_then_arm(staging_path, outputs, directories):
        real_stage(staging_path, outputs, directories)
        armed["value"] = True

    def redirected_lstat(path, *args, **kwargs):
        state = real_lstat(path, *args, **kwargs)
        if armed["value"] and os.path.normcase(
            os.path.abspath(os.fspath(path))
        ) == os.path.normcase(os.path.abspath(os.fspath(staging))):
            return SimpleNamespace(
                st_mode=state.st_mode,
                st_dev=state.st_dev,
                st_ino=state.st_ino,
                st_file_attributes=0x400,
            )
        return state

    monkeypatch.setattr(delivery, "_stage_outputs", stage_then_arm)
    monkeypatch.setattr(os, "lstat", redirected_lstat)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_STAGING_CHANGED"
    assert result.details["stagingRemoved"] is False
    assert result.details["cleanup"] == "skipped-replaced"
    assert staging.is_dir()
    assert not destination.exists()


def test_unexpected_staged_content_is_refused_before_publication(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    before = tree_digest(repo)
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    real_stage = delivery._stage_outputs

    def stage_with_extra(staging, outputs, directories):
        real_stage(staging, outputs, directories)
        (staging / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    monkeypatch.setattr(delivery, "_stage_outputs", stage_with_extra)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_APPLY_FAILED"
    assert result.details["phase"] == "stage"
    assert result.details["stagingRemoved"] is True
    assert not destination.exists()
    assert staging_entries(parent) == []
    assert tree_digest(repo) == before


def test_final_output_limit_overflow_is_refused_at_planning(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path, "limits")
    baseline = plan_keil_delivery(
        repo, parent / "baseline", inspect_keil(repo)
    )
    before = tree_digest(repo)

    # The source passes at exactly this file count, but the final output adds
    # generated files beyond it.
    monkeypatch.setattr(delivery, "_MAX_FILES", baseline.source_file_count)
    rejected = parent / "rejected"
    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(repo, rejected, inspect_keil(repo))
    assert caught.value.code == "DELIVERY_LIMIT_EXCEEDED"
    assert caught.value.details["scope"] == "output-files"
    assert not rejected.exists()
    assert tree_digest(repo) == before


def test_source_removed_during_stage_is_reported_and_cleaned(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    real_stage = delivery._stage_outputs

    def stage_then_remove_source(staging, outputs, directories):
        real_stage(staging, outputs, directories)
        shutil.rmtree(repo)

    monkeypatch.setattr(delivery, "_stage_outputs", stage_then_remove_source)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_SOURCE_CHANGED"
    assert result.details["stagingRemoved"] is True
    assert result.details["cleanup"] == "removed"
    assert not destination.exists()
    assert staging_entries(parent) == []


def test_unreadable_source_during_stage_preserves_path_diagnostic(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    real_stage = delivery._stage_outputs
    real_scan = delivery._scan_tree
    armed = {"value": False}

    def stage_then_arm(staging, outputs, directories):
        real_stage(staging, outputs, directories)
        armed["value"] = True

    def scan_with_unreadable_source(root, **kwargs):
        if armed["value"] and os.path.normcase(os.fspath(root)) == os.path.normcase(
            os.fspath(repo)
        ):
            raise MigrationPlanError(
                "DELIVERY_SOURCE_INVALID",
                "source file is unreadable",
                {"path": "Main/main.c", "rule": "unreadable"},
            )
        return real_scan(root, **kwargs)

    monkeypatch.setattr(delivery, "_stage_outputs", stage_then_arm)
    monkeypatch.setattr(delivery, "_scan_tree", scan_with_unreadable_source)
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_SOURCE_CHANGED"
    assert result.details["path"] == "Main/main.c"
    assert result.details["cause"] == "DELIVERY_SOURCE_INVALID"
    assert result.details["stagingRemoved"] is True
    assert not destination.exists()


@pytest.mark.parametrize(
    "forged",
    ["planVersion", "outputs", "directories", "patches", "size"],
)
def test_mutated_preview_plan_is_rejected_before_staging(
    tmp_path: Path, forged: str
) -> None:
    repo = make_repo(tmp_path)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    if forged == "planVersion":
        mutated = replace(plan, plan_version=True)
    elif forged == "outputs":
        mutated = replace(plan, outputs=plan.outputs[:-1])
    elif forged == "directories":
        mutated = replace(
            plan, output_directories=plan.output_directories + ("forged-dir",)
        )
    elif forged == "patches":
        mutated = replace(plan, source_patches=())
    else:
        mutated = replace(
            plan,
            outputs=(replace(plan.outputs[0], size=True),) + plan.outputs[1:],
        )
    assert mutated.plan_id == plan.plan_id

    result = apply_authorized(mutated)
    expected_code = (
        "DELIVERY_PLAN_INVALID"
        if forged in ("planVersion", "size")
        else "DELIVERY_PLAN_CHANGED"
    )
    assert result.ok is False
    assert result.code == expected_code
    assert not destination.exists()
    assert staging_entries(parent) == []


# ---------------------------------------------------------------------------
# explicit generated/copied collisions
# ---------------------------------------------------------------------------


def test_generated_collision_with_copied_source_is_explicit(tmp_path: Path) -> None:
    files = _default_files()
    user_cmake = "# user-owned CMake file in the Keil source tree\n"
    files["CMakeLists.txt"] = user_cmake
    repo = make_repo(tmp_path, files=files)
    parent = output_parent(tmp_path)
    destination = parent / "project"
    before = tree_digest(repo)
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))

    entry = _preview_by_path(plan)["CMakeLists.txt"]
    assert entry["kind"] == "replaced"
    assert entry["collision"] is True
    assert entry["beforeSha256"] == sha256(user_cmake.encode("utf-8"))
    assert entry["binary"] is False
    assert entry["unifiedDiff"]

    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    assert (destination / "CMakeLists.txt").read_text(encoding="utf-8") != user_cmake
    assert (repo / "CMakeLists.txt").read_text(encoding="utf-8") == user_cmake
    assert tree_digest(repo) == before


# ---------------------------------------------------------------------------
# report schema 1/2 decoding in the normal configure route
# ---------------------------------------------------------------------------


def _delivered(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    destination = output_parent(tmp_path) / "project"
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    return destination


def _write_report(root: Path, payload: dict[str, object]) -> None:
    (root / REPORT_PATH).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _report(root: Path) -> dict[str, object]:
    return json.loads((root / REPORT_PATH).read_text(encoding="utf-8"))


def test_schema2_report_requires_content_identity(tmp_path: Path) -> None:
    root = _delivered(tmp_path)
    payload = _report(root)

    without_snapshot = dict(payload)
    without_snapshot.pop("sourceSnapshotSha256")
    _write_report(root, without_snapshot)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "sourceSnapshotSha256"

    bad_content = dict(payload)
    bad_content["contentId"] = "not-a-digest"
    _write_report(root, bad_content)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "contentId"


def test_schema_version_must_be_a_strict_int(tmp_path: Path) -> None:
    root = _delivered(tmp_path)
    payload = _report(root)
    payload["schemaVersion"] = True  # bool would masquerade as 1
    _write_report(root, payload)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "schemaVersion"


def test_schema1_report_remains_strict_about_git_head(tmp_path: Path) -> None:
    root = _delivered(tmp_path)
    payload = _report(root)
    # Schema 1 keeps its original explicit planId contract; the schema-2
    # content identity is ignored historical data there.
    payload["planId"] = payload["contentId"]
    payload["schemaVersion"] = 1
    payload["gitHead"] = "0" * 40
    _write_report(root, payload)
    configuration = plan_project_configuration(load_project_model(root))
    assert configuration.blockers == ()

    payload.pop("gitHead")
    _write_report(root, payload)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "gitHead"


def test_unknown_report_schema_is_rejected(tmp_path: Path) -> None:
    root = _delivered(tmp_path)
    payload = _report(root)
    payload["schemaVersion"] = 99
    _write_report(root, payload)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "schemaVersion"


def test_post_migration_extra_region_adjustment_is_allowed(tmp_path: Path) -> None:
    # The report's migration-time extra region is historical evidence.  A
    # later legitimate owner adjustment to the manifest memory must configure
    # without rewriting the historical report or its digests.
    root = _delivered(tmp_path)

    def add_owner_ram(payload: dict) -> None:
        payload["memory"]["extraRegions"] = [
            {
                "name": "EXT_SRAM",
                "origin": 0x68000000,
                "length": 0x10000,
                "attributes": "rw-",
            }
        ]
        payload["memory"]["layout"] = {
            "flash": "IROM1",
            "data": "IRAM1",
            "bss": "IRAM1",
            "heap": "IRAM1",
            "stack": "IRAM1",
        }

    edit_manifest(root, add_owner_ram)
    configuration = plan_project_configuration(load_project_model(root))
    assert configuration.blockers == ()
    assert "EXT_SRAM" in configuration.model.memory.extra_region_names


def test_current_fixed_section_layout_must_contain_sections(tmp_path: Path) -> None:
    # Current validated memory remains authoritative for fixed-section
    # containment even though the historical report is unchanged.
    root = _delivered(tmp_path)

    def move_ram(payload: dict) -> None:
        for region in payload["memory"]["regions"]:
            if region["name"] == "IRAM1":
                region["origin"] = 0x20010000
                region["length"] = 0x1000

    edit_manifest(root, move_ram)
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(root))
    assert caught.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert caught.value.details["rule"] == "region"


def test_render_seam_matches_normal_configure_bytes(tmp_path: Path) -> None:
    root = _delivered(tmp_path)
    manifest_bytes = (root / ".stm32-project.json").read_bytes()
    report_bytes = (root / REPORT_PATH).read_bytes()
    rendered = render_new_project_configuration(
        root, manifest_bytes, conversion_report_bytes=report_bytes
    )
    configuration = plan_project_configuration(load_project_model(root))
    assert rendered.managed_manifest_bytes == configuration.managed_manifest_bytes
    assert {entry.path: entry.after_bytes for entry in rendered.files} == {
        entry.path: entry.after_bytes
        for entry in configuration.files
        if entry.status != "preserved-unowned"
    }


# ---------------------------------------------------------------------------
# real GCC evidence: isolated output-only relocation
# ---------------------------------------------------------------------------


def _require_tool(base: Path, name: str) -> str:
    candidates = [base / f"{name}.exe", base / name]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise AssertionError(f"required offline ARM GNU tool {name!r} was not found in {base}")


def _startup_source_repo(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path,
        name="startup-source",
        files={"Main/main.c": STARTUP_MAIN_C, STARTUP_SOURCE: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")',
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup_synthetic.s", "2", STARTUP_SOURCE),)),
            ),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


def test_real_gcc_builds_output_only_relocation(tmp_path: Path) -> None:
    gcc = _require_tool(GNU_BIN, "arm-none-eabi-gcc")
    cmake = _require_tool(CMAKE_BIN, "cmake")
    _require_tool(NINJA_BIN, "ninja")
    assert Path(gcc).is_file()

    repo = _startup_source_repo(tmp_path)
    assert not (repo / ".git").exists()
    output_root = output_parent(tmp_path, "delivery") / "gcc-project"
    plan = plan_keil_delivery(
        repo,
        output_root,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    # Configuration is not build or flash evidence.
    assert result.data["built"] is False
    assert result.data["flashed"] is False

    source_text = os.path.normcase(str(repo))
    staging_marker = ".stm32tk-staging-"
    for path in output_root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            continue
        text = os.path.normcase(data.decode("utf-8", "replace"))
        assert source_text not in text, path
        assert staging_marker not in text, path

    # Copy ONLY the output to an isolated directory, then make the original
    # source path unavailable before any compilation happens.
    relocated = tmp_path / "isolated" / "project"
    relocated.parent.mkdir()
    shutil.copytree(output_root, relocated)
    shutil.rmtree(repo)
    assert not repo.exists()

    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        [str(GNU_BIN), str(CMAKE_BIN), str(NINJA_BIN), environment.get("PATH", "")]
    )

    def run(*arguments: str) -> None:
        completed = subprocess.run(
            [cmake, *arguments],
            cwd=relocated,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert completed.returncode == 0, (
            "command failed: " + " ".join(arguments) + "\n"
            + completed.stdout + "\n" + completed.stderr
        )

    run("--preset", "arm-debug")
    run("--build", "--preset", "arm-debug")

    manifest = json.loads(
        (relocated / ".stm32-project.json").read_text(encoding="utf-8")
    )
    elf = relocated.joinpath(*manifest["build"]["elf"].split("/"))
    assert elf.is_file()
    assert elf.stat().st_size > 0
    assert elf.read_bytes()[:4] == b"\x7fELF"
    cache = (relocated / "build" / "arm-debug" / "CMakeCache.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    normalized_cache = os.path.normcase(cache.replace("/", os.sep))
    # The generated toolchain selected the verified ARM GNU compiler that the
    # test placed first on PATH (never a host-default or fake compiler).
    assert "arm-none-eabi-gcc" in normalized_cache
