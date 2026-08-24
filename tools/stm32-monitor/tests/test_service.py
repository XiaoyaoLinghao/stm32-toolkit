from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from uuid import UUID

import aiohttp
import pytest


TOKEN_BYTES = b"s" * 32


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str | None, dict[str, str]]] = []
        self.live_queue: asyncio.Queue[object] = asyncio.Queue()
        self.subscribed = asyncio.Event()
        self.unsubscribed = asyncio.Event()
        self.result: object | None = None
        self.error: Exception | None = None
        self.recorded_drops = 0
        self.drop_recorded = asyncio.Event()

    def record_service_drops(self, count: int) -> None:
        self.recorded_drops += count
        self.drop_recorded.set()

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

    async def live_subscribe(
        self, *, after_event_id: int | None = None
    ) -> AsyncIterator[dict[str, object]]:
        self.after_event_id = after_event_id
        self.subscribed.set()
        try:
            while True:
                item = await self.live_queue.get()
                if item is StopAsyncIteration:
                    return
                assert isinstance(item, dict)
                yield item
        finally:
            self.unsubscribed.set()


def _oversized_model_valid_live_event() -> dict[str, object]:
    from stm32_monitor.auth import MAX_REQUEST_BYTES
    from stm32_monitor.models import (
        LiveEvent,
        ObservationBinding,
        SampleBatch,
        SampleValue,
        WatchItem,
    )

    binding = ObservationBinding(
        "a" * 64,
        "12345678-1234-5678-9234-567812345678",
        "session-a",
        "probe-a",
        "STM32F407VGTx",
        "stm32f407vg",
        "b" * 64,
        "e" * 64,
        "d" * 64,
        "c" * 40,
        False,
        "flash-1",
        "lease-1",
        "f" * 64,
        None,
    )
    batch = SampleBatch(
        binding,
        UUID("12345678-1234-5678-9234-567812345678"),
        1,
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        1,
        1_000,
        1_250,
        250,
        4.0,
        0,
        0,
        0,
        (
            SampleValue(
                WatchItem.variable("counter"),
                "OK",
                typed_value="SENSITIVE_PAYLOAD_MARKER\n"
                + "\n" * (MAX_REQUEST_BYTES // 2),
            ),
        ),
    )
    return LiveEvent(
        1,
        "sample",
        {"batch": batch.to_dict(), "serviceSubscriberDrops": 0},
    ).to_dict()


async def _with_service(action, *, send_delay_seconds: float = 0.0, runtime_factory=None) -> None:
    from stm32_monitor.service import MonitorService

    runtime = runtime_factory() if runtime_factory is not None else FakeRuntime()
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


def _write_ui_dist(root: Path) -> Path:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (assets / "index-A1b2C3d4.js").write_bytes(b"console.log(1)")
    manifest = {"index.html": {"file": "assets/index-A1b2C3d4.js", "css": []}}
    (root / ".vite").mkdir()
    (root / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "index.html").write_text(
        '<!doctype html><html><body><div id="app"></div>'
        '<script type="module" src="/assets/index-A1b2C3d4.js"></script></body></html>',
        encoding="utf-8",
    )
    return root


async def _with_ui_service(action, ui_root: Path) -> None:
    from stm32_monitor.service import MonitorService

    runtime = FakeRuntime()
    service = MonitorService(
        runtime,
        workspace_id="workspace-a",
        session_id="session-a",
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
        serve_ui=True,
        ui_assets_root=ui_root,
    )
    endpoint = await service.start()
    try:
        await action(runtime, service, endpoint)
    finally:
        await service.stop()


def test_static_ui_serves_index_and_assets_with_exact_origin(tmp_path: Path) -> None:
    import aiohttp

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        headers = {"Origin": origin, "Host": f"127.0.0.1:{endpoint.port}"}
        async with aiohttp.ClientSession() as client:
            index = await client.get(endpoint.url + "/", headers=headers)
            assert index.status == 200
            assert b'id="app"' in await index.read()
            asset = await client.get(
                endpoint.url + "/assets/index-A1b2C3d4.js", headers=headers
            )
            assert asset.status == 200
            assert await asset.read() == b"console.log(1)"

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_rejects_wrong_host_and_origin(tmp_path: Path) -> None:
    import aiohttp

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        async with aiohttp.ClientSession() as client:
            bad_host = await client.get(
                endpoint.url + "/",
                headers={"Origin": origin, "Host": "attacker.invalid:9999"},
            )
            assert bad_host.status in (403, 404)
            body = await bad_host.text()
            assert "attacker" not in body
            bad_origin = await client.get(
                endpoint.url + "/",
                headers={"Origin": "http://attacker.invalid"},
            )
            assert bad_origin.status in (403, 404)
            body2 = await bad_origin.text()
            assert "attacker" not in body2
            null_origin = await client.get(
                endpoint.url + "/", headers={"Origin": "null"}
            )
            assert null_origin.status in (403, 404)

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_csp_uses_bound_port_not_request_host(tmp_path: Path) -> None:
    import aiohttp

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        headers = {"Origin": origin, "Host": f"127.0.0.1:{endpoint.port}"}
        async with aiohttp.ClientSession() as client:
            index = await client.get(endpoint.url + "/", headers=headers)
            csp = index.headers.get("Content-Security-Policy", "")
            assert f"ws://127.0.0.1:{endpoint.port}" in csp
            assert "9999" not in csp

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_unknown_asset_is_404_and_api_never_falls_back(tmp_path: Path) -> None:
    import aiohttp

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        headers = {"Origin": origin}
        async with aiohttp.ClientSession() as client:
            unknown = await client.get(
                endpoint.url + "/assets/nope-NotAHash.js", headers=headers
            )
            assert unknown.status == 404
            api = await client.get(endpoint.url + "/api/v1/status", headers=headers)
            assert api.status in (401, 403)

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_rejects_forged_peer_via_request_seam(tmp_path: Path) -> None:
    from aiohttp.test_utils import make_mocked_request

    ui_root = _write_ui_dist(tmp_path)

    class _FakeTransport:
        def get_extra_info(self, name: str):
            if name == "peername":
                return ("192.0.2.1", 12345)
            return None

    async def scenario(_runtime, service, endpoint) -> None:
        request = make_mocked_request(
            "GET",
            "/",
            headers={"Host": f"127.0.0.1:{endpoint.port}"},
            transport=_FakeTransport(),
        )
        assert request.remote == "192.0.2.1"
        response = await service._static(request)
        assert response.status == 403
        assert response.body == b""

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_rejects_oversized_header_budget(tmp_path: Path) -> None:
    import aiohttp

    from stm32_monitor.auth import MAX_REQUEST_BYTES

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        huge = "x" * (MAX_REQUEST_BYTES + 1)
        async with aiohttp.ClientSession() as client:
            response = await client.get(
                endpoint.url + "/",
                headers={"Origin": origin, "X-Huge": huge},
            )
            assert response.status in (400, 403, 431)

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_static_ui_traversal_is_404_without_route_reflection(tmp_path: Path) -> None:
    import aiohttp

    ui_root = _write_ui_dist(tmp_path)

    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        async with aiohttp.ClientSession() as client:
            for path in ("/assets/../auth.py", "/assets/%2e%2e/auth.py"):
                response = await client.get(
                    endpoint.url + path,
                    headers={"Origin": origin},
                )
                assert response.status in (403, 404)
                body = await response.text()
                assert "auth.py" not in body

    asyncio.run(_with_ui_service(scenario, ui_root))


def test_service_binds_dynamic_ipv4_loopback_and_status_is_authenticated() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        assert endpoint.host == "127.0.0.1"
        assert 1 <= endpoint.port <= 65535
        assert endpoint.port != 8888
        assert TOKEN_BYTES.hex() not in repr(endpoint)
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
        async with aiohttp.ClientSession() as client:
            denied = await client.get(endpoint.url + "/api/v1/status")
            assert denied.status == 401
            response = await client.get(endpoint.url + "/api/v1/status", headers=headers)
            payload = await response.json()
        assert response.status == 200
        assert set(payload) == {
            "protocol",
            "toolkitVersion",
            "monitorVersion",
            "ok",
            "operation",
            "code",
            "message",
            "data",
            "details",
        }
        assert payload["protocol"] == "stm32-toolkit-monitor/1"
        assert payload["monitorVersion"] == "0.9.0"
        assert endpoint.monitor_version == "0.9.0"
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
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
        origin = endpoint.url
        async with aiohttp.ClientSession() as client:
            bad_host = await client.get(
                endpoint.url + "/api/v1/status",
                headers={**auth, "Origin": origin, "Host": "localhost"},
            )
            bad_origin = await client.get(
                endpoint.url + "/api/v1/status",
                headers={**auth, "Origin": "http://localhost"},
            )
            override = await client.post(
                endpoint.url + "/api/v1/probe/connect",
                headers={**auth, "Origin": origin},
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


def test_cookie_transport_matrix_over_real_http() -> None:
    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        token = TOKEN_BYTES.hex()
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as client:
            boot = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={"Authorization": f"Bearer {token}", "Origin": origin},
            )
            assert boot.status == 200

            safe_get = await client.get(
                endpoint.url + "/api/v1/status", headers={"Origin": origin}
            )
            assert safe_get.status == 200

            get_without_origin = await client.get(endpoint.url + "/api/v1/status")
            assert get_without_origin.status in (401, 403)

            mutation_without_origin = await client.post(
                endpoint.url + "/api/v1/groups",
                headers={"Content-Type": "application/json"},
                json={"name": "g", "description": "", "intervalMs": 250, "items": []},
            )
            assert mutation_without_origin.status in (401, 403)

    asyncio.run(_with_service(scenario))


def test_bearer_requires_exact_origin_over_real_http() -> None:
    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        token = TOKEN_BYTES.hex()
        async with aiohttp.ClientSession() as client:
            no_origin = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert no_origin.status in (401, 403)

            wrong_origin = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Origin": "http://attacker.invalid",
                },
            )
            assert wrong_origin.status == 403

            exact = await client.post(
                endpoint.url + "/api/v1/auth/bootstrap",
                headers={"Authorization": f"Bearer {token}", "Origin": origin},
            )
            assert exact.status == 200

    asyncio.run(_with_service(scenario))


