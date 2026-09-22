from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import replace
from pathlib import Path

import pytest
from elftools.elf.elffile import ELFFile
from stm32_toolkit.debug.dwarf import DwarfCatalog
from stm32_toolkit.debug.model import MemoryRegionBinding
from stm32_toolkit.debug.svd import SvdError, select_svd
from stm32_toolkit.debug.types import DwarfError
from test_dwarf import (
    FIXTURE as ELF_FIXTURE,
)
from test_dwarf import (
    READABLE as DWARF_READABLE,
)
from test_dwarf import (
    _firmware_binding,
    _fixture_bytes,
)
from test_svd import (
    _document,
    _named_document,
    _number_document,
)
from test_svd import (
    select_svd as select_fixture_svd,
)


def _assert_dwarf_error(operation, code: str, message: str) -> None:
    with pytest.raises(DwarfError) as raised:
        operation()
    assert raised.value.code == code
    assert raised.value.message == message


def _assert_svd_error(operation, code: str, message: str) -> None:
    with pytest.raises(SvdError) as raised:
        operation()
    assert raised.value.code == code
    assert raised.value.message == message


def _dwarf_project(tmp_path: Path) -> tuple[Path, object, DwarfCatalog, bytes]:
    project = tmp_path / "dwarf-project"
    firmware = project / "build" / "firmware.elf"
    firmware.parent.mkdir(parents=True)
    original = ELF_FIXTURE.read_bytes()
    firmware.write_bytes(original)
    binding = _firmware_binding(project_root=project, elf_path="build/firmware.elf")
    catalog = DwarfCatalog.from_binding(binding, project)
    return project, binding, catalog, original


def test_public_dwarf_artifact_refusals_preserve_catalog_and_binding(
    tmp_path: Path,
) -> None:
    project, binding, catalog, original = _dwarf_project(tmp_path)
    firmware = project / "build" / "firmware.elf"

    blocked_parent = project / "blocked"
    blocked_parent.write_bytes(b"ordinary file")
    directory_file = project / "directory.elf"
    directory_file.mkdir()
    no_readable_regions = replace(
        binding,
        memory_regions=(MemoryRegionBinding("FLASH", 0x08000000, 0x1000, "x"),),
    )

    refusals = (
        (
            lambda: DwarfCatalog.from_elf(
                Path("build/../firmware.elf"),
                project_root=project,
                readable_regions=DWARF_READABLE,
            ),
            "DWARF_PATH_INVALID",
            "ELF path is invalid",
        ),
        (
            lambda: DwarfCatalog.from_elf(
                Path("blocked/firmware.elf"),
                project_root=project,
                readable_regions=DWARF_READABLE,
            ),
            "DWARF_ELF_UNAVAILABLE",
            "ELF bytes are unavailable",
        ),
        (
            lambda: DwarfCatalog.from_elf(
                Path("directory.elf"),
                project_root=project,
                readable_regions=DWARF_READABLE,
            ),
            "DWARF_ELF_UNAVAILABLE",
            "ELF bytes are unavailable",
        ),
        (
            lambda: DwarfCatalog.from_binding(
                binding, project_root=project / "other-root"
            ),
            "DWARF_PROVENANCE_MISMATCH",
            "Firmware binding provenance is invalid",
        ),
        (
            lambda: DwarfCatalog.from_binding(no_readable_regions, project),
            "DWARF_PROVENANCE_MISMATCH",
            "Firmware binding has no readable memory regions",
        ),
    )

    for operation, code, message in refusals:
        _assert_dwarf_error(operation, code, message)
        assert firmware.read_bytes() == original
        assert catalog.revalidate(binding, project) is True
        assert catalog.lookup("signed32").byte_size == 4

    assert binding.elf_sha256 == hashlib.sha256(original).hexdigest()
    assert (
        catalog.lookup("values[2]")
        .decode(_fixture_bytes(catalog.lookup("values[2]").address, 4))
        .value
        == 33
    )


def test_public_dwarf_lookup_refusals_recover_to_valid_lookup(tmp_path: Path) -> None:
    project, binding, catalog, original = _dwarf_project(tmp_path)

    refusals = (
        (
            lambda: catalog.lookup("values["),
            "DWARF_EXPRESSION_UNSUPPORTED",
            "DWARF expression is unsupported",
        ),
        (
            lambda: catalog.lookup("signed32[0]"),
            "DWARF_EXPRESSION_UNSUPPORTED",
            "Array indexing requires an array",
        ),
    )
    for operation, code, message in refusals:
        _assert_dwarf_error(operation, code, message)
        assert catalog.revalidate(binding, project) is True
        selected = catalog.lookup("values[2]")
        assert (
            selected.decode(_fixture_bytes(selected.address, selected.byte_size)).value
            == 33
        )

    assert (project / "build" / "firmware.elf").read_bytes() == original


