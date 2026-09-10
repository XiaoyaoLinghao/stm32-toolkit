from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from stm32_toolkit.debug import DebugFirmwareBinding, DebugReadReport
from stm32_toolkit.debug.types import CatalogPage

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


def _catalog_code(code: object) -> str:
    if isinstance(code, str) and code.endswith(
        ("QUERY_INVALID", "CURSOR_INVALID", "LIMIT_INVALID")
    ):
        return "MONITOR_REQUEST_INVALID"
    return "MONITOR_PROVENANCE_CHANGED"


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
        for name in (
            "binding",
            "catalog",
            "_read_batch",
            "revalidate",
        ):
            if not hasattr(observation, name):
                raise TypeError("observation session is invalid")
        self._observation = observation
        self.binding = _map_binding(observation, observation.binding)
        self._read_plan: object | None = None
        self._plan_watches: tuple[WatchItem, ...] = ()
        self._plan_report_watches: tuple[WatchItem, ...] = ()
        self._admission_token: object | None = None

    async def _list_catalog(
        self, method_name: str, query: str, cursor: str | None, limit: int
    ) -> ProtocolResult[object]:
        operation = "catalog.variables" if method_name == "list_variables" else "catalog.registers"
        try:
            result = await getattr(self._observation, method_name)(query, cursor, limit)
        except asyncio.CancelledError:
            raise
        except Exception:
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor catalog changed")
        if getattr(result, "ok", None) is not True:
            code = _catalog_code(getattr(result, "code", None))
            return failure(operation, code, "Monitor catalog request failed")
        page = getattr(result, "data", None)
        if type(page) is not CatalogPage:
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor catalog changed")
        return success(operation, page.to_dict())

    async def list_variables(
        self, query: str, cursor: str | None, limit: int
    ) -> ProtocolResult[object]:
        return await self._list_catalog("list_variables", query, cursor, limit)

    async def list_registers(
        self, query: str, cursor: str | None, limit: int
    ) -> ProtocolResult[object]:
        return await self._list_catalog("list_registers", query, cursor, limit)

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
        return self._map_read_result(watches, selectors, result)

    def _map_read_result(
        self,
        watches: tuple[WatchItem, ...],
        selectors: tuple[str, ...],
        result: object,
    ) -> ProbeReadOutcome:
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

    async def _read_mixed_batch(
        self, items: tuple[WatchItem, ...]
    ) -> ProbeReadOutcome:
        variables = tuple(item for item in items if item.kind == "variable")
        registers = tuple(item for item in items if item.kind == "register")
        report_watches = variables + registers
        selectors = tuple(item.selector for item in report_watches)
        try:
            result = await self._observation._read_batch(
                tuple(item.selector for item in variables),
                tuple(item.selector for item in registers),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return ProbeReadOutcome(
                (), "MONITOR_PROVENANCE_CHANGED", "Monitor observation read failed"
            )
        return self._map_read_result(report_watches, selectors, result)

    def invalidate_read_plan(self) -> None:
        self._read_plan = None
        self._plan_watches = ()
        self._plan_report_watches = ()
        self._admission_token = None
        method = getattr(self._observation, "_invalidate_read_plan", None)
        if callable(method):
            method()

    async def prepare_read_plan(
        self, watches: Iterable[WatchItem]
    ) -> ProtocolResult[dict[str, object]]:
        operation = "sampling.prepare"
        items = tuple(watches)
        if (
            not items
            or not all(type(item) is WatchItem for item in items)
            or len(set(items)) != len(items)
        ):
            self.invalidate_read_plan()
            return failure(operation, "MONITOR_REQUEST_INVALID", "Monitor watch set is invalid")
        variables = tuple(item for item in items if item.kind == "variable")
        registers = tuple(item for item in items if item.kind == "register")
        report_watches = variables + registers
        self._read_plan = None
        self._plan_watches = ()
        self._plan_report_watches = ()
        admission_token = self._admission_token

        def invalidate_failed_prepare() -> None:
            if self._read_plan is None and self._admission_token is admission_token:
                self.invalidate_read_plan()

        if admission_token is None:
            invalidate_failed_prepare()
            return failure(
                operation,
                "MONITOR_PROVENANCE_CHANGED",
                "Monitor read plan could not be prepared",
            )
        try:
            result = await self._observation._prepare_read_plan(
                tuple(item.selector for item in variables),
                tuple(item.selector for item in registers),
                admission_token=admission_token,
            )
        except asyncio.CancelledError:
            invalidate_failed_prepare()
            raise
        except Exception:
            invalidate_failed_prepare()
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor read plan could not be prepared")
        if getattr(result, "ok", None) is not True:
            invalidate_failed_prepare()
            code = _blocked_code(getattr(result, "code", None))
            if code is None:
                code = "MONITOR_PROVENANCE_CHANGED"
            return failure(operation, code, "Monitor read plan could not be prepared")
        plan = getattr(result, "data", None)
        if plan is None:
            invalidate_failed_prepare()
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor read plan is invalid")
        try:
            admission_method = getattr(self._observation, "_read_plan_admission", None)
            admission_matches = callable(admission_method) and admission_method() is admission_token
        except Exception:
            admission_matches = False
        if not admission_matches:
            invalidate_failed_prepare()
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor read admission changed")
        self._read_plan = plan
        self._plan_watches = items
        self._plan_report_watches = report_watches
        return success(operation, {"prepared": True})

    async def read(self, watches: Iterable[WatchItem]) -> ProbeReadOutcome:
        items = tuple(watches)
        if not items or not all(isinstance(item, WatchItem) for item in items):
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor watch set is invalid")
        plan = self._read_plan
        if plan is None:
            mixed_result = await self._read_mixed_batch(items)
        else:
            if items != self._plan_watches:
                return ProbeReadOutcome(
                    (), "MONITOR_PROVENANCE_CHANGED", "Monitor read plan changed"
                )
            selectors = tuple(item.selector for item in self._plan_report_watches)
            try:
                result = await self._observation._read_prepared(plan)
            except asyncio.CancelledError:
                if self._read_plan is plan:
                    self.invalidate_read_plan()
                raise
            except Exception:
                if self._read_plan is plan:
                    self.invalidate_read_plan()
                return ProbeReadOutcome(
                    (),
                    "MONITOR_PROVENANCE_CHANGED",
                    "Monitor observation read failed",
                )
            mixed_result = self._map_read_result(
                self._plan_report_watches, selectors, result
            )
        if mixed_result.blocked_code is not None:
            if plan is not None and self._read_plan is plan:
                self.invalidate_read_plan()
            return mixed_result
        by_watch = {
            (value.watch.kind, value.watch.selector): value
            for value in mixed_result.values
        }
        try:
            ordered = tuple(by_watch[(item.kind, item.selector)] for item in items)
        except KeyError:
            return ProbeReadOutcome((), "MONITOR_PROVENANCE_CHANGED", "Monitor observation report is incomplete")
        return ProbeReadOutcome(ordered)

    async def revalidate(self) -> ProtocolResult[ObservationBinding]:
        operation = "sampling.revalidate"
        revalidation_plan = self._read_plan
        revalidation_admission = self._admission_token

        def invalidate_failed_revalidation() -> None:
            if (
                self._read_plan is revalidation_plan
                and self._admission_token is revalidation_admission
            ):
                self.invalidate_read_plan()

        try:
            result = await self._observation.revalidate()
        except asyncio.CancelledError:
            invalidate_failed_revalidation()
            raise
        except Exception:
            invalidate_failed_revalidation()
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor observation changed")
        if getattr(result, "ok", None) is not True:
            invalidate_failed_revalidation()
            code = _blocked_code(getattr(result, "code", None)) or "MONITOR_PROVENANCE_CHANGED"
            return failure(operation, code, "Monitor observation changed")
        try:
            current = _map_binding(self._observation, getattr(result, "data", None))
        except (TypeError, ValueError):
            invalidate_failed_revalidation()
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
            invalidate_failed_revalidation()
            return failure(operation, code, "Monitor observation changed")
        try:
            admission_method = getattr(self._observation, "_read_plan_admission", None)
            token = admission_method() if callable(admission_method) else None
        except Exception:
            token = None
        if token is None:
            invalidate_failed_revalidation()
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor observation changed")
        self._admission_token = token
        return success(operation, current)

    async def _revalidate_lightweight(self) -> ProtocolResult[ObservationBinding]:
        operation = "sampling.revalidate"
        method = getattr(self._observation, "_revalidate_lightweight", None)
        if not callable(method):
            return failure(operation, "MONITOR_PROVENANCE_CHANGED", "Monitor observation changed")
        try:
            result = await method()
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
