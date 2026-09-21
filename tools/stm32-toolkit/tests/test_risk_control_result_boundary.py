from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

import pytest
from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.probe.authorization import ControlAuthorizationStore
from stm32_toolkit.probe.backend import ProbeAttachmentEvidence, ProbeDescriptor
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.worker import ProbeBackendWorker
from test_probe_service import make_service

IDENTITY = {
    "board_id": "board-a",
    "mcu": "STM32F429ZITx",
    "target_id": "target-a",
    "probe_serial_hash": "a" * 64,
}
DRIFTED_IDENTITY = {**IDENTITY, "target_id": "target-b"}
STATE = {"state": "running", "reason": "requested"}
PC_BEFORE = 0x08000101
PC_AFTER = 0x08000105


def _record(path: str, event: str) -> None:
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(f"{event}\n")


def _events(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _prepare(
    store: ControlAuthorizationStore,
    *,
    operation: str,
    identity: dict[str, object],
    state: dict[str, object],
) -> str:
    return store.prepare(
        {
            "workspace_id": "workspace-a",
            "project_id": "project-a",
            "session_id": "session-a",
            "revision": "revision-a",
            "target": identity,
            "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
            "operation": operation,
            "arguments": {},
            "identity_snapshot": identity,
            "state_snapshot": state,
        }
    ).action_digest


class _SnapshotDriftBackend(FakeProbeBackend):
    def __init__(self, marker: str) -> None:
        super().__init__(
            probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
            memory={0x20000000: b"abcd"},
            registers={"pc": PC_BEFORE},
        )
        self.marker = marker
        self.identity_reads = 0

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        _record(self.marker, "open_attach")
        return super().open_attach(probe_id, target, halt_on_connect=halt_on_connect)

    def target_identity(self) -> dict[str, str]:
        self._require_attach()
        self.identity_reads += 1
        _record(self.marker, "target_identity")
        if self.identity_reads == 2:
            return dict(DRIFTED_IDENTITY)
        return dict(IDENTITY)

    def target_state(self) -> dict[str, str]:
        self._require_attach()
        _record(self.marker, "target_state")
        return dict(STATE)

    def resume(self) -> None:
        _record(self.marker, "resume")
        super().resume()

    def close(self) -> None:
        _record(self.marker, "close")
        super().close()


def _snapshot_drift_factory(marker: str) -> _SnapshotDriftBackend:
    return _SnapshotDriftBackend(marker)


class _StepResultBackend(FakeProbeBackend):
    def __init__(self, variant: str | None, marker: str) -> None:
        super().__init__(
            probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
            memory={0x20000000: b"abcd"},
            registers={"pc": PC_BEFORE},
        )
        self.variant = variant
        self.marker = marker
        self.register_reads = 0
        self.stepped = False

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        _record(self.marker, "open_attach")
        evidence = super().open_attach(
            probe_id, target, halt_on_connect=halt_on_connect
        )
        return evidence

    def target_identity(self) -> dict[str, str]:
        self._require_attach()
        _record(self.marker, "target_identity")
        return dict(IDENTITY)

    def target_state(self) -> dict[str, str]:
        self._require_attach()
        _record(self.marker, "target_state")
        if self.variant == "running" and self.stepped:
            return {"state": "running", "reason": "requested"}
        return {
            "state": "halted" if self.halted else "running",
            "reason": "requested",
        }

    def read_core_registers(self, names: tuple[str, ...]) -> dict[str, int]:
        self._require_attach()
        _record(self.marker, "read_core_registers")
        if names != ("pc",):
            return dict(super().read_core_registers(names))
        self.register_reads += 1
        if self.register_reads == 1:
            return {"pc": PC_BEFORE}
        if self.variant == "missing":
            return {}
        if self.variant == "range":
            return {"pc": 1 << 64}
        return {"pc": PC_AFTER}

    def halt(self) -> None:
        _record(self.marker, "halt")
        super().halt()

    def step(self) -> None:
        _record(self.marker, "step")
        super().step()
        self.stepped = True

    def close(self) -> None:
        _record(self.marker, "close")
        super().close()


def _step_backend_factory(variant: str | None, marker: str) -> _StepResultBackend:
    return _StepResultBackend(variant, marker)


def test_control_authorization_snapshot_drift_consumes_digest_and_recovers(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        marker = tmp_path / "snapshot-drift-events.txt"
        backend = ProbeBackendWorker(
            _test_backend_factory=partial(_snapshot_drift_factory, str(marker))
        )
        store = ControlAuthorizationStore((tmp_path / "control").absolute())
        service = make_service(
            tmp_path,
            level=OperationLevel.CONTROL,
            backend=backend,
            control_authorizations=store,
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            identity = await client.target_identity()
            state = await client.target_state()
            digest = _prepare(
                store, operation="target.resume", identity=identity, state=state
            )

            with pytest.raises(ProbeClientError) as changed:
                await client.target_control("target.resume", {}, digest)
            assert changed.value.code == "PROBE_AUTHORIZATION_INVALID"
            assert (
                changed.value.message == "Control authorization target binding changed"
            )
            before_reuse = _events(marker)
            assert "resume" not in before_reuse

            with pytest.raises(ProbeClientError) as reused:
                await client.target_control("target.resume", {}, digest)
            assert reused.value.code == "PROBE_AUTHORIZATION_INVALID"
            assert reused.value.message == "Authorization is already consumed"
            assert _events(marker) == before_reuse

            recovered_identity = await client.target_identity()
            recovered_state = await client.target_state()
            assert recovered_identity == identity
            assert recovered_state == state
            fresh_digest = _prepare(
                store,
                operation="target.resume",
                identity=recovered_identity,
                state=recovered_state,
            )
            assert await client.target_control("target.resume", {}, fresh_digest) == {
                "state": "running"
            }
            assert _events(marker).count("resume") == 1
        finally:
            await client.close()
            await service.stop()
        assert backend.is_alive is False
        assert _events(marker).count("close") == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("variant", ["missing", "range", "running"])
def test_target_step_rejects_invalid_post_step_result_and_recovers(
    tmp_path: Path, variant: str
) -> None:
    async def scenario() -> None:
        failed_marker = tmp_path / f"step-{variant}-failed.txt"
        failed_backend = ProbeBackendWorker(
            _test_backend_factory=partial(
                _step_backend_factory, variant, str(failed_marker)
            )
        )
        failed_store = ControlAuthorizationStore(
            (tmp_path / f"control-{variant}-failed").absolute()
        )
        failed_service = make_service(
            tmp_path,
            level=OperationLevel.CONTROL,
            backend=failed_backend,
            control_authorizations=failed_store,
        )
        failed_endpoint = await failed_service.start()
        failed_client = ProbeClient(failed_endpoint)
        try:
            await failed_client.attach("probe-a", "STM32F429ZITx")
            identity = await failed_client.target_identity()
            state = await failed_client.target_state()
            halt_digest = _prepare(
                failed_store,
                operation="target.halt",
                identity=identity,
                state=state,
            )
            assert await failed_client.target_control(
                "target.halt", {}, halt_digest
            ) == {"state": "halted", "reason": "requested"}
            identity = await failed_client.target_identity()
            state = await failed_client.target_state()
            digest = _prepare(
                failed_store,
                operation="target.step",
                identity=identity,
                state=state,
            )
            with pytest.raises(ProbeClientError) as invalid:
                await failed_client.target_control("target.step", {}, digest)
            assert invalid.value.code == "PROBE_BACKEND_ERROR"
            assert invalid.value.message == "Target step result is invalid"
        finally:
            await failed_client.close()
            await failed_service.stop()
        assert failed_backend.is_alive is False
        failed_events = _events(failed_marker)
        assert failed_events.count("step") == 1
        assert failed_events.count("close") == 1

        recovered_marker = tmp_path / f"step-{variant}-recovered.txt"
        recovered_backend = ProbeBackendWorker(
            _test_backend_factory=partial(
                _step_backend_factory, None, str(recovered_marker)
            )
        )
        recovered_store = ControlAuthorizationStore(
            (tmp_path / f"control-{variant}-recovered").absolute()
        )
        recovered_service = make_service(
            tmp_path,
            level=OperationLevel.CONTROL,
            backend=recovered_backend,
            control_authorizations=recovered_store,
        )
        recovered_endpoint = await recovered_service.start()
        recovered_client = ProbeClient(recovered_endpoint)
        try:
            await recovered_client.attach("probe-a", "STM32F429ZITx")
            identity = await recovered_client.target_identity()
            state = await recovered_client.target_state()
            halt_digest = _prepare(
                recovered_store,
                operation="target.halt",
                identity=identity,
                state=state,
            )
            assert await recovered_client.target_control(
                "target.halt", {}, halt_digest
            ) == {"state": "halted", "reason": "requested"}
            identity = await recovered_client.target_identity()
            state = await recovered_client.target_state()
            digest = _prepare(
                recovered_store,
                operation="target.step",
                identity=identity,
                state=state,
            )
            assert await recovered_client.target_control("target.step", {}, digest) == {
                "state": "halted",
                "reason": "requested",
                "pc_before": PC_BEFORE,
                "pc_after": PC_AFTER,
            }
        finally:
            await recovered_client.close()
            await recovered_service.stop()
        assert recovered_backend.is_alive is False
        recovered_events = _events(recovered_marker)
        assert recovered_events.count("step") == 1
        assert recovered_events.count("close") == 1

    asyncio.run(scenario())
