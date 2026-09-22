from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import pytest
from test_runtime import FakeExporter, FakeStore, _project, _ready_service


def _runtime(
    *,
    group_store_factory=FakeStore,
    history_store_factory=FakeStore,
    exporter_factory=FakeExporter,
    service_factory=None,
):
    from stm32_monitor.runtime import MonitorRuntime

    return MonitorRuntime(
        group_store_factory=group_store_factory,
        history_store_factory=history_store_factory,
        exporter_factory=exporter_factory,
        sampler_factory=lambda *_args, **_kwargs: object(),
        observation_factory=lambda *_args, **_kwargs: None,
        service_factory=service_factory
        or (lambda *args, **kwargs: _ready_service(*args, **kwargs)),
    )


def test_public_stop_reports_record_and_dependency_cleanup_failures_then_reuses(
    tmp_path: Path,
) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntimeError

    class ClosingStore:
        def __init__(self, _paths, *, fail: bool = False) -> None:
            self.close_calls = 0
            self._fail = fail

        def close(self) -> None:
            self.close_calls += 1
            if self._fail:
                raise RuntimeError("store close failure")

    class ClosingExporter:
        def __init__(self, _paths, _history) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    project = _project(tmp_path)
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
    groups: list[ClosingStore] = []
    histories: list[ClosingStore] = []
    exporters: list[ClosingExporter] = []
    services = []

    def group_factory(paths):
        store = ClosingStore(paths, fail=True)
        groups.append(store)
        return store

    def history_factory(paths):
        store = ClosingStore(paths)
        histories.append(store)
        return store

    def exporter_factory(paths, history):
        exporter = ClosingExporter(paths, history)
        exporters.append(exporter)
        return exporter

    def service_factory(*args, **kwargs):
        service = _ready_service(*args, **kwargs)
        services.append(service)
        return service

    async def scenario() -> None:
        runtime = _runtime(
            group_store_factory=group_factory,
            history_store_factory=history_factory,
            exporter_factory=exporter_factory,
            service_factory=service_factory,
        )
        await runtime.start(config)
        record = runtime.runtime_record
        record.unlink()
        record.mkdir()
        try:
            with pytest.raises(MonitorRuntimeError) as caught:
                await runtime.stop()
            assert caught.value.code == "MONITOR_CLEANUP_FAILED"
            assert caught.value.message == "Monitor runtime cleanup failed"
            await runtime.wait_closed()
            assert groups[0].close_calls == 1
            assert histories[0].close_calls == 1
            assert exporters[0].close_calls == 1
            assert services[0].stop_calls == 1
        finally:
            if record.is_dir():
                record.rmdir()

        replacement = _runtime()
        await replacement.start(
            MonitorConfig(config.project_root, config.data_root, config.session_id)
        )
        await replacement.stop()

    asyncio.run(scenario())


def test_public_invalid_token_factory_failed_start_then_fresh_service_start_stop() -> (
    None
):
    from stm32_monitor.service import MonitorService
    from test_service import TOKEN_BYTES, FakeRuntime

    async def scenario() -> None:
        runtime = FakeRuntime()
        rejected = MonitorService(
            runtime,
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=lambda _size: b"x",
        )
        with pytest.raises(
            ValueError,
            match="Monitor token factory must return exactly 32 bytes",
        ):
            await rejected.start()
        assert rejected.endpoint is None
        await rejected.stop()

        replacement = MonitorService(
            runtime,
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
        )
        endpoint = await replacement.start()
        assert endpoint.host == "127.0.0.1"
        assert endpoint.workspace_id == "workspace-a"
        assert endpoint.session_id == "session-a"
        await replacement.stop()
        assert replacement.endpoint is None

    asyncio.run(scenario())


async def _wait_for_event(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


async def _assert_listener_open(host: str, port: int) -> None:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=5
    )
    writer.close()
    await asyncio.wait_for(writer.wait_closed(), timeout=5)
    del reader


async def _assert_listener_closed(host: str, port: int) -> None:
    with pytest.raises(OSError):
        await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)


