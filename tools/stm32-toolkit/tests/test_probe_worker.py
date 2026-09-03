from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
import json
from pathlib import Path
import shutil
import threading
import time

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.probe.backend import (
    FlashBackendReport, ProbeAttachmentEvidence, ProbeBackendError, ProbeDescriptor,
)
from stm32_toolkit.probe.model import OperationLevel, ProbeRequest
from stm32_toolkit.probe.worker import ProbeBackendWorker, ProbeWorkerError


ATK_RAW = "ATK 20210914"
ATK_FINGERPRINT = "91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c"
ATK_SELECTOR = f"pyocd:{ATK_FINGERPRINT}"


class _WorkerTestBackend:
    def __init__(self, mode: str, marker: str) -> None:
        if mode == "init-crash":
            raise RuntimeError("secret C:/credential")
        self.mode = mode
        self.marker = Path(marker)

    def target_identity(self):
        if self.mode == "error-close-hang":
            raise RuntimeError("private")
        if self.mode == "private-error":
            raise ProbeBackendError("PRIVATE_CODE", "secret")
        if self.mode == "hard-crash":
            import os
            os._exit(23)
        if self.mode == "crash":
            raise SystemExit(9)
        if self.mode == "oversize":
            return {"value": "x" * (17 * 1024 * 1024)}
        return {"worker": "ok"}

    def preflight_target_capabilities(self, probe_id, operation_level): return None
    def list_probes(self): return (ProbeDescriptor("probe-a", "v", "p", None),)
    def open_attach(self, probe_id, target, *, halt_on_connect=False):
        return ProbeAttachmentEvidence(probe_id, target, target, 1)
    def _record_read(self, operation: str) -> None:
        with self.marker.open("ab") as stream:
            stream.write((operation + "\n").encode("ascii"))
    def read_memory(self, address, length):
        self._record_read(f"legacy-memory:{address}:{length}")
        return b"m" * length
    def read_core_registers(self, names):
        self._record_read("legacy-registers:" + ",".join(names))
        return {name: 1 for name in names}
    def target_read_memory(self, address, length):
        self._record_read(f"target-memory:{address}:{length}")
        return b"t" * length
    def target_read_core_registers(self, names):
        self._record_read("target-registers:" + ",".join(names))
        return {name: 2 for name in names}
    def target_observation_policy(self):
        return {
            "readable_regions": [{"start": 0x20000000, "size": 4}],
            "register_allowlist": ["pc"],
        }
    def halt(self): return None
    def resume(self): return None
    def reset(self): return None
    def target_state(self): return {"state": "halted", "reason": "requested"}
    def set_temporary_breakpoint(self, address, size):
        return {"breakpoint_id": "bp-1", "address": address, "kind": "temporary", "size": size}
    def clear_temporary_breakpoint(self, breakpoint_id):
        return {"breakpoint_id": breakpoint_id, "cleared": True}
    def capture_fault(self, maximum): return {"fault_registers": {}, "stack": b"", "truncated": False}
    def capture_logs(self, channel, maximum, duration): return {"data": b"l", "truncated": False}
    def open_target_transport(self, transport, config, deadline):
        return {"transport_id": "transport-1", "identity": {"target_id": "t"}}
    def read_target_transport(self, transport_id, maximum, deadline): return {"data": b"r", "eof": False}
    def close_target_transport(self, transport_id): return {"transport_id": transport_id, "closed": True}

    def step(self) -> None:
        if self.mode == "hang":
            # Deliberately ignores cancellation. If the owned child survives its
            # deadline it creates an externally observable late action.
            time.sleep(2.0)
            self.marker.write_text("late", encoding="utf-8")

    def flash_elf(self, image: bytes):
        return FlashBackendReport(len(image), 1)

    def close(self) -> None:
        if self.mode in {"close-hang", "error-close-hang"}:
            time.sleep(2.0)
            self.marker.write_text("late-close", encoding="utf-8")
        return None