def test_body_and_route_grammar_are_bounded_and_exact() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        from stm32_monitor.auth import MAX_REQUEST_BYTES
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
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
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
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


def test_probe_and_catalog_get_routes_are_authenticated_exact_and_bounded() -> None:
    from stm32_monitor.protocol import failure

    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
        async with aiohttp.ClientSession() as client:
            denied = await client.get(endpoint.url + "/api/v1/probes")
            probes = await client.get(endpoint.url + "/api/v1/probes", headers=auth)
            variables = await client.get(
                endpoint.url + "/api/v1/catalog/variables?query=counter&limit=25",
                headers=auth,
            )
            registers = await client.get(
                endpoint.url + "/api/v1/catalog/registers?cursor=opaque",
                headers=auth,
            )
            calls_after_valid = len(runtime.calls)
            bad_body = await client.get(
                endpoint.url + "/api/v1/catalog/variables",
                headers=auth,
                json={},
            )
            probes_query = await client.get(
                endpoint.url + "/api/v1/probes?limit=1", headers=auth
            )
            unknown_query = await client.get(
                endpoint.url + "/api/v1/catalog/variables?unknown=x", headers=auth
            )
            duplicate_query = await client.get(
                endpoint.url + "/api/v1/catalog/registers?limit=1&limit=2",
                headers=auth,
            )
            wrong_method = await client.post(
                endpoint.url + "/api/v1/probes", headers=auth
            )
            runtime.result = failure(
                "monitor.catalog.variables",
                "MONITOR_PROVENANCE_CHANGED",
                "Monitor catalog changed",
            )
            changed = await client.get(
                endpoint.url + "/api/v1/catalog/variables", headers=auth
            )
            changed_payload = await changed.json()

        assert denied.status == 401
        assert [probes.status, variables.status, registers.status] == [200, 200, 200]
        assert runtime.calls[:3] == [
            ("monitor.probes.list", {}, None, {}),
            (
                "monitor.catalog.variables",
                {},
                None,
                {"query": "counter", "limit": "25"},
            ),
            ("monitor.catalog.registers", {}, None, {"cursor": "opaque"}),
        ]
        assert [
            bad_body.status,
            probes_query.status,
            unknown_query.status,
            duplicate_query.status,
            wrong_method.status,
        ] == [400, 400, 400, 400, 405]
        assert len(runtime.calls) == calls_after_valid + 1
        assert changed.status == 409
        assert changed_payload["operation"] == "monitor.catalog.variables"
        assert changed_payload["code"] == "MONITOR_PROVENANCE_CHANGED"

    asyncio.run(_with_service(scenario))


