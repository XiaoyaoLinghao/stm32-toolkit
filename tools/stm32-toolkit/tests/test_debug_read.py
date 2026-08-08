from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from elftools.elf.elffile import ELFFile

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import (
    atomic_write_json,
    build_identity_document,
    git_evidence,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_elf,
)
from stm32_toolkit.build.runner import build_result_document
from stm32_toolkit.debug.dwarf import DwarfCatalog
from stm32_toolkit.debug import read as read_mod
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.debug.read import (
    RegisterReadRequest,
    VariableReadRequest,
    read_registers,
    read_variables,
)
from stm32_toolkit.debug.svd import SvdSelection, select_svd
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION
from stm32_toolkit.project_model import load_project_model

from test_build_runner import prepare_project
from test_debug_firmware import _flash_result


FIXTURE_ELF = Path(__file__).parent / "fixtures" / "dwarf" / "typed.elf"
FIXTURE_SVD = Path(__file__).parent / "fixtures" / "svd" / "STM32F429-exact.svd"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class DebugEnv:
    root: Path
    binding: DebugFirmwareBinding
    catalog: DwarfCatalog
    selection: SvdSelection
    memory: dict[int, bytes]

    def client(self) -> "Client":
        return Client(dict(self.memory))


def _memory_image(path: Path) -> dict[int, bytes]:
    result: dict[int, bytes] = {}
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_LOAD" and int(segment["p_filesz"]) > 0:
                result[int(segment["p_vaddr"])] = bytes(segment.data())
    result[0x40020010] = bytes.fromhex(
        "78563412"  # GPIOA.IDR
        "20000000"  # GPIOA.EVENT
        "00000000"  # GPIOA.COMMAND
        "44332211"  # GPIOA.IDR_COPY
    )
    result[0x40020100] = b"\x34\x12"
    result[0x40020120] = b"\x78\x56"
    return result


@pytest.fixture
def debug_env(tmp_path: Path) -> DebugEnv:
    root = prepare_project(tmp_path / "project").resolve()
    manifest_path = root / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target"]["device"] = "STM32F429ZITx"
    manifest["debug"]["target"] = "stm32f429zi"
    manifest["debug"]["svd"] = "svd/device.svd"
    # The checked-in standalone DWARF fixture maps its initialized globals in
    # a file-backed RAM PT_LOAD. Mark that fixture region executable/read-only
    # so the production flash-evidence validator can prove every PT_LOAD.
    manifest["memory"]["regions"][1]["attributes"] = "r-x"
    manifest["memory"]["regions"].append(
        {
            "name": "PERIPH",
            "origin": 0x40000000,
            "length": 0x10000000,
            "attributes": "rw-",
        }
    )
    manifest_path.write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    svd_path = root / "svd" / "device.svd"
    svd_path.parent.mkdir()
    shutil.copyfile(FIXTURE_SVD, svd_path)

    model = load_project_model(root)
    snapshot = snapshot_project_inputs(model)
    git = git_evidence(root)
    elf_data = FIXTURE_ELF.read_bytes()
    map_data = b"typed DWARF fixture map\n"
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    map_path = root / "build" / "arm-debug" / "firmware.map"
    elf_path.parent.mkdir(parents=True, exist_ok=True)
    elf_path.write_bytes(elf_data)
    map_path.write_bytes(map_data)
    elf = validate_elf(elf_path, model)
    identity = build_identity_document(
        model=model,
        preset="arm-debug",
        git=git,
        snapshot=snapshot,
        elf=elf,
        elf_size=len(elf_data),
        elf_sha256=_sha256(elf_data),
        map_size=len(map_data),
        map_sha256=_sha256(map_data),
        built_at_utc=utc_now_rfc3339(),
    )
    atomic_write_json(
        root / "build" / "arm-debug" / "firmware-identity.json", identity
    )
    result = build_result_document(
        status="success",
        stage="complete",
        code="OK",
        build_id=str(identity["buildId"]),
        git_head=str(identity["gitHead"]),
        git_dirty=bool(identity["gitDirty"]),
        input_snapshot_sha256=str(identity["inputSnapshotSha256"]),
        target_device=str(identity["targetDevice"]),
        preset="arm-debug",
        started_at_utc=utc_now_rfc3339(),
        finished_at_utc=utc_now_rfc3339(),
        duration_ms=1,
        artifacts=[
            {
                "kind": "elf",
                "path": "build/arm-debug/firmware.elf",
                "sha256": _sha256(elf_data),
                "size": len(elf_data),
            },
            {
                "kind": "map",
                "path": "build/arm-debug/firmware.map",
                "sha256": _sha256(map_data),
                "size": len(map_data),
            },
        ],
        memory=[],
        warnings=[],
    )
    atomic_write_json(root / "artifacts" / "migration" / "build-result.json", result)
    flash = _flash_result(identity)
    flash["debugTarget"] = "stm32f429zi"
    with elf_path.open("rb") as stream:
        flash["verifiedBytes"] = sum(
            int(segment["p_filesz"])
            for segment in ELFFile(stream).iter_segments()
            if segment["p_type"] == "PT_LOAD" and int(segment["p_filesz"]) > 0
        )
    atomic_write_json(root / "artifacts" / "migration" / "flash-result.json", flash)

    regions = tuple(
        MemoryRegionBinding(item.name, item.origin, item.length, item.attributes)
        for item in model.memory.regions
        if "r" in item.attributes
    )
    binding = DebugFirmwareBinding(
        logical_project_id=str(model.logical_project_id),
        workspace_id="workspace-a",
        observation_session_id="observe-session",
        flash_session_id="flash-session",
        lease_id="lease-observe",
        probe_id="probe-123",
        target_device=model.target.device,
        debug_target=str(model.debug.target),
        build_id=str(identity["buildId"]),
        elf_sha256=str(identity["elfSha256"]),
        elf_size=int(identity["elfSize"]),
        elf_path=str(identity["elfPath"]),
        input_snapshot_sha256=str(identity["inputSnapshotSha256"]),
        git_head=str(identity["gitHead"]),
        git_dirty=bool(identity["gitDirty"]),
        confirmed_at_utc=utc_now_rfc3339(),
        memory_regions=regions,
        project_root=root,
    )
    catalog = DwarfCatalog.from_binding(binding)
    selection = select_svd(
        root,
        binding.target_device,
        (Path("svd/device.svd"),),
        readable_regions=binding.memory_regions,
    )
    return DebugEnv(root, binding, catalog, selection, _memory_image(elf_path))