class _AttachRecoveryWorkerBackend:
    """Picklable worker seam that exposes attach terminal recovery ordering."""

    def __init__(self, mode: str, marker_root: str) -> None:
        self.mode = mode
        self.marker_root = Path(marker_root)
        self.marker_root.mkdir(parents=True, exist_ok=True)
        self.marker = self.marker_root / "events.jsonl"
        self.attached = False
        self.halted = False
        self.closed = False

    def _record(self, event: str) -> None:
        with self.marker.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, separators=(",", ":")) + "\n")

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        self._record("attach-entered")
        self.attached = True
        self.halted = bool(halt_on_connect)
        if self.mode == "unresponsive":
            time.sleep(5.0)
            self._record("late-attach-returned")
        else:
            time.sleep(0.1)
            self._record("attach-returned")
        return ProbeAttachmentEvidence(probe_id, target, target, 1)

    def resume(self) -> None:
        self._record("resume")
        self.halted = False

    def target_state(self):
        state = "halted" if self.halted else "running"
        self._record(f"target-state-{state}")
        return {"state": state, "reason": "requested"}

    def close(self) -> None:
        state = "halted" if self.halted else "running"
        self._record(f"close-{state}")
        self.attached = False
        self.closed = True

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        self._record("program")
        return FlashBackendReport(len(image), 1)


@dataclass(frozen=True)
class _StructuredProbe:
    probe_id: str = ATK_SELECTOR
    hardware_id: str = ATK_RAW
    probe_fingerprint: str = ATK_FINGERPRINT
    vendor: str = "ATK"
    product: str = "ATK-HS-V3-CMSIS-DAP"
    board_name: str | None = None


class _StructuredProbeBackend:
    def list_probes(self):
        return (_StructuredProbe(),)

    def close(self) -> None:
        return None


def _structured_probe_factory() -> _StructuredProbeBackend:
    return _StructuredProbeBackend()


def _factory(mode: str, marker: str) -> _WorkerTestBackend:
    return _WorkerTestBackend(mode, marker)


def _attach_recovery_factory(mode: str, marker_root: str) -> _AttachRecoveryWorkerBackend:
    return _AttachRecoveryWorkerBackend(mode, marker_root)


def _attach_recovery_request(*, timeout_ms: int, request_id: str) -> ProbeRequest:
    return ProbeRequest(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        request_id=request_id,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-test",
        operation_level=OperationLevel.MODIFY,
        operation="probe.attach",
        timeout_ms=timeout_ms,
        data={"probeId": "probe-a", "target": "STM32F429ZITx"},
    )


def _read_recovery_events(marker_root: Path) -> list[str]:
    return [
        json.loads(line)
        for line in (marker_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _remove_recovery_marker_root(marker_root: Path) -> None:
    if marker_root.exists():
        shutil.rmtree(marker_root)


def test_worker_normal_call_and_close_leave_no_owned_process(tmp_path: Path) -> None:
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "normal", str(tmp_path / "unused"))
    )
    pid = worker.owned_pid
    assert worker.target_identity() == {"worker": "ok"}
    worker.close()
    assert not worker.is_alive
    assert pid > 0


def test_production_worker_uses_only_closed_serializable_pyocd_and_task8_config() -> None:
    from stm32_toolkit.probe import worker as module
    from stm32_toolkit.probe.pyocd_backend import admitted_target_transport_factory

    profile = {
        "backend": "pyocd", "board_id": "board-a", "mcu": "stm32f407vg",
        "target_id": "target-a", "ram": [{"start": 0x20000000, "size": 0x10000}],
        "mailbox": {"address": 0x20000000, "size": 4096},
        "rtt": {"channel": 0},
        "log_transport": {"kind": "rtt", "options": {"channel": 0}},
    }
    config = module.ProbeWorkerConfig(
        frequency_hz=1_000_000, target_profile=profile, transport_provider="task8"
    )
    assert config.target_profile() == profile
    target = object()
    assert {
        kind: type(admitted_target_transport_factory(kind, target, profile)).__name__
        for kind in ("mailbox", "rtt", "uart", "semihosting")
    } == {
        "mailbox": "MailboxTransport",
        "rtt": "RttTransport",
        "uart": "UartTransport",
        "semihosting": "SemihostingTransport",
    }
    worker = ProbeBackendWorker(config=config)
    try:
        worker.preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    finally:
        worker.close()
    with pytest.raises(TypeError):
        module.ProbeWorkerConfig(
            frequency_hz=1_000_000, target_profile=profile,
            transport_provider=lambda *args: object(),
        )


