from __future__ import annotations

import asyncio
import gc
import json
import os
import stat
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.lease import (
    ProcessIdentity,
    ProbeLeaseManager,
    _default_health_check,
)
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.service import ProbeEndpoint, ProbeService, ProbeServiceError
from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.probe.backend import ProbeDescriptor


NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)
IDENTITY = ProcessIdentity(4300, "start-4300", "boot-a")


def fake_backend() -> FakeProbeBackend:
    return FakeProbeBackend(
        probes=(
            ProbeDescriptor("probe-a", "STMicroelectronics", "ST-LINK/V3", None),
        ),
        memory={0x20000000: b"\x01\x02\x03\x04"},
        registers={"r0": 7, "pc": 0x08000101},
    )


def lease_manager(data_root: Path) -> ProbeLeaseManager:
    return ProbeLeaseManager(
        data_root,
        current_identity=lambda: IDENTITY,
        inspect_process=lambda pid: IDENTITY if pid == IDENTITY.pid else None,
        health_check=lambda endpoint, lease_id: False,
        utc_now=lambda: NOW,
    )


def make_service(
    tmp_path: Path,
    *,
    level: OperationLevel = OperationLevel.OBSERVE,
    backend: FakeProbeBackend | None = None,
    data_root: Path | None = None,
    session_root: Path | None = None,
    heartbeat_interval_seconds: float = 5.0,
) -> ProbeService:
    configured_data_root = data_root or tmp_path / "plugin-data"
    return ProbeService(
        backend=backend or fake_backend(),
        lease_manager=lease_manager(configured_data_root),
        probe_id="probe-a",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=level,
        session_root=session_root
        or configured_data_root / "projects" / "workspace-a" / "sessions" / "session-a",
        token_factory=lambda: b"\x11" * 32,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


def run(coroutine):
    return asyncio.run(coroutine)


def test_service_binds_loopback_dynamic_port_and_publishes_private_endpoint(tmp_path: Path):
    async def scenario():
        service = make_service(tmp_path)
        endpoint = await service.start()
        try:
            assert endpoint.host == "127.0.0.1"
            assert 0 < endpoint.port < 65536
            assert endpoint.protocol == "stm32-toolkit-probe/1"
            assert endpoint.toolkit_version == "0.3.0"
            assert endpoint.workspace_id == "workspace-a"
            assert endpoint.session_id == "session-a"
            assert endpoint.lease_id.startswith("lease-")
            assert endpoint.token == "11" * 32
            assert "11" * 8 not in repr(endpoint)

            record = json.loads(endpoint.record_path.read_text(encoding="utf-8"))
            assert record["url"] == f"http://127.0.0.1:{endpoint.port}"
            assert record["token"] == "11" * 32
            if os.name != "nt":
                assert stat.S_IMODE(endpoint.record_path.stat().st_mode) == 0o600
        finally:
            await service.stop()

    run(scenario())


def test_default_health_checker_authenticates_live_service_lease(tmp_path: Path):
    async def scenario():
        service = make_service(tmp_path)
        endpoint = await service.start()
        try:
            assert await asyncio.to_thread(
                _default_health_check,
                f"{endpoint.url}/health",
                endpoint.lease_id,
            )
            assert not await asyncio.to_thread(
                _default_health_check,
                f"{endpoint.url}/health",
                "lease-wrong",
            )
        finally:
            await service.stop()

    run(scenario())


def test_client_lists_attaches_and_reads_without_halting(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            probes = await client.list_probes()
            assert probes == [
                {
                    "probeId": "probe-a",
                    "vendor": "STMicroelectronics",
                    "product": "ST-LINK/V3",
                    "boardName": None,
                }
            ]
            await client.attach("probe-a", "STM32F429ZITx")
            assert backend.halted is False
            assert await client.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
            assert await client.read_registers(("r0", "pc")) == {
                "r0": 7,
                "pc": 0x08000101,
            }
        finally:
            await client.close()
            await service.stop()

    run(scenario())


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda endpoint: endpoint.with_token("00" * 32), "PROBE_AUTH_REQUIRED"),
        (
            lambda endpoint: endpoint.with_workspace("workspace-b"),
            "PROBE_SESSION_MISMATCH",
        ),
        (
            lambda endpoint: endpoint.with_toolkit_version("0.4.0"),
            "PROBE_TOOLKIT_INCOMPATIBLE",
        ),
    ],
)
def test_client_fails_closed_for_auth_session_and_version_mismatch(
    tmp_path: Path, mutation, code
):
    async def scenario():
        service = make_service(tmp_path)
        endpoint = await service.start()
        client = ProbeClient(mutation(endpoint))
        try:
            with pytest.raises(ProbeClientError) as error:
                await client.list_probes()
            assert error.value.code == code
            assert "11" * 8 not in error.value.message
        finally:
            try:
                await client.close()
            except ProbeClientError:
                pass
            await service.stop()

    run(scenario())