def test_group_pages_use_exact_query_grammar_and_fit_actual_http_body(
    tmp_path,
) -> None:
    from stm32_monitor.groups import GroupStore
    from stm32_monitor.models import WatchItem
    from stm32_toolkit.paths import WorkspacePaths

    project = tmp_path / "project"
    project.mkdir()
    paths = WorkspacePaths.from_roots(
        tmp_path / "state",
        project,
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        "monitor-1",
    )
    store = GroupStore(paths)
    selectors = tuple(
        WatchItem.variable(f"v{index:04d}" + "😀" * 507) for index in range(256)
    )
    try:
        for index in range(16):
            assert store.create_group(
                f"G{index:02d}", "d" * 1024, 250, selectors, authorized=True
            ).ok
        first_page = store.list_group_page(limit=16)
        assert first_page.ok and first_page.data.next_cursor is not None

        async def scenario(runtime, _service, endpoint) -> None:
            auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
            runtime.result = first_page
            async with aiohttp.ClientSession() as client:
                response = await client.get(
                    endpoint.url + "/api/v1/groups?limit=16", headers=auth
                )
                body = await response.read()
                payload = json.loads(body)
                calls_after_page = len(runtime.calls)
                unknown = await client.get(
                    endpoint.url + "/api/v1/groups?unknown=x", headers=auth
                )
                duplicate = await client.get(
                    endpoint.url + "/api/v1/groups?cursor=a&cursor=b", headers=auth
                )

            assert response.status == 200
            assert len(body) <= 1024 * 1024
            assert int(response.headers["Content-Length"]) == len(body)
            assert 1 <= len(payload["data"]["groups"]) <= 16
            assert payload["data"]["nextCursor"] == first_page.data.next_cursor
            assert payload["data"]["revision"] == first_page.data.revision
            assert runtime.calls[0] == (
                "monitor.groups.list",
                {},
                None,
                {"limit": "16"},
            )
            assert [unknown.status, duplicate.status] == [400, 400]
            assert len(runtime.calls) == calls_after_page

        asyncio.run(_with_service(scenario))
    finally:
        store.close()


