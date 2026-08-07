"""Bounded ELF/DWARF catalog with a deliberately tiny lookup language."""

from __future__ import annotations

import io
import re
import struct
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from elftools.common.exceptions import ELFError, DWARFError as ElfToolsDwarfError
from elftools.dwarf.dwarf_expr import DWARFExprParser
from elftools.dwarf.locationlists import LocationExpr, LocationParser
from elftools.elf.elffile import ELFFile

from .types import DwarfError, DwarfMember, DwarfSelection, DwarfType


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_ELF_BYTES = 64 * 1024 * 1024
_MAX_DEBUG_BYTES = 32 * 1024 * 1024
_MAX_DIES = 250_000
_MAX_DIE_DEPTH = 64
_MAX_CATALOG_ENTRIES = 50_000
_MAX_TYPE_DEPTH = 32
_MAX_TYPE_BYTES = 1024 * 1024
_MAX_ARRAY_ELEMENTS = 1_000_000
_MAX_EXPRESSION = 256
_MAX_REGIONS = 64
_MAX_ADDRESS = (1 << 64) - 1


def _fail(code: str, message: str) -> DwarfError:
    return DwarfError(code, message)


def _name(die: object, fallback: str) -> str:
    attributes = getattr(die, "attributes", {})
    attribute = attributes.get("DW_AT_name")
    if attribute is None:
        return fallback
    value = attribute.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:128]
    return str(value)[:128]


def _integer_attribute(die: object, attribute_name: str) -> int | None:
    attribute = getattr(die, "attributes", {}).get(attribute_name)
    if attribute is None or isinstance(attribute.value, bool):
        return None
    return attribute.value if isinstance(attribute.value, int) else None


@dataclass(frozen=True)
class _CatalogSymbol:
    name: str
    dwarf_type: DwarfType | None
    address: int | None
    location_error: str | None
    type_error: str | None = None


