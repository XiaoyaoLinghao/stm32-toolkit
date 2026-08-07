"""Immutable DWARF types, locations, decoded values, and stable failures."""

from __future__ import annotations

import math
import struct
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
