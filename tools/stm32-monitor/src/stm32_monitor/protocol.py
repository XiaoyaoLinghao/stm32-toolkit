from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Generic, Mapping, TypeVar, cast

from .models import (
    ObservationBinding,
    ProbeConnectRequest,
    SampleBatch,
    SampleValue,
    WatchGroup,
    WatchItem,
    _freeze_json,
    _thaw_json,
)


MONITOR_PROTOCOL_VERSION = "stm32-toolkit-monitor/1"
MAX_PROTOCOL_BYTES = 1024 * 1024
T = TypeVar("T")
_OPERATION = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*\Z")
_CODE = re.compile(r"(?:OK|MONITOR_[A-Z0-9_]+)\Z")


_CORE_MODEL_SERIALIZERS = {
    ProbeConnectRequest: ProbeConnectRequest.to_dict,
    WatchItem: WatchItem.to_dict,
    WatchGroup: WatchGroup.to_dict,
    ObservationBinding: ObservationBinding.to_dict,
    SampleValue: SampleValue.to_dict,
    SampleBatch: SampleBatch.to_dict,
}


def _known_model_payload(value: object) -> dict[str, object] | None:
    serializer = _CORE_MODEL_SERIALIZERS.get(type(value))
    if serializer is not None:
        return serializer(value)
    value_type = type(value)
    if value_type.__module__ == "stm32_monitor.history" and value_type.__name__ == "HistoryPage":
        from .history import HistoryPage

        if value_type is HistoryPage:
            return HistoryPage.to_dict(value)
    if value_type.__module__ == "stm32_monitor.exports" and value_type.__name__ == "ExportArtifact":
        from .exports import ExportArtifact

        if value_type is ExportArtifact:
            return ExportArtifact.to_dict(value)
    return None


def _snapshot_protocol_value(value: object) -> object:
    payload = _known_model_payload(value)
    if payload is not None:
        _freeze_json(payload)
        value_type = type(value)
        if value_type.__module__ == "stm32_monitor.history" and value_type.__name__ == "HistoryPage":
            from .history import HistoryPage

            if value_type is HistoryPage:
                rows = tuple(
                    cast(Mapping[str, object], _freeze_json(row))
                    for row in value.values
                )
                return HistoryPage(rows, value.next_cursor, value.serialized_bytes)
        return value
    if type(value) in (list, tuple):
        snapshot = tuple(_snapshot_protocol_value(item) for item in value)
        _freeze_json(_serialize_protocol_value(snapshot))
        return snapshot
    return _freeze_json(value)


def _serialize_protocol_value(value: object) -> object:
    payload = _known_model_payload(value)
    if payload is not None:
        return _thaw_json(_freeze_json(payload))
    if type(value) is tuple:
        return [_serialize_protocol_value(item) for item in value]
    return _thaw_json(value)


def _require_protocol_text(
    value: object, label: str, maximum: int, *, allow_empty: bool = False
) -> str:
    if type(value) is not str or "\x00" in value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} is invalid")
    normalized = unicodedata.normalize("NFC", value)
    if (not normalized and not allow_empty) or len(normalized) > maximum:
        raise ValueError(f"{label} is invalid")
    return normalized


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
        if type(self.ok) is not bool:
            raise TypeError("protocol result ok flag must be boolean")
        operation = _require_protocol_text(self.operation, "operation", 128)
        code = _require_protocol_text(self.code, "code", 128)
        message = _require_protocol_text(self.message, "message", 1024, allow_empty=True)
        if _OPERATION.fullmatch(operation) is None:
            raise ValueError("protocol operation is invalid")
        if _CODE.fullmatch(code) is None:
            raise ValueError("protocol code is invalid")
        if type(self.protocol) is not str or self.protocol != MONITOR_PROTOCOL_VERSION:
            raise ValueError("monitor protocol version is invalid")
        if self.ok:
            if code != "OK" or message:
                raise ValueError("successful protocol result is inconsistent")
        elif code == "OK" or not message or self.data is not None:
            raise ValueError("failed protocol result is inconsistent")
        data = _snapshot_protocol_value(self.data)
        details = _freeze_json(self.details)
        if not isinstance(details, Mapping):
            raise TypeError("protocol details must be a JSON object")
        if self.ok and details:
            raise ValueError("successful protocol result cannot include failure details")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "details", cast(Mapping[str, object], details))

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "ok": self.ok,
            "operation": self.operation,
            "code": self.code,
            "message": self.message,
            "data": _serialize_protocol_value(self.data),
            "details": _thaw_json(self.details),
        }


def success(operation: str, data: T) -> ProtocolResult[T]:
    return ProtocolResult(True, operation, "OK", "", data)


def failure(
    operation: str,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> ProtocolResult[None]:
    return ProtocolResult(False, operation, code, message, None, {} if details is None else details)


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
    def reject_constant(_value: str) -> object:
        raise ValueError("non-finite JSON number")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            normalized = unicodedata.normalize("NFC", key)
            if normalized in result:
                raise ValueError("duplicate JSON object key")
            result[normalized] = item
        return result

    try:
        value = json.loads(
            document.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        if type(value) is not dict:
            raise ValueError("root is not an object")
        frozen = _freeze_json(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as error:
        raise ProtocolViolation(invalid_code, "JSON document is invalid") from error
    return cast(dict[str, object], _thaw_json(frozen))
