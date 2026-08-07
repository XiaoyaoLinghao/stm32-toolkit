from __future__ import annotations

import math
import io
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from elftools.dwarf.locationlists import LocationExpr
from elftools.elf.elffile import ELFFile

from stm32_toolkit.debug.dwarf import (
    DwarfCatalog,
    _TypeGraph,
    _integer_attribute,
    _name,
)
from stm32_toolkit.debug.types import DwarfError, DwarfSelection, DwarfType


FIXTURE = Path(__file__).parent / "fixtures" / "dwarf" / "typed.elf"
READABLE = ((0x08000000, 0x08100000), (0x20000000, 0x20100000))


@pytest.fixture(scope="module")
def catalog() -> DwarfCatalog:
    return DwarfCatalog.from_elf(FIXTURE, readable_regions=READABLE)


def _assert_error(code: str, operation, *args) -> None:
    with pytest.raises(DwarfError) as raised:
        operation(*args)
    assert raised.value.code == code
    assert str(FIXTURE.resolve()) not in str(raised.value)


def _fixture_bytes(address: int, size: int) -> bytes:
    with FIXTURE.open("rb") as stream:
        elf = ELFFile(stream)
        for segment in elf.iter_segments():
            start = int(segment["p_vaddr"])
            file_size = int(segment["p_filesz"])
            if start <= address and address + size <= start + file_size:
                stream.seek(int(segment["p_offset"]) + address - start)
                return stream.read(size)
    raise AssertionError("selected fixture address has no file-backed bytes")


@pytest.mark.parametrize(
    ("expression", "raw", "expected", "bits"),
    [
        ("signed8", struct.pack("<b", -7), -7, 8),
        ("unsigned8", struct.pack("<B", 250), 250, 8),
        ("signed16", struct.pack("<h", -1234), -1234, 16),
        ("unsigned16", struct.pack("<H", 54321), 54321, 16),
        ("signed32", struct.pack("<i", -1234567), -1234567, 32),
        ("unsigned32", struct.pack("<I", 3456789012), 3456789012, 32),
        ("signed64", struct.pack("<q", -1234567890123), "-1234567890123", 64),
        (
            "unsigned64",
            struct.pack("<Q", 12345678901234567890),
            "12345678901234567890",
            64,
        ),
    ],
)
def test_integer_types_come_from_dwarf(
    catalog: DwarfCatalog, expression: str, raw: bytes, expected: object, bits: int
) -> None:
    selected = catalog.lookup(expression)
    decoded = selected.decode(raw)

    assert selected.type.kind == "integer"
    assert selected.byte_size == bits // 8
    assert decoded.value == expected
    assert decoded.bit_width == bits
    assert decoded.raw_hex == "0x" + raw[::-1].hex()


def test_bool_and_ieee_float_types(catalog: DwarfCatalog) -> None:
    assert catalog.lookup("enabled").decode(b"\x01").value is True
    assert catalog.lookup("ratio32").decode(struct.pack("<f", 1.25)).value == 1.25
    assert catalog.lookup("ratio64").decode(struct.pack("<d", -3.5)).value == -3.5


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("signed8", -7),
        ("unsigned8", 250),
        ("signed16", -1234),
        ("unsigned16", 54321),
        ("signed32", -1234567),
        ("unsigned32", 3456789012),
        ("signed64", "-1234567890123"),
        ("unsigned64", "12345678901234567890"),
        ("enabled", True),
        ("ratio32", 1.25),
        ("ratio64", -3.5),
        ("mode_known", 7),
        ("mode_unknown", 99),
        ("qualified", -42),
        ("values[2]", 33),
        ("packet.point.x", -12),
        ("packet.samples[1]", 202),
    ],
)
def test_real_elf_bytes_decode_through_real_dwarf_locations_and_types(
    catalog: DwarfCatalog, expression: str, expected: object
) -> None:
    selected = catalog.lookup(expression)
    raw = _fixture_bytes(selected.address, selected.byte_size)
    assert selected.decode(raw).value == expected


