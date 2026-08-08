from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import aiohttp
import pytest


TOKEN_BYTES = b"s" * 32


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str | None, dict[str, str]]] = []
        self.live_queue: asyncio.Queue[object] = asyncio.Queue()
        self.subscribed = asyncio.Event()
        self.result: object | None = None
        self.error: Exception | None = None

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        resource_id: str | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.calls.append((operation, payload, resource_id, dict(query or {})))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result  # type: ignore[return-value]
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
        for response in (unknown, wrong_method):
            document = await response.json()
            assert document["protocol"] == "stm32-toolkit-monitor/1"
            assert document["code"] == "MONITOR_REQUEST_INVALID"
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_bodyless_and_query_routes_reject_extra_input_before_dispatch() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            bodyless = await client.post(
                endpoint.url + "/api/v1/probe/release", headers=auth, json={}
            )
            status_query = await client.get(
                endpoint.url + "/api/v1/status?unexpected=1", headers=auth
            )
            list_query = await client.get(
                endpoint.url + "/api/v1/groups?unexpected=1", headers=auth
            )
            export_query = await client.get(
                endpoint.url + "/api/v1/exports/export-a?unexpected=1", headers=auth
            )
            bootstrap_body = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={**auth, "Origin": endpoint.url},
                json={},
            )
            live_query = await client.get(
                endpoint.url + "/api/v1/live?unexpected=1", headers=auth
            )
        assert [
            bodyless.status,
            status_query.status,
            list_query.status,
            export_query.status,
            bootstrap_body.status,
            live_query.status,
        ] == [
            400,
            400,
            400,
            400,
            400,
            400,
        ]
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_websocket_is_authenticated_bounded_and_drops_oldest_for_slow_clients() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            with pytest.raises(aiohttp.WSServerHandshakeError) as denied:
                await client.ws_connect(endpoint.url + "/api/v1/live")
            assert denied.value.status == 401
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            for sequence in range(20):
                await runtime.live_queue.put({"sequence": sequence})
            seen: list[dict[str, object]] = []
            for _ in range(9):
                frame = await asyncio.wait_for(ws.receive(), 2)
                assert int(frame.type) == int(aiohttp.WSMsgType.TEXT)
                message = json.loads(frame.data)
                seen.append(message)
                if message["data"]["sequence"] == 19:
                    break
            assert seen[-1]["data"]["sequence"] == 19
            assert any(item["details"].get("subscriberDropped", 0) > 0 for item in seen)
            await ws.close()

    asyncio.run(_with_service(scenario, send_delay_seconds=0.02))


def test_every_route_has_one_exact_method_and_operation_mapping() -> None:
    routes = [
        ("GET", "/api/v1/status", "monitor.status", None),
        ("GET", "/api/v1/groups", "monitor.groups.list", None),
        ("POST", "/api/v1/groups", "monitor.groups.create", None),
        ("PATCH", "/api/v1/groups/12345678-1234-5678-1234-567812345678", "monitor.groups.update", "12345678-1234-5678-1234-567812345678"),
        ("DELETE", "/api/v1/groups/12345678-1234-5678-1234-567812345678", "monitor.groups.delete", "12345678-1234-5678-1234-567812345678"),
        ("POST", "/api/v1/groups/import", "monitor.groups.import", None),
        ("POST", "/api/v1/probe/connect", "monitor.probe.connect", None),
        ("POST", "/api/v1/probe/release", "monitor.probe.release", None),
        ("POST", "/api/v1/probe/reconnect", "monitor.probe.reconnect", None),
        ("POST", "/api/v1/sampling/start", "monitor.sampling.start", None),
        ("POST", "/api/v1/sampling/pause", "monitor.sampling.pause", None),
        ("POST", "/api/v1/sampling/resume", "monitor.sampling.resume", None),
        ("POST", "/api/v1/sampling/stop", "monitor.sampling.stop", None),
        ("GET", "/api/v1/history?sessionId=session-a", "monitor.history.query", None),
        ("POST", "/api/v1/exports", "monitor.exports.create", None),
        ("GET", "/api/v1/exports/export-a", "monitor.exports.get", "export-a"),
    ]

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            for method, path, operation, resource_id in routes:
                kwargs = {"headers": headers}
                if method in {"POST", "PATCH", "DELETE"} and path not in {
                    "/api/v1/probe/release",
                    "/api/v1/probe/reconnect",
                    "/api/v1/sampling/pause",
                    "/api/v1/sampling/resume",
                    "/api/v1/sampling/stop",
                }:
                    kwargs["json"] = {"authorized": True}
                response = await client.request(method, endpoint.url + path, **kwargs)
                result = await response.json()
                assert response.status == 200
                assert result["operation"] == operation
                assert runtime.calls[-1][0] == operation
                assert runtime.calls[-1][2] == resource_id

    asyncio.run(_with_service(scenario))


