from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, Mapping, TypeVar, cast

T = TypeVar("T")
PROTOCOL_VERSION = "stm32-toolkit/1"


def _freeze_protocol_value(value: object) -> object:
    """Snapshot JSON-style containers without serializing arbitrary objects.

    OperationResult keeps scalar and custom Generic[T] values opaque. Mappings,
    lists, and tuples are recursively copied into immutable containers so callers
    cannot mutate protocol payloads after construction. Sets and frozensets are
    rejected because they are not JSON protocol values.
    """
    if isinstance(value, MappingABC):
        return MappingProxyType(
            {key: _freeze_protocol_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_protocol_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TypeError("set and frozenset values are not supported in OperationResult payloads")
    return value


def _thaw_protocol_value(value: object) -> object:
    """Convert frozen protocol containers to ordinary JSON-style containers."""
    if isinstance(value, MappingABC):
        return {key: _thaw_protocol_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_protocol_value(item) for item in value]
    return value


def _capture_json_snapshot(data: object) -> object | None:
    """Capture a construction-time immutable JSON snapshot when available.

    When ``data`` provides the explicit Toolkit ``to_dict()`` contract, its
    returned mapping is recursively frozen at construction time so later
    mutation of that mapping cannot change the captured protocol payload and
    ``json.dumps(result.to_dict())`` always succeeds.  Mapping/list/scalar
    data is already snapshotted by the ordinary freeze path and needs no
    separate capture; no arbitrary properties, iterators, serializers, or
    ``repr`` are invoked.
    """
    to_dict = getattr(data, "to_dict", None)
    if to_dict is None:
        return None
    payload = to_dict()
    return _freeze_protocol_value(payload)


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    protocol: str
    ok: bool
    operation: str
    code: str
    message: str
    data: T | None
    details: Mapping[str, object] = field(default_factory=dict)
    _json_data: object | None = field(init=False, repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze_protocol_value(self.data))
        frozen_details = _freeze_protocol_value(self.details)
        object.__setattr__(self, "details", cast(Mapping[str, object], frozen_details))
        object.__setattr__(self, "_json_data", _capture_json_snapshot(self.data))

    @classmethod
    def success(cls, operation: str, data: T) -> "OperationResult[T]":
        return cls(PROTOCOL_VERSION, True, operation, "OK", "", data, {})

    @classmethod
    def failure(
        cls,
        operation: str,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> "OperationResult[None]":
        return cls(
            PROTOCOL_VERSION,
            False,
            operation,
            code,
            message,
            None,
            details if details is not None else {},
        )

    def to_dict(self) -> dict[str, object]:
        data = self._json_data if self._json_data is not None else self.data
        return {
            "protocol": self.protocol,
            "ok": self.ok,
            "operation": self.operation,
            "code": self.code,
            "message": self.message,
            "data": _thaw_protocol_value(data),
            "details": _thaw_protocol_value(self.details),
        }