class _TypeGraph:
    def __init__(self, *, max_depth: int, max_type_bytes: int, max_elements: int):
        self._max_depth = max_depth
        self._max_type_bytes = max_type_bytes
        self._max_elements = max_elements
        self._cache: dict[int, DwarfType] = {}
        self._active: set[int] = set()

    def resolve_attribute(self, die: object, depth: int = 0) -> DwarfType:
        try:
            target = die.get_DIE_from_attribute("DW_AT_type")
        except (KeyError, TypeError, ValueError, ElfToolsDwarfError) as exc:
            raise _fail("DWARF_TYPE_INCOMPLETE", "DWARF type reference is unavailable") from None
        if target is None:
            raise _fail("DWARF_TYPE_INCOMPLETE", "DWARF type reference is unavailable")
        return self.resolve(target, depth + 1)

    def resolve(self, die: object, depth: int) -> DwarfType:
        if depth > self._max_depth:
            raise _fail("DWARF_TYPE_DEPTH_EXCEEDED", "DWARF type graph is too deep")
        offset = getattr(die, "offset", None)
        if not isinstance(offset, int):
            raise _fail("DWARF_TYPE_UNSUPPORTED", "DWARF type has no stable identity")
        cached = self._cache.get(offset)
        if cached is not None:
            return cached
        if offset in self._active:
            raise _fail("DWARF_TYPE_RECURSIVE", "Recursive DWARF value type is unsupported")
        self._active.add(offset)
        try:
            result = self._resolve_uncached(die, depth)
            if result.byte_size < 1 or result.byte_size > self._max_type_bytes:
                raise _fail("DWARF_TYPE_SIZE_INVALID", "DWARF type size is out of bounds")
            self._cache[offset] = result
            return result
        finally:
            self._active.discard(offset)

    def _resolve_uncached(self, die: object, depth: int) -> DwarfType:
        tag = getattr(die, "tag", "")
        if tag == "DW_TAG_base_type":
            return self._base(die)
        if tag in {
            "DW_TAG_typedef",
            "DW_TAG_const_type",
            "DW_TAG_volatile_type",
            "DW_TAG_restrict_type",
            "DW_TAG_atomic_type",
        }:
            target = self.resolve_attribute(die, depth)
            aliases = target.aliases
            qualifiers = target.qualifiers
            if tag == "DW_TAG_typedef":
                aliases = (_name(die, "<typedef>"),) + aliases
            else:
                qualifier = {
                    "DW_TAG_const_type": "const",
                    "DW_TAG_volatile_type": "volatile",
                    "DW_TAG_restrict_type": "restrict",
                    "DW_TAG_atomic_type": "atomic",
                }[tag]
                qualifiers = tuple(
                    item
                    for item in ("const", "volatile", "restrict", "atomic")
                    if item in set(target.qualifiers) | {qualifier}
                )
            return replace(target, aliases=aliases, qualifiers=qualifiers)
        if tag == "DW_TAG_enumeration_type":
            return self._enum(die, depth)
        if tag == "DW_TAG_array_type":
            return self._array(die, depth)
        if tag in {"DW_TAG_structure_type", "DW_TAG_union_type"}:
            return self._aggregate(die, depth, "structure" if tag.endswith("structure_type") else "union")
        if tag == "DW_TAG_pointer_type":
            size = self._checked_size(die)
            return DwarfType("pointer", _name(die, "pointer"), size, signed=False)
        raise _fail("DWARF_TYPE_UNSUPPORTED", "DWARF type kind is unsupported")

    def _checked_size(self, die: object) -> int:
        size = _integer_attribute(die, "DW_AT_byte_size")
        if size is None or size < 1 or size > self._max_type_bytes:
            raise _fail("DWARF_TYPE_SIZE_INVALID", "DWARF type size is out of bounds")
        return size

    def _base(self, die: object) -> DwarfType:
        size = self._checked_size(die)
        encoding = _integer_attribute(die, "DW_AT_encoding")
        name = _name(die, "<base>")
        if encoding in (5, 6):
            return DwarfType("integer", name, size, signed=True, encoding="signed")
        if encoding in (7, 8):
            return DwarfType("integer", name, size, signed=False, encoding="unsigned")
        if encoding == 2:
            return DwarfType("boolean", name, size, signed=False, encoding="boolean")
        if encoding == 4:
            return DwarfType("float", name, size, encoding="ieee754")
        raise _fail("DWARF_TYPE_UNSUPPORTED", "DWARF base type encoding is unsupported")

    def _enum(self, die: object, depth: int) -> DwarfType:
        size = self._checked_size(die)
        encoding = _integer_attribute(die, "DW_AT_encoding")
        signed = encoding in (5, 6)
        if encoding not in (5, 6, 7, 8):
            try:
                underlying = self.resolve_attribute(die, depth)
            except DwarfError:
                raise _fail("DWARF_TYPE_INCOMPLETE", "Enum signedness is unavailable") from None
            if underlying.kind != "integer" or underlying.byte_size != size:
                raise _fail("DWARF_TYPE_INCOMPLETE", "Enum underlying type is invalid")
            signed = bool(underlying.signed)
        values: list[tuple[int, str]] = []
        for child in die.iter_children():
            if child.tag != "DW_TAG_enumerator":
                continue
            value = _integer_attribute(child, "DW_AT_const_value")
            if value is None:
                raise _fail("DWARF_TYPE_INCOMPLETE", "Enum value is unavailable")
            values.append((value, _name(child, "<enumerator>")))
        return DwarfType(
            "enum", _name(die, "<enum>"), size, signed=signed, enum_values=tuple(values)
        )

    def _array(self, die: object, depth: int) -> DwarfType:
        element = self.resolve_attribute(die, depth)
        dimensions = [child for child in die.iter_children() if child.tag == "DW_TAG_subrange_type"]
        if len(dimensions) != 1:
            raise _fail("DWARF_TYPE_UNSUPPORTED", "Only bounded one-dimensional arrays are supported")
        subrange = dimensions[0]
        lower = _integer_attribute(subrange, "DW_AT_lower_bound")
        if lower not in (None, 0):
            raise _fail("DWARF_TYPE_UNSUPPORTED", "Non-zero array lower bound is unsupported")
        count = _integer_attribute(subrange, "DW_AT_count")
        if count is None:
            upper = _integer_attribute(subrange, "DW_AT_upper_bound")
            count = None if upper is None else upper + 1
        if count is None:
            raise _fail("DWARF_TYPE_INCOMPLETE", "Array bounds are unavailable")
        if count < 1 or count > self._max_elements:
            raise _fail("DWARF_ARRAY_LIMIT_EXCEEDED", "Array element count is out of bounds")
        size = element.byte_size * count
        declared_size = _integer_attribute(die, "DW_AT_byte_size")
        if size > self._max_type_bytes or declared_size not in (None, size):
            raise _fail("DWARF_TYPE_SIZE_INVALID", "Array byte size is invalid")
        return DwarfType(
            "array",
            _name(die, f"{element.name}[{count}]"),
            size,
            element_type=element,
            element_count=count,
        )

    def _aggregate(self, die: object, depth: int, kind: str) -> DwarfType:
        size = self._checked_size(die)
        members: list[DwarfMember] = []
        for child in die.iter_children():
            if child.tag != "DW_TAG_member":
                continue
            bit_size = _integer_attribute(child, "DW_AT_bit_size")
            member_type = self.resolve_attribute(child, depth)
            offset = _integer_attribute(child, "DW_AT_data_member_location")
            if offset is None and bit_size is not None:
                data_bit_offset = _integer_attribute(child, "DW_AT_data_bit_offset")
                offset = None if data_bit_offset is None else data_bit_offset // 8
            if offset is None or offset < 0:
                raise _fail("DWARF_TYPE_UNSUPPORTED", "Computed member locations are unsupported")
            if offset + member_type.byte_size > size:
                raise _fail("DWARF_TYPE_SIZE_INVALID", "Structure member exceeds its container")
            members.append(DwarfMember(_name(child, "<member>"), offset, member_type, bit_size))
        return DwarfType(kind, _name(die, f"<{kind}>"), size, members=tuple(members))


