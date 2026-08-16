"""PyOCD RTT adapter constrained to declared channel and RAM."""

from __future__ import annotations

from typing import Mapping, Protocol

from stm32_toolkit.testing.model import protocol_error
from stm32_toolkit.testing.transports.base import Clock, TransportBase, closed_config, default_clock, ram_regions, range_in_ram, unavailable


class PyOcdRttBackend(Protocol):
    def open(self, *, channel: int, control_block_address: int | None, ram_regions: tuple[tuple[int, int], ...], deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...


class RttTransport(TransportBase):
    def __init__(self, backend: PyOcdRttBackend, profile: Mapping[str, object], *, clock: Clock = default_clock) -> None:
        super().__init__("rtt", clock)
        if not all(callable(getattr(backend, name, None)) for name in ("open", "read", "close")):
            raise protocol_error("TEST_PROTOCOL_INVALID", "RTT backend does not implement the admitted PyOCD port")
        self._backend = backend
        self._profile = profile

    def open(self, config: Mapping[str, object], deadline: float) -> None:
        config = closed_config(config, {"channel", "control_block_address", "ram", "target_id", "probe_id"})
        identity = self._begin_open(config, deadline)
        declared = self._profile.get("rtt") if isinstance(self._profile, Mapping) else None
        declared_ram = self._profile.get("ram") if isinstance(self._profile, Mapping) else None
        if not isinstance(declared, Mapping) or declared_ram is None or set(declared) not in ({"channel"}, {"channel", "control_block_address"}):
            raise unavailable("RTT capability is absent from the support profile")
        channel = config["channel"]
        control = config["control_block_address"]
        regions = ram_regions(config["ram"])
        if type(channel) is not int or not 0 <= channel <= 15 or channel != declared["channel"]:
            raise unavailable("RTT channel is not profile-declared")
        if regions != ram_regions(declared_ram) or control != declared.get("control_block_address"):
            raise unavailable("RTT RAM or control block is not profile-declared")
        if control is not None and (type(control) is not int or not range_in_ram(control, 1, regions)):
            raise unavailable("RTT control block is outside declared RAM")
        try:
            self._backend.open(channel=channel, control_block_address=control, ram_regions=regions, deadline=deadline)
        except Exception as exc:
            self.close()
            raise unavailable("PyOCD RTT backend is unavailable") from exc
        self._commit_open(identity)

    def read(self, max_bytes: int, deadline: float) -> bytes:
        self._begin_read(max_bytes, deadline)
        try:
            data = self._backend.read(max_bytes, deadline)
        except Exception as exc:
            self.close()
            raise unavailable("PyOCD RTT backend disconnected") from exc
        if not isinstance(data, bytes) or len(data) > max_bytes:
            self.close()
            raise unavailable("PyOCD RTT backend returned invalid output")
        return data

    def close(self) -> None:
        try:
            self._backend.close()
        finally:
            self._mark_closed()
