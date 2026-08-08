from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from stm32_toolkit.debug import DebugFirmwareBinding, DebugReadReport

from .models import ObservationBinding, SampleValue, WatchItem
from .protocol import ProtocolResult, failure, success


_BLOCKING_CODES = {
    "MONITOR_FIRMWARE_CHANGED",
    "MONITOR_PROVENANCE_CHANGED",
    "MONITOR_PROBE_BUSY",
    "PROBE_ENDPOINT_UNAVAILABLE",
    "PROBE_LEASE_LOST",
    "SVD_SELECTION_REQUIRED",
}


@dataclass(frozen=True)
class ProbeReadOutcome:
    values: tuple[SampleValue, ...]
    blocked_code: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or not all(isinstance(value, SampleValue) for value in self.values):
            raise TypeError("probe read values must be an immutable tuple")
        if self.blocked_code is not None and self.values:
            raise ValueError("blocked probe reads cannot contain values")


def _blocked_code(code: object) -> str | None:
    if code == "MONITOR_FIRMWARE_CHANGED":
        return "MONITOR_FIRMWARE_CHANGED"
    if isinstance(code, str) and (
        code in _BLOCKING_CODES
        or code.startswith("PROBE_")
        or code.startswith("DWARF_")
        or code.startswith("SVD_")
        or "LEASE" in code
        or "ENDPOINT" in code
        or "PROVENANCE" in code
    ):
        return "MONITOR_PROVENANCE_CHANGED"
    return None


def _map_binding(observation: object, raw: object) -> ObservationBinding:
    if not isinstance(raw, DebugFirmwareBinding):
        raise ValueError("observation binding is invalid")
    catalog = getattr(observation, "catalog", None)
    dwarf_sha256 = getattr(catalog, "elf_sha256", None)
    svd = getattr(observation, "svd", None)
    svd_sha256 = None if svd is None else getattr(svd, "sha256", None)
    return ObservationBinding(
        workspace_id=raw.workspace_id,
        logical_project_id=raw.logical_project_id,
        session_id=raw.observation_session_id,
        probe_id=raw.probe_id,
        target_device=raw.target_device,
        physical_target=raw.debug_target,
        build_id=raw.build_id,
        elf_sha256=raw.elf_sha256,
        input_snapshot_sha256=raw.input_snapshot_sha256,
        git_head=raw.git_head,
        git_dirty=raw.git_dirty,
        flash_session_id=raw.flash_session_id,
        lease_id=raw.lease_id,
        dwarf_sha256=dwarf_sha256,
        svd_sha256=svd_sha256,
    )


class ProbeSession:
    """Non-owning typed adapter around one public Monitor observation session."""

    def __init__(self, observation: object) -> None:
        for name in ("binding", "catalog", "read_variables", "sample_registers", "revalidate"):
            if not hasattr(observation, name):
                raise TypeError("observation session is invalid")
        self._observation = observation
        self.binding = _map_binding(observation, observation.binding)

    async def _read_group(
        self,
        watches: tuple[WatchItem, ...],
        method_name: str,
    ) -> ProbeReadOutcome:
        if not watches:
            return ProbeReadOutcome(())
        selectors = tuple(watch.selector for watch in watches)
        try:
            result = await getattr(self._observation, method_name)(selectors)
        except asyncio.CancelledError:
            raise
        except Exception:
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation read failed")
        if getattr(result, "ok", None) is not True:
            code = _blocked_code(getattr(result, "code", None))
            if code is not None:
                return ProbeReadOutcome((), code, "Monitor observation changed")
            item_code = getattr(result, "code", None)
            if not isinstance(item_code, str) or not item_code:
                item_code = "MONITOR_PROVENANCE_CHANGED"
            return ProbeReadOutcome(
                tuple(
                    SampleValue(
                        watch,
                        "ERROR",
                        code=item_code,
                        definition={"kind": watch.kind, "selector": watch.selector},
                    )
                    for watch in watches
                )
            )
        report = getattr(result, "data", None)
        if not isinstance(report, DebugReadReport):
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation report is invalid")
        try:
            report_binding = _map_binding(self._observation, report.binding)
        except (TypeError, ValueError):
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation report is invalid")
        if report_binding != self.binding or tuple(item.expression for item in report.items) != selectors:
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation report changed")
        values: list[SampleValue] = []
        for watch, item in zip(watches, report.items):
            definition = {"kind": watch.kind, "selector": watch.selector}
            if item.status == "ok" and item.value is not None:
                values.append(SampleValue(watch, "OK", typed_value=item.value.to_dict(), definition=definition))
            else:
                values.append(SampleValue(watch, "ERROR", code=item.code or "MONITOR_PROVENANCE_CHANGED", definition=definition))
        return ProbeReadOutcome(tuple(values))

    async def read(self, watches: Iterable[WatchItem]) -> ProbeReadOutcome:
        items = tuple(watches)
        if not items or not all(isinstance(item, WatchItem) for item in items):
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor watch set is invalid")
        variables = tuple(item for item in items if item.kind == "variable")
        registers = tuple(item for item in items if item.kind == "register")
        variable_result = await self._read_group(variables, "read_variables")
        if variable_result.blocked_code is not None:
            return variable_result
        register_result = await self._read_group(registers, "sample_registers")
        if register_result.blocked_code is not None:
            return register_result
        by_watch = {
            (value.watch.kind, value.watch.selector): value
            for value in (*variable_result.values, *register_result.values)
        }
        try:
            ordered = tuple(by_watch[(item.kind, item.selector)] for item in items)
        except KeyError:
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation report is incomplete")
        return ProbeReadOutcome(ordered)

    async def revalidate(self) -> ProtocolResult[ObservationBinding]:
        operation = "sampling.revalidate"
        try:
            result = await self._observation.revalidate()
        except asyncio.CancelledError:
            raise
        except Exception:
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor observation changed")
        if getattr(result, "ok", None) is not True:
            code = _blocked_code(getattr(result, "code", None)) or "MONITOR_PROVENANCE_CHANGED"
            return failure(operation, code, "Monitor observation changed")
        try:
            current = _map_binding(self._observation, getattr(result, "data", None))
        except (TypeError, ValueError):
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor observation changed")
        if current != self.binding:
            firmware_fields = (
                "build_id", "elf_sha256", "input_snapshot_sha256", "git_head", "git_dirty", "flash_session_id",
            )
            code = (
                "MONITOR_FIRMWARE_CHANGED"
                if any(getattr(current, field) != getattr(self.binding, field) for field in firmware_fields)
                else "MONITOR_PROVENANCE_CHANGED"
            )
            return failure(operation, code, "Monitor observation changed")
        return success(operation, current)


__all__ = ["ProbeReadOutcome", "ProbeSession"]
