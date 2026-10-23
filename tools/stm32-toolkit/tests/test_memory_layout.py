"""Shared memory-layout validation, model and configuration placement tests."""

from __future__ import annotations

import hashlib
import json

import pytest

import stm32_toolkit.generation.configure as configure_mod
from stm32_toolkit.generation import GenerationError, plan_project_configuration
from stm32_toolkit.generation.managed_files import model_sha256_for
from stm32_toolkit.memory_layout import (
    MemoryLayout,
    MemoryLayoutError,
    normalize_memory_layout,
    parse_memory_layout_json,
    resolve_memory_layout,
    validate_memory_layout_regions,
)
from stm32_toolkit.project_model import ProjectManifestError, load_project_model

from test_generation import (
    plan_for,
    report_payload,
    standard_payload,
    write_project,
    write_report_bytes,
)

FLASH = {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"}
RAM = {"name": "RAM", "origin": 0x20000000, "length": 0x30000, "attributes": "rwx"}
CCM = {"name": "CCM", "origin": 0x10000000, "length": 0x10000, "attributes": "rwx"}

ALL_MAIN = {
    "flash": "FLASH",
    "data": "RAM",
    "bss": "RAM",
    "heap": "RAM",
    "stack": "RAM",
}

SPLIT = {
    "flash": "FLASH",
    "data": "RAM",
    "bss": "CCM",
    "heap": "CCM",
    "stack": "CCM",
}


def multi_region_payload(layout=None, regions=None):
    payload = standard_payload()
    payload["memory"]["regions"] = list(regions or (FLASH, RAM, CCM))
    if layout is not None:
        payload["memory"]["layout"] = dict(layout)
    return payload


# ---------------------------------------------------------------------------
# shared validation
# ---------------------------------------------------------------------------


def test_normalize_requires_exactly_the_five_named_roles():
    assert normalize_memory_layout(ALL_MAIN).to_dict() == ALL_MAIN

    with pytest.raises(MemoryLayoutError) as missing:
        normalize_memory_layout({"flash": "FLASH", "data": "RAM"})
    assert missing.value.code == "MEMORY_LAYOUT_INVALID"
    assert missing.value.details == {
        "field": "memoryLayout.bss",
        "rule": "required",
        "remediation": missing.value.details["remediation"],
    }

    with pytest.raises(MemoryLayoutError) as unknown:
        normalize_memory_layout({**ALL_MAIN, "extra": "RAM"})
    assert unknown.value.details["field"] == "memoryLayout.extra"
    assert unknown.value.details["rule"] == "unknownKey"

    for value in ({"flash": 1, **{key: "RAM" for key in ALL_MAIN if key != "flash"}},
                  {**ALL_MAIN, "stack": ""}):
        with pytest.raises(MemoryLayoutError) as invalid:
            normalize_memory_layout(value)
        assert invalid.value.details["rule"] == "type"

    with pytest.raises(MemoryLayoutError) as not_object:
        normalize_memory_layout(["flash"])
    assert not_object.value.details["rule"] == "type"


def test_parse_rejects_duplicate_keys_bad_json_and_oversized_integers():
    with pytest.raises(MemoryLayoutError) as duplicate:
        parse_memory_layout_json(
            '{"flash":"FLASH","flash":"FLASH","data":"RAM","bss":"RAM",'
            '"heap":"RAM","stack":"RAM"}'
        )
    assert duplicate.value.details["rule"] == "duplicateKey"
    assert duplicate.value.details["field"] == "memoryLayout"

    with pytest.raises(MemoryLayoutError) as malformed:
        parse_memory_layout_json('{"flash":')
    assert malformed.value.details["rule"] == "json"

    # Regression: CPython's integer-string conversion limit raises a plain
    # ValueError from ``json``; it must remain a bounded layout failure.
    with pytest.raises(MemoryLayoutError) as oversized:
        parse_memory_layout_json('{"flash":' + "9" * 5000 + "}")
    assert oversized.value.code == "MEMORY_LAYOUT_INVALID"
    assert oversized.value.details["field"] == "memoryLayout"
    assert oversized.value.details["rule"] == "json"

    with pytest.raises(MemoryLayoutError) as nested:
        parse_memory_layout_json("[" * 10000 + "]" * 10000)
    assert nested.value.details["rule"] in ("nesting", "json")
    assert nested.value.code == "MEMORY_LAYOUT_INVALID"


def test_role_access_rules_reject_writable_flash_and_readonly_ram():
    regions = [FLASH, RAM, CCM]
    validate_memory_layout_regions(MemoryLayout(**ALL_MAIN), regions)

    with pytest.raises(MemoryLayoutError) as writable_flash:
        validate_memory_layout_regions(
            MemoryLayout("RAM", "RAM", "RAM", "RAM", "RAM"), regions
        )
    assert writable_flash.value.details == {
        "field": "memory.layout.flash",
        "rule": "access",
        "remediation": writable_flash.value.details["remediation"],
    }

    with pytest.raises(MemoryLayoutError) as readonly_ram:
        validate_memory_layout_regions(
            MemoryLayout("FLASH", "FLASH", "RAM", "RAM", "RAM"), regions
        )
    assert readonly_ram.value.details["field"] == "memory.layout.data"
    assert readonly_ram.value.details["rule"] == "access"

    with pytest.raises(MemoryLayoutError) as unknown:
        validate_memory_layout_regions(
            MemoryLayout("FLASH", "MISSING", "RAM", "RAM", "RAM"), regions
        )
    assert unknown.value.details["field"] == "memory.layout.data"
    assert unknown.value.details["rule"] == "unknownRegion"


def test_flash_selection_skips_writable_executable_ram_even_when_first():
    resolution = resolve_memory_layout([RAM, FLASH])
    assert resolution.status == "implicit"
    assert resolution.layout == MemoryLayout("FLASH", "RAM", "RAM", "RAM", "RAM")
    assert [fact.name for fact in resolution.flash_candidates] == ["FLASH"]
    assert [fact.name for fact in resolution.ram_candidates] == ["RAM"]


def test_multiple_ram_regions_require_selection_with_actual_candidates():
    resolution = resolve_memory_layout([FLASH, RAM, CCM])
    assert resolution.status == "requires-selection"
    assert resolution.layout is None
    assert resolution.unresolved_roles == ("data", "bss", "heap", "stack")
    assert resolution.to_dict()["candidates"]["flash"] == [FLASH]
    assert resolution.to_dict()["candidates"]["ram"] == [RAM, CCM]
    assert resolution.requires_selection is True
    details = resolution.blocker_details()
    assert details["unresolvedRoles"] == ["data", "bss", "heap", "stack"]
    assert "FLASH" in details["remediation"]


def test_two_flash_candidates_require_an_explicit_flash_role():
    second_flash = {
        "name": "CODE",
        "origin": 0x09000000,
        "length": 0x100000,
        "attributes": "r-x",
    }
    resolution = resolve_memory_layout([FLASH, second_flash, RAM])
    assert resolution.status == "requires-selection"
    assert resolution.unresolved_roles == ("flash",)
    assert [fact.name for fact in resolution.flash_candidates] == ["FLASH", "CODE"]


# ---------------------------------------------------------------------------
# model integration
# ---------------------------------------------------------------------------


def test_omitted_layout_preserves_legacy_hash_and_linker_bytes(tmp_path):
    baseline_payload = standard_payload()
    legacy_root = write_project(tmp_path / "legacy", baseline_payload)
    legacy_model = load_project_model(legacy_root)
    legacy_hash = model_sha256_for(legacy_model)
    legacy_linker = next(
        entry
        for entry in plan_for(legacy_root).files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes
    assert legacy_model.memory.layout is None
    assert legacy_model.memory.stack_size is None
    assert legacy_model.memory.heap_size is None
    # Independently measured from the accepted startup CodeHead c76f03c3 with
    # unchanged standard_payload and no memory-layout options.  These exact
    # values are the compatibility contract for this new optional field.
    assert legacy_hash == (
        "10a807a4850f8a40060b416451c8f9381d5abb6d36b90dbaa9d408954bd90e1a"
    )
    assert hashlib.sha256(legacy_linker).hexdigest() == (
        "88b8414b398684f609098aa03c648f25bc7a1f9b13e322ed1fd2da8dbbb1b576"
    )

    # Only memory.layout is added; regions, sizes and every other field stay
    # exactly the accepted baseline configuration.
    explicit_payload = json.loads(json.dumps(baseline_payload))
    explicit_payload["memory"]["layout"] = dict(ALL_MAIN)
    assert explicit_payload["memory"]["regions"] == baseline_payload["memory"]["regions"]
    explicit_root = write_project(tmp_path / "explicit", explicit_payload)
    explicit_model = load_project_model(explicit_root)
    assert explicit_model.memory.layout == MemoryLayout(**ALL_MAIN)
    # The explicit mapping is a reviewed choice and therefore binds the model
    # hash even when the generated section placement is byte-identical.
    assert model_sha256_for(explicit_model) != legacy_hash
    explicit_linker = next(
        entry
        for entry in plan_for(explicit_root).files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes
    assert explicit_linker == legacy_linker


def test_explicit_all_main_ram_and_split_layouts_place_each_section(tmp_path):
    main_root = write_project(tmp_path / "main", multi_region_payload(ALL_MAIN))
    main_text = next(
        entry
        for entry in plan_for(main_root).files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert "  } > FLASH\n\n  .data" in main_text
    assert "  } > RAM AT> FLASH" in main_text
    assert "  } > RAM\n\n  .heap" in main_text
    assert "  } > RAM\n\n  .stack" in main_text
    assert "> CCM" not in main_text

    split_root = write_project(tmp_path / "split", multi_region_payload(SPLIT))
    split_text = next(
        entry
        for entry in plan_for(split_root).files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert "  } > RAM AT> FLASH" in split_text
    assert "  } > CCM\n\n  .heap" in split_text
    assert "  } > CCM\n\n  .stack" in split_text


def test_missing_layout_for_multiple_regions_is_a_configuration_blocker(tmp_path):
    root = write_project(tmp_path / "ambiguous", multi_region_payload())
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "MEMORY_LAYOUT_REQUIRED"
    assert error.value.details["unresolvedRoles"] == [
        "data",
        "bss",
        "heap",
        "stack",
    ]
    assert [entry["name"] for entry in error.value.details["candidates"]["ram"]] == [
        "RAM",
        "CCM",
    ]
    assert "remediation" in error.value.details


def test_invalid_explicit_layout_fails_model_loading(tmp_path):
    cases = [
        ({"flash": "MISSING"}, "memory.layout.flash", "unknownRegion"),
        ({"flash": "RAM"}, "memory.layout.flash", "access"),
        ({"data": "FLASH"}, "memory.layout.data", "access"),
    ]
    for index, (override, field, rule) in enumerate(cases):
        payload = multi_region_payload({**ALL_MAIN, **override})
        root = write_project(tmp_path / f"invalid-{index}", payload)
        with pytest.raises(ProjectManifestError) as error:
            load_project_model(root)
        assert error.value.code == "MEMORY_LAYOUT_INVALID"
        assert error.value.details["field"] == field
        assert error.value.details["rule"] == rule
        assert "remediation" in error.value.details


def test_schema_rejects_incomplete_or_extra_layout_roles(tmp_path):
    missing = multi_region_payload(ALL_MAIN)
    del missing["memory"]["layout"]["stack"]
    missing_root = write_project(tmp_path / "missing", missing)
    with pytest.raises(ProjectManifestError) as missing_error:
        load_project_model(missing_root)
    assert missing_error.value.code == "PROJECT_SCHEMA_INVALID"
    assert missing_error.value.details == {
        "field": "memory.layout.stack",
        "rule": "required",
    }

    extra = multi_region_payload(ALL_MAIN)
    extra["memory"]["layout"]["extra"] = "RAM"
    extra_root = write_project(tmp_path / "extra", extra)
    with pytest.raises(ProjectManifestError) as extra_error:
        load_project_model(extra_root)
    assert extra_error.value.code == "PROJECT_SCHEMA_INVALID"
    assert extra_error.value.details == {
        "field": "memory.layout.extra",
        "rule": "additionalProperties",
    }


def test_explicit_layout_with_native_linker_is_rejected_not_ignored(tmp_path):
    payload = multi_region_payload(ALL_MAIN)
    payload["generation"]["nativeLinkerScript"] = "native.ld"
    root = write_project(tmp_path / "native", payload)
    # Materialize the native script so the intended layout/native ownership
    # conflict is the first failure, not a missing-input error.
    (root / "native.ld").write_text("/* user-owned */\n", encoding="utf-8")
    with pytest.raises(ProjectManifestError) as error:
        load_project_model(root)
    assert error.value.code == "MEMORY_LAYOUT_INVALID"
    assert error.value.details["field"] == "memory.layout"
    assert error.value.details["rule"] == "nativeLinkerOwned"


def test_native_linker_without_layout_keeps_its_ownership(tmp_path):
    payload = multi_region_payload()
    payload["generation"]["nativeLinkerScript"] = "native.ld"
    root = write_project(tmp_path / "native-owned", payload)
    (root / "native.ld").write_text("/* user-owned */\n", encoding="utf-8")
    model = load_project_model(root)
    assert model.memory.layout is None
    plan = plan_project_configuration(model)
    assert plan.blockers == ()
    assert all(entry.path != "linker/stm32tk.ld" for entry in plan.files)
    # A native linker owns placement; multiple RAM regions do not require a
    # managed layout decision.
    assert not any(
        blocker.code == "MEMORY_LAYOUT_REQUIRED" for blocker in plan.blockers
    )


def test_fixed_noload_section_is_placed_in_its_region_not_copied(tmp_path):
    payload = multi_region_payload(SPLIT)
    root = write_project(tmp_path / "fixed-ok", payload)
    address = 0x10000100
    section = ".stm32tk.abs.%08x" % address
    write_report_bytes(
        root,
        json.dumps(
            report_payload(
                [
                    {
                        "section": section,
                        "address": address,
                        "sourcePath": "Src/main.c",
                        "line": 1,
                        "symbol": "fixed_value",
                    }
                ]
            )
        ).encode("utf-8"),
    )
    text = next(
        entry
        for entry in plan_for(root).files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert f"  {section} 0x{address:08x} (NOLOAD) :" in text
    assert "  } > CCM" in text
    data_block = text.split("  .data :", 1)[1].split("  .bss :", 1)[0]
    bss_block = text.split("  .bss :", 1)[1].split("  .heap", 1)[0]
    assert section not in data_block
    assert section not in bss_block
    assert "*(.data*)" in data_block
    assert "*(.bss*)" in bss_block


def test_fixed_section_outside_declared_regions_remains_a_blocker(tmp_path):
    payload = multi_region_payload(ALL_MAIN)
    root = write_project(tmp_path / "fixed", payload)
    address = 0x30000000
    write_report_bytes(
        root,
        json.dumps(
            report_payload(
                [
                    {
                        "section": ".stm32tk.abs.%08x" % address,
                        "address": address,
                        "sourcePath": "Src/main.c",
                        "line": 1,
                        "symbol": "outside_region",
                    }
                ]
            )
        ).encode("utf-8"),
    )
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details["rule"] == "region"
