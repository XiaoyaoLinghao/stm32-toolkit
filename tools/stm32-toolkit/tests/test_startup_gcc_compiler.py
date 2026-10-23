"""Real ARM GNU assembly/link checks for the generated STARTUP-GCC file.

These tests use the coordinator-supplied offline ARM GNU toolchain.  On this
known host a missing compiler is a test failure, never a silent skip: the
generated reset path, vector words, weak/strong handlers, stack/heap symbols
and constructor retention are part of the slice contract.

Symbols and section bounds are read from the ELF itself (pyelftools) rather
than from ``nm`` text: GNU symbol values for Thumb code need not carry the
Thumb bit in every output form, so code vectors are compared on the aligned
address and their Thumb bit is asserted independently.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
import pytest

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import StartupOptions, apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.project_model import load_project_model

from startup_gcc_fixture import (
    GENERATED_SOURCE,
    STARTUP_SOURCE,
    SYNTHETIC_STARTUP,
    startup_repo,
)

GNU_BIN = Path(
    os.environ.get(
        "STM32TK_ARM_GNU_BIN",
        r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin",
    )
)
VECTOR_COUNT = 24
RESERVED = (7, 8, 9, 10, 13)
ALIGNED_SYMBOLS = ("_sidata", "_sdata", "_edata", "_sbss", "_ebss")


def _tool(name: str) -> str:
    candidates = [GNU_BIN / f"{name}.exe", GNU_BIN / name]
    resolved = shutil.which(name)
    if resolved:
        candidates.append(Path(resolved))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise AssertionError(
        f"required offline ARM GNU tool {name!r} was not found in {GNU_BIN}"
    )


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "command failed:\n"
            + " ".join(command)
            + "\nstdout:\n"
            + result.stdout
            + "\nstderr:\n"
            + result.stderr
        )
    return result


def _migrate_and_render(tmp_path: Path, *, core: str, name: str):
    repo = startup_repo(tmp_path, name=name, core=core)
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert apply_keil_conversion(plan).ok is True
    configuration = plan_project_configuration(load_project_model(repo))
    assert configuration.blockers == ()
    linker = next(
        file for file in configuration.files if file.path == "linker/stm32tk.ld"
    ).after_bytes
    build = tmp_path / f"build-{name}"
    build.mkdir()
    linker_path = build / "stm32tk.ld"
    linker_path.write_bytes(linker)
    return repo, build, linker_path


def _compile_objects(
    repo: Path,
    build: Path,
    *,
    cpu_flag: str,
    defines: tuple[str, ...] = (),
) -> list[Path]:
    gcc = _tool("arm-none-eabi-gcc")
    objects = []
    for source, name in (
        (repo / GENERATED_SOURCE, "startup.o"),
        (repo / "Main" / "main.c", "main.o"),
    ):
        obj = build / name
        _run(
            [
                gcc,
                cpu_flag,
                "-mthumb",
                "-ffunction-sections",
                "-fdata-sections",
                "-fno-common",
                "-Og",
                "-g3",
                *defines,
                "-c",
                str(source),
                "-o",
                str(obj),
            ],
            cwd=build,
        )
        objects.append(obj)
    return objects


def _link(
    build: Path,
    linker_path: Path,
    objects: list[Path],
    *,
    cpu_flag: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _tool("arm-none-eabi-gcc"),
            cpu_flag,
            "-mthumb",
            "-nostartfiles",
            "-T",
            str(linker_path),
            f"-Wl,-Map={build / 'firmware.map'}",
            "-Wl,--gc-sections",
            *[str(obj) for obj in objects],
            "-o",
            str(build / "firmware.elf"),
        ],
        cwd=build,
        capture_output=True,
        text=True,
        check=False,
    )


def _compile(
    repo: Path,
    build: Path,
    linker_path: Path,
    *,
    cpu_flag: str,
    defines: tuple[str, ...] = (),
) -> tuple[Path, Path, Path]:
    """Compile real objects, then link them with the newlib constructor path."""
    objects = _compile_objects(repo, build, cpu_flag=cpu_flag, defines=defines)
    result = _link(build, linker_path, objects, cpu_flag=cpu_flag)
    if result.returncode != 0:
        raise AssertionError(
            "link failed:\nstdout:\n" + result.stdout + "\nstderr:\n" + result.stderr
        )
    return build / "firmware.elf", build / "firmware.map", objects[1]


def _elf_symbols(elf: Path) -> dict[str, list[dict[str, object]]]:
    symbols: dict[str, list[dict[str, object]]] = {}
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        table = parsed.get_section_by_name(".symtab")
        assert isinstance(table, SymbolTableSection), "ELF has no symbol table"
        for symbol in table.iter_symbols():
            symbols.setdefault(symbol.name, []).append(
                {
                    "value": int(symbol["st_value"]),
                    "size": int(symbol["st_size"]),
                    "type": symbol["st_info"]["type"],
                    "bind": symbol["st_info"]["bind"],
                }
            )
    return symbols


def _symbol(
    symbols: dict[str, list[dict[str, object]]],
    name: str,
    *,
    bind: str | None = None,
) -> dict[str, object]:
    entries = symbols.get(name)
    assert entries, f"missing ELF symbol {name}"
    if bind is not None:
        selected = [entry for entry in entries if entry["bind"] == bind]
        assert selected, f"symbol {name} has no {bind} entry: {entries}"
        return selected[0]
    return entries[0]


def _value(symbols: dict[str, list[dict[str, object]]], name: str) -> int:
    return int(_symbol(symbols, name)["value"])


def _elf_sections(elf: Path) -> dict[str, dict[str, int]]:
    sections: dict[str, dict[str, int]] = {}
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        for section in parsed.iter_sections():
            sections[section.name] = {
                "address": int(section["sh_addr"]),
                "size": int(section["sh_size"]),
                "alignment": int(section["sh_addralign"]),
            }
    return sections


def _section_data(elf: Path, name: str) -> bytes:
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        section = parsed.get_section_by_name(name)
        assert section is not None, f"missing ELF section {name}"
        return section.data()


def _load_image_bytes(elf: Path, address: int, size: int) -> bytes:
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        for segment in parsed.iter_segments():
            if segment["p_type"] != "PT_LOAD":
                continue
            start = int(segment["p_paddr"])
            file_size = int(segment["p_filesz"])
            if start <= address and address + size <= start + file_size:
                handle.seek(int(segment["p_offset"]) + address - start)
                return handle.read(size)
    raise AssertionError(f"no PT_LOAD segment covers 0x{address:08x}+{size}")


def _entry_point(elf: Path) -> int:
    with elf.open("rb") as handle:
        return int(ELFFile(handle).header["e_entry"])


def _vector_words(elf: Path, build: Path) -> bytes:
    output = build / "vectors.bin"
    _run(
        [
            _tool("arm-none-eabi-objcopy"),
            "-O",
            "binary",
            "--only-section=.isr_vector",
            str(elf),
            str(output),
        ],
        cwd=build,
    )
    return output.read_bytes()


def _object_section_alignment(obj: Path, name: str) -> int:
    with obj.open("rb") as handle:
        parsed = ELFFile(handle)
        section = parsed.get_section_by_name(name)
        assert section is not None, f"missing object section {name}"
        return int(section["sh_addralign"])


def _fixture_vectors() -> tuple[str | None, ...]:
    """Independent DCD order/count from the authored synthetic fixture."""
    result: list[str | None] = []
    in_vectors = False
    for line in SYNTHETIC_STARTUP.splitlines():
        text = line.strip()
        if text.startswith("__Vectors ") and " DCD " in text:
            in_vectors = True
            value = text.split(" DCD ", 1)[1].strip()
        elif text.startswith("__Vectors_End"):
            break
        elif in_vectors and text.startswith("DCD "):
            value = text[4:].strip()
        else:
            continue
        result.append(None if value == "0" else value)
    return tuple(result)


def test_cortex_m4_full_runtime_vector_and_handler_assertions(tmp_path):
    repo, build, linker = _migrate_and_render(tmp_path, core="Cortex-M4", name="m4")
    generated = (repo / GENERATED_SOURCE).read_text("utf-8")
    assert ".cpu cortex-m4" in generated

    elf, map_file, main_object = _compile(
        repo,
        build,
        linker,
        cpu_flag="-mcpu=cortex-m4",
        defines=("-DSTM32TK_STRONG_IRQ",),
    )
    symbols = _elf_symbols(elf)
    sections = _elf_sections(elf)
    vector_bytes = _vector_words(elf, build)
    words = list(struct.unpack(f"<{len(vector_bytes) // 4}I", vector_bytes))

    # The fixture inputs are genuinely byte-aligned: this is exactly the case
    # the generated word-wise copy/clear loop must handle safely.
    assert _object_section_alignment(main_object, ".data.initialized_value") == 1
    assert _object_section_alignment(main_object, ".bss.zeroed_value") == 1

    expected = _fixture_vectors()
    assert len(expected) == VECTOR_COUNT == len(words)
    assert sections[".isr_vector"]["address"] == _value(symbols, "__Vectors")
    assert sections[".isr_vector"]["size"] == VECTOR_COUNT * 4
    assert _value(symbols, "__Vectors_End") - _value(symbols, "__Vectors") == VECTOR_COUNT * 4
    assert _value(symbols, "__Vectors_Size") == VECTOR_COUNT * 4

    stack_top = _value(symbols, "__StackTop")
    initial_sp = _value(symbols, "__initial_sp")
    assert words[0] == initial_sp == stack_top
    assert initial_sp % 8 == 0
    assert _value(symbols, "__StackTop") - _value(symbols, "__StackLimit") == 0x1000

    for index, name in enumerate(expected):
        if name is None:
            assert words[index] == 0, f"reserved vector {index} is not zero"
            continue
        if index == 0:
            assert words[index] == initial_sp
            continue
        symbol = _symbol(symbols, name)
        assert words[index] & 1 == 1, f"vector {index} ({name}) lacks the Thumb bit"
        assert words[index] & ~1 == int(symbol["value"]) & ~1, (
            f"vector {index} ({name}) does not match its ELF symbol"
        )
    assert [index for index in RESERVED if words[index] != 0] == []

    # Strong C override wins; weak unimplemented IRQs remain aliases.
    # pyelftools reports real ELF bindings (STB_GLOBAL/STB_WEAK), never the
    # shortened GLOBAL/WEAK spellings.
    strong = _symbol(symbols, "WWDG_IRQHandler", bind="STB_GLOBAL")
    assert strong["type"] == "STT_FUNC"
    assert words[23] & 1 == 1
    assert words[23] & ~1 == int(strong["value"]) & ~1

    default_handler = _symbol(symbols, "Default_Handler", bind="STB_WEAK")
    weak_tim2 = _symbol(symbols, "TIM2_IRQHandler", bind="STB_WEAK")
    assert int(weak_tim2["value"]) & ~1 == int(default_handler["value"]) & ~1
    assert words[17] & 1 == 1
    assert words[17] & ~1 == int(weak_tim2["value"]) & ~1

    assert _value(symbols, "__HeapLimit") - _value(symbols, "__HeapBase") == 0x400
    assert _value(symbols, "__heap_base") == _value(symbols, "__HeapBase")
    assert _value(symbols, "__heap_limit") == _value(symbols, "__HeapLimit")
    assert _entry_point(elf) & ~1 == _value(symbols, "Reset_Handler") & ~1
    assert _symbol(symbols, "Reset_Handler", bind="STB_WEAK")["type"] == "STT_FUNC"

    # The real newlib constructor path is linked, not stubbed.
    assert _symbol(symbols, "__libc_init_array", bind="STB_GLOBAL")["type"] == "STT_FUNC"
    assert _symbol(symbols, "main", bind="STB_GLOBAL")["type"] == "STT_FUNC"
    assert _symbol(symbols, "_init", bind="STB_WEAK")["type"] == "STT_FUNC"
    assert _symbol(symbols, "_fini", bind="STB_WEAK")["type"] == "STT_FUNC"

    # Whole-word copy/clear contract: the linked addresses, byte counts and
    # .data load source used by the four-byte loop must be aligned.  The input
    # objects are byte-aligned (asserted above), so GNU ld may keep the output
    # section metadata at sh_addralign 1; that is not the runtime contract.
    for name in ALIGNED_SYMBOLS:
        assert _value(symbols, name) % 4 == 0, f"{name} is not 4-byte aligned"

    data_section = sections[".data"]
    bss_section = sections[".bss"]
    assert data_section["size"] > 0
    assert bss_section["size"] > 0
    assert data_section["address"] % 4 == 0
    assert data_section["size"] % 4 == 0
    assert bss_section["address"] % 4 == 0
    assert bss_section["size"] % 4 == 0

    sdata = _value(symbols, "_sdata")
    edata = _value(symbols, "_edata")
    sbss = _value(symbols, "_sbss")
    ebss = _value(symbols, "_ebss")
    assert data_section["address"] == sdata
    assert data_section["address"] + data_section["size"] == edata
    assert bss_section["address"] == sbss
    assert bss_section["address"] + bss_section["size"] == ebss
    assert _value(symbols, "_sidata") % 4 == 0

    data_bytes = _section_data(elf, ".data")
    assert len(data_bytes) == edata - sdata
    assert len(data_bytes) >= 4
    assert _load_image_bytes(elf, _value(symbols, "_sidata"), len(data_bytes)) == data_bytes

    # The C constructor really is retained in the linked .init_array.
    init_section = sections[".init_array"]
    init_start = _value(symbols, "__init_array_start")
    init_end = _value(symbols, "__init_array_end")
    assert init_section["address"] == init_start
    assert init_section["address"] % 4 == 0
    assert init_end - init_start == init_section["size"]
    assert init_section["size"] >= 4
    init_bytes = _section_data(elf, ".init_array")
    init_words = struct.unpack(f"<{len(init_bytes) // 4}I", init_bytes)
    constructor = _value(symbols, "synthetic_constructor")
    assert constructor != 0
    assert any(word & ~1 == constructor & ~1 for word in init_words)

    # GNU ld drops empty .preinit_array/.fini_array output sections.  The
    # preinit boundary symbols are materialized and must bracket a zero-byte
    # span.  An unreferenced empty fini array may omit its hidden symbols and
    # section entirely, so validate them only when they exist.
    pre_start = _value(symbols, "__preinit_array_start")
    pre_end = _value(symbols, "__preinit_array_end")
    assert pre_start == pre_end, "__preinit_array must remain an empty span"
    assert pre_start % 4 == 0
    preinit_section = sections.get(".preinit_array")
    if preinit_section is not None:
        assert preinit_section["size"] == 0

    fini_section = sections.get(".fini_array")
    if fini_section is not None:
        assert fini_section["size"] == 0
    for name in ("__fini_array_start", "__fini_array_end"):
        if name in symbols:
            assert _value(symbols, name) % 4 == 0
    if "__fini_array_start" in symbols or "__fini_array_end" in symbols:
        assert "__fini_array_start" in symbols and "__fini_array_end" in symbols
        assert _value(symbols, "__fini_array_start") == _value(
            symbols, "__fini_array_end"
        )

    map_text = map_file.read_text("utf-8")
    assert ".init_array" in map_text
    assert "__libc_init_array" in map_text
    assert "_sidata" in map_text
    assert "_sdata" in map_text
    assert "_sbss" in map_text
    assert "overflow" not in map_text.lower()


def test_emitted_assert_refuses_a_padded_data_copy(tmp_path):
    """An unaligned RAM origin must not link a silently corrupt .data copy.

    The input objects and the generated script stay byte-for-byte as emitted;
    only the RAM origin is made odd.  GNU ld then places padding at the start
    of .data, so LOADADDR(.data) points at leading bytes that _sdata skips.
    The emitted cmsis-gcc-v1 guard must refuse the link instead of producing
    an ELF whose word-wise copy shifts .data contents.
    """
    repo, build, linker = _migrate_and_render(
        tmp_path, core="Cortex-M4", name="m4-unsafe"
    )
    script = linker.read_text("utf-8")
    assert "ASSERT(ADDR(.data) == _sdata" in script
    assert "ASSERT(SIZEOF(.data) == _edata - _sdata" in script
    # The unsafe layout below keeps this ALIGN(4) in place: the padding it
    # creates is exactly what the new copy-source guard must reject.
    assert "  .data :\n  {\n    . = ALIGN(4);\n    _sdata = .;" in script

    unsafe = script.replace(
        "ORIGIN = 0x20000000,",
        "ORIGIN = 0x20000001,",
        1,
    )
    assert unsafe != script
    unsafe_linker = build / "unsafe.ld"
    unsafe_linker.write_text(unsafe, encoding="utf-8")

    objects = _compile_objects(repo, build, cpu_flag="-mcpu=cortex-m4")
    result = _link(build, unsafe_linker, objects, cpu_flag="-mcpu=cortex-m4")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert (
        "cmsis-gcc-v1 requires the .data copy source to start at _sdata" in output
    )
    assert not (build / "firmware.elf").exists()


@pytest.mark.parametrize(
    ("core", "cpu_flag", "cpu_directive"),
    [
        ("Cortex-M3", "-mcpu=cortex-m3", ".cpu cortex-m3"),
        ("Cortex-M7", "-mcpu=cortex-m7", ".cpu cortex-m7"),
    ],
)
def test_supported_m3_and_m7_cpu_selection_links_compatibly(
    tmp_path, core: str, cpu_flag: str, cpu_directive: str
):
    repo, build, linker = _migrate_and_render(
        tmp_path, core=core, name=core.replace("-", "").lower()
    )
    generated = (repo / GENERATED_SOURCE).read_text("utf-8")
    assert cpu_directive in generated

    elf, _map, _main_object = _compile(repo, build, linker, cpu_flag=cpu_flag)
    symbols = _elf_symbols(elf)
    sections = _elf_sections(elf)
    vector_bytes = _vector_words(elf, build)
    words = list(struct.unpack(f"<{len(vector_bytes) // 4}I", vector_bytes))

    assert len(words) == VECTOR_COUNT
    assert sections[".isr_vector"]["size"] == VECTOR_COUNT * 4
    assert words[0] == _value(symbols, "__initial_sp") == _value(symbols, "__StackTop")
    assert words[0] % 8 == 0
    reset = _value(symbols, "Reset_Handler")
    assert words[1] & 1 == 1
    assert words[1] & ~1 == reset & ~1
    assert _value(symbols, "__StackTop") - _value(symbols, "__StackLimit") == 0x1000
    assert _value(symbols, "__HeapLimit") - _value(symbols, "__HeapBase") == 0x400
    for name in ALIGNED_SYMBOLS:
        assert _value(symbols, name) % 4 == 0
