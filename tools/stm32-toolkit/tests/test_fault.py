from __future__ import annotations

import asyncio
import hashlib
import io
import struct
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from elftools.elf.elffile import ELFFile

from stm32_toolkit import __version__
import stm32_toolkit.debug.fault as fault_mod
from stm32_toolkit.debug.fault import FaultAnalysisRequest, analyze_fault
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.probe.client import ProbeClientError
from stm32_toolkit.probe.backend import ProbeAttachmentEvidence
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION


CORE_REGISTERS = (
    "r0",
    "r1",
    "r2",
    "r3",
    "r12",
    "sp",
    "lr",
    "pc",
    "xpsr",
    "msp",
    "psp",
    "control",
    "primask",
    "basepri",
    "faultmask",
)
SCB_BASE = 0xE000_ED24
SCB_LENGTH = 24


def _binding(elf: bytes, project_root: Path) -> DebugFirmwareBinding:
    return DebugFirmwareBinding(
        logical_project_id="12345678-1234-1234-1234-123456789abc",
        workspace_id="workspace-a",
        observation_session_id="observe-session",
        flash_session_id="flash-session",
        lease_id="lease-a",
        probe_id="probe-123",
        target_device="STM32F407VGTx",
        debug_target="stm32f407vg",
        build_id="1" * 64,
        elf_sha256=hashlib.sha256(elf).hexdigest(),
        elf_size=len(elf),
        elf_path="build/arm-debug/firmware.elf",
        input_snapshot_sha256="3" * 64,
        git_head="4" * 40,
        git_dirty=False,
        confirmed_at_utc="2026-08-08T01:02:03.000004Z",
        memory_regions=(
            MemoryRegionBinding("FLASH", 0x0800_0000, 0x1000, "r-x"),
            MemoryRegionBinding("RAM", 0x2000_0000, 0x1000, "rwx"),
        ),
        project_root=project_root,
    )


def _status_bytes(
    *,
    shcsr: int = (1 << 16) | (1 << 17),
    cfsr: int = (1 << 0) | (1 << 7) | (1 << 9) | (1 << 15) | (1 << 25),
    hfsr: int = (1 << 30),
    dfsr: int = (1 << 1),
    mmfar: int = 0x2000_0010,
    bfar: int = 0x2000_0020,
) -> bytes:
    return b"".join(
        value.to_bytes(4, "little")
        for value in (shcsr, cfsr, hfsr, dfsr, mmfar, bfar)
    )


def _frame(
    *, pc: int = 0x0800_0111, lr: int = 0x0800_0105, xpsr: int = 0x2100_0000
) -> bytes:
    return b"".join(
        value.to_bytes(4, "little")
        for value in (1, 2, 3, 4, 12, lr, pc, xpsr)
    )


def _symbol_entry(image: bytes, name: str) -> tuple[int, dict[str, int]]:
    elf = ELFFile(io.BytesIO(image))
    for section in elf.iter_sections():
        if section.header["sh_type"] != "SHT_SYMTAB":
            continue
        entry_size = int(section.header["sh_entsize"])
        for index, symbol in enumerate(section.iter_symbols()):
            if symbol.name == name:
                return int(section.header["sh_offset"]) + index * entry_size, {
                    "name": int(symbol.entry["st_name"]),
                    "value": int(symbol.entry["st_value"]),
                    "size": int(symbol.entry["st_size"]),
                    "shndx": int(symbol.entry["st_shndx"]),
                }
    raise AssertionError(f"missing fixture symbol {name}")


def _mutate_symbol(
    image: bytes,
    name: str,
    *,
    name_offset: int | None = None,
    value: int | None = None,
    size: int | None = None,
    shndx: int | None = None,
) -> bytes:
    data = bytearray(image)
    offset, original = _symbol_entry(image, name)
    struct.pack_into("<I", data, offset, original["name"] if name_offset is None else name_offset)
    struct.pack_into("<I", data, offset + 4, original["value"] if value is None else value)
    struct.pack_into("<I", data, offset + 8, original["size"] if size is None else size)
    struct.pack_into("<H", data, offset + 14, original["shndx"] if shndx is None else shndx)
    return bytes(data)


def _rebind_elf(fault_env, image: bytes) -> FaultAnalysisRequest:
    _root, _elf, binding, current, _calls, _client, _request = fault_env
    digest = hashlib.sha256(image).hexdigest()
    current.elf_data = image
    current.identity["elfSha256"] = digest
    current.identity["elfSize"] = len(image)
    return FaultAnalysisRequest(
        replace(binding, elf_sha256=digest, elf_size=len(image))
    )


