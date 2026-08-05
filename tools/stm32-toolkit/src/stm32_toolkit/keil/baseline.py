"""Optional read-only AXF/MAP baseline evidence capture.

Consumes only paths already validated in ``KeilInspection`` and revalidates
containment and existing-link behavior before every read.
"""

from __future__ import annotations

import hashlib
import os
import re
from io import BytesIO
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

from stm32_toolkit.keil import uvprojx
from stm32_toolkit.keil.model import (
    KeilArtifactEvidence,
    KeilBaseline,
    KeilInspection,
    KeilInspectionError,
    KeilProgramSize,
    KeilSectionEvidence,
    KeilSymbolEvidence,
    KeilWarning,
)

AXF_SIZE_LIMIT = 256 * 1024 * 1024
MAP_SIZE_LIMIT = 32 * 1024 * 1024
SHF_ALLOC = 0x2
SHN_UNDEF = 0
SHN_ABS = 0xFFF1
SHN_COMMON = 0xFFF2
_NON_SECTION_SHNDX = {SHN_UNDEF, SHN_ABS, SHN_COMMON}

_SELECTED_SYMBOLS = ("__Vectors", "Reset_Handler", "SystemInit", "main", "HardFault_Handler")
_PROGRAM_SIZE_RE = re.compile(
    r"Program Size:[ \t]*Code=(\d+)[ \t]+RO-data=(\d+)[ \t]+RW-data=(\d+)[ \t]+ZI-data=(\d+)"
)
_MAX_UINT64 = 0xFFFFFFFFFFFFFFFF


def _raise(code: str, message: str, details: dict[str, object]) -> KeilInspectionError:
    return KeilInspectionError(code, message, details)


def _validate_root(root: object, inspection: KeilInspection) -> Path:
    if not isinstance(root, Path):
        raise _raise(
            "KEIL_INSPECTION_ROOT_MISMATCH",
            "root must be a Path matching the inspection project root",
            {"field": "projectRoot"},
        )
    try:
        canonical = root.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "KEIL_INSPECTION_ROOT_MISMATCH",
            "root does not match the inspection project root",
            {"field": "projectRoot"},
        )
    if canonical != inspection.project_root:
        raise _raise(
            "KEIL_INSPECTION_ROOT_MISMATCH",
            "root does not match the inspection project root",
            {"field": "projectRoot"},
        )
    return canonical


def _read_artifact(
    root: Path,
    relative: str,
    artifact: str,
    size_limit: int,
    invalid_code: str,
    warnings: list[KeilWarning],
) -> bytes | None:
    absolute = uvprojx.resolve_project_path(root, relative)
    try:
        metadata = os.stat(absolute)
    except FileNotFoundError:
        warnings.append(
            KeilWarning(
                "KEIL_BASELINE_ARTIFACT_MISSING",
                "baseline artifact is missing",
                (("artifact", artifact), ("path", relative)),
            )
        )
        return None
    except NotADirectoryError:
        warnings.append(
            KeilWarning(
                "KEIL_BASELINE_ARTIFACT_MISSING",
                "baseline artifact is missing",
                (("artifact", artifact), ("path", relative)),
            )
        )
        return None
    except OSError:
        raise _raise(
            "KEIL_BASELINE_ARTIFACT_UNAVAILABLE",
            "baseline artifact is unreadable",
            {"artifact": artifact, "path": relative},
        )
    if metadata.st_size > size_limit:
        raise _raise(
            invalid_code,
            "baseline artifact exceeds the size limit",
            {"path": relative, "rule": "size"},
        )
    try:
        return absolute.read_bytes()
    except FileNotFoundError:
        warnings.append(
            KeilWarning(
                "KEIL_BASELINE_ARTIFACT_MISSING",
                "baseline artifact is missing",
                (("artifact", artifact), ("path", relative)),
            )
        )
        return None
    except OSError:
        raise _raise(
            "KEIL_BASELINE_ARTIFACT_UNAVAILABLE",
            "baseline artifact is unreadable",
            {"artifact": artifact, "path": relative},
        )