def test_ordinary_response_actual_body_limit_fails_closed_without_payload_leak() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
        runtime.result = {"secret": "z" * (1024 * 1024)}
        async with aiohttp.ClientSession() as client:
            response = await client.get(endpoint.url + "/api/v1/status", headers=auth)
            body = await response.read()
            payload = json.loads(body)
        assert response.status == 500
        assert len(body) <= 1024 * 1024
        assert payload["code"] == "MONITOR_INTERNAL_ERROR"
        assert payload["message"] == "Monitor Service request failed"
        assert "secret" not in payload["details"]
        assert b"zzzzzzzz" not in body

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
                await runtime.live_queue.put(
                    {
                        "eventId": sequence + 1,
                        "type": "sample",
                        "data": {
                            "batch": {"sequence": sequence},
                            "serviceSubscriberDrops": 0,
                        },
                    }
                )
            await asyncio.wait_for(runtime.drop_recorded.wait(), 0.1)
            assert runtime.recorded_drops > 0
            seen: list[dict[str, object]] = []
            for _ in range(9):
                frame = await asyncio.wait_for(ws.receive(), 2)
                assert int(frame.type) == int(aiohttp.WSMsgType.TEXT)
                message = json.loads(frame.data)
                seen.append(message)
                if message["data"]["data"]["batch"]["sequence"] == 19:
                    break
            assert seen[-1]["data"]["data"]["batch"]["sequence"] == 19
            assert any(item["details"].get("subscriberDropped", 0) > 0 for item in seen)
            assert len(seen) + sum(
                item["details"].get("subscriberDropped", 0) for item in seen
            ) == 20
            assert runtime.recorded_drops == sum(
                item["details"].get("subscriberDropped", 0) for item in seen
            )
            assert any(
                item["data"]["data"]["serviceSubscriberDrops"] > 0
                for item in seen
            )
            await ws.close()

    asyncio.run(_with_service(scenario, send_delay_seconds=0.2))