def _valid_svd_with_cluster_copy() -> bytes:
    return (
        b"<device><name>STM32F429ZITx</name><size>32</size><peripherals>"
        b"<peripheral><name>GPIOA</name><baseAddress>0x40020000</baseAddress>"
        b"<registers>"
        b'<cluster derivedFrom="GROUP_BASE"><name>GROUP_COPY</name>'
        b"<addressOffset>0x40</addressOffset></cluster>"
        b"<cluster><name>GROUP_BASE</name><addressOffset>0x20</addressOffset>"
        b"<size>8</size><register><name>VALUE</name>"
        b"<addressOffset>0</addressOffset></register></cluster>"
        b"</registers></peripheral></peripherals></device>"
    )


def _selection_snapshot(selection) -> tuple[object, ...]:
    register = selection.register("GPIOA.GROUP_COPY.VALUE")
    return (
        selection.device,
        selection.path,
        selection.sha256,
        selection.file_size,
        register.path,
        register.address,
        register.size_bytes,
        register.access,
    )


def test_public_svd_artifact_refusals_restore_original_selection_and_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "svd-project"
    project.mkdir()
    path = project / "device.svd"
    original = _valid_svd_with_cluster_copy()
    path.write_bytes(original)
    selection = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    original_snapshot = _selection_snapshot(selection)
    original_sha256 = hashlib.sha256(original).hexdigest()

    inherited_fields = _document(
        "<registers><register><name>BASE</name><addressOffset>0</addressOffset>"
        "<size>64</size><fields><field><name>WIDE</name><bitOffset>32</bitOffset>"
        "<bitWidth>32</bitWidth></field></fields></register>"
        '<register derivedFrom="BASE"><name>COPY</name><addressOffset>4</addressOffset>'
        "<size>16</size></register></registers>"
    )
    duplicate_nested_cluster = _document(
        "<registers><cluster><name>TOP</name><addressOffset>0</addressOffset>"
        "<size>8</size><cluster><name>DUP</name><addressOffset>0</addressOffset>"
        "<register><name>VALUE</name><addressOffset>0</addressOffset></register></cluster>"
        "<cluster><name>DUP</name><addressOffset>4</addressOffset></cluster>"
        "</cluster></registers>"
    )
    missing_cluster_scope = _document(
        "<registers><cluster><name>TOP</name><addressOffset>0</addressOffset>"
        '<size>8</size><cluster derivedFrom="MISSING"><name>COPY</name>'
        "<addressOffset>0</addressOffset></cluster></cluster></registers>"
    )
    duplicate_register_path = _document(
        "<registers><register><name>VALUE%s</name><addressOffset>0</addressOffset>"
        "<dim>1</dim><dimIncrement>4</dimIncrement><dimIndex>0</dimIndex>"
        "<size>32</size></register><register><name>VALUE0</name>"
        "<addressOffset>4</addressOffset><size>32</size></register></registers>"
    )
    refusals = (
        (
            b"plain text without XML delimiters",
            "SVD_XML_INVALID",
            "SVD XML encoding is invalid",
        ),
        (
            _number_document("0x100000000"),
            "SVD_XML_INVALID",
            "SVD numeric metadata is out of range",
        ),
        (
            inherited_fields,
            "SVD_XML_INVALID",
            "SVD inherited field metadata is invalid",
        ),
        (
            duplicate_nested_cluster,
            "SVD_XML_INVALID",
            "SVD cluster declaration is ambiguous",
        ),
        (
            missing_cluster_scope,
            "SVD_XML_INVALID",
            "SVD derived cluster scope is invalid",
        ),
        (
            duplicate_register_path,
            "SVD_XML_INVALID",
            "SVD register path is duplicated",
        ),
        (
            _named_document("BAD NAME"),
            "SVD_XML_INVALID",
            "SVD device name is invalid",
        ),
    )

    for payload, code, message in refusals:
        path.write_bytes(payload)
        _assert_svd_error(
            lambda: select_svd(
                project,
                "STM32F429ZITx",
                (Path("device.svd"),),
                readable_regions=(
                    MemoryRegionBinding("PERIPHERAL", 0x40000000, 0x01000000, "rw-"),
                ),
            ),
            code,
            message,
        )
        assert path.read_bytes() == payload
        path.write_bytes(original)
        restored = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
        assert _selection_snapshot(restored) == original_snapshot
        assert restored.sha256 == original_sha256
        assert path.read_bytes() == original


def _selection_identity_snapshot(selection) -> tuple[object, ...]:
    return (
        selection.device,
        selection.target_device,
        selection.path,
        selection.sha256,
        selection.file_size,
        selection.registers,
        selection.readable_regions,
    )


