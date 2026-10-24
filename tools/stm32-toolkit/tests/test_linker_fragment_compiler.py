"""Real ARM GNU evidence for the LINKER-FRAGMENT slice.

The 0x68000000/0x10000 external RAM and all section addresses are synthetic
test values, not board facts.  Every artifact stays below the synthetic
project root so ``validate_elf`` and the MAP validator see the same model.
No hardware is accessed.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from dataclasses import replace
from pathlib import Path

from elftools.elf.elffile import ELFFile
import pytest

from stm32_toolkit.build.identity import validate_elf
from stm32_toolkit.build.map_file import parse_map
from stm32_toolkit.build.model import BuildError
from stm32_toolkit.generation import apply_project_configuration, plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.migration import StartupOptions, apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.project_model import (
    MemoryRegion,
    MemorySpec,
    load_project_model,
)

import test_startup_gcc_compiler as compiler
from startup_gcc_fixture import GENERATED_SOURCE, STARTUP_SOURCE, SYNTHETIC_STARTUP
from test_memory_layout_migration import STARTUP
from test_migration_plan import FRAMEWORK_INCLUDE, build_repo

CPU_FLAG = "-mcpu=cortex-m4"
CPU_SETTING = 'IROM(0x08000000,0x100000) IRAM(0x20000000,0x30000) CPUTYPE("Cortex-M4")'
EXT = ExtraRegion("EXT_SRAM", 0x68000000, 0x10000, "rw-")
EXT_LAYOUT = MemoryLayout("IROM1", "IRAM1", "EXT_SRAM", "EXT_SRAM", "EXT_SRAM")
FIXED_ADDRESS = 0x68000010
FRAGMENT_PATH = "linker/user.ld"
MAIN_FRAGMENT_ADDRESS = 0x68000020
#: Explicit addresses make placement and deliberate relocation observable; a
#: bare section would simply follow the region cursor before ``.data``.
AUX_FRAGMENT_ADDRESS = 0x20000100
MOVED_AUX_ADDRESS = 0x20000200
FRAGMENT_TEXT = (
    "/* Authored synthetic NOLOAD fragment: no vendor or board facts. */\n"
    ".sram2 0x68000020 (NOLOAD) :\n"
    "{\n"
    "  . = ALIGN(8);\n"
    "  *(.sram2 .sram2.*)\n"
    "} > EXT_SRAM\n"
    "\n"
    ".sram3 0x20000100 (NOLOAD) :\n"
    "{\n"
    "  KEEP(*(.sram3.*))\n"
    "} > IRAM1\n"
)
FRAGMENT_C = (
    "/* Synthetic migrated source: fixed buffer plus fragment-owned objects. */\n"
    "__attribute__((at(0x68000010))) volatile unsigned int extra_buffer;\n"
    '__attribute__((section(".sram2.buf"))) volatile unsigned int frag_main[4];\n'
    '__attribute__((section(".sram3.keep"))) volatile unsigned int frag_aux[4];\n'
    "volatile unsigned int initialized_value = 0x12345678u;\n"
    "volatile unsigned int zeroed_value;\n"
    "\n"
    "void SystemInit(void) {}\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "    frag_main[0] = extra_buffer;\n"
    "    frag_aux[1] = initialized_value;\n"
    "    return (int)(zeroed_value + frag_main[0] + frag_aux[1]);\n"
    "}\n"
)

GNU_BIN = Path(
    os.environ.get(
        "STM32TK_ARM_GNU_BIN",
        r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin",
    )
)
CMAKE_BIN = Path(
    os.environ.get("STM32TK_CMAKE_BIN", r"C:/ST/STM32CubeCLT_1.22.0/CMake/bin")
)
NINJA_BIN = Path(
    os.environ.get("STM32TK_NINJA_BIN", r"C:/ST/STM32CubeCLT_1.22.0/Ninja/bin")
)


def _require_tool(base: Path, name: str) -> str:
    candidates = [base / f"{name}.exe", base / name]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise AssertionError(f"required offline tool {name!r} was not found in {base}")


def _fragment_repo(tmp_path: Path) -> Path:
    # ``build_repo`` creates ``base / name`` with a single ``mkdir``; materialize
    # the per-test base directory first.
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    repo = build_repo(
        base,
        name="fragment",
        files={"Main/main.c": FRAGMENT_C, STARTUP_SOURCE: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": CPU_SETTING,
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Startup", (("startup_synthetic.s", "2", STARTUP_SOURCE),)),
            ),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
        commit=True,
    )
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=STARTUP,
        memory_layout=EXT_LAYOUT,
        extra_regions=(EXT,),
    )
    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    manifest_path = repo / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generation"]["linkerFragment"] = FRAGMENT_PATH
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    fragment = repo / "linker" / "user.ld"
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text(FRAGMENT_TEXT, encoding="utf-8")
    return repo


def _configure(repo: Path, *, fragment_text: str | None = None):
    if fragment_text is not None:
        (repo / "linker" / "user.ld").write_text(fragment_text, encoding="utf-8")
    model = load_project_model(repo)
    configuration = plan_project_configuration(model)
    assert configuration.blockers == (), configuration.blockers
    applied = apply_project_configuration(configuration)
    assert applied.ok is True, applied.to_dict()
    linker_bytes = next(
        item for item in configuration.files if item.path == "linker/stm32tk.ld"
    ).after_bytes
    return model, linker_bytes


def _compile_and_link(repo: Path, linker_bytes: bytes):
    build = repo / ".lf-test-build"
    build.mkdir(exist_ok=True)
    linker = build / "stm32tk.ld"
    linker.write_bytes(linker_bytes)
    objects = compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )
    result = compiler._link(build, linker, objects, cpu_flag=CPU_FLAG)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return build / "firmware.elf", build / "firmware.map"


def _elf_section_type(elf: Path, name: str) -> tuple[int, int, int]:
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        section = parsed.get_section_by_name(name)
        assert section is not None, f"missing ELF section {name}"
        return (
            int(section["sh_type"] == "SHT_NOBITS"),
            int(section["sh_flags"]),
            int(section["sh_addr"]),
        )


def _write_patched_elf(
    elf: Path,
    destination: Path,
    name: str,
    *,
    sh_type: int | None = None,
    sh_flags: int | None = None,
    sh_addr: int | None = None,
) -> Path:
    """Copy a real ELF and mutate one section header field in place.

    ELF32 little-endian ``Elf32_Shdr`` layout: sh_name 0, sh_type 4,
    sh_flags 8, sh_addr 12.  The copy stays a genuine parser input.
    """
    data = bytearray(elf.read_bytes())
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        sections = list(parsed.iter_sections())
        index = next(
            index for index, section in enumerate(sections) if section.name == name
        )
        shoff = int(parsed.header["e_shoff"])
        entsize = int(parsed.header["e_shentsize"])
    offset = shoff + index * entsize
    if sh_type is not None:
        struct.pack_into("<I", data, offset + 4, sh_type)
    if sh_flags is not None:
        struct.pack_into("<I", data, offset + 8, sh_flags)
    if sh_addr is not None:
        struct.pack_into("<I", data, offset + 12, sh_addr)
    destination.write_bytes(bytes(data))
    return destination


def _adjacent_ext_model(model):
    """A test-only map whose EXT_SRAM ends exactly at .sram2's start.

    The fragment still declares EXT_SRAM while the real ELF section fits in an
    adjacent, separately declared region.  That is the only shape in which a
    section can be inside the model map yet outside its selected fragment
    region.
    """
    regions = [
        region
        for region in model.memory.regions
        if region.name not in ("EXT_SRAM", "EXT_TAIL")
    ]
    return replace(
        model,
        memory=MemorySpec(
            source=model.memory.source,
            regions=tuple(
                regions
                + [
                    MemoryRegion("EXT_SRAM", 0x68000000, 0x20, "rw-"),
                    # Large enough for the managed bss/heap/stack that follow
                    # the fragment in EXT_SRAM; only .sram2 is retargeted by
                    # the region split under test.
                    MemoryRegion("EXT_TAIL", 0x68000020, 0x10000, "rw-"),
                ]
            ),
            stack_size=model.memory.stack_size,
            heap_size=model.memory.heap_size,
            layout=model.memory.layout,
            extra_region_names=("EXT_SRAM", "EXT_TAIL"),
        ),
    )


def test_fragment_sections_link_with_fixed_sections_and_multiple_rams(tmp_path):
    repo = _fragment_repo(tmp_path)
    model, linker_bytes = _configure(repo)
    text = linker_bytes.decode("utf-8")
    assert "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00010000" in text
    assert "  .sram2 0x68000020 (NOLOAD) :" in text
    assert "  .sram3 0x20000100 (NOLOAD) :" in text
    assert text.index(f".stm32tk.abs.{FIXED_ADDRESS:08x}") < text.index(".sram2") < text.index("  .data :")
    assert text.index(".sram2") < text.index(".sram3") < text.index("  .data :")

    elf, map_file = _compile_and_link(repo, linker_bytes)
    sections = compiler._elf_sections(elf)
    nobits, flags, address = _elf_section_type(elf, ".sram2")
    assert nobits == 1 and flags & 0x2
    assert address == MAIN_FRAGMENT_ADDRESS
    assert sections[".sram2"]["size"] == 16
    nobits, flags, address = _elf_section_type(elf, ".sram3")
    assert nobits == 1 and flags & 0x2
    assert address == AUX_FRAGMENT_ADDRESS
    assert sections[".sram3"]["size"] == 16
    assert sections[f".stm32tk.abs.{FIXED_ADDRESS:08x}"]["size"] == 4
    # Managed .data shares IRAM1 with the explicit fragment section.  Whether
    # GNU ld keeps its region cursor at the origin or after the explicit
    # address, the two allocated intervals must stay inside IRAM1 and disjoint.
    data = sections[".data"]
    assert 0x20000000 <= data["address"]
    assert data["address"] + data["size"] <= 0x20030000
    assert (
        data["address"] + data["size"] <= AUX_FRAGMENT_ADDRESS
        or AUX_FRAGMENT_ADDRESS + sections[".sram3"]["size"] <= data["address"]
    )
    assert sections[".bss"]["address"] >= 0x68000014

    evidence = validate_elf(elf, model)
    assert evidence.sections
    usage = {
        item.name: item
        for item in parse_map(
            map_file.read_text("utf-8"),
            model.memory.regions,
            "firmware.map",
            elf_sections=evidence.sections,
        )
    }
    assert set(usage) == {"IROM1", "IRAM1", "EXT_SRAM"}
    assert usage["EXT_SRAM"].used >= 16 + 4
    assert usage["IRAM1"].used >= 16 + 4


def test_real_elf_rejects_wrong_attributes_address_and_overlap(tmp_path):
    repo = _fragment_repo(tmp_path)
    model, linker_bytes = _configure(repo)
    elf, _map_file = _compile_and_link(repo, linker_bytes)
    validate_elf(elf, model)
    variants = repo / ".lf-test-build"

    loadable = _write_patched_elf(
        elf, variants / "loadable.elf", ".sram2", sh_type=1
    )
    with pytest.raises(BuildError) as caught:
        validate_elf(loadable, model)
    assert caught.value.code == "BUILD_ARTIFACT_INVALID"
    assert caught.value.details["rule"] == "fragmentLoadable"

    moved = _write_patched_elf(
        elf, variants / "moved.elf", ".sram2", sh_addr=MAIN_FRAGMENT_ADDRESS + 4
    )
    with pytest.raises(BuildError) as caught:
        validate_elf(moved, model)
    assert caught.value.details["rule"] == "fragmentAddress"

    # Every nonempty section carrying a declared name must stay allocated,
    # even when clearing SHF_ALLOC would otherwise hide it from the allocated
    # subset.  The copy remains a real, parseable ELF.
    unallocated = _write_patched_elf(
        elf, variants / "unallocated.elf", ".sram2", sh_flags=0
    )
    with pytest.raises(BuildError) as caught:
        validate_elf(unallocated, model)
    assert caught.value.details["rule"] == "fragmentNotAllocated"

    # A section inside the map but outside its selected region is refused by
    # the fragment-specific bound, not merely by the generic map check.
    adjacent = _adjacent_ext_model(model)
    with pytest.raises(BuildError) as caught:
        validate_elf(elf, adjacent)
    assert caught.value.details["rule"] == "fragmentOutOfRange"

    # A genuinely overlapping allocated section is not hidden by MAP interval
    # union accounting: .bss is moved into .sram2's real VMA range.
    overlapping = _write_patched_elf(
        elf, variants / "overlap.elf", ".bss", sh_addr=MAIN_FRAGMENT_ADDRESS + 2
    )
    with pytest.raises(BuildError) as caught:
        validate_elf(overlapping, model)
    assert caught.value.details["rule"] == "fragmentOverlap"


def test_narrowed_model_and_linker_capacity_are_refused(tmp_path):
    repo = _fragment_repo(tmp_path)
    model, linker_bytes = _configure(repo)
    elf, _map_file = _compile_and_link(repo, linker_bytes)
    validate_elf(elf, model)

    base_regions = [
        region for region in model.memory.regions if region.name != "EXT_SRAM"
    ]
    # The fixed buffer still fits this shortened region, but the materialized
    # fragment section no longer does; the generic map bound refuses it.
    shortened = MemoryRegion("EXT_SRAM", 0x68000000, 0x24, "rw-")
    narrowed = replace(
        model,
        memory=MemorySpec(
            source=model.memory.source,
            regions=tuple(base_regions + [shortened]),
            stack_size=model.memory.stack_size,
            heap_size=model.memory.heap_size,
            layout=model.memory.layout,
            extra_region_names=("EXT_SRAM",),
        ),
    )
    with pytest.raises(BuildError) as caught:
        validate_elf(elf, narrowed)
    assert caught.value.code == "BUILD_ARTIFACT_INVALID"
    assert caught.value.details["rule"] == "sectionOutOfRange"

    text = linker_bytes.decode("utf-8")
    shortened_text = text.replace(
        "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00010000",
        "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x0000000e",
        1,
    )
    assert shortened_text != text
    build = repo / ".lf-test-build"
    shortened_linker = build / "shortened.ld"
    shortened_linker.write_text(shortened_text, encoding="utf-8")
    elf.unlink()
    objects = compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )
    result = compiler._link(build, shortened_linker, objects, cpu_flag=CPU_FLAG)
    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert "overflow" in output or "will not fit" in output
    assert not elf.exists()


def test_generated_cmake_relinks_after_fragment_regeneration_and_clean_build(tmp_path):
    cmake = _require_tool(CMAKE_BIN, "cmake")
    _require_tool(NINJA_BIN, "ninja")
    _require_tool(GNU_BIN, "arm-none-eabi-gcc")
    repo = _fragment_repo(tmp_path)
    model, _linker_bytes = _configure(repo)
    elf_rel = model.build.elf
    assert elf_rel is not None
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        [str(GNU_BIN), str(CMAKE_BIN), str(NINJA_BIN), env.get("PATH", "")]
    )

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [cmake, *arguments],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        return result

    run("--preset", "arm-debug")
    run("--build", "--preset", "arm-debug")
    elf = repo.joinpath(*elf_rel.split("/"))
    first = elf.read_bytes()

    moved_text = FRAGMENT_TEXT.replace("0x20000100", "0x20000200", 1)
    assert moved_text != FRAGMENT_TEXT
    _configure(repo, fragment_text=moved_text)
    run("--build", "--preset", "arm-debug")
    second = elf.read_bytes()
    assert second != first
    assert compiler._elf_sections(elf)[".sram3"]["address"] == MOVED_AUX_ADDRESS

    # Explicit clean semantics remain available through the generated preset.
    run("--build", "--preset", "arm-debug", "--clean-first")
    assert compiler._elf_sections(elf)[".sram3"]["address"] == MOVED_AUX_ADDRESS