@pytest.mark.parametrize(("raw", "symbol"), [(7, "MODE_RUN"), (99, None)])
def test_enum_known_and_unknown_values(
    catalog: DwarfCatalog, raw: int, symbol: str | None
) -> None:
    expression = "mode_known" if symbol else "mode_unknown"
    value = catalog.lookup(expression).decode(bytes([raw]))
    assert value.value == raw
    assert value.enum_name == symbol


def test_typedef_and_qualifiers_preserve_real_underlying_type(
    catalog: DwarfCatalog,
) -> None:
    selected = catalog.lookup("qualified")
    assert selected.type.kind == "integer"
    assert selected.type.signed is True
    assert selected.type.qualifiers == ("const", "volatile")
    assert "qualified_word_t" in selected.type.aliases


def test_constant_array_index_and_nested_structure_member(
    catalog: DwarfCatalog,
) -> None:
    values = catalog.lookup("values[2]")
    point = catalog.lookup("packet.point.y")
    sample = catalog.lookup("packet.samples[1]")

    assert values.address == catalog.lookup("values").address + 8
    assert values.decode(struct.pack("<i", 33)).value == 33
    assert point.address == catalog.lookup("packet").address + 4
    assert point.decode(struct.pack("<H", 34)).value == 34
    assert sample.address == catalog.lookup("packet").address + 12


def test_pointer_is_an_address_and_is_never_implicitly_dereferenced(
    catalog: DwarfCatalog,
) -> None:
    pointer = catalog.lookup("value_pointer")
    decoded = pointer.decode(struct.pack("<I", 0x20000024))
    assert pointer.type.kind == "pointer"
    assert decoded.value == "0x20000024"
    _assert_error("DWARF_EXPRESSION_UNSUPPORTED", catalog.lookup, "*value_pointer")


@pytest.mark.parametrize(
    "expression",
    [
        "values[-1]",
        "values[index]",
        "values[1 + 1]",
        "packet.point.x + 1",
        "signed32()",
        "(int)signed32",
        "value_pointer->x",
        "packet..tag",
    ],
)
def test_expression_language_rejects_everything_except_members_and_constants(
    catalog: DwarfCatalog, expression: str
) -> None:
    _assert_error("DWARF_EXPRESSION_UNSUPPORTED", catalog.lookup, expression)


def test_out_of_range_array_and_unknown_member_are_explicit(
    catalog: DwarfCatalog,
) -> None:
    _assert_error("DWARF_ARRAY_INDEX_OUT_OF_RANGE", catalog.lookup, "values[3]")
    _assert_error("DWARF_MEMBER_NOT_FOUND", catalog.lookup, "packet.missing")


def test_bitfield_and_aggregate_decode_are_explicitly_unsupported(
    catalog: DwarfCatalog,
) -> None:
    _assert_error("DWARF_BITFIELD_UNSUPPORTED", catalog.lookup, "packed_bits.active")
    _assert_error("DWARF_TYPE_UNSUPPORTED", catalog.lookup("packet").decode, bytes(20))


def test_decode_requires_exact_bytes_and_maps_non_finite_floats(
    catalog: DwarfCatalog,
) -> None:
    _assert_error("DWARF_DECODE_SIZE_MISMATCH", catalog.lookup("signed32").decode, b"\0")
    positive_inf = catalog.lookup("ratio32").decode(struct.pack("<f", math.inf))
    not_a_number = catalog.lookup("ratio64").decode(struct.pack("<d", math.nan))
    assert positive_inf.value == "positiveInfinity"
    assert not_a_number.value == "nan"


def test_duplicate_local_names_are_ambiguous(catalog: DwarfCatalog) -> None:
    _assert_error("DWARF_SYMBOL_AMBIGUOUS", catalog.lookup, "ambiguous")


def test_register_optimized_or_frame_locations_never_become_guessed_addresses(
    catalog: DwarfCatalog,
) -> None:
    _assert_error("DWARF_LOCATION_REGISTER_ONLY", catalog.lookup, "register_local")
    _assert_error("DWARF_LOCATION_OPTIMIZED_OUT", catalog.lookup, "optimized_out")


