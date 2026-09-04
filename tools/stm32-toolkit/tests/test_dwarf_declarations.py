from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from elftools.elf.elffile import ELFFile

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import atomic_write_json, compute_build_id, validate_elf
from stm32_toolkit.debug.dwarf import DwarfCatalog, _integer_attribute
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.debug.read import VariableReadRequest, read_variables
from stm32_toolkit.debug.sampling import SampleVariablesRequest, sample_variables
from stm32_toolkit.debug.types import DwarfError
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION

from dwarf_declaration_fixture import (
    DECLARATION_ADDRESS,
    VARIABLE_ADDRESS,
    build_declaration_elf,
)
from stm32_toolkit.project_model import load_project_model
from test_debug_read import DebugEnv, debug_env


def _write_elf(tmp_path: Path, **options: object) -> Path:
    path = tmp_path / "declarations.elf"
    path.write_bytes(build_declaration_elf(**options))
    return path


def _error_code(code: str, operation, *args: object) -> None:
    with pytest.raises(DwarfError) as raised:
        operation(*args)
    assert raised.value.code == code


def test_concrete_specification_definition_resolves_literal_unsigned_variable(
    tmp_path: Path,
) -> None:
    elf_path = _write_elf(tmp_path)
    catalog = DwarfCatalog.from_elf(
        elf_path, readable_regions=((0x20000000, 0x20030000),)
    )

    selected = catalog.lookup("testtime")

    assert selected.address == 0x20000134
    assert selected.byte_size == 4
    assert selected.type.signed is False
    assert selected.decode(bytes([37, 0, 0, 0])).value == 37


def test_direct_definition_without_specification_remains_readable(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(
            tmp_path,
            direct_definition=True,
            definition_name="direct_testtime",
            definition_type="base",
        ),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("direct_testtime")

    assert selected.address == VARIABLE_ADDRESS
    assert selected.type.name == "unsigned int"
    assert selected.type.aliases == ()


def test_declaration_only_symbols_are_not_readable(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(tmp_path, declaration_only=True),
        readable_regions=((0x20000000, 0x20030000),),
    )

    _error_code("DWARF_SYMBOL_NOT_FOUND", catalog.lookup, "testtime")


@pytest.mark.parametrize("equal_address", [False, True])
def test_true_duplicate_concrete_definitions_remain_ambiguous(
    tmp_path: Path, equal_address: bool
) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(
            tmp_path,
            definition_count=2,
            equal_definition_addresses=equal_address,
        ),
        readable_regions=((0x20000000, 0x20030000),),
    )

    _error_code("DWARF_SYMBOL_AMBIGUOUS", catalog.lookup, "testtime")


