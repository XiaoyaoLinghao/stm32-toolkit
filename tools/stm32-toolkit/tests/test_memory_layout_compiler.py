"""Real ARM GNU link evidence for explicit multi-RAM managed placement.

The synthetic project is migrated with ``data`` in main RAM and
``bss``/``heap``/``stack`` in a second writable RAM, then linked with the
accepted startup fixture and the real newlib constructor path.  The ELF/MAP
are inspected for section VMAs, the .data load address, initialization
symbols, stack alignment and heap/stack sizes.  This is offline linked-image
evidence only; it says nothing about board, CCM or external-memory behavior.
"""

from __future__ import annotations

import struct

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.project_model import load_project_model

import test_startup_gcc_compiler as compiler
from startup_gcc_fixture import GENERATED_SOURCE
from test_memory_layout_migration import SPLIT, STARTUP, multi_ram_repo

CPU_FLAG = "-mcpu=cortex-m4"
FLASH_RANGE = (0x08000000, 0x100000)
MAIN_RAM_RANGE = (0x20000000, 0x30000)
SECOND_RAM_RANGE = (0x10000000, 0x10000)


def _within(address: int, size: int, region: tuple[int, int]) -> bool:
    return region[0] <= address and address + size <= region[0] + region[1]


def _migrate_and_render(tmp_path, name: str):
    repo = multi_ram_repo(tmp_path, name=name)
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=STARTUP,
        memory_layout=SPLIT,
    )
    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    assert (repo / GENERATED_SOURCE).is_file()

    configuration = plan_project_configuration(load_project_model(repo))
    assert configuration.blockers == ()
    linker_bytes = next(
        entry
        for entry in configuration.files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes
    build = tmp_path / f"build-{name}"
    build.mkdir()
    linker = build / "stm32tk.ld"
    linker.write_bytes(linker_bytes)
    return repo, build, linker, linker_bytes


def _link_ok(repo, build, linker):
    objects = compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )
    result = compiler._link(build, linker, objects, cpu_flag=CPU_FLAG)
    if result.returncode != 0:
        raise AssertionError(
            "link failed:\nstdout:\n" + result.stdout + "\nstderr:\n" + result.stderr
        )
    return build / "firmware.elf", build / "firmware.map"


def test_split_layout_links_with_real_section_vma_lma_and_symbol_evidence(tmp_path):
    repo, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "split", "split"
    )
    text = linker_bytes.decode("utf-8")
    assert "  .data :\n  {\n    . = ALIGN(4);\n    _sdata = .;" in text
    assert "  } > IRAM1 AT> IROM1" in text
    assert "  } > IRAM2\n\n  .heap" in text
    assert "  } > IRAM2\n\n  .stack" in text

    elf, map_file = _link_ok(repo, build, linker)
    symbols = compiler._elf_symbols(elf)
    sections = compiler._elf_sections(elf)
    value = lambda name: compiler._value(symbols, name)

    flash = sections[".isr_vector"]
    assert _within(flash["address"], flash["size"], FLASH_RANGE)
    assert _within(sections[".text"]["address"], sections[".text"]["size"], FLASH_RANGE)
    assert _within(sections[".init_array"]["address"], sections[".init_array"]["size"], FLASH_RANGE)

    data = sections[".data"]
    bss = sections[".bss"]
    heap = sections[".heap"]
    stack = sections[".stack"]
    assert data["size"] > 0
    assert bss["size"] > 0
    assert _within(data["address"], data["size"], MAIN_RAM_RANGE)
    assert _within(bss["address"], bss["size"], SECOND_RAM_RANGE)
    assert _within(heap["address"], heap["size"], SECOND_RAM_RANGE)
    assert _within(stack["address"], stack["size"], SECOND_RAM_RANGE)

    # The .data load address is in Flash, distinct from its RAM VMA, and the
    # flash bytes really are the linked .data image.
    sidata = value("_sidata")
    assert _within(sidata, data["size"], FLASH_RANGE)
    assert sidata != data["address"]
    data_bytes = compiler._section_data(elf, ".data")
    assert compiler._load_image_bytes(elf, sidata, len(data_bytes)) == data_bytes

    assert data["address"] == value("_sdata")
    assert data["address"] + data["size"] == value("_edata")
    assert bss["address"] == value("_sbss")
    assert bss["address"] + bss["size"] == value("_ebss")
    for name in ("_sidata", "_sdata", "_edata", "_sbss", "_ebss"):
        assert value(name) % 4 == 0

    # Exact reviewed sizes and 8-byte stack alignment survive the split.
    assert value("__HeapLimit") - value("__HeapBase") == 0x400
    assert value("__heap_base") == value("__HeapBase")
    assert value("__heap_limit") == value("__HeapLimit")
    assert value("__StackTop") - value("__StackLimit") == 0x1000
    assert value("__initial_sp") == value("__StackTop")
    assert value("__initial_sp") % 8 == 0
    assert _within(value("__StackLimit"), 0x1000, SECOND_RAM_RANGE)

    vector_bytes = compiler._vector_words(elf, build)
    words = list(struct.unpack(f"<{len(vector_bytes) // 4}I", vector_bytes))
    assert words[0] == value("__initial_sp")

    assert compiler._symbol(symbols, "__libc_init_array")["type"] == "STT_FUNC"
    assert compiler._symbol(symbols, "main")["type"] == "STT_FUNC"
    assert compiler._entry_point(elf) & ~1 == value("Reset_Handler") & ~1

    map_text = map_file.read_text("utf-8")
    assert "IRAM1" in map_text
    assert "IRAM2" in map_text
    assert "_sidata" in map_text
    assert "_sdata" in map_text
    assert "_sbss" in map_text
    assert "overflow" not in map_text.lower()


def test_too_small_second_ram_region_fails_the_link(tmp_path):
    repo, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "small", "small"
    )
    text = linker_bytes.decode("utf-8")
    assert "IRAM2 (rwx) : ORIGIN = 0x10000000, LENGTH = 0x00010000" in text
    unsafe = text.replace(
        "IRAM2 (rwx) : ORIGIN = 0x10000000, LENGTH = 0x00010000",
        "IRAM2 (rwx) : ORIGIN = 0x10000000, LENGTH = 0x00000100",
        1,
    )
    assert unsafe != text
    unsafe_linker = build / "too-small.ld"
    unsafe_linker.write_text(unsafe, encoding="utf-8")

    objects = compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )
    result = compiler._link(build, unsafe_linker, objects, cpu_flag=CPU_FLAG)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "IRAM2" in output
    assert "overflow" in output.lower()
    assert not (build / "firmware.elf").exists()