def test_worker_config_derives_only_the_fixed_under_reset_recovery_profile() -> None:
    from stm32_toolkit.probe import worker as module

    normal = module.ProbeWorkerConfig(
        target_profile={"backend": "pyocd", "mcu": "stm32f429zgtx"}
    )
    recovery = normal.for_under_reset_recovery()

    assert normal.frequency_hz == 1_000_000
    assert normal.connection_policy == module.NORMAL_CONNECTION_POLICY
    assert recovery.frequency_hz == 100_000
    assert recovery.connection_policy == module.UNDER_RESET_RECOVERY_CONNECTION_POLICY
    assert recovery.target_profile() == normal.target_profile()
    assert recovery.transport_provider == normal.transport_provider


def test_worker_config_and_direct_production_child_fail_closed() -> None:
    from stm32_toolkit.probe import worker as module

    for kwargs in (
        {"frequency_hz": True}, {"frequency_hz": 99_999},
        {"transport_provider": "dynamic"}, {"target_profile": []},
        {"target_profile": {"bad": {1}}},
        {"connection_policy": "under-reset"},
        {"connection_policy": "UNDER-RESET-RECOVERY"},
        {"connection_policy": True},
        {"frequency_hz": 1_000_000, "connection_policy": "under-reset-recovery"},
    ):
        with pytest.raises(TypeError):
            module.ProbeWorkerConfig(**kwargs)
    corrupted = module.ProbeWorkerConfig()
    object.__setattr__(corrupted, "target_profile_json", "[]")
    with pytest.raises(ProbeWorkerError):
        corrupted.target_profile()
    for kwargs in ({}, {"config": module.ProbeWorkerConfig(), "_test_backend_factory": lambda: object()}, {"config": object()}):
        with pytest.raises(TypeError):
            ProbeBackendWorker(**kwargs)

    class EofConnection:
        def __init__(self): self.sent = []; self.closed = False
        def send_bytes(self, payload): self.sent.append(module._decode_message(payload))
        def recv_bytes(self, maximum): raise EOFError
        def close(self): self.closed = True

    production = EofConnection()
    module._worker_main(production, module.ProbeWorkerConfig(), None)
    assert production.sent[0]["ok"] is True
    assert production.closed is True
    invalid = EofConnection()
    module._worker_main(invalid, None, None)
    assert invalid.sent[-1]["error"]["code"] == "PROBE_BACKEND_ERROR"
    assert invalid.closed is True

    corrupted = module.ProbeWorkerConfig()
    object.__setattr__(corrupted, "connection_policy", "under-reset")
    corrupted_child = EofConnection()
    module._worker_main(corrupted_child, corrupted, None)
    assert corrupted_child.sent[-1]["error"]["code"] == "PROBE_BACKEND_ERROR"
    assert corrupted_child.closed is True


def test_worker_flash_ipc_is_bounded_but_not_limited_by_evidence_json_strings(tmp_path: Path) -> None:
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "normal", str(tmp_path / "unused"))
    )
    image = b"f" * (1024 * 1024)
    assert worker.flash_elf(image) == FlashBackendReport(len(image), 1)
    worker.close()


