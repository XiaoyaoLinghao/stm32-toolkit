from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp import web

from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.probe.backend import ProbeDescriptor
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
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
    data_root: Path,
    *,
    session_root: Path | None = None,
    operation_level: OperationLevel = OperationLevel.OBSERVE,
    project_root: Path | None = None,
) -> ProbeServiceConfig:
    return ProbeServiceConfig(
        probe_id="probe-a",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=operation_level,
        session_root=session_root
        or data_root / "projects" / "workspace-a" / "sessions" / "session-a",
        project_root=project_root,
    )


def make_supervisor(
    data_root: Path,
    backend_factory,
    *,
    session_root: Path | None = None,
    operation_level: OperationLevel = OperationLevel.OBSERVE,
    project_root: Path | None = None,
) -> ProbeServiceSupervisor:
    return ProbeServiceSupervisor(
        config=make_config(
            data_root,
            session_root=session_root,
            operation_level=operation_level,
            project_root=project_root,
        ),
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


def test_cancelled_supervisor_start_rolls_back_backend_listener_and_lease(
    tmp_path: Path, monkeypatch
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        factory = BackendFactory()
        supervisor = make_supervisor(data_root, factory)
        entered = asyncio.Event()
        bound_port: list[int] = []
        captured_runners = []
        calls = 0
        original_start = web.TCPSite.start

        async def phased_start(site) -> None:
            nonlocal calls
            calls += 1
            await original_start(site)
            if calls == 1:
                captured_runners.append(site._runner)
                bound_port.append(int(site._runner.addresses[0][1]))
                entered.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(web.TCPSite, "start", phased_start)
        starting = asyncio.create_task(supervisor.start())
        await entered.wait()
        starting.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await starting

            assert supervisor.endpoint is None
            assert factory.backends[0].closed is True
            assert factory.backends[0].close_attempts == 1
            assert not ProbeLeaseManager(data_root).record_path("probe-a").exists()
            with pytest.raises(OSError):
                await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", bound_port[0]), timeout=0.5
                )

            endpoint = await supervisor.start()
            assert supervisor.endpoint is endpoint
            assert len(factory.backends) == 2
            await supervisor.stop()
        finally:
            for runner in captured_runners:
                await runner.cleanup()

    run(scenario())


def test_cancelled_supervisor_stop_retains_ownership_until_cleanup_and_retries(
    tmp_path: Path,
) -> None:
    class BlockingBackend(RecordingBackend):
        def __init__(self) -> None:
            super().__init__()
            self.entered = __import__("threading").Event()
            self.release = __import__("threading").Event()

        def close(self) -> None:
            self.entered.set()
            self.release.wait()
            super().close()

    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        first_backend = BlockingBackend()
        replacements: list[RecordingBackend] = []

        def factory():
            if not replacements:
                replacements.append(first_backend)
                return first_backend
            backend = RecordingBackend()
            replacements.append(backend)
            return backend

        supervisor = make_supervisor(data_root, factory)
        endpoint = await supervisor.start()
        owned_service = supervisor._service
        assert owned_service is not None
        stopping = asyncio.create_task(supervisor.stop())
        assert await asyncio.to_thread(first_backend.entered.wait, 2)
        stopping.cancel()
        await asyncio.sleep(0)

        remained_pending = not stopping.done()
        retained_endpoint = supervisor.endpoint is endpoint
        retained_service = supervisor._service is owned_service
        retained_backend = supervisor._backend is first_backend
        first_backend.release.set()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        await owned_service.stop()
        assert remained_pending
        assert retained_endpoint
        assert retained_service
        assert retained_backend
        assert supervisor.endpoint is None
        assert supervisor._service is None
        assert supervisor._backend is None
        assert first_backend.closed is True
        assert not endpoint.record_path.exists()

        replacement_endpoint = await supervisor.start()
        assert replacement_endpoint.lease_id != endpoint.lease_id
        await supervisor.stop()
        assert replacements[1].closed is True

    run(scenario())


def test_cancelled_supervisor_stop_during_service_dispatch_still_cleans(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        backend = RecordingBackend()
        supervisor = make_supervisor(data_root, lambda: backend)
        endpoint = await supervisor.start()
        service = supervisor._service
        assert service is not None
        original_stop = service.stop
        entered = asyncio.Event()
        proceed = asyncio.Event()

        async def phased_stop() -> None:
            entered.set()
            await proceed.wait()
            await original_stop()

        service.stop = phased_stop
        stopping = asyncio.create_task(supervisor.stop())
        await entered.wait()
        stopping.cancel()
        await asyncio.sleep(0)
        remained_pending = not stopping.done()
        retained_endpoint = supervisor.endpoint is endpoint
        proceed.set()
        try:
            with pytest.raises(asyncio.CancelledError):
                await stopping
        finally:
            service.stop = original_stop
            await original_stop()

        assert remained_pending
        assert retained_endpoint
        assert backend.closed is True
        assert not endpoint.record_path.exists()
        assert supervisor.endpoint is None

    run(scenario())


def test_supervisor_cleanup_failure_wins_over_concurrent_cancellation(
    tmp_path: Path,
) -> None:
    class BlockingFailingBackend(RecordingBackend):
        def __init__(self) -> None:
            super().__init__()
            self.entered = __import__("threading").Event()
            self.release = __import__("threading").Event()

        def close(self) -> None:
            self.entered.set()
            self.release.wait()
            super().close()
            raise RuntimeError("supervisor backend cleanup failed")

    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        backend = BlockingFailingBackend()
        supervisor = make_supervisor(data_root, lambda: backend)
        endpoint = await supervisor.start()
        stopping = asyncio.create_task(supervisor.stop())
        assert await asyncio.to_thread(backend.entered.wait, 2)

        stopping.cancel()
        await asyncio.sleep(0)
        assert not stopping.done()
        assert supervisor.endpoint is endpoint
        backend.release.set()
        with pytest.raises(RuntimeError, match="supervisor backend cleanup failed"):
            await stopping

        assert backend.closed is True
        assert supervisor.endpoint is None
        assert supervisor._service is None
        assert supervisor._backend is None
        assert not endpoint.record_path.exists()
        lease_record = __import__("json").loads(
            ProbeLeaseManager(data_root)
            .record_path("probe-a")
            .read_text(encoding="utf-8")
        )
        assert lease_record == {
            "leaseId": endpoint.lease_id,
            "schemaVersion": 1,
            "state": "released",
        }

    run(scenario())


def test_supervisor_drain_requires_running_service(tmp_path: Path) -> None:
    async def scenario() -> None:
        supervisor = make_supervisor(tmp_path / "plugin-data", BackendFactory())
        with pytest.raises(ProbeServiceError) as error:
            await supervisor.drain_modifications()
        assert error.value.code == "PROBE_SERVICE_UNAVAILABLE"

    run(scenario())


def test_supervisor_drain_blocks_modify_and_keeps_observe_available(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "firmware.elf").write_bytes(b"firmware")
        backend = RecordingBackend()
        supervisor = make_supervisor(
            data_root,
            lambda: backend,
            operation_level=OperationLevel.MODIFY,
            project_root=project_root,
        )
        endpoint = await supervisor.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            await supervisor.drain_modifications()
            with pytest.raises(ProbeClientError) as error:
                await client.program_verified_elf(
                    "firmware.elf", hashlib.sha256(b"firmware").hexdigest(), 8
                )
            assert error.value.code == "PROBE_MODIFICATIONS_DRAINING"
            assert backend.flashed_images == []
            assert await client.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
        finally:
            await client.close()
            await supervisor.stop()

    run(scenario())
