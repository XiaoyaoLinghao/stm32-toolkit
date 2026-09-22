from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
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