def test_worker_exercises_the_complete_fixed_probe_backend_port(tmp_path: Path) -> None:
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "normal", str(tmp_path / "unused"))
    )
    worker.preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    assert worker.list_probes() == (ProbeDescriptor("probe-a", "v", "p", None),)
    assert worker.open_attach("probe-a", "stm32", halt_on_connect=False).core_count == 1
    assert worker.read_memory(0, 2) == b"mm"
    assert worker.read_core_registers(("pc",)) == {"pc": 1}
    worker.halt(); worker.resume(); worker.step(); worker.reset()
    assert worker.target_state()["state"] == "halted"
    assert worker.set_temporary_breakpoint(1, 2)["breakpoint_id"] == "bp-1"
    assert worker.clear_temporary_breakpoint("bp-1")["cleared"] is True
    assert worker.capture_fault(0)["stack"] == b""
    assert worker.capture_logs("rtt", 1, 1)["data"] == b"l"
    opened = worker.open_target_transport("mailbox", {}, 1)
    assert worker.read_target_transport(opened["transport_id"], 1, 1)["data"] == b"r"
    assert worker.close_target_transport(opened["transport_id"])["closed"] is True
    worker.close()


def test_worker_preserves_all_six_probe_descriptor_facts_through_canonical_serializer() -> None:
    worker = ProbeBackendWorker(_test_backend_factory=_structured_probe_factory)
    try:
        assert worker.list_probes()[0].to_dict() == {
            "probeId": ATK_SELECTOR,
            "hardwareId": ATK_RAW,
            "probeFingerprint": ATK_FINGERPRINT,
            "vendor": "ATK",
            "product": "ATK-HS-V3-CMSIS-DAP",
            "boardName": None,
        }
    finally:
        worker.close()


def test_spawned_worker_service_isolates_legacy_and_target_observation_reads(
    tmp_path: Path,
) -> None:
    """The production Service/worker boundary preserves both read contracts."""
    from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
    from test_probe_service import make_service, run

    async def scenario() -> None:
        marker = tmp_path / "backend-reads.txt"
        worker = ProbeBackendWorker(
            _test_backend_factory=partial(
                _factory, "normal", str(marker)
            )
        )
        service = make_service(
            tmp_path / "service", level=OperationLevel.OBSERVE, backend=worker
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "stm32f407vg")
            assert await client.read_memory(0x40000000, 4) == b"mmmm"
            assert await client.read_registers(("r1",)) == {"r1": 1}
            with pytest.raises(ProbeClientError):
                await client.target_memory(0x40000000, 4)
            with pytest.raises(ProbeClientError):
                await client.target_registers(("r1",))
            assert marker.read_text(encoding="ascii").splitlines() == [
                "legacy-memory:1073741824:4",
                "legacy-registers:r1",
            ]
            assert await client.target_memory(0x20000000, 4) == b"tttt"
            assert (await client.target_registers(("pc",)))[0]["value"] == 2
            assert marker.read_text(encoding="ascii").splitlines() == [
                "legacy-memory:1073741824:4",
                "legacy-registers:r1",
                "target-memory:536870912:4",
                "target-registers:pc",
            ]
        finally:
            await client.close()
            await service.stop()
        assert not worker.is_alive

    run(scenario())


def test_spawned_worker_attach_timeout_cooperatively_recovers_before_propagating(
    tmp_path: Path,
) -> None:
    from test_probe_service import make_service, run

    async def scenario() -> None:
        marker_root = tmp_path / "cooperative-attach-marker"
        worker: ProbeBackendWorker | None = None
        service = None
        try:
            worker = ProbeBackendWorker(
                _test_backend_factory=partial(
                    _attach_recovery_factory, "cooperative", str(marker_root)
                )
            )
            service = make_service(
                tmp_path / "cooperative-service",
                level=OperationLevel.MODIFY,
                backend=worker,
            )
            with pytest.raises(asyncio.TimeoutError):
                await service._run_backend(
                    _attach_recovery_request(
                        timeout_ms=20,
                        request_id="request-worker-cooperative-attach",
                    )
                )
            assert worker.is_alive is False
            events = _read_recovery_events(marker_root)
            assert events == [
                "attach-entered",
                "attach-returned",
                "resume",
                "target-state-running",
                "close-running",
            ]
            assert "program" not in events
        finally:
            if worker is not None and worker.is_alive:
                await asyncio.to_thread(worker.abort_owned_execution)
            if service is not None:
                pending = tuple(service._backend_tasks)
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            _remove_recovery_marker_root(marker_root)

    run(scenario())