async def _assert_authenticated(endpoint) -> None:
    headers = {
        "Authorization": f"Bearer {endpoint.token}",
        "Origin": endpoint.url,
    }
    async with aiohttp.ClientSession() as client:
        response = await asyncio.wait_for(
            client.get(endpoint.url + "/api/v1/status", headers=headers), timeout=5
        )
        payload = await response.json()
    assert response.status == 200
    assert payload["data"]["operation"] == "monitor.status"


async def _cancel_twice(task: asyncio.Task[object]) -> None:
    task.cancel("first cancellation")
    await asyncio.sleep(0)
    task.cancel("second cancellation")
    await asyncio.sleep(0)
    assert not task.done()


def test_public_partial_start_cancel_precedes_start_error_and_reuses_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService
    from test_service import TOKEN_BYTES, FakeRuntime

    async def scenario() -> None:
        token_valid = False

        def token_factory(size: int) -> bytes:
            return TOKEN_BYTES if token_valid and size == 32 else b"x"

        original_cleanup = web.AppRunner.cleanup
        cleanup_entered = asyncio.Event()
        cleanup_release = asyncio.Event()
        cleanup_finished = asyncio.Event()
        captured_addresses: list[tuple[str, int]] = []

        async def gated_cleanup(runner: web.AppRunner) -> None:
            addresses = tuple(runner.addresses)
            assert len(addresses) == 1
            captured_addresses.append((str(addresses[0][0]), int(addresses[0][1])))
            cleanup_entered.set()
            await cleanup_release.wait()
            try:
                await original_cleanup(runner)
            finally:
                cleanup_finished.set()

        monkeypatch.setattr(web.AppRunner, "cleanup", gated_cleanup)
        service = MonitorService(
            FakeRuntime(),
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=token_factory,
        )
        starting: asyncio.Task[object] | None = None
        try:
            starting = asyncio.create_task(service.start())
            await _wait_for_event(cleanup_entered)
            host, port = captured_addresses[0]
            assert host == "127.0.0.1"
            assert 0 < port < 65536
            await _assert_listener_open(host, port)

            await _cancel_twice(starting)
            cleanup_release.set()
            await _wait_for_event(cleanup_finished)
            await _assert_listener_closed(host, port)
            assert service.endpoint is None
            with pytest.raises(asyncio.CancelledError) as cancelled:
                await starting
            assert str(cancelled.value) == "first cancellation"

            token_valid = True
            monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
            endpoint = await service.start()
            await _assert_authenticated(endpoint)
            await service.stop()
            assert service.endpoint is None
        finally:
            cleanup_release.set()
            if starting is not None and not starting.done():
                await asyncio.wait_for(
                    asyncio.gather(starting, return_exceptions=True), timeout=5
                )
            monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
            await service.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "retry_mode", ("failure", "cancelled"), ids=("retry-fails", "retry-cancelled")
)
def test_public_partial_start_cleanup_retry_is_sanitized_or_cancelled(
    monkeypatch: pytest.MonkeyPatch, retry_mode: str
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService
    from test_service import TOKEN_BYTES, FakeRuntime

    async def scenario() -> None:
        token_valid = False
        cleanup_calls = 0
        captured_addresses: list[tuple[str, int]] = []
        retry_entered = asyncio.Event()
        retry_release = asyncio.Event()
        retry_finished = asyncio.Event()
        original_cleanup = web.AppRunner.cleanup

        def token_factory(size: int) -> bytes:
            return TOKEN_BYTES if token_valid and size == 32 else b"x"

        async def controlled_cleanup(runner: web.AppRunner) -> None:
            nonlocal cleanup_calls
            cleanup_calls += 1
            addresses = tuple(runner.addresses)
            assert len(addresses) == 1
            captured_addresses.append((str(addresses[0][0]), int(addresses[0][1])))
            if cleanup_calls == 1:
                raise OSError("SECRET cleanup failure")
            if cleanup_calls == 2 and retry_mode == "failure":
                raise OSError("SECRET cleanup failure")
            if cleanup_calls == 2:
                retry_entered.set()
                await retry_release.wait()
            try:
                await original_cleanup(runner)
            finally:
                if cleanup_calls == 2:
                    retry_finished.set()

        monkeypatch.setattr(web.AppRunner, "cleanup", controlled_cleanup)
        service = MonitorService(
            FakeRuntime(),
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=token_factory,
        )
        retrying: asyncio.Task[object] | None = None
        try:
            with pytest.raises(RuntimeError) as first_error:
                await service.start()
            assert str(first_error.value) == "Monitor Service cleanup failed"
            assert "SECRET" not in str(first_error.value)
            assert service.endpoint is None
            host, port = captured_addresses[0]
            assert host == "127.0.0.1"
            assert 0 < port < 65536
            await _assert_listener_open(host, port)

            if retry_mode == "failure":
                with pytest.raises(RuntimeError) as retry_error:
                    await service.start()
                assert str(retry_error.value) == "Monitor Service cleanup failed"
                assert "SECRET" not in str(retry_error.value)
                assert cleanup_calls == 2
                await _assert_listener_open(host, port)
                monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
                await service.stop()
                await _assert_listener_closed(host, port)
            else:
                retrying = asyncio.create_task(service.start())
                await _wait_for_event(retry_entered)
                assert cleanup_calls == 2
                await _assert_listener_open(host, port)
                await _cancel_twice(retrying)
                retry_release.set()
                await _wait_for_event(retry_finished)
                await _assert_listener_closed(host, port)
                assert service.endpoint is None
                with pytest.raises(asyncio.CancelledError) as cancelled:
                    await retrying
                assert str(cancelled.value) == "first cancellation"
                monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)

            token_valid = True
            endpoint = await service.start()
            await _assert_authenticated(endpoint)
            await service.stop()
            assert service.endpoint is None
        finally:
            retry_release.set()
            if retrying is not None and not retrying.done():
                await asyncio.wait_for(
                    asyncio.gather(retrying, return_exceptions=True), timeout=5
                )
            monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
            await service.stop()

    asyncio.run(scenario())


