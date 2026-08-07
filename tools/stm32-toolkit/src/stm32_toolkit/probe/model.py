"""Immutable JSON-safe models for the Probe Service protocol."""

from __future__ import annotations

import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, cast

from stm32_toolkit import __version__

PROBE_PROTOCOL_VERSION = "stm32-toolkit-probe/1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Probe protocol mappings require string keys")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError("Probe protocol values must be JSON-safe")


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_identifier(field_name: str, value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a portable identifier")


def _validate_timestamp(field_name: str, value: str) -> None:
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError(f"{field_name} must be a UTC timestamp with microseconds")


class OperationLevel(str, Enum):
    OBSERVE = "observe"
    CONTROL = "control"
    MODIFY = "modify"

    def allows(self, required: "OperationLevel") -> bool:
        order = {
            OperationLevel.OBSERVE: 0,
            OperationLevel.CONTROL: 1,
            OperationLevel.MODIFY: 2,
        }
        return order[self] >= order[required]


@dataclass(frozen=True)
class ProbeRequest:
    protocol: str
    toolkit_version: str
    request_id: str
    workspace_id: str
    session_id: str
    lease_id: str
    operation_level: OperationLevel
    operation: str
    timeout_ms: int
    data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        frozen = _freeze_json(self.data)
        object.__setattr__(self, "data", cast(Mapping[str, object], frozen))


@dataclass(frozen=True)
class ProbeOwnerEvidence:
    probe_id: str
    workspace_id: str
    session_id: str
    lease_id: str
    pid: int
    operation_level: OperationLevel
    created_at_utc: str
    heartbeat_at_utc: str

    def __post_init__(self) -> None:
        for name in ("probe_id", "workspace_id", "session_id", "lease_id"):
            _validate_identifier(name, getattr(self, name))
        if self.pid < 1:
            raise ValueError("pid must be positive")
        _validate_timestamp("created_at_utc", self.created_at_utc)
        _validate_timestamp("heartbeat_at_utc", self.heartbeat_at_utc)

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "workspaceId": self.workspace_id,
            "sessionId": self.session_id,
            "leaseId": self.lease_id,
            "pid": self.pid,
            "operationLevel": self.operation_level.value,
            "createdAtUtc": self.created_at_utc,
            "heartbeatAtUtc": self.heartbeat_at_utc,
        }


@dataclass(frozen=True)
class ProbeResponse:
    protocol: str
    toolkit_version: str
    request_id: str
    ok: bool
    operation: str
    code: str
    message: str
    data: object
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze_json(self.data))
        frozen_details = _freeze_json(self.details)
        object.__setattr__(self, "details", cast(Mapping[str, object], frozen_details))

    @classmethod
    def success(
        cls, request_id: str, operation: str, data: object
    ) -> "ProbeResponse":
        return cls(
            PROBE_PROTOCOL_VERSION,
            __version__,
            request_id,
            True,
            operation,
            "OK",
            "",
            data,
            {},
        )

    @classmethod
    def failure(
        cls,
        request_id: str,
        operation: str,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> "ProbeResponse":
        return cls(
            PROBE_PROTOCOL_VERSION,
            __version__,
            request_id,
            False,
            operation,
            code,
            message,
            None,
            details or {},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "toolkitVersion": self.toolkit_version,
            "requestId": self.request_id,
            "ok": self.ok,
            "operation": self.operation,
            "code": self.code,
            "message": self.message,
            "data": _thaw_json(self.data),
            "details": _thaw_json(self.details),
        }