class FaultClient:
    def __init__(self) -> None:
        self.endpoint = SimpleNamespace(
            protocol=PROBE_PROTOCOL_VERSION,
            toolkit_version=__version__,
            host="127.0.0.1",
            port=43123,
            token="11" * 32,
            workspace_id="workspace-a",
            session_id="observe-session",
            lease_id="lease-a",
            probe_id="probe-123",
            operation_level=OperationLevel.OBSERVE,
        )
        self.state = "halted"
        self.events: list[tuple[object, ...]] = []
        self.register_reads = 0
        self.attach_reads = 0
        self.resolved_target = "STM32F407VG"
        self.change_attachment_after_first = False
        self.register_error: BaseException | None = None
        self.memory_error: BaseException | None = None
        self.short_address: int | None = None
        self.change_register_after_first = False
        self.core = {
            "r0": 10,
            "r1": 11,
            "r2": 12,
            "r3": 13,
            "r12": 22,
            "sp": 0x2000_0000,
            "lr": 0xFFFF_FFF9,
            "pc": 0x0800_0015,
            "xpsr": 0x2100_0000,
            "msp": 0x2000_0000,
            "psp": 0x2000_0100,
            "control": 0,
            "primask": 0,
            "basepri": 0,
            "faultmask": 0,
        }
        self.memory = {
            SCB_BASE: _status_bytes(),
            0x2000_0000: _frame(),
            0x2000_0148: _frame(xpsr=0x2100_0200),
        }

    async def attach(self, probe_id: str, target: str) -> ProbeAttachmentEvidence:
        self.events.append(("attach", probe_id, target))
        self.attach_reads += 1
        resolved = self.resolved_target
        if self.change_attachment_after_first and self.attach_reads > 1:
            resolved = "STM32F429ZI"
        return ProbeAttachmentEvidence(probe_id, target, resolved, 1)

    async def read_registers(self, names: tuple[str, ...]) -> dict[str, int]:
        self.events.append(("read_registers", names))
        self.register_reads += 1
        if self.register_error is not None:
            raise self.register_error
        if self.state != "halted":
            raise ProbeClientError(
                "PROBE_REGISTER_UNAVAILABLE",
                "Core registers require an already halted target",
                {"state": self.state},
            )
        values = dict(self.core)
        if self.change_register_after_first and self.register_reads > 1:
            values["pc"] += 2
        return {name: values[name] for name in names}

    async def read_memory(self, address: int, length: int) -> bytes:
        self.events.append(("read_memory", address, length))
        if self.memory_error is not None:
            raise self.memory_error
        data = self.memory.get(address, b"\x00" * length)[:length]
        if self.short_address == address:
            return data[:-1]
        return data


@pytest.fixture
def fault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = (tmp_path / "project").resolve()
    elf = Path("tools/stm32-toolkit/tests/fixtures/dwarf/typed.elf").read_bytes()
    path = root / "build" / "arm-debug" / "firmware.elf"
    path.parent.mkdir(parents=True)
    path.write_bytes(elf)
    binding = _binding(elf, root)
    current = SimpleNamespace(
        elf_data=elf,
        elf_path=binding.elf_path,
        identity={
            "buildId": binding.build_id,
            "elfSha256": binding.elf_sha256,
            "elfSize": binding.elf_size,
            "inputSnapshotSha256": binding.input_snapshot_sha256,
            "gitHead": binding.git_head,
            "gitDirty": binding.git_dirty,
            "logicalProjectId": binding.logical_project_id,
            "targetDevice": binding.target_device,
        },
        model=SimpleNamespace(
            logical_project_id=binding.logical_project_id,
            target=SimpleNamespace(device=binding.target_device),
            debug=SimpleNamespace(target=binding.debug_target),
        ),
    )
    calls = {"load": 0}

    def load(_: Path):
        calls["load"] += 1
        return current

    monkeypatch.setattr("stm32_toolkit.debug.fault._load_fresh_firmware", load)
    client = FaultClient()
    request = FaultAnalysisRequest(binding)
    return root, elf, binding, current, calls, client, request


