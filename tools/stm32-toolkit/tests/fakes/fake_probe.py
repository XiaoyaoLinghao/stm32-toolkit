"""Stateful deterministic implementation of the ProbeBackend contract."""

from __future__ import annotations

import threading
from collections.abc import Mapping

from stm32_toolkit.probe.backend import (
    FlashBackendReport,
    ProbeAttachmentEvidence,
    ProbeBackendError,
    ProbeDescriptor,
)


class FakeProbeBackend:
    def __init__(
        self,
        *,
        probes: tuple[ProbeDescriptor, ...],
        memory: Mapping[int, bytes],
        registers: Mapping[str, int],
    ) -> None:
        self._probes = tuple(probes)
        self._memory = {address: bytes(value) for address, value in memory.items()}
        self._registers = dict(registers)
        self._read_failures: dict[int, tuple[str, str]] = {}
        self._next_read_barrier: tuple[threading.Event, threading.Event] | None = None
        self._active_read_releases: set[threading.Event] = set()
        self._barrier_lock = threading.Lock()
        self.events: list[tuple[object, ...]] = []
        self.attached_probe_id: str | None = None
        self.attached_target: str | None = None
        self.halted = False
        self.disconnected = False
        self.closed = False
        self.reset_count = 0
        self.flashed_paths: list[str] = []
        self.flashed_images: list[bytes] = []

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        self.events.append(("list_probes",))
        if self.disconnected:
            raise ProbeBackendError("PROBE_DISCONNECTED", "Probe backend is disconnected")
        return self._probes

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        available = self.list_probes()
        if not probe_id:
            raise ProbeBackendError(
                "PROBE_SELECTION_REQUIRED", "An exact probe identifier is required"
            )
        if not any(item.probe_id == probe_id for item in available):
            raise ProbeBackendError("PROBE_NOT_FOUND", "Selected probe is unavailable")
        if not target or len(target) > 128:
            raise ProbeBackendError("PROBE_TARGET_INVALID", "Target is invalid")
        self.events.append(("open_attach", probe_id, target, halt_on_connect))
        self.attached_probe_id = probe_id
        self.attached_target = target
        self.halted = bool(halt_on_connect)
        self.closed = False
        return ProbeAttachmentEvidence(probe_id, target, target, 1)

    def _require_attach(self) -> None:
        if self.disconnected:
            raise ProbeBackendError("PROBE_DISCONNECTED", "Probe backend is disconnected")
        if self.attached_probe_id is None:
            raise ProbeBackendError("PROBE_NOT_ATTACHED", "Probe is not attached")

    def _wait_for_read_barrier(self) -> None:
        barrier = self._next_read_barrier
        if barrier is None:
            return
        self._next_read_barrier = None
        entered, release = barrier
        with self._barrier_lock:
            self._active_read_releases.add(release)
        entered.set()
        try:
            release.wait()
        finally:
            with self._barrier_lock:
                self._active_read_releases.discard(release)

    def read_memory(self, address: int, length: int) -> bytes:
        self._require_attach()
        self._wait_for_read_barrier()
        self.events.append(("read_memory", address, length))
        if address in self._read_failures:
            code, message = self._read_failures[address]
            raise ProbeBackendError(
                code, message, {"address": address, "length": length}
            )
        for base, data in self._memory.items():
            offset = address - base
            if offset >= 0 and length > 0 and offset + length <= len(data):
                return data[offset : offset + length]
        raise ProbeBackendError(
            "PROBE_READ_UNAVAILABLE",
            "Selected memory is unavailable",
            {"address": address, "length": length},
        )

    def read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]:
        self._require_attach()
        self.events.append(("read_core_registers", names))
        values: dict[str, int] = {}
        for name in names:
            if name not in self._registers:
                raise ProbeBackendError(
                    "PROBE_REGISTER_UNAVAILABLE",
                    "Selected core register is unavailable",
                    {"name": name},
                )
            values[name] = self._registers[name]
        return values

    def fail_memory_read(self, address: int, code: str, message: str) -> None:
        self._read_failures[address] = (code, message)

    def block_next_read(
        self, *, entered: threading.Event, release: threading.Event
    ) -> None:
        self._next_read_barrier = (entered, release)

    def disconnect(self) -> None:
        self.disconnected = True
        self.attached_probe_id = None
        self.attached_target = None

    def reconnect(self) -> None:
        self.disconnected = False
        self.closed = False

    def halt(self) -> None:
        self._require_attach()
        self.events.append(("halt",))
        self.halted = True

    def resume(self) -> None:
        self._require_attach()
        self.events.append(("resume",))
        self.halted = False

    def step(self) -> None:
        self._require_attach()
        if not self.halted:
            raise ProbeBackendError("PROBE_NOT_HALTED", "Target must be halted to step")
        self.events.append(("step",))

    def reset(self) -> None:
        self._require_attach()
        self.events.append(("reset",))
        self.reset_count += 1
        self.halted = False

    def flash_file(self, path: str) -> FlashBackendReport:
        self._require_attach()
        self.events.append(("flash_file", path))
        self.flashed_paths.append(path)
        return FlashBackendReport(bytes_programmed=1024, sectors_programmed=2)

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        self._require_attach()
        self.events.append(("flash_elf", len(image)))
        self.flashed_images.append(bytes(image))
        return FlashBackendReport(bytes_programmed=1024, sectors_programmed=2)

    def close(self) -> None:
        if self.closed:
            return
        with self._barrier_lock:
            active_releases = tuple(self._active_read_releases)
        for release in active_releases:
            release.set()
        self.events.append(("close",))
        self.attached_probe_id = None
        self.attached_target = None
        self.halted = False
        self.closed = True
