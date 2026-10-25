"""Frozen static memory-margin summary for validated ELF/MAP evidence.

The summary accounts exactly the interval-union ``used``/``free`` values that
``parse_map`` already produced for every normalized model region (base regions
first, then explicit ``memory.extraRegions``).  It never guesses capacity,
changes allocation, or treats static free space as a runtime guarantee.

A region warns with the nonblocking ``MEMORY_LOW_MARGIN`` code when
``free < 1024`` or ``free * 20 < length``.  Equality at either threshold does
not warn.  Warnings are emitted once per triggering region in the summary's
deterministic region order, and their boolean fields record exactly which
threshold(s) matched.

Every value is immutable; ``to_dict`` returns fresh JSON-safe containers, and
``from_document`` strictly validates shape, exact integer types, ranges,
``used + free == length``, unique non-overlapping address ranges, and warnings
that exactly correspond to the region rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

BASIS = "elf-map-static-v1"
MEMORY_LOW_MARGIN = "MEMORY_LOW_MARGIN"
LOW_MARGIN_BYTES = 1024
LOW_MARGIN_DIVISOR = 20
MAX_ADDRESS = 0xFFFFFFFF
MAX_LENGTH = 0x1_0000_0000

_SUMMARY_FIELDS = frozenset({"basis", "regions", "warnings"})
_REGION_FIELDS = frozenset({"name", "origin", "length", "used", "free"})
_WARNING_FIELDS = frozenset(
    {
        "code",
        "region",
        "freeBytes",
        "lengthBytes",
        "belowBytes",
        "belowPercent",
    }
)


class MemorySummaryError(ValueError):
    """A stable, bounded summary validation failure."""

    def __init__(self, message: str, field: str, rule: str) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.rule = rule


def _fail(message: str, field: str, rule: str) -> MemorySummaryError:
    return MemorySummaryError(message, field, rule)


def _is_int(value: object) -> bool:
    return type(value) is int


class _UsageLike(Protocol):
    name: str
    origin: int
    length: int
    used: int
    free: int


@dataclass(frozen=True)
class MemoryMarginRegion:
    """One region row of the static ELF/MAP summary."""

    name: str
    origin: int
    length: int
    used: int
    free: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise _fail("memory summary region name is invalid", "name", "value")
        if not _is_int(self.origin) or not 0 <= self.origin <= MAX_ADDRESS:
            raise _fail("memory summary region origin is invalid", "origin", "range")
        if not _is_int(self.length) or not 1 <= self.length <= MAX_LENGTH:
            raise _fail("memory summary region length is invalid", "length", "range")
        if self.origin + self.length > MAX_LENGTH:
            raise _fail("memory summary region end is invalid", "length", "range")
        if not _is_int(self.used) or not 0 <= self.used <= self.length:
            raise _fail("memory summary region used is invalid", "used", "range")
        if not _is_int(self.free) or not 0 <= self.free <= self.length:
            raise _fail("memory summary region free is invalid", "free", "range")
        if self.used + self.free != self.length:
            raise _fail(
                "memory summary region used and free do not sum to length",
                "used",
                "sum",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "length": self.length,
            "used": self.used,
            "free": self.free,
        }

    @classmethod
    def from_document(cls, document: object) -> "MemoryMarginRegion":
        if not isinstance(document, dict):
            raise _fail("memory summary region must be an object", "regions", "type")
        if set(document) != _REGION_FIELDS:
            raise _fail(
                "memory summary region fields are invalid", "regions", "fields"
            )
        return cls(
            name=document["name"],  # type: ignore[arg-type]
            origin=document["origin"],  # type: ignore[arg-type]
            length=document["length"],  # type: ignore[arg-type]
            used=document["used"],  # type: ignore[arg-type]
            free=document["free"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class MemoryMarginWarning:
    """One deterministic nonblocking low-margin warning."""

    code: str
    region: str
    free_bytes: int
    length_bytes: int
    below_bytes: bool
    below_percent: bool

    def __post_init__(self) -> None:
        if self.code != MEMORY_LOW_MARGIN:
            raise _fail("memory summary warning code is invalid", "code", "value")
        if not isinstance(self.region, str) or not self.region:
            raise _fail("memory summary warning region is invalid", "region", "value")
        if not _is_int(self.free_bytes) or self.free_bytes < 0:
            raise _fail("memory summary warning freeBytes is invalid", "freeBytes", "range")
        if not _is_int(self.length_bytes) or self.length_bytes < 1:
            raise _fail(
                "memory summary warning lengthBytes is invalid", "lengthBytes", "range"
            )
        if type(self.below_bytes) is not bool:
            raise _fail(
                "memory summary warning belowBytes is invalid", "belowBytes", "type"
            )
        if type(self.below_percent) is not bool:
            raise _fail(
                "memory summary warning belowPercent is invalid",
                "belowPercent",
                "type",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "region": self.region,
            "freeBytes": self.free_bytes,
            "lengthBytes": self.length_bytes,
            "belowBytes": self.below_bytes,
            "belowPercent": self.below_percent,
        }

    def text(self) -> str:
        """Deterministic readable warning derived from this exact row."""
        return (
            f"{self.code}: region {self.region} has {self.free_bytes} free bytes "
            f"of {self.length_bytes} (belowBytes="
            f"{str(self.below_bytes).lower()}, belowPercent="
            f"{str(self.below_percent).lower()}); static interval-union free "
            "space is not the largest contiguous free block, runtime stack/heap "
            "peak, or initialization proof"
        )

    @classmethod
    def from_document(cls, document: object) -> "MemoryMarginWarning":
        if not isinstance(document, dict):
            raise _fail("memory summary warning must be an object", "warnings", "type")
        if set(document) != _WARNING_FIELDS:
            raise _fail(
                "memory summary warning fields are invalid", "warnings", "fields"
            )
        return cls(
            code=document["code"],  # type: ignore[arg-type]
            region=document["region"],  # type: ignore[arg-type]
            free_bytes=document["freeBytes"],  # type: ignore[arg-type]
            length_bytes=document["lengthBytes"],  # type: ignore[arg-type]
            below_bytes=document["belowBytes"],  # type: ignore[arg-type]
            below_percent=document["belowPercent"],  # type: ignore[arg-type]
        )


def _warning_for(region: MemoryMarginRegion) -> MemoryMarginWarning | None:
    below_bytes = region.free < LOW_MARGIN_BYTES
    below_percent = region.free * LOW_MARGIN_DIVISOR < region.length
    if not (below_bytes or below_percent):
        return None
    return MemoryMarginWarning(
        code=MEMORY_LOW_MARGIN,
        region=region.name,
        free_bytes=region.free,
        length_bytes=region.length,
        below_bytes=below_bytes,
        below_percent=below_percent,
    )


def _validate_unique_and_disjoint(regions: tuple[MemoryMarginRegion, ...]) -> None:
    names: set[str] = set()
    for region in regions:
        if region.name in names:
            raise _fail("memory summary region names are not unique", "regions", "unique")
        names.add(region.name)
    ordered = sorted(regions, key=lambda item: (item.origin, item.origin + item.length))
    previous_end: int | None = None
    for region in ordered:
        end = region.origin + region.length
        if previous_end is not None and region.origin < previous_end:
            raise _fail(
                "memory summary region ranges overlap", "regions", "overlap"
            )
        previous_end = end if previous_end is None else max(previous_end, end)


@dataclass(frozen=True)
class MemorySummary:
    """The complete frozen static memory summary."""

    basis: str
    regions: tuple[MemoryMarginRegion, ...]
    warnings: tuple[MemoryMarginWarning, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "regions", tuple(self.regions))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.basis != BASIS:
            raise _fail("memory summary basis is invalid", "basis", "value")
        if not self.regions:
            raise _fail("memory summary must contain regions", "regions", "count")
        for region in self.regions:
            if not isinstance(region, MemoryMarginRegion):
                raise _fail(
                    "memory summary region is invalid", "regions", "type"
                )
        _validate_unique_and_disjoint(self.regions)
        expected = tuple(
            warning
            for region in self.regions
            if (warning := _warning_for(region)) is not None
        )
        if len(self.warnings) != len(expected):
            raise _fail(
                "memory summary warnings do not match the region rows",
                "warnings",
                "count",
            )
        for index, (actual, required) in enumerate(zip(self.warnings, expected)):
            if not isinstance(actual, MemoryMarginWarning):
                raise _fail(
                    "memory summary warning is invalid", "warnings", "type"
                )
            if actual.to_dict() != required.to_dict():
                raise _fail(
                    "memory summary warning does not match its region",
                    f"warnings[{index}]",
                    "value",
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "basis": self.basis,
            "regions": [region.to_dict() for region in self.regions],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }

    def warning_texts(self) -> tuple[str, ...]:
        return tuple(warning.text() for warning in self.warnings)

    @classmethod
    def from_document(cls, document: object) -> "MemorySummary":
        if not isinstance(document, dict):
            raise _fail("memory summary must be an object", "memorySummary", "type")
        if set(document) != _SUMMARY_FIELDS:
            raise _fail(
                "memory summary fields are invalid", "memorySummary", "fields"
            )
        regions_value = document["regions"]
        warnings_value = document["warnings"]
        if not isinstance(regions_value, list):
            raise _fail("memory summary regions must be an array", "regions", "type")
        if not isinstance(warnings_value, list):
            raise _fail("memory summary warnings must be an array", "warnings", "type")
        return cls(
            basis=document["basis"],  # type: ignore[arg-type]
            regions=tuple(
                MemoryMarginRegion.from_document(item) for item in regions_value
            ),
            warnings=tuple(
                MemoryMarginWarning.from_document(item) for item in warnings_value
            ),
        )

    @classmethod
    def from_usages(cls, usages: Iterable[_UsageLike]) -> "MemorySummary":
        regions = tuple(
            MemoryMarginRegion(
                name=usage.name,
                origin=usage.origin,
                length=usage.length,
                used=usage.used,
                free=usage.free,
            )
            for usage in usages
        )
        return cls(
            basis=BASIS,
            regions=regions,
            warnings=tuple(
                warning
                for region in regions
                if (warning := _warning_for(region)) is not None
            ),
        )


def build_memory_summary(usages: Iterable[_UsageLike]) -> MemorySummary:
    """Build the frozen summary from validated ``parse_map`` usage rows."""
    return MemorySummary.from_usages(usages)


def memory_summary_matches(
    document: object, usages: Iterable[_UsageLike]
) -> bool:
    """True only when a stored summary equals a fresh recomputation."""
    try:
        declared = MemorySummary.from_document(document)
    except MemorySummaryError:
        return False
    return declared == build_memory_summary(usages)


__all__ = [
    "BASIS",
    "LOW_MARGIN_BYTES",
    "LOW_MARGIN_DIVISOR",
    "MEMORY_LOW_MARGIN",
    "MemoryMarginRegion",
    "MemoryMarginWarning",
    "MemorySummary",
    "MemorySummaryError",
    "build_memory_summary",
    "memory_summary_matches",
]
