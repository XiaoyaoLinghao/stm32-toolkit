"""Semihosting stdout adapter with deny-before-backend host-file policy."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Mapping, Protocol

from stm32_toolkit.testing.model import protocol_error
from stm32_toolkit.testing.transports.base import Clock, TransportBase, closed_config, default_clock, unavailable


class SemihostingBackend(Protocol):
    def open(self, *, elf_path: str, deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...


class SemihostingTransport(TransportBase):
    def __init__(self, backend: SemihostingBackend, profile: Mapping[str, object], *, clock: Clock = default_clock) -> None:
        super().__init__("semihosting", clock)
        if not all(callable(getattr(backend, name, None)) for name in ("open", "read", "close")):
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting backend does not implement the frozen port")
        self._backend = backend
        self._profile = profile

    def open(self, config: Mapping[str, object], deadline: float) -> None:
        config = closed_config(config, {"elf_path", "elf_sha256", "host_files", "target_id", "probe_id"})
        identity = self._begin_open(config, deadline)
        if config["host_files"] is not False:
            raise unavailable("semihosting host-file operations are denied")
        declared = self._profile.get("semihosting") if isinstance(self._profile, Mapping) else None
        if not isinstance(declared, Mapping) or set(declared) != {"declared"} or declared["declared"] is not True:
            raise unavailable("semihosting capability is absent from the support profile")
        path, digest = config["elf_path"], config["elf_sha256"]
        if not isinstance(path, str) or not path or not PureWindowsPath(path).is_absolute():
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF path must be an absolute Windows path")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF digest is invalid")
        try:
            self._backend.open(elf_path=str(PureWindowsPath(path)), deadline=deadline)
        except Exception as exc:
            self.close()
            raise unavailable("semihosting backend is unavailable") from exc
        self._commit_open(identity)

    def read(self, max_bytes: int, deadline: float) -> bytes:
        self._begin_read(max_bytes, deadline)
        try:
            data = self._backend.read(max_bytes, deadline)
        except Exception as exc:
            self.close()
            raise unavailable("semihosting backend disconnected") from exc
        if not isinstance(data, bytes) or len(data) > max_bytes:
            self.close()
            raise unavailable("semihosting backend returned invalid output")
        return data

    def close(self) -> None:
        try:
            self._backend.close()
        finally:
            self._mark_closed()
