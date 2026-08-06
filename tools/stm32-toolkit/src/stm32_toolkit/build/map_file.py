"""Bounded GNU ld MAP evidence parsing (STM32TK-0305).

Parses the ``Memory Configuration`` region table and the anchored
output-section header rows of the ``Linker script and memory map`` section,
then computes per-region usage with interval-union accounting.  Malformed,
incomplete, or inconsistent evidence fails closed with
:class:`MapParseError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stm32_toolkit.build.model import BUILD_EVIDENCE_INVALID, BuildError, MemoryUsage

#: Anchored row of the GNU ld ``Memory Configuration`` region table.
_MEMORY_REGION_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<origin>0x[0-9a-fA-F]+)\s+"
    r"(?P<length>0x[0-9a-fA-F]+)"
    r"(?:\s+(?P<attributes>[A-Za-z]+))?\s*$"
)

#: Anchored output-section header row.  GNU ld prints the VMA first and an
#: optional ``load address`` tail when the LMA differs (for example ``.data``).
_OUTPUT_SECTION_RE = re.compile(
    r"^\s*(?P<name>\.[A-Za-z0-9_.]+|COMMON|\*fill\*)\s+"
    r"(?P<address>0x[0-9a-fA-F]+)\s+"
    r"(?P<size>0x[0-9a-fA-F]+)"
    r"(?:\s+load address\s+0x[0-9a-fA-F]+)?\s*$"
)

_MEMORY_CONFIGURATION_HEADER = "Memory Configuration"
_MEMORY_MAP_HEADER = "Linker script and memory map"


class MapParseError(BuildError):
    """Malformed or inconsistent MAP evidence with a stable rule."""

    def __init__(self, rule: str) -> None:
        super().__init__(
            BUILD_EVIDENCE_INVALID,
            "MAP evidence is malformed",
            {"rule": rule},
        )


@dataclass(frozen=True)
class MapMemoryRegion:
    """One GNU ld ``Memory Configuration`` row."""

    name: str
    origin: int
    length: int
    attributes: str | None


@dataclass(frozen=True)
class MapSection:
    """One output-section header row (VMA and size)."""

    name: str
    address: int
    size: int


@dataclass(frozen=True)
class MapFile:
    """Validated MAP evidence: regions plus output sections."""

    memory_regions: tuple[MapMemoryRegion, ...]
    sections: tuple[MapSection, ...]

    def region_usage(self) -> tuple[MemoryUsage, ...]:
        """Compute per-region usage by intersecting and unioning intervals."""
        usages: list[MemoryUsage] = []
        for region in self.memory_regions:
            region_start = region.origin
            region_end = region.origin + region.length
            intervals: list[tuple[int, int]] = []
            for section in self.sections:
                if section.size <= 0:
                    continue
                low = max(section.address, region_start)
                high = min(section.address + section.size, region_end)
                if low < high:
                    intervals.append((low, high))
            used = _union_length(intervals)
            percent = round(used * 100.0 / region.length, 2) if region.length else 0.0
            usages.append(
                MemoryUsage(
                    region=region.name,
                    origin=region.origin,
                    length=region.length,
                    used=used,
                    percent=percent,
                )
            )
        return tuple(usages)


def parse_map(text: str) -> MapFile:
    """Parse bounded GNU ld MAP text into validated regions and sections."""
    regions = _parse_regions(text)
    sections = _parse_sections(text)
    if not regions:
        raise MapParseError("memoryConfiguration")
    if not sections:
        raise MapParseError("outputSections")
    _reject_overlapping_regions(regions)
    return MapFile(memory_regions=regions, sections=sections)


def _parse_regions(text: str) -> tuple[MapMemoryRegion, ...]:
    regions: list[MapMemoryRegion] = []
    in_memory_configuration = False
    for line in text.splitlines():
        if line.strip() == _MEMORY_CONFIGURATION_HEADER:
            in_memory_configuration = True
            continue
        if not in_memory_configuration:
            continue
        if line.strip() == _MEMORY_MAP_HEADER:
            break
        match = _MEMORY_REGION_RE.match(line)
        if match is not None:
            regions.append(
                MapMemoryRegion(
                    name=match.group("name"),
                    origin=int(match.group("origin"), 16),
                    length=int(match.group("length"), 16),
                    attributes=match.group("attributes"),
                )
            )
    return tuple(regions)


def _parse_sections(text: str) -> tuple[MapSection, ...]:
    sections: list[MapSection] = []
    for line in text.splitlines():
        match = _OUTPUT_SECTION_RE.match(line)
        if match is not None:
            sections.append(
                MapSection(
                    name=match.group("name"),
                    address=int(match.group("address"), 16),
                    size=int(match.group("size"), 16),
                )
            )
    return tuple(sections)


def _reject_overlapping_regions(regions: tuple[MapMemoryRegion, ...]) -> None:
    ordered = sorted(regions, key=lambda region: region.origin)
    for previous, current in zip(ordered, ordered[1:]):
        if current.origin < previous.origin + previous.length:
            raise MapParseError("overlappingRegions")


def _union_length(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    total = 0
    current_low, current_high = ordered[0]
    for low, high in ordered[1:]:
        if low <= current_high:
            current_high = max(current_high, high)
        else:
            total += current_high - current_low
            current_low, current_high = low, high
    total += current_high - current_low
    return total
