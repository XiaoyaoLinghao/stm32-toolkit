"""Read-only Cortex-M Fault evidence bound to one current firmware image."""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.probe.flash import _load_fresh_firmware
from stm32_toolkit.probe.handoff import _validate_attachment
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION
from stm32_toolkit.result import OperationResult

from .model import DebugFirmwareBinding, FaultReport

_OPERATION = "stm32_fault_analyze"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CORE_REGISTERS = (
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
_CORE_REGISTER_SET = frozenset(_CORE_REGISTERS)
_SCB_BASE = 0xE000_ED24
_SCB_LENGTH = 24
_VALID_EXC_RETURN = frozenset(
    (0xFFFF_FFE1, 0xFFFF_FFE9, 0xFFFF_FFED, 0xFFFF_FFF1, 0xFFFF_FFF9, 0xFFFF_FFFD)
)


@dataclass(frozen=True)
class FaultAnalysisRequest:
    """Inputs that select an already-proven debug binding, never an address."""

    binding: DebugFirmwareBinding


class _FaultFailure(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _fail(code: str, message: str, **details: object) -> _FaultFailure:
    return _FaultFailure(code, message, details)


def _request(value: object) -> tuple[FaultAnalysisRequest, Path]:
    if (
        not isinstance(value, FaultAnalysisRequest)
        or not isinstance(value.binding, DebugFirmwareBinding)
    ):
        raise _fail("FAULT_REQUEST_INVALID", "Fault analysis request is invalid")
    project_root = value.binding.project_root
    if not isinstance(project_root, Path):
        raise _fail("FAULT_REQUEST_INVALID", "Fault analysis request is invalid")
    try:
        lexical = project_root.expanduser().absolute()
        root = project_root.expanduser().resolve(strict=True)
        metadata = root.stat()
    except (OSError, RuntimeError):
        raise _fail("FAULT_REQUEST_INVALID", "Fault analysis request is invalid") from None
    if lexical != root or not stat.S_ISDIR(metadata.st_mode):
        raise _fail(
            "FAULT_REQUEST_INVALID",
            "Fault analysis request is invalid",
            rule="canonicalProjectRoot",
        )
    return value, root


def _endpoint(binding: DebugFirmwareBinding, client: object) -> None:
    endpoint = getattr(client, "endpoint", None)
    level = getattr(endpoint, "operation_level", None)
    level_value = getattr(level, "value", level)
    token = getattr(endpoint, "token", None)
    port = getattr(endpoint, "port", None)
    if (
        endpoint is None
        or getattr(endpoint, "protocol", None) != PROBE_PROTOCOL_VERSION
        or getattr(endpoint, "toolkit_version", None) != __version__
        or getattr(endpoint, "host", None) not in {"127.0.0.1", "::1"}
        or type(port) is not int
        or not 1 <= port <= 65_535
        or not isinstance(token, str)
        or _SHA256.fullmatch(token) is None
        or getattr(endpoint, "workspace_id", None) != binding.workspace_id
        or getattr(endpoint, "session_id", None) != binding.observation_session_id
        or getattr(endpoint, "lease_id", None) != binding.lease_id
        or getattr(endpoint, "probe_id", None) != binding.probe_id
        or level_value != OperationLevel.OBSERVE.value
    ):
        raise _fail(
            "FAULT_ENDPOINT_MISMATCH",
            "Probe client endpoint does not match the Fault binding",
        )


def _current_firmware(root: Path, binding: DebugFirmwareBinding) -> bytes:
    try:
        current = _load_fresh_firmware(root)
        identity = current.identity
        image = current.elf_data
        if not isinstance(image, bytes):
            raise ValueError("ELF bytes are invalid")
        expected = {
            "buildId": binding.build_id,
            "elfSha256": binding.elf_sha256,
            "elfSize": binding.elf_size,
            "inputSnapshotSha256": binding.input_snapshot_sha256,
            "gitHead": binding.git_head,
            "gitDirty": binding.git_dirty,
            "logicalProjectId": binding.logical_project_id,
            "targetDevice": binding.target_device,
        }
        if (
            any(identity.get(name) != value for name, value in expected.items())
            or str(current.model.logical_project_id) != binding.logical_project_id
            or current.model.target.device != binding.target_device
            or current.model.debug.target != binding.debug_target
            or current.elf_path != binding.elf_path
            or len(image) != binding.elf_size
            or hashlib.sha256(image).hexdigest() != binding.elf_sha256
        ):
            raise ValueError("firmware binding changed")
        return image
    except asyncio.CancelledError:
        raise
    except Exception:
        raise _fail(
            "FAULT_FIRMWARE_CHANGED",
            "Current firmware no longer matches the Fault binding",
        ) from None


async def _attachment(
    binding: DebugFirmwareBinding, client: object, *, final: bool = False
) -> None:
    try:
        attachment = await client.attach(binding.probe_id, binding.debug_target)
        _validate_attachment(attachment, binding.probe_id, binding.debug_target)
    except asyncio.CancelledError:
        raise
    except Exception:
        raise _fail(
            "FAULT_TARGET_CHANGED" if final else "FAULT_TARGET_MISMATCH",
            "Connected target does not match the Fault binding",
        ) from None


def _hex32(value: int) -> str:
    return f"0x{value:08x}"


def _word32(value: int) -> dict[str, object]:
    return {"value": value, "rawHex": _hex32(value), "bitWidth": 32}


def _validate_registers(values: object) -> dict[str, int]:
    if not isinstance(values, Mapping) or set(values) != _CORE_REGISTER_SET:
        raise _fail(
            "FAULT_REGISTER_UNAVAILABLE", "Required core registers are unavailable"
        )
    result: dict[str, int] = {}
    for name in _CORE_REGISTERS:
        value = values[name]
        if type(value) is not int or not 0 <= value <= 0xFFFF_FFFF:
            raise _fail(
                "FAULT_REGISTER_UNAVAILABLE",
                "Required core registers are unavailable",
            )
        result[name] = value
    return result


def _state_detail(error: BaseException) -> str | None:
    details = getattr(error, "details", None)
    state = details.get("state") if isinstance(details, Mapping) else None
    return state if isinstance(state, str) and state else None


async def _read_registers(client: object, *, final: bool = False) -> dict[str, int]:
    try:
        values = await client.read_registers(_CORE_REGISTERS)
        return _validate_registers(values)
    except asyncio.CancelledError:
        raise
    except _FaultFailure:
        raise
    except Exception as error:
        state = _state_detail(error)
        if state is not None:
            raise _fail(
                "FAULT_STATE_CHANGED" if final else "FAULT_TARGET_NOT_HALTED",
                "Target must remain already halted during Fault analysis",
                state=state,
            ) from None
        raise _fail(
            "FAULT_REGISTER_UNAVAILABLE", "Required core registers are unavailable"
        ) from None


async def _read_exact(
    client: object, address: int, length: int, code: str, message: str
) -> bytes:
    try:
        data = await client.read_memory(address, length)
    except asyncio.CancelledError:
        raise
    except Exception:
        raise _fail(code, message) from None
    if not isinstance(data, bytes) or len(data) != length:
        raise _fail(code, message)
    return data


def _active(value: int, fields: tuple[tuple[int, str], ...]) -> list[str]:
    return [name for bit, name in fields if value & (1 << bit)]


def _decode_fault_status(data: bytes) -> dict[str, object]:
    shcsr, cfsr, hfsr, dfsr, mmfar, bfar = (
        int.from_bytes(data[offset : offset + 4], "little")
        for offset in range(0, _SCB_LENGTH, 4)
    )
    return {
        "shcsr": {
            "value": shcsr,
            "rawHex": _hex32(shcsr),
            "bitWidth": 32,
            "active": _active(
                shcsr,
                (
                    (0, "memFaultActive"),
                    (1, "busFaultActive"),
                    (3, "usageFaultActive"),
                    (7, "svCallActive"),
                    (8, "monitorActive"),
                    (10, "pendSvActive"),
                    (11, "sysTickActive"),
                    (12, "usageFaultPending"),
                    (13, "memFaultPending"),
                    (14, "busFaultPending"),
                    (15, "svCallPending"),
                    (16, "memFaultEnabled"),
                    (17, "busFaultEnabled"),
                    (18, "usageFaultEnabled"),
                ),
            ),
        },
        "cfsr": {
            "value": cfsr,
            "rawHex": _hex32(cfsr),
            "bitWidth": 32,
            "active": _active(
                cfsr,
                (
                    (0, "iaccviol"),
                    (1, "daccviol"),
                    (3, "munstkerr"),
                    (4, "mstkerr"),
                    (5, "mlsperr"),
                    (7, "mmarvalid"),
                    (8, "ibuserr"),
                    (9, "preciserr"),
                    (10, "impreciserr"),
                    (11, "unstkerr"),
                    (12, "stkerr"),
                    (13, "lsperr"),
                    (15, "bfarvalid"),
                    (16, "undefinstr"),
                    (17, "invstate"),
                    (18, "invpc"),
                    (19, "nocp"),
                    (20, "stkof"),
                    (24, "unaligned"),
                    (25, "divbyzero"),
                ),
            ),
        },
        "hfsr": {
            "value": hfsr,
            "rawHex": _hex32(hfsr),
            "bitWidth": 32,
            "active": _active(
                hfsr, ((1, "vecttbl"), (30, "forced"), (31, "debugEvt"))
            ),
        },
        "dfsr": {
            "value": dfsr,
            "rawHex": _hex32(dfsr),
            "bitWidth": 32,
            "active": _active(
                dfsr,
                (
                    (0, "halted"),
                    (1, "bkpt"),
                    (2, "dwtTrap"),
                    (3, "vCatch"),
                    (4, "external"),
                ),
            ),
        },
        "mmfar": {
            "valid": bool(cfsr & (1 << 7)),
            "address": _word32(mmfar) if cfsr & (1 << 7) else None,
        },
        "bfar": {
            "valid": bool(cfsr & (1 << 15)),
            "address": _word32(bfar) if cfsr & (1 << 15) else None,
        },
    }


def _readable(binding: DebugFirmwareBinding, start: int, length: int) -> bool:
    if type(start) is not int or type(length) is not int or start < 0 or length < 1:
        return False
    end = start + length
    if end > 0x1_0000_0000:
        return False
    return any(
        "r" in region.attributes
        and start >= region.origin
        and end <= region.origin + region.length
        for region in binding.memory_regions
    )


async def _stack_frame(
    client: object, binding: DebugFirmwareBinding, registers: Mapping[str, int]
) -> dict[str, object] | None:
    exc_return = registers["lr"]
    if exc_return not in _VALID_EXC_RETURN:
        return None
    stack_source = "psp" if exc_return & (1 << 2) else "msp"
    extended = not bool(exc_return & (1 << 4))
    stack_pointer = registers[stack_source]
    basic_offset = 72 if extended else 0
    basic_address = stack_pointer + basic_offset
    if (
        stack_pointer & 0x3
        or basic_address > 0xFFFF_FFFF
        or not _readable(binding, basic_address, 32)
    ):
        raise _fail(
            "FAULT_STACK_OUTSIDE_READABLE_MEMORY",
            "Fault stack frame is outside project-readable memory",
        )
    data = await _read_exact(
        client,
        basic_address,
        32,
        "FAULT_STACK_UNAVAILABLE",
        "Fault stack frame is unavailable",
    )
    words = [int.from_bytes(data[index : index + 4], "little") for index in range(0, 32, 4)]
    alignment = 4 if words[7] & (1 << 9) else 0
    total = basic_offset + 32 + alignment
    if not _readable(binding, stack_pointer, total):
        raise _fail(
            "FAULT_STACK_OUTSIDE_READABLE_MEMORY",
            "Fault stack frame is outside project-readable memory",
        )
    frame: dict[str, object] = {
        "stackSource": stack_source,
        "frameKind": "extended" if extended else "basic",
        "stackPointer": _word32(stack_pointer),
        "basicFrameAddress": _word32(basic_address),
        "alignmentPaddingBytes": alignment,
        "totalFrameBytes": total,
    }
    for name, value in zip(("r0", "r1", "r2", "r3", "r12", "lr", "pc", "xpsr"), words):
        frame[name] = _word32(value)
    return frame


def _symbol_candidates(image: bytes) -> tuple[tuple[str, int, int], ...]:
    try:
        elf = ELFFile(io.BytesIO(image))
        candidates: list[tuple[str, int, int]] = []
        for section in elf.iter_sections():
            if section.header["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
                continue
            for symbol in section.iter_symbols():
                if symbol["st_info"]["type"] != "STT_FUNC" or not symbol.name:
                    continue
                start = int(symbol["st_value"]) & ~1
                size = int(symbol["st_size"])
                if not 0 <= start <= 0xFFFF_FFFF or not 0 <= size <= 0x1_0000_0000 - start:
                    continue
                candidates.append((symbol.name[:256], start, size))
        return tuple(candidates)
    except (ELFError, KeyError, TypeError, ValueError, IndexError, OverflowError):
        return ()


def _symbolize_one(
    address: int, candidates: tuple[tuple[str, int, int], ...]
) -> dict[str, object]:
    normalized = address & ~1
    matches = [
        (name, start, size)
        for name, start, size in candidates
        if (size > 0 and start <= normalized < start + size)
        or (size == 0 and normalized == start)
    ]
    unique = {(name, start, size) for name, start, size in matches}
    if len(unique) != 1:
        return {"status": "unavailable", "address": _word32(address)}
    name, start, _size = next(iter(unique))
    return {
        "status": "resolved",
        "address": _word32(address),
        "name": name,
        "symbolAddress": _word32(start),
        "offset": normalized - start,
    }


def _symbols(
    image: bytes,
    registers: Mapping[str, int],
    stack_frame: Mapping[str, object] | None,
) -> dict[str, object]:
    if stack_frame is None:
        addresses = {"pc": registers["pc"], "lr": registers["lr"]}
    else:
        addresses = {
            "pc": int(stack_frame["pc"]["value"]),
            "lr": int(stack_frame["lr"]["value"]),
        }
    candidates = _symbol_candidates(image)
    return {name: _symbolize_one(address, candidates) for name, address in addresses.items()}


async def analyze_fault(
    request: object, client: object
) -> OperationResult[FaultReport]:
    """Capture Fault evidence without target control, target writes, or project writes."""

    try:
        typed, root = _request(request)
        binding = typed.binding
        _endpoint(binding, client)
        image = _current_firmware(root, binding)
        await _attachment(binding, client)
        registers = await _read_registers(client)
        status_data = await _read_exact(
            client,
            _SCB_BASE,
            _SCB_LENGTH,
            "FAULT_STATUS_UNAVAILABLE",
            "Cortex-M Fault status registers are unavailable",
        )
        fault_status = _decode_fault_status(status_data)
        stack_frame = await _stack_frame(client, binding, registers)
        symbols = _symbols(image, registers, stack_frame)
        await _attachment(binding, client, final=True)
        final_registers = await _read_registers(client, final=True)
        if final_registers != registers:
            raise _fail(
                "FAULT_STATE_CHANGED",
                "Target state changed during Fault analysis",
            )
        _endpoint(binding, client)
        _current_firmware(root, binding)
        confirmed_at = utc_now_rfc3339()
        report = FaultReport(
            binding=binding,
            target_state="halted",
            registers={name: _word32(value) for name, value in registers.items()},
            fault_status=fault_status,
            stack_frame=stack_frame,
            symbols=symbols,
            confirmed_at_utc=confirmed_at,
            audit_operation="fault.analyze",
        )
        return OperationResult.success(_OPERATION, report)
    except asyncio.CancelledError:
        raise
    except _FaultFailure as error:
        return OperationResult.failure(
            _OPERATION, error.code, error.message, error.details
        )
    except Exception:
        return OperationResult.failure(
            _OPERATION,
            "FAULT_INTERNAL_ERROR",
            "Fault analysis failed",
            {},
        )


__all__ = ["FaultAnalysisRequest", "analyze_fault"]
