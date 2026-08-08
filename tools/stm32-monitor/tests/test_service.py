from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import aiohttp


TOKEN_BYTES = b"s" * 32


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str | None, dict[str, str]]] = []
        self.live_queue: asyncio.Queue[object] = asyncio.Queue()
        self.subscribed = asyncio.Event()

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        resource_id: str | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.calls.append((operation, payload, resource_id, dict(query or {})))
        return {"operation": operation, "workspaceId": "workspace-a"}

    async def live_subscribe(self) -> AsyncIterator[dict[str, object]]:
        self.subscribed.set()
        while True:
            item = await self.live_queue.get()
            if item is StopAsyncIteration:
                return
            assert isinstance(item, dict)
            yield item


async def _with_service(action, *, send_delay_seconds: float = 0.0) -> None:
    from stm32_monitor.service import MonitorService

    runtime = FakeRuntime()
    service = MonitorService(
        runtime,
        workspace_id="workspace-a",
        session_id="session-a",
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
        send_delay_seconds=send_delay_seconds,
    )
    endpoint = await service.start()
    try:
        await action(runtime, service, endpoint)
    finally:
        await service.stop()


def test_service_binds_dynamic_ipv4_loopback_and_status_is_authenticated() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        assert endpoint.host == "127.0.0.1"
        assert 1 <= endpoint.port <= 65535
        assert endpoint.port != 8888
        assert TOKEN_BYTES.hex() not in repr(endpoint)
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            denied = await client.get(endpoint.url + "/api/v1/status")
            assert denied.status == 401
            response = await client.get(endpoint.url + "/api/v1/status", headers=headers)
            payload = await response.json()
        assert response.status == 200
        assert set(payload) == {
            "protocol",
            "toolkitVersion",
            "ok",
            "operation",
            "code",
            "message",
            "data",
            "details",
        }
        assert payload["protocol"] == "stm32-toolkit-monitor/1"
        assert payload["data"]["operation"] == "monitor.status"
        assert runtime.calls[0][0] == "monitor.status"

    asyncio.run(_with_service(scenario))


def test_bearer_bootstrap_sets_only_httponly_strict_cookie() -> None:
    async def scenario(_runtime, _service, endpoint) -> None:
        jar = aiohttp.CookieJar(unsafe=True)
        origin = endpoint.url
        async with aiohttp.ClientSession(cookie_jar=jar) as client:
            bootstrap = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={
                    "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
                    "Origin": origin,
                },
            )
            assert bootstrap.status == 200
            cookie = bootstrap.cookies["stm32_monitor_session"]
            assert cookie["httponly"] is True
            assert cookie["samesite"].lower() == "strict"
            assert cookie["path"] == "/api/v1"
            response = await client.get(
                endpoint.url + "/api/v1/status", headers={"Origin": origin}
            )
            assert response.status == 200
        assert TOKEN_BYTES.hex() not in json.dumps(await bootstrap.json())

    asyncio.run(_with_service(scenario))


def test_host_origin_and_forbidden_identity_overrides_fail_closed() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            bad_host = await client.get(
                endpoint.url + "/api/v1/status", headers={**auth, "Host": "localhost"}
            )
            bad_origin = await client.get(
                endpoint.url + "/api/v1/status",
                headers={**auth, "Origin": "http://localhost"},
            )
            override = await client.post(
                endpoint.url + "/api/v1/probe/connect",
                headers=auth,
                json={
                    "probeId": "probe-a",
                    "expectedBuildId": "a" * 64,
                    "expectedElfSha256": "b" * 64,
                    "target": "attacker-target",
                },
            )
        assert (bad_host.status, bad_origin.status, override.status) == (403, 403, 400)
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_body_and_route_grammar_are_bounded_and_exact() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        from stm32_monitor.auth import MAX_REQUEST_BYTES

        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            too_large = await client.post(
                endpoint.url + "/api/v1/groups",
                headers={**auth, "Content-Type": "application/json"},
                data=b"{" + b" " * MAX_REQUEST_BYTES + b"}",
            )
            unknown = await client.get(endpoint.url + "/api/v1/unknown", headers=auth)
            wrong_method = await client.put(endpoint.url + "/api/v1/groups", headers=auth)
        assert (too_large.status, unknown.status, wrong_method.status) == (413, 404, 405)
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_websocket_is_authenticated_bounded_and_drops_oldest_for_slow_clients() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            denied = await client.ws_connect(endpoint.url + "/api/v1/live")
            denied_message = await denied.receive()
            assert denied_message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            for sequence in range(20):
                await runtime.live_queue.put({"sequence": sequence})
            seen: list[dict[str, object]] = []
            for _ in range(9):
                message = await asyncio.wait_for(ws.receive_json(), 2)
                seen.append(message)
                if message["data"]["sequence"] == 19:
                    break
            assert seen[-1]["data"]["sequence"] == 19
            assert any(item["details"].get("subscriberDropped", 0) > 0 for item in seen)
            await ws.close()

    asyncio.run(_with_service(scenario, send_delay_seconds=0.02))

