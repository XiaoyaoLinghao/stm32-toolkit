"""Real ARM GNU link evidence for the explicit external-RAM map.

The synthetic 0x68000000/0x10000 region is a test capacity, not a board fact.
This is offline linked-image evidence only: the owner still has to initialize
external memory before any access.
"""

from __future__ import annotations

import io
import struct
from dataclasses import replace

from elftools.elf.elffile import ELFFile
import pytest

from stm32_toolkit.build.identity import BuildError, validate_elf
from stm32_toolkit.build.map_file import MapError, parse_map
from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.migration import apply_keil_conversion
from stm32_toolkit.project_model import (
    MemoryRegion,
    MemorySpec,
    load_project_model,
)
import stm32_toolkit.probe.flash as flash_mod

import test_startup_gcc_compiler as compiler
from test_extra_memory_regions_migration import EXT, _plan, extra_repo

CPU_FLAG = "-mcpu=cortex-m4"
FLASH_RANGE = (0x08000000, 0x100000)
MAIN_RAM_RANGE = (0x20000000, 0x30000)
EXT_RAM_RANGE = (0x68000000, 0x10000)
FIXED_ADDRESS = 0x68000010


def _within(address: int, size: int, region: tuple[int, int]) -> bool:
    return region[0] <= address and address + size <= region[0] + region[1]


def _migrate_and_render(tmp_path, name: str):
    repo = extra_repo(tmp_path, name=name)
    plan = _plan(repo)
    assert plan.extra_regions == (EXT,)
    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    model = load_project_model(repo)
    assert [region.name for region in model.memory.regions] == [
        "IROM1",
        "IRAM1",
        "EXT_SRAM",
    ]
    configuration = plan_project_configuration(model)
    assert configuration.blockers == ()
    linker_bytes = next(
        entry
        for entry in configuration.files
        if entry.path == "linker/stm32tk.ld"
    ).after_bytes
    # validate_elf requires the artifact to be inside the canonical project
    # root; the disposable build directory therefore lives in this synthetic
    # repository, not beside it.
    build = model.project_root / ".er24-test-build"
    build.mkdir()
    linker = build / "stm32tk.ld"
    linker.write_bytes(linker_bytes)
    return repo, model, build, linker, linker_bytes


def _compile_objects(repo, build):
    return compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )


def _with_regions(model, regions, extra_names=()):
    """A test-only model view used to prove product guards, not a new loader."""
    return replace(
        model,
        memory=MemorySpec(
            source=model.memory.source,
            regions=tuple(regions),
            stack_size=model.memory.stack_size,
            heap_size=model.memory.heap_size,
            layout=model.memory.layout,
            extra_region_names=tuple(extra_names),
        ),
    )


def test_external_ram_fixed_noload_buffer_links_and_accounts_in_the_same_map(
    tmp_path,
):
    repo, model, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "split", "ext"
    )
    text = linker_bytes.decode("utf-8")
    assert "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00010000" in text
    assert f"  .stm32tk.abs.{FIXED_ADDRESS:08x} 0x{FIXED_ADDRESS:08x} (NOLOAD)" in text
    assert "} > EXT_SRAM" in text
    assert "} > IRAM1 AT> IROM1" in text

    objects = _compile_objects(repo, build)
    result = compiler._link(build, linker, objects, cpu_flag=CPU_FLAG)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    elf = build / "firmware.elf"
    map_file = build / "firmware.map"
    assert elf.is_file() and map_file.is_file()

    sections = compiler._elf_sections(elf)
    fixed = sections[f".stm32tk.abs.{FIXED_ADDRESS:08x}"]
    assert fixed["address"] == FIXED_ADDRESS
    assert fixed["size"] == 4
    assert _within(fixed["address"], fixed["size"], EXT_RAM_RANGE)
    assert _within(
        sections[".isr_vector"]["address"], sections[".isr_vector"]["size"], FLASH_RANGE
    )
    assert sections[".data"]["size"] > 0
    assert sections[".bss"]["size"] > 0
    assert _within(sections[".data"]["address"], sections[".data"]["size"], MAIN_RAM_RANGE)
    for name in (".bss", ".heap", ".stack"):
        assert _within(sections[name]["address"], sections[name]["size"], EXT_RAM_RANGE)

    # The real product ELF guard accepts the combined map, and the real MAP
    # validator accounts the same ELF section evidence in that same map.
    evidence = validate_elf(elf, model)
    assert evidence.sections
    assert evidence.vector_address == sections[".isr_vector"]["address"]
    usage = {
        entry.name: entry
        for entry in parse_map(
            map_file.read_text("utf-8"),
            model.memory.regions,
            "firmware.map",
            elf_sections=evidence.sections,
        )
    }
    assert set(usage) == {"IROM1", "IRAM1", "EXT_SRAM"}
    assert usage["EXT_SRAM"].used >= 4
    assert usage["EXT_SRAM"].used == (
        usage["EXT_SRAM"].length - usage["EXT_SRAM"].free
    )
    assert usage["EXT_SRAM"].origin == EXT_RAM_RANGE[0]
    assert usage["EXT_SRAM"].length == EXT_RAM_RANGE[1]


