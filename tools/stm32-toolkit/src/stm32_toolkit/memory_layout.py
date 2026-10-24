"""Explicit managed memory-layout validation and region selection.

Managed generation always needs one Flash role and one role for each of
``.data``, ``.bss``, ``.heap`` and ``.stack``.  This module owns the single
validation/selection implementation shared by the project model, migration
planning and configuration generation:

* an explicit layout has exactly the five required role names and every name
  must address an existing region with the required access;
* with no explicit layout, only an unambiguous single-Flash/single-RAM
  topology is usable; anything else is reported as a selection requirement
  with the actual candidates;
* a writable executable RAM region is never inferred as Flash.

This module performs no I/O and has no Toolkit imports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LAYOUT_ROLES = ("flash", "data", "bss", "heap", "stack")
RAM_ROLES = ("data", "bss", "heap", "stack")
MAX_LAYOUT_JSON_BYTES = 64 * 1024

_REMEDIATION = (
    "Choose an explicit memoryLayout object with exactly flash, data, bss, heap "
    "and stack keys; every value must name an existing region. Flash must be "
    "readable and executable but not writable, and every data/bss/heap/stack "
    "region must be readable and writable."
)


class MemoryLayoutError(Exception):
    """A stable memory-layout failure with bounded structured details."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details if details is not None else {})


def memory_layout_error(
    code: str,
    message: str,
    field: str,
    rule: str,
    remediation: str = _REMEDIATION,
) -> MemoryLayoutError:
    return MemoryLayoutError(
        code,
        message,
        {"field": field, "rule": rule, "remediation": remediation},
    )


@dataclass(frozen=True)
class MemoryLayout:
    """The immutable five-role managed section mapping."""

    flash: str
    data: str
    bss: str
    heap: str
    stack: str

    def __post_init__(self) -> None:
        for role in LAYOUT_ROLES:
            value = getattr(self, role)
            if type(value) is not str or not value:
                raise memory_layout_error(
                    "MEMORY_LAYOUT_INVALID",
                    "memoryLayout role values must be non-empty region names",
                    f"memoryLayout.{role}",
                    "type",
                )

    def to_dict(self) -> dict[str, str]:
        return {
            "flash": self.flash,
            "data": self.data,
            "bss": self.bss,
            "heap": self.heap,
            "stack": self.stack,
        }

    def role(self, name: str) -> str:
        return {
            "flash": self.flash,
            "data": self.data,
            "bss": self.bss,
            "heap": self.heap,
            "stack": self.stack,
        }[name]


@dataclass(frozen=True)
class RegionFact:
    """The stable subset of one memory region used for role selection."""

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

    @property
    def flags(self) -> frozenset[str]:
        return frozenset(self.attributes)


@dataclass(frozen=True)
class MemoryLayoutResolution:
    """The resolved role map plus the actual candidate evidence.

    ``status`` is ``implicit`` (single unambiguous Flash and RAM), ``explicit``
    (the reviewed five-role mapping) or ``requires-selection`` (no usable
    implicit choice; ``layout`` is then ``None``).
    """

    status: str
    layout: MemoryLayout | None
    flash_candidates: tuple[RegionFact, ...]
    ram_candidates: tuple[RegionFact, ...]
    unresolved_roles: tuple[str, ...] = ()

    @property
    def requires_selection(self) -> bool:
        return self.status == "requires-selection"

    def candidates_dict(self) -> dict[str, list[dict[str, object]]]:
        return {
            "flash": [fact.to_dict() for fact in self.flash_candidates],
            "ram": [fact.to_dict() for fact in self.ram_candidates],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "layout": self.layout.to_dict() if self.layout is not None else None,
            "candidates": self.candidates_dict(),
        }

    def blocker_details(self) -> dict[str, object]:
        """Bounded structured evidence for a selection requirement."""
        return {
            "unresolvedRoles": list(self.unresolved_roles),
            "candidates": self.candidates_dict(),
            "remediation": self.remediation(),
        }

    def remediation(self) -> str:
        if not self.requires_selection:
            return _REMEDIATION
        flash_names = ", ".join(fact.name for fact in self.flash_candidates) or "none"
        ram_names = ", ".join(fact.name for fact in self.ram_candidates) or "none"
        return (
            "Memory roles "
            + ", ".join(self.unresolved_roles)
            + " are unresolved. Flash candidates: "
            + flash_names
            + "; RAM candidates: "
            + ram_names
            + ". Pass an explicit memoryLayout naming one Flash region and the "
            "data/bss/heap/stack regions. A writable executable region is never "
            "selected as Flash, and other RAM is left unused only by an explicit "
            "choice."
        )


