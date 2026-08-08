"""Immutable DWARF types, locations, decoded values, and stable failures."""

from __future__ import annotations

import math
import struct
import unicodedata
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


class DwarfError(Exception):
    """A bounded, stable DWARF catalog or decode failure."""

    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = MappingProxyType(dict(details or {}))


@dataclass(frozen=True)
class DwarfLimits:
    """Effective parser limits after caller values are clamped to hard caps."""

    max_elf_bytes: int
    max_debug_bytes: int
    max_dies: int
    max_die_depth: int
    max_catalog_entries: int
    max_type_depth: int
    max_type_bytes: int
    max_array_elements: int
    max_location_expression_bytes: int
    max_location_operations: int

    def to_dict(self) -> dict[str, int]:
        return {
            "maxElfBytes": self.max_elf_bytes,
            "maxDebugBytes": self.max_debug_bytes,
            "maxDies": self.max_dies,
            "maxDieDepth": self.max_die_depth,
            "maxCatalogEntries": self.max_catalog_entries,
            "maxTypeDepth": self.max_type_depth,
            "maxTypeBytes": self.max_type_bytes,
            "maxArrayElements": self.max_array_elements,
            "maxLocationExpressionBytes": self.max_location_expression_bytes,
            "maxLocationOperations": self.max_location_operations,
        }


@dataclass(frozen=True)
class DwarfMember:
    name: str
    offset: int
    type: "DwarfType"
    bit_size: int | None = None


@dataclass(frozen=True)
class DwarfType:
    """A bounded type graph created only from DWARF DIE attributes."""

    kind: str
    name: str
    byte_size: int
    signed: bool | None = None
    encoding: str | None = None
    qualifiers: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    enum_values: tuple[tuple[int, str], ...] = ()
    element_type: "DwarfType | None" = None
    element_count: int | None = None
    members: tuple[DwarfMember, ...] = ()
    pointee_type: "DwarfType | None" = field(default=None, repr=False)

    def member(self, name: str) -> DwarfMember:
        matches = tuple(item for item in self.members if item.name == name)
        if len(matches) != 1:
            raise DwarfError("DWARF_MEMBER_NOT_FOUND", "Structure member was not found")
        return matches[0]


@dataclass(frozen=True)
class DwarfValue:
    """A JSON-safe decoded scalar value with lossless raw evidence."""

    kind: str
    type_name: str
    value: object
    raw_hex: str
    bit_width: int
    enum_name: str | None = None


def _descriptor_text(value: object, label: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or len(normalized) > maximum
        or "/" in normalized
        or "\\" in normalized
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError(f"{label} is invalid")
    return normalized


@dataclass(frozen=True)
class VariableDescriptor:
    """Display-only DWARF metadata for one symbolic variable selector."""

    selector: str
    type_name: str
    kind: str
    byte_size: int
    signed: bool | None = None
    encoding: str | None = None
    qualifiers: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    enum_values: tuple[tuple[int, str], ...] = ()
    element_count: int | None = None
    element_kind: str | None = None
    member_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "selector", _descriptor_text(self.selector, "selector"))
        object.__setattr__(self, "type_name", _descriptor_text(self.type_name, "type name"))
        object.__setattr__(self, "kind", _descriptor_text(self.kind, "type kind", 64))
        if type(self.byte_size) is not int or not 1 <= self.byte_size <= 1024 * 1024:
            raise ValueError("byte size is invalid")
        if self.signed is not None and type(self.signed) is not bool:
            raise ValueError("signed metadata is invalid")
        if self.encoding is not None:
            object.__setattr__(self, "encoding", _descriptor_text(self.encoding, "encoding", 64))
        qualifiers = tuple(
            _descriptor_text(value, "qualifier", 64) for value in self.qualifiers
        )
        aliases = tuple(_descriptor_text(value, "alias", 128) for value in self.aliases)
        try:
            enum_values = tuple(
                (value, _descriptor_text(name, "enumerator", 128))
                for value, name in self.enum_values
            )
        except (TypeError, ValueError):
            raise ValueError("enum metadata is invalid") from None
        if any(type(value) is not int for value, _ in enum_values):
            raise ValueError("enum metadata is invalid")
        if self.element_count is not None and (
            type(self.element_count) is not int or self.element_count < 1
        ):
            raise ValueError("array metadata is invalid")
        if self.element_kind is not None:
            object.__setattr__(
                self, "element_kind", _descriptor_text(self.element_kind, "element kind", 64)
            )
        member_names = tuple(
            _descriptor_text(value, "member name", 128) for value in self.member_names
        )
        object.__setattr__(self, "qualifiers", qualifiers)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "enum_values", enum_values)
        object.__setattr__(self, "member_names", member_names)

    def to_dict(self) -> dict[str, object]:
        return {
            "selector": self.selector,
            "typeName": self.type_name,
            "kind": self.kind,
            "byteSize": self.byte_size,
            "signed": self.signed,
            "encoding": self.encoding,
            "qualifiers": list(self.qualifiers),
            "aliases": list(self.aliases),
            "enumValues": [
                {"value": value, "name": name} for value, name in self.enum_values
            ],
            "elementCount": self.element_count,
            "elementKind": self.element_kind,
            "memberNames": list(self.member_names),
        }