def _forward_svd_with_local_cluster_cache() -> bytes:
    return (
        b"<device><name>STM32F429ZITx</name><size>32</size><peripherals>"
        b'<peripheral derivedFrom="BASE"><name>COPY</name>'
        b"<baseAddress>0x40021000</baseAddress></peripheral>"
        b"<peripheral><name>BASE</name><baseAddress>0x40020000</baseAddress>"
        b"<size>16</size><access>read-only</access><registers>"
        b'<cluster derivedFrom="GROUP_BASE"><name>GROUP_COPY</name>'
        b"<addressOffset>0x40</addressOffset></cluster>"
        b"<cluster><name>GROUP_BASE</name><addressOffset>0x20</addressOffset>"
        b"<size>8</size><resetValue>1</resetValue><resetMask>0xff</resetMask>"
        b"<register><name>VALUE</name><addressOffset>0</addressOffset></register>"
        b"</cluster></registers></peripheral></peripherals></device>"
    )


def _nested_svd_with_local_cluster_cache() -> bytes:
    return _document(
        "<registers><cluster><name>TOP%s</name><addressOffset>0x100</addressOffset>"
        "<dim>2</dim><dimIncrement>0x1000</dimIncrement><size>16</size>"
        "<access>read-only</access>"
        '<cluster derivedFrom="INNER_BASE"><name>INNER%s</name>'
        "<addressOffset>0x40</addressOffset><dim>2</dim>"
        "<dimIncrement>0x20</dimIncrement></cluster>"
        "<cluster><name>INNER_BASE</name><addressOffset>0x10</addressOffset>"
        "<size>8</size><register><name>VALUE%s</name>"
        "<addressOffset>0</addressOffset><dim>2</dim>"
        "<dimIncrement>1</dimIncrement></register></cluster></cluster></registers>"
    )


def _cluster_cycle_svd() -> bytes:
    return _document(
        '<registers><cluster derivedFrom="B"><name>A</name>'
        "<addressOffset>0</addressOffset></cluster>"
        '<cluster derivedFrom="A"><name>B</name>'
        "<addressOffset>4</addressOffset></cluster></registers>"
    )


def _deep_cluster_chain_svd() -> bytes:
    declarations = [
        f'<cluster derivedFrom="C{index + 1}"><name>C{index}</name>'
        f"<addressOffset>{index * 4}</addressOffset></cluster>"
        for index in range(1099)
    ]
    declarations.append(
        "<cluster><name>C1099</name><addressOffset>0</addressOffset>"
        "<register><name>VALUE</name><addressOffset>0</addressOffset></register>"
        "</cluster>"
    )
    return _document(f"<registers>{''.join(declarations)}</registers>")


def _missing_cluster_scope_svd() -> bytes:
    return _document(
        "<registers><cluster><name>TOP</name><addressOffset>0</addressOffset>"
        '<size>8</size><cluster derivedFrom="MISSING"><name>COPY</name>'
        "<addressOffset>0</addressOffset></cluster></cluster></registers>"
    )


def test_public_svd_derived_metadata_refusals_restore_selection_and_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "svd-derived-project"
    project.mkdir()
    path = project / "device.svd"

    path.write_bytes(_forward_svd_with_local_cluster_cache())
    forward = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert forward.register("BASE.GROUP_COPY.VALUE").address == 0x40020040
    assert forward.register("COPY.GROUP_BASE.VALUE").address == 0x40021020

    path.write_bytes(_nested_svd_with_local_cluster_cache())
    nested = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert nested.register("GPIOA.TOP1.INNER1.VALUE1").address == 0x40021161

    original = _valid_svd_with_cluster_copy()
    path.write_bytes(original)
    original_selection = select_fixture_svd(
        project, "STM32F429ZITx", (Path("device.svd"),)
    )
    original_snapshot = _selection_identity_snapshot(original_selection)
    original_sha256 = hashlib.sha256(original).hexdigest()

    refusals = (
        (
            _cluster_cycle_svd(),
            "SVD_XML_INVALID",
            "SVD derived cluster cycle is invalid",
        ),
        (
            _deep_cluster_chain_svd(),
            "SVD_SIZE_LIMIT",
            "SVD derived chain exceeds the limit",
        ),
        (
            _missing_cluster_scope_svd(),
            "SVD_XML_INVALID",
            "SVD derived cluster scope is invalid",
        ),
    )
    for payload, code, message in refusals:
        path.write_bytes(payload)
        _assert_svd_error(
            lambda: select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),)),
            code,
            message,
        )
        assert path.read_bytes() == payload

        path.write_bytes(original)
        restored = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
        assert _selection_identity_snapshot(restored) == original_snapshot
        assert restored.sha256 == original_sha256
        assert path.read_bytes() == original


