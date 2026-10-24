"""Keil migration preflight/plan/apply behavior for explicit memory layouts."""

from __future__ import annotations

import json

import pytest

from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.migration import (
    MigrationPlanError,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.migration.startup import StartupOptions

from startup_gcc_fixture import (
    MAIN_C,
    STARTUP_SOURCE,
    SYNTHETIC_STARTUP,
)
from test_migration_plan import FRAMEWORK_INCLUDE, build_repo

MULTI_CPU = (
    'IROM(0x8000000,0x100000) IRAM(0x20000000,0x30000) '
    'IRAM2(0x10000000,0x10000) CPUTYPE("Cortex-M4")'
)

ALL_MAIN = MemoryLayout(
    flash="IROM1", data="IRAM1", bss="IRAM1", heap="IRAM1", stack="IRAM1"
)
SPLIT = MemoryLayout(
    flash="IROM1", data="IRAM1", bss="IRAM2", heap="IRAM2", stack="IRAM2"
)
STARTUP = StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE)


def multi_ram_repo(
    tmp_path, *, name: str = "memory-layout-project", main: str = MAIN_C
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.c": main, STARTUP_SOURCE: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": MULTI_CPU,
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup_synthetic.s", "2", STARTUP_SOURCE),)),
            ),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


def single_ram_repo(tmp_path, *, name: str = "single-ram-project"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.c": MAIN_C, STARTUP_SOURCE: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": (
                'IROM(0x8000000,0x100000) IRAM(0x20000000,0x30000) '
                'CPUTYPE("Cortex-M4")'
            ),
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup_synthetic.s", "2", STARTUP_SOURCE),)),
            ),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


def manifest_payload(plan) -> dict:
    patch = next(
        entry for entry in plan.patches if entry.path == ".stm32-project.json"
    )
    return json.loads(patch.after_bytes.decode("utf-8"))


def test_preflight_requires_selection_and_reports_actual_candidates(tmp_path):
    repo = multi_ram_repo(tmp_path)
    preflight = preflight_keil_conversion(
        repo, inspect_keil(repo), startup_options=STARTUP
    )
    analysis = preflight["analysis"]
    layout = analysis["memoryLayout"]
    assert layout["status"] == "requires-selection"
    assert layout["layout"] is None
    assert [entry["name"] for entry in layout["candidates"]["flash"]] == ["IROM1"]
    assert [entry["name"] for entry in layout["candidates"]["ram"]] == [
        "IRAM1",
        "IRAM2",
    ]
    assert layout["candidates"]["ram"][1] == {
        "name": "IRAM2",
        "origin": 0x10000000,
        "length": 0x10000,
        "attributes": "rwx",
    }
    layout_blockers = [
        blocker
        for blocker in analysis["blockers"]
        if blocker["code"] == "MEMORY_LAYOUT_REQUIRED"
    ]
    assert len(layout_blockers) == 1
    assert layout_blockers[0]["evidence"] == "data,bss,heap,stack"
    assert preflight["planReadiness"]["ready"] is False


def test_absent_layout_aggregates_with_other_migration_blockers(tmp_path):
    repo = multi_ram_repo(tmp_path)
    preflight = preflight_keil_conversion(
        repo, inspect_keil(repo)
    )
    codes = {blocker["code"] for blocker in preflight["analysis"]["blockers"]}
    assert "MEMORY_LAYOUT_REQUIRED" in codes
    # Omitting the startup strategy leaves the ordinary assembly blocker too;
    # the layout decision must not short-circuit the rest of the analysis.
    assert "ARMCC_ASSEMBLY_UNSUPPORTED" in codes


def test_plan_binds_the_exact_explicit_layout_into_identity_and_manifest(tmp_path):
    repo = multi_ram_repo(tmp_path / "plan")
    inspection = inspect_keil(repo)

    first = plan_keil_conversion(
        repo, inspection, startup_options=STARTUP, memory_layout=ALL_MAIN
    )
    second = plan_keil_conversion(
        repo, inspection, startup_options=STARTUP, memory_layout=ALL_MAIN
    )
    assert first.plan_id == second.plan_id
    assert first.memory_layout == ALL_MAIN
    assert first.memory_layout_resolution is not None
    assert first.memory_layout_resolution.status == "explicit"
    exposed = first.to_dict()["memory_layout"]
    assert exposed["status"] == "explicit"
    assert exposed["layout"] == ALL_MAIN.to_dict()
    assert exposed["candidates"]["flash"][0]["name"] == "IROM1"
    assert "MEMORY_LAYOUT_REQUIRED" not in {b.code for b in first.blockers}

    payload = manifest_payload(first)
    assert payload["memory"]["layout"] == ALL_MAIN.to_dict()
    assert payload["memory"]["stackSize"] == 0x1000
    assert payload["memory"]["heapSize"] == 0x400

    split = plan_keil_conversion(
        repo, inspection, startup_options=STARTUP, memory_layout=SPLIT
    )
    assert split.plan_id != first.plan_id
    assert manifest_payload(split)["memory"]["layout"] == SPLIT.to_dict()


