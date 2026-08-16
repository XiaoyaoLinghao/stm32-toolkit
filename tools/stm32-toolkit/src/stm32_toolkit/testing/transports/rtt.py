"""PyOCD RTT adapter constrained to declared channel and RAM."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from stm32_toolkit.testing.model import TestProtocolError, protocol_error
from stm32_toolkit.testing.transports.base import MAX_TRANSPORT_READ_BYTES, Clock, TransportBase, closed_config, default_clock, ram_regions, range_in_ram, unavailable


class PyOcdRttBackend(Protocol):
    def open(self, *, channel: int, control_block_address: int | None, ram_regions: tuple[tuple[int, int], ...], deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def identity(self) -> Mapping[str, str]: ...
    def close(self) -> None: ...


class _TrackedPyOcdControlBlock:
    """Expose PyOCD's discovered address without duplicating its RTT parser."""

    def __new__(cls, target: object, *, address: int, size: int):
        from pyocd.debug.rtt import GenericRTTControlBlock

        class Tracked(GenericRTTControlBlock):
            control_block_address: int | None = None

            def _find_control_block(self):
                result = super()._find_control_block()
                self.control_block_address = result
                return result

        return Tracked(target, address=address, size=size)


ControlBlockFactory = Callable[..., object]


class PyOcdRttAdapter:
    """Concrete bounded adapter over PyOCD's admitted RTT implementation."""

    def __init__(self, target: object, *, control_block_factory: ControlBlockFactory = _TrackedPyOcdControlBlock) -> None:
        self._target = target
        self._factory = control_block_factory
        self._block: object | None = None
        self._channel: object | None = None
        self._buffer = bytearray()
        self._actual_address: int | None = None

    def open(self, *, channel: int, control_block_address: int | None, ram_regions: tuple[tuple[int, int], ...], deadline: float) -> None:
        if control_block_address is None:
            if len(ram_regions) != 1:
                raise unavailable("PyOCD RTT search requires one declared RAM region")
            address, size = ram_regions[0]
        else:
            address, size = control_block_address, 0
        try:
            block = self._factory(self._target, address=address, size=size)
            start = getattr(block, "start")
            start()
            channels = getattr(block, "up_channels")
            actual = getattr(block, "control_block_address", control_block_address)
        except Exception as exc:
            self.close()
            raise unavailable("PyOCD RTT control block is unavailable") from exc
        if type(actual) is not int or not range_in_ram(actual, 1, ram_regions) or not isinstance(channels, (list, tuple)) or channel >= len(channels):
            self.close()
            raise unavailable("PyOCD RTT control block identity is invalid")
        self._block, self._channel, self._actual_address = block, channels[channel], actual

    def read(self, max_bytes: int, deadline: float) -> bytes:
        if self._channel is None:
            raise unavailable("PyOCD RTT channel is not open")
        if not self._buffer:
            try:
                data = self._channel.read()
            except Exception as exc:
                self.close()
                raise unavailable("PyOCD RTT channel disconnected") from exc
            if not isinstance(data, bytes) or len(data) > MAX_TRANSPORT_READ_BYTES:
                self.close()
                raise unavailable("PyOCD RTT channel returned invalid output")
            self._buffer.extend(data)
        result = bytes(self._buffer[:max_bytes])
        del self._buffer[:max_bytes]
        return result

    def identity(self) -> Mapping[str, str]:
        if self._actual_address is None:
            raise unavailable("PyOCD RTT control block is not open")
        return {"control_block_address": f"0x{self._actual_address:08x}"}

    def close(self) -> None:
        self._block = None
        self._channel = None
        self._actual_address = None
        self._buffer.clear()


class RttTransport(TransportBase):
    def __init__(self, backend: PyOcdRttBackend, profile: Mapping[str, object], *, clock: Clock = default_clock) -> None:
        super().__init__("rtt", clock)
        if not all(callable(getattr(backend, name, None)) for name in ("open", "read", "identity", "close")):
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
        backend_identity = self._backend.identity()
        actual_text = backend_identity.get("control_block_address")
        try:
            actual = int(actual_text, 16) if isinstance(actual_text, str) else -1
        except ValueError:
            actual = -1
        if not range_in_ram(actual, 1, regions) or (control is not None and actual != control):
            self._close_quietly()
            raise unavailable("PyOCD RTT control block identity is invalid")
        self._commit_open({**identity, "channel": str(channel), "control_block_address": f"0x{actual:08x}"})

    def read(self, max_bytes: int, deadline: float) -> bytes:
        try:
            self._begin_read(max_bytes, deadline)
        except TestProtocolError as exc:
            if exc.code == "TEST_TIMEOUT":
                self._close_quietly()
            raise
        try:
            data = self._backend.read(max_bytes, deadline)
        except Exception as exc:
            self._close_quietly()
            raise unavailable("PyOCD RTT backend disconnected") from exc
        if not isinstance(data, bytes) or len(data) > max_bytes:
            self._close_quietly()
            raise unavailable("PyOCD RTT backend returned invalid output")
        return data

    def close(self) -> None:
        failure: Exception | None = None
        try:
            self._backend.close()
        except Exception as exc:
            failure = exc
        finally:
            self._mark_closed()
        if failure is not None:
            raise unavailable("PyOCD RTT cleanup failed") from failure

    def _close_quietly(self) -> None:
        try:
            self.close()
        except TestProtocolError:
            pass
