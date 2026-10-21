"""Offline regressions for Monitor's qualified combined-byte snapshots."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from stm32_toolkit.debug.model import DebugReadItem, MemoryRegionBinding, TypedValue
from stm32_toolkit.debug.read import (
    _ReadFailure, _Resolved, _execute_prepared, _freeze_prepared_plan,
)
from stm32_toolkit.debug.types import DwarfSelection, DwarfType
from stm32_toolkit.debug.read import _variable
from test_debug_read import DebugEnv, debug_env


def _byte(
    expression: str, address: int, region: MemoryRegionBinding, *,
    unsigned: bool = True,
) -> _Resolved:
    def decode(data: bytes) -> TypedValue:
        value = data[0]
        return TypedValue(expression, "uint8_t", value, f"0x{value:02x}", 8)

    return _Resolved(expression, address, 1, region, decode, unsigned_byte=unsigned)


def _pair_plan(
    env: DebugEnv, *,
    region: MemoryRegionBinding | None = None,
    extra_regions: tuple[MemoryRegionBinding, ...] = (),
    svd_regions: tuple[MemoryRegionBinding, ...] | None = None,
    addresses: tuple[int, int] = (0x2001DC29, 0x2001DC2A),
    unsigned: tuple[bool, bool] = (True, True),
):
    region = region or MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    svd_regions = svd_regions or (MemoryRegionBinding("PERIPH", 0x40000000, 0x100, "r--"),)
    binding = replace(
        env.binding,
        memory_regions=(region, *extra_regions),
        svd_readable_regions=svd_regions,
    )
    items = [
        (0, _byte("low", addresses[0], region, unsigned=unsigned[0])),
        (1, _byte("high", addresses[1], region, unsigned=unsigned[1])),
    ]
    return _freeze_prepared_plan(
        ("low", "high"), (items, []), [None, None],
        binding=binding, u16_pairs=(("low", "high"),),
    )


def test_combined_pair_avoids_split_reader_old_low_new_high(debug_env: DebugEnv) -> None:
    region = MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    peripheral = MemoryRegionBinding("PERIPH", 0x40000000, 0x100, "r--")
    binding = replace(
        debug_env.binding,
        memory_regions=(region,),
        svd_readable_regions=(peripheral,),
    )
    items = [
        (0, _byte("PC_send2[53]", 0x2001DC29, region)),
        (1, _byte("PC_send2[54]", 0x2001DC2A, region)),
    ]
    plan = _freeze_prepared_plan(
        ("PC_send2[53]", "PC_send2[54]"),
        (items, []),
        [None, None],
        binding=binding,
        u16_pairs=(("PC_send2[53]", "PC_send2[54]"),),
    )
    calls: list[tuple[int, int]] = []

    async def read(address: int, size: int) -> bytes:
        calls.append((address, size))
        if (address, size) == (0x2001DC29, 2):
            return b"\xff\x01"  # two read8 operations crossed an update
        assert (address, size) == (0x2001DC28, 4)
        return b"\x00\x00\x01\x00"

    result = asyncio.run(_execute_prepared("prepared", plan, read))
    assert result.ok
    assert [item.value.value for item in result.data] == [0, 1]
    assert calls == [(0x2001DC28, 4), (0x2001DC28, 4)]


def test_protected_pair_accepts_latest_equal_snapshots_and_ignores_padding(
    debug_env: DebugEnv,
) -> None:
    plan = _pair_plan(debug_env)
    sequence = iter((
        b"\x01\x00\x00\x01",
        b"\x02\x05\x06\x02",
        b"\x03\x05\x06\x03",
    ))
    calls = []

    async def read(address: int, size: int) -> bytes:
        calls.append((address, size))
        return next(sequence)

    result = asyncio.run(_execute_prepared("prepared", plan, read))
    assert result.ok
    assert [item.value.value for item in result.data] == [5, 6]
    assert calls == [(0x2001DC28, 4)] * 3

    sequence = iter((b"\x01\x05\x06\x01", b"\x02\x05\x06\x02"))
    result = asyncio.run(_execute_prepared("prepared", plan, read))
    assert [item.value.value for item in result.data] == [5, 6]
    assert calls[-2:] == [(0x2001DC28, 4)] * 2


def test_protected_pair_unstable_or_broken_word_produces_item_gaps(
    debug_env: DebugEnv,
) -> None:
    plan = _pair_plan(debug_env)
    scenarios = (
        ([b"\x00\x00\x00\x00", b"\x00\x01\x01\x00", b"\x00\x02\x02\x00"], "DEBUG_READ_UNSTABLE", 3),
        ([RuntimeError("unavailable")], "DEBUG_READ_UNAVAILABLE", 1),
        ([b"\x00\x01\x02"], "DEBUG_PARTIAL_READ", 1),
        ([b"\x00\x01\x02\x03", RuntimeError("unavailable")], "DEBUG_READ_UNAVAILABLE", 2),
        ([b"\x00\x01\x02\x03", b"\x00"], "DEBUG_PARTIAL_READ", 2),
        ([bytearray(b"\x00\x01\x02\x03")], "DEBUG_PARTIAL_READ", 1),
    )
    for snapshots, expected, count in scenarios:
        remaining = iter(snapshots)
        calls = []

        async def read(address: int, size: int) -> bytes:
            calls.append((address, size))
            value = next(remaining)
            if isinstance(value, Exception):
                raise value
            return value

        result = asyncio.run(_execute_prepared("prepared", plan, read))
        assert result.ok
        assert [(item.status, item.code) for item in result.data] == [
            ("error", expected), ("error", expected)
        ]
        assert calls == [(0x2001DC28, 4)] * count


def test_overlapping_reversed_pairs_share_one_word_and_leave_neighbor_ordinary(
    debug_env: DebugEnv,
) -> None:
    region = MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    binding = replace(
        debug_env.binding, memory_regions=(region,),
        svd_readable_regions=(MemoryRegionBinding("PERIPH", 0x40000000, 0x100, "r--"),),
    )
    names = ("byte55", "byte54", "byte52", "byte53")
    addresses = (0x2001DC2B, 0x2001DC2A, 0x2001DC28, 0x2001DC29)
    plan = _freeze_prepared_plan(
        names,
        ([(index, _byte(name, address, region)) for index, (name, address) in enumerate(zip(names, addresses))], []),
        [None] * 4,
        binding=binding,
        u16_pairs=(("byte53", "byte54"), ("byte52", "byte53"), ("byte54", "byte53")),
    )
    calls = []
    words = iter((b"\x00\x01\x02\x03", b"\x05\x01\x02\x03", b"\x05\x01\x02\x03"))

    async def read(address: int, size: int) -> bytes:
        calls.append((address, size))
        if size == 4:
            return next(words)
        assert (address, size) == (0x2001DC2B, 1)
        return b"\x03"

    result = asyncio.run(_execute_prepared("prepared", plan, read))
    assert result.ok
    assert [item.expression for item in result.data] == list(names)
    assert [item.value.value for item in result.data] == [3, 2, 5, 1]
    assert calls == [(0x2001DC28, 4)] * 3 + [(0x2001DC2B, 1)]


@pytest.mark.parametrize("boundary", [
    "read-only", "write-only", "overlap-read-only", "overlap-write-only",
    "outside-sram", "cross-word", "nonadjacent", "non-u8", "svd-padding",
])
def test_ineligible_pairs_keep_ordinary_read_plan(
    debug_env: DebugEnv, boundary: str,
) -> None:
    region = MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    extras = ()
    svd = None
    addresses = (0x2001DC29, 0x2001DC2A)
    unsigned = (True, True)
    if boundary == "read-only":
        region = replace(region, attributes="r--")
    elif boundary == "write-only":
        region = replace(region, attributes="-w-")
    elif boundary == "overlap-read-only":
        extras = (MemoryRegionBinding("PADDING", 0x2001DC28, 1, "r--"),)
    elif boundary == "overlap-write-only":
        extras = (MemoryRegionBinding("PADDING", 0x2001DC28, 1, "-w-"),)
    elif boundary == "outside-sram":
        region = MemoryRegionBinding("OTHER", 0x22000000, 0x100, "rw-")
        addresses = (0x22000001, 0x22000002)
    elif boundary == "cross-word":
        addresses = (0x2001DC2B, 0x2001DC2C)
    elif boundary == "nonadjacent":
        addresses = (0x2001DC29, 0x2001DC2B)
    elif boundary == "non-u8":
        unsigned = (True, False)
    elif boundary == "svd-padding":
        svd = (MemoryRegionBinding("SVD", 0x2001DC28, 1, "r--"),)
    plan = _pair_plan(
        debug_env, region=region, extra_regions=extras,
        svd_regions=svd, addresses=addresses, unsigned=unsigned,
    )
    assert plan.protected_words == ()


def test_unresolved_operand_keeps_ordinary_error_and_other_read(debug_env: DebugEnv) -> None:
    region = MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    binding = replace(
        debug_env.binding, memory_regions=(region,),
        svd_readable_regions=(MemoryRegionBinding("PERIPH", 0x40000000, 0x100, "r--"),),
    )
    plan = _freeze_prepared_plan(
        ("low", "high"), ([(0, _byte("low", 0x2001DC29, region))], []),
        [None, DebugReadItem("high", "error", code="DWARF_VARIABLE_NOT_FOUND")],
        binding=binding, u16_pairs=(("low", "high"),),
    )
    calls = []

    async def read(address: int, size: int) -> bytes:
        calls.append((address, size))
        return b"\x07"

    result = asyncio.run(_execute_prepared("prepared", plan, read))
    assert result.ok
    assert result.data[0].value.value == 7
    assert result.data[1].code == "DWARF_VARIABLE_NOT_FOUND"
    assert calls == [(0x2001DC29, 1)]


def test_protected_read_preserves_cancellation_and_provenance_failure(
    debug_env: DebugEnv,
) -> None:
    plan = _pair_plan(debug_env)

    async def changed(_address: int, _size: int) -> bytes:
        raise _ReadFailure("DEBUG_PLAN_CHANGED", "changed")

    result = asyncio.run(_execute_prepared("prepared", plan, changed))
    assert not result.ok and result.code == "DEBUG_PLAN_CHANGED"

    async def cancelled(_address: int, _size: int) -> bytes:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_execute_prepared("prepared", plan, cancelled))


@pytest.mark.parametrize("dwarf_type, expected", [
    (DwarfType("integer", "uint8_t", 1, signed=False, encoding="unsigned"), True),
    (DwarfType("integer", "int8_t", 1, signed=True, encoding="signed"), False),
    (DwarfType("boolean", "bool", 1, signed=False, encoding="boolean"), False),
    (DwarfType("enum", "enum", 1, signed=False, encoding="unsigned"), False),
])
def test_dwarf_type_facts_control_private_unsigned_byte_qualification(
    debug_env: DebugEnv, dwarf_type: DwarfType, expected: bool,
) -> None:
    selected = DwarfSelection("byte", 0x2001DC29, dwarf_type)
    catalog = type("Catalog", (), {"lookup": lambda self, expression: selected})()
    region = MemoryRegionBinding("SRAM", 0x2001DC00, 0x100, "rw-")
    binding = replace(debug_env.binding, memory_regions=(region,))
    assert _variable(binding, catalog, "byte").unsigned_byte is expected


def test_installed_pyocd_odd_two_bytes_split_but_aligned_word_is_one_access() -> None:
    memory_module = pytest.importorskip("pyocd.core.memory_interface")

    class OfflineMemory(memory_module.MemoryInterface):
        def __init__(self) -> None:
            self.calls = []

        def read8(self, address: int, **_kwargs: object) -> int:
            self.calls.append((8, address))
            return 0

        def read16(self, address: int, **_kwargs: object) -> int:
            self.calls.append((16, address))
            return 0

        def read_memory_block32(self, address: int, size: int) -> list[int]:
            self.calls.append((32, address, size))
            return [0x00010000] * size

    reader = OfflineMemory()
    assert reader.read_memory_block8(0x2001DC29, 2) == [0, 0]
    assert reader.calls == [(8, 0x2001DC29), (8, 0x2001DC2A)]
    reader.calls.clear()
    assert reader.read_memory_block8(0x2001DC28, 4) == [0, 0, 1, 0]
    assert reader.calls == [(32, 0x2001DC28, 1)]