def test_websocket_accepts_only_one_bounded_after_event_id() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(
                endpoint.url + "/api/v1/live?afterEventId=41", headers=headers
            )
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            assert runtime.after_event_id == 41
            await ws.close()
            for query in (
                "afterEventId=0",
                "afterEventId=-1",
                "afterEventId=true",
                "afterEventId=1&afterEventId=2",
                "unexpected=1",
            ):
                with pytest.raises(aiohttp.WSServerHandshakeError) as denied:
                    await client.ws_connect(
                        endpoint.url + "/api/v1/live?" + query, headers=headers
                    )
                assert denied.value.status == 400

    asyncio.run(_with_service(scenario))


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
        ("GET", "/api/v1/history?startNs=0&endNs=1", "monitor.history.query", None),
        ("POST", "/api/v1/exports", "monitor.exports.create", None),
        ("GET", "/api/v1/exports/export-a", "monitor.exports.get", "export-a"),
    ]

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
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


def test_verified_export_download_streams_fixed_public_headers_and_rejects_overrides() -> None:
    from stm32_monitor.exports import ExportDownload, ExportDownloadResult
    from stm32_monitor.protocol import failure

    export_id = UUID("12345678-1234-5678-9234-567812345678")
    body = b'{"value":1}\n'

    async def scenario(runtime, _service, endpoint) -> None:
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
        runtime.result = ExportDownload(
            BytesIO(body),
            export_id=export_id,
            format_name="jsonl",
            byte_count=len(body),
        )
        async with aiohttp.ClientSession() as client:
            response = await client.get(
                endpoint.url + f"/api/v1/exports/{export_id}/download",
                headers=auth,
            )
            received = await response.read()
            runtime.result = ExportDownloadResult(
                True,
                "OK",
                "",
                ExportDownload(
                    BytesIO(body),
                    export_id=export_id,
                    format_name="jsonl",
                    byte_count=len(body),
                ),
            )
            wrapped = await client.get(
                endpoint.url + f"/api/v1/exports/{export_id}/download",
                headers=auth,
            )
            assert await wrapped.read() == body
            runtime.result = ExportDownloadResult(
                False, "MONITOR_EXPORT_FAILED", "history export is unavailable", None
            )
            unavailable = await client.get(
                endpoint.url + f"/api/v1/exports/{export_id}/download",
                headers=auth,
            )
            runtime.result = failure(
                "monitor.exports.download",
                "MONITOR_REQUEST_INVALID",
                "Monitor request is invalid",
            )
            malformed_uuid = await client.get(
                endpoint.url + "/api/v1/exports/not-a-uuid/download",
                headers=auth,
            )
            malformed_payload = await malformed_uuid.json()
            runtime.result = object()
            invalid_runtime = await client.get(
                endpoint.url + f"/api/v1/exports/{export_id}/download",
                headers=auth,
            )
            calls_before_rejected_inputs = len(runtime.calls)
            ranged = await client.get(
                endpoint.url + f"/api/v1/exports/{export_id}/download",
                headers={**auth, "Range": "bytes=0-1"},
            )
            path_override = await client.get(
                endpoint.url
                + f"/api/v1/exports/{export_id}/download?path=C:%5Cprivate%5Cx",
                headers=auth,
            )
            filename_override = await client.get(
                endpoint.url
                + f"/api/v1/exports/{export_id}/download?filename=secret.jsonl",
                headers=auth,
            )

        assert response.status == 200 and received == body
        assert wrapped.status == 200
        assert unavailable.status == 409
        assert malformed_uuid.status == 409
        assert malformed_payload == {
            "protocol": endpoint.protocol,
            "toolkitVersion": endpoint.toolkit_version,
            "monitorVersion": endpoint.monitor_version,
            "ok": False,
            "operation": "monitor.exports.download",
            "code": "MONITOR_REQUEST_INVALID",
            "message": "Monitor request is invalid",
            "data": None,
            "details": {},
        }
        assert invalid_runtime.status == 500
        assert response.headers["Content-Type"] == "application/x-ndjson"
        assert response.headers["Content-Length"] == str(len(body))
        assert response.headers["Content-Disposition"] == (
            f'attachment; filename="history-{export_id}.jsonl"'
        )
        public_headers = json.dumps(dict(response.headers))
        assert "C:\\private" not in public_headers
        assert TOKEN_BYTES.hex() not in public_headers
        assert [ranged.status, path_override.status, filename_override.status] == [
            400,
            400,
            400,
        ]
        assert len(runtime.calls) == calls_before_rejected_inputs
        assert runtime.calls[0] == (
            "monitor.exports.download",
            {},
            str(export_id),
            {},
        )

    asyncio.run(_with_service(scenario))


def test_protocol_results_and_arbitrary_runtime_exceptions_are_bounded() -> None:
    from stm32_monitor.protocol import failure, success

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
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
        auth = {"Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": endpoint.url}
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


