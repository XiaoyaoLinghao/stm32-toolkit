"""Real ARM GNU assembly/link checks for the generated STARTUP-GCC file.

These tests use the coordinator-supplied offline ARM GNU toolchain.  On this
known host a missing compiler is a test failure, never a silent skip: the
generated reset path, vector words, weak/strong handlers, stack/heap symbols
and constructor retention are part of the slice contract.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import StartupOptions, apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.project_model import load_project_model

from startup_gcc_fixture import GENERATED_SOURCE, STARTUP_SOURCE, startup_repo

GNU_BIN = Path(
    os.environ.get(
        "STM32TK_ARM_GNU_BIN",
        r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin",
    )
)
VECTOR_COUNT = 24
RESERVED = (7, 8, 9, 10, 13)


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


def _compile(
    repo: Path,
    build: Path,
    linker_path: Path,
    *,
    cpu_flag: str,
    defines: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    gcc = _tool("arm-none-eabi-gcc")
    elf = build / "firmware.elf"
    map_file = build / "firmware.map"
    command = [
        gcc,
        cpu_flag,
        "-mthumb",
        "-ffunction-sections",
        "-fdata-sections",
        "-Og",
        "-g3",
        "-nostartfiles",
        "-T",
        str(linker_path),
        f"-Wl,-Map={map_file}",
        "-Wl,--gc-sections",
        *defines,
        str(repo / GENERATED_SOURCE),
        str(repo / "Main" / "main.c"),
        "-o",
        str(elf),
    ]
    _run(command, cwd=build)
    return elf, map_file


def _symbols(elf: Path) -> dict[str, list[tuple[int, str]]]:
    output = _run([_tool("arm-none-eabi-nm"), "-n", str(elf)], cwd=elf.parent).stdout
    symbols: dict[str, list[tuple[int, str]]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        address, kind, name = parts
        try:
            value = int(address, 16)
        except ValueError:
            continue
        symbols.setdefault(name, []).append((value, kind))
    return symbols


def _symbol(symbols: dict[str, list[tuple[int, str]]], name: str, *, kind: str | None = None) -> int:
    entries = symbols.get(name)
    assert entries, f"missing symbol {name}"
    if kind is not None:
        selected = [value for value, entry_kind in entries if entry_kind == kind]
        assert selected, f"symbol {name} has no {kind} entry: {entries}"
        return selected[0]
    return entries[0][0]


def _sections(elf: Path) -> dict[str, int]:
    output = _run([_tool("arm-none-eabi-objdump"), "-h", str(elf)], cwd=elf.parent).stdout
    sizes: dict[str, int] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        name = parts[1]
        try:
            sizes[name] = int(parts[2], 16)
        except ValueError:
            continue
    return sizes


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


def _entry_point(elf: Path, build: Path) -> int:
    output = _run([_tool("arm-none-eabi-objdump"), "-f", str(elf)], cwd=build).stdout
    match = re.search(r"start address 0x([0-9a-fA-F]+)", output)
    assert match is not None, output
    return int(match.group(1), 16)


def test_cortex_m4_full_runtime_vector_and_handler_assertions(tmp_path):
    repo, build, linker = _migrate_and_render(tmp_path, core="Cortex-M4", name="m4")
    generated = (repo / GENERATED_SOURCE).read_text("utf-8")
    assert ".cpu cortex-m4" in generated

    elf, map_file = _compile(
        repo,
        build,
        linker,
        cpu_flag="-mcpu=cortex-m4",
        defines=("-DSTM32TK_STRONG_IRQ",),
    )
    symbols = _symbols(elf)
    sections = _sections(elf)
    vector_bytes = _vector_words(elf, build)
    words = list(struct.unpack(f"<{len(vector_bytes) // 4}I", vector_bytes))

    assert len(words) == VECTOR_COUNT
    assert sections[".isr_vector"] == VECTOR_COUNT * 4

    stack_top = _symbol(symbols, "__StackTop")
    initial_sp = _symbol(symbols, "__initial_sp")
    reset = _symbol(symbols, "Reset_Handler")
    assert words[0] == initial_sp == stack_top
    assert initial_sp % 8 == 0
    assert reset & 1 == 1
    assert words[1] == reset
    assert _entry_point(elf, build) & ~1 == reset & ~1

    for index in RESERVED:
        assert words[index] == 0

    strong = _symbol(symbols, "WWDG_IRQHandler", kind="T")
    assert strong & 1 == 1
    assert words[23] == strong

    weak_aliases = symbols["TIM2_IRQHandler"]
    assert any(kind in ("W", "w", "t") for _value, kind in weak_aliases)
    default_handler = _symbol(symbols, "Default_Handler")
    weak_tim2 = weak_aliases[0][0]
    assert weak_tim2 == default_handler
    assert words[17] == weak_tim2

    assert _symbol(symbols, "__StackTop") - _symbol(symbols, "__StackLimit") == 0x1000
    assert _symbol(symbols, "__HeapLimit") - _symbol(symbols, "__HeapBase") == 0x400
    assert initial_sp == _symbol(symbols, "__StackTop")
    assert _symbol(symbols, "__heap_base") == _symbol(symbols, "__HeapBase")
    assert _symbol(symbols, "__heap_limit") == _symbol(symbols, "__HeapLimit")

    assert sections[".data"] > 0
    assert sections[".bss"] > 0
    assert sections.get(".init_array", 0) >= 4
    assert sections.get(".preinit_array", 0) >= 0
    assert sections.get(".fini_array", 0) >= 0

    map_text = map_file.read_text("utf-8")
    assert ".init_array" in map_text
    assert "__libc_init_array" in map_text
    assert "_sidata" in map_text
    assert "overflow" not in map_text.lower()


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

    elf, _map = _compile(repo, build, linker, cpu_flag=cpu_flag)
    symbols = _symbols(elf)
    sections = _sections(elf)
    vector_bytes = _vector_words(elf, build)
    words = list(struct.unpack(f"<{len(vector_bytes) // 4}I", vector_bytes))

    assert len(words) == VECTOR_COUNT
    assert sections[".isr_vector"] == VECTOR_COUNT * 4
    assert words[0] == _symbol(symbols, "__initial_sp") == _symbol(symbols, "__StackTop")
    assert words[0] % 8 == 0
    reset = _symbol(symbols, "Reset_Handler")
    assert reset & 1 == 1
    assert words[1] == reset
    assert _symbol(symbols, "__StackTop") - _symbol(symbols, "__StackLimit") == 0x1000
    assert _symbol(symbols, "__HeapLimit") - _symbol(symbols, "__HeapBase") == 0x400
