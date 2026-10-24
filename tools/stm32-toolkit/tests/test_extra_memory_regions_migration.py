"""Public migration preflight/PLAN/APPLY behavior for explicit external RAM.

The 0x68000000/0x10000 capacity is a synthetic test value, not a board fact.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.migration import (
    MigrationPlanError,
    apply_keil_conversion,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES
from stm32_toolkit.workflows import convert_keil_workflow, preflight_keil_workflow

from startup_gcc_fixture import STARTUP_SOURCE, SYNTHETIC_STARTUP, TARGET, UVPROJX
from test_memory_layout_migration import STARTUP
from test_migration_plan import FRAMEWORK_INCLUDE, build_repo

CPU = 'IROM(0x08000000,0x100000) IRAM(0x20000000,0x30000) CPUTYPE("Cortex-M4")'
EXT = ExtraRegion("EXT_SRAM", 0x68000000, 0x10000, "rw-")
EXT_DICT = EXT.to_dict()
ALL_MAIN = MemoryLayout("IROM1", "IRAM1", "IRAM1", "IRAM1", "IRAM1")
EXT_LAYOUT = MemoryLayout("IROM1", "IRAM1", "EXT_SRAM", "EXT_SRAM", "EXT_SRAM")
EXT_BUFFER_C = (
    "/* Synthetic external-RAM fixed buffer: no vendor code. */\n"
    "__attribute__((at(0x68000010))) volatile unsigned int extra_buffer;\n"
    "volatile unsigned int initialized_value = 0x12345678u;\n"
    "volatile unsigned int zeroed_value;\n"
    "\n"
    "void SystemInit(void) {}\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "    return (int)(extra_buffer + initialized_value + zeroed_value);\n"
    "}\n"
)
STARTUP_ARGS = ["--startup-strategy", "generate-cmsis-gcc", "--startup-source", STARTUP_SOURCE]


def extra_repo(
    tmp_path, *, name: str = "extra-project", commit: bool = True
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.c": EXT_BUFFER_C, STARTUP_SOURCE: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": CPU,
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup_synthetic.s", "2", STARTUP_SOURCE),)),
            ),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
        commit=commit,
    )


def _plan(repo, *, extras=(EXT,), layout=EXT_LAYOUT):
    return plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=STARTUP,
        memory_layout=layout,
        extra_regions=extras,
    )


def _manifest_payload(plan) -> dict:
    patch = next(
        entry for entry in plan.patches if entry.path == ".stm32-project.json"
    )
    return json.loads(patch.after_bytes.decode("utf-8"))


def test_plan_and_apply_accept_a_layout_role_in_external_ram(tmp_path):
    repo = extra_repo(tmp_path / "layout")
    plan = _plan(repo)
    assert plan.extra_regions == (EXT,)
    exposed = plan.to_dict()["extra_regions"]
    assert exposed == [EXT_DICT]
    assert plan.memory_layout_resolution.status == "explicit"
    resolution = plan.to_dict()["memory_layout"]
    assert [item["name"] for item in resolution["candidates"]["ram"]] == [
        "IRAM1",
        "EXT_SRAM",
    ]
    assert [item["name"] for item in resolution["candidates"]["flash"]] == ["IROM1"]
    assert "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY" not in {
        blocker.code for blocker in plan.blockers
    }

    payload = _manifest_payload(plan)
    # The inspected Keil base list is preserved byte-for-byte in shape; the
    # explicit region is added separately.
    assert payload["memory"]["regions"] == [
        {"name": "IROM1", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "IRAM1", "origin": 0x20000000, "length": 0x30000, "attributes": "rwx"},
    ]
    assert payload["memory"]["extraRegions"] == [EXT_DICT]
    assert payload["memory"]["layout"] == EXT_LAYOUT.to_dict()

    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    manifest = json.loads((repo / ".stm32-project.json").read_text("utf-8"))
    assert manifest["memory"]["regions"] == payload["memory"]["regions"]
    assert manifest["memory"]["extraRegions"] == [EXT_DICT]
    report = json.loads(
        (repo / "artifacts/migration/conversion-report.json").read_text("utf-8")
    )
    assert report["extraRegions"] == [EXT_DICT]
    assert report["planId"] == plan.plan_id
    assert report["fixedSections"] == [
        {
            "section": ".stm32tk.abs.68000010",
            "address": 0x68000010,
            "sourcePath": "Main/main.c",
            "line": 2,
            "symbol": "extra_buffer",
        }
    ]


def test_preflight_exposes_extra_regions_and_retains_the_exact_request(tmp_path):
    repo = extra_repo(tmp_path / "preflight")
    data = preflight_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=STARTUP,
        memory_layout=EXT_LAYOUT,
        extra_regions=(EXT,),
    )
    assert data["analysis"]["extraRegions"] == [EXT_DICT]
    assert data["analysis"]["memoryLayout"]["candidates"]["ram"][1]["name"] == (
        "EXT_SRAM"
    )
    guidance = " ".join(data["planReadiness"]["nextSteps"])
    assert "Retain extraRegions=" in guidance
    assert json.dumps([EXT_DICT], sort_keys=True, separators=(",", ":")) in guidance
    assert "omitting or changing any entry" in guidance


def test_git_free_preflight_accepts_the_same_explicit_request(tmp_path):
    repo = extra_repo(tmp_path / "gitfree", commit=False)
    assert not (repo / ".git").exists()
    data = preflight_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
        memory_layout=EXT_LAYOUT,
        extra_regions=[EXT_DICT],
    ).to_dict()
    assert data["ok"] is True, data
    assert data["data"]["analysis"]["extraRegions"] == [EXT_DICT]
    assert data["data"]["analysis"]["requiresGit"] is False
    # The fixture itself has no repository; even if an enclosing repository
    # were discovered, this project root cannot be its toplevel.
    assert data["data"]["git"]["head"]["available"] is False
    assert data["data"]["planReadiness"]["status"] == "blocked"


def test_omitted_and_explicit_empty_extras_are_the_same_request(tmp_path):
    repo = extra_repo(tmp_path / "empty-compat")
    inspection = inspect_keil(repo)
    omitted = plan_keil_conversion(repo, inspection, startup_options=STARTUP)
    empty = plan_keil_conversion(
        repo, inspection, startup_options=STARTUP, extra_regions=()
    )
    assert omitted.plan_id == empty.plan_id
    assert omitted.to_dict() == empty.to_dict()
    assert _manifest_payload(omitted) == _manifest_payload(empty)
    assert preflight_keil_conversion(
        repo, inspection, startup_options=STARTUP
    ) == preflight_keil_conversion(
        repo, inspection, startup_options=STARTUP, extra_regions=()
    )


def test_extra_ram_adds_a_candidate_and_never_places_data_implicitly(tmp_path):
    repo = extra_repo(tmp_path / "selection")
    data = preflight_keil_conversion(
        repo, inspect_keil(repo), startup_options=STARTUP, extra_regions=(EXT,)
    )
    layout = data["analysis"]["memoryLayout"]
    assert layout["status"] == "requires-selection"
    assert layout["layout"] is None
    assert [item["name"] for item in layout["candidates"]["ram"]] == [
        "IRAM1",
        "EXT_SRAM",
    ]
    assert [item["name"] for item in layout["candidates"]["flash"]] == ["IROM1"]
    assert [item["name"] for item in layout["candidates"]["flash"]] != ["EXT_SRAM"]
    codes = {blocker["code"] for blocker in data["analysis"]["blockers"]}
    assert "MEMORY_LAYOUT_REQUIRED" in codes


def test_fixed_section_outside_base_is_actionable_without_extras(tmp_path):
    repo = extra_repo(tmp_path / "outside")
    data = preflight_keil_conversion(repo, inspect_keil(repo), startup_options=STARTUP)
    blocker = next(
        entry
        for entry in data["analysis"]["blockers"]
        if entry["code"] == "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY"
    )
    assert blocker["remediation"]["category"] == "needs-user-input"
    assert blocker["remediation"]["tool"] == "stm32_keil_preflight"
    assert blocker["remediation"]["requiredInputs"] == ["extraRegions"]
    assert "never guesses a length" in blocker["remediation"]["summary"]
    assert "extraRegions" not in data["analysis"]

    with_extras = _plan(repo)
    assert "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY" not in {
        blocker.code for blocker in with_extras.blockers
    }


def test_no_extra_request_preserves_historical_fields_and_identity(tmp_path):
    repo = extra_repo(tmp_path / "legacy")
    inspection = inspect_keil(repo)
    first = plan_keil_conversion(repo, inspection, startup_options=STARTUP)
    second = plan_keil_conversion(repo, inspection, startup_options=STARTUP)
    assert first.plan_id == second.plan_id
    assert first.extra_regions == ()
    assert "extra_regions" not in first.to_dict()
    assert "extraRegions" not in _manifest_payload(first)["memory"]
    preflight = preflight_keil_conversion(repo, inspection, startup_options=STARTUP)
    assert "extraRegions" not in preflight["analysis"]
    assert "Retain extraRegions" not in " ".join(preflight["planReadiness"]["nextSteps"])

    with_extra = _plan(repo)
    assert with_extra.plan_id != first.plan_id


def test_omitted_and_changed_extras_are_never_accepted_against_a_reviewed_plan(
    tmp_path,
):
    repo = extra_repo(tmp_path / "stale")
    # The external layout role itself is covered by the explicit PLAN/APPLY
    # test above; here the base-only layout keeps omission/change diagnostic
    # deterministic (PLAN_CHANGED rather than an unknown-role layout error).
    plan = _plan(repo, layout=ALL_MAIN)
    base = dict(
        uvprojx=UVPROJX,
        target_name=TARGET,
        plan_id=plan.plan_id,
        authorized=True,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
        memory_layout=ALL_MAIN,
    )
    omitted = convert_keil_workflow(repo, **base).to_dict()
    assert omitted["ok"] is False and omitted["code"] == "PLAN_CHANGED"
    changed = convert_keil_workflow(
        repo,
        **base,
        extra_regions=[
            {**EXT_DICT, "origin": 0x68010000, "length": 0x8000}
        ],
    ).to_dict()
    assert changed["ok"] is False and changed["code"] == "PLAN_CHANGED"
    assert not (repo / ".stm32-project.json").exists()


def test_tampered_typed_plan_is_rejected_before_any_write(tmp_path):
    repo = extra_repo(tmp_path / "tampered")
    plan = _plan(repo)
    changed = replace(
        plan, extra_regions=(ExtraRegion("EXT_SRAM", 0x68000000, 0x8000, "rw-"),)
    )
    rejected = apply_keil_conversion(changed)
    assert rejected.ok is False
    assert rejected.code == "MIGRATION_PLAN_INVALID"
    assert rejected.details["rule"] == "planId"
    assert not (repo / ".stm32-project.json").exists()

    overlapping = replace(
        plan, extra_regions=(ExtraRegion("EXT_SRAM", 0x2002FFFF, 0x10000, "rw-"),)
    )
    rejected_overlap = apply_keil_conversion(overlapping)
    assert rejected_overlap.ok is False
    assert rejected_overlap.code == "MIGRATION_PLAN_INVALID"
    assert rejected_overlap.details["rule"] == "extraRegions"
    assert not (repo / ".stm32-project.json").exists()


def test_invalid_extra_regions_fail_before_planning(tmp_path):
    repo = extra_repo(tmp_path / "invalid")
    inspection = inspect_keil(repo)
    # A forged normalized-looking tuple is revalidated with exact field rules.
    cases = [
        (
            (ExtraRegion("EXT_SRAM", True, 0x10000, "rw-"),),
            "extraRegions[0].origin",
            "type",
        ),
        (
            (ExtraRegion("EXT_SRAM", 0x68000000, 0x10000, "r-x"),),
            "extraRegions[0].attributes",
            "attributes",
        ),
        (
            (ExtraRegion("EXT_SRAM", 0x2002FFFF, 0x10000, "rw-"),),
            "extraRegions[0]",
            "overlap",
        ),
    ]
    for extras, field, rule in cases:
        with pytest.raises(MigrationPlanError) as caught:
            plan_keil_conversion(
                repo,
                inspection,
                startup_options=STARTUP,
                memory_layout=EXT_LAYOUT,
                extra_regions=extras,
            )
        assert caught.value.code == "EXTRA_REGIONS_INVALID"
        assert caught.value.details["field"] == field
        assert caught.value.details["rule"] == rule
        assert "remediation" in caught.value.details
    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_conversion(repo, inspection, extra_regions=[EXT_DICT])
    assert caught.value.code == "EXTRA_REGIONS_INVALID"
    assert caught.value.details["rule"] == "type"


def test_cli_routes_the_exact_json_array_and_rejects_bad_grammar(tmp_path, capsys):
    repo = extra_repo(tmp_path / "cli")
    extras_text = json.dumps([EXT_DICT])
    arguments = [
        "keil",
        "preflight",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        *STARTUP_ARGS,
        "--memory-layout",
        json.dumps(EXT_LAYOUT.to_dict()),
        "--extra-regions",
        extras_text,
        "--json",
    ]
    assert cli_main(arguments) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["data"]["analysis"]["extraRegions"] == [EXT_DICT]

    duplicate = [
        "keil",
        "convert",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        "--extra-regions",
        extras_text,
        "--extra-regions",
        extras_text,
        "--dry-run",
        "--json",
    ]
    assert cli_main(duplicate) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "stm32-toolkit: invalid arguments\n"

    malformed = [
        "keil",
        "preflight",
        "--project",
        str(repo),
        "--uvprojx",
        "missing.uvprojx",
        "--target-name",
        TARGET,
        "--extra-regions",
        '[{"name":"A","origin":0,"origin":1,"length":1,"attributes":"rw-"}]',
        "--json",
    ]
    assert cli_main(malformed) != 0
    failure = json.loads(capsys.readouterr().out)
    assert failure["code"] == "EXTRA_REGIONS_INVALID"
    assert failure["details"]["field"] == "extraRegions"
    assert failure["details"]["rule"] == "duplicateKey"


def test_cli_plan_and_apply_require_the_same_extra_request(tmp_path, capsys):
    repo = extra_repo(tmp_path / "cli-apply")
    extras_text = json.dumps([EXT_DICT])
    layout_text = json.dumps(ALL_MAIN.to_dict())

    planned = [
        "keil",
        "convert",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        *STARTUP_ARGS,
        "--memory-layout",
        layout_text,
        "--extra-regions",
        extras_text,
        "--dry-run",
        "--json",
    ]
    assert cli_main(planned) == 0
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["plan_id"]

    def apply(*extra: str):
        return cli_main(
            [
                "keil",
                "convert",
                "--project",
                str(repo),
                "--uvprojx",
                UVPROJX,
                "--target-name",
                TARGET,
                *STARTUP_ARGS,
                "--memory-layout",
                layout_text,
                *extra,
                "--apply",
                "--plan-id",
                plan_id,
                "--authorized",
                "--json",
            ]
        )

    assert apply() != 0
    omitted = json.loads(capsys.readouterr().out)
    assert omitted["code"] == "PLAN_CHANGED"
    assert apply(
        "--extra-regions",
        json.dumps([{**EXT_DICT, "length": 0x8000}]),
    ) != 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["code"] == "PLAN_CHANGED"

    assert apply("--extra-regions", extras_text) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    manifest = json.loads((repo / ".stm32-project.json").read_text("utf-8"))
    assert manifest["memory"]["extraRegions"] == [EXT_DICT]
    assert [region["name"] for region in manifest["memory"]["regions"]] == [
        "IROM1",
        "IRAM1",
    ]


def test_registered_mcp_schema_and_calls_preserve_raw_scalar_values(tmp_path):
    repo = extra_repo(tmp_path / "mcp")
    server = mcp_mod.create_server(repo, tmp_path / "data", "session-extra-regions")
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == set(MCP_TOOL_NAMES.values())
    for name in ("stm32_keil_preflight", "stm32_keil_convert"):
        schema = tools[name].inputSchema["properties"]["extraRegions"]
        assert "array" in str(schema)
        assert "object" in str(schema)

    def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        _, structured = asyncio.run(server.call_tool(name, arguments))
        assert structured is not None
        return structured

    selection = {
        "uvprojx": UVPROJX,
        "targetName": TARGET,
        "startupStrategy": "generate-cmsis-gcc",
        "startupSource": STARTUP_SOURCE,
    }
    for bad_origin in (True, "0x68000000", 1.0):
        invalid = call(
            "stm32_keil_preflight",
            {**selection, "extraRegions": [{**EXT_DICT, "origin": bad_origin}]},
        )
        assert invalid["ok"] is False
        assert invalid["code"] == "EXTRA_REGIONS_INVALID"
        assert invalid["details"]["field"] == "extraRegions[0].origin"
        assert invalid["details"]["rule"] == "type"

    preflight = call(
        "stm32_keil_preflight",
        {**selection, "extraRegions": [EXT_DICT]},
    )
    assert preflight["ok"] is True
    assert preflight["data"]["analysis"]["extraRegions"] == [EXT_DICT]

    planned = call(
        "stm32_keil_convert",
        {
            **selection,
            "extraRegions": [EXT_DICT],
            "memoryLayout": EXT_LAYOUT.to_dict(),
        },
    )
    assert planned["ok"] is True
    assert planned["data"]["extra_regions"] == [EXT_DICT]
    plan_id = planned["data"]["plan_id"]
    applied = call(
        "stm32_keil_convert",
        {
            **selection,
            "extraRegions": [EXT_DICT],
            "memoryLayout": EXT_LAYOUT.to_dict(),
            "planId": plan_id,
            "authorized": True,
        },
    )
    assert applied["ok"] is True
    assert json.loads((repo / ".stm32-project.json").read_text("utf-8"))["memory"][
        "extraRegions"
    ] == [EXT_DICT]


def test_workflow_preflight_returns_structured_extra_failure(tmp_path):
    repo = extra_repo(tmp_path / "workflow")
    result = preflight_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        extra_regions=[{**EXT_DICT, "length": 0}],
    ).to_dict()
    assert result["ok"] is False
    assert result["code"] == "EXTRA_REGIONS_INVALID"
    assert result["details"]["field"] == "extraRegions[0].length"
    assert result["details"]["rule"] == "range"