def test_direct_name_and_type_override_referenced_declaration(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(
            tmp_path,
            definition_name="overridden_testtime",
            definition_type="base",
        ),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("overridden_testtime")

    assert selected.address == VARIABLE_ADDRESS
    assert selected.type.name == "unsigned int"
    assert selected.type.aliases == ()
    _error_code("DWARF_SYMBOL_NOT_FOUND", catalog.lookup, "testtime")


def test_direct_name_precedes_inherited_name_but_inherits_type(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(tmp_path, definition_name="overridden_testtime"),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("overridden_testtime")

    assert selected.type.aliases == ("word_alias",)
    _error_code("DWARF_SYMBOL_NOT_FOUND", catalog.lookup, "testtime")


def test_direct_type_precedes_inherited_type_but_inherits_name(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(tmp_path, definition_type="base"),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("testtime")

    assert selected.type.name == "unsigned int"
    assert selected.type.aliases == ()


def test_missing_type_inherits_alias_from_same_cu_declaration(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(tmp_path),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("testtime")

    assert selected.type.name == "unsigned int"
    assert selected.type.aliases == ("word_alias",)


def test_concrete_location_is_not_inherited_from_declaration(tmp_path: Path) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(
            tmp_path,
            definition_location=None,
            declaration_location=DECLARATION_ADDRESS,
        ),
        readable_regions=((0x20000000, 0x20030000),),
    )

    _error_code("DWARF_LOCATION_UNAVAILABLE", catalog.lookup, "testtime")


@pytest.mark.parametrize("flag_form", ["flag", "present"])
def test_flag_present_and_integer_one_declarations_are_both_skipped(
    tmp_path: Path, flag_form: str
) -> None:
    catalog = DwarfCatalog.from_elf(
        _write_elf(tmp_path, declaration_flag_form=flag_form),
        readable_regions=((0x20000000, 0x20030000),),
    )

    selected = catalog.lookup("testtime")

    assert selected.address == VARIABLE_ADDRESS


@pytest.mark.parametrize(
    ("value", "expected"), [(True, None), (False, None), (1, 1), (0, 0)]
)
def test_integer_attribute_rejects_boolean_values_but_keeps_integers(
    value: object, expected: int | None
) -> None:
    die = SimpleNamespace(
        attributes={"DW_AT_declaration": SimpleNamespace(value=value)}
    )

    assert _integer_attribute(die, "DW_AT_declaration") == expected


@pytest.mark.parametrize("kind", ["form", "offset", "target", "self", "chain"])
def test_malformed_specification_references_fail_closed(
    tmp_path: Path, kind: str
) -> None:
    path = _write_elf(tmp_path, malformed_reference=kind)

    with pytest.raises(DwarfError) as raised:
        DwarfCatalog.from_elf(
            path, readable_regions=((0x20000000, 0x20030000),)
        )
    assert raised.value.code == "DWARF_ELF_MALFORMED"


class _MemoryClient:
    def __init__(self, binding: DebugFirmwareBinding, memory: bytes) -> None:
        self.calls: list[tuple[int, int]] = []
        self.attach_count = 0
        self._binding = binding
        self._memory = memory
        self.endpoint = SimpleNamespace(
            protocol=PROBE_PROTOCOL_VERSION,
            toolkit_version=__version__,
            host="127.0.0.1",
            port=23456,
            token="d" * 64,
            workspace_id=binding.workspace_id,
            session_id=binding.observation_session_id,
            lease_id=binding.lease_id,
            probe_id=binding.probe_id,
            operation_level=OperationLevel.OBSERVE,
        )

    async def attach(self, probe_id: str, target: str) -> object:
        self.attach_count += 1
        return SimpleNamespace(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number="STM32F429ZI",
            core_count=1,
        )

    async def read_memory(self, address: int, length: int) -> bytes:
        self.calls.append((address, length))
        if (address, length) != (VARIABLE_ADDRESS, 4):
            raise AssertionError("unexpected memory request")
        return self._memory


class _Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        assert delay >= 0
        self.now += delay


def _rewrite_debug_environment(env: DebugEnv, elf_data: bytes) -> DebugEnv:
    elf_path = env.root / env.binding.elf_path
    elf_path.write_bytes(elf_data)
    model = load_project_model(env.root)
    evidence = validate_elf(elf_path, model)
    identity_path = env.root / "build" / "arm-debug" / "firmware-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity.update(
        {
            "elfSha256": evidence.sha256,
            "elfSize": evidence.size,
            "entryPoint": evidence.entry_point,
            "vectorAddress": evidence.vector_address,
            "resetHandlerAddress": evidence.reset_handler_address,
        }
    )
    identity["buildId"] = compute_build_id(identity)
    atomic_write_json(identity_path, identity)

    build_result_path = env.root / "artifacts" / "migration" / "build-result.json"
    build_result = json.loads(build_result_path.read_text(encoding="utf-8"))
    build_result["buildId"] = identity["buildId"]
    for artifact in build_result.get("artifacts", []):
        if artifact.get("kind") == "elf":
            artifact["sha256"] = evidence.sha256
            artifact["size"] = evidence.size
    atomic_write_json(build_result_path, build_result)

    with elf_path.open("rb") as stream:
        verified_bytes = sum(
            int(segment["p_filesz"])
            for segment in ELFFile(stream).iter_segments()
            if segment["p_type"] == "PT_LOAD" and int(segment["p_filesz"]) > 0
        )
    flash_path = env.root / "artifacts" / "migration" / "flash-result.json"
    flash = json.loads(flash_path.read_text(encoding="utf-8"))
    flash.update(
        {
            "buildId": identity["buildId"],
            "elfSha256": evidence.sha256,
            "elfSize": evidence.size,
            "verifiedBytes": verified_bytes,
        }
    )
    atomic_write_json(flash_path, flash)

    binding = replace(
        env.binding,
        build_id=str(identity["buildId"]),
        elf_sha256=evidence.sha256,
        elf_size=evidence.size,
    )
    catalog = DwarfCatalog.from_binding(binding)
    return replace(env, binding=binding, catalog=catalog)


@pytest.fixture
def declaration_debug_env(debug_env: DebugEnv) -> DebugEnv:
    return _rewrite_debug_environment(
        debug_env,
        build_declaration_elf(),
    )


def test_catalog_listing_exposes_only_the_concrete_definition(
    declaration_debug_env: DebugEnv,
) -> None:
    page = declaration_debug_env.catalog.variable_descriptors(
        declaration_debug_env.binding
    )

    assert [item.selector for item in page.items] == ["testtime"]


def test_catalog_listing_excludes_declaration_only_symbols(
    debug_env: DebugEnv,
) -> None:
    env = _rewrite_debug_environment(
        debug_env,
        build_declaration_elf(declaration_only=True),
    )

    assert env.catalog.variable_descriptors(env.binding).items == ()


def test_catalog_listing_excludes_ambiguous_definitions(
    debug_env: DebugEnv,
) -> None:
    env = _rewrite_debug_environment(
        debug_env,
        build_declaration_elf(definition_count=2),
    )

    assert env.catalog.variable_descriptors(env.binding).items == ()


def test_read_variables_decodes_definition_with_exact_memory_request(
    declaration_debug_env: DebugEnv,
) -> None:
    client = _MemoryClient(declaration_debug_env.binding, bytes((37, 0, 0, 0)))
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                declaration_debug_env.binding,
                declaration_debug_env.catalog,
                ("testtime",),
            ),
            client,
        )
    )

    assert result.ok is True
    assert result.data.items[0].status == "ok"
    assert result.data.items[0].value.value == 37
    assert client.calls == [(0x20000134, 4)]


def test_sample_variables_decodes_definition_with_exact_memory_requests(
    declaration_debug_env: DebugEnv,
) -> None:
    clock = _Clock()
    client = _MemoryClient(declaration_debug_env.binding, bytes((37, 0, 0, 0)))
    result = asyncio.run(
        sample_variables(
            SampleVariablesRequest(
                declaration_debug_env.binding,
                declaration_debug_env.catalog,
                ("testtime",),
                100,
                count=2,
            ),
            client,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )

    assert result.ok is True
    assert len(result.data.samples) == 2
    assert [
        sample["items"][0]["value"]["value"]
        for sample in result.data.to_dict()["samples"]
    ] == [37, 37]
    assert client.calls == [(0x20000134, 4), (0x20000134, 4)]
