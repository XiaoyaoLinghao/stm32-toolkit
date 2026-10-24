"""Strict explicit external-RAM region validation.

Extra regions are an owner-supplied input for Schema 2/3 manifests and Keil
migration.  Nothing here infers a name, origin, length or access from a
device, address expression, source symbol or board: every field is explicit.
Only writable RAM is representable (``rw-`` or ``rwx``); a new programmable
Flash region cannot be declared this way.

This module performs no I/O and is shared by the manifest/model loader and the
migration transport adapters so both accept exactly the same bounded values.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from stm32_toolkit.memory_layout import region_facts

#: One bounded reviewed request; larger lists are rejected, never sampled.
MAX_EXTRA_REGIONS = 32
MAX_EXTRA_REGIONS_JSON_BYTES = 64 * 1024
MAX_EXTRA_REGION_NAME_LENGTH = 64
EXTRA_REGION_ATTRIBUTES = frozenset({"rw-", "rwx"})
EXTRA_REGION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXTRA_REGION_FIELDS = frozenset({"name", "origin", "length", "attributes"})

_REMEDIATION = (
    "Pass extraRegions as a JSON array of at most 32 objects. Each object must "
    "have exactly name, origin, length and attributes. name is a 1-64 "
    "character ASCII linker identifier; origin is an exact integer in "
    "0..0xffffffff; length is an exact integer in 1..0x100000000 and the "
    "half-open end must not exceed 0x100000000; attributes is rw- or rwx. "
    "Names are case-insensitively unique and no extra region may overlap a "
    "declared base or another extra region. Omit the option for no extra "
    "regions; Toolkit never guesses an external region."
)


class ExtraRegionError(Exception):
    """A stable extra-region failure with portable field/rule/remediation."""

    def __init__(self, message: str, field: str, rule: str) -> None:
        super().__init__(message)
        self.code = "EXTRA_REGIONS_INVALID"
        self.message = message
        self.details: dict[str, object] = {
            "field": field,
            "rule": rule,
            "remediation": _REMEDIATION,
        }


def _fail(message: str, field: str, rule: str) -> ExtraRegionError:
    return ExtraRegionError(message, field, rule)


@dataclass(frozen=True)
class ExtraRegion:
    """One validated explicit writable RAM region."""

    name: str
    origin: int
    length: int
    attributes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "length": self.length,
            "attributes": self.attributes,
        }


def _name_error(value: object, field: str) -> ExtraRegionError | None:
    if not isinstance(value, str):
        return _fail("extra region name must be a string", field, "type")
    if len(value) > MAX_EXTRA_REGION_NAME_LENGTH:
        return _fail("extra region name is too long", field, "length")
    if EXTRA_REGION_NAME_RE.fullmatch(value) is None:
        return _fail(
            "extra region name is not a linker-safe ASCII identifier",
            field,
            "pattern",
        )
    return None


def _entry_region(entry: object, index: int) -> ExtraRegion:
    field = f"extraRegions[{index}]"
    if isinstance(entry, ExtraRegion):
        entry = entry.to_dict()
    if not isinstance(entry, Mapping):
        raise _fail("extra region entry must be an object", field, "type")
    keys = set(entry)
    unknown = sorted(
        (key for key in keys if key not in EXTRA_REGION_FIELDS), key=str
    )
    if unknown:
        key = unknown[0]
        # Diagnostics stay bounded and portable: only a short ASCII identifier
        # is echoed; arbitrary long/path-like text never enters the field.
        display = (
            key
            if isinstance(key, str)
            and len(key) <= 32
            and EXTRA_REGION_NAME_RE.fullmatch(key) is not None
            else "<unknown>"
        )
        raise _fail(
            "extra region object contains an unknown field",
            f"{field}.{display}",
            "unknownKey",
        )
    missing = sorted(EXTRA_REGION_FIELDS - keys)
    if missing:
        raise _fail(
            "extra region object is incomplete",
            f"{field}.{missing[0]}",
            "required",
        )

    name = entry["name"]
    error = _name_error(name, f"{field}.name")
    if error is not None:
        raise error
    assert isinstance(name, str)

    origin = entry["origin"]
    if type(origin) is not int:
        raise _fail("extra region origin must be an integer", f"{field}.origin", "type")
    if origin < 0 or origin > 0xFFFFFFFF:
        raise _fail("extra region origin is out of range", f"{field}.origin", "range")

    length = entry["length"]
    if type(length) is not int:
        raise _fail("extra region length must be an integer", f"{field}.length", "type")
    if length < 1 or length > 0x1_0000_0000:
        raise _fail("extra region length is out of range", f"{field}.length", "range")

    if origin + length > 0x1_0000_0000:
        raise _fail("extra region end is out of range", field, "range")

    attributes = entry["attributes"]
    if not isinstance(attributes, str):
        raise _fail(
            "extra region attributes must be a string", f"{field}.attributes", "type"
        )
    if attributes not in EXTRA_REGION_ATTRIBUTES:
        raise _fail(
            "extra region attributes must be rw- or rwx",
            f"{field}.attributes",
            "attributes",
        )
    return ExtraRegion(name=name, origin=origin, length=length, attributes=attributes)


def _overlaps(
    origin: int, length: int, other_origin: int, other_length: int
) -> bool:
    return origin < other_origin + other_length and other_origin < origin + length


def _validate_extra_names(regions: Sequence[ExtraRegion]) -> None:
    seen: dict[str, int] = {}
    for index, region in enumerate(regions):
        folded = region.name.casefold()
        if folded in seen:
            raise _fail(
                "extra region names must be unique ignoring case",
                f"extraRegions[{index}].name",
                "casefoldCollision",
            )
        seen[folded] = index


def _validate_extra_overlaps(regions: Sequence[ExtraRegion]) -> None:
    for index, region in enumerate(regions):
        for prior in regions[:index]:
            if _overlaps(region.origin, region.length, prior.origin, prior.length):
                raise _fail(
                    "extra regions must not overlap each other",
                    f"extraRegions[{index}]",
                    "overlap",
                )


def normalize_extra_regions(value: object) -> tuple[ExtraRegion, ...]:
    """Validate one already-parsed option and return the immutable request.

    ``None`` and an empty sequence are the same no-extra request.  A direct
    ``ExtraRegion`` is accepted only inside the bounded sequence so its fields
    are revalidated with the same exact rules.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(
        value, Sequence
    ):
        raise _fail(
            "extraRegions must be an array of region objects", "extraRegions", "type"
        )
    if len(value) > MAX_EXTRA_REGIONS:
        raise _fail(
            "extraRegions exceeds the supported entry count",
            "extraRegions",
            "count",
        )
    regions = tuple(_entry_region(entry, index) for index, entry in enumerate(value))
    _validate_extra_names(regions)
    _validate_extra_overlaps(regions)
    return regions


