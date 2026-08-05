"""Tests for read-only Keil AXF/MAP baseline capture (STM32TK-0302)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import struct
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from stm32_toolkit.keil import (
    KeilArtifactEvidence,
    KeilInspectionError,
    KeilProgramSize,
    KeilSectionEvidence,
    KeilSymbolEvidence,
    capture_keil_baseline,
    inspect_keil,
)

FIXTURES = Path(__file__).parent / "fixtures"
KEIL_FIXTURE = FIXTURES / "keil-project"

SHN_ABS = 0xFFF1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def build_minimal_elf32(
    entry: int = 0x08000000,
    alloc_sections: list[tuple[str, int, int, int]] | None = None,
    symbols: list[tuple[str, int, int, int]] | None = None,
) -> bytes:
    """Build a minimal valid ELF32 (EM_ARM) suitable for pyelftools."""
    alloc_sections = list(alloc_sections or [(".text", 0x08000000, 0x100, 0x6)])
    symbols = list(symbols or [])
    shstr = bytearray(b"\x00")
    name_offsets: dict[str, int] = {}

    def intern(name: str) -> int:
        if name not in name_offsets:
            name_offsets[name] = len(shstr)
            shstr.extend(name.encode("utf-8"))
            shstr.append(0)
        return name_offsets[name]

    body = bytearray()
    shdrs: list[tuple[int, int, int, int, int, int, int, int, int, int]] = []
    for name, addr, size, flags in alloc_sections:
        off = len(body)
        body.extend(b"\x00" * size)
        shdrs.append((intern(name), 1, flags, addr, off, size, 0, 0, 4, 0))
    num_alloc = len(alloc_sections)
    symtab_index = num_alloc + 1
    strtab_index = num_alloc + 2
    shstrtab_index = num_alloc + 3
    strtab = bytearray(b"\x00")
    sym_entries = []
    for sym_name, value, size, shndx in symbols:
        off = len(strtab)
        strtab.extend(sym_name.encode("utf-8"))
        strtab.append(0)
        sym_entries.append(struct.pack("<IIIBBH", off, value, size, 0x10, 0, shndx))
    symtab_off = len(body)
    body.extend(b"".join(sym_entries))
    shdrs.append((intern(".symtab"), 2, 0, 0, symtab_off, len(sym_entries) * 16, strtab_index, 1, 4, 16))
    strtab_off = len(body)
    body.extend(strtab)
    shdrs.append((intern(".strtab"), 3, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0))
    shstrtab_off = len(body)
    body.extend(shstr)
    shdrs.append((intern(".shstrtab"), 3, 0, 0, shstrtab_off, len(shstr), 0, 0, 1, 0))
    shoff = 52 + len(body)
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH",
        2,          # e_type ET_EXEC
        40,         # e_machine EM_ARM
        1,          # e_version
        entry,      # e_entry
        0,          # e_phoff
        shoff,      # e_shoff
        0,          # e_flags
        52,         # e_ehsize
        0,          # e_phentsize
        0,          # e_phnum
        40,         # e_shentsize
        shstrtab_index + 1,  # e_shnum
        shstrtab_index,      # e_shstrndx
    )
    table = bytearray(b"\x00" * 40)
    for name_off, typ, flags, addr, off, size, link, info, align, entsize in shdrs:
        table.extend(
            struct.pack("<IIIIIIIIII", name_off, typ, flags, addr, 52 + off, size, link, info, align, entsize)
        )
    return header + bytes(body) + bytes(table)


def snapshot_tree(root: Path) -> dict[str, tuple]:
    entries: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        lst = os.lstat(path)
        if stat.S_ISDIR(lst.st_mode):
            entries[rel] = ("dir", lst.st_mode)
        else:
            data = path.read_bytes()
            entries[rel] = (
                "file",
                hashlib.sha256(data).hexdigest(),
                len(data),
                lst.st_mode,
                lst.st_mtime_ns,
            )
    return entries


@pytest.fixture
def keil_project(tmp_path: Path) -> Path:
    destination = tmp_path / "keil-project"
    shutil.copytree(KEIL_FIXTURE, destination)
    return destination


@pytest.fixture
def baseline_map(keil_project: Path) -> Path:
    return keil_project / "Objects" / "legacy.map"


def write_axf(keil_project: Path, data: bytes) -> Path:
    objects = keil_project / "Objects"
    objects.mkdir(parents=True, exist_ok=True)
    target = objects / "legacy.axf"
    target.write_bytes(data)
    return target


# ---------------------------------------------------------------------------
# exact ELF/MAP parsing
# ---------------------------------------------------------------------------


def test_elf_exact_parse(keil_project: Path) -> None:
    elf = build_minimal_elf32(
        entry=0x08000000,
        alloc_sections=[
            (".text", 0x08000000, 0x100, 0x6),
            (".data", 0x20000000, 0x40, 0x3),
        ],
        symbols=[
            ("__Vectors", 0x08000000, 0x40, 1),
            ("Reset_Handler", 0x08000040, 0x10, 1),
            ("SystemInit", 0x08000050, 0x10, 1),
            ("main", 0x08000060, 0x8, 1),
            ("HardFault_Handler", 0x08000070, 0x8, SHN_ABS),
            ("extra_symbol", 0x08000080, 0x4, 1),
        ],
    )
    axf_path = write_axf(keil_project, elf)
    inspection = inspect_keil(keil_project)
    baseline = capture_keil_baseline(keil_project, inspection)
    assert baseline.available is True
    assert baseline.axf == KeilArtifactEvidence(
        "Objects/legacy.axf",
        True,
        hashlib.sha256(elf).hexdigest(),
        len(elf),
    )
    assert baseline.entry_point == 0x08000000
    assert baseline.sections == (
        KeilSectionEvidence(".text", 0x08000000, 0x100, 0x6),
        KeilSectionEvidence(".data", 0x20000000, 0x40, 0x3),
    )
    assert baseline.symbols == (
        KeilSymbolEvidence("__Vectors", 0x08000000, 0x40, ".text"),
        KeilSymbolEvidence("Reset_Handler", 0x08000040, 0x10, ".text"),
        KeilSymbolEvidence("SystemInit", 0x08000050, 0x10, ".text"),
        KeilSymbolEvidence("main", 0x08000060, 0x8, ".text"),
        KeilSymbolEvidence("HardFault_Handler", 0x08000070, 0x8, None),
    )
    assert baseline.program_size == KeilProgramSize(8124, 720, 92, 16988, 8936, 17080)
    assert str(axf_path) not in json.dumps(baseline.to_dict())


def test_map_program_size_parsing(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "Objects").mkdir(parents=True)
    (root / "Objects" / "firmware.map").write_text(
        "Program Size:\tCode=1000  RO-data=200  RW-data=50  ZI-data=750\n", encoding="utf-8"
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?><Project>'
        "<Targets><Target><TargetName>T</TargetName><pCCUsed>5060750::V5::ARMCC</pCCUsed>"
        "<TargetOption><TargetCommonOption><Device>D</Device>"
        '<Cpu>CPUTYPE("Cortex-M4")</Cpu></TargetCommonOption>'
        "<OutputDirectory>.\\Objects\\</OutputDirectory><OutputName>firmware</OutputName>"
        "<TargetArmAds><Cads><VariousControls/></Cads><LDads><VariousControls/></LDads></TargetArmAds>"
        "</TargetOption><Groups/></Target></Targets></Project>"
    )
    (root / "proj.uvprojx").write_text(xml, encoding="utf-8")
    inspection = inspect_keil(root)
    baseline = capture_keil_baseline(root, inspection)
    assert baseline.program_size == KeilProgramSize(1000, 200, 50, 750, 1250, 800)


def test_committed_fixture_map_only_baseline(keil_project: Path) -> None:
    inspection = inspect_keil(keil_project)
    baseline = capture_keil_baseline(keil_project, inspection)
    assert baseline.available is True
    assert baseline.map_file.path == "Objects/legacy.map"
    assert baseline.map_file.available is True
    assert baseline.map_file.sha256 == hashlib.sha256(
        (keil_project / "Objects" / "legacy.map").read_bytes()
    ).hexdigest()
    assert baseline.map_file.size == (keil_project / "Objects" / "legacy.map").stat().st_size
    assert baseline.axf == KeilArtifactEvidence("Objects/legacy.axf", False, None, None)
    assert baseline.entry_point is None
    assert baseline.sections == ()
    assert baseline.symbols == ()
    assert baseline.program_size == KeilProgramSize(8124, 720, 92, 16988, 8936, 17080)
    codes = [w.code for w in baseline.warnings]
    assert codes == ["KEIL_BASELINE_ARTIFACT_MISSING"]


def test_missing_both_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "Src").mkdir(parents=True)
    (root / "Src" / "a.c").write_text("int a;\n", encoding="utf-8")
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?><Project>'
        "<Targets><Target><TargetName>T</TargetName><pCCUsed>5060750::V5::ARMCC</pCCUsed>"
        "<TargetOption><TargetCommonOption><Device>D</Device>"
        '<Cpu>CPUTYPE("Cortex-M4")</Cpu></TargetCommonOption>'
        "<OutputDirectory>.\\Objects\\</OutputDirectory><OutputName>firmware</OutputName>"
        "<TargetArmAds><Cads><VariousControls/></Cads><LDads><VariousControls/></LDads></TargetArmAds>"
        "</TargetOption><Groups><Group><GroupName>G</GroupName><Files><File><FileName>a.c</FileName>"
        "<FileType>1</FileType><FilePath>.\\Src\\a.c</FilePath></File></Files></Group></Groups>"
        "</Target></Targets></Project>"
    )
    (root / "proj.uvprojx").write_text(xml, encoding="utf-8")
    inspection = inspect_keil(root)
    baseline = capture_keil_baseline(root, inspection)
    assert baseline.available is False
    assert baseline.axf.available is False
    assert baseline.map_file.available is False
    assert baseline.program_size is None
    codes = [w.code for w in baseline.warnings]
    assert codes == ["KEIL_BASELINE_ARTIFACT_MISSING", "KEIL_BASELINE_ARTIFACT_MISSING"]


def test_axf_only_availability(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    os.remove(keil_project / "Objects" / "legacy.map")
    inspection = inspect_keil(keil_project)
    baseline = capture_keil_baseline(keil_project, inspection)
    assert baseline.available is True
    assert baseline.axf.available is True
    assert baseline.map_file.available is False
    assert baseline.program_size is None
    assert baseline.entry_point == 0x08000000


def test_root_mismatch(keil_project: Path, tmp_path: Path) -> None:
    inspection = inspect_keil(keil_project)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(other, inspection)
    assert error.value.code == "KEIL_INSPECTION_ROOT_MISMATCH"
    assert error.value.details == {"field": "projectRoot"}
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline("not-a-path", inspection)  # type: ignore[arg-type]
    assert error.value.code == "KEIL_INSPECTION_ROOT_MISMATCH"


# ---------------------------------------------------------------------------
# corrupt / unreadable / oversized artifacts
# ---------------------------------------------------------------------------


def test_corrupt_axf_rejected(keil_project: Path) -> None:
    write_axf(keil_project, b"this is not an elf file at all")
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_AXF_INVALID"
    assert error.value.details == {"path": "Objects/legacy.axf", "rule": "elf"}


def test_truncated_axf_rejected(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf[:32])
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_AXF_INVALID"
    assert error.value.details == {"path": "Objects/legacy.axf", "rule": "elf"}


def test_axf_size_cap(keil_project: Path) -> None:
    target = keil_project / "Objects" / "legacy.axf"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.truncate(256 * 1024 * 1024 + 1)
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_AXF_INVALID"
    assert error.value.details == {"path": "Objects/legacy.axf", "rule": "size"}


def test_map_size_cap(keil_project: Path) -> None:
    target = keil_project / "Objects" / "legacy.map"
    with target.open("wb") as handle:
        handle.truncate(32 * 1024 * 1024 + 1)
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_MAP_INVALID"
    assert error.value.details == {"path": "Objects/legacy.map", "rule": "size"}


def test_map_missing_program_size(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.map").write_text(
        "Execution Region ER_IROM1 (Base: 0x08000000, Size: 0x100)\n", encoding="utf-8"
    )
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_MAP_INVALID"
    assert error.value.details == {"path": "Objects/legacy.map", "rule": "programSize"}


def test_map_conflicting_summaries(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.map").write_text(
        "Program Size: Code=1 RO-data=2 RW-data=3 ZI-data=4\n"
        "Program Size: Code=1 RO-data=2 RW-data=3 ZI-data=5\n",
        encoding="utf-8",
    )
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_MAP_INVALID"
    assert error.value.details == {"path": "Objects/legacy.map", "rule": "conflict"}


def test_map_duplicate_identical_summaries_accepted(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.map").write_text(
        "Program Size: Code=1 RO-data=2 RW-data=3 ZI-data=4\n"
        "Program Size: Code=1 RO-data=2 RW-data=3 ZI-data=4\n",
        encoding="utf-8",
    )
    inspection = inspect_keil(keil_project)
    baseline = capture_keil_baseline(keil_project, inspection)
    assert baseline.program_size == KeilProgramSize(1, 2, 3, 4, 6, 7)


def test_map_overflow(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.map").write_text(
        "Program Size: Code=18446744073709551616 RO-data=0 RW-data=0 ZI-data=0\n",
        encoding="utf-8",
    )
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_MAP_INVALID"
    assert error.value.details == {"path": "Objects/legacy.map", "rule": "overflow"}


def test_map_invalid_encoding(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.map").write_bytes(b"Program Size:\xff\xfe Code=1\n")
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_MAP_INVALID"
    assert error.value.details == {"path": "Objects/legacy.map", "rule": "encoding"}


def test_unreadable_artifact(keil_project: Path) -> None:
    (keil_project / "Objects" / "legacy.axf").mkdir()
    inspection = inspect_keil(keil_project)
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_BASELINE_ARTIFACT_UNAVAILABLE"
    assert error.value.details == {"artifact": "axf", "path": "Objects/legacy.axf"}


# ---------------------------------------------------------------------------
# path revalidation and read-only guarantees
# ---------------------------------------------------------------------------


def test_artifact_symlink_escape_rejected(keil_project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.elf").write_bytes(build_minimal_elf32())
    inspection = inspect_keil(keil_project)
    os.symlink(outside / "payload.elf", keil_project / "Objects" / "legacy.axf")
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, inspection)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert "outside" not in str(error.value.details)


def test_artifact_escape_via_relative_path_rejected(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    inspection = inspect_keil(keil_project)
    tampered = inspect_keil(keil_project)
    object.__setattr__(tampered.output, "axf", "../escape.axf")
    with pytest.raises(KeilInspectionError) as error:
        capture_keil_baseline(keil_project, tampered)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"


def test_baseline_immutable(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    inspection = inspect_keil(keil_project)
    baseline = capture_keil_baseline(keil_project, inspection)
    with pytest.raises(FrozenInstanceError):
        baseline.entry_point = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        baseline.sections[0].name = "x"  # type: ignore[misc]
    assert isinstance(baseline.sections, tuple)
    assert isinstance(baseline.symbols, tuple)


def test_baseline_to_dict_portable(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    inspection = inspect_keil(keil_project)
    data = capture_keil_baseline(keil_project, inspection).to_dict()
    json.dumps(data)
    assert data["axf"]["path"] == "Objects/legacy.axf"
    assert data["program_size"]["flash"] == 8936

    def assert_no_absolute(value: object) -> None:
        if isinstance(value, str):
            assert not value.startswith("/")
            assert "\\" not in value
        elif isinstance(value, dict):
            for item in value.values():
                assert_no_absolute(item)
        elif isinstance(value, list):
            for item in value:
                assert_no_absolute(item)

    assert_no_absolute(data)


def test_baseline_read_only_snapshot(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    before = snapshot_tree(keil_project)
    inspection = inspect_keil(keil_project)
    capture_keil_baseline(keil_project, inspection)
    capture_keil_baseline(keil_project, inspection)
    assert snapshot_tree(keil_project) == before


def test_repeated_capture_equal_serialization(keil_project: Path) -> None:
    elf = build_minimal_elf32()
    write_axf(keil_project, elf)
    inspection = inspect_keil(keil_project)
    first = capture_keil_baseline(keil_project, inspection).to_dict()
    second = capture_keil_baseline(keil_project, inspection).to_dict()
    assert first == second


def test_artifact_unreadable_permission(keil_project: Path) -> None:
    target = write_axf(keil_project, build_minimal_elf32())
    target.chmod(0)
    try:
        inspection = inspect_keil(keil_project)
        with pytest.raises(KeilInspectionError) as error:
            capture_keil_baseline(keil_project, inspection)
        assert error.value.code == "KEIL_BASELINE_ARTIFACT_UNAVAILABLE"
        assert error.value.details == {"artifact": "axf", "path": "Objects/legacy.axf"}
    finally:
        target.chmod(0o644)


def test_no_output_name_no_artifact_candidates(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "Src").mkdir(parents=True)
    (root / "Src" / "a.c").write_text("int a;\n", encoding="utf-8")
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?><Project>'
        "<Targets><Target><TargetName>T</TargetName><pCCUsed>5060750::V5::ARMCC</pCCUsed>"
        "<TargetOption><TargetCommonOption><Device>D</Device>"
        '<Cpu>CPUTYPE("Cortex-M4")</Cpu></TargetCommonOption>'
        "<TargetArmAds><Cads><VariousControls/></Cads><LDads><VariousControls/></LDads></TargetArmAds>"
        "</TargetOption><Groups/></Target></Targets></Project>"
    )
    (root / "proj.uvprojx").write_text(xml, encoding="utf-8")
    inspection = inspect_keil(root)
    assert inspection.output.axf is None
    assert inspection.output.map_file is None
    baseline = capture_keil_baseline(root, inspection)
    assert baseline.available is False
    assert baseline.axf.path is None
    assert baseline.map_file.path is None
    assert [w.code for w in baseline.warnings] == [
        "KEIL_BASELINE_ARTIFACT_MISSING",
        "KEIL_BASELINE_ARTIFACT_MISSING",
    ]
