"""GNU ld MAP parsing, interval accounting, and overflow contracts.

The MAP parser is bounded and fail-closed: every malformed, duplicate,
overlapping, unknown, or out-of-region row is rejected with a stable rule;
usage is computed as interval union (never a sum) over VMA and LMA
intervals; and any region overflow maps to the stable overflow codes.
"""

from __future__ import annotations

import pytest

from stm32_toolkit.build.map_file import MapError, parse_map
from stm32_toolkit.project_model import MemoryRegion

from test_build_runner import build_map_text

FLASH = MemoryRegion(name="FLASH", origin=0x08000000, length=0x100000, attributes="r-x")
RAM = MemoryRegion(name="RAM", origin=0x20000000, length=0x20000, attributes="rwx")
CCM = MemoryRegion(name="CCM", origin=0x10000000, length=0x10000, attributes="rw")

DEFAULT_REGIONS = (FLASH, RAM)


def parse(text: str, regions=DEFAULT_REGIONS):
    return parse_map(text, regions)


def test_valid_map_accounts_vma_and_lma_with_interval_union():
    text = build_map_text()
    usage = parse(text)
    flash, ram = usage
    assert flash.name == "FLASH"
    assert flash.origin == 0x08000000
    assert flash.length == 0x100000
    assert flash.used == 0x40 + 0x100 + 0x100  # .isr_vector + .text + .data LMA
    assert flash.free == flash.length - flash.used
    assert ram.used == 0x100 + 0x400  # .data + .bss
    assert ram.free == ram.length - ram.used


def test_overlapping_sections_are_not_double_counted():
    text = build_map_text(
        sections=(
            (".text", 0x08000040, 0x100, None),
            (".rodata", 0x08000080, 0x40, None),
        )
    )
    flash, _ = parse(text)
    assert flash.used == 0x100


def test_lma_in_different_region_is_accounted_to_both():
    text = build_map_text()
    flash, ram = parse(text)
    # .data: VMA in RAM (0x100), LMA in FLASH (0x100)
    assert ram.used == 0x100 + 0x400
    assert flash.used == 0x40 + 0x100 + 0x100


def test_zero_size_sections_are_ignored():
    text = build_map_text(sections=((".text", 0x08000040, 0x0, None),))
    flash, _ = parse(text)
    assert flash.used == 0


def test_crlf_map_parses_identically():
    lf = parse(build_map_text())
    crlf = parse(build_map_text(linesep="\r\n"))
    assert crlf == lf


def test_model_regions_must_match_exactly_in_order():
    text = build_map_text(regions=(("FLASH", 0x08000000, 0x100000),))
    with pytest.raises(MapError) as error:
        parse(text, DEFAULT_REGIONS)  # model declares FLASH and RAM
    assert error.value.code == "BUILD_MAP_INVALID"
    assert error.value.details == {"rule": "regions"}


def test_wrong_region_origin_is_rejected():
    text = build_map_text(regions=(("FLASH", 0x08010000, 0x100000), ("RAM", 0x20000000, 0x20000)))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "regions"}


def test_wrong_region_length_is_rejected():
    text = build_map_text(regions=(("FLASH", 0x08000000, 0x200000), ("RAM", 0x20000000, 0x20000)))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "regions"}


def test_region_order_mismatch_is_rejected():
    text = build_map_text(regions=(("RAM", 0x20000000, 0x20000), ("FLASH", 0x08000000, 0x100000)))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "regions"}


def test_duplicate_region_names_are_rejected():
    text = build_map_text(
        regions=(("FLASH", 0x08000000, 0x100000), ("FLASH", 0x08000000, 0x100000))
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "duplicateRegion"}


def test_overlapping_declared_regions_are_rejected():
    text = build_map_text(
        regions=(("FLASH", 0x08000000, 0x100000), ("F2", 0x08001000, 0x100000))
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "overlap"}


def test_malformed_integer_is_rejected():
    text = build_map_text().replace(
        "0x0000000008000040", "0xZZ00000040", 1
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "ambiguous"}


def test_overflowing_integer_is_rejected():
    text = build_map_text().replace(
        "0x0000000008000000", "0x10000000000000000", 1
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "integer"}


def test_duplicate_section_rows_are_rejected():
    text = build_map_text(
        sections=(
            (".text", 0x08000040, 0x100, None),
            (".text", 0x08000040, 0x100, None),
        )
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "duplicateSection"}


def test_conflicting_section_rows_are_rejected():
    text = build_map_text(
        sections=(
            (".text", 0x08000040, 0x100, None),
            (".text", 0x08000200, 0x200, None),
        )
    )
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "duplicateSection"}


def test_ambiguous_row_is_rejected():
    text = build_map_text() + "junk! 0x0000000008000000 0x40 trailing\n"
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "ambiguous"}


def test_section_outside_any_model_region_is_rejected():
    text = build_map_text(sections=((".text", 0x30000000, 0x100, None),))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "outOfRegion"}


def test_flash_overflow_returns_stable_details():
    text = build_map_text(sections=((".text", 0x08000000, 0x200000, None),))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.code == "FLASH_OVERFLOW"
    assert error.value.details == {
        "region": "FLASH",
        "used": 0x200000,
        "length": 0x100000,
        "overflow": 0x100000,
    }


def test_ram_overflow_returns_stable_details():
    text = build_map_text(sections=((".bss", 0x20000000, 0x30000, None),))
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.code == "RAM_OVERFLOW"
    assert error.value.details == {
        "region": "RAM",
        "used": 0x30000,
        "length": 0x20000,
        "overflow": 0x10000,
    }


def test_other_region_overflow_returns_memory_overflow():
    text = build_map_text(
        regions=(("FLASH", 0x08000000, 0x100000), ("RAM", 0x20000000, 0x20000), ("CCM", 0x10000000, 0x10000)),
        region_attributes=("xr", "xrw", "rw"),
        sections=((".ccm", 0x10000000, 0x20000, None),),
    )
    with pytest.raises(MapError) as error:
        parse(text, (FLASH, RAM, CCM))
    assert error.value.code == "MEMORY_OVERFLOW"
    assert error.value.details == {
        "region": "CCM",
        "used": 0x20000,
        "length": 0x10000,
        "overflow": 0x10000,
    }


def test_usage_reports_every_model_region_in_model_order():
    text = build_map_text(
        regions=(("FLASH", 0x08000000, 0x100000), ("RAM", 0x20000000, 0x20000), ("CCM", 0x10000000, 0x10000)),
        region_attributes=("xr", "xrw", "rw"),
        sections=((".ccm", 0x10000000, 0x100, None),),
    )
    usage = parse(text, (FLASH, RAM, CCM))
    assert [item.name for item in usage] == ["FLASH", "RAM", "CCM"]
    assert usage[2].used == 0x100
    assert usage[2].free == 0x10000 - 0x100


def test_empty_section_list_is_rejected():
    text = build_map_text(sections=())
    with pytest.raises(MapError) as error:
        parse(text)
    assert error.value.details == {"rule": "sections"}


def test_map_without_memory_configuration_is_rejected():
    with pytest.raises(MapError) as error:
        parse("Linker script and memory map\n\n.text 0x0000000008000000 0x40\n")
    assert error.value.details == {"rule": "regions"}


def test_memory_usage_is_frozen_and_json_safe():
    usage = parse(build_map_text())
    with pytest.raises(AttributeError):
        usage[0].used = 1  # type: ignore[misc]
    assert usage[0].to_dict() == {
        "name": "FLASH",
        "origin": 0x08000000,
        "length": 0x100000,
        "used": 0x240,
        "free": 0x100000 - 0x240,
    }