def test_already_halted_basic_msp_fault_is_complete_and_read_only(fault_env):
    root, _elf, binding, _current, calls, client, request = fault_env

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    report = result.data
    assert report is not None
    document = report.to_dict()
    assert document["binding"] == binding.to_dict()
    assert document["targetState"] == "halted"
    assert document["auditOperation"] == "fault.analyze"
    assert document["registers"]["pc"] == {
        "value": 0x0800_0015,
        "rawHex": "0x08000015",
        "bitWidth": 32,
    }
    assert document["faultStatus"] == {
        "shcsr": {
            "value": 0x0003_0000,
            "rawHex": "0x00030000",
            "bitWidth": 32,
            "active": ["memFaultEnabled", "busFaultEnabled"],
        },
        "cfsr": {
            "value": 0x0200_8281,
            "rawHex": "0x02008281",
            "bitWidth": 32,
            "active": ["iaccviol", "mmarvalid", "preciserr", "bfarvalid", "divbyzero"],
        },
        "hfsr": {"value": 0x4000_0000, "rawHex": "0x40000000", "bitWidth": 32, "active": ["forced"]},
        "dfsr": {"value": 2, "rawHex": "0x00000002", "bitWidth": 32, "active": ["bkpt"]},
        "mmfar": {
            "valid": True,
            "address": {"value": 0x2000_0010, "rawHex": "0x20000010", "bitWidth": 32},
        },
        "bfar": {
            "valid": True,
            "address": {"value": 0x2000_0020, "rawHex": "0x20000020", "bitWidth": 32},
        },
    }
    assert document["stackFrame"] == {
        "stackSource": "msp",
        "frameKind": "basic",
        "stackPointer": {"value": 0x2000_0000, "rawHex": "0x20000000", "bitWidth": 32},
        "basicFrameAddress": {"value": 0x2000_0000, "rawHex": "0x20000000", "bitWidth": 32},
        "alignmentPaddingBytes": 0,
        "totalFrameBytes": 32,
        "r0": {"value": 1, "rawHex": "0x00000001", "bitWidth": 32},
        "r1": {"value": 2, "rawHex": "0x00000002", "bitWidth": 32},
        "r2": {"value": 3, "rawHex": "0x00000003", "bitWidth": 32},
        "r3": {"value": 4, "rawHex": "0x00000004", "bitWidth": 32},
        "r12": {"value": 12, "rawHex": "0x0000000c", "bitWidth": 32},
        "lr": {"value": 0x0800_0105, "rawHex": "0x08000105", "bitWidth": 32},
        "pc": {"value": 0x0800_0111, "rawHex": "0x08000111", "bitWidth": 32},
        "xpsr": {"value": 0x2100_0000, "rawHex": "0x21000000", "bitWidth": 32},
    }
    assert document["symbols"]["pc"]["name"] == "main"
    assert document["symbols"]["lr"]["name"] == "local_case_one"
    assert client.events == [
        ("attach", "probe-123", "stm32f407vg"),
        ("read_registers", CORE_REGISTERS),
        ("read_memory", SCB_BASE, SCB_LENGTH),
        ("read_memory", 0x2000_0000, 32),
        ("attach", "probe-123", "stm32f407vg"),
        ("read_registers", CORE_REGISTERS),
    ]
    assert calls["load"] == 2
    assert not any(name in repr(client.events) for name in ("halt", "resume", "reset", "write"))
    assert (root / "build" / "arm-debug" / "firmware.elf").read_bytes() == _elf


@pytest.mark.parametrize("state", ["running", "sleeping", "reset", "lockedup", "unknown"])
def test_non_halted_target_fails_before_memory_and_never_requests_control(fault_env, state: str):
    *_rest, client, request = fault_env
    client.state = state

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is False
    assert result.code == "FAULT_TARGET_NOT_HALTED"
    assert dict(result.details) == {"state": state}
    assert client.events == [
        ("attach", "probe-123", "stm32f407vg"),
        ("read_registers", CORE_REGISTERS),
    ]


def test_psp_extended_frame_uses_fp_offset_and_alignment_word(fault_env):
    *_rest, client, request = fault_env
    client.core["lr"] = 0xFFFF_FFED

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    frame = result.data.to_dict()["stackFrame"]
    assert frame["stackSource"] == "psp"
    assert frame["frameKind"] == "extended"
    assert frame["stackPointer"] == {"value": 0x2000_0100, "rawHex": "0x20000100", "bitWidth": 32}
    assert frame["basicFrameAddress"] == {"value": 0x2000_0148, "rawHex": "0x20000148", "bitWidth": 32}
    assert frame["alignmentPaddingBytes"] == 4
    assert frame["totalFrameBytes"] == 108
    assert ("read_memory", 0x2000_0148, 32) in client.events