class Client:
    def __init__(self, memory: dict[int, bytes]) -> None:
        self.memory = memory
        self.calls: list[tuple[int, int]] = []
        self.attach_count = 0
        self.fail_once: set[tuple[int, int]] = set()
        self.partial: set[tuple[int, int]] = set()
        self.after_read = None
        self.endpoint = SimpleNamespace(
            protocol=PROBE_PROTOCOL_VERSION,
            toolkit_version=__version__,
            host="127.0.0.1",
            port=23456,
            token="d" * 64,
            workspace_id="workspace-a",
            session_id="observe-session",
            lease_id="lease-observe",
            probe_id="probe-123",
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
        key = (address, length)
        self.calls.append(key)
        if key in self.fail_once:
            self.fail_once.remove(key)
            raise RuntimeError("raw transport detail must not escape")
        data = bytearray()
        for offset in range(length):
            byte = None
            for start, value in reversed(tuple(self.memory.items())):
                if start <= address + offset < start + len(value):
                    byte = value[address + offset - start]
                    break
            if byte is None:
                raise RuntimeError("unavailable")
            data.append(byte)
        if callable(self.after_read):
            callback, self.after_read = self.after_read, None
            callback()
        if key in self.partial:
            return bytes(data[:-1])
        return bytes(data)


def test_variables_use_real_provenance_merge_and_preserve_order(
    debug_env: DebugEnv,
) -> None:
    values = tuple(debug_env.catalog.lookup(f"values[{index}]") for index in range(3))
    far = debug_env.catalog.lookup("signed32")
    client = debug_env.client()
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding,
                debug_env.catalog,
                ("values[1]", "values[0]", "values[2]", "signed32"),
            ),
            client,
        )
    )
    assert result.ok is True
    assert client.calls == [(values[0].address, 12), (far.address, 4)]
    assert [item.expression for item in result.data.items] == [
        "values[1]",
        "values[0]",
        "values[2]",
        "signed32",
    ]
    assert [item.value.value for item in result.data.items[:3]] == [22, 11, 33]
    assert result.data.binding == debug_env.binding
    assert client.attach_count == 4  # before and after both hardware reads


