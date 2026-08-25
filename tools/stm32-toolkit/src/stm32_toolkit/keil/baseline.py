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
_COMPONENT_SECTION_RE = re.compile(r"^[ \t]*Image component sizes[ \t]*$")
_COMPONENT_HEADER_RE = re.compile(
    r"^[ \t]*Code[ \t]+\(inc\. data\)[ \t]+RO[ \t]+Data[ \t]+RW[ \t]+Data"
    r"[ \t]+ZI[ \t]+Data[ \t]+Debug(?:[ \t]+Object[ \t]+Name)?[ \t]*$"
)
_COMPONENT_RO_SIZE_RE = re.compile(
    r"^[ \t]*Total[ \t]+RO[ \t]+Size(?:[ \t]+\([^\r\n]*\))?[ \t]+([0-9]+)"
    r"(?:[ \t]+\([^\r\n]*\))?[ \t]*$",
    re.MULTILINE,
)
_COMPONENT_RW_SIZE_RE = re.compile(
    r"^[ \t]*Total[ \t]+RW[ \t]+Size(?:[ \t]+\([^\r\n]*\))?[ \t]+([0-9]+)"
    r"(?:[ \t]+\([^\r\n]*\))?[ \t]*$",
    re.MULTILINE,
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
        data = uvprojx._read_limited(absolute, size_limit)
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
    if len(data) > size_limit:
        raise _raise(
            invalid_code,
            "baseline artifact exceeds the size limit",
            {"path": relative, "rule": "size"},
        )
    return data


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


def _parse_component_summary(text: str, relative: str) -> tuple[int, int, int, int] | None:
    lines = text.splitlines()
    section_indices = [
        index for index, line in enumerate(lines) if _COMPONENT_SECTION_RE.fullmatch(line)
    ]
    header_indices = [
        index
        for index, line in enumerate(lines)
        if _COMPONENT_HEADER_RE.fullmatch(line)
    ]
    has_component_signal = bool(section_indices) or any(
        len(line.strip().split()) > 2 and line.strip().endswith("Grand Totals") for line in lines
    )
    if not has_component_signal:
        return None
    if len(section_indices) != 1:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals require one exact section",
            {"path": relative, "rule": "componentSection"},
        )
    section_index = section_indices[0]
    header_indices = [index for index in header_indices if index > section_index]
    if not header_indices:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals require an exact header",
            {"path": relative, "rule": "componentHeader"},
        )
    total_rows = [
        line.strip()
        for line in lines[header_indices[0] + 1 :]
        if line.strip().endswith("Grand Totals")
    ]
    if not total_rows or len(total_rows) != 1:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals require exactly one Grand Totals row",
            {"path": relative, "rule": "componentTotals"},
        )
    fields = total_rows[0].split()
    if len(fields) < 2 or fields[-2:] != ["Grand", "Totals"]:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals row is malformed",
            {"path": relative, "rule": "componentColumns"},
        )
    values = fields[:-2]
    if len(values) != 6 or any(not value or not all("0" <= char <= "9" for char in value) for value in values):
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals require six ASCII decimal columns",
            {"path": relative, "rule": "componentColumns"},
        )
    parsed = tuple(int(value) for value in values)
    if any(value > _MAX_UINT64 for value in parsed):
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals overflow unsigned 64-bit",
            {"path": relative, "rule": "overflow"},
        )
    code, _inc_data, ro_data, rw_data, zi_data, _debug = parsed
    section_text = "\n".join(lines[section_index + 1 :])
    ro_matches = [match for match in _COMPONENT_RO_SIZE_RE.finditer(section_text)]
    rw_matches = [match for match in _COMPONENT_RW_SIZE_RE.finditer(section_text)]
    if len(ro_matches) != 1 or len(rw_matches) != 1:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals require RO and RW cross-checks",
            {"path": relative, "rule": "componentCrossCheck"},
        )
    ro_total = int(ro_matches[0].group(1))
    rw_total = int(rw_matches[0].group(1))
    if ro_total > _MAX_UINT64 or rw_total > _MAX_UINT64:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component cross-check overflows unsigned 64-bit",
            {"path": relative, "rule": "overflow"},
        )
    if code > _MAX_UINT64 - ro_data or rw_data > _MAX_UINT64 - zi_data:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component totals overflow unsigned 64-bit",
            {"path": relative, "rule": "overflow"},
        )
    if ro_total != code + ro_data or rw_total != rw_data + zi_data:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component RO/RW cross-check mismatch",
            {"path": relative, "rule": "componentCrossCheck"},
        )
    if code > _MAX_UINT64 - ro_data - rw_data:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map component flash size overflows unsigned 64-bit",
            {"path": relative, "rule": "overflow"},
        )
    return code, ro_data, rw_data, zi_data


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
    component = _parse_component_summary(text, relative)
    if not summaries and component is None:
        raise _raise(
            "KEIL_MAP_INVALID",
            "map file has no program size summary",
            {"path": relative, "rule": "programSize"},
        )
    if summaries:
        if component is not None and component != summaries[-1]:
            raise _raise(
                "KEIL_MAP_INVALID",
                "conflicting classic and component program size summaries",
                {"path": relative, "rule": "componentConflict"},
            )
        code, ro_data, rw_data, zi_data = summaries[-1]
    else:
        code, ro_data, rw_data, zi_data = component
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