def _parse_axf(
    data: bytes, relative: str
) -> tuple[int, tuple[KeilSectionEvidence, ...], tuple[KeilSymbolEvidence, ...]]:
    try:
        elf = ELFFile(BytesIO(data))
        entry = int(elf.header["e_entry"])
        sections: list[KeilSectionEvidence] = []
        for section in elf.iter_sections():
            if section["sh_size"] and section["sh_flags"] & SHF_ALLOC:
                sections.append(
                    KeilSectionEvidence(
                        section.name,
                        int(section["sh_addr"]),
                        int(section["sh_size"]),
                        int(section["sh_flags"]),
                    )
                )
        sections.sort(key=lambda item: (item.address, item.name))
        found: dict[str, tuple[int, int | None, str | None]] = {}
        symtab = elf.get_section_by_name(".symtab")
        if symtab is not None:
            for symbol in symtab.iter_symbols():
                if not symbol.name:
                    continue
                shndx = symbol["st_shndx"]
                section_name: str | None = None
                if not isinstance(shndx, str) and shndx not in _NON_SECTION_SHNDX:
                    if 0 <= shndx < elf.num_sections():
                        section_name = elf.get_section(shndx).name
                found[symbol.name] = (
                    int(symbol["st_value"]),
                    int(symbol["st_size"]),
                    section_name,
                )
        symbols = tuple(
            KeilSymbolEvidence(name, found[name][0], found[name][1], found[name][2])
            for name in _SELECTED_SYMBOLS
            if name in found
        )
        return entry, tuple(sections), symbols
    except ELFError:
        raise _raise(
            "KEIL_AXF_INVALID",
            "artifact is not a valid ELF file",
            {"path": relative, "rule": "elf"},
        )
    except (ValueError, IndexError, KeyError) as error:
        raise _raise(
            "KEIL_AXF_INVALID",
            "artifact is not a valid ELF file",
            {"path": relative, "rule": "elf"},
        ) from error


def _parse_map(data: bytes, relative: str) -> KeilProgramSize:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map file is not valid UTF-8",
            {"path": relative, "rule": "encoding"},
        )
    summaries: list[tuple[int, int, int, int]] = []
    for match in _PROGRAM_SIZE_RE.finditer(text):
        values = tuple(int(group) for group in match.groups())
        if any(value > _MAX_UINT64 for value in values):
            raise _raise(
                "KEIL_MAP_INVALID",
                "map program size overflows unsigned 64-bit",
                {"path": relative, "rule": "overflow"},
            )
        if summaries and summaries[-1] != values:
            raise _raise(
                "KEIL_MAP_INVALID",
                "conflicting map program size summaries",
                {"path": relative, "rule": "conflict"},
            )
        summaries.append(values)
    if not summaries:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map file has no program size summary",
            {"path": relative, "rule": "programSize"},
        )
    code, ro_data, rw_data, zi_data = summaries[-1]
    return KeilProgramSize(code, ro_data, rw_data, zi_data, code + ro_data + rw_data, rw_data + zi_data)


def capture_keil_baseline(root: Path, inspection: KeilInspection) -> KeilBaseline:
    canonical = _validate_root(root, inspection)
    warnings: list[KeilWarning] = []
    axf_evidence = KeilArtifactEvidence(None, False, None, None)
    map_evidence = KeilArtifactEvidence(None, False, None, None)
    entry_point: int | None = None
    sections: tuple[KeilSectionEvidence, ...] = ()
    symbols: tuple[KeilSymbolEvidence, ...] = ()
    program_size: KeilProgramSize | None = None
    available = False

    if inspection.output.axf is not None:
        axf_evidence = KeilArtifactEvidence(inspection.output.axf, False, None, None)
        data = _read_artifact(
            canonical,
            inspection.output.axf,
            "axf",
            AXF_SIZE_LIMIT,
            "KEIL_AXF_INVALID",
            warnings,
        )
        if data is not None:
            entry_point, sections, symbols = _parse_axf(data, inspection.output.axf)
            axf_evidence = KeilArtifactEvidence(
                inspection.output.axf,
                True,
                hashlib.sha256(data).hexdigest(),
                len(data),
            )
            available = True
    else:
        warnings.append(
            KeilWarning(
                "KEIL_BASELINE_ARTIFACT_MISSING",
                "baseline artifact is missing",
                (("artifact", "axf"), ("path", None)),
            )
        )

    if inspection.output.map_file is not None:
        map_evidence = KeilArtifactEvidence(inspection.output.map_file, False, None, None)
        data = _read_artifact(
            canonical,
            inspection.output.map_file,
            "map",
            MAP_SIZE_LIMIT,
            "KEIL_MAP_INVALID",
            warnings,
        )
        if data is not None:
            program_size = _parse_map(data, inspection.output.map_file)
            map_evidence = KeilArtifactEvidence(
                inspection.output.map_file,
                True,
                hashlib.sha256(data).hexdigest(),
                len(data),
            )
            available = True
    else:
        warnings.append(
            KeilWarning(
                "KEIL_BASELINE_ARTIFACT_MISSING",
                "baseline artifact is missing",
                (("artifact", "map"), ("path", None)),
            )
        )

    return KeilBaseline(
        available=available,
        axf=axf_evidence,
        map_file=map_evidence,
        entry_point=entry_point,
        sections=sections,
        symbols=symbols,
        program_size=program_size,
        warnings=tuple(warnings),
    )