def test_nonadjacent_and_cross_region_reads_are_not_merged(debug_env: DebugEnv) -> None:
    flash = debug_env.catalog.lookup("qualified")
    ram = debug_env.catalog.lookup("signed32")
    client = debug_env.client()
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding, debug_env.catalog, ("signed32", "qualified")
            ),
            client,
        )
    )
    assert result.ok is True
    assert client.calls == [(flash.address, 4), (ram.address, 4)]


def test_merged_failure_retries_items_and_isolates_transport_error(
    debug_env: DebugEnv,
) -> None:
    first = debug_env.catalog.lookup("values[0]")
    client = debug_env.client()
    client.fail_once.update({(first.address, 8), (first.address + 4, 4)})
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding, debug_env.catalog, ("values[0]", "values[1]")
            ),
            client,
        )
    )
    assert client.calls == [
        (first.address, 8),
        (first.address, 4),
        (first.address + 4, 4),
    ]
    assert [(item.status, item.code) for item in result.data.items] == [
        ("ok", None),
        ("error", "DEBUG_READ_UNAVAILABLE"),
    ]

    partial = debug_env.client()
    partial.partial.add((first.address, 8))
    recovered = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding, debug_env.catalog, ("values[0]", "values[1]")
            ),
            partial,
        )
    )
    assert partial.calls == [
        (first.address, 8),
        (first.address, 4),
        (first.address + 4, 4),
    ]
    assert all(item.status == "ok" for item in recovered.data.items)


def test_exact_length_and_dwarf_failures_are_item_scoped(debug_env: DebugEnv) -> None:
    selected = debug_env.catalog.lookup("signed32")
    client = debug_env.client()
    client.partial.add((selected.address, selected.byte_size))
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding,
                debug_env.catalog,
                ("signed32", "register_local", "missing"),
            ),
            client,
        )
    )
    assert [(item.status, item.code) for item in result.data.items] == [
        ("error", "DEBUG_PARTIAL_READ"),
        ("error", "DWARF_LOCATION_REGISTER_ONLY"),
        ("error", "DWARF_SYMBOL_NOT_FOUND"),
    ]


def test_endpoint_attachment_and_firmware_are_revalidated(debug_env: DebugEnv) -> None:
    request = VariableReadRequest(
        debug_env.binding, debug_env.catalog, ("signed32",)
    )
    client = debug_env.client()
    client.endpoint.lease_id = "replacement"
    assert asyncio.run(read_variables(request, client)).code == "DEBUG_ENDPOINT_MISMATCH"
    assert client.calls == []

    client = debug_env.client()

    async def wrong_attach(probe_id: str, target: str) -> object:
        return SimpleNamespace(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number="STM32F103",
            core_count=1,
        )

    client.attach = wrong_attach
    assert asyncio.run(read_variables(request, client)).code == "DEBUG_TARGET_MISMATCH"
    assert client.calls == []

    client = debug_env.client()

    async def failed_attach(probe_id: str, target: str) -> object:
        raise RuntimeError("raw attach detail")

    client.attach = failed_attach
    failed = asyncio.run(read_variables(request, client))
    assert failed.code == "DEBUG_TARGET_MISMATCH"
    assert "raw attach detail" not in str(failed.to_dict())

    client = debug_env.client()
    elf_path = debug_env.root / debug_env.binding.elf_path
    client.after_read = lambda: elf_path.write_bytes(elf_path.read_bytes() + b"changed")
    changed = asyncio.run(read_variables(request, client))
    assert changed.code == "DEBUG_FIRMWARE_CHANGED"
    assert len(client.calls) == 1


def test_requests_reject_raw_or_forged_catalogs(debug_env: DebugEnv) -> None:
    client = debug_env.client()
    invalid = ((), tuple("x" for _ in range(257)), ("x", "x"))
    for expressions in invalid:
        result = asyncio.run(
            read_variables(
                VariableReadRequest(debug_env.binding, debug_env.catalog, expressions),
                client,
            )
        )
        assert result.code == "DEBUG_REQUEST_INVALID"
    assert asyncio.run(read_variables(object(), client)).code == "DEBUG_REQUEST_INVALID"
    assert (
        asyncio.run(
            read_variables(
                VariableReadRequest(debug_env.binding, object(), ("signed32",)), client
            )
        ).code
        == "DEBUG_REQUEST_INVALID"
    )


