"""Semihosting stdout adapter with deny-before-backend host-file policy."""

from __future__ import annotations

from pathlib import PureWindowsPath
import re
from typing import Mapping, Protocol
from unicodedata import normalize

from stm32_toolkit.testing.model import TestProtocolError, protocol_error
from stm32_toolkit.testing.transports.base import Clock, TransportBase, closed_config, default_clock, effective_identity, unavailable


class SemihostingBackend(Protocol):
    def open(self, *, elf_path: str, deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_WINDOWS_INVALID = re.compile(r'[<>:"/|?*\x00-\x1f\x7f]')


def _canonical_elf_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF path is not canonical")
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF path is not canonical") from None
    if (
        encoded_length > 32_767
        or normalize("NFC", value) != value or re.fullmatch(r"[A-Z]:\\[^\r\n]+", value) is None
    ):
        raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF path is not canonical")
    path = PureWindowsPath(value)
    members = value[3:].split("\\")
    if (
        str(path) != value or not path.is_absolute() or any(
            not member or member in {".", ".."} or member.rstrip(" .") != member
            or member.casefold() != member or "~" in member or _WINDOWS_INVALID.search(member)
            or member.split(".", 1)[0].upper() in _WINDOWS_RESERVED
            for member in members
        )
    ):
        raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF path is not canonical")
    return value


def _semihost_handlers(max_buffer_bytes: int):
    from io import BytesIO
    from pyocd.debug.semihost import ConsoleIOHandler, SemihostIOHandler

    class DeniedHostIO(SemihostIOHandler):
        def open(self, fnptr, fnlen, mode):
            return -1

        def close(self, fd):
            return -1

        def write(self, fd, ptr, length):
            return length

        def read(self, fd, ptr, length):
            return length

        def readc(self):
            return 0

        def istty(self, fd):
            return 0

        def seek(self, fd, pos):
            return -1

        def flen(self, fd):
            return -1

        def remove(self, ptr, length):
            return -1

        def rename(self, oldptr, oldlength, newptr, newlength):
            return -1

    class BoundedSink:
        def __init__(self):
            self.buffer = bytearray()
            self.expected: int | None = None

        def write(self, data: bytes) -> int:
            if (
                not isinstance(data, bytes) or self.expected is None or len(data) != self.expected
                or len(self.buffer) + len(data) > max_buffer_bytes
            ):
                raise unavailable("semihosting console exceeded its bound")
            self.buffer.extend(data)
            return len(data)

        def drain(self, maximum: int) -> bytes:
            result = bytes(self.buffer[:maximum])
            del self.buffer[:maximum]
            return result

        def cleanup(self) -> None:
            self.expected = None
            self.buffer.clear()

    class BoundedConsole(ConsoleIOHandler):
        def __init__(self):
            self._sink = BoundedSink()
            super().__init__(BytesIO(), self._sink)

        def write(self, fd: int, ptr: int, length: int) -> int:
            if type(length) is not int or length < 0 or len(self._sink.buffer) + length > max_buffer_bytes:
                raise unavailable("semihosting console exceeded its bound")
            self._sink.expected = length
            try:
                return super().write(fd, ptr, length)
            finally:
                self._sink.expected = None

        def drain(self, maximum: int) -> bytes:
            return self._sink.drain(maximum)

        def cleanup(self) -> None:
            self._sink.cleanup()
            super().cleanup()

    return DeniedHostIO(), BoundedConsole()


class PyOcdSemihostingAdapter:
    """Concrete controlled PyOCD semihost I/O adapter for a frozen debug session."""

    def __init__(self, session: object, *, max_buffer_bytes: int = 64 * 1024) -> None:
        if not all(callable(getattr(session, name, None)) for name in ("open", "poll", "close")):
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting session is invalid")
        if type(max_buffer_bytes) is not int or not 1 <= max_buffer_bytes <= 64 * 1024:
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting buffer bound is invalid")
        self._session = session
        self._host_io, self._console = _semihost_handlers(max_buffer_bytes)
        self._open = False

    def open(self, *, elf_path: str, deadline: float) -> None:
        try:
            self._session.open(
                elf_path=elf_path, host_io=self._host_io, console=self._console, deadline=deadline
            )
        except Exception as exc:
            self._close_quietly()
            raise unavailable("PyOCD semihosting session is unavailable") from exc
        self._open = True

    def read(self, max_bytes: int, deadline: float) -> bytes:
        if not self._open:
            raise unavailable("PyOCD semihosting session is not open")
        try:
            self._session.poll(agent=None, deadline=deadline)
            return self._console.drain(max_bytes)
        except Exception as exc:
            self._close_quietly()
            raise unavailable("PyOCD semihosting session disconnected") from exc

    def close(self) -> None:
        failure: Exception | None = None
        try:
            self._session.close()
        except Exception as exc:
            failure = exc
        finally:
            try:
                self._host_io.cleanup()
                self._console.cleanup()
            except Exception as exc:
                failure = failure or exc
            self._open = False
        if failure is not None:
            raise unavailable("PyOCD semihosting cleanup failed") from failure

    def _close_quietly(self) -> None:
        try:
            self.close()
        except TestProtocolError:
            pass


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
        path, digest = _canonical_elf_path(config["elf_path"]), config["elf_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise protocol_error("TEST_PROTOCOL_INVALID", "semihosting ELF digest is invalid")
        try:
            self._backend.open(elf_path=path, deadline=deadline)
        except Exception as exc:
            self._close_quietly()
            raise unavailable("semihosting backend is unavailable") from exc
        readable = {
            "elf_path": path, "elf_sha256": digest, "host_file_policy": "deny",
        }
        effective = {
            "elf_path": path, "elf_sha256": digest, "host_files": False,
            "profile_declared": True,
        }
        self._commit_open({**effective_identity(identity, effective), **readable})

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
            raise unavailable("semihosting backend disconnected") from exc
        if not isinstance(data, bytes) or len(data) > max_bytes:
            self._close_quietly()
            raise unavailable("semihosting backend returned invalid output")
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
            raise unavailable("semihosting cleanup failed") from failure

    def _close_quietly(self) -> None:
        try:
            self.close()
        except TestProtocolError:
            pass