def test_websocket_closes_before_sending_an_oversized_model_valid_live_event() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        from stm32_monitor.auth import MAX_REQUEST_BYTES

        event = _oversized_model_valid_live_event()
        assert len(json.dumps(event, separators=(",", ":")).encode("utf-8")) > (
            MAX_REQUEST_BYTES
        )
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            await runtime.live_queue.put(event)
            frame = await asyncio.wait_for(ws.receive(), 2)
            assert frame.type == aiohttp.WSMsgType.CLOSE
            assert frame.data == aiohttp.WSCloseCode.MESSAGE_TOO_BIG
            assert frame.extra == "live event exceeds size limit"
            assert "SENSITIVE_PAYLOAD_MARKER" not in frame.extra
            assert TOKEN_BYTES.hex() not in frame.extra
            await asyncio.wait_for(runtime.unsubscribed.wait(), 1)

    asyncio.run(_with_service(scenario))


def test_duplicate_query_and_json_object_keys_reject_before_dispatch() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as client:
            duplicate_query = await client.get(
                endpoint.url
                + "/api/v1/history?startNs=0&startNs=1&endNs=2",
                headers=headers,
            )
            session_override = await client.get(
                endpoint.url
                + "/api/v1/history?startNs=0&endNs=1&sessionId=session-b",
                headers=headers,
            )
            workspace_override = await client.get(
                endpoint.url
                + "/api/v1/history?startNs=0&endNs=1&workspaceId=workspace-b",
                headers=headers,
            )
            duplicate_top = await client.post(
                endpoint.url + "/api/v1/groups",
                headers=headers,
                data=b'{"name":"first","name":"second"}',
            )
            duplicate_nested = await client.post(
                endpoint.url + "/api/v1/groups",
                headers=headers,
                data=b'{"items":[{"kind":"variable","expression":"a","expression":"b"}]}',
            )
        assert [
            duplicate_query.status,
            session_override.status,
            workspace_override.status,
            duplicate_top.status,
            duplicate_nested.status,
        ] == [400, 400, 400, 400, 400]
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_repeated_cancellation_of_real_partial_start_waits_for_owned_listener_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService

    site_started = asyncio.Event()
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    captured: dict[str, object] = {}
    original_site_start = web.TCPSite.start
    original_runner_cleanup = web.AppRunner.cleanup

    async def paused_site_start(site: web.TCPSite) -> None:
        await original_site_start(site)
        assert site._server is not None
        captured["port"] = site._server.sockets[0].getsockname()[1]
        site_started.set()
        await asyncio.Future()

    async def paused_cleanup(runner: web.AppRunner) -> None:
        captured["runner"] = runner
        cleanup_entered.set()
        await allow_cleanup.wait()
        await original_runner_cleanup(runner)

    monkeypatch.setattr(web.TCPSite, "start", paused_site_start)
    monkeypatch.setattr(web.AppRunner, "cleanup", paused_cleanup)
    service = MonitorService(
        FakeRuntime(),
        workspace_id="workspace-a",
        session_id="session-a",
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
    )

    async def scenario() -> None:
        starting = asyncio.create_task(service.start())
        try:
            await site_started.wait()
            port = int(captured["port"])
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            del reader

            starting.cancel("first")
            await cleanup_entered.wait()
            starting.cancel("second")
            await asyncio.sleep(0)
            assert not starting.done()
            allow_cleanup.set()
            with pytest.raises(asyncio.CancelledError):
                await starting
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", port)
            assert service.endpoint is None
        finally:
            allow_cleanup.set()
            await asyncio.gather(starting, return_exceptions=True)
            runner = captured.get("runner")
            if isinstance(runner, web.AppRunner):
                await original_runner_cleanup(runner)

    asyncio.run(scenario())


