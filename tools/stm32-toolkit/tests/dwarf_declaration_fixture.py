"""Small test-only ELF/DWARF fixtures for declaration/definition coverage."""

from __future__ import annotations

import struct
from dataclasses import dataclass


VARIABLE_ADDRESS = 0x20000134
ALTERNATE_VARIABLE_ADDRESS = 0x20000144
DECLARATION_ADDRESS = 0x20000190


_DW_TAG_COMPILE_UNIT = 0x11
_DW_TAG_BASE_TYPE = 0x24
_DW_TAG_TYPEDEF = 0x16
_DW_TAG_VARIABLE = 0x34

_DW_AT_NAME = 0x03
_DW_AT_BYTE_SIZE = 0x0B
_DW_AT_ENCODING = 0x3E
_DW_AT_TYPE = 0x49
_DW_AT_DECLARATION = 0x3C
_DW_AT_LOCATION = 0x02
_DW_AT_SPECIFICATION = 0x47

_DW_FORM_STRING = 0x08
_DW_FORM_DATA1 = 0x0B
_DW_FORM_FLAG = 0x0C
_DW_FORM_REF1 = 0x11
_DW_FORM_REF2 = 0x12
_DW_FORM_REF4 = 0x13
_DW_FORM_REF8 = 0x14
_DW_FORM_REF_ADDR = 0x10
_DW_FORM_EXPRLOC = 0x18
_DW_FORM_FLAG_PRESENT = 0x19
_DW_FORM_REF_UDATA = 0x16


def _uleb(value: int) -> bytes:
    if value < 0:
        raise ValueError("ULEB128 value must be non-negative")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


@dataclass(frozen=True)
class _Attribute:
    name: int
    form: int
    value: object


@dataclass
class _Die:
    tag: int
    attributes: tuple[_Attribute, ...]
    children: tuple["_Die", ...] = ()
    offset: int | None = None


class _Abbreviations:
    def __init__(self) -> None:
        self._entries: dict[tuple[int, bool, tuple[tuple[int, int], ...]], int] = {}
        self._ordered: list[tuple[int, bool, tuple[tuple[int, int], ...]]] = []

    def code_for(self, die: _Die) -> int:
        key = (
            die.tag,
            bool(die.children),
            tuple((attribute.name, attribute.form) for attribute in die.attributes),
        )
        code = self._entries.get(key)
        if code is None:
            code = len(self._ordered) + 1
            self._entries[key] = code
            self._ordered.append(key)
        return code

    def encode(self) -> bytes:
        output = bytearray()
        for code, (tag, children, attributes) in enumerate(self._ordered, 1):
            output += _uleb(code)
            output += _uleb(tag)
            output.append(1 if children else 0)
            for name, form in attributes:
                output += _uleb(name)
                output += _uleb(form)
            output += b"\x00\x00"
        output.append(0)
        return bytes(output)


class _Cu:
    def __init__(self, start: int, abbreviations: _Abbreviations, name: str) -> None:
        self.start = start
        self.abbreviations = abbreviations
        self.name = name
        self.body = bytearray()
        self.dies: list[_Die] = []
        self._current_die: _Die | None = None

    def add(self, die: _Die) -> _Die:
        die.offset = self.start + 11 + len(self.body)
        self.body += _uleb(self.abbreviations.code_for(die))
        self._current_die = die
        try:
            for attribute in die.attributes:
                self.body += self._attribute_bytes(attribute)
        finally:
            self._current_die = None
        self.dies.append(die)
        for child in die.children:
            self.add(child)
        if die.children:
            self.body.append(0)
        return die

    def _attribute_bytes(self, attribute: _Attribute) -> bytes:
        value = attribute.value
        if attribute.form == _DW_FORM_STRING:
            return str(value).encode("utf-8") + b"\x00"
        if attribute.form == _DW_FORM_DATA1:
            return struct.pack("<B", int(value))
        if attribute.form == _DW_FORM_FLAG:
            return struct.pack("<B", int(bool(value)))
        if attribute.form == _DW_FORM_FLAG_PRESENT:
            return b""
        if attribute.form in {
            _DW_FORM_REF1,
            _DW_FORM_REF2,
            _DW_FORM_REF4,
            _DW_FORM_REF8,
            _DW_FORM_REF_UDATA,
            _DW_FORM_REF_ADDR,
        }:
            if isinstance(value, _Die):
                if value.offset is None:
                    raise AssertionError("reference target was not assigned an offset")
                raw = value.offset - self.start
            elif value == "self":
                if self._current_die is None or self._current_die.offset is None:
                    raise AssertionError("self reference has no current DIE")
                raw = self._current_die.offset - self.start
            else:
                raw = int(value)
            if attribute.form == _DW_FORM_REF1:
                return struct.pack("<B", raw)
            if attribute.form == _DW_FORM_REF2:
                return struct.pack("<H", raw)
            if attribute.form in {_DW_FORM_REF4, _DW_FORM_REF_ADDR}:
                return struct.pack("<I", raw)
            if attribute.form == _DW_FORM_REF8:
                return struct.pack("<Q", raw)
            return _uleb(raw)
        if attribute.form == _DW_FORM_EXPRLOC:
            expression = bytes(value)
            return _uleb(len(expression)) + expression
        raise AssertionError(f"unsupported test form {attribute.form:#x}")

    def encode(self) -> bytes:
        length = 7 + len(self.body)
        header = struct.pack("<I H I B", length, 4, 0, 4)
        return header + bytes(self.body)


