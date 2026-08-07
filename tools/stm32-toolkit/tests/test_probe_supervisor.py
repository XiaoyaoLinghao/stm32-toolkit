from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.probe.backend import ProbeDescriptor
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.supervisor import (
    ProbeServiceConfig,
    ProbeServiceSupervisor,
)
from stm32_toolkit.probe.service import ProbeServiceError


class RecordingBackend(FakeProbeBackend):
    def __init__(self) -> None:
        super().__init__(
            probes=(
                ProbeDescriptor(
                    "probe-a", "STMicroelectronics", "ST-LINK/V3", None
                ),
            ),
            memory={0x20000000: b"\x01\x02\x03\x04"},
            registers={"r0": 7},
        )
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        super().close()


class FailsFirstCloseBackend(RecordingBackend):
    def close(self) -> None:
        super().close()
        if self.close_attempts == 1:
            raise RuntimeError("backend close failed")


class BackendFactory:
    def __init__(self) -> None:
        self.backends: list[RecordingBackend] = []
        self.fail_next = False

    def __call__(self) -> RecordingBackend:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("backend construction failed")
        backend = RecordingBackend()
        self.backends.append(backend)
        return backend


def make_config(
    data_root: Path, *, session_root: Path | None = None
) -> ProbeServiceConfig:
    return ProbeServiceConfig(
        probe_id="probe-a",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        session_root=session_root
        or data_root / "projects" / "workspace-a" / "sessions" / "session-a",
    )


def make_supervisor(
    data_root: Path,
    backend_factory,
    *,
    session_root: Path | None = None,
) -> ProbeServiceSupervisor:
    return ProbeServiceSupervisor(
        config=make_config(data_root, session_root=session_root),
        lease_manager=ProbeLeaseManager(data_root),
        backend_factory=backend_factory,
    )


def run(coroutine):
    return asyncio.run(coroutine)


def test_concurrent_start_and_stop_share_one_owned_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        supervisor = make_supervisor(data_root, factory)

        endpoints = await asyncio.gather(*(supervisor.start() for _ in range(12)))
        endpoint = endpoints[0]
        assert all(item is endpoint for item in endpoints)
        assert supervisor.endpoint is endpoint
        assert len(factory.backends) == 1

        await asyncio.gather(*(supervisor.stop() for _ in range(12)))
        assert supervisor.endpoint is None
        assert factory.backends[0].close_attempts == 1
        assert not endpoint.record_path.exists()

        await supervisor.stop()
        assert factory.backends[0].close_attempts == 1

    run(scenario())


def test_restart_creates_a_new_backend_endpoint_and_lease(tmp_path: Path) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        supervisor = make_supervisor(data_root, factory)

        first = await supervisor.start()
        await supervisor.stop()
        second = await supervisor.start()
        try:
            assert second is not first
            assert second.lease_id != first.lease_id
            assert second.token != first.token
            assert len(factory.backends) == 2
            assert factory.backends[0].close_attempts == 1
            assert factory.backends[1].close_attempts == 0
        finally:
            await supervisor.stop()

        assert factory.backends[1].close_attempts == 1

    run(scenario())


def test_backend_factory_failure_publishes_no_state_and_can_retry(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        factory.fail_next = True
        supervisor = make_supervisor(data_root, factory)

        with pytest.raises(RuntimeError, match="backend construction failed"):
            await supervisor.start()
        assert supervisor.endpoint is None
        assert factory.backends == []

        endpoint = await supervisor.start()
        try:
            assert supervisor.endpoint is endpoint
            assert len(factory.backends) == 1
        finally:
            await supervisor.stop()

    run(scenario())


def test_service_start_failure_closes_only_the_new_backend(tmp_path: Path) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        supervisor = make_supervisor(
            data_root,
            factory,
            session_root=tmp_path / "outside-plugin-data" / "session-a",
        )

        with pytest.raises(ProbeServiceError) as error:
            await supervisor.start()

        assert error.value.code == "PROBE_SESSION_UNSAFE"
        assert supervisor.endpoint is None
        assert len(factory.backends) == 1
        assert factory.backends[0].close_attempts == 1
        await supervisor.stop()
        assert factory.backends[0].close_attempts == 1

    run(scenario())


def test_async_context_manager_stops_after_body_cancellation(tmp_path: Path) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        supervisor = make_supervisor(data_root, factory)
        entered = asyncio.Event()
        endpoint_holder = []

        async def worker() -> None:
            async with supervisor as endpoint:
                endpoint_holder.append(endpoint)
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(worker())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        endpoint = endpoint_holder[0]
        assert supervisor.endpoint is None
        assert factory.backends[0].close_attempts == 1
        assert not endpoint.record_path.exists()

    run(scenario())


def test_stop_clears_supervisor_state_before_backend_close_error(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        backend = FailsFirstCloseBackend()
        supervisor = make_supervisor(data_root, lambda: backend)
        endpoint = await supervisor.start()

        with pytest.raises(RuntimeError, match="backend close failed"):
            await supervisor.stop()
        assert supervisor.endpoint is None
        assert not endpoint.record_path.exists()
        assert backend.close_attempts == 1

        await supervisor.stop()
        assert backend.close_attempts == 1

    run(scenario())


def test_start_and_stop_do_not_terminate_an_unrelated_process(tmp_path: Path) -> None:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        async def scenario() -> None:
            data_root = tmp_path / "plugin-data"
            factory = BackendFactory()
            supervisor = make_supervisor(data_root, factory)
            await supervisor.start()
            await supervisor.stop()

        run(scenario())
        assert sentinel.poll() is None
    finally:
        sentinel.terminate()
        try:
            sentinel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sentinel.kill()
            sentinel.wait(timeout=5)

    assert sentinel.returncode is not None