def _role_access_error(role: str, fact: RegionFact) -> MemoryLayoutError | None:
    flags = fact.flags
    if role == "flash":
        if "r" not in flags or "x" not in flags or "w" in flags:
            return memory_layout_error(
                "MEMORY_LAYOUT_INVALID",
                "Flash must be a readable, executable, non-writable region",
                f"memory.layout.{role}",
                "access",
                "Choose a readable executable non-writable region for flash.",
            )
        return None
    if "r" not in flags or "w" not in flags:
        return memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "data, bss, heap and stack must name readable writable regions",
            f"memory.layout.{role}",
            "access",
            "Choose readable writable regions for data, bss, heap and stack.",
        )
    return None


def region_fact(value: object) -> RegionFact:
    """Normalize a model region object or a manifest mapping."""
    if isinstance(value, Mapping):
        return RegionFact(
            name=str(value["name"]),
            origin=value["origin"],  # type: ignore[arg-type]
            length=value["length"],  # type: ignore[arg-type]
            attributes=str(value["attributes"]),
        )
    return RegionFact(
        name=value.name,  # type: ignore[attr-defined]
        origin=value.origin,  # type: ignore[attr-defined]
        length=value.length,  # type: ignore[attr-defined]
        attributes=value.attributes,  # type: ignore[attr-defined]
    )


def region_facts(regions: Sequence[object]) -> tuple[RegionFact, ...]:
    return tuple(region_fact(region) for region in regions)


def normalize_memory_layout(value: object) -> MemoryLayout:
    """Validate one already-parsed layout object without touching the filesystem."""
    if isinstance(value, MemoryLayout):
        return value
    if not isinstance(value, Mapping):
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout must be a JSON object",
            "memoryLayout",
            "type",
        )
    unknown = sorted(key for key in value if key not in LAYOUT_ROLES)
    if unknown:
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout contains an unknown role",
            f"memoryLayout.{unknown[0]}",
            "unknownKey",
        )
    for role in LAYOUT_ROLES:
        if role not in value:
            raise memory_layout_error(
                "MEMORY_LAYOUT_INVALID",
                "memoryLayout is incomplete",
                f"memoryLayout.{role}",
                "required",
            )
        name = value[role]
        if not isinstance(name, str) or not name:
            raise memory_layout_error(
                "MEMORY_LAYOUT_INVALID",
                "memoryLayout role values must be non-empty region names",
                f"memoryLayout.{role}",
                "type",
            )
    return MemoryLayout(
        flash=value["flash"],
        data=value["data"],
        bss=value["bss"],
        heap=value["heap"],
        stack=value["stack"],
    )


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def parse_memory_layout_json(text: str) -> MemoryLayout:
    """Parse the CLI ``--memory-layout`` JSON object with duplicate-key refusal."""
    if not isinstance(text, str):
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout must be a JSON object string",
            "memoryLayout",
            "type",
        )
    if len(text.encode("utf-8", "replace")) > MAX_LAYOUT_JSON_BYTES:
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout exceeds the supported size",
            "memoryLayout",
            "size",
        )
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateJsonKey:
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout contains a duplicate role key",
            "memoryLayout",
            "duplicateKey",
        ) from None
    except RecursionError:
        # Deeply nested input must fail with stable bounded details instead of
        # escaping as an interpreter error; global recursion limits are kept.
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout nesting exceeds the supported depth",
            "memoryLayout",
            "nesting",
        ) from None
    except json.JSONDecodeError:
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout is not valid JSON",
            "memoryLayout",
            "json",
        ) from None
    except (ValueError, OverflowError):
        # ``json`` raises plain ValueError for a numeric literal beyond the
        # interpreter's integer-string conversion limit; that is malformed or
        # unsupported input, not an internal failure.
        raise memory_layout_error(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout contains an unsupported JSON value",
            "memoryLayout",
            "json",
        ) from None
    return normalize_memory_layout(value)


