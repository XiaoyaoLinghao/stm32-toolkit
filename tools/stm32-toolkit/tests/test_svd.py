from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.debug import svd as svd_module
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.debug.svd import SvdError, SvdSelection, select_svd as _select_svd


FIXTURE = Path(__file__).parent / "fixtures" / "svd" / "STM32F429-exact.svd"
READABLE = (
    MemoryRegionBinding("PERIPHERAL", 0x40000000, 0x01000000, "rw-"),
)


def select_svd(project_root, target_device, candidates, *, readable_regions=READABLE):
    return _select_svd(
        project_root,
        target_device,
        candidates,
        readable_regions=readable_regions,
    )


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
        '<device><name>STM32F429ZITx</name><size>32</size>'
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


def _binding(project_root: Path, *, regions=READABLE) -> DebugFirmwareBinding:
    return DebugFirmwareBinding(
        project_root=project_root.resolve(strict=True),
        logical_project_id="project-a",
        workspace_id="workspace-a",
        observation_session_id="observe-a",
        flash_session_id="flash-a",
        lease_id="lease-a",
        probe_id="probe-a",
        target_device="STM32F429ZITx",
        debug_target="stm32f429zitx",
        build_id="a" * 64,
        elf_sha256="b" * 64,
        elf_size=1024,
        elf_path="build/firmware.elf",
        input_snapshot_sha256="c" * 64,
        git_head="d" * 40,
        git_dirty=False,
        confirmed_at_utc="2026-08-08T12:00:00.000000Z",
        memory_regions=regions,
    )


def test_readable_regions_are_required_and_every_register_must_be_contained(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "device.svd").write_bytes(FIXTURE.read_bytes())

    with pytest.raises(TypeError):
        _select_svd(project, "STM32F429ZITx", (Path("device.svd"),))
    with pytest.raises(SvdError) as outside:
        select_svd(
            project,
            "STM32F429ZITx",
            (Path("device.svd"),),
            readable_regions=(MemoryRegionBinding("RAM", 0x20000000, 0x1000, "rw-"),),
        )
    assert outside.value.code == "SVD_ADDRESS_OUT_OF_RANGE"


def test_selection_has_unforgeable_provenance_and_revalidates_current_binding(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "device.svd"
    path.write_bytes(FIXTURE.read_bytes())
    selection = select_svd(project, "STM32F429ZITx", (Path("device.svd"),))

    assert selection.file_size == path.stat().st_size
    assert selection.readable_regions == READABLE
    assert selection.revalidate(_binding(project), project) is True
    with pytest.raises(TypeError):
        SvdSelection("STM32F429ZITx", "device.svd", "a" * 64, ())

    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SvdError) as changed:
        selection.revalidate(_binding(project), project)
    assert changed.value.code == "SVD_INPUT_CHANGED"


def test_forward_derived_register_and_cluster_defaults_are_resolved(
    tmp_path: Path,
) -> None:
    selection = _select_payload(
        tmp_path,
        _document(
            '<access>read-write</access><registers>'
            '<register derivedFrom="BASE"><name>COPY</name><addressOffset>4</addressOffset></register>'
            '<register><name>BASE</name><addressOffset>0</addressOffset><size>16</size>'
            '<access>read-only</access><resetValue>0x12</resetValue><resetMask>0xffff</resetMask></register>'
            '<cluster><name>GROUP</name><addressOffset>0x20</addressOffset><size>8</size>'
            '<access>write-only</access><resetValue>1</resetValue><resetMask>0xff</resetMask>'
            '<register><name>COMMAND</name><addressOffset>0</addressOffset></register></cluster>'
            '</registers>'
        ),
    )

    copy = selection.register("GPIOA.COPY")
    assert (copy.size_bytes, copy.access, copy.reset_value, copy.reset_mask) == (
        2,
        "read-only",
        0x12,
        0xFFFF,
    )
    command = selection.register("GPIOA.GROUP.COMMAND")
    assert (command.size_bytes, command.access, command.reset_value) == (
        1,
        "write-only",
        1,
    )
    with pytest.raises(SvdError) as denied:
        command.authorize_read(True, sampling=False)
    assert denied.value.code == "SVD_REGISTER_WRITE_ONLY"