def test_stack_frame_must_be_word_aligned_and_inside_one_readable_region(fault_env):
    *_rest, client, request = fault_env
    client.core["msp"] = 0x2000_0FEF

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is False
    assert result.code == "FAULT_STACK_OUTSIDE_READABLE_MEMORY"
    assert [event for event in client.events if event[0] == "read_memory"] == [
        ("read_memory", SCB_BASE, SCB_LENGTH)
    ]


@pytest.mark.parametrize(
    ("short_address", "code"),
    [(SCB_BASE, "FAULT_STATUS_UNAVAILABLE"), (0x2000_0000, "FAULT_STACK_UNAVAILABLE")],
)
def test_partial_memory_reads_fail_closed(fault_env, short_address: int, code: str):
    *_rest, client, request = fault_env
    client.short_address = short_address

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is False
    assert result.code == code


def test_unavailable_register_or_scb_read_returns_stable_failure(fault_env):
    *_rest, client, request = fault_env
    client.register_error = RuntimeError("backend secret")
    registers = asyncio.run(analyze_fault(request, client))
    assert registers.code == "FAULT_REGISTER_UNAVAILABLE"
    assert "secret" not in registers.message

    client.register_error = None
    client.events.clear()
    client.memory_error = RuntimeError("backend secret")
    status = asyncio.run(analyze_fault(request, client))
    assert status.code == "FAULT_STATUS_UNAVAILABLE"
    assert "secret" not in status.message


@pytest.mark.parametrize(
    "mutation",
    [
        lambda values: values.pop("xpsr"),
        lambda values: values.__setitem__("pc", True),
        lambda values: values.__setitem__("pc", 1 << 32),
        lambda values: values.__setitem__("caller", 0),
    ],
)
def test_core_register_response_is_exact_32_bit_allowlist(fault_env, mutation):
    *_rest, client, request = fault_env

    async def malformed(names: tuple[str, ...]):
        client.events.append(("read_registers", names))
        values = {name: client.core[name] for name in names}
        mutation(values)
        return values

    client.read_registers = malformed
    result = asyncio.run(analyze_fault(request, client))
    assert result.ok is False
    assert result.code == "FAULT_REGISTER_UNAVAILABLE"


def test_exact_endpoint_and_firmware_binding_are_checked_before_target_access(fault_env):
    _root, _elf, binding, current, _calls, client, request = fault_env
    client.endpoint.lease_id = "different"
    endpoint = asyncio.run(analyze_fault(request, client))
    assert endpoint.code == "FAULT_ENDPOINT_MISMATCH"
    assert client.events == []

    client.endpoint.lease_id = binding.lease_id
    current.identity["buildId"] = "9" * 64
    firmware = asyncio.run(analyze_fault(request, client))
    assert firmware.code == "FAULT_FIRMWARE_CHANGED"
    assert client.events == []


def test_exact_attachment_is_checked_before_and_after_capture(fault_env):
    *_rest, client, request = fault_env
    client.resolved_target = "STM32F429ZI"
    before = asyncio.run(analyze_fault(request, client))
    assert before.code == "FAULT_TARGET_MISMATCH"
    assert client.events == [("attach", "probe-123", "stm32f407vg")]

    client.resolved_target = "STM32F407VG"
    client.events.clear()
    client.attach_reads = 0
    client.change_attachment_after_first = True
    after = asyncio.run(analyze_fault(request, client))
    assert after.code == "FAULT_TARGET_CHANGED"
    assert client.events[-1] == ("attach", "probe-123", "stm32f407vg")

def test_identity_or_halted_register_change_during_capture_fails_closed(fault_env):
    _root, _elf, _binding, current, calls, client, request = fault_env
    client.change_register_after_first = True
    changed_state = asyncio.run(analyze_fault(request, client))
    assert changed_state.code == "FAULT_STATE_CHANGED"

    client.change_register_after_first = False
    client.events.clear()
    original = current.identity["elfSha256"]

    async def change_identity_on_stack(address: int, length: int):
        client.events.append(("read_memory", address, length))
        if address == 0x2000_0000:
            current.identity["elfSha256"] = "8" * 64
        return client.memory.get(address, b"\x00" * length)[:length]

    client.read_memory = change_identity_on_stack
    changed_firmware = asyncio.run(analyze_fault(request, client))
    assert changed_firmware.code == "FAULT_FIRMWARE_CHANGED"
    assert calls["load"] >= 3
    current.identity["elfSha256"] = original