def test_plan_exposes_required_candidates_without_a_layout(tmp_path):
    repo = multi_ram_repo(tmp_path / "required")
    plan = plan_keil_conversion(
        repo, inspect_keil(repo), startup_options=STARTUP
    )
    exposed = plan.to_dict()["memory_layout"]
    assert exposed["status"] == "requires-selection"
    assert exposed["layout"] is None
    assert [entry["name"] for entry in exposed["candidates"]["ram"]] == [
        "IRAM1",
        "IRAM2",
    ]
    assert "MEMORY_LAYOUT_REQUIRED" in {blocker.code for blocker in plan.blockers}
    assert manifest_payload(plan)["memory"].get("layout") is None


def test_invalid_explicit_layouts_are_rejected_before_planning(tmp_path):
    repo = multi_ram_repo(tmp_path / "invalid")
    inspection = inspect_keil(repo)
    cases = [
        (
            MemoryLayout("IROM1", "MISSING", "IRAM1", "IRAM1", "IRAM1"),
            "memory.layout.data",
            "unknownRegion",
        ),
        (
            MemoryLayout("IRAM1", "IRAM1", "IRAM1", "IRAM1", "IRAM1"),
            "memory.layout.flash",
            "access",
        ),
        (
            MemoryLayout("IROM1", "IROM1", "IRAM1", "IRAM1", "IRAM1"),
            "memory.layout.data",
            "access",
        ),
    ]
    for layout, field, rule in cases:
        with pytest.raises(MigrationPlanError) as error:
            plan_keil_conversion(
                repo, inspection, startup_options=STARTUP, memory_layout=layout
            )
        assert error.value.code == "MEMORY_LAYOUT_INVALID"
        assert error.value.details["field"] == field
        assert error.value.details["rule"] == rule
        assert "remediation" in error.value.details


def test_implicit_single_ram_keeps_legacy_manifest_bytes_and_identity(tmp_path):
    repo = single_ram_repo(tmp_path / "implicit")
    inspection = inspect_keil(repo)
    first = plan_keil_conversion(repo, inspection, startup_options=STARTUP)
    second = plan_keil_conversion(repo, inspection, startup_options=STARTUP)
    assert first.plan_id == second.plan_id
    assert first.memory_layout is None
    assert first.memory_layout_resolution is not None
    exposed = first.to_dict()["memory_layout"]
    assert exposed["status"] == "implicit"
    assert exposed["layout"] == {
        "flash": "IROM1",
        "data": "IRAM1",
        "bss": "IRAM1",
        "heap": "IRAM1",
        "stack": "IRAM1",
    }
    payload = manifest_payload(first)
    assert "layout" not in payload["memory"]

    explicit = plan_keil_conversion(
        repo,
        inspection,
        startup_options=STARTUP,
        memory_layout=MemoryLayout(
            "IROM1", "IRAM1", "IRAM1", "IRAM1", "IRAM1"
        ),
    )
    assert explicit.plan_id != first.plan_id
    assert manifest_payload(explicit)["memory"]["layout"] == {
        "flash": "IROM1",
        "data": "IRAM1",
        "bss": "IRAM1",
        "heap": "IRAM1",
        "stack": "IRAM1",
    }


def test_macro_absolute_placement_resolves_from_a_source_define(tmp_path):
    main = (
        "#define BASE_ADDRESS 0x20000000\n"
        "__attribute__((at(BASE_ADDRESS + 0x100))) volatile unsigned int fixed_value;\n"
        "void SystemInit(void) {}\n"
        "int main(void) { return fixed_value; }\n"
    )
    repo = multi_ram_repo(tmp_path / "absolute", main=main)
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=STARTUP,
        memory_layout=ALL_MAIN,
    )
    codes = {blocker.code for blocker in plan.blockers}
    assert "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED" not in codes
    # The bounded evaluator resolves the in-file object-like define; the
    # fixed address is still constrained by the declared memory regions.
    assert [section.address for section in plan.fixed_sections] == [0x20000100]
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    assert (
        b'__attribute__((section(".stm32tk.abs.20000100"), used)) '
        b"volatile unsigned int fixed_value;" in patch.after_bytes
    )