def test_registers_use_real_exact_svd_and_strict_risk_ack(debug_env: DebugEnv) -> None:
    client = debug_env.client()
    denied = asyncio.run(
        read_registers(
            RegisterReadRequest(
                debug_env.binding, debug_env.selection, ("GPIOA.EVENT",), False
            ),
            client,
        )
    )
    assert denied.data.items[0].code == "SVD_ACCESS_RISK_ACK_REQUIRED"
    assert client.calls == []

    allowed = asyncio.run(
        read_registers(
            RegisterReadRequest(
                debug_env.binding, debug_env.selection, ("GPIOA.EVENT",), True
            ),
            client,
        )
    )
    assert allowed.data.items[0].value.value == 32
    assert allowed.data.items[0].value.raw_hex == "0x00000020"

    multiple = asyncio.run(
        read_registers(
            RegisterReadRequest(
                debug_env.binding,
                debug_env.selection,
                ("GPIOA.IDR", "GPIOA.EVENT"),
                True,
            ),
            client,
        )
    )
    assert multiple.data.items[1].code == "SVD_ACCESS_RISK_ACK_REQUIRED"


def test_register_write_only_missing_and_provenance_fail_closed(
    debug_env: DebugEnv,
) -> None:
    result = asyncio.run(
        read_registers(
            RegisterReadRequest(
                debug_env.binding,
                debug_env.selection,
                ("GPIOA.COMMAND", "MISSING.REG"),
                True,
            ),
            debug_env.client(),
        )
    )
    assert [(item.status, item.code) for item in result.data.items] == [
        ("error", "SVD_REGISTER_WRITE_ONLY"),
        ("error", "SVD_REGISTER_NOT_FOUND"),
    ]
    forged = replace(
        debug_env.binding,
        target_device="STM32F407VGTx",
    )
    assert (
        asyncio.run(
            read_registers(
                RegisterReadRequest(forged, debug_env.selection, ("GPIOA.IDR",), False),
                debug_env.client(),
            )
        ).code
        == "DEBUG_FIRMWARE_CHANGED"
    )


def test_real_enum_wide_integer_and_decode_error(debug_env: DebugEnv) -> None:
    client = debug_env.client()
    enabled = debug_env.catalog.lookup("enabled")
    client.memory[enabled.address] = b"\x02"
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding,
                debug_env.catalog,
                ("mode_known", "unsigned64", "enabled"),
            ),
            client,
        )
    )
    assert result.data.items[0].value.value == {"value": 7, "name": "MODE_RUN"}
    assert result.data.items[1].value.value == "12345678901234567890"
    assert result.data.items[2].code == "DWARF_BOOLEAN_INVALID"


def test_cancellation_propagates_without_orphan(debug_env: DebugEnv) -> None:
    request = VariableReadRequest(
        debug_env.binding, debug_env.catalog, ("signed32",)
    )

    class CancelAttach(Client):
        async def attach(self, probe_id: str, target: str) -> object:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(read_variables(request, CancelAttach(dict(debug_env.memory))))

    class CancelRead(Client):
        async def read_memory(self, address: int, length: int) -> bytes:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(read_variables(request, CancelRead(dict(debug_env.memory))))


def test_invalid_register_request_shapes(debug_env: DebugEnv) -> None:
    client = debug_env.client()
    assert asyncio.run(read_registers(object(), client)).code == "DEBUG_REQUEST_INVALID"
    invalid = (
        RegisterReadRequest(object(), debug_env.selection, ("GPIOA.IDR",), False),
        RegisterReadRequest(debug_env.binding, object(), ("GPIOA.IDR",), False),
        RegisterReadRequest(debug_env.binding, debug_env.selection, ("GPIOA.IDR",), 1),
    )
    for request in invalid:
        assert asyncio.run(read_registers(request, client)).code == "DEBUG_REQUEST_INVALID"


def test_debug_read_report_constructor_failures_are_stable(
    debug_env: DebugEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_report(*args: object, **kwargs: object) -> object:
        raise TypeError("raw constructor detail")

    monkeypatch.setattr(read_mod, "DebugReadReport", invalid_report)
    result = asyncio.run(
        read_variables(
            VariableReadRequest(
                debug_env.binding, debug_env.catalog, ("signed32",)
            ),
            debug_env.client(),
        )
    )
    assert result.code == "DEBUG_INTERNAL_ERROR"
    assert "raw constructor detail" not in str(result.to_dict())