def test_identity_change_during_final_halted_check_is_caught_before_publish(fault_env):
    _root, _elf, _binding, current, calls, client, request = fault_env
    original = client.read_registers

    async def mutate_after_final_register_read(names: tuple[str, ...]):
        values = await original(names)
        if client.register_reads == 2:
            current.identity["elfSha256"] = "8" * 64
        return values

    client.read_registers = mutate_after_final_register_read
    result = asyncio.run(analyze_fault(request, client))

    assert result.code == "FAULT_FIRMWARE_CHANGED"
    assert calls["load"] == 2


def test_endpoint_change_during_final_halted_check_is_caught_before_publish(fault_env):
    *_rest, client, request = fault_env
    original = client.read_registers

    async def mutate_endpoint_after_final_register_read(names: tuple[str, ...]):
        values = await original(names)
        if client.register_reads == 2:
            client.endpoint.lease_id = "successor"
        return values

    client.read_registers = mutate_endpoint_after_final_register_read
    result = asyncio.run(analyze_fault(request, client))

    assert result.code == "FAULT_ENDPOINT_MISMATCH"


def test_confirmation_time_is_captured_before_final_external_revalidation(
    fault_env, monkeypatch: pytest.MonkeyPatch
):
    *_rest, client, request = fault_env

    def clock() -> str:
        client.events.append(("confirmed_at",))
        return "2026-08-08T02:03:04.000005Z"

    monkeypatch.setattr(fault_mod, "utc_now_rfc3339", clock)
    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.confirmed_at_utc == "2026-08-08T02:03:04.000005Z"
    assert client.events.index(("confirmed_at",)) < max(
        index for index, event in enumerate(client.events) if event[0] == "attach"
    )


def test_transition_away_from_halted_during_capture_fails_closed(fault_env):
    *_rest, client, request = fault_env
    original = client.read_registers

    async def transition(names: tuple[str, ...]):
        if client.register_reads == 1:
            client.state = "running"
        return await original(names)

    client.read_registers = transition
    result = asyncio.run(analyze_fault(request, client))
    assert result.code == "FAULT_STATE_CHANGED"
    assert dict(result.details) == {"state": "running"}


def test_symbolization_failure_keeps_raw_fault_evidence(fault_env):
    *_rest, client, request = fault_env
    client.memory[0x2000_0000] = _frame(pc=0x0800_0301, lr=0x0800_0305)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    document = result.data.to_dict()
    assert document["stackFrame"]["pc"] == {
        "value": 0x0800_0301,
        "rawHex": "0x08000301",
        "bitWidth": 32,
    }
    assert document["symbols"] == {
        "pc": {
            "status": "unavailable",
            "address": {"value": 0x0800_0301, "rawHex": "0x08000301", "bitWidth": 32},
        },
        "lr": {
            "status": "unavailable",
            "address": {"value": 0x0800_0305, "rawHex": "0x08000305", "bitWidth": 32},
        },
    }


def test_symbolization_rejects_ram_value_claimed_by_executable_symbol(fault_env):
    *_rest, client, _request = fault_env
    image = _mutate_symbol(
        fault_env[1], "main", value=0x2000_0201, shndx=3
    )
    request = _rebind_elf(fault_env, image)
    client.memory[0x2000_0000] = _frame(pc=0x2000_0201)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.to_dict()["symbols"]["pc"] == {
        "status": "unavailable",
        "address": {"value": 0x2000_0201, "rawHex": "0x20000201", "bitWidth": 32},
    }


@pytest.mark.parametrize("shndx", [0, 0xFFF1, 100])
def test_symbolization_rejects_undefined_absolute_and_invalid_section_indices(
    fault_env, shndx: int
):
    *_rest, client, _request = fault_env
    image = _mutate_symbol(fault_env[1], "main", shndx=shndx)
    request = _rebind_elf(fault_env, image)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.to_dict()["symbols"]["pc"]["status"] == "unavailable"


def test_symbolization_rejects_symbol_extent_outside_owning_section(fault_env):
    *_rest, client, _request = fault_env
    image = _mutate_symbol(fault_env[1], "main", value=0x0800_0135, size=0)
    request = _rebind_elf(fault_env, image)
    client.memory[0x2000_0000] = _frame(pc=0x0800_0135)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.to_dict()["symbols"]["pc"]["status"] == "unavailable"