def _name(value: str) -> _Attribute:
    return _Attribute(_DW_AT_NAME, _DW_FORM_STRING, value)


def _type(target: _Die) -> _Attribute:
    return _Attribute(_DW_AT_TYPE, _DW_FORM_REF4, target)


def _location(address: int) -> _Attribute:
    return _Attribute(
        _DW_AT_LOCATION,
        _DW_FORM_EXPRLOC,
        b"\x03" + struct.pack("<I", address),
    )


def _specification(target: object, form: int = _DW_FORM_REF4) -> _Attribute:
    return _Attribute(_DW_AT_SPECIFICATION, form, target)


def build_declaration_elf(
    *,
    declaration_only: bool = False,
    definition_count: int = 1,
    direct_definition: bool = False,
    equal_definition_addresses: bool = False,
    definition_name: str | None = None,
    definition_type: str | None = None,
    definition_location: int | None = VARIABLE_ADDRESS,
    declaration_location: int | None = None,
    declaration_flag_form: str = "flag",
    malformed_reference: str | None = None,
) -> bytes:
    """Build a valid ELF32/ARM image with bounded DWARF declaration shapes."""

    if definition_count < 0:
        raise ValueError("definition count must be non-negative")
    if declaration_only:
        definition_count = 0
    if declaration_flag_form not in {"flag", "present"}:
        raise ValueError("unsupported declaration flag form")
    if malformed_reference not in {
        None,
        "form",
        "offset",
        "target",
        "self",
        "chain",
        "cross-cu",
    }:
        raise ValueError("unsupported malformed reference kind")

    abbreviations = _Abbreviations()
    cu1 = _Cu(0, abbreviations, "declaration-only.c")
    cu1_root = _Die(
        _DW_TAG_COMPILE_UNIT,
        (_name(cu1.name),),
        children=(),
    )
    # CU 1 deliberately carries a DW_FORM_flag_present declaration. It is
    # declaration-only and must never consume a catalog entry.
    cu1_decl = _Die(
        _DW_TAG_VARIABLE,
        (
            _name("testtime"),
            _Attribute(_DW_AT_DECLARATION, _DW_FORM_FLAG_PRESENT, True),
        ),
    )
    cu1_root.children = (cu1_decl,)
    cu1.add(cu1_root)
    cu1_bytes = cu1.encode()

    cu2 = _Cu(len(cu1_bytes), abbreviations, "definition.c")
    base = _Die(
        _DW_TAG_BASE_TYPE,
        (
            _name("unsigned int"),
            _Attribute(_DW_AT_BYTE_SIZE, _DW_FORM_DATA1, 4),
            _Attribute(_DW_AT_ENCODING, _DW_FORM_DATA1, 7),
        ),
    )
    alias = _Die(
        _DW_TAG_TYPEDEF,
        (_name("word_alias"), _type(base)),
    )
    flag_form = (
        _DW_FORM_FLAG_PRESENT if declaration_flag_form == "present" else _DW_FORM_FLAG
    )
    declaration_attributes: list[_Attribute] = [
        _name("testtime"),
        _type(alias),
        _Attribute(_DW_AT_DECLARATION, flag_form, True),
    ]
    if declaration_location is not None:
        declaration_attributes.append(_location(declaration_location))
    if malformed_reference == "chain":
        declaration_attributes.append(_specification("self"))
    declaration = _Die(_DW_TAG_VARIABLE, tuple(declaration_attributes))

    concrete: list[_Die] = []
    for index in range(definition_count):
        location = (
            None
            if definition_location is None
            else definition_location
            if equal_definition_addresses
            else definition_location + index * 0x10
        )
        attributes: list[_Attribute] = []
        if definition_name is not None:
            attributes.append(_name(definition_name))
        if definition_type == "base":
            attributes.append(_type(base))
        elif definition_type == "alias":
            attributes.append(_type(alias))
        if location is not None:
            attributes.append(_location(location))
        target: object = declaration
        specification_form = _DW_FORM_REF4
        if malformed_reference == "form":
            specification_form = _DW_FORM_REF_ADDR
            target = declaration.offset or 0
        elif malformed_reference == "offset":
            target = 0xFFFF_FFFF
        elif malformed_reference == "target":
            target = base
        elif malformed_reference == "self":
            # The builder assigns this DIE's offset just before encoding its
            # attributes, so this sentinel is resolved below after insertion.
            target = "self"
        elif malformed_reference == "chain":
            target = declaration
        elif malformed_reference == "cross-cu":
            target = cu1_decl
        if not direct_definition:
            attributes.append(_specification(target, specification_form))
        concrete.append(_Die(_DW_TAG_VARIABLE, tuple(attributes)))

    # Roots use children to retain a valid tree while the parser still visits
    # each variable in CU order. Add all nodes once so reference offsets exist.
    cu2_root = _Die(_DW_TAG_COMPILE_UNIT, (_name(cu2.name),))
    cu2_root.children = (base, alias, declaration, *concrete)
    cu2.add(cu2_root)

    cu2_bytes = cu2.encode()
    info = cu1_bytes + cu2_bytes
    abbrev = abbreviations.encode()
    return _build_elf(info, abbrev)