def test_removed_or_shortened_region_is_rejected_by_model_elf_and_map_guards(
    tmp_path,
):
    repo, model, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "bounds", "bounds"
    )
    text = linker_bytes.decode("utf-8")
    objects = _compile_objects(repo, build)
    result = compiler._link(build, linker, objects, cpu_flag=CPU_FLAG)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    elf = build / "firmware.elf"
    map_text = (build / "firmware.map").read_text("utf-8")
    validate_elf(elf, model)  # the complete map accepts the same real ELF

    base_regions = [region for region in model.memory.regions if region.name != "EXT_SRAM"]
    removed_model = _with_regions(model, base_regions)
    shortened_ext = MemoryRegion("EXT_SRAM", EXT_RAM_RANGE[0], 0x12, "rw-")
    shortened_model = _with_regions(
        model,
        base_regions + [shortened_ext],
        ("EXT_SRAM",),
    )
    cross_end_ext = MemoryRegion("EXT_SRAM", EXT_RAM_RANGE[0], 0x14, "rw-")
    cross_end_model = _with_regions(
        model,
        base_regions + [cross_end_ext],
        ("EXT_SRAM",),
    )

    for narrowed in (removed_model, shortened_model, cross_end_model):
        with pytest.raises(BuildError) as caught:
            validate_elf(elf, narrowed)
        assert caught.value.code == "BUILD_ARTIFACT_INVALID"
        assert caught.value.details["rule"] == "sectionOutOfRange"

    # The same ELF/MAP evidence is invalid once the declared map no longer
    # equals the linker-declared regions; a removed or shortened region is
    # never silently re-interpreted.
    for narrowed in (removed_model, shortened_model, cross_end_model):
        with pytest.raises(MapError) as caught:
            parse_map(
                map_text,
                narrowed.memory.regions,
                "firmware.map",
                elf_sections=validate_elf(elf, model).sections,
            )
        assert caught.value.details["rule"] == "regions"

    # Genuine linker evidence: the fixed 4-byte buffer starts inside the
    # shortened region but crosses its end, so the real link overflows instead
    # of clipping the section.
    shortened_text = text.replace(
        "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00010000",
        "  EXT_SRAM (rw) : ORIGIN = 0x68000000, LENGTH = 0x00000012",
        1,
    )
    assert shortened_text != text
    shortened_linker = build / "shortened.ld"
    shortened_linker.write_text(shortened_text, encoding="utf-8")
    elf.unlink()
    failed_short = compiler._link(build, shortened_linker, objects, cpu_flag=CPU_FLAG)
    assert failed_short.returncode != 0
    output = failed_short.stdout + failed_short.stderr
    assert "EXT_SRAM" in output and "overflow" in output.lower()
    assert not elf.exists()


def test_flash_segment_parser_refuses_writable_executable_external_ram(tmp_path):
    repo, model, build, linker, _linker_bytes = _migrate_and_render(
        tmp_path / "flash-guard", "flashguard"
    )
    objects = _compile_objects(repo, build)
    result = compiler._link(build, linker, objects, cpu_flag=CPU_FLAG)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    elf = build / "firmware.elf"
    data = elf.read_bytes()
    accepted = flash_mod._flash_segments(data, model, "build/arm-debug/firmware.elf")
    assert accepted and all(
        segment.address < FLASH_RANGE[0] + FLASH_RANGE[1] for segment in accepted
    )

    # Keep the real base Flash and declare the synthetic external range as
    # writable executable RAM.  The unmodified image (still in base Flash) is
    # accepted; then one file-backed PT_LOAD destination is retargeted into
    # that external range in a synthetic copy of the ELF bytes.
    base_regions = [
        region for region in model.memory.regions if region.name != "EXT_SRAM"
    ]
    external_model = _with_regions(
        model,
        base_regions
        + [MemoryRegion("EXT_RWX", EXT_RAM_RANGE[0], EXT_RAM_RANGE[1], "rwx")],
        ("EXT_RWX",),
    )
    assert flash_mod._flash_segments(
        data, external_model, "build/arm-debug/firmware.elf"
    )

    parsed = ELFFile(io.BytesIO(data))
    header = parsed.header
    phoff = int(header["e_phoff"])
    entsize = int(header["e_phentsize"])
    assert entsize >= 32
    chosen: int | None = None
    for index in range(int(header["e_phnum"])):
        offset = phoff + index * entsize
        p_type = struct.unpack_from("<I", data, offset)[0]
        p_filesz = struct.unpack_from("<I", data, offset + 16)[0]
        if p_type == 1 and p_filesz > 0:  # PT_LOAD, file-backed
            chosen = offset
            break
    assert chosen is not None, "synthetic ELF has no file-backed PT_LOAD"
    mutated = bytearray(data)
    # ELF32 little-endian Phdr.p_paddr is at offset 12 in the program header.
    struct.pack_into("<I", mutated, chosen + 12, EXT_RAM_RANGE[0])
    assert bytes(mutated) != data
    with pytest.raises(flash_mod._FlashFailure) as caught:
        flash_mod._flash_segments(
            bytes(mutated), external_model, "build/arm-debug/firmware.elf"
        )
    assert caught.value.code == "FLASH_IMAGE_INVALID"
    assert caught.value.details["rule"] == "region"