def test_unresponsive_worker_attach_uses_bounded_close_failure_fallback(
    tmp_path: Path,
) -> None:
    from test_probe_service import make_service, run

    async def scenario() -> None:
        marker_root = tmp_path / "unresponsive-attach-marker"
        worker: ProbeBackendWorker | None = None
        service = None
        try:
            worker = ProbeBackendWorker(
                _test_backend_factory=partial(
                    _attach_recovery_factory, "unresponsive", str(marker_root)
                )
            )
            service = make_service(
                tmp_path / "unresponsive-service",
                level=OperationLevel.MODIFY,
                backend=worker,
            )
            started = asyncio.get_running_loop().time()
            with pytest.raises(ProbeBackendError) as caught:
                await service._run_backend(
                    _attach_recovery_request(
                        timeout_ms=20,
                        request_id="request-worker-unresponsive-attach",
                    )
                )
            elapsed = asyncio.get_running_loop().time() - started
            assert caught.value.code == "PROBE_CLOSE_FAILED"
            assert caught.value.message == "Probe attach cleanup failed"
            assert caught.value.details == {}
            cause = caught.value.__cause__
            assert isinstance(cause, ProbeBackendError)
            assert cause.code == "PROBE_TIMEOUT"
            assert cause.message == "Attach recovery did not reach a terminal state"
            assert cause.details == {}
            assert cause.__cause__ is None
            assert caught.value.__cause__ is cause
            assert "private" not in str(caught.value)
            assert "private" not in str(cause)
            assert elapsed >= 0.9
            assert elapsed < 4.0
            assert worker.is_alive is False
            await asyncio.sleep(1.1)
            events = _read_recovery_events(marker_root)
            assert events == ["attach-entered"]
            assert not any(
                event
                in {
                    "late-attach-returned",
                    "resume",
                    "close-running",
                    "close-halted",
                    "reset",
                    "erase",
                    "unlock",
                    "program",
                }
                for event in events
            )
        finally:
            if worker is not None and worker.is_alive:
                await asyncio.to_thread(worker.abort_owned_execution)
            if service is not None:
                pending = tuple(service._backend_tasks)
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            _remove_recovery_marker_root(marker_root)

    run(scenario())


def test_worker_accepts_the_300_second_transport_and_log_protocol_limit(tmp_path: Path) -> None:
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "normal", str(tmp_path / "unused"))
    )
    assert worker.capture_logs("rtt", 1, 300_000)["data"] == b"l"
    opened = worker.open_target_transport("mailbox", {}, 300_000)
    assert worker.read_target_transport(opened["transport_id"], 1, 300_000)["data"] == b"r"
    worker.close()


def test_worker_closed_codec_rejects_duplicate_noncanonical_and_unsupported_values() -> None:
    from stm32_toolkit.probe import worker as module

    assert module._from_json([{"$bytes": "eA=="}]) == [b"x"]
    assert module._json_value(FlashBackendReport(1, 1)) == {
        "bytes_programmed": 1, "sectors_programmed": 1,
    }
    for raw in (b'{"a":1,"a":1}', b'{"a": 1}', b'[]'):
        with pytest.raises((ValueError, ProbeWorkerError)):
            module._decode_message(raw)
    for value in ({1: "bad"}, {1, 2}):
        with pytest.raises(TypeError):
            module._json_value(value)
    with pytest.raises(ValueError):
        module._from_json({"$bytes": "***"})
    with pytest.raises(ValueError):
        module._from_json({"$bytes": 1})
    with pytest.raises(ValueError):
        module._from_json({"$bytes": "eB=="})
    with pytest.raises(ProbeWorkerError):
        module._canonical_bytes({"bad": {1}})