def test_derived_from_cycle_and_wrong_scope_fail_closed(tmp_path: Path) -> None:
    cycle = _document(
        '<registers><register derivedFrom="B"><name>A</name><addressOffset>0</addressOffset></register>'
        '<register derivedFrom="A"><name>B</name><addressOffset>4</addressOffset></register></registers>'
    )
    with pytest.raises(SvdError) as cycle_error:
        _select_payload(tmp_path, cycle)
    assert cycle_error.value.code == "SVD_XML_INVALID"

    wrong_scope = tmp_path / "wrong-scope"
    payload = _document(
        '<registers><cluster><name>GROUP</name><addressOffset>0</addressOffset>'
        '<register derivedFrom="OUTER"><name>VALUE</name><addressOffset>0</addressOffset></register>'
        '</cluster><register><name>OUTER</name><addressOffset>4</addressOffset></register></registers>'
    )
    with pytest.raises(SvdError) as scope_error:
        _select_payload(wrong_scope, payload)
    assert scope_error.value.code == "SVD_XML_INVALID"


def test_forward_peripheral_and_cluster_inheritance_use_local_scope(
    tmp_path: Path,
) -> None:
    payload = (
        '<device><name>STM32F429ZITx</name><size>32</size><peripherals>'
        '<peripheral derivedFrom="BASE"><name>COPY</name><baseAddress>0x40021000</baseAddress></peripheral>'
        '<peripheral><name>BASE</name><baseAddress>0x40020000</baseAddress><size>16</size>'
        '<access>read-only</access><registers>'
        '<cluster derivedFrom="GROUP_BASE"><name>GROUP_COPY</name><addressOffset>0x40</addressOffset></cluster>'
        '<cluster><name>GROUP_BASE</name><addressOffset>0x20</addressOffset><size>8</size>'
        '<resetValue>1</resetValue><resetMask>0xff</resetMask>'
        '<register><name>VALUE</name><addressOffset>0</addressOffset></register>'
        '</cluster></registers></peripheral></peripherals></device>'
    ).encode("utf-8")

    selection = _select_payload(tmp_path, payload)

    assert selection.register("BASE.GROUP_COPY.VALUE").address == 0x40020040
    inherited = selection.register("COPY.GROUP_BASE.VALUE")
    assert (inherited.address, inherited.size_bytes, inherited.access) == (
        0x40021020,
        1,
        "read-only",
    )


def test_nested_cluster_local_scope_inheritance_and_arrays_are_supported(
    tmp_path: Path,
) -> None:
    selection = _select_payload(
        tmp_path,
        _document(
            '<registers><cluster><name>TOP%s</name><addressOffset>0x100</addressOffset>'
            '<dim>2</dim><dimIncrement>0x1000</dimIncrement><size>16</size>'
            '<access>read-only</access>'
            '<cluster derivedFrom="INNER_BASE"><name>INNER%s</name><addressOffset>0x40</addressOffset>'
            '<dim>2</dim><dimIncrement>0x20</dimIncrement></cluster>'
            '<cluster><name>INNER_BASE</name><addressOffset>0x10</addressOffset><size>8</size>'
            '<register><name>VALUE%s</name><addressOffset>0</addressOffset>'
            '<dim>2</dim><dimIncrement>1</dimIncrement></register></cluster>'
            '</cluster></registers>'
        ),
    )

    assert len(selection.registers) == 12
    inherited = selection.register("GPIOA.TOP1.INNER1.VALUE1")
    assert (inherited.address, inherited.size_bytes, inherited.access) == (
        0x40021161,
        1,
        "read-only",
    )


def test_cluster_nesting_depth_is_rejected_before_expansion(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(svd_module, "_MAX_CLUSTER_NESTING_DEPTH", 2, raising=False)
    monkeypatch.setattr(
        svd_module,
        "_format_dim_name",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("cluster expansion began before nesting validation")
        ),
    )
    payload = _document(
        '<registers><cluster><name>LEVEL0</name><addressOffset>0</addressOffset>'
        '<cluster><name>LEVEL1</name><addressOffset>0</addressOffset>'
        '<cluster><name>LEVEL2</name><addressOffset>0</addressOffset>'
        '<register><name>VALUE</name><addressOffset>0</addressOffset></register>'
        '</cluster></cluster></cluster></registers>'
    )

    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_SIZE_LIMIT"