def test_zero_size_function_resolves_only_at_its_owned_executable_start(fault_env):
    *_rest, client, _request = fault_env
    image = _mutate_symbol(fault_env[1], "main", size=0)
    request = _rebind_elf(fault_env, image)

    result = asyncio.run(analyze_fault(request, client))

    symbol = result.data.to_dict()["symbols"]["pc"]
    assert symbol["status"] == "resolved"
    assert symbol["name"] == "main"
    assert symbol["offset"] == 0


def test_duplicate_identical_symbols_are_ambiguous_not_collapsed(fault_env):
    *_rest, client, _request = fault_env
    main_offset, main = _symbol_entry(fault_env[1], "main")
    assert main_offset > 0
    image = _mutate_symbol(
        fault_env[1],
        "local_case_two",
        name_offset=main["name"],
        value=main["value"],
        size=main["size"],
        shndx=main["shndx"],
    )
    request = _rebind_elf(fault_env, image)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.to_dict()["symbols"]["pc"]["status"] == "unavailable"


@pytest.mark.parametrize("limit_name", ["_MAX_ELF_SECTIONS", "_MAX_ELF_SYMBOLS"])
def test_symbolization_fails_closed_when_elf_catalog_limit_is_exceeded(
    fault_env, monkeypatch: pytest.MonkeyPatch, limit_name: str
):
    *_rest, client, request = fault_env
    monkeypatch.setattr(fault_mod, limit_name, 1, raising=False)

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    assert result.data.to_dict()["symbols"]["pc"]["status"] == "unavailable"


def test_cortex_m4_fault_bits_include_hardfault_nmi_and_exclude_armv8_stkof(fault_env):
    *_rest, client, request = fault_env
    client.memory[SCB_BASE] = _status_bytes(
        shcsr=(1 << 2) | (1 << 5), cfsr=(1 << 20)
    )

    result = asyncio.run(analyze_fault(request, client))

    status = result.data.to_dict()["faultStatus"]
    assert status["shcsr"]["active"] == ["hardFaultActive", "nmiActive"]
    assert status["cfsr"]["active"] == []


def test_invalid_fault_address_bits_never_publish_scb_address_values(fault_env):
    *_rest, client, request = fault_env
    client.memory[SCB_BASE] = _status_bytes(cfsr=(1 << 1), mmfar=0xDEAD_BEEF, bfar=0xCAFE_BABE)

    result = asyncio.run(analyze_fault(request, client))

    status = result.data.to_dict()["faultStatus"]
    assert status["mmfar"] == {"valid": False, "address": None}
    assert status["bfar"] == {"valid": False, "address": None}


def test_alignment_padding_must_also_fit_readable_memory(fault_env):
    *_rest, client, request = fault_env
    client.core["msp"] = 0x2000_0FE0
    client.memory[0x2000_0FE0] = _frame(xpsr=0x2100_0200)

    result = asyncio.run(analyze_fault(request, client))

    assert result.code == "FAULT_STACK_OUTSIDE_READABLE_MEMORY"
    assert ("read_memory", 0x2000_0FE0, 32) in client.events


def test_non_exception_lr_keeps_register_and_status_evidence_without_guessing_frame(fault_env):
    *_rest, client, request = fault_env
    client.core["lr"] = 0x0800_0005

    result = asyncio.run(analyze_fault(request, client))

    assert result.ok is True
    document = result.data.to_dict()
    assert document["stackFrame"] is None
    assert document["registers"]["lr"] == {
        "value": 0x0800_0005,
        "rawHex": "0x08000005",
        "bitWidth": 32,
    }
    assert [event for event in client.events if event[0] == "read_memory"] == [
        ("read_memory", SCB_BASE, SCB_LENGTH)
    ]


def test_cancellation_propagates_without_starting_more_reads(fault_env):
    *_rest, client, request = fault_env

    async def cancelled(_names: tuple[str, ...]):
        raise asyncio.CancelledError

    client.read_registers = cancelled
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(analyze_fault(request, client))
    assert client.events == [("attach", "probe-123", "stm32f407vg")]


def test_request_validation_and_public_import_do_not_load_pyocd(fault_env):
    import sys

    _root, *_rest, client, request = fault_env
    wrong = asyncio.run(analyze_fault(object(), client))
    assert wrong.code == "FAULT_REQUEST_INVALID"
    with pytest.raises(TypeError):
        FaultAnalysisRequest(request.binding, project_root=Path("different"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        FaultAnalysisRequest(request.binding, address=0xDEADBEEF)  # type: ignore[call-arg]
    assert "pyocd" not in sys.modules
