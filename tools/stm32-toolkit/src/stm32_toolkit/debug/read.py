"""Bounded typed reads derived exclusively from current DWARF or exact SVD."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.probe.client import ProbeClientError
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION
from stm32_toolkit.probe.protocol import MAX_BATCH_ITEMS, MAX_READ_BYTES
from stm32_toolkit.probe.flash import _load_fresh_firmware
from stm32_toolkit.probe.handoff import _load_flash_result, _validate_flash
from stm32_toolkit.result import OperationResult

from .dwarf import DwarfCatalog
from .model import (
    DebugFirmwareBinding,
    DebugReadItem,
    DebugReadReport,
    MemoryRegionBinding,
    TypedValue,
)
from .svd import SvdError, SvdRegister, SvdSelection
from .types import DwarfError, DwarfSelection, DwarfValue

_VARIABLE_OPERATION = "stm32_debug_read_variables"
_REGISTER_OPERATION = "stm32_debug_read_registers"
_TARGET_CANONICAL = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True)
class VariableReadRequest:
    binding: DebugFirmwareBinding
    catalog: object
    expressions: tuple[str, ...]


@dataclass(frozen=True)
class RegisterReadRequest:
    binding: DebugFirmwareBinding
    selection: SvdSelection
    paths: tuple[str, ...]
    acknowledge_access_risk: object = False


class _ReadFailure(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True)
class _Resolved:
    expression: str
    address: int
    size: int
    region: MemoryRegionBinding
    decode: Callable[[bytes], TypedValue]


def _fail(
    code: str, message: str, details: Mapping[str, object] | None = None
) -> _ReadFailure:
    return _ReadFailure(code, message, details)


def _items(value: object) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or not 1 <= len(value) <= MAX_BATCH_ITEMS
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 512
            or "\x00" in item
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
    return value


def _binding(value: object) -> DebugFirmwareBinding:
    if type(value) is not DebugFirmwareBinding:
        raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
    return value


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
        or re.fullmatch(r"[0-9a-f]{64}", token) is None
        or getattr(endpoint, "workspace_id", None) != binding.workspace_id
        or getattr(endpoint, "session_id", None) != binding.observation_session_id
        or getattr(endpoint, "lease_id", None) != binding.lease_id
        or getattr(endpoint, "probe_id", None) != binding.probe_id
        or level_value != OperationLevel.OBSERVE.value
    ):
        raise _fail(
            "DEBUG_ENDPOINT_MISMATCH",
            "Probe client endpoint does not match the debug binding",
        )


def _canonical_target(value: str) -> str:
    return _TARGET_CANONICAL.sub("", value.casefold())


def _current_firmware(binding: DebugFirmwareBinding) -> None:
    """Reprove the complete disk/Git/flash chain captured by the binding."""

    try:
        firmware = _load_fresh_firmware(binding.project_root)
        identity = firmware.identity
        regions = tuple(
            MemoryRegionBinding(
                region.name, region.origin, region.length, region.attributes
            )
            for region in firmware.model.memory.regions
            if "r" in region.attributes
        )
        if (
            str(firmware.model.logical_project_id) != binding.logical_project_id
            or firmware.model.target.device != binding.target_device
            or firmware.model.debug.target != binding.debug_target
            or str(identity.get("buildId")) != binding.build_id
            or str(identity.get("elfSha256")) != binding.elf_sha256
            or str(identity.get("elfPath")) != binding.elf_path
            or len(firmware.elf_data) != binding.elf_size
            or str(identity.get("inputSnapshotSha256"))
            != binding.input_snapshot_sha256
            or str(identity.get("gitHead")) != binding.git_head
            or type(identity.get("gitDirty")) is not bool
            or identity.get("gitDirty") != binding.git_dirty
            or regions != binding.memory_regions
        ):
            raise ValueError("identity changed")
        flash = _load_flash_result(binding.project_root)
        if flash.get("sessionId") != binding.flash_session_id:
            raise ValueError("flash session changed")
        _validate_flash(
            flash,
            firmware,
            probe=binding.probe_id,
            workspace=binding.workspace_id,
            session=binding.flash_session_id,
            target=binding.debug_target,
        )
    except Exception:
        raise _fail(
            "DEBUG_FIRMWARE_CHANGED",
            "Current firmware evidence no longer matches the debug binding",
        ) from None


async def _attach(binding: DebugFirmwareBinding, client: object) -> None:
    try:
        attachment = await client.attach(binding.probe_id, binding.debug_target)
    except asyncio.CancelledError:
        raise
    except ProbeClientError as error:
        if error.code == "PROBE_IDENTITY_MISMATCH":
            raise _fail(
                "DEBUG_TARGET_MISMATCH",
                "Connected target does not match the debug binding",
            ) from None
        raise _fail(error.code, error.message, error.details) from None
    resolved = getattr(attachment, "resolved_part_number", None)
    if (
        getattr(attachment, "probe_id", None) != binding.probe_id
        or getattr(attachment, "requested_target", None) != binding.debug_target
        or not isinstance(resolved, str)
        or _canonical_target(resolved) != _canonical_target(binding.debug_target)
        or getattr(attachment, "core_count", None) != 1
    ):
        raise _fail("DEBUG_TARGET_MISMATCH", "Connected target does not match the debug binding")


async def _guard(
    binding: DebugFirmwareBinding,
    client: object,
    revalidate_source: Callable[[], None],
) -> None:
    _endpoint(binding, client)
    _current_firmware(binding)
    revalidate_source()
    try:
        await _attach(binding, client)
    except asyncio.CancelledError:
        raise
    except _ReadFailure:
        raise
    except Exception:
        raise _fail("DEBUG_INTERNAL_ERROR", "Debug read failed") from None
    _endpoint(binding, client)


async def _memory_read(
    binding: DebugFirmwareBinding,
    client: object,
    revalidate_source: Callable[[], None],
    address: int,
    size: int,
) -> bytes:
    await _guard(binding, client, revalidate_source)
    try:
        data = await client.read_memory(address, size)
    except asyncio.CancelledError:
        raise
    except Exception:
        await _guard(binding, client, revalidate_source)
        raise
    await _guard(binding, client, revalidate_source)
    return data


def _region(
    binding: DebugFirmwareBinding,
    address: object,
    size: object,
    *,
    svd: bool = False,
) -> MemoryRegionBinding:
    if (
        type(address) is not int
        or type(size) is not int
        or address < 0
        or size < 1
        or size > MAX_READ_BYTES
        or address + size > 0x1_0000_0000
    ):
        raise _fail(
            "DEBUG_ADDRESS_OUTSIDE_READABLE_MEMORY",
            "Typed location is outside readable project memory",
        )
    readable_regions = binding.svd_readable_regions if svd else binding.memory_regions
    matches = tuple(
        item
        for item in readable_regions
        if "r" in item.attributes
        and address >= item.origin
        and address + size <= item.origin + item.length
    )
    if len(matches) != 1:
        raise _fail(
            "DEBUG_ADDRESS_OUTSIDE_READABLE_MEMORY",
            "Typed location is outside readable project memory",
        )
    return matches[0]


def _typed_value(expression: str, decoded: DwarfValue) -> TypedValue:
    value: object = decoded.value
    if decoded.kind == "enum":
        value = {"value": decoded.value, "name": decoded.enum_name}
    return TypedValue(
        expression,
        decoded.type_name,
        value,
        decoded.raw_hex,
        decoded.bit_width,
    )


def _revalidate_catalog(
    catalog: DwarfCatalog, binding: DebugFirmwareBinding
) -> None:
    try:
        catalog.revalidate(binding)
    except DwarfError as error:
        raise _fail(error.code, "DWARF catalog provenance is invalid") from None
    except Exception:
        raise _fail(
            "DWARF_PROVENANCE_MISMATCH",
            "DWARF catalog provenance is invalid",
        ) from None


def _revalidate_selection(
    selection: SvdSelection, binding: DebugFirmwareBinding
) -> None:
    try:
        selection.revalidate(binding, binding.project_root)
    except SvdError as error:
        raise _fail(error.code, "SVD selection provenance is invalid") from None
    except Exception:
        raise _fail(
            "SVD_PROVENANCE_MISMATCH", "SVD selection provenance is invalid"
        ) from None


def _variable(
    binding: DebugFirmwareBinding, catalog: DwarfCatalog, expression: str
) -> _Resolved:
    try:
        selected = catalog.lookup(expression)
    except DwarfError as error:
        raise _fail(error.code, "DWARF variable cannot be read") from None
    except Exception:
        raise _fail("DWARF_LOOKUP_FAILED", "DWARF variable cannot be read") from None
    region = _region(binding, selected.address, selected.byte_size)

    def decode(data: bytes) -> TypedValue:
        try:
            return _typed_value(expression, selected.decode(data))
        except DwarfError as error:
            raise _fail(error.code, "DWARF variable cannot be decoded") from None
        except Exception:
            raise _fail("DWARF_DECODE_FAILED", "DWARF variable cannot be decoded") from None

    return _Resolved(expression, selected.address, selected.byte_size, region, decode)


def _register(
    binding: DebugFirmwareBinding,
    selection: SvdSelection,
    path: str,
    acknowledge: object,
    *,
    single: bool,
) -> _Resolved:
    try:
        register = selection.register(path)
        register.authorize_read(acknowledge if single else False, sampling=False)
    except SvdError as error:
        raise _fail(error.code, "SVD register cannot be read") from None
    region = _region(binding, register.address, register.size_bytes, svd=True)

    def decode(data: bytes) -> TypedValue:
        value = int.from_bytes(data, "little", signed=False)
        bits = register.size_bytes * 8
        safe_value: object = str(value) if bits > 53 else value
        return TypedValue(
            path,
            f"uint{bits}_register",
            safe_value,
            f"0x{value:0{register.size_bytes * 2}x}",
            bits,
        )

    return _Resolved(path, register.address, register.size_bytes, region, decode)


def _groups(items: list[tuple[int, _Resolved]]) -> list[list[tuple[int, _Resolved]]]:
    ordered = sorted(items, key=lambda entry: (entry[1].address, entry[0]))
    groups: list[list[tuple[int, _Resolved]]] = []
    for entry in ordered:
        if not groups:
            groups.append([entry])
            continue
        previous = groups[-1][-1][1]
        start = groups[-1][0][1].address
        current = entry[1]
        if (
            current.region == previous.region
            and current.address == previous.address + previous.size
            and current.address + current.size - start <= MAX_READ_BYTES
        ):
            groups[-1].append(entry)
        else:
            groups.append([entry])
    return groups


async def _one(
    binding: DebugFirmwareBinding,
    client: object,
    revalidate_source: Callable[[], None],
    item: _Resolved,
) -> DebugReadItem:
    return await _read_one(
        lambda address, size: _memory_read(
            binding, client, revalidate_source, address, size
        ),
        item,
    )


async def _group(
    binding: DebugFirmwareBinding,
    client: object,
    revalidate_source: Callable[[], None],
    group: list[tuple[int, _Resolved]],
) -> list[tuple[int, DebugReadItem]]:
    return await _read_group(
        lambda address, size: _memory_read(
            binding, client, revalidate_source, address, size
        ),
        group,
    )


async def _read_one(
    raw_read: Callable[[int, int], Awaitable[bytes]],
    item: _Resolved,
) -> DebugReadItem:
    try:
        data = await raw_read(item.address, item.size)
    except asyncio.CancelledError:
        raise
    except _ReadFailure:
        raise
    except Exception:
        return DebugReadItem(item.expression, "error", code="DEBUG_READ_UNAVAILABLE")
    if not isinstance(data, bytes) or len(data) != item.size:
        return DebugReadItem(item.expression, "error", code="DEBUG_PARTIAL_READ")
    try:
        return DebugReadItem(item.expression, "ok", value=item.decode(data))
    except _ReadFailure as error:
        return DebugReadItem(item.expression, "error", code=error.code)


async def _read_group(
    raw_read: Callable[[int, int], Awaitable[bytes]],
    group: list[tuple[int, _Resolved]],
) -> list[tuple[int, DebugReadItem]]:
    if len(group) == 1:
        index, item = group[0]
        return [(index, await _read_one(raw_read, item))]
    start = group[0][1].address
    length = group[-1][1].address + group[-1][1].size - start
    try:
        data = await raw_read(start, length)
        if not isinstance(data, bytes) or len(data) != length:
            raise ValueError("partial")
    except asyncio.CancelledError:
        raise
    except _ReadFailure:
        raise
    except Exception:
        results: list[tuple[int, DebugReadItem]] = []
        for index, item in group:
            results.append((index, await _read_one(raw_read, item)))
        return results
    results = []
    for index, item in group:
        offset = item.address - start
        try:
            value = item.decode(data[offset : offset + item.size])
            results.append((index, DebugReadItem(item.expression, "ok", value=value)))
        except _ReadFailure as error:
            results.append((index, DebugReadItem(item.expression, "error", code=error.code)))
    return results


def _resolve_items(
    expressions: tuple[str, ...], resolver: Callable[[str], _Resolved]
) -> tuple[list[tuple[int, _Resolved]], list[DebugReadItem | None]]:
    resolved: list[tuple[int, _Resolved]] = []
    output: list[DebugReadItem | None] = [None] * len(expressions)
    for index, expression in enumerate(expressions):
        try:
            resolved.append((index, resolver(expression)))
        except _ReadFailure as error:
            output[index] = DebugReadItem(expression, "error", code=error.code)
    return resolved, output


async def _execute_prepared(
    operation: str,
    binding: DebugFirmwareBinding,
    expressions: tuple[str, ...],
    prepared_groups: tuple[list[tuple[int, _Resolved]], ...],
    output: list[DebugReadItem | None],
    raw_read: Callable[[int, int], Awaitable[bytes]],
) -> OperationResult[tuple[DebugReadItem, ...]]:
    """Execute resolved groups with a caller-owned guard boundary.

    Public reads continue to pass a guarded reader. Monitor's private mixed
    batch passes a raw reader and owns one guard before and after all groups.
    """

    try:
        for prepared in prepared_groups:
            for group in _groups(prepared):
                for index, result in await _read_group(raw_read, group):
                    output[index] = result
        items = tuple(item for item in output if item is not None)
        return OperationResult.success(operation, items)
    except asyncio.CancelledError:
        raise
    except _ReadFailure as error:
        return OperationResult.failure(
            operation, error.code, error.message, error.details
        )
    except Exception:
        return OperationResult.failure(
            operation, "DEBUG_INTERNAL_ERROR", "Debug read failed", {}
        )


async def _execute(
    operation: str,
    binding: DebugFirmwareBinding,
    expressions: tuple[str, ...],
    resolver: Callable[[str], _Resolved],
    revalidate_source: Callable[[], None],
    client: object,
) -> OperationResult[DebugReadReport]:
    try:
        _endpoint(binding, client)
        _current_firmware(binding)
        revalidate_source()
        resolved, output = _resolve_items(expressions, resolver)
        if resolved:
            for group in _groups(resolved):
                for index, result in await _group(
                    binding, client, revalidate_source, group
                ):
                    output[index] = result
            _endpoint(binding, client)
            _current_firmware(binding)
            revalidate_source()
        items = tuple(item for item in output if item is not None)
        return OperationResult.success(
            operation,
            DebugReadReport(binding, items, utc_now_rfc3339()),
        )
    except asyncio.CancelledError:
        raise
    except _ReadFailure as error:
        return OperationResult.failure(
            operation, error.code, error.message, error.details
        )
    except Exception:
        return OperationResult.failure(
            operation, "DEBUG_INTERNAL_ERROR", "Debug read failed", {}
        )


async def read_variables(
    request: object, client: object
) -> OperationResult[DebugReadReport]:
    """Read bounded scalar locations resolved only by a DWARF catalog."""

    try:
        if not isinstance(request, VariableReadRequest):
            raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
        binding = _binding(request.binding)
        expressions = _items(request.expressions)
        if type(request.catalog) is not DwarfCatalog:
            raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
    except _ReadFailure as error:
        return OperationResult.failure(
            _VARIABLE_OPERATION, error.code, error.message, error.details
        )
    return await _execute(
        _VARIABLE_OPERATION,
        binding,
        expressions,
        lambda expression: _variable(binding, request.catalog, expression),
        lambda: _revalidate_catalog(request.catalog, binding),
        client,
    )


async def read_registers(
    request: object, client: object
) -> OperationResult[DebugReadReport]:
    """Read bounded registers resolved only by one exact SVD selection."""

    try:
        if not isinstance(request, RegisterReadRequest):
            raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
        binding = _binding(request.binding)
        paths = _items(request.paths)
        if type(request.selection) is not SvdSelection or type(
            request.acknowledge_access_risk
        ) is not bool:
            raise _fail("DEBUG_REQUEST_INVALID", "Debug read request is invalid")
    except _ReadFailure as error:
        return OperationResult.failure(
            _REGISTER_OPERATION, error.code, error.message, error.details
        )
    return await _execute(
        _REGISTER_OPERATION,
        binding,
        paths,
        lambda path: _register(
            binding,
            request.selection,
            path,
            request.acknowledge_access_risk,
            single=len(paths) == 1,
        ),
        lambda: _revalidate_selection(request.selection, binding),
        client,
    )


__all__ = [
    "RegisterReadRequest",
    "VariableReadRequest",
    "read_registers",
    "read_variables",
]
