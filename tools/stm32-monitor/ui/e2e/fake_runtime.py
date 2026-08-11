"""Stateful test runtime driving the real MonitorService over real HTTP/WS.

The Playwright browser test spawns this process. It builds a MonitorService
with a scripted fake runtime and prints the access URL on stdout so the test
can open the browser at ``/#token=<token>``. Product traffic (bootstrap,
status, live WebSocket, static assets) stays on the real aiohttp boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from stm32_monitor.service import MonitorService

_TOOLKIT_VERSION = "0.5.0"
_MONITOR_VERSION = "0.5.0"


@dataclass
class _State:
    workspace_id: str = "workspace-a"
    session_id: str = "session-a"
    logical_project_id: str = "project"
    target_device: str = "STM32F407VG"


async def _dispatch_operation(
    state: _State,
    operation: str,
    payload: dict[str, object],
    *,
    resource_id: str | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, object]:
    if operation == "monitor.status":
        return {
            "workspaceId": state.workspace_id,
            "sessionId": state.session_id,
            "project": {
                "logicalProjectId": state.logical_project_id,
                "name": "Fake Project",
                "targetDevice": state.target_device,
            },
            "firmware": None,
            "probe": {"connected": False, "probeId": None},
            "sampling": {
                "state": "IDLE",
                "active": False,
                "blockedCode": None,
                "groupId": None,
                "groupRevision": None,
                "runId": None,
                "lastSequence": None,
                "bindingEpoch": 0,
                "subscriberDrops": 0,
                "historyDrops": 0,
                "deadlineDrops": 0,
                "serviceDrops": 0,
            },
            "probeConnected": False,
            "samplingActive": False,
        }
    if operation == "monitor.probes.list":
        return {"probes": []}
    if operation == "monitor.groups.list":
        return {"groups": [], "nextCursor": None, "revision": "0"}
    if operation == "monitor.catalog.variables":
        return {"items": [], "nextCursor": None}
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
        return {
            "groupId": "group-1",
            "name": str(payload.get("name", "")),
            "description": str(payload.get("description", "")),
            "intervalMs": int(payload.get("intervalMs", 250)),
            "items": payload.get("items", []),
            "revision": 1,
            "createdAtUtc": "2026-08-10T00:00:00Z",
            "updatedAtUtc": "2026-08-10T00:00:00Z",
        }
    return {"operation": operation}


class _FakeRuntime:
    def __init__(self, state: _State) -> None:
        self._state = state
        self._live: asyncio.Queue[object] = asyncio.Queue()

    def record_service_drops(self, count: int) -> None:
        pass

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

    def subscribe(
        self, operation: str
    ) -> object:
        return self

    def unsubscribe(self, subscriber: object) -> None:
        pass

    async def _events(self) -> asyncio.Queue[object]:
        return self._live


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    _ = args.repo

    state = _State()
    service = MonitorService(
        _FakeRuntime(state),
        workspace_id=state.workspace_id,
        session_id=state.session_id,
        serve_ui=True,
    )
    endpoint = await service.start()
    access_url = endpoint.access_url
    payload = {"ok": True, "accessUrl": access_url, "url": endpoint.url}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()
    try:
        await asyncio.Event().wait()
    finally:
        await service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
