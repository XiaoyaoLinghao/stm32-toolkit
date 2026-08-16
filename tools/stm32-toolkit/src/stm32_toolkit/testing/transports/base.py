"""Closed interfaces and validation shared by target transports."""

from __future__ import annotations

import math
from hashlib import sha256
import time
from typing import Callable, Mapping, Protocol, Sequence

from stm32_toolkit.evidence import canonical_json_bytes
from stm32_toolkit.testing.model import protocol_error


MAX_TRANSPORT_READ_BYTES = 64 * 1024
Clock = Callable[[], float]


class TargetTransport(Protocol):
    def open(self, config: Mapping[str, object], deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...
    def identity(self) -> Mapping[str, str]: ...


def default_clock() -> float:
    return time.monotonic()


def check_deadline(deadline: float, clock: Clock) -> None:
    if not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or not math.isfinite(deadline):
        raise protocol_error("TEST_PROTOCOL_INVALID", "transport deadline must be finite")
    if deadline <= clock():
        raise protocol_error("TEST_TIMEOUT", "target transport deadline expired")


def check_read_size(max_bytes: int) -> None:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_TRANSPORT_READ_BYTES:
        raise protocol_error("TEST_PROTOCOL_INVALID", "transport read size is invalid")


def closed_config(config: Mapping[str, object], fields: set[str]) -> Mapping[str, object]:
    if not isinstance(config, Mapping) or set(config) != fields:
        raise protocol_error("TEST_PROTOCOL_INVALID", "transport config has an invalid shape")
    return config


def identity_from(config: Mapping[str, object], transport: str) -> dict[str, str]:
    target_id = config.get("target_id")
    probe_id = config.get("probe_id")
    if not isinstance(target_id, str) or not target_id or not isinstance(probe_id, str) or not probe_id:
        raise protocol_error("TEST_PROTOCOL_INVALID", "transport identity is invalid")
    return {"probe_id": probe_id, "target_id": target_id, "transport": transport}


def effective_identity(identity: Mapping[str, str], effective: Mapping[str, object]) -> dict[str, str]:
    """Bind the complete closed effective transport configuration canonically."""
    return {**identity, "config_digest": sha256(canonical_json_bytes(dict(effective))).hexdigest()}


def format_ram_bounds(regions: tuple[tuple[int, int], ...]) -> str:
    return ",".join(f"0x{start:08x}+0x{size:08x}" for start, size in regions)


def ram_regions(value: object) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise protocol_error("TEST_PROTOCOL_INVALID", "RAM regions are invalid")
    regions: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"start", "size"}:
            raise protocol_error("TEST_PROTOCOL_INVALID", "RAM region has an invalid shape")
        start, size = item["start"], item["size"]
        if type(start) is not int or type(size) is not int or start < 0 or size <= 0 or start + size > 2**64:
            raise protocol_error("TEST_PROTOCOL_INVALID", "RAM region is out of bounds")
        regions.append((start, size))
    if regions != sorted(regions) or any(a + size > b for (a, size), (b, _) in zip(regions, regions[1:])):
        raise protocol_error("TEST_PROTOCOL_INVALID", "RAM regions overlap or are not sorted")
    return tuple(regions)


def range_in_ram(address: int, size: int, regions: tuple[tuple[int, int], ...]) -> bool:
    return type(address) is int and type(size) is int and size > 0 and any(
        start <= address and address + size <= start + length for start, length in regions
    )


def unavailable(message: str):
    return protocol_error("TEST_TRANSPORT_UNAVAILABLE", message)


class TransportBase:
    def __init__(self, transport: str, clock: Clock = default_clock) -> None:
        self._transport = transport
        self._clock = clock
        self._opened = False
        self._identity: dict[str, str] | None = None

    def _begin_open(self, config: Mapping[str, object], deadline: float) -> dict[str, str]:
        check_deadline(deadline, self._clock)
        if self._opened:
            raise protocol_error("TEST_PROTOCOL_INVALID", "transport is already open")
        return identity_from(config, self._transport)

    def _commit_open(self, identity: dict[str, str]) -> None:
        self._identity = identity
        self._opened = True

    def _begin_read(self, max_bytes: int, deadline: float) -> None:
        check_deadline(deadline, self._clock)
        check_read_size(max_bytes)
        if not self._opened:
            raise unavailable("target transport is not open")

    def identity(self) -> Mapping[str, str]:
        if not self._opened or self._identity is None:
            raise unavailable("target transport is not open")
        return dict(self._identity)

    def _mark_closed(self) -> None:
        self._opened = False
        self._identity = None
