from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.debug import svd as svd_module
from stm32_toolkit.debug.svd import SvdError, select_svd


FIXTURE = Path(__file__).parent / "fixtures" / "svd" / "STM32F429-exact.svd"


def test_selects_one_exact_device_and_expands_register_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    svd = project / "device.svd"
    project.mkdir()
    svd.write_bytes(FIXTURE.read_bytes())

    selection = select_svd(project, "STM32F429ZITx", (Path("device.svd"),))

    assert selection.device == "STM32F429ZITx"
    assert selection.path == "device.svd"
    assert selection.sha256 == __import__("hashlib").sha256(svd.read_bytes()).hexdigest()
    assert selection.register("GPIOA.IDR").address == 0x40020010
    assert selection.register("GPIOA.IDR").size_bytes == 4
    assert selection.register("GPIOA.IDR").fields[0].mask == 1
    assert selection.register("GPIOA.IDR").fields[1].mask == 2
    assert selection.register("GPIOA.IDR").reset_value == 0
    assert selection.register("GPIOA.IDR").reset_mask == 0xFFFF_FFFF
    assert selection.register("GPIOA.IDR_COPY").access == "read-only"
    assert selection.register("GPIOA.CHANNEL0.VALUE").address == 0x40020100
    assert selection.register("GPIOA.CHANNEL1.VALUE").address == 0x40020120
    with pytest.raises(SvdError) as missing:
        selection.register("GPIOA.MISSING")
    assert missing.value.code == "SVD_REGISTER_NOT_FOUND"


@pytest.mark.parametrize("target", ["STM32F429", "stm32f429zitx", "STM32F429ZIT"])
def test_rejects_family_partial_or_casefold_target(tmp_path: Path, target: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "device.svd").write_bytes(FIXTURE.read_bytes())
    with pytest.raises(SvdError) as error:
        select_svd(project, target, (Path("device.svd"),))
    assert error.value.code == "SVD_SELECTION_REQUIRED"


def test_rejects_zero_or_ambiguous_exact_matches(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.svd").write_bytes(FIXTURE.read_bytes())
    (project / "b.svd").write_bytes(FIXTURE.read_bytes())
    with pytest.raises(SvdError) as missing:
        select_svd(project, "STM32F407VGTx", (Path("a.svd"),))
    assert missing.value.code == "SVD_SELECTION_REQUIRED"
    with pytest.raises(SvdError) as ambiguous:
        select_svd(project, "STM32F429ZITx", (Path("a.svd"), Path("b.svd")))
    assert ambiguous.value.code == "SVD_SELECTION_REQUIRED"
    with pytest.raises(SvdError) as duplicate:
        select_svd(
            project,
            "STM32F429ZITx",
            (Path("a.svd"), Path("a.svd")),
        )
    assert duplicate.value.code == "SVD_SELECTION_REQUIRED"


@pytest.mark.parametrize(
    ("project_root", "target", "candidates"),
    [
        (Path("project"), "bad target", (Path("device.svd"),)),
        (Path("project"), "STM32F429ZITx", ()),
        (Path("project"), "STM32F429ZITx", [Path("device.svd")]),
        (Path("project"), "STM32F429ZITx", tuple(Path(f"{i}.svd") for i in range(33))),
    ],
)
def test_selection_envelope_is_strict(project_root, target, candidates) -> None:
    with pytest.raises(SvdError) as error:
        select_svd(project_root, target, candidates)
    assert error.value.code == "SVD_SELECTION_REQUIRED"


def test_candidate_must_be_path_and_regular_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "device.svd").mkdir()
    with pytest.raises(SvdError) as kind:
        select_svd(project, "STM32F429ZITx", ("device.svd",))
    assert kind.value.code == "SVD_PATH_INVALID"
    with pytest.raises(SvdError) as regular:
        select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert regular.value.code == "SVD_PATH_INVALID"


@pytest.mark.parametrize("candidate", [Path("../outside.svd"), Path("/absolute.svd"), Path("bad:name.svd")])
def test_rejects_nonportable_candidate_before_read(tmp_path: Path, candidate: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(SvdError) as error:
        select_svd(project, "STM32F429ZITx", (candidate,))
    assert error.value.code == "SVD_PATH_INVALID"


@pytest.mark.parametrize(
    "payload",
    [
        b"<!DOCTYPE device><device><name>STM32F429ZITx</name></device>",
        b"<!ENTITY x SYSTEM 'file:///secret'><device><name>&x;</name></device>",
        "<!DoCtYpE device><device><name>STM32F429ZITx</name></device>".encode("utf-16"),
        "<!ENTITY x 'unsafe'><device><name>&x;</name></device>".encode("utf-16-le"),
        "<!DOCTYPE device><device><name>STM32F429ZITx</name></device>".encode("utf-16-be"),
    ],
)
def test_rejects_dtd_entity_before_xml_parse(
    tmp_path: Path, payload: bytes, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "device.svd").write_bytes(payload)
    monkeypatch.setattr(
        svd_module.ET,
        "fromstring",
        lambda value: (_ for _ in ()).throw(
            AssertionError("XML parser must not receive unsafe declarations")
        ),
    )
    with pytest.raises(SvdError) as error:
        select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert error.value.code == "SVD_XML_UNSAFE"


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"])
def test_supported_xml_encodings_parse_exact_device(
    tmp_path: Path, encoding: str
) -> None:
    payload = (
        '<device><name>STM32F429ZITx</name><peripherals><peripheral>'
        '<name>GPIOA</name><baseAddress>0x40020000</baseAddress>'
        '</peripheral></peripherals></device>'
    ).encode(encoding)

    selection = _select_payload(tmp_path, payload)

    assert selection.device == "STM32F429ZITx"
    assert selection.registers == ()


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\x00\xfe\x01",
        b"<not-device/>",
        b"<device><peripherals/></device>",
        b"<device><name>STM32F429ZITx</name></device>",
        b"<device><name>STM32F429ZITx</name><peripherals><peripheral>"
        b"<name>GPIOA</name><baseAddress>-1</baseAddress></peripheral></peripherals></device>",
        b"<device><name>STM32F429ZITx</name>",
    ],
)
def test_invalid_encoding_root_required_metadata_number_and_xml_are_stable(
    tmp_path: Path, payload: bytes
) -> None:
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_XML_INVALID"