def test_worker_child_dispatch_parser_is_closed_in_process(tmp_path: Path) -> None:
    from stm32_toolkit.probe import worker as module

    class Connection:
        def __init__(self, requests): self.requests = list(requests); self.sent = []; self.closed = False
        def recv_bytes(self, maximum):
            if not self.requests: raise EOFError
            return self.requests.pop(0)
        def send_bytes(self, payload): self.sent.append(module._decode_message(payload))
        def close(self): self.closed = True

    request = lambda identifier, method, args=None: module._canonical_bytes({
        "version": module._VERSION, "id": identifier, "method": method,
        "args": args or [], "kwargs": {},
    })
    connection = Connection([
        request(1, "preflight_target_capabilities", ["probe-a", "observe"]),
        request(2, "target_identity"), request(3, "close"),
    ])
    module._worker_main(
        connection, None, partial(_factory, "normal", str(tmp_path / "unused"))
    )
    assert [item["ok"] for item in connection.sent] == [True, True, True, True]
    assert connection.sent[2]["result"] == {"worker": "ok"}
    assert connection.closed

    invalid = Connection([module._canonical_bytes({"unexpected": True})])
    module._worker_main(invalid, None, partial(_factory, "normal", str(tmp_path / "unused")))
    assert invalid.sent[-1]["error"]["code"] == "PROBE_BACKEND_ERROR"
    private = Connection([request(1, "target_identity")])
    module._worker_main(private, None, partial(_factory, "private-error", str(tmp_path / "secret")))
    assert private.sent[-1]["error"] == {
        "code": "PROBE_BACKEND_ERROR", "message": "Probe worker operation failed",
    }

    small = Connection([])
    original = module._MAX_OUTPUT_BYTES
    module._MAX_OUTPUT_BYTES = 10
    try:
        module._send(small, {"large": "output"})
    finally:
        module._MAX_OUTPUT_BYTES = original
    assert small.sent[-1]["error"]["code"] == "PROBE_LIMIT_EXCEEDED"


def test_worker_rejects_invalid_calls_and_is_idempotently_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_toolkit.probe import worker as module

    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "normal", str(tmp_path / "unused"))
    )
    for method, timeout in (("unknown", 1.0), ("target_identity", 0.0), ("target_identity", 302.0)):
        with pytest.raises(ProbeWorkerError) as invalid:
            worker.call(method, timeout_seconds=timeout)
        assert invalid.value.code == "PROBE_PROTOCOL_INVALID"
    monkeypatch.setattr(module, "_MAX_MESSAGE_BYTES", 10)
    with pytest.raises(ProbeWorkerError) as oversized:
        worker.target_identity()
    assert oversized.value.code == "PROBE_LIMIT_EXCEEDED"
    worker.abort_owned_execution()
    worker.abort_owned_execution()
    with pytest.raises(ProbeWorkerError):
        worker.target_identity()
    worker.close()


def test_worker_timeout_terminates_cancel_ignored_child_without_late_action(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "late-action"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "hang", str(marker))
    )
    pid = worker.owned_pid
    failures: list[BaseException] = []

    def invoke() -> None:
        try:
            worker.call("step", timeout_seconds=0.05)
        except BaseException as error:
            failures.append(error)

    caller = threading.Thread(target=invoke)
    caller.start()
    caller.join(2.0)
    assert not caller.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], ProbeWorkerError)
    assert failures[0].code == "PROBE_TIMEOUT"
    assert not worker.is_alive
    assert worker.owned_pid == pid
    time.sleep(2.1)
    assert not marker.exists()


