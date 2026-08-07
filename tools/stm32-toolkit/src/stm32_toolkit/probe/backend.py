"""Backend contract shared by PyOCD, FakeProbe, and the Probe Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


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

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
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