def test_public_stop_cancel_waits_for_listener_cleanup_then_restarts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from stm32_monitor.service import MonitorService
    from test_service import TOKEN_BYTES, FakeRuntime

    async def scenario() -> None:
        original_cleanup = web.AppRunner.cleanup
        cleanup_entered = asyncio.Event()
        cleanup_release = asyncio.Event()
        cleanup_finished = asyncio.Event()
        captured_addresses: list[tuple[str, int]] = []

        def token_factory(size: int) -> bytes:
            return TOKEN_BYTES if size == 32 else b""

        service = MonitorService(
            FakeRuntime(),
            workspace_id="workspace-a",
            session_id="session-a",
            token_factory=token_factory,
        )
        stopping: asyncio.Task[object] | None = None
        try:
            endpoint = await service.start()
            await _assert_authenticated(endpoint)

            async def gated_cleanup(runner: web.AppRunner) -> None:
                addresses = tuple(runner.addresses)
                assert len(addresses) == 1
                captured_addresses.append(
                    (str(addresses[0][0]), int(addresses[0][1]))
                )
                cleanup_entered.set()
                await cleanup_release.wait()
                try:
                    await original_cleanup(runner)
                finally:
                    cleanup_finished.set()

            monkeypatch.setattr(web.AppRunner, "cleanup", gated_cleanup)
            stopping = asyncio.create_task(service.stop())
            await _wait_for_event(cleanup_entered)
            host, port = captured_addresses[0]
            assert host == "127.0.0.1"
            assert 0 < port < 65536
            await _assert_listener_open(host, port)
            await _cancel_twice(stopping)
            cleanup_release.set()
            await _wait_for_event(cleanup_finished)
            await _assert_listener_closed(host, port)
            assert service.endpoint is None
            with pytest.raises(asyncio.CancelledError) as cancelled:
                await stopping
            assert str(cancelled.value) == "first cancellation"

            monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
            endpoint = await service.start()
            await _assert_authenticated(endpoint)
            await service.stop()
            assert service.endpoint is None
        finally:
            cleanup_release.set()
            if stopping is not None and not stopping.done():
                await asyncio.wait_for(
                    asyncio.gather(stopping, return_exceptions=True), timeout=5
                )
            monkeypatch.setattr(web.AppRunner, "cleanup", original_cleanup)
            await service.stop()

    asyncio.run(scenario())
