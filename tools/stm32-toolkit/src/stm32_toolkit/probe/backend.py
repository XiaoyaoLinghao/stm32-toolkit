"""Backend contract shared by PyOCD, FakeProbe, and the Probe Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from .selector import (
    probe_fingerprint as calculate_probe_fingerprint,
    public_probe_selector,
    valid_hardware_probe_id,
)


class ProbeBackendError(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True)
class ProbeDescriptor:
    probe_id: str
    vendor: str
    product: str
    board_name: str | None
    hardware_id: str | None = None
    probe_fingerprint: str | None = None

    def __post_init__(self) -> None:
        hardware_id = self.hardware_id if self.hardware_id is not None else self.probe_id
        if not valid_hardware_probe_id(hardware_id):
            raise ValueError("probe descriptor hardware identifier is invalid")
        expected_selector = public_probe_selector(hardware_id)
        if self.probe_id != expected_selector:
            raise ValueError("probe descriptor selector is invalid")
        expected_fingerprint = calculate_probe_fingerprint(hardware_id)
        if (
            self.probe_fingerprint is not None
            and self.probe_fingerprint != expected_fingerprint
        ):
            raise ValueError("probe descriptor fingerprint is invalid")
        object.__setattr__(self, "hardware_id", hardware_id)
        object.__setattr__(self, "probe_fingerprint", expected_fingerprint)

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "hardwareId": self.hardware_id,
            "probeFingerprint": self.probe_fingerprint,
            "vendor": self.vendor,
            "product": self.product,
            "boardName": self.board_name,
        }


@dataclass(frozen=True)
class FlashBackendReport:
    bytes_programmed: int | None
    sectors_programmed: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "bytesProgrammed": self.bytes_programmed,
            "sectorsProgrammed": self.sectors_programmed,
        }


@dataclass(frozen=True)
class ProbeAttachmentEvidence:
    probe_id: str
    requested_target: str
    resolved_part_number: str
    core_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "requestedTarget": self.requested_target,
            "resolvedPartNumber": self.resolved_part_number,
            "coreCount": self.core_count,
        }


@runtime_checkable
class ProbeBackend(Protocol):
    def preflight_target_capabilities(self, probe_id: str, operation_level: object) -> None: ...

    def list_probes(self) -> tuple[ProbeDescriptor, ...]: ...

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence: ...

    def read_memory(self, address: int, length: int) -> bytes: ...

    def read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]: ...

    def halt(self) -> None: ...

    def resume(self) -> None: ...

    def step(self) -> None: ...

    def reset(self) -> None: ...

    def flash_elf(self, image: bytes) -> FlashBackendReport: ...

    def close(self) -> None: ...


@runtime_checkable
class TargetProbeBackend(ProbeBackend, Protocol):
    """Additive v2 target capabilities without invalidating existing Probe fakes."""

    def target_observation_policy(self) -> Mapping[str, object]: ...
    def target_read_memory(self, address: int, length: int) -> bytes: ...
    def target_read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]: ...
    def target_identity(self) -> Mapping[str, object]: ...
    def target_state(self) -> Mapping[str, object]: ...
    def set_temporary_breakpoint(self, address: int, size: int) -> Mapping[str, object]: ...
    def clear_temporary_breakpoint(self, breakpoint_id: str) -> Mapping[str, object]: ...
    def capture_fault(self, max_stack_bytes: int) -> Mapping[str, object]: ...
    def capture_logs(self, channel: str, max_bytes: int, duration_ms: int) -> Mapping[str, object]: ...
    def open_target_transport(self, transport: str, config: Mapping[str, object], deadline_ms: int) -> Mapping[str, object]: ...
    def read_target_transport(self, transport_id: str, max_bytes: int, deadline_ms: int) -> Mapping[str, object]: ...
    def close_target_transport(self, transport_id: str) -> Mapping[str, object]: ...
