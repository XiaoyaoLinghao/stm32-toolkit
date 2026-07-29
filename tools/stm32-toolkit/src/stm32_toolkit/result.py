from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Generic, Mapping, TypeVar

T = TypeVar("T")
PROTOCOL_VERSION = "stm32-toolkit/1"


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    protocol: str
    ok: bool
    operation: str
    code: str
    message: str
    data: T | None
    details: Mapping[str, object] = field(default_factory=dict)

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
        return cls(PROTOCOL_VERSION, False, operation, code, message, None, details or {})

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