def test_partial_start_cleanup_error_has_priority_and_stop_retries_owned_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService

    captured: dict[str, int] = {}
    cleanup_calls = 0
    original_site_start = web.TCPSite.start
    original_runner_cleanup = web.AppRunner.cleanup

    async def failing_site_start(site: web.TCPSite) -> None:
        await original_site_start(site)
        assert site._server is not None
        captured["port"] = site._server.sockets[0].getsockname()[1]
        raise ValueError("SECRET start failure")

    async def fail_first_cleanup(runner: web.AppRunner) -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            raise OSError("SECRET cleanup failure")
        await original_runner_cleanup(runner)

    monkeypatch.setattr(web.TCPSite, "start", failing_site_start)
    monkeypatch.setattr(web.AppRunner, "cleanup", fail_first_cleanup)
    service = MonitorService(
        FakeRuntime(), workspace_id="workspace-a", session_id="session-a"
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="Service cleanup failed") as raised:
            await service.start()
        assert "SECRET" not in str(raised.value)
        port = captured["port"]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        await writer.wait_closed()
        del reader

        await service.stop()
        assert cleanup_calls == 2
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)

    asyncio.run(scenario())


def test_static_returns_503_before_service_is_started() -> None:
    from stm32_monitor.service import MonitorService

    async def scenario() -> None:
        service = MonitorService(
            FakeRuntime(), workspace_id="workspace-a", session_id="session-a"
        )
        response = await service._static(None)
        assert response.status == 503
        assert response.body == b""

    asyncio.run(scenario())


def test_authorize_rejects_before_service_has_an_auth() -> None:
    from stm32_monitor.service import MonitorService, _ServiceFailure

    async def scenario() -> None:
        service = MonitorService(
            FakeRuntime(), workspace_id="workspace-a", session_id="session-a"
        )
        with pytest.raises(_ServiceFailure) as caught:
            service._authorize(None, bootstrap=True)
        assert caught.value.code == "MONITOR_SERVICE_UNAVAILABLE"

    asyncio.run(scenario())


def test_raise_cleanup_error_rejects_non_exception_base() -> None:
    from stm32_monitor.service import MonitorService

    with pytest.raises(BaseException) as caught:
        MonitorService._raise_cleanup_error(BaseException("SECRET boom"))
    assert "SECRET" in str(caught.value)


def test_restart_cleans_owned_runner_before_rebinding() -> None:
    from stm32_monitor.service import MonitorService

    class FakeRunner:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup(self) -> None:
            self.cleanup_calls += 1

    async def scenario() -> None:
        service = MonitorService(
            FakeRuntime(),
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
        )
        runner = FakeRunner()
        service._runner = runner
        endpoint = await service.start()
        assert runner.cleanup_calls == 1
        assert service.endpoint == endpoint
        await service.stop()

    asyncio.run(scenario())


def test_reject_overrides_aborts_huge_payload_before_dispatch() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
            "Content-Type": "application/json",
        }
        body = json.dumps({"nested": [{"k": index} for index in range(20_010)]}).encode()
        async with aiohttp.ClientSession() as client:
            response = await client.post(
                endpoint.url + "/api/v1/groups", headers=headers, data=body
            )
            assert response.status == 400
            assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_serve_ui_loads_packaged_dist_when_root_is_omitted() -> None:
    from stm32_monitor.service import MonitorService

    async def scenario() -> None:
        runtime = FakeRuntime()
        service = MonitorService(
            runtime,
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
            serve_ui=True,
        )
        endpoint = await service.start()
        try:
            headers = {
                "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
                "Origin": endpoint.url,
            }
            async with aiohttp.ClientSession() as client:
                response = await client.get(endpoint.url + "/", headers=headers)
                assert response.status == 200
                assert "text/html" in response.headers["Content-Type"]
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_live_drops_oldest_when_runtime_has_no_drop_recorder() -> None:
    class NoRecorderRuntime(FakeRuntime):
        record_service_drops = None  # type: ignore[assignment]

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            for sequence in range(20):
                await runtime.live_queue.put(
                    {
                        "eventId": sequence + 1,
                        "type": "sample",
                        "data": {
                            "batch": {"sequence": sequence},
                            "serviceSubscriberDrops": 0,
                        },
                    }
                )
            # Produce drains the unbounded source into the bounded send queue;
            # once the source is empty, the send queue has evicted old frames
            # without calling a (missing) drop recorder.
            for _ in range(100):
                if runtime.live_queue.qsize() == 0:
                    break
                await asyncio.sleep(0.01)
            assert runtime.live_queue.qsize() == 0
            await ws.close()

    asyncio.run(
        _with_service(scenario, send_delay_seconds=0.2, runtime_factory=NoRecorderRuntime)
    )


