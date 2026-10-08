from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.generation import configure as configure_module
from stm32_toolkit.generation.configure import apply_project_configuration
from stm32_toolkit.generation.managed_files import MANAGED_MANIFEST_PATH
from stm32_toolkit.probe.backend import ProbeBackendError
from stm32_toolkit.probe.client import ProbeClient
from stm32_toolkit.probe.service import (
    ProbeServiceCleanupError,
    ProbeServiceError,
)
from test_generation import plan_for, staging_dir, tree_snapshot, write_project
from test_probe_service import fake_backend, lease_manager, make_service


def test_risk_project_directory_fsync_failure_rolls_back_after_destination_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = write_project(tmp_path / "project")
    before = tree_snapshot(root)
    plan = plan_for(root)
    expected_destinations = tuple(
        (entry.path, root.joinpath(*entry.path.split("/")), entry.after_bytes, entry.before_bytes)
        for entry in plan.files
    ) + (
        (
            MANAGED_MANIFEST_PATH,
            root.joinpath(*MANAGED_MANIFEST_PATH.split("/")),
            plan.managed_manifest_bytes,
            None,
        ),
    )
    guard: dict[str, object] = {"calls": 0, "destination_written": False}

    def fail_directory_fsync(path: Path) -> None:
        guard["calls"] = int(guard["calls"]) + 1
        guard["fsync_parent"] = Path(path)
        for relative, destination, after_bytes, before_bytes in expected_destinations:
            if destination.parent != Path(path) or not destination.is_file():
                continue
            observed = destination.read_bytes()
            if observed == after_bytes and (
                before_bytes is None or observed != before_bytes
            ):
                guard["destination_written"] = True
                guard["written_path"] = relative
                break
        raise OSError(5, "injected directory fsync failure")

    monkeypatch.setattr(configure_module, "_fsync_dir", fail_directory_fsync)
    result = apply_project_configuration(plan)

    assert result.ok is False
    assert result.operation == "project-configuration-apply"
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.message == "apply failed"
    assert result.details == {"phase": "fsync"}
    assert int(guard["calls"]) == 1
    assert guard["destination_written"] is True
    assert isinstance(guard["written_path"], str)
    assert tree_snapshot(root) == before
    assert not staging_dir(root, plan.plan_id).exists()
    assert not (root / ".stm32-toolkit").exists()


def test_risk_preflight_untyped_provider_failure_does_not_bind_lease(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        backend = fake_backend()
        calls: list[tuple[str, object]] = []

        def fail_preflight(probe_id: str, operation_level: object) -> None:
            calls.append((probe_id, operation_level))
            raise RuntimeError("provider preflight failed")

        backend.preflight_target_capabilities = fail_preflight  # type: ignore[method-assign]
        data_root = tmp_path / "plugin-data"
        service = make_service(tmp_path, backend=backend, data_root=data_root)
        try:
            with pytest.raises(ProbeServiceError) as caught:
                await service.start()

            assert caught.value.code == "PROBE_BACKEND_ERROR"
            assert caught.value.message == "Probe capability preflight failed"
            assert len(calls) == 1
            assert calls[0][0] == "probe-a"
            assert not any(event[0] == "open_attach" for event in backend.events)
            assert service._lease is None
            assert service.endpoint is None
            assert backend.attached_probe_id is None
            assert not list(data_root.rglob("*.owner.json"))
            assert not list(data_root.rglob("probe-endpoint.json"))
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_risk_malformed_handoff_metadata_clears_attachment_and_settles(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        backend = fake_backend()
        metadata_calls: list[float | None] = []

        def malformed_metadata(*, deadline: float | None = None) -> dict[str, str]:
            metadata_calls.append(deadline)
            backend.events.append(("debug_handoff_metadata",))
            return {"probeId": "probe-a", "target": "STM32F429ZITx"}

        backend.debug_handoff_metadata = malformed_metadata  # type: ignore[method-assign]
        data_root = tmp_path / "plugin-data"
        service = make_service(tmp_path, backend=backend, data_root=data_root)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        lease_path = lease_manager(data_root).record_path("probe-a")
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            endpoint_before = endpoint.record_path.read_bytes()
            lease_before = lease_path.read_bytes()

            with pytest.raises(ProbeBackendError) as caught:
                await service.debug_handoff_metadata("probe-a", "STM32F429ZITx")

            assert caught.value.code == "PROBE_BACKEND_ERROR"
            assert caught.value.message == "Debug handoff identity is invalid"
            assert caught.value.details == {}
            assert len(metadata_calls) == 1
            assert service._observation_attachment is None
            assert service._metadata_cleanup_unresolved is False
            assert not service._metadata_owned_tasks
            assert endpoint.record_path.read_bytes() == endpoint_before
            assert lease_path.read_bytes() == lease_before
            assert await client.list_probes()
        finally:
            await client.close()
            await service.stop()

        assert backend.closed is True
        assert not endpoint.record_path.exists()
        assert json.loads(lease_path.read_text(encoding="utf-8")) == {
            "leaseId": endpoint.lease_id,
            "schemaVersion": 1,
            "state": "released",
        }

    asyncio.run(scenario())


def test_risk_backend_close_timeout_still_releases_lease(tmp_path: Path) -> None:
    class TimeoutCloseBackend(FakeProbeBackend):
        def __init__(self) -> None:
            source = fake_backend()
            super().__init__(
                probes=source.list_probes(),
                memory={0x20000000: b"\x01\x02\x03\x04"},
                registers={"r0": 7, "pc": 0x08000101},
            )
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1
            super().close()
            raise TimeoutError("backend close timed out")

    async def scenario() -> None:
        backend = TimeoutCloseBackend()
        data_root = tmp_path / "plugin-data"
        service = make_service(tmp_path, backend=backend, data_root=data_root)
        endpoint = await service.start()
        lease_path = lease_manager(data_root).record_path("probe-a")
        replacement = None
        try:
            with pytest.raises(ProbeServiceCleanupError) as caught:
                await service.stop()

            assert caught.value.code == "PROBE_CLOSE_FAILED"
            assert caught.value.cleanup_fragment.to_list()[-2:] == [
                {
                    "stage": "service-stop-backend-close",
                    "outcome": "failed",
                    "reason": "timeout",
                    "sourceCode": "UNTYPED",
                },
                {"stage": "service-lease-release", "outcome": "succeeded"},
            ]
            assert backend.close_calls == 1
            assert backend.closed is True
            assert service.endpoint is None
            assert service._lease is None
            assert not endpoint.record_path.exists()
            assert json.loads(lease_path.read_text(encoding="utf-8")) == {
                "leaseId": endpoint.lease_id,
                "schemaVersion": 1,
                "state": "released",
            }

            replacement = make_service(
                tmp_path, backend=fake_backend(), data_root=data_root
            )
            successor = await replacement.start()
            assert successor.lease_id != endpoint.lease_id
        finally:
            try:
                await service.stop()
            except ProbeServiceCleanupError:
                pass
            if replacement is not None:
                await replacement.stop()

    asyncio.run(scenario())
