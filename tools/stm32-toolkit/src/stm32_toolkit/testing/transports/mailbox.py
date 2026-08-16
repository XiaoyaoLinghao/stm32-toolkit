"""Read-only bounded memory-mailbox transport."""

from __future__ import annotations

from typing import Mapping, Protocol

from stm32_toolkit.testing.model import protocol_error
from stm32_toolkit.testing.transports.base import (
    Clock,
    TransportBase,
    closed_config,
    default_clock,
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
        if not isinstance(declared, Mapping) or set(declared) != {"address", "size"} or declared_ram is None:
            raise unavailable("mailbox capability is absent from the support profile")
        regions = ram_regions(config["ram"])
        if regions != ram_regions(declared_ram):
            raise unavailable("mailbox RAM map is not the profile-declared map")
        address, size = config["address"], config["size"]
        if address != declared["address"] or size != declared["size"] or not range_in_ram(address, _HEADER_BYTES + size, regions):
            raise unavailable("mailbox range is not the profile-declared bounded RAM range")
        self._address, self._size, self._cursor = int(address), int(size), None
        self._commit_open(identity)

    def _external_read(self, address: int, size: int, deadline: float) -> bytes:
        try:
            data = self._reader.read_memory(address, size, deadline)
        except Exception as exc:
            self.close()
            raise unavailable("mailbox reader disconnected") from exc
        if not isinstance(data, bytes) or len(data) != size:
            self.close()
            raise unavailable("mailbox reader returned partial output")
        return data

    def read(self, max_bytes: int, deadline: float) -> bytes:
        self._begin_read(max_bytes, deadline)
        header = self._external_read(self._address, _HEADER_BYTES, deadline)
        producer = int.from_bytes(header[:8], "little")
        consumer = int.from_bytes(header[8:], "little")
        target_available = (producer - consumer) & _COUNTER_MASK
        if target_available > self._size:
            raise protocol_error("TEST_PROTOCOL_INVALID", "mailbox producer/consumer counters exceed the ring")
        if self._cursor is None:
            self._cursor = consumer
        available = (producer - self._cursor) & _COUNTER_MASK
        if available > self._size:
            raise protocol_error("TEST_PROTOCOL_INVALID", "mailbox local cursor is outside the target window")
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

    def close(self) -> None:
        try:
            self._reader.close()
        finally:
            self._cursor = None
            self._mark_closed()