def test_deep_sibling_derived_cluster_chain_has_a_stable_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        svd_module,
        "_format_dim_name",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("cluster expansion began before derived-depth validation")
        ),
    )
    declarations = [
        f'<cluster derivedFrom="C{index + 1}"><name>C{index}</name>'
        f'<addressOffset>{index * 4}</addressOffset></cluster>'
        for index in range(1099)
    ]
    declarations.append(
        '<cluster><name>C1099</name><addressOffset>0</addressOffset>'
        '<register><name>VALUE</name><addressOffset>0</addressOffset></register></cluster>'
    )
    payload = _document(f"<registers>{''.join(declarations)}</registers>")

    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_SIZE_LIMIT"


@pytest.mark.parametrize(
    "payload",
    [
        (
            '<device><name>STM32F429ZITx</name><size>32</size><peripherals>'
            '<peripheral derivedFrom="B"><name>A</name><baseAddress>0x40020000</baseAddress></peripheral>'
            '<peripheral derivedFrom="A"><name>B</name><baseAddress>0x40021000</baseAddress></peripheral>'
            '</peripherals></device>'
        ).encode("utf-8"),
        _document(
            '<registers><cluster derivedFrom="B"><name>A</name><addressOffset>0</addressOffset></cluster>'
            '<cluster derivedFrom="A"><name>B</name><addressOffset>4</addressOffset></cluster></registers>'
        ),
        (
            '<device><name>STM32F429ZITx</name><size>32</size><peripherals>'
            '<peripheral><name>GPIOA</name><baseAddress>0x40020000</baseAddress></peripheral>'
            '<peripheral><name>GPIOA</name><baseAddress>0x40021000</baseAddress></peripheral>'
            '</peripherals></device>'
        ).encode("utf-8"),
    ],
)
def test_peripheral_cluster_cycles_and_ambiguity_fail_closed(
    tmp_path: Path, payload: bytes
) -> None:
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_XML_INVALID"


def test_expansion_budget_fails_before_dim_cartesian_product(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(svd_module, "_MAX_REGISTERS", 2)
    monkeypatch.setattr(
        svd_module,
        "_format_dim_name",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("dimension expansion began before budget check")
        ),
    )
    payload = _document(
        '<registers><register><name>VALUE%s</name><addressOffset>0</addressOffset>'
        '<dim>3</dim><dimIncrement>4</dimIncrement></register></registers>'
    )
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, payload)
    assert error.value.code == "SVD_SIZE_LIMIT"


def test_xml_and_declaration_budgets_return_stable_size_limit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(svd_module, "_MAX_XML_ELEMENTS", 3)
    with pytest.raises(SvdError) as xml_error:
        _select_payload(tmp_path, FIXTURE.read_bytes())
    assert xml_error.value.code == "SVD_SIZE_LIMIT"


@pytest.mark.parametrize(
    ("constant", "limit"),
    [
        ("_MAX_PERIPHERALS", 0),
        ("_MAX_CLUSTERS", 0),
        ("_MAX_REGISTER_DECLARATIONS", 1),
        ("_MAX_FIELDS", 1),
    ],
)
def test_each_declaration_budget_has_a_stable_limit_plus_one_failure(
    tmp_path: Path, monkeypatch, constant: str, limit: int
) -> None:
    monkeypatch.setattr(svd_module, constant, limit)
    with pytest.raises(SvdError) as error:
        _select_payload(tmp_path, FIXTURE.read_bytes())
    assert error.value.code == "SVD_SIZE_LIMIT"


def test_revalidation_rejects_wrong_root_binding_and_replaced_descriptor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "device.svd"
    path.write_bytes(FIXTURE.read_bytes())
    selection = select_svd(project, "STM32F429ZITx", (Path("device.svd"),))

    wrong_regions = (
        MemoryRegionBinding("PERIPHERAL", 0x40000000, 0x00800000, "rw-"),
    )
    with pytest.raises(SvdError) as binding_error:
        selection.revalidate(_binding(project, regions=wrong_regions), project)
    assert binding_error.value.code == "SVD_PROVENANCE_MISMATCH"

    other = tmp_path / "other"
    other.mkdir()
    (other / "device.svd").write_bytes(FIXTURE.read_bytes())
    with pytest.raises(SvdError) as root_error:
        selection.revalidate(_binding(other), other)
    assert root_error.value.code == "SVD_PROVENANCE_MISMATCH"

    original = path.read_bytes()
    replacement = project / "replacement.svd"
    replacement.write_bytes(original)
    path.unlink()
    replacement.rename(path)
    with pytest.raises(SvdError) as descriptor_error:
        selection.revalidate(_binding(project), project)
    assert descriptor_error.value.code == "SVD_INPUT_CHANGED"
