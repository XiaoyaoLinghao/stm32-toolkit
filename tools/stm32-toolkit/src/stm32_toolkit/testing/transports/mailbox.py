"""Read-only bounded memory-mailbox transport."""

from __future__ import annotations

import inspect
from typing import Mapping, Protocol

from stm32_toolkit.testing.model import TestProtocolError, protocol_error
from stm32_toolkit.testing.transports.base import (
    Clock,
    TransportBase,
    closed_config,
    default_clock,
    effective_identity,
    format_ram_bounds,
    ram_regions,
    range_in_ram,
    unavailable,
)


_HEADER_BYTES = 16
_COUNTER_MASK = 2**64 - 1


class BoundedMemoryReader(Protocol):
    """Closed Task 8 port; the production Probe v2 binding is Task 9."""

    def read_memory(self, address: int, size: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...


class MailboxTransport(TransportBase):
    def __init__(self, reader: BoundedMemoryReader, profile: Mapping[str, object], *, clock: Clock = default_clock) -> None:
        super().__init__("mailbox", clock)
        if not callable(getattr(reader, "read_memory", None)) or not callable(getattr(reader, "close", None)):
            raise protocol_error("TEST_PROTOCOL_INVALID", "mailbox reader does not implement the closed read-only port")
        if callable(getattr(reader, "write_memory", None)):
            raise protocol_error("TEST_PROTOCOL_INVALID", "mailbox reader must not expose target writes")
        self._reader = reader
        self._profile = profile
        self._address = 0
        self._size = 0
        self._cursor: int | None = None

    def open(self, config: Mapping[str, object], deadline: float) -> None:
        config = closed_config(config, {"address", "size", "ram", "target_id", "probe_id"})
        identity = self._begin_open(config, deadline)
        declared = self._profile.get("mailbox") if isinstance(self._profile, Mapping) else None
        declared_ram = self._profile.get("ram") if isinstance(self._profile, Mapping) else None
        if (
            not isinstance(declared, Mapping) or set(declared) != {"address", "size"}
            or type(declared.get("address")) is not int or type(declared.get("size")) is not int
            or declared_ram is None
        ):
            raise unavailable("mailbox capability is absent from the support profile")
        regions = ram_regions(config["ram"])
        if regions != ram_regions(declared_ram):
            raise unavailable("mailbox RAM map is not the profile-declared map")
        address, size = config["address"], config["size"]
        if (
            type(address) is not int or type(size) is not int
            or address != declared["address"] or size != declared["size"]
            or not range_in_ram(address, _HEADER_BYTES + size, regions)
        ):
            raise unavailable("mailbox range is not the profile-declared bounded RAM range")
        self._address, self._size, self._cursor = int(address), int(size), None
        readable = {
            "address": f"0x{self._address:08x}", "ring_size": str(self._size),
            "ram_bounds": format_ram_bounds(regions),
        }
        effective = {"address": self._address, "ring_size": self._size, "ram": regions}
        self._commit_open({**effective_identity(identity, effective), **readable})

    def _external_read(self, address: int, size: int, deadline: float) -> bytes:
        try:
            data = self._reader.read_memory(address, size, deadline)
        except Exception as exc:
            self._close_quietly()
            raise unavailable("mailbox reader disconnected") from exc
        if not isinstance(data, bytes) or len(data) != size:
            self._close_quietly()
            raise unavailable("mailbox reader returned partial output")
        return data

    def read(self, max_bytes: int, deadline: float) -> bytes:
        try:
            self._begin_read(max_bytes, deadline)
        except TestProtocolError as exc:
            if exc.code == "TEST_TIMEOUT":
                self._close_quietly()
            raise
        header = self._external_read(self._address, _HEADER_BYTES, deadline)
        producer = int.from_bytes(header[:8], "little")
        consumer = int.from_bytes(header[8:], "little")
        target_available = (producer - consumer) & _COUNTER_MASK
        if target_available > self._size:
            self._invalid_target_output("mailbox producer/consumer counters exceed the ring")
        if self._cursor is None:
            self._cursor = consumer
        available = (producer - self._cursor) & _COUNTER_MASK
        if available > self._size:
            self._invalid_target_output("mailbox local cursor is outside the target window")
        count = min(max_bytes, available)
        if count == 0:
            return b""
        offset = self._cursor % self._size
        first = min(count, self._size - offset)
        data = self._external_read(self._address + _HEADER_BYTES + offset, first, deadline)
        if first < count:
            data += self._external_read(self._address + _HEADER_BYTES, count - first, deadline)
        self._cursor = (self._cursor + count) & _COUNTER_MASK
        return data

    async def _external_read_async(self, address: int, size: int, deadline: float) -> bytes:
        try:
            data = self._reader.read_memory(address, size, deadline)
            if inspect.isawaitable(data):
                data = await data
        except Exception as exc:
            await self._close_quietly_async()
            raise unavailable("mailbox reader disconnected") from exc
        if not isinstance(data, bytes) or len(data) != size:
            await self._close_quietly_async()
            raise unavailable("mailbox reader returned partial output")
        return data

    async def read_async(self, max_bytes: int, deadline: float) -> bytes:
        """Read through either the original sync port or the production async Probe v2 port."""
        try:
            self._begin_read(max_bytes, deadline)
        except TestProtocolError as exc:
            if exc.code == "TEST_TIMEOUT":
                await self._close_quietly_async()
            raise
        header = await self._external_read_async(self._address, _HEADER_BYTES, deadline)
        producer = int.from_bytes(header[:8], "little")
        consumer = int.from_bytes(header[8:], "little")
        target_available = (producer - consumer) & _COUNTER_MASK
        if target_available > self._size:
            await self._invalid_target_output_async("mailbox producer/consumer counters exceed the ring")
        if self._cursor is None:
            self._cursor = consumer
        available = (producer - self._cursor) & _COUNTER_MASK
        if available > self._size:
            await self._invalid_target_output_async("mailbox local cursor is outside the target window")
        count = min(max_bytes, available)
        if count == 0:
            return b""
        offset = self._cursor % self._size
        first = min(count, self._size - offset)
        data = await self._external_read_async(self._address + _HEADER_BYTES + offset, first, deadline)
        if first < count:
            data += await self._external_read_async(self._address + _HEADER_BYTES, count - first, deadline)
        self._cursor = (self._cursor + count) & _COUNTER_MASK
        return data

    def close(self) -> None:
        failure: Exception | None = None
        try:
            self._reader.close()
        except Exception as exc:
            failure = exc
        finally:
            self._cursor = None
            self._mark_closed()
        if failure is not None:
            raise unavailable("mailbox cleanup failed") from failure

    async def close_async(self) -> None:
        failure: Exception | None = None
        try:
            result = self._reader.close()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            failure = exc
        finally:
            self._cursor = None
            self._mark_closed()
        if failure is not None:
            raise unavailable("mailbox cleanup failed") from failure

    def _close_quietly(self) -> None:
        try:
            self.close()
        except TestProtocolError:
            pass

    async def _close_quietly_async(self) -> None:
        try:
            await self.close_async()
        except TestProtocolError:
            pass

    def _invalid_target_output(self, message: str) -> None:
        self._close_quietly()
        raise protocol_error("TEST_PROTOCOL_INVALID", message)

    async def _invalid_target_output_async(self, message: str) -> None:
        await self._close_quietly_async()
        raise protocol_error("TEST_PROTOCOL_INVALID", message)