def normalize_memory_layout_option(value: object) -> MemoryLayout | None:
    """Accept ``None``, a parsed mapping, a ``MemoryLayout`` or CLI JSON text."""
    if value is None:
        return None
    if isinstance(value, MemoryLayout):
        return value
    if isinstance(value, str):
        return parse_memory_layout_json(value)
    return normalize_memory_layout(value)


def validate_memory_layout_regions(
    layout: MemoryLayout, regions: Sequence[object]
) -> None:
    """Require every role to name an existing region with the required access."""
    facts = region_facts(regions)
    by_name = {fact.name: fact for fact in facts}
    for role in LAYOUT_ROLES:
        name = layout.role(role)
        fact = by_name.get(name)
        if fact is None:
            available = ", ".join(sorted(by_name)) or "none"
            raise memory_layout_error(
                "MEMORY_LAYOUT_INVALID",
                "memoryLayout names an unknown memory region",
                f"memory.layout.{role}",
                "unknownRegion",
                f"Choose an existing region for {role}; declared regions: {available}.",
            )
        error = _role_access_error(role, fact)
        if error is not None:
            raise error


def _flash_candidates(facts: tuple[RegionFact, ...]) -> tuple[RegionFact, ...]:
    return tuple(
        fact
        for fact in facts
        if "r" in fact.flags and "x" in fact.flags and "w" not in fact.flags
    )


def _ram_candidates(facts: tuple[RegionFact, ...]) -> tuple[RegionFact, ...]:
    return tuple(
        fact for fact in facts if "r" in fact.flags and "w" in fact.flags
    )


def resolve_memory_layout(
    regions: Sequence[object],
    layout: MemoryLayout | None = None,
    *,
    extra_region_names: Sequence[str] = (),
) -> MemoryLayoutResolution:
    """Resolve explicit roles, or the only unambiguous implicit topology.

    ``extra_region_names`` marks owner-supplied regions that must never be
    selected implicitly for data/bss/heap/stack.  The candidates still report
    every actual region, so an explicit reviewed choice may name one.
    """
    facts = region_facts(regions)
    flash_candidates = _flash_candidates(facts)
    ram_candidates = _ram_candidates(facts)
    if layout is not None:
        validate_memory_layout_regions(layout, facts)
        return MemoryLayoutResolution(
            "explicit", layout, flash_candidates, ram_candidates, ()
        )
    extra_names = {
        name.casefold() for name in extra_region_names if isinstance(name, str)
    }
    if len(flash_candidates) == 1 and len(ram_candidates) == 1:
        ram = ram_candidates[0]
        if ram.name.casefold() in extra_names:
            # The only writable region is owner-supplied external RAM; placing
            # managed sections there requires an explicit reviewed mapping.
            return MemoryLayoutResolution(
                "requires-selection",
                None,
                flash_candidates,
                ram_candidates,
                tuple(RAM_ROLES),
            )
        implicit = MemoryLayout(
            flash=flash_candidates[0].name,
            data=ram.name,
            bss=ram.name,
            heap=ram.name,
            stack=ram.name,
        )
        return MemoryLayoutResolution(
            "implicit", implicit, flash_candidates, ram_candidates, ()
        )
    unresolved: list[str] = []
    if len(flash_candidates) != 1:
        unresolved.append("flash")
    if len(ram_candidates) != 1:
        unresolved.extend(RAM_ROLES)
    return MemoryLayoutResolution(
        "requires-selection",
        None,
        flash_candidates,
        ram_candidates,
        tuple(unresolved),
    )


__all__ = [
    "LAYOUT_ROLES",
    "MAX_LAYOUT_JSON_BYTES",
    "RAM_ROLES",
    "MemoryLayout",
    "MemoryLayoutError",
    "MemoryLayoutResolution",
    "RegionFact",
    "memory_layout_error",
    "normalize_memory_layout",
    "normalize_memory_layout_option",
    "parse_memory_layout_json",
    "region_fact",
    "region_facts",
    "resolve_memory_layout",
    "validate_memory_layout_regions",
]