def test_start_failure_with_successful_cleanup_raises_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService

    async def failing_site_start(_site: web.TCPSite) -> None:
        raise ValueError("SECRET start boom")

    monkeypatch.setattr(web.TCPSite, "start", failing_site_start)
    service = MonitorService(
        FakeRuntime(), workspace_id="workspace-a", session_id="session-a"
    )

    async def scenario() -> None:
        with pytest.raises(ValueError, match="SECRET"):
            await service.start()

    asyncio.run(scenario())


def test_start_rejects_wrong_bind_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService

    monkeypatch.setattr(
        web.AppRunner, "addresses", property(lambda self: [("0.0.0.0", 80)])
    )
    service = MonitorService(
        FakeRuntime(), workspace_id="workspace-a", session_id="session-a"
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError):
            await service.start()

    asyncio.run(scenario())


def test_chunked_oversized_body_rejected_before_dispatch() -> None:
    from stm32_monitor.auth import MAX_REQUEST_BYTES

    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
            "Content-Type": "application/json",
        }
        body = b"x" * (MAX_REQUEST_BYTES + 10)
        async with aiohttp.ClientSession() as client:
            response = await client.post(
                endpoint.url + "/api/v1/groups",
                headers=headers,
                data=body,
                chunked=True,
            )
            assert response.status == 413
            assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_stop_surfaces_owned_cleanup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService

    async def failing_cleanup(_runner: web.AppRunner) -> None:
        raise OSError("SECRET cleanup boom")

    monkeypatch.setattr(web.AppRunner, "cleanup", failing_cleanup)
    service = MonitorService(
        FakeRuntime(),
        workspace_id="workspace-a",
        session_id="session-a",
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
    )

    async def scenario() -> None:
        await service.start()
        with pytest.raises(RuntimeError, match="Service cleanup failed") as raised:
            await service.stop()
        assert "SECRET" not in str(raised.value)

    asyncio.run(scenario())


def test_live_sends_undropped_event_without_enrichment() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            await runtime.live_queue.put(
                {
                    "eventId": 1,
                    "type": "sample",
                    "data": {"batch": {"sequence": 0}, "serviceSubscriberDrops": 0},
                }
            )
            frame = await asyncio.wait_for(ws.receive(), 2)
            assert int(frame.type) == int(aiohttp.WSMsgType.TEXT)
            message = json.loads(frame.data)
            assert message["details"] == {"subscriberDropped": 0}
            assert message["data"]["data"]["serviceSubscriberDrops"] == 0
            await ws.close()

    asyncio.run(_with_service(scenario))


def test_json_constant_in_body_rejected_before_dispatch() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as client:
            for body in (b'{"name": NaN}', b'{"name": Infinity}'):
                response = await client.post(
                    endpoint.url + "/api/v1/groups", headers=headers, data=body
                )
                assert response.status == 400
        assert runtime.calls == []

    asyncio.run(_with_service(scenario))


def test_live_enrichment_skips_non_sample_and_malformed_sample_data() -> None:
    async def scenario(runtime, _service, endpoint) -> None:
        headers = {
            "Authorization": f"Bearer {TOKEN_BYTES.hex()}",
            "Origin": endpoint.url,
        }
        async with aiohttp.ClientSession() as client:
            ws = await client.ws_connect(endpoint.url + "/api/v1/live", headers=headers)
            await asyncio.wait_for(runtime.subscribed.wait(), 1)
            for sequence in range(20):
                await runtime.live_queue.put(
                    {
                        "eventId": sequence + 1,
                        "type": "sample",
                        "data": {
                            "batch": {"sequence": sequence},
                            "serviceSubscriberDrops": 0,
                        },
                    }
                )
            await runtime.live_queue.put(
                {"eventId": 21, "type": "state", "data": {"stateRevision": 1}}
            )
            await runtime.live_queue.put(
                {"eventId": 22, "type": "sample", "data": "not-a-mapping"}
            )
            await runtime.live_queue.put(
                {
                    "eventId": 23,
                    "type": "sample",
                    "data": {"batch": {"sequence": 1}, "serviceSubscriberDrops": "bad"},
                }
            )
            # Let the slow sender process every queued event, then drain the
            # frames so the socket keeps flowing.
            await asyncio.sleep(1.5)
            try:
                while True:
                    frame = await asyncio.wait_for(ws.receive(), 0.2)
                    if int(frame.type) != int(aiohttp.WSMsgType.TEXT):
                        break
            except asyncio.TimeoutError:
                pass
            await ws.close()

    asyncio.run(_with_service(scenario, send_delay_seconds=0.1))
