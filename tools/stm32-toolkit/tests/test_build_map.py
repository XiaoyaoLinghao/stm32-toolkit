"""GNU ld MAP parsing contract tests (STM32TK-0305).

The MAP parser extracts the GNU ld ``Memory Configuration`` region table and
the output-section rows of the ``Linker script and memory map`` section with
anchored regexes, then computes per-region usage by interval union
accounting.  Malformed or inconsistent evidence fails closed.
"""

from __future__ import annotations

import pytest

from stm32_toolkit.build.map_file import (
    MapFile,
    MapMemoryRegion,
    MapParseError,
    MapSection,
    parse_map,
)


REALISTIC_MAP = """\
Archive member included to satisfy reference by file (symbol)

build/arm-debug/obj/main.o

Discarded input sections

 .ARM.attributes 0x0000000000000000 0x0 build/arm-debug/obj/main.o

Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000 xr
RAM              0x0000000020000000 0x0000000000040000 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.isr_vector      0x0000000008000000     0x400
 .isr_vector     0x0000000008000000       0x400 build/arm-debug/obj/startup.o
                 0x0000000008000000                g_pfnVectors

.text            0x0000000008000400     0x2c8
 .text           0x0000000008000400       0x2c8 build/arm-debug/obj/main.o
                 0x0000000008000400                Reset_Handler
                 0x0000000008000401                main

.ARM.exidx       0x00000000080006c8     0x8
 .ARM.exidx      0x00000000080006c8        0x8 build/arm-debug/obj/main.o

.data            0x0000000020000000     0x18 load address 0x00000000080006d0
 .data           0x0000000020000000       0x18 build/arm-debug/obj/main.o

.bss             0x0000000020000018     0x200
 .bss            0x0000000020000018       0x200 build/arm-debug/obj/main.o

.heap            0x0000000020000218     0x1000
                0x0000000020000218                __end__ = .

.stack           0x0000000020001218     0x400
                0x0000000020001218                __StackTop = .

.ARM.attributes 0x0000000008000000     0x0
"""


def test_parse_map_extracts_memory_regions():
    parsed = parse_map(REALISTIC_MAP)

    assert parsed.memory_regions == (
        MapMemoryRegion("FLASH", 0x08000000, 0x100000, "xr"),
        MapMemoryRegion("RAM", 0x20000000, 0x40000, "rw"),
    )


def test_parse_map_extracts_output_sections_with_vma():
    parsed = parse_map(REALISTIC_MAP)

    assert parsed.sections == (
        MapSection(".isr_vector", 0x08000000, 0x400),
        MapSection(".text", 0x08000400, 0x2c8),
        MapSection(".ARM.exidx", 0x080006C8, 0x8),
        MapSection(".data", 0x20000000, 0x18),
        MapSection(".bss", 0x20000018, 0x200),
        MapSection(".heap", 0x20000218, 0x1000),
        MapSection(".stack", 0x20001218, 0x400),
        MapSection(".ARM.attributes", 0x08000000, 0x0),
    )


def test_parse_map_load_address_rows_use_vma_not_lma():
    parsed = parse_map(REALISTIC_MAP)
    data = next(section for section in parsed.sections if section.name == ".data")

    assert data.address == 0x20000000
    assert data.size == 0x18


def test_region_usage_accounts_by_interval_union():
    parsed = parse_map(REALISTIC_MAP)

    flash_used = 0x400 + 0x2C8 + 0x8
    ram_used = 0x18 + 0x200 + 0x1000 + 0x400
    usage = parsed.region_usage()

    assert usage[0].region == "FLASH"
    assert usage[0].origin == 0x08000000
    assert usage[0].length == 0x100000
    assert usage[0].used == flash_used
    assert usage[0].percent == round(flash_used * 100.0 / 0x100000, 2)
    assert usage[1].region == "RAM"
    assert usage[1].used == ram_used
    assert usage[1].percent == round(ram_used * 100.0 / 0x40000, 2)


def test_region_usage_unions_overlapping_sections():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
REGION           0x0000000000001000 0x0000000000000200 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.a               0x0000000000001000     0x100
.b               0x0000000000001080     0x100
"""
    parsed = parse_map(text)
    usage = parsed.region_usage()

    assert usage[0].used == 0x180


def test_region_usage_clips_sections_to_region_bounds():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
REGION           0x0000000000001000 0x0000000000000300 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.overflow        0x0000000000001000     0x400
"""
    parsed = parse_map(text)
    usage = parsed.region_usage()

    assert usage[0].used == 0x300


def test_region_usage_ignores_sections_outside_regions():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
REGION           0x0000000000001000 0x0000000000000100 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.elsewhere       0x0000000008000000     0x100
"""
    parsed = parse_map(text)
    usage = parsed.region_usage()

    assert usage[0].used == 0
    assert usage[0].percent == 0.0


def test_parse_map_handles_fill_and_common_rows():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000 xr
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

*fill*          0x0000000008000000     0x4
COMMON          0x0000000020000000     0x8
"""
    parsed = parse_map(text)

    assert parsed.sections == (
        MapSection("*fill*", 0x08000000, 0x4),
        MapSection("COMMON", 0x20000000, 0x8),
    )


def test_parse_map_accepts_short_and_lowercase_hex():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x8000000 0x100000 xr
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.text            0x8000400 0x2c8
"""
    parsed = parse_map(text)

    assert parsed.memory_regions[0] == MapMemoryRegion("FLASH", 0x08000000, 0x100000, "xr")
    assert parsed.sections == (MapSection(".text", 0x08000400, 0x2C8),)


def test_parse_map_without_regions_is_malformed():
    with pytest.raises(MapParseError) as error:
        parse_map("")
    assert error.value.code == "BUILD_EVIDENCE_INVALID"
    assert error.value.details == {"rule": "memoryConfiguration"}


def test_parse_map_without_output_sections_is_malformed():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000 xr
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map
"""
    with pytest.raises(MapParseError) as error:
        parse_map(text)
    assert error.value.details == {"rule": "outputSections"}


def test_parse_map_rejects_overlapping_memory_regions():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
A                0x0000000000001000 0x0000000000000100 rw
B                0x00000000000010ff 0x0000000000000100 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.a               0x0000000000001000     0x100
"""
    with pytest.raises(MapParseError) as error:
        parse_map(text)
    assert error.value.details == {"rule": "overlappingRegions"}


def test_parse_map_region_without_attributes_is_accepted():
    text = """\
Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.text            0x0000000008000400     0x2c8
"""
    parsed = parse_map(text)

    assert parsed.memory_regions[0] == MapMemoryRegion("FLASH", 0x08000000, 0x100000, None)


def test_parse_map_ignores_unrelated_lines():
    text = """\
some random preamble line
Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000 xr
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

0x0000000008000400 0x2c8
0x0000000008000400                Reset_Handler
.text            0x0000000008000400     0x2c8
"""
    parsed = parse_map(text)

    assert parsed.sections == (MapSection(".text", 0x08000400, 0x2C8),)


def test_map_file_values_are_immutable():
    parsed = parse_map(REALISTIC_MAP)

    with pytest.raises(AttributeError):
        parsed.memory_regions = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        parsed.sections = ()  # type: ignore[misc]
