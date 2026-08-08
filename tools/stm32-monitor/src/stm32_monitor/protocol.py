from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, Mapping, TypeVar, cast


MONITOR_PROTOCOL_VERSION = "stm32-toolkit-monitor/1"
MAX_PROTOCOL_BYTES = 1024 * 1024
T = TypeVar("T")


def _freeze(value: object) -> object:
    if isinstance(value, MappingABC):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TypeError("sets are not JSON protocol values")
    return value


def _thaw(value: object) -> object:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _thaw(to_dict())
    if isinstance(value, MappingABC):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class ProtocolResult(Generic[T]):
    ok: bool
    operation: str
    code: str
    message: str
    data: T | None
    details: Mapping[str, object] = field(default_factory=dict)
    protocol: str = MONITOR_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze(self.data))
        object.__setattr__(self, "details", cast(Mapping[str, object], _freeze(self.details)))

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "ok": self.ok,
            "operation": self.operation,
            "code": self.code,
            "message": self.message,
            "data": _thaw(self.data),
            "details": _thaw(self.details),
        }


def success(operation: str, data: T) -> ProtocolResult[T]:
    return ProtocolResult(True, operation, "OK", "", data)


def failure(
    operation: str,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> ProtocolResult[None]:
    return ProtocolResult(False, operation, code, message, None, details or {})


class ProtocolViolation(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def parse_json_object(
    document: bytes,
    *,
    limit: int = MAX_PROTOCOL_BYTES,
    invalid_code: str = "MONITOR_REQUEST_INVALID",
) -> dict[str, object]:
    if not isinstance(document, bytes) or len(document) > limit:
        raise ProtocolViolation(invalid_code, "JSON document exceeds the allowed size")
    try:
        value = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolViolation(invalid_code, "JSON document is invalid") from error
    if not isinstance(value, dict):
        raise ProtocolViolation(invalid_code, "JSON document must be an object")
    return value