def test_unsupported_symbol_type_is_item_scoped(catalog: DwarfCatalog) -> None:
    assert catalog.lookup("signed32").type.kind == "integer"
    _assert_error("DWARF_TYPE_UNSUPPORTED", catalog.lookup, "unsupported_complex")


def test_address_must_be_inside_explicit_readable_regions() -> None:
    limited = DwarfCatalog.from_elf(
        FIXTURE, readable_regions=((0x08000000, 0x08100000),)
    )
    _assert_error("DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY", limited.lookup, "signed32")


def test_malformed_no_dwarf_and_input_limits_fail_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.elf"
    malformed.write_bytes(b"not an elf")
    no_dwarf = tmp_path / "no-dwarf.elf"
    no_dwarf_bytes = bytearray(FIXTURE.read_bytes())
    struct.pack_into("<I", no_dwarf_bytes, 32, 0)  # e_shoff
    struct.pack_into("<H", no_dwarf_bytes, 48, 0)  # e_shnum
    struct.pack_into("<H", no_dwarf_bytes, 50, 0)  # e_shstrndx
    no_dwarf.write_bytes(no_dwarf_bytes)

    _assert_error("DWARF_ELF_MALFORMED", DwarfCatalog.from_elf, malformed)
    _assert_error("DWARF_INFO_UNAVAILABLE", DwarfCatalog.from_elf, no_dwarf)
    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(FIXTURE, max_elf_bytes=100)
    assert raised.value.code == "DWARF_ELF_TOO_LARGE"
    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(FIXTURE, max_dies=2, readable_regions=READABLE)
    assert raised.value.code == "DWARF_DIE_LIMIT_EXCEEDED"


def test_compressed_and_oversized_debug_sections_fail_before_decode(tmp_path: Path) -> None:
    data = bytearray(FIXTURE.read_bytes())
    elf = ELFFile(io.BytesIO(data))
    debug_info_index = next(
        index for index, section in enumerate(elf.iter_sections()) if section.name == ".debug_info"
    )
    section_offset = int(elf.header["e_shoff"]) + debug_info_index * int(
        elf.header["e_shentsize"]
    )
    flags = struct.unpack_from("<I", data, section_offset + 8)[0]
    struct.pack_into("<I", data, section_offset + 8, flags | 0x800)
    compressed = tmp_path / "compressed.elf"
    compressed.write_bytes(data)

    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(compressed, readable_regions=READABLE)
    assert raised.value.code == "DWARF_COMPRESSED_UNSUPPORTED"
    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(
            FIXTURE, readable_regions=READABLE, max_debug_bytes=100
        )
    assert raised.value.code == "DWARF_DEBUG_INFO_TOO_LARGE"


def test_catalog_and_expression_limits_are_bounded(catalog: DwarfCatalog) -> None:
    _assert_error("DWARF_EXPRESSION_TOO_LONG", catalog.lookup, "a" * 257)
    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(
            FIXTURE, max_catalog_entries=2, readable_regions=READABLE
        )
    assert raised.value.code == "DWARF_CATALOG_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"max_dies": 0}, "DWARF_LIMIT_INVALID"),
        ({"max_type_depth": True}, "DWARF_LIMIT_INVALID"),
        ({"max_die_depth": 1, "readable_regions": READABLE}, "DWARF_DIE_DEPTH_EXCEEDED"),
        ({"readable_regions": ((True, 4),)}, "DWARF_READABLE_REGION_INVALID"),
        ({"readable_regions": ((4, 4),)}, "DWARF_READABLE_REGION_INVALID"),
        ({"readable_regions": (1,)}, "DWARF_READABLE_REGION_INVALID"),
    ],
)
def test_parser_limits_and_regions_reject_invalid_values(
    kwargs: dict[str, object], code: str
) -> None:
    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(FIXTURE, **kwargs)
    assert raised.value.code == code


def test_project_readable_regions_are_mandatory() -> None:
    _assert_error("DWARF_READABLE_REGION_REQUIRED", DwarfCatalog.from_elf, FIXTURE)


