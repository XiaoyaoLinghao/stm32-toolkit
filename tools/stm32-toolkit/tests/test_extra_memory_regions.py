"""Strict explicit external-RAM region validation and model/model-hash behavior.

All capacities here are synthetic test values, never board facts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stm32_toolkit.extra_regions import (
    EXTRA_REGION_NAME_RE,
    MAX_EXTRA_REGIONS,
    MAX_EXTRA_REGIONS_JSON_BYTES,
    ExtraRegion,
    ExtraRegionError,
    combined_regions,
    normalize_extra_regions,
    normalize_extra_regions_option,
    parse_extra_regions_json,
    validate_extra_regions,
)
from stm32_toolkit.generation import GenerationError, plan_project_configuration
from stm32_toolkit.generation.managed_files import model_sha256_for
from stm32_toolkit.memory_layout import (
    MemoryLayout,
    MemoryLayoutError,
    resolve_memory_layout,
)
from stm32_toolkit.project_model import ProjectManifestError, load_project_model

from test_project_v3 import _v2_payload

REPO_ROOT = Path(__file__).resolve().parents[3]

FLASH = {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"}
RAM = {"name": "RAM", "origin": 0x20000000, "length": 0x30000, "attributes": "rwx"}
#: Synthetic external-RAM example capacity (not a board fact).
EXT = {
    "name": "EXT_SRAM",
    "origin": 0x68000000,
    "length": 0x10000,
    "attributes": "rw-",
}


def _v2_payload_with(memory: dict, *, schema_version: int = 2) -> dict:
    payload = _v2_payload()
    payload["schemaVersion"] = schema_version
    payload["build"].update(
        {
            "presets": ["arm-debug", "arm-release"],
            "elf": "build/arm-debug/firmware.elf",
        }
    )
    payload["memory"] = memory
    return payload


def _write_project(root: Path, payload: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".stm32-project.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    source = root / "App" / "main.c"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# shared normalization
# ---------------------------------------------------------------------------


def test_boundary_values_and_adjacency_are_accepted():
    # TOP and WHOLE would overlap if requested together; each boundary is a
    # separate valid request.
    assert normalize_extra_regions(
        [{"name": "TOP", "origin": 0xFFFFFFFF, "length": 1, "attributes": "rw-"}]
    ) == (ExtraRegion("TOP", 0xFFFFFFFF, 1, "rw-"),)
    assert normalize_extra_regions(
        [{"name": "WHOLE", "origin": 0, "length": 0x1_0000_0000, "attributes": "rwx"}]
    ) == (ExtraRegion("WHOLE", 0, 0x1_0000_0000, "rwx"),)
    adjacent = normalize_extra_regions(
        [
            {"name": "A", "origin": 0x68000000, "length": 0x100, "attributes": "rw-"},
            {"name": "B", "origin": 0x68000100, "length": 0x100, "attributes": "rw-"},
        ]
    )
    assert [region.name for region in adjacent] == ["A", "B"]


def test_none_and_empty_are_the_same_no_extra_request():
    assert normalize_extra_regions(None) == ()
    assert normalize_extra_regions([]) == ()
    assert normalize_extra_regions_option(None) == ()
    assert normalize_extra_regions_option([]) == ()


@pytest.mark.parametrize(
    ("entry", "field", "rule"),
    [
        ({**EXT, "extra": 1}, "extraRegions[0].extra", "unknownKey"),
        (
            {key: value for key, value in EXT.items() if key != "name"},
            "extraRegions[0].name",
            "required",
        ),
        ({**EXT, "name": ""}, "extraRegions[0].name", "pattern"),
        ({**EXT, "name": "EXT-SRAM"}, "extraRegions[0].name", "pattern"),
        ({**EXT, "name": "é"}, "extraRegions[0].name", "pattern"),
        ({**EXT, "name": "A" * 65}, "extraRegions[0].name", "length"),
        ({**EXT, "origin": True}, "extraRegions[0].origin", "type"),
        ({**EXT, "origin": "0x20040000"}, "extraRegions[0].origin", "type"),
        ({**EXT, "origin": -1}, "extraRegions[0].origin", "range"),
        ({**EXT, "origin": 0x1_0000_0000}, "extraRegions[0].origin", "range"),
        ({**EXT, "length": 0}, "extraRegions[0].length", "range"),
        ({**EXT, "length": 1.5}, "extraRegions[0].length", "type"),
        ({**EXT, "length": 0x1_0000_0001}, "extraRegions[0].length", "range"),
        (
            {**EXT, "origin": 0xFFFFFFFF, "length": 2},
            "extraRegions[0]",
            "range",
        ),
        ({**EXT, "attributes": "r-x"}, "extraRegions[0].attributes", "attributes"),
        ({**EXT, "attributes": "r--"}, "extraRegions[0].attributes", "attributes"),
        ("not-an-object", "extraRegions[0]", "type"),
    ],
)
def test_invalid_entries_are_rejected_with_portable_details(entry, field, rule):
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions([entry])
    assert caught.value.code == "EXTRA_REGIONS_INVALID"
    assert caught.value.details["field"] == field
    assert caught.value.details["rule"] == rule
    assert "remediation" in caught.value.details


def test_duplicate_case_collision_overlap_and_count_are_rejected():
    duplicate = normalize_extra_regions([EXT])[0]
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions([EXT, duplicate])
    assert caught.value.details["rule"] == "casefoldCollision"
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions([EXT, {**EXT, "name": "ext_sram"}])
    assert caught.value.details["rule"] == "casefoldCollision"
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions(
            [
                EXT,
                {
                    "name": "OVERLAP",
                    "origin": 0x6800FFFF,
                    "length": 2,
                    "attributes": "rw-",
                },
            ]
        )
    assert caught.value.details == {
        "field": "extraRegions[1]",
        "rule": "overlap",
        "remediation": caught.value.details["remediation"],
    }
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions(
            [
                {
                    "name": f"R{index}",
                    "origin": index * 0x1000,
                    "length": 0x1000,
                    "attributes": "rw-",
                }
                for index in range(MAX_EXTRA_REGIONS + 1)
            ]
        )
    assert caught.value.details["field"] == "extraRegions"
    assert caught.value.details["rule"] == "count"


def test_unknown_key_diagnostic_is_bounded_portable_text():
    key = "x" * 4096
    with pytest.raises(ExtraRegionError) as caught:
        normalize_extra_regions([{**EXT, key: 1}])
    field = caught.value.details["field"]
    assert field == "extraRegions[0].<unknown>"
    assert len(field) < 64
    assert "\\" not in field and "/" not in field


def test_cross_validation_rejects_base_collisions_and_overlap_but_allows_adjacency():
    base = [FLASH, RAM]
    assert validate_extra_regions([EXT], base) == (ExtraRegion(**EXT),)
    with pytest.raises(ExtraRegionError) as caught:
        validate_extra_regions(
            [{**EXT, "name": "ram", "origin": 0x68010000}], base
        )
    assert caught.value.details["rule"] == "casefoldCollision"
    with pytest.raises(ExtraRegionError) as caught:
        validate_extra_regions(
            [{**EXT, "origin": 0x2002FFFF}], base
        )
    assert caught.value.details["rule"] == "overlap"
    adjacent_to_ram = {**EXT, "origin": 0x20030000, "length": 0x10}
    assert validate_extra_regions([adjacent_to_ram], base)


def test_combined_regions_preserves_base_order_then_extras():
    base = [FLASH, RAM]
    extras = normalize_extra_regions([EXT])
    combined = combined_regions(base, extras)
    assert combined[:2] == tuple(base)
    assert combined[2] == ExtraRegion(**EXT)


def test_json_transport_is_bounded_and_rejects_duplicate_or_malformed_input():
    valid = json.dumps([EXT])
    assert parse_extra_regions_json(valid) == (ExtraRegion(**EXT),)
    with pytest.raises(ExtraRegionError) as caught:
        parse_extra_regions_json(
            '[{"name":"A","origin":0,"origin":1,"length":1,"attributes":"rw-"}]'
        )
    assert caught.value.details["rule"] == "duplicateKey"
    for text, rule in (
        ("{", "json"),
        ("null", "type"),
        (json.dumps({"name": "A"}), "type"),
        (json.dumps([[EXT]]), "nesting"),
        ("[NaN]", "json"),
    ):
        with pytest.raises(ExtraRegionError) as caught:
            parse_extra_regions_json(text)
        assert caught.value.details["rule"] == rule
        assert caught.value.details["field"] == "extraRegions"
    # Very deep text is rejected either by the explicit depth guard (when the
    # parser returns) or by the interpreter limit (caught as nesting); the
    # bounded public contract is a stable rejection, never a raw RecursionError.
    try:
        parse_extra_regions_json("[" * 2000 + "]" * 2000)
    except ExtraRegionError as error:
        assert error.details["field"] == "extraRegions"
        assert error.details["rule"] in {"nesting", "type"}
    else:
        pytest.fail("deeply nested extraRegions JSON was accepted")
    oversized = " " * (MAX_EXTRA_REGIONS_JSON_BYTES + 1)
    with pytest.raises(ExtraRegionError) as caught:
        parse_extra_regions_json(oversized)
    assert caught.value.details["rule"] == "size"


def test_mcp_style_values_are_never_coerced():
    # Zero is an explicit valid origin, never treated as an omission.
    assert normalize_extra_regions_option(
        [{**EXT, "origin": 0, "length": 1}]
    ) == (ExtraRegion("EXT_SRAM", 0, 1, "rw-"),)
    for value in (True, "0x20040000", 1.0):
        with pytest.raises(ExtraRegionError) as caught:
            normalize_extra_regions_option([{**EXT, "origin": value}])
        assert caught.value.details["field"] == "extraRegions[0].origin"
        assert caught.value.details["rule"] == "type"


# ---------------------------------------------------------------------------
# schema and typed model
# ---------------------------------------------------------------------------


def test_root_and_packaged_schemas_stay_byte_identical():
    packaged = (
        REPO_ROOT
        / "tools"
        / "stm32-toolkit"
        / "src"
        / "stm32_toolkit"
        / "schemas"
        / "stm32-project.schema.json"
    )
    assert (REPO_ROOT / "schemas" / "stm32-project.schema.json").read_bytes() == (
        packaged.read_bytes()
    )


@pytest.mark.parametrize("version", (2, 3))
def test_v2_and_v3_models_compose_base_and_extra_once(tmp_path, version):
    root = _write_project(
        tmp_path / f"v{version}",
        _v2_payload_with(
            {"source": "manual", "regions": [FLASH, RAM], "extraRegions": [EXT]},
            schema_version=version,
        ),
    )
    model = load_project_model(root)
    assert [region.name for region in model.memory.regions] == [
        "FLASH",
        "RAM",
        "EXT_SRAM",
    ]
    assert model.memory.regions[2] == type(model.memory.regions[2])(
        name="EXT_SRAM",
        origin=0x68000000,
        length=0x10000,
        attributes="rw-",
    )
    assert model.memory.extra_region_names == ("EXT_SRAM",)
    if version == 3:
        assert [region.name for region in model.debug.readable_regions] == [
            "FLASH",
            "RAM",
            "EXT_SRAM",
        ]


@pytest.mark.parametrize(
    ("memory", "field", "rule"),
    [
        (
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [{**EXT, "attributes": "r-x"}],
            },
            "memory.extraRegions[0].attributes",
            "enum",
        ),
        (
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [{**EXT, "length": 0}],
            },
            "memory.extraRegions[0].length",
            "minimum",
        ),
        (
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [{**EXT, "origin": 0x2002FFFF}],
            },
            "memory.extraRegions[0]",
            "overlap",
        ),
        (
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [EXT, {**EXT, "name": "ext_sram"}],
            },
            "memory.extraRegions[1].name",
            "casefoldCollision",
        ),
        (
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [{**EXT, "name": "ram"}],
            },
            "memory.extraRegions[0].name",
            "casefoldCollision",
        ),
    ],
)
def test_manifest_extra_region_failures_use_the_schema_error_family(
    tmp_path, memory, field, rule
):
    root = _write_project(tmp_path, _v2_payload_with(memory))
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "PROJECT_SCHEMA_INVALID"
    assert caught.value.details["field"] == field
    assert caught.value.details["rule"] == rule
    assert "remediation" in caught.value.details or rule != "overlap"


def test_explicit_layout_may_name_an_extra_region(tmp_path):
    root = _write_project(
        tmp_path,
        _v2_payload_with(
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [EXT],
                "layout": {
                    "flash": "FLASH",
                    "data": "RAM",
                    "bss": "EXT_SRAM",
                    "heap": "EXT_SRAM",
                    "stack": "EXT_SRAM",
                },
            }
        ),
    )
    model = load_project_model(root)
    assert model.memory.layout.bss == "EXT_SRAM"


def test_empty_extras_keep_the_historical_model_hash_but_nonempty_changes_it(
    tmp_path,
):
    without = _write_project(
        tmp_path / "without",
        _v2_payload_with({"source": "manual", "regions": [FLASH, RAM]}),
    )
    empty = _write_project(
        tmp_path / "empty",
        _v2_payload_with(
            {"source": "manual", "regions": [FLASH, RAM], "extraRegions": []}
        ),
    )
    with_extra = _write_project(
        tmp_path / "extra",
        _v2_payload_with(
            {"source": "manual", "regions": [FLASH, RAM], "extraRegions": [EXT]}
        ),
    )
    resized = _write_project(
        tmp_path / "resized",
        _v2_payload_with(
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [{**EXT, "length": 0x8000}],
            }
        ),
    )
    base_hash = model_sha256_for(load_project_model(without))
    extra_hash = model_sha256_for(load_project_model(with_extra))
    assert model_sha256_for(load_project_model(empty)) == base_hash
    assert extra_hash != base_hash
    assert model_sha256_for(load_project_model(resized)) != extra_hash


# ---------------------------------------------------------------------------
# generation semantics
# ---------------------------------------------------------------------------


def test_generation_uses_the_complete_map_and_never_implicitly_places_in_ext(
    tmp_path,
):
    explicit = _write_project(
        tmp_path / "explicit",
        _v2_payload_with(
            {
                "source": "manual",
                "regions": [FLASH, RAM],
                "extraRegions": [EXT],
                "layout": {
                    "flash": "FLASH",
                    "data": "RAM",
                    "bss": "EXT_SRAM",
                    "heap": "EXT_SRAM",
                    "stack": "EXT_SRAM",
                },
            }
        ),
    )
    plan = plan_project_configuration(load_project_model(explicit))
    assert plan.blockers == ()
    linker = next(
        entry for entry in plan.files if entry.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00010000" in linker
    assert "  .bss :" in linker and "} > EXT_SRAM" in linker
    assert "} > RAM AT> FLASH" in linker

    no_base_ram = _write_project(
        tmp_path / "extra-only",
        _v2_payload_with(
            {"source": "manual", "regions": [FLASH], "extraRegions": [EXT]}
        ),
    )
    with pytest.raises(GenerationError) as caught:
        plan_project_configuration(load_project_model(no_base_ram))
    assert caught.value.code == "MEMORY_LAYOUT_REQUIRED"
    assert "EXT_SRAM" in str(caught.value.details["candidates"]["ram"])
    assert "EXT_SRAM" in str(caught.value.details["remediation"])


def test_omitted_and_explicit_empty_extras_render_identical_generation(tmp_path):
    omitted = _write_project(
        tmp_path / "cfg-omitted",
        _v2_payload_with({"source": "manual", "regions": [FLASH, RAM]}),
    )
    empty = _write_project(
        tmp_path / "cfg-empty",
        _v2_payload_with(
            {"source": "manual", "regions": [FLASH, RAM], "extraRegions": []}
        ),
    )
    first = plan_project_configuration(load_project_model(omitted))
    second = plan_project_configuration(load_project_model(empty))
    # The manifest bytes themselves differ (the empty array is explicit), but
    # the normalized model identity and every rendered target are identical.
    assert first.model_sha256 == second.model_sha256
    assert [(entry.path, entry.after_bytes) for entry in first.files] == [
        (entry.path, entry.after_bytes) for entry in second.files
    ]


def test_native_linker_is_preserved_and_extras_change_model_identity(tmp_path):
    payload = _v2_payload_with(
        {"source": "manual", "regions": [FLASH, RAM], "extraRegions": [EXT]}
    )
    payload["generation"]["nativeLinkerScript"] = "linker/user.ld"
    root = _write_project(tmp_path / "native", payload)
    native = root / "linker" / "user.ld"
    native.parent.mkdir(parents=True)
    native.write_text("/* user-owned */\nMEMORY { }\n", encoding="utf-8")
    original = native.read_bytes()
    model = load_project_model(root)
    plan = plan_project_configuration(model)
    assert plan.blockers == ()
    assert all(entry.path != "linker/stm32tk.ld" for entry in plan.files)
    assert native.read_bytes() == original
    assert plan.model_sha256 == model_sha256_for(model)
    assert model.memory.extra_region_names == ("EXT_SRAM",)

    without = _write_project(
        tmp_path / "native-without",
        _v2_payload_with({"source": "manual", "regions": [FLASH, RAM]}),
    )
    assert model_sha256_for(model) != model_sha256_for(load_project_model(without))

    managed = _v2_payload_with(
        {
            "source": "manual",
            "regions": [FLASH, RAM],
            "extraRegions": [EXT],
            "layout": {
                "flash": "FLASH",
                "data": "RAM",
                "bss": "RAM",
                "heap": "RAM",
                "stack": "RAM",
            },
        }
    )
    managed["generation"]["nativeLinkerScript"] = "linker/user.ld"
    conflicting = _write_project(tmp_path / "native-conflict", managed)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(conflicting)
    assert caught.value.code == "MEMORY_LAYOUT_INVALID"
    assert caught.value.details["rule"] == "nativeLinkerOwned"


def test_resolve_memory_layout_never_infers_an_extra_ram_and_excludes_it_as_flash():
    base = [FLASH]
    extras = normalize_extra_regions(
        [{**EXT, "name": "EXT_RWX", "attributes": "rwx"}]
    )
    resolution = resolve_memory_layout(
        combined_regions(base, extras),
        None,
        extra_region_names=("EXT_RWX",),
    )
    assert resolution.status == "requires-selection"
    assert resolution.layout is None
    assert [fact.name for fact in resolution.flash_candidates] == ["FLASH"]
    assert [fact.name for fact in resolution.ram_candidates] == ["EXT_RWX"]
    assert resolution.unresolved_roles == ("data", "bss", "heap", "stack")

    rejected = MemoryLayout("EXT_RWX", "EXT_RWX", "EXT_RWX", "EXT_RWX", "EXT_RWX")
    with pytest.raises(MemoryLayoutError) as caught:
        resolve_memory_layout(combined_regions(base, extras), rejected)
    assert caught.value.details["field"] == "memory.layout.flash"
    assert caught.value.details["rule"] == "access"
    assert EXTRA_REGION_NAME_RE.fullmatch("EXT_RWX")
