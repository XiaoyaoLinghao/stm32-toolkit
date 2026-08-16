"""pyserial 3.5 UART adapter with exact named-port 8N1 configuration."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from stm32_toolkit.testing.model import TestProtocolError, protocol_error
from stm32_toolkit.testing.transports.base import Clock, TransportBase, closed_config, default_clock, unavailable


ALLOWED_BAUDS = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)


class SerialPort(Protocol):
    def read(self, size: int) -> bytes: ...
    def close(self) -> None: ...


SerialFactory = Callable[..., SerialPort]


def pyserial_factory(**kwargs: object) -> SerialPort:
    import serial

    if serial.VERSION != "3.5":
        raise unavailable("installed pyserial version is not the admitted 3.5")
    return serial.Serial(**kwargs)


class UartTransport(TransportBase):
    def __init__(self, factory: SerialFactory, profile: Mapping[str, object], *, clock: Clock = default_clock) -> None:
        super().__init__("uart", clock)
        if not callable(factory):
            raise protocol_error("TEST_PROTOCOL_INVALID", "UART factory is invalid")
        self._factory = factory
        self._profile = profile
        self._port: SerialPort | None = None

    def open(self, config: Mapping[str, object], deadline: float) -> None:
        config = closed_config(config, {"port", "baud", "data_bits", "parity", "stop_bits", "target_id", "probe_id"})
        identity = self._begin_open(config, deadline)
        declared = self._profile.get("uart") if isinstance(self._profile, Mapping) else None
        if not isinstance(declared, Mapping) or set(declared) != {"port", "baud"}:
            raise unavailable("UART capability is absent from the support profile")
        port, baud = config["port"], config["baud"]
        if (
            not isinstance(port, str) or not port or type(baud) is not int or baud not in ALLOWED_BAUDS
            or port != declared["port"] or baud != declared["baud"]
            or config["data_bits"] != 8 or config["parity"] != "N" or config["stop_bits"] != 1
        ):
            raise unavailable("UART configuration is not the exact profile-declared 8N1 port")
        try:
            self._port = self._factory(
                port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
                xonxoff=False, rtscts=False, dsrdtr=False, timeout=0,
            )
        except Exception as exc:
            self._close_quietly()
            raise unavailable("pyserial UART port is unavailable") from exc
        if not callable(getattr(self._port, "read", None)) or not callable(getattr(self._port, "close", None)):
            self._close_quietly()
            raise unavailable("pyserial returned an invalid UART port")
        self._commit_open({
            **identity, "port": port, "baud": str(baud), "data_bits": "8",
            "parity": "N", "stop_bits": "1",
        })

    def read(self, max_bytes: int, deadline: float) -> bytes:
        try:
            self._begin_read(max_bytes, deadline)
        except TestProtocolError as exc:
            if exc.code == "TEST_TIMEOUT":
                self._close_quietly()
            raise
        assert self._port is not None
        try:
            data = self._port.read(max_bytes)
        except Exception as exc:
            self._close_quietly()
            raise unavailable("pyserial UART port disconnected") from exc
        if not isinstance(data, bytes) or len(data) > max_bytes:
            self._close_quietly()
            raise unavailable("pyserial UART returned invalid output")
        return data

    def close(self) -> None:
        failure: Exception | None = None
        try:
            if self._port is not None and callable(getattr(self._port, "close", None)):
                self._port.close()
        except Exception as exc:
            failure = exc
        finally:
            self._port = None
            self._mark_closed()
        if failure is not None:
            raise unavailable("pyserial UART cleanup failed") from failure

    def _close_quietly(self) -> None:
        try:
            self.close()
        except TestProtocolError:
            pass
