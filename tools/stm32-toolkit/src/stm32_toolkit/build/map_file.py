"""Bounded GNU ld MAP parsing and memory accounting (STM32TK-0305).

Parses ``Memory Configuration`` region rows and output-section rows with
optional ``load address`` using anchored bounded regexes, requires the
declared regions to exactly equal the model memory regions in model order,
accounts non-empty section VMA intervals (and LMA intervals when an explicit
load address differs) to their containing model region as interval union,
rejects every malformed, duplicate, conflicting, ambiguous, unknown, or
out-of-region row, and maps region overflow to the stable overflow codes.

When ``parse_map`` receives the immutable ``ElfSectionEvidence`` produced by
ELF validation, every non-zero MAP output section is classified from the ELF
flags instead of its name: sections with ``SHF_ALLOC`` participate in VMA
memory accounting (and their explicit different LMA continues to participate
in the corresponding region), sections without ``SHF_ALLOC`` never
participate (GNU ld may place them at VMA 0), a non-zero MAP section absent
from the ELF evidence fails closed, MAP/ELF VMA or size disagreement for an
alloc section fails closed, and every non-zero ``SHF_ALLOC`` ELF section
must be uniquely matched in the MAP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stm32_toolkit.build.model import (
    BUILD_MAP_INVALID,
    FLASH_OVERFLOW,
    MEMORY_OVERFLOW,
    RAM_OVERFLOW,
    BuildError,
    MemoryUsage,
    build_error,
)
from stm32_toolkit.project_model import MemoryRegion

#: Anchored GNU ld memory configuration row: name, origin, length, attributes.
_REGION_ROW_RE = re.compile(
    r"^([A-Za-z_*][A-Za-z0-9_*]*)\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)(?:\s+\S+)?\s*$"
)
#: Anchored GNU ld output-section row with optional load address.
_SECTION_ROW_RE = re.compile(
    r"^([A-Za-z_.$][A-Za-z0-9_.$-]*)\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)"
    r"(?:\s+load address\s+0x([0-9A-Fa-f]+))?\s*$"
)
#: GNU ld wraps output-section names longer than its 16-column name field:
#: the first line contains only the name and the immediately following
#: indented line contains address, size, and optional load address.
_WRAPPED_SECTION_NAME_RE = re.compile(
    r"^([A-Za-z_.$][A-Za-z0-9_.$-]{16,})\s*$"
)
_WRAPPED_SECTION_VALUE_RE = re.compile(
    r"^\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)"
    r"(?:\s+load address\s+0x([0-9A-Fa-f]+))?\s*$"
)
#: Rows that look like section rows but fail the anchored patterns (including
#: rows whose second/third tokens start with ``0x`` but are not valid hex).
_AMBIGUOUS_ROW_RE = re.compile(r"^(\S+)\s+0x\S+\s+0x\S+")

_MAX_64_BIT = 0xFFFFFFFFFFFFFFFF
_DEFAULT_REGION = "*default*"

#: First characters that can start a region row (letters, underscore, star).
_REGION_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_*")
#: First characters that can start an output-section row (adds dot and dollar).
_SECTION_START = _REGION_START | frozenset(".$")


class MapError(BuildError):
    """A stable MAP failure carrying a stable code and bounded details."""


def map_error(rule: str, path: str | None = None) -> MapError:
    details: dict[str, object] = {"rule": rule}
    if path is not None:
        details["path"] = path
    return MapError(BUILD_MAP_INVALID, "linker map is invalid", details)


@dataclass(frozen=True)
class ElfSectionEvidence:
    """Immutable deterministic ELF section evidence for MAP classification.

    Produced by the ELF validation stage from the already validated ELF
    bytes and consumed by ``parse_map``: ``alloc`` is the ``SHF_ALLOC``
    flag, ``address`` is the section VMA, and ``size`` is the section size.
    Zero-size sections are excluded by the producer and never required to
    match.
    """

    name: str
    address: int
    size: int
    alloc: bool


@dataclass(frozen=True)
class _DeclaredRegion:
    name: str
    origin: int
    length: int


@dataclass(frozen=True)
class _Section:
    name: str
    address: int
    size: int
    load_address: int | None


def parse_map(
    text: str,
    regions: tuple[MemoryRegion, ...],
    path: str | None = None,
    *,
    elf_sections: tuple[ElfSectionEvidence, ...] | None = None,
) -> tuple[MemoryUsage, ...]:
    """Validate the GNU MAP against the model regions and account usage.

    ``path`` is an optional portable relative path attached to stable error
    details; when omitted the details contain only the rule.

    When ``elf_sections`` is provided every non-zero MAP output section is
    classified from the ELF evidence: ``SHF_ALLOC`` sections must agree with
    the MAP on VMA and size and participate in memory accounting; non-alloc
    sections never participate (GNU ld may place them at VMA 0); a non-zero
    MAP section absent from the evidence fails closed with ``unknown``; and
    every non-zero ``SHF_ALLOC`` ELF section must be matched in the MAP or
    the MAP fails closed with ``missing``.  When omitted, every non-zero MAP
    section participates exactly as before (no allocation classification).
    """
    declared, sections = _parse_rows(text, path)
    _reconcile_regions(declared, regions, path)
    usage = _account(sections, regions, path, elf_sections)
    return usage


def _parse_rows(
    text: str, path: str | None
) -> tuple[list[_DeclaredRegion], list[_Section]]:
    declared: list[_DeclaredRegion] = []
    sections: list[_Section] = []
    seen_regions: set[str] = set()
    seen_sections: set[str] = set()
    pending_section: str | None = None

    def append_section(
        name: str,
        address_text: str,
        size_text: str,
        load_address_text: str | None,
    ) -> None:
        if name in seen_sections:
            raise map_error("duplicateSection", path)
        seen_sections.add(name)
        sections.append(
            _Section(
                name=name,
                address=_parse_hex(address_text, path),
                size=_parse_hex(size_text, path),
                load_address=(
                    _parse_hex(load_address_text, path)
                    if load_address_text is not None
                    else None
                ),
            )
        )

    for line in text.splitlines():
        if not line:
            if pending_section is not None:
                raise map_error("ambiguous", path)
            continue
        if pending_section is not None:
            continuation = _WRAPPED_SECTION_VALUE_RE.match(line)
            if continuation is None:
                raise map_error("ambiguous", path)
            append_section(
                pending_section,
                continuation.group(1),
                continuation.group(2),
                continuation.group(3),
            )
            pending_section = None
            continue
        first = line[0]
        if first not in _SECTION_START:
            if _AMBIGUOUS_ROW_RE.match(line):
                raise map_error("ambiguous", path)
            continue
        region_match = None
        if first in _REGION_START:
            region_match = _REGION_ROW_RE.match(line)
        if region_match is not None:
            name = region_match.group(1)
            if name == _DEFAULT_REGION:
                continue
            origin = _parse_hex(region_match.group(2), path)
            length = _parse_hex(region_match.group(3), path)
            if name in seen_regions:
                raise map_error("duplicateRegion", path)
            seen_regions.add(name)
            for prior in declared:
                if origin < prior.origin + prior.length and prior.origin < origin + length:
                    raise map_error("overlap", path)
            declared.append(_DeclaredRegion(name=name, origin=origin, length=length))
            continue
        section_match = _SECTION_ROW_RE.match(line)
        if section_match is not None:
            append_section(
                section_match.group(1),
                section_match.group(2),
                section_match.group(3),
                section_match.group(4),
            )
            continue
        wrapped_name = _WRAPPED_SECTION_NAME_RE.match(line)
        if wrapped_name is not None:
            pending_section = wrapped_name.group(1)
            continue
        if _AMBIGUOUS_ROW_RE.match(line):
            raise map_error("ambiguous", path)
    if pending_section is not None:
        raise map_error("ambiguous", path)
    if not declared:
        raise map_error("regions", path)
    if not sections:
        raise map_error("sections", path)
    return declared, sections


def _parse_hex(value: str, path: str | None) -> int:
    parsed = int(value, 16)
    if parsed > _MAX_64_BIT:
        raise map_error("integer", path)
    return parsed


def _reconcile_regions(
    declared: list[_DeclaredRegion],
    regions: tuple[MemoryRegion, ...],
    path: str | None,
) -> None:
    if len(declared) != len(regions):
        raise map_error("regions", path)
    for index, model_region in enumerate(regions):
        map_region = declared[index]
        if (
            map_region.name != model_region.name
            or map_region.origin != model_region.origin
            or map_region.length != model_region.length
        ):
            raise map_error("regions", path)


def _account(
    sections: list[_Section],
    regions: tuple[MemoryRegion, ...],
    path: str | None,
    elf_sections: tuple[ElfSectionEvidence, ...] | None = None,
) -> tuple[MemoryUsage, ...]:
    intervals: dict[str, list[tuple[int, int]]] = {region.name: [] for region in regions}
    if elf_sections is None:
        for section in sections:
            if section.size == 0:
                continue
            _account_interval(section.address, section.size, intervals, regions, path)
            if section.load_address is not None and section.load_address != section.address:
                _account_interval(section.load_address, section.size, intervals, regions, path)
    else:
        evidence_by_name = _index_evidence(elf_sections, path)
        matched: set[str] = set()
        for section in sections:
            if section.size == 0:
                continue
            evidence = evidence_by_name.get(section.name)
            if evidence is None:
                raise map_error("unknown", path)
            if not evidence.alloc:
                continue
            if evidence.address != section.address:
                raise map_error("address", path)
            if evidence.size != section.size:
                raise map_error("size", path)
            matched.add(section.name)
            _account_interval(section.address, section.size, intervals, regions, path)
            if section.load_address is not None and section.load_address != section.address:
                _account_interval(section.load_address, section.size, intervals, regions, path)
        for evidence in elf_sections:
            if evidence.alloc and evidence.size > 0 and evidence.name not in matched:
                raise map_error("missing", path)
    flash = next((region.name for region in regions if "x" in region.attributes), None)
    ram = next((region.name for region in regions if "w" in region.attributes), None)
    usage: list[MemoryUsage] = []
    for region in regions:
        used = _union_length(intervals[region.name])
        if used > region.length:
            if region.name == flash:
                code = FLASH_OVERFLOW
            elif region.name == ram:
                code = RAM_OVERFLOW
            else:
                code = MEMORY_OVERFLOW
            raise MapError(
                code,
                "memory region overflow",
                {
                    "region": region.name,
                    "used": used,
                    "length": region.length,
                    "overflow": used - region.length,
                },
            )
        usage.append(
            MemoryUsage(
                name=region.name,
                origin=region.origin,
                length=region.length,
                used=used,
                free=region.length - used,
            )
        )
    return tuple(usage)


def _index_evidence(
    elf_sections: tuple[ElfSectionEvidence, ...], path: str | None
) -> dict[str, ElfSectionEvidence]:
    """Index evidence by section name; duplicate names make unique MAP
    matching impossible and fail closed."""
    indexed: dict[str, ElfSectionEvidence] = {}
    for evidence in elf_sections:
        if evidence.name in indexed:
            raise map_error("duplicate", path)
        indexed[evidence.name] = evidence
    return indexed


def _account_interval(
    start: int,
    size: int,
    intervals: dict[str, list[tuple[int, int]]],
    regions: tuple[MemoryRegion, ...],
    path: str | None,
) -> None:
    """Account the interval to the region containing its start.

    An interval that begins inside a region but extends past its end is
    accounted in full so the region overflow is detected and reported with
    the stable overflow code; it is never clipped (r001 rejected behavior).
    An interval that starts in no model region is rejected as out-of-region.
    """
    end = start + size
    for region in regions:
        if region.origin <= start < region.origin + region.length:
            intervals[region.name].append((start, end))
            return
    raise map_error("outOfRegion", path)


def _union_length(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    total = 0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    total += current_end - current_start
    return total