def validate_extra_regions(
    regions: object, base_regions: object
) -> tuple[ExtraRegion, ...]:
    """Revalidate ``regions`` and reject collisions/overlap with base regions.

    Overlap inside the declared base map is not reinterpreted; only the
    owner-supplied extras are checked against it.
    """
    extras = normalize_extra_regions(regions)
    facts = region_facts(base_regions if isinstance(base_regions, Sequence) else ())
    folded_base = {fact.name.casefold() for fact in facts}
    for index, region in enumerate(extras):
        if region.name.casefold() in folded_base:
            raise _fail(
                "extra region name collides with a declared region",
                f"extraRegions[{index}].name",
                "casefoldCollision",
            )
    for index, region in enumerate(extras):
        for fact in facts:
            if _overlaps(region.origin, region.length, fact.origin, fact.length):
                raise _fail(
                    "extra region overlaps a declared region",
                    f"extraRegions[{index}]",
                    "overlap",
                )
    return extras


def combined_regions(base_regions: object, regions: object) -> tuple[object, ...]:
    """Return the ordered base-plus-extra region tuple (base order preserved)."""
    base = tuple(base_regions) if isinstance(base_regions, Sequence) else ()
    extras = tuple(regions) if isinstance(regions, Sequence) else ()
    return base + extras


def extra_region_names(regions: Sequence[ExtraRegion]) -> tuple[str, ...]:
    return tuple(region.name for region in regions)


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(value)


def parse_extra_regions_json(text: object) -> tuple[ExtraRegion, ...]:
    """Parse the CLI ``--extra-regions`` JSON array with duplicate-key refusal."""
    if not isinstance(text, str):
        raise _fail(
            "extraRegions must be a JSON array string", "extraRegions", "type"
        )
    if len(text.encode("utf-8", "replace")) > MAX_EXTRA_REGIONS_JSON_BYTES:
        raise _fail(
            "extraRegions exceeds the supported JSON size", "extraRegions", "size"
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except _DuplicateJsonKey:
        raise _fail(
            "extraRegions contains a duplicate object key",
            "extraRegions",
            "duplicateKey",
        ) from None
    except RecursionError:
        raise _fail(
            "extraRegions nesting exceeds the supported depth",
            "extraRegions",
            "nesting",
        ) from None
    except json.JSONDecodeError:
        raise _fail("extraRegions is not valid JSON", "extraRegions", "json") from None
    except (ValueError, OverflowError):
        raise _fail(
            "extraRegions contains an unsupported JSON value",
            "extraRegions",
            "json",
        ) from None
    if not isinstance(value, list):
        raise _fail(
            "extraRegions must be a JSON array", "extraRegions", "type"
        )
    return normalize_extra_regions(value)


def normalize_extra_regions_option(value: object) -> tuple[ExtraRegion, ...]:
    """Accept ``None``, a parsed array or the CLI JSON text."""
    if value is None:
        return ()
    if isinstance(value, str):
        return parse_extra_regions_json(value)
    return normalize_extra_regions(value)


__all__ = [
    "EXTRA_REGION_ATTRIBUTES",
    "EXTRA_REGION_NAME_RE",
    "ExtraRegion",
    "ExtraRegionError",
    "MAX_EXTRA_REGIONS",
    "MAX_EXTRA_REGIONS_JSON_BYTES",
    "MAX_EXTRA_REGION_NAME_LENGTH",
    "combined_regions",
    "extra_region_names",
    "normalize_extra_regions",
    "normalize_extra_regions_option",
    "parse_extra_regions_json",
    "validate_extra_regions",
]
