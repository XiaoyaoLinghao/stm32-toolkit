from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from test_runtime import (
    FakeEndpoint,
    FakeExporter,
    FakeStore,
    _project,
    _protocol_runtime,
)


def test_failed_start_cancellation_waits_for_cleanup_and_releases_workspace(
    tmp_path: Path,
) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError

    project = _project(tmp_path)
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    closed: list[str] = []

    class ClosingStore(FakeStore):
        def __init__(self, paths, name: str) -> None:
            super().__init__(paths)
            self.name = name
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1
            closed.append(self.name)

    class ClosingExporter(FakeExporter):
        def __init__(self, paths, history) -> None:
            super().__init__(paths, history)
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1
            closed.append("exporter")

    class InvalidEndpointService:
        def __init__(self, *_args, **kwargs) -> None:
            self.endpoint = FakeEndpoint(
                host="0.0.0.0",
                workspace_id=kwargs["workspace_id"],
                session_id=kwargs["session_id"],
            )
            self.start_calls = 0
            self.close_calls = 0

        async def start(self):
            self.start_calls += 1
            return self.endpoint

        async def close(self) -> None:
            self.close_calls += 1
            cleanup_entered.set()
            await allow_cleanup.wait()
            closed.append("service")

    groups: list[ClosingStore] = []
    histories: list[ClosingStore] = []
    exporters: list[ClosingExporter] = []
    services: list[InvalidEndpointService] = []

    def group_factory(paths):
        store = ClosingStore(paths, "groups")
        groups.append(store)
        return store

    def history_factory(paths):
        store = ClosingStore(paths, "history")
        histories.append(store)
        return store

    def exporter_factory(paths, history):
        exporter = ClosingExporter(paths, history)
        exporters.append(exporter)
        return exporter

    def service_factory(*args, **kwargs):
        service = InvalidEndpointService(*args, **kwargs)
        services.append(service)
        return service

    def make_runtime() -> MonitorRuntime:
        return MonitorRuntime(
            group_store_factory=group_factory,
            history_store_factory=history_factory,
            exporter_factory=exporter_factory,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=service_factory,
        )

    async def scenario() -> None:
        runtime = make_runtime()
        starting = asyncio.create_task(runtime.start(config))
        contender: MonitorRuntime | None = None
        replacement: MonitorRuntime | None = None
        replacement_started = False
        try:
            await asyncio.wait_for(cleanup_entered.wait(), timeout=5)
            assert services[0].start_calls == 1
            assert services[0].endpoint.host == "0.0.0.0"
            assert not starting.done()

            starting.cancel("caller cancellation during owned cleanup")
            scheduling_barrier = asyncio.Event()
            asyncio.get_running_loop().call_soon(scheduling_barrier.set)
            await asyncio.wait_for(scheduling_barrier.wait(), timeout=5)
            assert not starting.done()

            contender, contender_config, *_ = _protocol_runtime(
                tmp_path / "contender"
            )
            contender_config = MonitorConfig(
                project, config.data_root, config.session_id
            )
            with pytest.raises(MonitorRuntimeError) as busy:
                await asyncio.wait_for(contender.start(contender_config), timeout=5)
            assert busy.value.code == "MONITOR_RUNTIME_BUSY"
            assert not starting.done()

            allow_cleanup.set()
            with pytest.raises(asyncio.CancelledError):
                await starting

            assert closed == ["service", "exporter", "history", "groups"]
            assert services[0].close_calls == 1
            assert exporters[0].close_calls == 1
            assert histories[0].close_calls == 1
            assert groups[0].close_calls == 1

            replacement, replacement_config, *_ = _protocol_runtime(
                tmp_path / "replacement"
            )
            replacement_config = MonitorConfig(
                project, config.data_root, config.session_id
            )
            await replacement.start(replacement_config)
            replacement_started = True
            await replacement.stop()
            replacement_started = False
        finally:
            allow_cleanup.set()
            if not starting.done():
                starting.cancel("cleanup finalizer")
            await asyncio.wait_for(
                asyncio.gather(starting, return_exceptions=True), timeout=5
            )
            if contender is not None:
                await asyncio.wait_for(contender.stop(), timeout=5)
            if replacement is not None and replacement_started:
                await asyncio.wait_for(replacement.stop(), timeout=5)

    asyncio.run(scenario())