def test_observe_lease_rejects_control_level_before_backend_dispatch(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            with pytest.raises(ProbeClientError) as error:
                await client.request(
                    "probe.attach",
                    {"probeId": "probe-a", "target": "STM32F429ZITx"},
                    operation_level=OperationLevel.CONTROL,
                )
            assert error.value.code == "PROBE_OPERATION_LEVEL_DENIED"
            assert backend.attached_probe_id is None
        finally:
            await client.close()
            await service.stop()

    run(scenario())


def test_cross_origin_and_wrong_content_type_are_rejected(tmp_path: Path):
    async def scenario():
        service = make_service(tmp_path)
        endpoint = await service.start()
        try:
            origin_client = ProbeClient(endpoint, extra_headers={"Origin": "https://evil.invalid"})
            with pytest.raises(ProbeClientError) as origin_error:
                await origin_client.list_probes()
            assert origin_error.value.code == "PROBE_ORIGIN_REJECTED"

            content_client = ProbeClient(endpoint, content_type="text/plain")
            with pytest.raises(ProbeClientError) as content_error:
                await content_client.list_probes()
            assert content_error.value.code == "PROBE_CONTENT_TYPE_REQUIRED"
        finally:
            for client in (origin_client, content_client):
                try:
                    await client.close()
                except ProbeClientError:
                    pass
            await service.stop()

    run(scenario())


def test_oversized_body_is_rejected_without_backend_dispatch(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        try:
            client = ProbeClient(endpoint)
            with pytest.raises(ProbeClientError) as error:
                await client.send_raw(b"{" + b" " * 65_536 + b"}")
            assert error.value.code == "PROBE_REQUEST_TOO_LARGE"
            assert backend.events == []
        finally:
            await service.stop()

    run(scenario())


def test_partial_backend_error_is_structured_and_service_stays_healthy(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        backend.fail_memory_read(
            0x20000000, "PROBE_READ_UNAVAILABLE", "Selected memory is unavailable"
        )
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            with pytest.raises(ProbeClientError) as error:
                await client.read_memory(0x20000000, 4)
            assert error.value.code == "PROBE_READ_UNAVAILABLE"
            assert await client.list_probes()
        finally:
            await client.close()
            await service.stop()

    run(scenario())


def test_stop_closes_backend_releases_lease_and_removes_endpoint_record(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        await service.stop()
        await service.stop()

        assert backend.closed is True
        assert not endpoint.record_path.exists()

        successor = make_service(tmp_path, backend=fake_backend())
        next_endpoint = await successor.start()
        try:
            assert next_endpoint.lease_id != endpoint.lease_id
        finally:
            await successor.stop()

    run(scenario())


def test_cancelled_client_read_propagates_and_shutdown_waits_for_backend(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        entered = __import__("threading").Event()
        release = __import__("threading").Event()
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            backend.block_next_read(entered=entered, release=release)
            request = asyncio.create_task(client.read_memory(0x20000000, 4))
            assert await asyncio.to_thread(entered.wait, 2)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            release.set()
        finally:
            release.set()
            await client.close()
            await service.stop()

    run(scenario())


def test_backend_operations_are_serialized_across_concurrent_requests(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        first_client = ProbeClient(endpoint)
        second_client = ProbeClient(endpoint)
        entered = threading.Event()
        release = threading.Event()
        second_backend_entry = threading.Event()
        call_lock = threading.Lock()
        call_count = 0
        original_read = backend.read_memory

        def observed_read(address: int, length: int) -> bytes:
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count == 2:
                    second_backend_entry.set()
            return original_read(address, length)

        backend.read_memory = observed_read
        try:
            await first_client.attach("probe-a", "STM32F429ZITx")
            backend.block_next_read(entered=entered, release=release)
            first = asyncio.create_task(first_client.read_memory(0x20000000, 4))
            assert await asyncio.to_thread(entered.wait, 2)
            second = asyncio.create_task(second_client.read_memory(0x20000000, 4))

            assert not await asyncio.to_thread(second_backend_entry.wait, 0.2)
            release.set()
            assert await first == b"\x01\x02\x03\x04"
            assert await second == b"\x01\x02\x03\x04"
            assert second_backend_entry.is_set()
        finally:
            release.set()
            await first_client.close()
            await second_client.close()
            await service.stop()

    run(scenario())


def test_timed_out_queued_operation_never_dispatches_later(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        first_client = ProbeClient(endpoint)
        second_client = ProbeClient(endpoint)
        entered = threading.Event()
        release = threading.Event()
        second_backend_entry = threading.Event()
        call_lock = threading.Lock()
        call_count = 0
        original_read = backend.read_memory

        def observed_read(address: int, length: int) -> bytes:
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count == 2:
                    second_backend_entry.set()
            return original_read(address, length)

        backend.read_memory = observed_read
        try:
            await first_client.attach("probe-a", "STM32F429ZITx")
            backend.block_next_read(entered=entered, release=release)
            first = asyncio.create_task(first_client.read_memory(0x20000000, 4))
            assert await asyncio.to_thread(entered.wait, 2)

            with pytest.raises(ProbeClientError) as error:
                await second_client.request(
                    "memory.read",
                    {"address": 0x20000000, "length": 4},
                    timeout_ms=10,
                )
            assert error.value.code == "PROBE_TIMEOUT"

            release.set()
            assert await first == b"\x01\x02\x03\x04"
            assert not await asyncio.to_thread(second_backend_entry.wait, 0.2)
        finally:
            release.set()
            await first_client.close()
            await second_client.close()
            await service.stop()

    run(scenario())


def test_timed_out_running_backend_error_is_retrieved(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        backend.fail_memory_read(
            0x20000000, "PROBE_READ_UNAVAILABLE", "Selected memory is unavailable"
        )
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        entered = threading.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        unhandled: list[dict[str, object]] = []
        loop.set_exception_handler(lambda current_loop, context: unhandled.append(context))
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            backend.block_next_read(entered=entered, release=release)
            request = asyncio.create_task(
                client.request(
                    "memory.read",
                    {"address": 0x20000000, "length": 4},
                    timeout_ms=10,
                )
            )
            assert await asyncio.to_thread(entered.wait, 2)
            with pytest.raises(ProbeClientError) as error:
                await request
            assert error.value.code == "PROBE_TIMEOUT"

            release.set()
            deadline = loop.time() + 1
            while service._backend_tasks and loop.time() < deadline:
                await asyncio.sleep(0.01)
            gc.collect()
            await asyncio.sleep(0)
            assert not service._backend_tasks
            assert unhandled == []
        finally:
            loop.set_exception_handler(previous_handler)
            release.set()
            await client.close()
            await service.stop()

    run(scenario())


def test_session_root_redirect_is_rejected_before_endpoint_write(
    tmp_path: Path, monkeypatch
):
    data_root = tmp_path / "plugin-data"
    sessions = data_root / "projects" / "workspace-a" / "sessions"
    session_root = sessions / "session-a"
    outside = tmp_path / "outside"
    sessions.mkdir(parents=True)
    outside.mkdir()
    try:
        session_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(session_root), str(outside)],
            capture_output=True,
            check=False,
        ) if os.name == "nt" else None
        if result is None or result.returncode != 0:
            session_root.mkdir()
            import stm32_toolkit.probe.service as service_module

            real_lstat = service_module.os.lstat

            def injected_lstat(path):
                metadata = real_lstat(path)
                if Path(path) == session_root:
                    return type(
                        "InjectedReparseStat",
                        (),
                        {
                            "st_mode": metadata.st_mode,
                            "st_file_attributes": 0x400,
                        },
                    )()
                return metadata

            monkeypatch.setattr(service_module.os, "lstat", injected_lstat)

    service = make_service(tmp_path, session_root=session_root)

    with pytest.raises(ProbeServiceError) as error:
        run(service.start())

    assert error.value.code == "PROBE_SESSION_UNSAFE"
    assert list(outside.iterdir()) == []


def test_data_root_parent_redirect_is_rejected_before_session_creation(
    tmp_path: Path, monkeypatch
):
    container = tmp_path / "container"
    outside = tmp_path / "outside"
    redirect_parent = container / "redirect-parent"
    container.mkdir()
    outside.mkdir()
    try:
        redirect_parent.symlink_to(outside, target_is_directory=True)
    except OSError:
        result = (
            subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(redirect_parent), str(outside)],
                capture_output=True,
                check=False,
            )
            if os.name == "nt"
            else None
        )
        if result is None or result.returncode != 0:
            redirect_parent.mkdir()
            import stm32_toolkit.probe.service as service_module

            real_lstat = service_module.os.lstat

            def injected_lstat(path):
                metadata = real_lstat(path)
                if Path(path) == redirect_parent:
                    return type(
                        "InjectedParentReparseStat",
                        (),
                        {
                            "st_mode": metadata.st_mode,
                            "st_file_attributes": 0x400,
                        },
                    )()
                return metadata

            monkeypatch.setattr(service_module.os, "lstat", injected_lstat)

    data_root = redirect_parent / "plugin-data"
    service = make_service(tmp_path, data_root=data_root)

    with pytest.raises(ProbeServiceError) as error:
        run(service.start())

    assert error.value.code == "PROBE_SESSION_UNSAFE"
    assert not (outside / "plugin-data").exists()


def test_stop_interrupts_a_blocked_backend_read_without_external_release(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        entered = __import__("threading").Event()
        never_released_by_test = __import__("threading").Event()
        await client.attach("probe-a", "STM32F429ZITx")
        backend.block_next_read(entered=entered, release=never_released_by_test)
        request = asyncio.create_task(client.read_memory(0x20000000, 4))
        assert await asyncio.to_thread(entered.wait, 2)

        await asyncio.wait_for(service.stop(), timeout=2)

        assert backend.closed is True
        assert request.done()
        try:
            await request
        except (ProbeClientError, asyncio.CancelledError):
            pass
        try:
            await client.close()
        except ProbeClientError:
            pass

    run(scenario())


def test_service_refreshes_lease_heartbeat_until_shutdown(tmp_path: Path):
    async def scenario():
        service = make_service(tmp_path, heartbeat_interval_seconds=0.01)
        endpoint = await service.start()
        lease_record = lease_manager(tmp_path / "plugin-data").record_path("probe-a")
        initial = json.loads(lease_record.read_text(encoding="utf-8"))["heartbeatAtUtc"]
        deadline = asyncio.get_running_loop().time() + 1
        current = initial
        while current == initial and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
            current = json.loads(lease_record.read_text(encoding="utf-8"))["heartbeatAtUtc"]
        try:
            assert current != initial
            assert endpoint.record_path.exists()
        finally:
            await service.stop()

    run(scenario())


def test_heartbeat_lease_loss_closes_service_and_removes_endpoint(tmp_path: Path):
    async def scenario():
        backend = fake_backend()
        service = make_service(
            tmp_path, backend=backend, heartbeat_interval_seconds=0.01
        )
        endpoint = await service.start()
        lease_record = lease_manager(tmp_path / "plugin-data").record_path("probe-a")
        record = json.loads(lease_record.read_text(encoding="utf-8"))
        record["leaseId"] = "lease-successor"
        lease_record.write_bytes(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )

        deadline = asyncio.get_running_loop().time() + 1
        while endpoint.record_path.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)

        assert backend.closed is True
        assert service.endpoint is None
        assert not endpoint.record_path.exists()
        await service.stop()

    run(scenario())
