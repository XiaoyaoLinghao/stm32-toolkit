"""Authentication policy for the loopback-only Monitor HTTP service."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

MAX_REQUEST_BYTES = 1_048_576
MONITOR_COOKIE_NAME = "stm32_monitor_session"


class MonitorAuthError(Exception):
    """A stable public authentication or request-boundary failure."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int) -> MonitorAuthError:
    return MonitorAuthError(code, message, status)


@dataclass(frozen=True)
class MonitorAuth:
    host: str
    port: int
    token: str = field(repr=False)
    token_digest: str

    @classmethod
    def create(
        cls,
        *,
        host: str,
        port: int,
        token_factory: Callable[[int], object] = secrets.token_bytes,
    ) -> "MonitorAuth":
        if host != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65_535:
            raise ValueError("Monitor authentication endpoint is invalid")
        value = token_factory(32)
        if type(value) is not bytes or len(value) != 32:
            raise ValueError("Monitor token factory must return exactly 32 bytes")
        token = value.hex()
        return cls(host, port, token, hashlib.sha256(token.encode("ascii")).hexdigest())

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    def require_header_budget(self, headers: Iterable[tuple[str, str]]) -> None:
        total = 0
        try:
            for name, value in headers:
                total += len(name.encode("utf-8")) + len(value.encode("utf-8")) + 4
                if total > MAX_REQUEST_BYTES:
                    raise _error(
                        "MONITOR_REQUEST_TOO_LARGE",
                        "Monitor request headers exceed the allowed size",
                        431,
                    )
        except UnicodeError:
            raise _error(
                "MONITOR_REQUEST_INVALID", "Monitor request headers are invalid", 400
            ) from None

    def authorize(
        self,
        *,
        peer: str | None,
        host: str,
        origin: str | None,
        authorization: str | None,
        cookie: str | None,
        bootstrap: bool,
    ) -> str:
        if peer != self.host:
            raise _error(
                "MONITOR_PEER_REJECTED",
                "Monitor Service accepts IPv4 loopback peers only",
                403,
            )
        if host != f"{self.host}:{self.port}":
            raise _error(
                "MONITOR_HOST_REJECTED", "Monitor Service Host is invalid", 403
            )
        if origin is not None and origin != self.origin:
            raise _error(
                "MONITOR_ORIGIN_REJECTED", "Monitor Service Origin is invalid", 403
            )

        supplied = authorization or ""
        prefix = "Bearer "
        bearer = supplied[len(prefix) :] if supplied.startswith(prefix) else ""
        bearer_ok = len(bearer) == 64 and secrets.compare_digest(bearer, self.token)
        cookie_ok = (
            not bootstrap
            and origin == self.origin
            and isinstance(cookie, str)
            and len(cookie) == 64
            and secrets.compare_digest(cookie, self.token)
        )
        if bearer_ok:
            return "bearer"
        if cookie_ok:
            return "cookie"
        raise _error(
            "MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401
        )


__all__ = [
    "MAX_REQUEST_BYTES",
    "MONITOR_COOKIE_NAME",
    "MonitorAuth",
    "MonitorAuthError",
]