def test_access_policy_denies_write_only_and_guards_side_effects(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "device.svd").write_bytes(FIXTURE.read_bytes())
    selection = select_svd(project, "STM32F429ZITx", (Path("device.svd"),))

    assert selection.register("GPIOA.IDR").authorize_read(False, sampling=True) is True
    with pytest.raises(SvdError) as write_only:
        selection.register("GPIOA.COMMAND").authorize_read(True, sampling=False)
    assert write_only.value.code == "SVD_REGISTER_WRITE_ONLY"
    with pytest.raises(SvdError) as side_effect:
        selection.register("GPIOA.EVENT").authorize_read(False, sampling=False)
    assert side_effect.value.code == "SVD_ACCESS_RISK_ACK_REQUIRED"
    assert selection.register("GPIOA.EVENT").authorize_read(True, sampling=False) is True
    with pytest.raises(SvdError) as sampled:
        selection.register("GPIOA.EVENT").authorize_read(True, sampling=True)
    assert sampled.value.code == "SVD_REGISTER_NOT_SAMPLEABLE"

    for invalid_ack in (False, "true", 1, 0, None, [], {}):
        with pytest.raises(SvdError) as strict:
            selection.register("GPIOA.EVENT").authorize_read(
                invalid_ack, sampling=False
            )
        assert strict.value.code == "SVD_ACCESS_RISK_ACK_REQUIRED"


def _document(peripheral_body: str, *, device_access: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<device><name>STM32F429ZITx</name>'
        f'{device_access}<peripherals><peripheral><name>GPIOA</name>'
        '<baseAddress>0x40020000</baseAddress>'
        f'{peripheral_body}</peripheral></peripherals></device>'
    ).encode("utf-8")


def _select_payload(tmp_path: Path, payload: bytes):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / "device.svd").write_bytes(payload)
    return select_svd(project, "STM32F429ZITx", (Path("device.svd"),))


def test_device_access_and_peripheral_reset_metadata_are_inherited(tmp_path: Path) -> None:
    selection = _select_payload(
        tmp_path,
        _document(
            '<resetValue>0x12</resetValue><resetMask>0xff</resetMask>'
            '<registers><register><name>VALUE</name><addressOffset>0</addressOffset>'
            '<size>8</size></register></registers>',
            device_access='<access>read-only</access>',
        ),
    )

    register = selection.register("GPIOA.VALUE")
    assert register.access == "read-only"
    assert register.reset_value == 0x12
    assert register.reset_mask == 0xFF
    assert register.authorize_read(False, sampling=True)


def test_duplicate_fields_and_register_paths_fail_closed(tmp_path: Path) -> None:
    duplicate_fields = _document(
        '<registers><register><name>VALUE</name><addressOffset>0</addressOffset>'
        '<fields><field><name>FLAG</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>'
        '<field><name>FLAG</name><bitOffset>1</bitOffset><bitWidth>1</bitWidth></field>'
        '</fields></register></registers>'
    )
    with pytest.raises(SvdError) as fields:
        _select_payload(tmp_path, duplicate_fields)
    assert fields.value.code == "SVD_XML_INVALID"

    other = tmp_path / "other"
    duplicate_registers = _document(
        '<registers><register><name>VALUE</name><addressOffset>0</addressOffset></register>'
        '<register><name>VALUE</name><addressOffset>4</addressOffset></register></registers>'
    )
    with pytest.raises(SvdError) as registers:
        _select_payload(other, duplicate_registers)
    assert registers.value.code == "SVD_XML_INVALID"


def test_register_extent_and_array_address_overflow_fail_closed(tmp_path: Path) -> None:
    payload = (
        b'<device><name>STM32F429ZITx</name><peripherals><peripheral>'
        b'<name>GPIOA</name><baseAddress>0xffffffff</baseAddress><registers>'
        b'<register><name>VALUE</name><addressOffset>0</addressOffset><size>32</size>'
        b'</register></registers></peripheral></peripherals></device>'
    )
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_XML_INVALID"