def test_unavailable_elf_and_non_string_expression_fail_closed(tmp_path: Path) -> None:
    _assert_error("DWARF_ELF_UNAVAILABLE", DwarfCatalog.from_elf, tmp_path / "missing")
    catalog = DwarfCatalog.from_elf(FIXTURE, readable_regions=READABLE)
    _assert_error("DWARF_EXPRESSION_UNSUPPORTED", catalog.lookup, 123)
    _assert_error("DWARF_SYMBOL_NOT_FOUND", catalog.lookup, "does_not_exist")


def test_catalog_is_immutable_and_uses_real_location_and_type(catalog: DwarfCatalog) -> None:
    selected = catalog.lookup("signed32")
    assert selected.address == 0x2000005C
    assert selected.byte_size == 4
    with pytest.raises((AttributeError, TypeError)):
        selected.address = 0  # type: ignore[misc]


class _Die:
    _next_offset = 10000

    def __init__(
        self,
        tag: str,
        *,
        attributes: dict[str, object] | None = None,
        target: "_Die | None" = None,
        children: tuple["_Die", ...] = (),
        offset: object = ...,  # stable identity unless explicitly overridden
        raises: bool = False,
    ) -> None:
        self.tag = tag
        self.attributes = {
            key: SimpleNamespace(value=value) for key, value in (attributes or {}).items()
        }
        if offset is ...:
            _Die._next_offset += 1
            self.offset = _Die._next_offset
        else:
            self.offset = offset
        self.target = target
        self.children = children
        self.raises = raises

    def get_DIE_from_attribute(self, name: str) -> "_Die | None":
        if self.raises:
            raise ValueError("malformed reference")
        return self.target

    def iter_children(self):
        return iter(self.children)


def _graph(**kwargs: int) -> _TypeGraph:
    return _TypeGraph(
        max_depth=kwargs.get("max_depth", 8),
        max_type_bytes=kwargs.get("max_type_bytes", 64),
        max_elements=kwargs.get("max_elements", 16),
    )


def _base(encoding: int = 5, size: int = 4) -> _Die:
    return _Die(
        "DW_TAG_base_type",
        attributes={"DW_AT_name": b"base", "DW_AT_byte_size": size, "DW_AT_encoding": encoding},
    )


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        (lambda: _graph().resolve_attribute(_Die("x", raises=True)), "DWARF_TYPE_INCOMPLETE"),
        (lambda: _graph().resolve_attribute(_Die("x")), "DWARF_TYPE_INCOMPLETE"),
        (lambda: _graph(max_depth=1).resolve(_base(), 2), "DWARF_TYPE_DEPTH_EXCEEDED"),
        (lambda: _graph().resolve(_Die("x", offset="bad"), 0), "DWARF_TYPE_UNSUPPORTED"),
        (lambda: _graph().resolve(_Die("DW_TAG_subroutine_type"), 0), "DWARF_TYPE_UNSUPPORTED"),
        (lambda: _graph().resolve(_base(size=0), 0), "DWARF_TYPE_SIZE_INVALID"),
        (lambda: _graph().resolve(_base(encoding=3), 0), "DWARF_TYPE_UNSUPPORTED"),
    ],
)
def test_malformed_type_graph_nodes_fail_closed(operation, code: str) -> None:
    with pytest.raises(DwarfError) as raised:
        operation()
    assert raised.value.code == code


def test_type_graph_cache_names_and_non_integer_attributes() -> None:
    graph = _graph()
    die = _base()
    assert graph.resolve(die, 0) is graph.resolve(die, 0)
    assert _name(_Die("x"), "fallback") == "fallback"
    assert _name(_Die("x", attributes={"DW_AT_name": 123}), "fallback") == "123"
    assert _integer_attribute(_Die("x", attributes={"value": True}), "value") is None
    assert _integer_attribute(_Die("x", attributes={"value": "1"}), "value") is None


def test_recursive_type_graph_is_rejected() -> None:
    recursive = _Die("DW_TAG_typedef", attributes={"DW_AT_name": b"loop"})
    recursive.target = recursive
    with pytest.raises(DwarfError) as raised:
        _graph().resolve(recursive, 0)
    assert raised.value.code == "DWARF_TYPE_RECURSIVE"