@dataclass(frozen=True)
class RegisterDescriptor:
    """Display/read-risk metadata for one symbolic register selector."""

    selector: str
    size_bits: int
    access: str | None
    read_action: str | None
    reset_value: int | None
    reset_mask: int | None
    fields: tuple[tuple[str, int, int], ...]
    sampleable: bool
    requires_access_acknowledgement: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "selector", _descriptor_text(self.selector, "selector"))
        if type(self.size_bits) is not int or not 1 <= self.size_bits <= 64:
            raise ValueError("register size is invalid")
        for name in ("access", "read_action"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _descriptor_text(value, name, 64))
        for name in ("reset_value", "reset_mask"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("register reset metadata is invalid")
        try:
            fields = tuple(
                (_descriptor_text(name, "field name", 128), offset, width)
                for name, offset, width in self.fields
            )
        except (TypeError, ValueError):
            raise ValueError("register field metadata is invalid") from None
        if any(
            type(offset) is not int
            or type(width) is not int
            or offset < 0
            or width < 1
            or offset + width > self.size_bits
            for _, offset, width in fields
        ):
            raise ValueError("register field metadata is invalid")
        if type(self.sampleable) is not bool or type(self.requires_access_acknowledgement) is not bool:
            raise ValueError("register read-risk metadata is invalid")
        object.__setattr__(self, "fields", fields)

    def to_dict(self) -> dict[str, object]:
        return {
            "selector": self.selector,
            "sizeBits": self.size_bits,
            "access": self.access,
            "readAction": self.read_action,
            "resetValue": self.reset_value,
            "resetMask": self.reset_mask,
            "fields": [
                {"name": name, "bitOffset": offset, "bitWidth": width}
                for name, offset, width in self.fields
            ],
            "sampleable": self.sampleable,
            "requiresAccessAcknowledgement": self.requires_access_acknowledgement,
        }


@dataclass(frozen=True)
class CatalogPage:
    """One immutable bounded page of display-only catalog descriptors."""

    items: tuple[VariableDescriptor | RegisterDescriptor, ...]
    next_cursor: str | None

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if len(items) > 256:
            raise ValueError("catalog page exceeds its item limit")
        if not all(
            type(item) in (VariableDescriptor, RegisterDescriptor) for item in items
        ):
            raise TypeError("catalog page items must be an immutable descriptor tuple")
        if self.next_cursor is not None and (
            not isinstance(self.next_cursor, str) or not 1 <= len(self.next_cursor) <= 512
        ):
            raise TypeError("catalog cursor is invalid")
        object.__setattr__(self, "items", items)

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "nextCursor": self.next_cursor,
        }


@dataclass(frozen=True)
class DwarfSelection:
    """A catalog expression resolved to an exact address and DWARF type."""

    expression: str
    address: int
    type: DwarfType
    little_endian: bool = field(default=True, repr=False)

    @property
    def byte_size(self) -> int:
        return self.type.byte_size

    def decode(self, data: bytes) -> DwarfValue:
        if not isinstance(data, bytes) or len(data) != self.byte_size:
            raise DwarfError(
                "DWARF_DECODE_SIZE_MISMATCH",
                "Typed value bytes do not match the DWARF type size",
            )
        byte_order = "little" if self.little_endian else "big"
        raw_hex = "0x" + (data[::-1] if self.little_endian else data).hex()
        bits = self.byte_size * 8
        dwarf_type = self.type

        if dwarf_type.kind == "integer":
            value = int.from_bytes(data, byte_order, signed=bool(dwarf_type.signed))
            safe_value: object = str(value) if bits > 53 else value
            return DwarfValue("integer", dwarf_type.name, safe_value, raw_hex, bits)
        if dwarf_type.kind == "boolean":
            value = int.from_bytes(data, byte_order, signed=False)
            if value not in (0, 1):
                raise DwarfError("DWARF_BOOLEAN_INVALID", "DWARF boolean is not 0 or 1")
            return DwarfValue("boolean", dwarf_type.name, bool(value), raw_hex, bits)
        if dwarf_type.kind == "float":
            if self.byte_size not in (4, 8):
                raise DwarfError(
                    "DWARF_TYPE_UNSUPPORTED", "Floating-point width is unsupported"
                )
            prefix = "<" if self.little_endian else ">"
            value = struct.unpack(prefix + ("f" if self.byte_size == 4 else "d"), data)[0]
            if math.isnan(value):
                safe_float: object = "nan"
            elif value == math.inf:
                safe_float = "positiveInfinity"
            elif value == -math.inf:
                safe_float = "negativeInfinity"
            else:
                safe_float = value
            return DwarfValue("float", dwarf_type.name, safe_float, raw_hex, bits)
        if dwarf_type.kind == "enum":
            value = int.from_bytes(data, byte_order, signed=bool(dwarf_type.signed))
            enum_name = dict(dwarf_type.enum_values).get(value)
            safe_enum: object = str(value) if bits > 53 else value
            return DwarfValue(
                "enum", dwarf_type.name, safe_enum, raw_hex, bits, enum_name=enum_name
            )
        if dwarf_type.kind == "pointer":
            value = int.from_bytes(data, byte_order, signed=False)
            address = f"0x{value:0{self.byte_size * 2}x}"
            return DwarfValue("pointer", dwarf_type.name, address, raw_hex, bits)
        raise DwarfError(
            "DWARF_TYPE_UNSUPPORTED", "Aggregate type decoding is unsupported"
        )