class DwarfCatalog:
    """Immutable variable catalog parsed from bounded, current ELF/DWARF bytes."""

    def __init__(
        self,
        symbols: Mapping[str, tuple[_CatalogSymbol, ...]],
        readable_regions: tuple[tuple[int, int], ...],
        little_endian: bool,
    ) -> None:
        self._symbols = MappingProxyType(dict(symbols))
        self._readable_regions = readable_regions
        self._little_endian = little_endian

    @classmethod
    def from_elf(
        cls,
        path: str | Path,
        *,
        readable_regions: Iterable[tuple[int, int]] | None = None,
        max_elf_bytes: int = _MAX_ELF_BYTES,
        max_debug_bytes: int = _MAX_DEBUG_BYTES,
        max_dies: int = _MAX_DIES,
        max_die_depth: int = _MAX_DIE_DEPTH,
        max_catalog_entries: int = _MAX_CATALOG_ENTRIES,
        max_type_depth: int = _MAX_TYPE_DEPTH,
        max_type_bytes: int = _MAX_TYPE_BYTES,
        max_array_elements: int = _MAX_ARRAY_ELEMENTS,
    ) -> "DwarfCatalog":
        for value in (
            max_elf_bytes,
            max_debug_bytes,
            max_dies,
            max_die_depth,
            max_catalog_entries,
            max_type_depth,
            max_type_bytes,
            max_array_elements,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _fail("DWARF_LIMIT_INVALID", "DWARF parser limit is invalid")
        if max_elf_bytes > _MAX_ELF_BYTES:
            max_elf_bytes = _MAX_ELF_BYTES
        if max_debug_bytes > _MAX_DEBUG_BYTES:
            max_debug_bytes = _MAX_DEBUG_BYTES
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(max_elf_bytes + 1)
        except (OSError, ValueError, TypeError):
            raise _fail("DWARF_ELF_UNAVAILABLE", "ELF bytes are unavailable") from None
        if len(data) > max_elf_bytes:
            raise _fail("DWARF_ELF_TOO_LARGE", "ELF exceeds the configured byte limit")
        try:
            elf = ELFFile(io.BytesIO(data))
            cls._validate_debug_sections(elf, data, max_debug_bytes)
            if not elf.has_dwarf_info(strict=True):
                raise _fail("DWARF_INFO_UNAVAILABLE", "ELF contains no DWARF information")
            dwarf = elf.get_dwarf_info()
            regions = cls._normalize_regions(readable_regions)
            type_graph = _TypeGraph(
                max_depth=max_type_depth,
                max_type_bytes=max_type_bytes,
                max_elements=max_array_elements,
            )
            expression_parser = DWARFExprParser(dwarf.structs)
            location_parser = LocationParser(dwarf.location_lists())
            entries: dict[str, list[_CatalogSymbol]] = {}
            die_count = 0
            catalog_count = 0
            for cu in dwarf.iter_CUs():
                for die in cu.iter_DIEs():
                    die_count += 1
                    if die_count > max_dies:
                        raise _fail("DWARF_DIE_LIMIT_EXCEEDED", "DWARF DIE count exceeds its limit")
                    depth = 0
                    parent = getattr(die, "_parent", None)
                    while parent is not None:
                        depth += 1
                        if depth > max_die_depth:
                            raise _fail(
                                "DWARF_DIE_DEPTH_EXCEEDED",
                                "DWARF DIE nesting exceeds its limit",
                            )
                        parent = getattr(parent, "_parent", None)
                    if die.tag != "DW_TAG_variable":
                        continue
                    if _integer_attribute(die, "DW_AT_declaration") == 1:
                        continue
                    name = _name(die, "")
                    if not _IDENTIFIER.fullmatch(name):
                        continue
                    catalog_count += 1
                    if catalog_count > max_catalog_entries:
                        raise _fail(
                            "DWARF_CATALOG_LIMIT_EXCEEDED",
                            "DWARF catalog entry count exceeds its limit",
                        )
                    try:
                        dwarf_type = type_graph.resolve_attribute(die)
                        type_error = None
                    except DwarfError as exc:
                        dwarf_type = None
                        type_error = exc.code
                    address, location_error = cls._location(
                        die, cu, location_parser, expression_parser
                    )
                    entries.setdefault(name, []).append(
                        _CatalogSymbol(
                            name, dwarf_type, address, location_error, type_error
                        )
                    )
            frozen = {name: tuple(values) for name, values in entries.items()}
            return cls(frozen, regions, bool(elf.little_endian))
        except DwarfError:
            raise
        except (ELFError, ElfToolsDwarfError, KeyError, TypeError, ValueError, IndexError, OverflowError):
            raise _fail("DWARF_ELF_MALFORMED", "ELF or DWARF data is malformed") from None

    @staticmethod
    def _validate_debug_sections(
        elf: ELFFile, data: bytes, max_debug_bytes: int
    ) -> None:
        section_offset = int(elf.header["e_shoff"])
        section_size = int(elf.header["e_shentsize"])
        section_count = int(elf.header["e_shnum"])
        endian = "<" if elf.little_endian else ">"
        flag_format = endian + ("I" if elf.elfclass == 32 else "Q")
        for index in range(section_count):
            flag_offset = section_offset + index * section_size + 8
            if flag_offset < 0 or flag_offset + struct.calcsize(flag_format) > len(data):
                raise _fail("DWARF_ELF_MALFORMED", "ELF section headers are malformed")
            flags = struct.unpack_from(flag_format, data, flag_offset)[0]
            if flags & 0x800:
                raise _fail(
                    "DWARF_COMPRESSED_UNSUPPORTED",
                    "Compressed ELF sections are unsupported",
                )
        total = 0
        for section in elf.iter_sections():
            if section.name.startswith(".zdebug"):
                raise _fail(
                    "DWARF_COMPRESSED_UNSUPPORTED",
                    "Compressed ELF sections are unsupported",
                )
            if section.name.startswith(".debug"):
                total += int(section.header["sh_size"])
                if total > max_debug_bytes:
                    raise _fail(
                        "DWARF_DEBUG_INFO_TOO_LARGE",
                        "DWARF debug sections exceed their byte limit",
                    )

    @staticmethod
    def _normalize_regions(
        regions: Iterable[tuple[int, int]] | None,
    ) -> tuple[tuple[int, int], ...]:
        if regions is None:
            raise _fail(
                "DWARF_READABLE_REGION_REQUIRED",
                "Project-readable memory regions are required",
            )
        normalized: list[tuple[int, int]] = []
        try:
            for start, end in regions:
                if (
                    isinstance(start, bool)
                    or isinstance(end, bool)
                    or not isinstance(start, int)
                    or not isinstance(end, int)
                    or start < 0
                    or end <= start
                    or end > _MAX_ADDRESS + 1
                ):
                    raise _fail("DWARF_READABLE_REGION_INVALID", "Readable memory region is invalid")
                normalized.append((start, end))
                if len(normalized) > _MAX_REGIONS:
                    raise _fail("DWARF_READABLE_REGION_INVALID", "Too many readable memory regions")
        except (TypeError, ValueError):
            raise _fail("DWARF_READABLE_REGION_INVALID", "Readable memory region is invalid") from None
        normalized.sort()
        return tuple(normalized)

    @staticmethod
    def _location(die, cu, parser: LocationParser, expression_parser: DWARFExprParser):
        attribute = die.attributes.get("DW_AT_location")
        if attribute is None:
            if "DW_AT_const_value" in die.attributes:
                return None, "DWARF_LOCATION_OPTIMIZED_OUT"
            return None, "DWARF_LOCATION_UNAVAILABLE"
        try:
            parsed = parser.parse_from_attribute(attribute, cu["version"], die)
            expressions = (
                [parsed.loc_expr]
                if isinstance(parsed, LocationExpr)
                else [entry.loc_expr for entry in parsed if hasattr(entry, "loc_expr")]
            )
            if not expressions:
                return None, "DWARF_LOCATION_OPTIMIZED_OUT"
            addresses: set[int] = set()
            failures: set[str] = set()
            for expression in expressions:
                operations = expression_parser.parse_expr(expression)
                if len(operations) == 1 and operations[0].op_name == "DW_OP_addr":
                    addresses.add(int(operations[0].args[0]))
                    continue
                names = {operation.op_name for operation in operations}
                if any(name.startswith(("DW_OP_reg", "DW_OP_breg")) for name in names):
                    failures.add("DWARF_LOCATION_REGISTER_ONLY")
                elif "DW_OP_implicit_value" in names or "DW_OP_stack_value" in names:
                    failures.add("DWARF_LOCATION_OPTIMIZED_OUT")
                elif "DW_OP_fbreg" in names:
                    failures.add("DWARF_LOCATION_UNAVAILABLE")
                else:
                    failures.add("DWARF_LOCATION_UNSUPPORTED")
            if addresses and not failures and len(addresses) == 1:
                return next(iter(addresses)), None
            if len(failures) == 1:
                return None, next(iter(failures))
            return None, "DWARF_LOCATION_UNAVAILABLE"
        except (ElfToolsDwarfError, KeyError, TypeError, ValueError, IndexError, OverflowError):
            return None, "DWARF_LOCATION_UNSUPPORTED"

    def lookup(self, expression: str) -> DwarfSelection:
        if not isinstance(expression, str):
            raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "DWARF expression is unsupported")
        if len(expression) > _MAX_EXPRESSION:
            raise _fail("DWARF_EXPRESSION_TOO_LONG", "DWARF expression exceeds its limit")
        match = _IDENTIFIER.match(expression)
        if match is None or match.start() != 0:
            raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "DWARF expression is unsupported")
        name = match.group(0)
        symbols = self._symbols.get(name, ())
        if not symbols:
            raise _fail("DWARF_SYMBOL_NOT_FOUND", "DWARF symbol was not found")
        if len(symbols) != 1:
            raise _fail("DWARF_SYMBOL_AMBIGUOUS", "DWARF symbol is ambiguous")
        symbol = symbols[0]
        if symbol.type_error is not None or symbol.dwarf_type is None:
            raise _fail(
                symbol.type_error or "DWARF_TYPE_UNAVAILABLE",
                "DWARF variable type is unavailable",
            )
        if symbol.location_error is not None or symbol.address is None:
            raise _fail(
                symbol.location_error or "DWARF_LOCATION_UNAVAILABLE",
                "DWARF variable location is unavailable",
            )
        dwarf_type = symbol.dwarf_type
        address = symbol.address
        cursor = match.end()
        while cursor < len(expression):
            if expression[cursor] == ".":
                member_match = _IDENTIFIER.match(expression, cursor + 1)
                if member_match is None:
                    raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "DWARF expression is unsupported")
                if dwarf_type.kind not in ("structure", "union"):
                    raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "Member access requires a structure")
                member = dwarf_type.member(member_match.group(0))
                if member.bit_size is not None:
                    raise _fail("DWARF_BITFIELD_UNSUPPORTED", "DWARF bitfields are unsupported")
                address += member.offset
                dwarf_type = member.type
                cursor = member_match.end()
                continue
            if expression[cursor] == "[":
                close = expression.find("]", cursor + 1)
                if close < 0:
                    raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "DWARF expression is unsupported")
                index_text = expression[cursor + 1 : close]
                if not index_text.isascii() or not index_text.isdigit():
                    raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "Array index must be a constant")
                if dwarf_type.kind != "array" or dwarf_type.element_type is None:
                    raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "Array indexing requires an array")
                index = int(index_text)
                if dwarf_type.element_count is None or index >= dwarf_type.element_count:
                    raise _fail("DWARF_ARRAY_INDEX_OUT_OF_RANGE", "Array index is out of range")
                address += index * dwarf_type.element_type.byte_size
                dwarf_type = dwarf_type.element_type
                cursor = close + 1
                continue
            raise _fail("DWARF_EXPRESSION_UNSUPPORTED", "DWARF expression is unsupported")
        end = address + dwarf_type.byte_size
        if end > _MAX_ADDRESS + 1 or not any(
            address >= start and end <= limit for start, limit in self._readable_regions
        ):
            raise _fail(
                "DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY",
                "DWARF location is outside readable project memory",
            )
        return DwarfSelection(expression, address, dwarf_type, self._little_endian)
