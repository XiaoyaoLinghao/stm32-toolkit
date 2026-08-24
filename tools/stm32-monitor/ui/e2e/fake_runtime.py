"""Stateful test runtime driving the real MonitorService over real HTTP/WS.

The Playwright browser test spawns this process. It builds a MonitorService
with a scripted fake runtime and prints the access URL on stdout so the test
can open the browser at ``/#token=<token>``. Product traffic (bootstrap,
status, live WebSocket, static assets) stays on the real aiohttp boundary.

A separate loopback control HTTP server (also bound to ``127.0.0.1``) exposes
the fixture RPC used by Playwright specs: producer start/stop, drop totals,
sample count, and asset sizes. The control URL is printed on stdout so the
fixture can drive the runtime without touching the product service.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import web

from stm32_monitor.protocol import failure, success
from stm32_monitor.service import MonitorService

_TOOLKIT_VERSION = "0.9.0"
_MONITOR_VERSION = "0.9.0"
_DEFAULT_ROWS = 2


@dataclass
class _Group:
    group_id: str
    name: str
    description: str
    interval_ms: int
    items: list[dict[str, object]]
    revision: int = 1


@dataclass
class _State:
    workspace_id: str = "workspace-a"
    session_id: str = "session-a"
    logical_project_id: str = "project"
    target_device: str = "STM32F407VG"
    groups: list[_Group] = field(default_factory=list)
    probe_connected: bool = False
    probe_id: str | None = None
    sampling_state: str = "IDLE"
    binding_epoch: int = 0
    active_group_id: str | None = None
    active_run_id: str | None = None
    group_counter: int = 0
    producer_active: bool = False
    producer_hz: float = 10.0
    sample_count: int = 0
    service_drops_total: int = 0
    rows: int = _DEFAULT_ROWS

    def next_group_id(self) -> str:
        self.group_counter += 1
        return f"group-{self.group_counter}"


def _sampling_status(state: _State) -> dict[str, object]:
    active = state.sampling_state in {"RUNNING", "PAUSED"}
    return {
        "state": state.sampling_state,
        "active": active,
        "blockedCode": None,
        "groupId": state.active_group_id,
        "groupRevision": None,
        "runId": state.active_run_id if active else None,
        "lastSequence": None,
        "bindingEpoch": state.binding_epoch,
        "subscriberDrops": 0,
        "historyDrops": 0,
        "deadlineDrops": 0,
        "serviceDrops": state.service_drops_total,
    }


def _status(state: _State) -> dict[str, object]:
    firmware = None
    if state.probe_connected:
        firmware = {
            "buildId": "0" * 64,
            "elfSha256": "1" * 64,
            "inputSnapshotSha256": "2" * 64,
            "gitHead": "a" * 40,
            "gitDirty": False,
            "targetDevice": state.target_device,
        }
    return {
        "workspaceId": state.workspace_id,
        "sessionId": state.session_id,
        "project": {
            "logicalProjectId": state.logical_project_id,
            "name": "Fake Project",
            "targetDevice": state.target_device,
        },
        "firmware": firmware,
        "probe": {"connected": state.probe_connected, "probeId": state.probe_id},
        "sampling": _sampling_status(state),
        "probeConnected": state.probe_connected,
        "samplingActive": state.sampling_state in {"RUNNING", "PAUSED"},
    }


def _group_dict(group: _Group) -> dict[str, object]:
    return {
        "groupId": group.group_id,
        "name": group.name,
        "description": group.description,
        "intervalMs": group.interval_ms,
        "items": group.items,
        "revision": group.revision,
        "createdAtUtc": "2026-08-10T00:00:00Z",
        "updatedAtUtc": "2026-08-10T00:00:00Z",
    }


def _catalog_item(index: int) -> dict[str, object]:
    return {
        "selector": f"v{index}",
        "typeName": "uint32_t",
        "kind": "scalar",
        "byteSize": 4,
        "signed": False,
        "encoding": None,
        "qualifiers": [],
        "aliases": [],
        "enumValues": [],
        "elementCount": None,
        "elementKind": None,
        "memberNames": [],
    }


def _debug_binding(state: _State) -> dict[str, object]:
    return {
        "logicalProjectId": state.logical_project_id,
        "workspaceId": state.workspace_id,
        "observationSessionId": state.session_id,
        "flashSessionId": "flash-a",
        "leaseId": "lease-a",
        "probeId": state.probe_id or "probe-a",
        "targetDevice": state.target_device,
        "debugTarget": "cortex_m",
        "buildId": "0" * 64,
        "elfSha256": "1" * 64,
        "elfSize": 4096,
        "elfPath": "build/fw.elf",
        "inputSnapshotSha256": "2" * 64,
        "gitHead": "a" * 40,
        "gitDirty": False,
        "confirmedAtUtc": "2026-08-10T00:00:00Z",
        "memoryRegions": [
            {"name": "FLASH", "origin": 0x08000000, "length": 0x10000, "attributes": "rx"}
        ],
    }


def _watch(expression: str) -> dict[str, object]:
    return {"kind": "variable", "expression": expression}


async def _dispatch_operation(
    state: _State,
    operation: str,
    payload: dict[str, object],
    *,
    resource_id: str | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, object]:
    if operation == "monitor.status":
        return _status(state)
    if operation == "monitor.probes.list":
        return {
            "probes": [
                {
                    "probeId": "probe-a",
                    "vendor": "STMicroelectronics",
                    "product": "STM32 ST-LINK",
                    "boardName": "Nucleo",
                }
            ]
        }
    if operation == "monitor.groups.list":
        return {
            "groups": [_group_dict(group) for group in state.groups],
            "nextCursor": None,
            "revision": "0",
        }
    if operation == "monitor.catalog.variables":
        counter = {
            "selector": "counter",
            "typeName": "uint32_t",
            "kind": "scalar",
            "byteSize": 4,
            "signed": False,
            "encoding": None,
            "qualifiers": [],
            "aliases": [],
            "enumValues": [],
            "elementCount": None,
            "elementKind": None,
            "memberNames": [],
        }
        faulty = dict(counter, selector="faulty")
        all_items = [counter, faulty, *( _catalog_item(index) for index in range(state.rows))]
        text_query = (query or {}).get("query", "")
        items = (
            [item for item in all_items if item["selector"].startswith(text_query)]
            if text_query
            else all_items
        )
        return {"items": items, "nextCursor": None}
    if operation == "monitor.catalog.registers":
        return {"items": [], "nextCursor": None}
    if operation == "monitor.history.query":
        return {
            "batches": [],
            "valueCount": 0,
            "nextCursor": None,
            "serializedBytes": 0,
        }
    if operation == "monitor.groups.create":
        group = _Group(
            state.next_group_id(),
            str(payload.get("name", "")),
            str(payload.get("description", "")),
            int(payload.get("intervalMs", 250)),
            list(payload.get("items", [])),
        )
        state.groups.append(group)
        return _group_dict(group)
    if operation == "monitor.groups.update":
        found = next(
            (group for group in state.groups if group.group_id == resource_id), None
        )
        if found is None:
            return failure(
                operation, "MONITOR_GROUP_NOT_FOUND", "Monitor group is unknown"
            )
        if "name" in payload:
            found.name = str(payload["name"])
        if "description" in payload:
            found.description = str(payload["description"])
        if "intervalMs" in payload:
            found.interval_ms = int(payload["intervalMs"])
        if "items" in payload:
            found.items = list(payload["items"])
        found.revision += 1
        return _group_dict(found)
    if operation == "monitor.groups.delete":
        state.groups = [
            group for group in state.groups if group.group_id != resource_id
        ]
        return {"groupId": resource_id, "deleted": True}
    if operation == "monitor.groups.import":
        document = payload.get("document")
        if not isinstance(document, dict):
            return failure(
                operation, "MONITOR_IMPORT_INVALID", "Monitor group import is invalid"
            )
        imported: list[dict[str, object]] = []
        for entry in document.get("groups", []):
            if not isinstance(entry, dict):
                continue
            group = _Group(
                state.next_group_id(),
                str(entry.get("name", "")),
                str(entry.get("description", "")),
                int(entry.get("intervalMs", 250)),
                list(entry.get("items", [])),
            )
            state.groups.append(group)
            imported.append(_group_dict(group))
        return success(operation, imported)
    if operation == "monitor.probe.connect":
        state.probe_connected = True
        state.probe_id = str(payload.get("probeId", "probe-a"))
        state.binding_epoch += 1
        return _debug_binding(state)
    if operation == "monitor.probe.reconnect":
        state.binding_epoch += 1
        return _debug_binding(state)
    if operation == "monitor.probe.release":
        state.probe_connected = False
        state.probe_id = None
        state.sampling_state = "IDLE"
        state.active_group_id = None
        return {"released": True}
    if operation == "monitor.sampling.start":
        group_id = str(payload.get("groupId", ""))
        found = next(
            (group for group in state.groups if group.group_id == group_id), None
        )
        if found is None:
            return failure(
                operation, "MONITOR_GROUP_NOT_FOUND", "Monitor group is unknown"
            )
        if not state.probe_connected:
            return failure(
                operation, "MONITOR_REQUEST_INVALID", "A probe must be connected"
            )
        state.sampling_state = "RUNNING"
        state.active_group_id = group_id
        state.active_run_id = "run-a"
        return {
            "groupId": group_id,
            "groupRevision": found.revision,
            "runId": "run-a",
            "intervalMs": found.interval_ms,
        }
    if operation == "monitor.sampling.pause":
        state.sampling_state = "PAUSED"
        return {"paused": True}
    if operation == "monitor.sampling.resume":
        state.sampling_state = "RUNNING"
        return {"resumed": True}
    if operation == "monitor.sampling.stop":
        state.sampling_state = "IDLE"
        state.active_group_id = None
        state.active_run_id = None
        return {"stopped": True}
    return {"operation": operation}


def _sample_event(state: _State, sequence: int) -> dict[str, object]:
    binding = {
        "workspaceId": state.workspace_id,
        "logicalProjectId": state.logical_project_id,
        "sessionId": state.session_id,
        "probeId": state.probe_id or "probe-a",
        "targetDevice": state.target_device,
        "physicalTarget": state.target_device,
        "buildId": "0" * 64,
        "elfSha256": "1" * 64,
        "inputSnapshotSha256": "2" * 64,
        "gitHead": "a" * 40,
        "gitDirty": False,
        "flashSessionId": "flash-a",
        "leaseId": "lease-a",
        "dwarfSha256": "3" * 64,
        "svdSha256": None,
    }
    group = next(
        (item for item in state.groups if item.group_id == state.active_group_id), None
    )
    items = list(group.items) if group is not None else []
    values: list[dict[str, object]] = []
    for item in items:
        expression = str(item.get("expression", ""))
        watch = _watch(expression)
        if expression == "faulty":
            values.append(
                {
                    "watch": watch,
                    "status": "ERROR",
                    "typedValue": None,
                    "code": "MONITOR_SAMPLE_ITEM_FAILED",
                    "definition": None,
                }
            )
        else:
            values.append(
                {
                    "watch": watch,
                    "status": "OK",
                    "typedValue": {
                        "expression": expression,
                        "typeName": "uint32_t",
                        "value": sequence,
                        "rawHex": "0x00000000",
                        "bitWidth": 32,
                    },
                    "code": None,
                    "definition": None,
                }
            )
    state.sample_count += 1
    return {
        "eventId": 100 + sequence,
        "type": "sample",
        "data": {
            "batch": {
                "binding": binding,
                "groupId": state.active_group_id,
                "groupRevision": 1,
                "runId": "run-a",
                "sequence": sequence,
                "scheduledUnixNs": 0,
                "scheduledAtUtc": "2026-08-10T00:00:00Z",
                "capturedUnixNs": 0,
                "capturedAtUtc": "2026-08-10T00:00:00Z",
                "latencyNs": 0,
                "actualRateHz": state.producer_hz,
                "subscriberDrops": 0,
                "historyDrops": 0,
                "deadlineDrops": 0,
                "values": values,
            },
            "serviceSubscriberDrops": 0,
        },
    }


class _FakeRuntime:
    def __init__(self, state: _State) -> None:
        self._state = state
        self._live: asyncio.Queue[object] = asyncio.Queue()

    def record_service_drops(self, count: int) -> None:
        if type(count) is int and count > 0:
            self._state.service_drops_total += count

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        resource_id: str | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, object]:
        return await _dispatch_operation(
            self._state, operation, payload, resource_id=resource_id, query=query
        )

    async def live_subscribe(
        self, *, after_event_id: int | None = None
    ):
        sequence = 0
        if after_event_id is None:
            yield {
                "eventId": 1,
                "type": "hello",
                "data": {
                    "protocol": "stm32-toolkit-monitor/1",
                    "toolkitVersion": _TOOLKIT_VERSION,
                    "monitorVersion": _MONITOR_VERSION,
                    "stateRevision": 0,
                },
            }
            yield {
                "eventId": 2,
                "type": "state",
                "data": {
                    "stateRevision": 0,
                    "gap": False,
                    "status": _status(self._state),
                },
            }
        while True:
            if self._state.sampling_state == "RUNNING":
                sequence += 1
                yield _sample_event(self._state, sequence)
                if self._state.producer_active:
                    await asyncio.sleep(1.0 / self._state.producer_hz)
                else:
                    await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.2)


def _asset_sizes() -> dict[str, int]:
    from importlib import resources

    ui = resources.files("stm32_monitor") / "ui_dist"
    raw = 0
    js_blobs: list[bytes] = []
    css_blobs: list[bytes] = []
    for path in ui.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            raw += len(blob)
            if path.name.endswith(".js"):
                js_blobs.append(blob)
            elif path.name.endswith(".css"):
                css_blobs.append(blob)
    return {
        "rawBytes": raw,
        "gzipJsBytes": sum(len(gzip.compress(blob)) for blob in js_blobs),
        "gzipCssBytes": sum(len(gzip.compress(blob)) for blob in css_blobs),
    }


async def _control_app(state: _State) -> web.Application:
    async def start_producer(request: web.Request) -> web.Response:
        payload = await request.json()
        state.producer_hz = float(payload.get("hz", 10.0))
        if not 0.5 <= state.producer_hz <= 100:
            return web.json_response({"ok": False, "code": "INVALID_HZ"})
        state.producer_active = True
        state.sample_count = 0
        return web.json_response({"ok": True, "active": True, "hz": state.producer_hz})

    async def stop_producer(request: web.Request) -> web.Response:
        state.producer_active = False
        return web.json_response({"ok": True, "active": False})

    async def producer_status(request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "active": state.producer_active, "hz": state.producer_hz}
        )

    async def drops(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "drops": {
                    "subscriber": 0,
                    "history": 0,
                    "deadline": 0,
                    "service": state.service_drops_total,
                },
            }
        )

    async def sample_count(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "count": state.sample_count})

    async def assets(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "assets": _asset_sizes()})

    async def rows(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "rows": state.rows})

    app = web.Application()
    app.router.add_post("/producer/start", start_producer)
    app.router.add_post("/producer/stop", stop_producer)
    app.router.add_get("/producer/status", producer_status)
    app.router.add_get("/drops", drops)
    app.router.add_get("/sample-count", sample_count)
    app.router.add_get("/assets", assets)
    app.router.add_get("/rows", rows)
    return app


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=_DEFAULT_ROWS)
    args = parser.parse_args()
    _ = args.repo
    if not 1 <= args.rows <= 4096:
        raise SystemExit("rows must be between 1 and 4096")

    state = _State(rows=args.rows)
    service = MonitorService(
        _FakeRuntime(state),
        workspace_id=state.workspace_id,
        session_id=state.session_id,
        serve_ui=True,
    )
    endpoint = await service.start()
    control = await _start_control(state)
    payload = {
        "ok": True,
        "accessUrl": endpoint.access_url,
        "url": endpoint.url,
        "controlUrl": control,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()
    try:
        await asyncio.Event().wait()
    finally:
        await service.stop()
    return 0


async def _start_control(state: _State) -> str:
    from aiohttp import web

    runner = web.AppRunner(await _control_app(state), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = int(runner.addresses[0][1])
    return f"http://127.0.0.1:{port}"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