def test_default_array_indices_expand_deterministically(tmp_path: Path) -> None:
    selection = _select_payload(
        tmp_path,
        _document(
            '<registers><register><name>VALUE%s</name><addressOffset>0</addressOffset>'
            '<dim>2</dim><dimIncrement>4</dimIncrement><size>32</size>'
            '</register></registers>'
        ),
    )
    assert selection.register("GPIOA.VALUE0").address == 0x40020000
    assert selection.register("GPIOA.VALUE1").address == 0x40020004


def test_reset_metadata_wider_than_register_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(SvdError) as error:
        _select_payload(
            tmp_path,
            _document(
                '<registers><register><name>VALUE</name><addressOffset>0</addressOffset>'
                '<size>8</size><resetValue>0x100</resetValue></register></registers>'
            ),
        )
    assert error.value.code == "SVD_XML_INVALID"


@pytest.mark.parametrize(
    "payload",
    [
        _document('<registers><register derivedFrom="B"><name>A</name><addressOffset>0</addressOffset></register>'
                  '<register derivedFrom="A"><name>B</name><addressOffset>4</addressOffset></register></registers>'),
        _document('<registers><register><name>BAD NAME</name><addressOffset>0</addressOffset></register></registers>'),
        _document('<registers><register><name>VALUE</name><addressOffset>wat</addressOffset></register></registers>'),
        _document('<registers><register><name>VALUE</name><addressOffset>0</addressOffset><size>7</size></register></registers>'),
        _document('<registers><register><name>VALUE%s</name><addressOffset>0</addressOffset><dim>2</dim>'
                  '<dimIncrement>4</dimIncrement><dimIndex>0</dimIndex></register></registers>'),
        _document('<registers><cluster><name>BAD NAME</name><addressOffset>0</addressOffset>'
                  '<register><name>VALUE</name><addressOffset>0</addressOffset></register></cluster></registers>'),
    ],
)
def test_malformed_inheritance_array_cluster_and_numbers_are_rejected(
    tmp_path: Path, payload: bytes
) -> None:
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_XML_INVALID"


def test_permission_and_oversize_fail_with_stable_codes(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "device.svd"
    path.write_bytes(FIXTURE.read_bytes())
    real_open = os.open

    def denied(path_value, flags):
        if Path(path_value) == path:
            raise PermissionError(r"denied C:\\private\\device.svd")
        return real_open(path_value, flags)

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(SvdError) as permission:
        select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert permission.value.code == "SVD_PATH_INVALID"
    assert "private" not in permission.value.message

    monkeypatch.setattr(os, "open", real_open)
    real_lstat = os.lstat

    def oversized(path_value):
        result = real_lstat(path_value)
        if Path(path_value) == path:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_dev=result.st_dev,
                st_ino=result.st_ino,
                st_size=8 * 1024 * 1024 + 1,
                st_file_attributes=getattr(result, "st_file_attributes", 0),
            )
        return result

    monkeypatch.setattr(os, "lstat", oversized)
    with pytest.raises(SvdError) as size:
        select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert size.value.code == "SVD_SIZE_LIMIT"


def test_parent_identity_swap_is_rejected_before_xml_parse(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    nested = project / "svd"
    nested.mkdir(parents=True)
    (nested / "device.svd").write_bytes(FIXTURE.read_bytes())
    real_lstat = os.lstat
    nested_calls = 0

    def swapped(path_value):
        nonlocal nested_calls
        result = real_lstat(path_value)
        if Path(path_value) == nested:
            nested_calls += 1
            if nested_calls > 1:
                values = list(result)
                values[1] += 1
                return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", swapped)
    with pytest.raises(SvdError) as error:
        select_svd(project, "STM32F429ZITx", (Path("svd/device.svd"),))
    assert error.value.code == "SVD_INPUT_CHANGED"


def test_descriptor_identity_swap_is_rejected_before_xml_parse(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "device.svd"
    path.write_bytes(FIXTURE.read_bytes())
    real_lstat = os.lstat
    file_calls = 0

    def swapped(path_value):
        nonlocal file_calls
        result = real_lstat(path_value)
        if Path(path_value) == path:
            file_calls += 1
            if file_calls > 1:
                values = list(result)
                values[1] += 1
                return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", swapped)
    with pytest.raises(SvdError) as error:
        select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    assert error.value.code == "SVD_INPUT_CHANGED"


@pytest.mark.skipif(os.name != "nt", reason="Windows NTFS junction gate")
def test_real_ntfs_junction_candidate_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "device.svd").write_bytes(FIXTURE.read_bytes())
    junction = project / "redirect"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    with pytest.raises(SvdError) as error:
        select_svd(project, "STM32F429ZITx", (Path("redirect/device.svd"),))
    assert error.value.code == "SVD_PATH_INVALID"

    with pytest.raises(SvdError) as root_error:
        select_svd(junction, "STM32F429ZITx", (Path("device.svd"),))
    assert root_error.value.code == "SVD_PATH_INVALID"
