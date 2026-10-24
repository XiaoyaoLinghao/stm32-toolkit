"""Real ARM GNU link evidence for the explicit external-RAM map.

The synthetic 0x20040000/0x10000 region is a test capacity, not a board fact.
This is offline linked-image evidence only: the owner still has to initialize
external memory before any access.
"""

from __future__ import annotations

from elftools.elf.elffile import ELFFile

from stm32_toolkit.build.map_file import ElfSectionEvidence, parse_map
from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.migration import apply_keil_conversion
from stm32_toolkit.project_model import load_project_model

import test_startup_gcc_compiler as compiler
from test_extra_memory_regions_migration import EXT, _plan, extra_repo

CPU_FLAG = "-mcpu=cortex-m4"
FLASH_RANGE = (0x08000000, 0x100000)
MAIN_RAM_RANGE = (0x20000000, 0x30000)
EXT_RAM_RANGE = (0x20040000, 0x10000)
FIXED_ADDRESS = 0x20040010


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
    build = tmp_path / f"build-{name}"
    build.mkdir()
    linker = build / "stm32tk.ld"
    linker.write_bytes(linker_bytes)
    return repo, model, build, linker, linker_bytes


def _compile_objects(repo, build):
    return compiler._compile_objects(
        repo, build, cpu_flag=CPU_FLAG, defines=("-DSTM32TK_STRONG_IRQ",)
    )


def _elf_evidence(elf) -> tuple[ElfSectionEvidence, ...]:
    evidence = []
    with elf.open("rb") as handle:
        parsed = ELFFile(handle)
        for section in parsed.iter_sections():
            size = int(section["sh_size"])
            if size == 0:
                continue
            evidence.append(
                ElfSectionEvidence(
                    name=section.name,
                    address=int(section["sh_addr"]),
                    size=size,
                    alloc=bool(int(section["sh_flags"]) & 0x2),
                    nobits=section["sh_type"] == "SHT_NOBITS",
                )
            )
    return tuple(evidence)


def test_external_ram_fixed_noload_buffer_links_and_accounts_in_the_same_map(
    tmp_path,
):
    repo, model, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "split", "ext"
    )
    text = linker_bytes.decode("utf-8")
    assert "  EXT_SRAM (rw) : ORIGIN = 0x20040000, LENGTH = 0x00010000" in text
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
    assert _within(sections[".data"]["address"], sections[".data"]["size"], MAIN_RAM_RANGE)
    for name in (".bss", ".heap", ".stack"):
        assert _within(sections[name]["address"], sections[name]["size"], EXT_RAM_RANGE)

    usage = {
        entry.name: entry
        for entry in parse_map(
            map_file.read_text("utf-8"),
            model.memory.regions,
            "firmware.map",
            elf_sections=_elf_evidence(elf),
        )
    }
    assert set(usage) == {"IROM1", "IRAM1", "EXT_SRAM"}
    assert usage["EXT_SRAM"].used >= 4
    assert usage["EXT_SRAM"].used == (
        usage["EXT_SRAM"].length - usage["EXT_SRAM"].free
    )
    assert usage["EXT_SRAM"].origin == EXT_RAM_RANGE[0]
    assert usage["EXT_SRAM"].length == EXT_RAM_RANGE[1]


def test_removed_or_shortened_extra_region_really_fails_the_link(tmp_path):
    repo, _model, build, linker, linker_bytes = _migrate_and_render(
        tmp_path / "bounds", "bounds"
    )
    text = linker_bytes.decode("utf-8")
    objects = _compile_objects(repo, build)
    elf = build / "firmware.elf"

    removed_text = text.replace(
        "  EXT_SRAM (rw) : ORIGIN = 0x20040000, LENGTH = 0x00010000\n", ""
    )
    assert removed_text != text
    removed = build / "removed.ld"
    removed.write_text(removed_text, encoding="utf-8")
    if elf.exists():
        elf.unlink()
    failed_removed = compiler._link(build, removed, objects, cpu_flag=CPU_FLAG)
    assert failed_removed.returncode != 0
    assert "EXT_SRAM" in failed_removed.stdout + failed_removed.stderr
    assert not elf.exists()

    # The fixed 4-byte buffer starts inside the shortened region but crosses
    # its end; the real linker must refuse instead of clipping.
    shortened_text = text.replace(
        "  EXT_SRAM (rw) : ORIGIN = 0x20040000, LENGTH = 0x00010000",
        "  EXT_SRAM (rw) : ORIGIN = 0x20040000, LENGTH = 0x00000012",
        1,
    )
    assert shortened_text != text
    shortened = build / "shortened.ld"
    shortened.write_text(shortened_text, encoding="utf-8")
    if elf.exists():
        elf.unlink()
    failed_short = compiler._link(build, shortened, objects, cpu_flag=CPU_FLAG)
    assert failed_short.returncode != 0
    output = failed_short.stdout + failed_short.stderr
    assert "EXT_SRAM" in output and "overflow" in output.lower()
    assert not elf.exists()