def _build_elf(debug_info: bytes, debug_abbrev: bytes) -> bytes:
    sections: list[dict[str, object]] = []

    def add(
        name: str,
        sh_type: int,
        flags: int,
        address: int,
        data: bytes,
        *,
        link: int = 0,
        info: int = 0,
        align: int = 1,
        entsize: int = 0,
    ) -> int:
        sections.append(
            {
                "name": name,
                "type": sh_type,
                "flags": flags,
                "address": address,
                "data": data,
                "link": link,
                "info": info,
                "align": align,
                "entsize": entsize,
            }
        )
        return len(sections)

    vector_index = add(
        ".isr_vector",
        1,
        0x2,
        0x08000000,
        struct.pack("<II", 0x20020000, 0x08000041) + b"\x00" * 56,
        align=4,
    )
    text_index = add(
        ".text",
        1,
        0x6,
        0x08000040,
        b"\x00\xbf" * 32,
        align=4,
    )
    add(".data", 1, 0x3, VARIABLE_ADDRESS, bytes((37, 0, 0, 0)), align=4)
    add(".debug_info", 1, 0, 0, debug_info, align=1)
    add(".debug_abbrev", 1, 0, 0, debug_abbrev, align=1)

    names = ["", "Reset_Handler", "main", "testtime"]
    strtab = b"\x00" + b"".join(name.encode("ascii") + b"\x00" for name in names[1:])
    string_offsets = {name: strtab.index(name.encode("ascii")) for name in names[1:]}
    strtab_index = add(".strtab", 3, 0, 0, strtab, align=1)
    symbols = b"".join(
        (
            struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0),
            struct.pack("<IIIBBH", string_offsets["Reset_Handler"], 0x08000041, 4, 0x12, 0, text_index),
            struct.pack("<IIIBBH", string_offsets["main"], 0x08000050, 4, 0x12, 0, text_index),
            struct.pack("<IIIBBH", string_offsets["testtime"], VARIABLE_ADDRESS, 4, 0x11, 0, 3),
        )
    )
    add(
        ".symtab",
        2,
        0,
        0,
        symbols,
        link=strtab_index,
        info=1,
        align=4,
        entsize=16,
    )

    shstr_names = [section["name"] for section in sections]
    shstr_data = b"\x00" + b"\x00".join(name.encode("ascii") for name in shstr_names) + b"\x00"
    shstr_index = add(".shstrtab", 3, 0, 0, shstr_data, align=1)

    offset = 52 + 32
    for section in sections:
        align = int(section["align"])
        offset = (offset + align - 1) // align * align
        section["offset"] = offset
        offset += len(section["data"])
    shoff = (offset + 3) // 4 * 4
    output = bytearray(b"\x00" * (52 + 32))
    for section in sections:
        section_offset = int(section["offset"])
        if len(output) < section_offset:
            output.extend(b"\x00" * (section_offset - len(output)))
        output.extend(section["data"])
    if len(output) < shoff:
        output.extend(b"\x00" * (shoff - len(output)))

    output.extend(b"\x00" * 40)
    for section in sections:
        name = str(section["name"])
        name_offset = shstr_data.find(b"\x00" + name.encode("ascii") + b"\x00") + 1
        output.extend(
            struct.pack(
                "<IIIIIIIIII",
                name_offset,
                int(section["type"]),
                int(section["flags"]),
                int(section["address"]),
                int(section["offset"]),
                len(section["data"]),
                int(section["link"]),
                int(section["info"]),
                int(section["align"]),
                int(section["entsize"]),
            )
        )

    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + b"\x00" * 8
    header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident,
        2,
        40,
        1,
        0x08000041,
        52,
        shoff,
        0,
        52,
        32,
        1,
        40,
        len(sections) + 1,
        shstr_index,
    )
    output[:52] = header
    output[52:84] = struct.pack(
        "<IIIIIIII",
        1,
        0,
        0x08000000,
        0x08000000,
        shoff,
        shoff,
        5,
        4,
    )
    return bytes(output)


__all__ = [
    "ALTERNATE_VARIABLE_ADDRESS",
    "DECLARATION_ADDRESS",
    "VARIABLE_ADDRESS",
    "build_declaration_elf",
]
