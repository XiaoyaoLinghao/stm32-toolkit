from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest
from stm32_toolkit.debug.model import MemoryRegionBinding
from stm32_toolkit.debug.svd import SvdError, select_svd

TARGET_DEVICE = "STM32F429ZITx"
SVD_PATH = Path("device.svd")


@dataclass(frozen=True)
class _RefusalCase:
    name: str
    payload: bytes
    code: str
    message: str


def _device(peripherals: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<device><name>STM32F429ZITx</name><size>32</size>"
        f"<peripherals>{peripherals}</peripherals></device>"
    ).encode()


def _cached_ancestor_payload() -> bytes:
    return _device(
        "<peripheral><name>BASE</name><baseAddress>0x40020000</baseAddress>"
        "<access>read-only</access><registers>"
        "<register><name>VALUE</name><addressOffset>0x20</addressOffset>"
        "<size>16</size><access>read-only</access><resetValue>0x12</resetValue>"
        "<resetMask>0xffff</resetMask></register></registers></peripheral>"
        '<peripheral derivedFrom="BASE"><name>COPY</name></peripheral>'
    )


def _deep_peripheral_payload() -> bytes:
    declarations: list[str] = []
    for index in range(256, -1, -1):
        name = f"P{index:03d}"
        if index == 0:
            declarations.append(
                f"<peripheral><name>{name}</name>"
                "<baseAddress>0x40020000</baseAddress></peripheral>"
            )
        else:
            declarations.append(
                f'<peripheral derivedFrom="P{index - 1:03d}">'
                f"<name>{name}</name></peripheral>"
            )
    return _device("".join(declarations))


def _refusal_cases() -> tuple[_RefusalCase, ...]:
    return (
        _RefusalCase(
            "acyclic-derived-chain-depth",
            _deep_peripheral_payload(),
            "SVD_SIZE_LIMIT",
            "SVD derived chain exceeds the limit",
        ),
        _RefusalCase(
            "undeclared-derived-parent",
            _device(
                '<peripheral derivedFrom="MISSING"><name>CHILD</name>'
                "<baseAddress>0x40020000</baseAddress></peripheral>"
            ),
            "SVD_XML_INVALID",
            "SVD derived peripheral scope is invalid",
        ),
        _RefusalCase(
            "root-peripheral-missing-base",
            _device("<peripheral><name>ROOT</name></peripheral>"),
            "SVD_XML_INVALID",
            "SVD peripheral base address is missing",
        ),
        _RefusalCase(
            "peripheral-array-address-overflow",
            _device(
                "<peripheral><name>ARRAY%s</name>"
                "<baseAddress>0xffffffff</baseAddress><dim>2</dim>"
                "<dimIncrement>1</dimIncrement></peripheral>"
            ),
            "SVD_XML_INVALID",
            "SVD peripheral address overflows",
        ),
    )


REFUSAL_CASES = _refusal_cases()


def _tree_snapshot(root: Path) -> tuple[tuple[str, ...], tuple[tuple[str, bytes], ...]]:
    directories: list[str] = []
    files: list[tuple[str, bytes]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files.append((relative, path.read_bytes()))
        else:
            raise AssertionError(f"unexpected project entry: {path}")
    return tuple(directories), tuple(files)


def _write_document(project: Path, payload: bytes) -> Path:
    project.mkdir(parents=True)
    path = project / SVD_PATH
    path.write_bytes(payload)
    return path


def _select(project: Path):
    return select_svd(
        project,
        TARGET_DEVICE,
        (SVD_PATH,),
        readable_regions=(
            # The public parser requires a trusted region for every parsed register.
            # This range covers the synthetic peripheral addresses used by this test.
            MemoryRegionBinding("PERIPHERAL", 0x40000000, 0x01000000, "rw-"),
        ),
    )


def _assert_restored_selection(project: Path, payload: bytes) -> None:
    selection = _select(project)
    register = selection.register("COPY.VALUE")
    assert selection.sha256 == hashlib.sha256(payload).hexdigest()
    assert (register.address, register.size_bytes, register.access) == (
        0x40020020,
        2,
        "read-only",
    )
    assert (register.reset_value, register.reset_mask) == (0x12, 0xFFFF)


def test_public_peripheral_cached_ancestor_inherits_base_and_metadata(
    tmp_path: Path,
) -> None:
    payload = _cached_ancestor_payload()
    project = tmp_path / "project"
    path = _write_document(project, payload)

    selection = _select(project)
    base = selection.register("BASE.VALUE")
    copy = selection.register("COPY.VALUE")

    assert selection.device == TARGET_DEVICE
    assert selection.path == SVD_PATH.as_posix()
    assert selection.file_size == len(payload)
    assert path.read_bytes() == payload
    assert (base.address, base.size_bytes, base.access) == (
        0x40020020,
        2,
        "read-only",
    )
    assert (copy.address, copy.size_bytes, copy.access) == (
        0x40020020,
        2,
        "read-only",
    )
    assert (copy.reset_value, copy.reset_mask) == (0x12, 0xFFFF)


@pytest.mark.parametrize(
    "case",
    REFUSAL_CASES,
    ids=lambda case: case.name,
)
def test_public_peripheral_refusal_preserves_and_restores_valid_document(
    tmp_path: Path, case: _RefusalCase
) -> None:
    valid_payload = _cached_ancestor_payload()
    project = tmp_path / "project"
    path = _write_document(project, valid_payload)
    valid_snapshot = _tree_snapshot(project)

    path.write_bytes(case.payload)
    refusal_snapshot = _tree_snapshot(project)
    with pytest.raises(SvdError) as raised:
        _select(project)

    assert raised.value.code == case.code
    assert raised.value.message == case.message
    assert str(raised.value) == case.message
    assert _tree_snapshot(project) == refusal_snapshot

    path.write_bytes(valid_payload)
    assert _tree_snapshot(project) == valid_snapshot
    _assert_restored_selection(project, valid_payload)
    assert _tree_snapshot(project) == valid_snapshot