def test_protocol_results_and_arbitrary_runtime_exceptions_are_bounded() -> None:
    from stm32_monitor.protocol import failure, success

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            runtime.result = success("groups.list", {"groups": []})
            good = await client.get(endpoint.url + "/api/v1/groups", headers=headers)
            good_payload = await good.json()
            runtime.result = failure(
                "groups.list", "MONITOR_GROUP_CONFLICT", "Group changed", {"revision": 2}
            )
            conflict = await client.get(endpoint.url + "/api/v1/groups", headers=headers)
            conflict_payload = await conflict.json()
            runtime.result = None
            runtime.error = RuntimeError("SECRET C:\\private\\database.sqlite3")
            failed = await client.get(endpoint.url + "/api/v1/groups", headers=headers)
            failed_text = await failed.text()
            runtime.error = None

            class ForgedResult:
                def to_dict(self):
                    return {
                        "ok": False,
                        "code": "FORGED",
                        "message": "SECRET C:\\private\\token.txt",
                        "data": None,
                        "details": {"token": TOKEN_BYTES.hex()},
                    }

            runtime.result = ForgedResult()
            forged = await client.get(endpoint.url + "/api/v1/groups", headers=headers)
            forged_text = await forged.text()
        assert good.status == 200 and good_payload["data"] == {"groups": []}
        assert conflict.status == 409
        assert conflict_payload["details"] == {"revision": 2}
        assert failed.status == 500
        assert "SECRET" not in failed_text and "database.sqlite3" not in failed_text
        assert forged.status == 500
        assert "SECRET" not in forged_text and TOKEN_BYTES.hex() not in forged_text

    asyncio.run(_with_service(scenario))


def test_invalid_json_content_type_and_nested_override_never_dispatch() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}"}
        async with aiohttp.ClientSession() as client:
            wrong_type = await client.post(
                endpoint.url + "/api/v1/groups", headers=auth, data=b"{}"
            )
            malformed = await client.post(
                endpoint.url + "/api/v1/groups",
                headers={**auth, "Content-Type": "application/json"},
                data=b"{",
            )
            non_object = await client.post(
                endpoint.url + "/api/v1/groups", headers=auth, json=[]
            )
            nested = await client.post(
                endpoint.url + "/api/v1/groups",
                headers=auth,
                json={"items": [{"address": 536870912}]},
            )
        assert [wrong_type.status, malformed.status, non_object.status, nested.status] == [
            415,
            400,
            400,
            400,
        ]
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_constructor_start_and_stop_are_strict_and_idempotent() -> None:
    from stm32_monitor.service import MonitorService

    for kwargs in (
        {"workspace_id": "", "session_id": "session-a"},
        {"workspace_id": "workspace-a", "session_id": ""},
        {"workspace_id": "workspace-a", "session_id": "session-a", "send_delay_seconds": -1},
    ):
        with pytest.raises(ValueError):
            MonitorService(FakeRuntime(), **kwargs)

    async def scenario(runtime, service, endpoint) -> None:
        assert service.endpoint == endpoint
        assert await service.start() == endpoint
        assert endpoint.access_url.endswith("#token=" + TOKEN_BYTES.hex())
        await service.stop()
        await service.stop()

    asyncio.run(_with_service(scenario))


def test_websocket_rejects_client_messages() -> None:
    async def scenario(_runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await ws.send_json({"unexpected": True})
            message = await asyncio.wait_for(ws.receive(), 1)
            assert message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}

    asyncio.run(_with_service(scenario))
