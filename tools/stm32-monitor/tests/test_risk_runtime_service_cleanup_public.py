from __future__ import annotations

import asyncio
from pathlib import Path

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