def test_enum_without_encoding_uses_explicit_underlying_dwarf_type() -> None:
    underlying = _base(encoding=5, size=4)
    enumerator = _Die(
        "DW_TAG_enumerator",
        attributes={"DW_AT_name": b"NEG", "DW_AT_const_value": -1},
    )
    ignored = _Die("DW_TAG_variable")
    enum = _Die(
        "DW_TAG_enumeration_type",
        attributes={"DW_AT_name": b"Fallback", "DW_AT_byte_size": 4},
        target=underlying,
        children=(ignored, enumerator),
    )
    resolved = _graph().resolve(enum, 0)
    assert resolved.signed is True
    assert resolved.enum_values == ((-1, "NEG"),)


@pytest.mark.parametrize(
    ("array", "code"),
    [
        (_Die("DW_TAG_array_type", target=_base()), "DWARF_TYPE_UNSUPPORTED"),
        (
            _Die(
                "DW_TAG_array_type",
                target=_base(),
                children=(_Die("DW_TAG_subrange_type", attributes={"DW_AT_lower_bound": 1}),),
            ),
            "DWARF_TYPE_UNSUPPORTED",
        ),
        (
            _Die("DW_TAG_array_type", target=_base(), children=(_Die("DW_TAG_subrange_type"),)),
            "DWARF_TYPE_INCOMPLETE",
        ),
        (
            _Die(
                "DW_TAG_array_type",
                target=_base(),
                children=(_Die("DW_TAG_subrange_type", attributes={"DW_AT_count": 17}),),
            ),
            "DWARF_ARRAY_LIMIT_EXCEEDED",
        ),
        (
            _Die(
                "DW_TAG_array_type",
                attributes={"DW_AT_byte_size": 99},
                target=_base(),
                children=(_Die("DW_TAG_subrange_type", attributes={"DW_AT_count": 2}),),
            ),
            "DWARF_TYPE_SIZE_INVALID",
        ),
    ],
)
def test_array_metadata_is_bounded(array: _Die, code: str) -> None:
    with pytest.raises(DwarfError) as raised:
        _graph().resolve(array, 0)
    assert raised.value.code == code


def test_decode_scalar_error_branches_are_stable() -> None:
    boolean = DwarfSelection("bad_bool", 0, DwarfType("boolean", "bool", 1))
    unsupported_float = DwarfSelection("float16", 0, DwarfType("float", "float16", 2))
    with pytest.raises(DwarfError) as raised:
        boolean.decode(b"\x02")
    assert raised.value.code == "DWARF_BOOLEAN_INVALID"
    with pytest.raises(DwarfError) as raised:
        unsupported_float.decode(b"\0\0")
    assert raised.value.code == "DWARF_TYPE_UNSUPPORTED"
    negative_inf = DwarfSelection("f", 0, DwarfType("float", "float", 4)).decode(
        struct.pack("<f", -math.inf)
    )
    assert negative_inf.value == "negativeInfinity"


def test_location_parser_failures_never_become_addresses() -> None:
    class _Parser:
        def __init__(self, result: object):
            self.result = result

        def parse_from_attribute(self, *args):
            return self.result

    class _ExpressionParser:
        def __init__(self, names: tuple[str, ...]):
            self.names = names

        def parse_expr(self, expression):
            return [SimpleNamespace(op_name=name, args=[]) for name in self.names]

    die = SimpleNamespace(attributes={"DW_AT_location": SimpleNamespace(value=b"")})
    cu = {"version": 5}
    assert DwarfCatalog._location(die, cu, _Parser([]), _ExpressionParser(()))[1] == (
        "DWARF_LOCATION_OPTIMIZED_OUT"
    )
    for names, code in [
        (("DW_OP_fbreg",), "DWARF_LOCATION_UNAVAILABLE"),
        (("DW_OP_implicit_value",), "DWARF_LOCATION_OPTIMIZED_OUT"),
        (("DW_OP_piece",), "DWARF_LOCATION_UNSUPPORTED"),
    ]:
        assert DwarfCatalog._location(
            die,
            cu,
            _Parser(LocationExpr([1])),
            _ExpressionParser(names),
        )[1] == code