def test_public_svd_empty_readable_regions_reject_before_candidate_read(
    tmp_path: Path,
) -> None:
    project = tmp_path / "svd-regions-project"
    project.mkdir()
    path = project / "device.svd"
    original = _valid_svd_with_cluster_copy()
    path.write_bytes(original)

    _assert_svd_error(
        lambda: select_svd(
            project,
            "STM32F429ZITx",
            (Path("device.svd"),),
            readable_regions=(),
        ),
        "SVD_SELECTION_REQUIRED",
        "Trusted readable memory regions are required",
    )
    assert path.read_bytes() == original

    restored = select_fixture_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert restored.register("GPIOA.GROUP_COPY.VALUE").address == 0x40020040
    assert path.read_bytes() == original


def _mutated_elf_section_header_offset(data: bytes) -> bytes:
    mutated = bytearray(data)
    struct.pack_into("<I", mutated, 32, len(mutated) - 1)
    struct.pack_into("<H", mutated, 48, 1)
    return bytes(mutated)


def _mutated_elf_compressed_section_name(data: bytes) -> bytes:
    marker = b".debug_info"
    replacement = b".zdebugXXXX"
    assert len(marker) == len(replacement)
    assert data.count(marker) == 1
    offset = data.index(marker)
    mutated = bytearray(data)
    mutated[offset : offset + len(marker)] = replacement
    return bytes(mutated)


def _mutated_elf_invalid_variable_name(data: bytes) -> bytes:
    old_name = b"signed32"
    new_name = b"bad-name"
    assert len(old_name) == len(new_name)
    elf = ELFFile(io.BytesIO(data))
    debug_str = elf.get_section_by_name(".debug_str")
    assert debug_str is not None
    offset = None
    dwarf = elf.get_dwarf_info()
    for cu in dwarf.iter_CUs():
        for die in cu.iter_DIEs():
            attribute = die.attributes.get("DW_AT_name")
            value = None if attribute is None else attribute.value
            if die.tag == "DW_TAG_variable" and value == old_name:
                assert isinstance(attribute.raw_value, int)
                offset = int(debug_str["sh_offset"]) + attribute.raw_value
                break
        if offset is not None:
            break
    assert offset is not None
    assert data[offset : offset + len(old_name)] == old_name
    mutated = bytearray(data)
    mutated[offset : offset + len(old_name)] = new_name
    return bytes(mutated)


def test_public_dwarf_metadata_refusals_and_item_isolation_restore_bytes(
    tmp_path: Path,
) -> None:
    project, binding, catalog, original = _dwarf_project(tmp_path)
    firmware = project / "build" / "firmware.elf"

    refusals = (
        (
            _mutated_elf_section_header_offset(original),
            "DWARF_ELF_MALFORMED",
            "ELF section headers are malformed",
        ),
        (
            _mutated_elf_compressed_section_name(original),
            "DWARF_COMPRESSED_UNSUPPORTED",
            "Compressed ELF sections are unsupported",
        ),
    )
    for payload, code, message in refusals:
        firmware.write_bytes(payload)
        _assert_dwarf_error(
            lambda: DwarfCatalog.from_elf(
                Path("build/firmware.elf"),
                project_root=project,
                readable_regions=DWARF_READABLE,
            ),
            code,
            message,
        )
        assert firmware.read_bytes() == payload

        firmware.write_bytes(original)
        assert catalog.revalidate(binding, project) is True
        restored = DwarfCatalog.from_elf(
            Path("build/firmware.elf"),
            project_root=project,
            readable_regions=DWARF_READABLE,
        )
        assert restored.lookup("signed32").byte_size == 4
        assert firmware.read_bytes() == original

    firmware.write_bytes(_mutated_elf_invalid_variable_name(original))
    isolated = DwarfCatalog.from_elf(
        Path("build/firmware.elf"),
        project_root=project,
        readable_regions=DWARF_READABLE,
    )
    _assert_dwarf_error(
        lambda: isolated.lookup("signed32"),
        "DWARF_SYMBOL_NOT_FOUND",
        "DWARF symbol was not found",
    )
    selected = isolated.lookup("values[2]")
    assert (
        selected.decode(_fixture_bytes(selected.address, selected.byte_size)).value
        == 33
    )
    assert firmware.read_bytes() != original

    firmware.write_bytes(original)
    restored = DwarfCatalog.from_elf(
        Path("build/firmware.elf"),
        project_root=project,
        readable_regions=DWARF_READABLE,
    )
    assert restored.lookup("signed32").byte_size == 4
    assert catalog.revalidate(binding, project) is True
    assert firmware.read_bytes() == original