@pytest.mark.parametrize("mode", ["crash", "hard-crash", "oversize"])
def test_worker_maps_crash_and_oversize_to_closed_failure(tmp_path: Path, mode: str) -> None:
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, mode, str(tmp_path / "unused"))
    )
    with pytest.raises(ProbeWorkerError) as caught:
        worker.target_identity()
    assert caught.value.code in {"PROBE_BACKEND_ERROR", "PROBE_LIMIT_EXCEEDED"}
    worker.abort_owned_execution()
    assert not worker.is_alive


def test_worker_constructor_failure_is_sanitized_and_reaped(tmp_path: Path) -> None:
    with pytest.raises(ProbeWorkerError) as caught:
        ProbeBackendWorker(
            _test_backend_factory=partial(_factory, "init-crash", str(tmp_path / "secret"))
        )
    assert caught.value.code == "PROBE_BACKEND_ERROR"
    assert "secret" not in caught.value.message


@pytest.mark.parametrize("exit_kind", ["operation-error", "malformed-request", "eof"])
def test_worker_child_closes_backend_once_on_every_nonclose_exit(exit_kind: str) -> None:
    from stm32_toolkit.probe import worker as module

    class Backend:
        def __init__(self): self.close_calls = 0
        def target_identity(self): raise RuntimeError("private")
        def close(self): self.close_calls += 1

    class Connection:
        def __init__(self, requests): self.requests = list(requests); self.sent = []
        def recv_bytes(self, maximum):
            if not self.requests: raise EOFError
            return self.requests.pop(0)
        def send_bytes(self, payload): self.sent.append(module._decode_message(payload))
        def close(self): pass

    backend = Backend()
    valid = module._canonical_bytes({
        "version": module._VERSION, "id": 1, "method": "target_identity",
        "args": [], "kwargs": {},
    })
    requests = {
        "operation-error": [valid],
        "malformed-request": [module._canonical_bytes({"unexpected": True})],
        "eof": [],
    }[exit_kind]
    module._worker_main(Connection(requests), None, lambda: backend)
    assert backend.close_calls == 1


def test_worker_child_does_not_retry_a_failing_explicit_close() -> None:
    from stm32_toolkit.probe import worker as module

    class Backend:
        def __init__(self): self.close_calls = 0
        def close(self): self.close_calls += 1; raise RuntimeError("private")

    class Connection:
        def __init__(self): self.sent = []
        def recv_bytes(self, maximum):
            return module._canonical_bytes({
                "version": module._VERSION, "id": 1, "method": "close",
                "args": [], "kwargs": {},
            })
        def send_bytes(self, payload): self.sent.append(module._decode_message(payload))
        def close(self): pass

    backend = Backend()
    connection = Connection()
    module._worker_main(connection, None, lambda: backend)
    assert backend.close_calls == 1
    assert connection.sent[-1]["error"] == {
        "code": "PROBE_BACKEND_ERROR", "message": "Probe worker operation failed",
    }


def test_worker_hanging_close_is_terminated_without_late_cleanup_action(tmp_path: Path) -> None:
    marker = tmp_path / "late-close"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "close-hang", str(marker))
    )
    started = time.monotonic()
    with pytest.raises(ProbeWorkerError) as caught:
        worker.call("close", timeout_seconds=0.05)
    assert caught.value.code == "PROBE_TIMEOUT"
    assert time.monotonic() - started < 1.5
    assert not worker.is_alive
    time.sleep(2.1)
    assert not marker.exists()


def test_worker_operation_error_reaps_a_hanging_backend_cleanup_before_response(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "late-close"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_factory, "error-close-hang", str(marker))
    )
    started = time.monotonic()
    with pytest.raises(ProbeWorkerError) as caught:
        worker.target_identity()
    assert caught.value.code == "PROBE_BACKEND_ERROR"
    assert time.monotonic() - started < 1.5
    assert not worker.is_alive
    time.sleep(2.1)
    assert not marker.exists()
