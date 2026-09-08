"""Strict asynchronous client for the authenticated loopback Probe Service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
import secrets
import urllib.parse
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import aiohttp

from stm32_toolkit import __version__
from stm32_toolkit.evidence import ArtifactRef, EvidenceValidationError, canonical_json_bytes

from .backend import FlashBackendReport, ProbeAttachmentEvidence
from .model import OperationLevel
from .protocol import PROBE_PROTOCOL_VERSION, TARGET_ERROR_CODES
from .service import ProbeEndpoint
from .authorization import (
    ControlAuthorizationError,
    ControlAuthorizationStore,
    PreparedControlAuthorization,
)
from .selector import (
    probe_fingerprint as calculate_probe_fingerprint,
    public_probe_selector,
    valid_hardware_probe_id,
)

_ENDPOINT_FIELDS = {
    "protocol",
    "toolkitVersion",
    "url",
    "token",
    "workspaceId",
    "sessionId",
    "leaseId",
    "probeId",
    "operationLevel",
}
_RESPONSE_FIELDS = {
    "protocol",
    "toolkitVersion",
    "requestId",
    "ok",
    "operation",
    "code",
    "message",
    "data",
    "details",
}
_PROBE_DESCRIPTOR_FIELDS = {
    "probeId",
    "hardwareId",
    "probeFingerprint",
    "vendor",
    "product",
    "boardName",
}
MAX_RESPONSE_BYTES = 11 * 1_048_576
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ProbeClientError(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _endpoint_error() -> ProbeClientError:
    return ProbeClientError("PROBE_ENDPOINT_INVALID", "Probe endpoint record is invalid")


def _response_error() -> ProbeClientError:
    return ProbeClientError("PROBE_RESPONSE_INVALID", "Probe Service response is invalid")


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError("duplicate response member")
        value[key] = member
    return value


def _valid_probe_display_text(value: object, *, allow_none: bool) -> bool:
    if value is None:
        return allow_none
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= 128
        and all(ord(character) >= 0x20 for character in value)
    )


def _valid_probe_descriptor(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _PROBE_DESCRIPTOR_FIELDS:
        return False
    probe_id = value["probeId"]
    hardware_id = value["hardwareId"]
    fingerprint = value["probeFingerprint"]
    if (
        not isinstance(probe_id, str)
        or _IDENTIFIER.fullmatch(probe_id) is None
        or not valid_hardware_probe_id(hardware_id)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
        or not _valid_probe_display_text(value["vendor"], allow_none=False)
        or not _valid_probe_display_text(value["product"], allow_none=False)
        or not _valid_probe_display_text(value["boardName"], allow_none=True)
    ):
        return False
    try:
        return (
            probe_id == public_probe_selector(hardware_id)
            and fingerprint == calculate_probe_fingerprint(hardware_id)
        )
    except (TypeError, ValueError):
        return False


def _decode_response(
    raw: bytes,
    *,
    expected_request_id: str | None = None,
    expected_operation: str | None = None,
) -> dict[str, object]:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise _response_error()
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_closed_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise _response_error() from error
    if (
        not isinstance(payload, dict)
        or set(payload) != _RESPONSE_FIELDS
        or canonical_json_bytes(payload) != raw
    ):
        raise _response_error()
    if (
        payload["protocol"] != PROBE_PROTOCOL_VERSION
        or payload["toolkitVersion"] != __version__
        or not isinstance(payload["requestId"], str)
        or not payload["requestId"]
        or not isinstance(payload["operation"], str)
        or not payload["operation"]
        or type(payload["ok"]) is not bool
        or not isinstance(payload["code"], str)
        or not isinstance(payload["message"], str)
        or not isinstance(payload["details"], dict)
    ):
        raise _response_error()
    generic_failure = (
        payload["ok"] is False
        and payload["requestId"] == "request-invalid"
        and payload["operation"] == "probe.request"
    )
    if (
        expected_request_id is not None
        and payload["requestId"] != expected_request_id
        and not generic_failure
    ):
        raise _response_error()
    if (
        expected_operation is not None
        and payload["operation"] != expected_operation
        and not generic_failure
    ):
        raise _response_error()
    if payload["ok"] is True:
        if payload["code"] != "OK" or payload["message"] != "" or not isinstance(
            payload["data"], dict
        ):
            raise _response_error()
    else:
        if payload["code"] in ("", "OK") or payload["data"] is not None:
            raise _response_error()
        if (
            expected_operation is not None
            and expected_operation.startswith("target.")
            and not generic_failure
            and payload["code"] not in TARGET_ERROR_CODES
        ):
            raise _response_error()
    return payload


def load_probe_endpoint(path: Path) -> ProbeEndpoint:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != _ENDPOINT_FIELDS:
            raise _endpoint_error()
        if (
            payload["protocol"] != PROBE_PROTOCOL_VERSION
            or payload["toolkitVersion"] != __version__
        ):
            raise _endpoint_error()
        parsed = urllib.parse.urlparse(str(payload["url"]))
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise _endpoint_error()
        token = str(payload["token"])
        if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
            raise _endpoint_error()
        for field in ("workspaceId", "sessionId", "leaseId"):
            value = payload[field]
            if not isinstance(value, str) or not value or len(value) > 128:
                raise _endpoint_error()
        probe_id = payload["probeId"]
        if not isinstance(probe_id, str) or _IDENTIFIER.fullmatch(probe_id) is None:
            raise _endpoint_error()
        try:
            operation_level = OperationLevel(payload["operationLevel"])
        except (TypeError, ValueError) as error:
            raise _endpoint_error() from error
        return ProbeEndpoint(
            protocol=str(payload["protocol"]),
            toolkit_version=str(payload["toolkitVersion"]),
            host="127.0.0.1",
            port=parsed.port,
            token=token,
            workspace_id=str(payload["workspaceId"]),
            session_id=str(payload["sessionId"]),
            lease_id=str(payload["leaseId"]),
            probe_id=probe_id,
            operation_level=operation_level,
            record_path=path,
        )
    except ProbeClientError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise _endpoint_error() from error


class ProbeClient:
    def __init__(
        self,
        endpoint: ProbeEndpoint,
        *,
        extra_headers: Mapping[str, str] | None = None,
        content_type: str = "application/json",
    ) -> None:
        self.endpoint = endpoint
        self._extra_headers = dict(extra_headers or {})
        self._content_type = content_type
        self._session: aiohttp.ClientSession | None = None

    async def _session_for_request(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # The protocol permits a 300-second native operation. Retain one
            # fixed, bounded five-second envelope for response and cleanup.
            timeout = aiohttp.ClientTimeout(total=305)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _send(
        self,
        body: bytes,
        *,
        expected_request_id: str | None = None,
        expected_operation: str | None = None,
    ) -> dict[str, object]:
        session = await self._session_for_request()
        headers = {
            "Authorization": f"Bearer {self.endpoint.token}",
            "Content-Type": self._content_type,
            **self._extra_headers,
        }
        try:
            async with session.post(
                f"{self.endpoint.url}/v1/request", data=body, headers=headers
            ) as response:
                chunks = bytearray()
                while len(chunks) <= MAX_RESPONSE_BYTES:
                    chunk = await response.content.read(
                        min(65_536, MAX_RESPONSE_BYTES + 1 - len(chunks))
                    )
                    if not chunk:
                        break
                    chunks.extend(chunk)
                raw = bytes(chunks)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise _response_error()
        except asyncio.CancelledError:
            raise
        except ProbeClientError:
            raise
        except Exception as error:
            raise ProbeClientError(
                "PROBE_SERVICE_UNAVAILABLE", "Probe Service request failed"
            ) from error
        payload = _decode_response(
            raw,
            expected_request_id=expected_request_id,
            expected_operation=expected_operation,
        )
        if payload.get("ok") is not True:
            raise ProbeClientError(
                str(payload.get("code", "PROBE_RESPONSE_INVALID")),
                str(payload.get("message", "Probe Service request failed")),
                payload.get("details") if isinstance(payload.get("details"), dict) else {},
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProbeClientError(
                "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
            )
        return data

    async def send_raw(self, body: bytes) -> dict[str, object]:
        return await self._send(body)

    async def request(
        self,
        operation: str,
        data: Mapping[str, object],
        *,
        operation_level: OperationLevel = OperationLevel.OBSERVE,
        timeout_ms: int = 5000,
    ) -> dict[str, object]:
        request_id = f"request-{uuid4().hex}"
        payload = {
            "protocol": self.endpoint.protocol,
            "toolkitVersion": self.endpoint.toolkit_version,
            "requestId": request_id,
            "workspaceId": self.endpoint.workspace_id,
            "sessionId": self.endpoint.session_id,
            "leaseId": self.endpoint.lease_id,
            "operationLevel": operation_level.value,
            "operation": operation,
            "timeoutMs": timeout_ms,
            "data": dict(data),
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return await self._send(
            body,
            expected_request_id=request_id,
            expected_operation=operation,
        )

    async def list_probes(self) -> list[dict[str, object]]:
        data = await self.request("probe.list", {})
        probes = data.get("probes")
        if not isinstance(probes, list):
            raise _response_error()
        selectors: set[str] = set()
        for probe in probes:
            if not _valid_probe_descriptor(probe):
                raise _response_error()
            probe_id = probe["probeId"]
            assert isinstance(probe_id, str)
            if probe_id in selectors:
                raise _response_error()
            selectors.add(probe_id)
        return probes

    async def attach(self, probe_id: str, target: str) -> ProbeAttachmentEvidence:
        data = await self.request("probe.attach", {"probeId": probe_id, "target": target})
        if set(data) != {
            "probeId",
            "requestedTarget",
            "resolvedPartNumber",
            "coreCount",
        }:
            raise _response_error()
        if (
            data["probeId"] != probe_id
            or data["requestedTarget"] != target
            or not isinstance(data["resolvedPartNumber"], str)
            or _IDENTIFIER.fullmatch(data["resolvedPartNumber"]) is None
            or type(data["coreCount"]) is not int
            or data["coreCount"] != 1
        ):
            raise _response_error()
        return ProbeAttachmentEvidence(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number=data["resolvedPartNumber"],
            core_count=1,
        )

    async def program_verified_elf(
        self,
        elf_path: str,
        elf_sha256: str,
        elf_size: int,
        *,
        timeout_ms: int = 30_000,
    ) -> FlashBackendReport:
        data = await self.request(
            "flash.program",
            {
                "elfPath": elf_path,
                "elfSha256": elf_sha256,
                "elfSize": elf_size,
            },
            operation_level=OperationLevel.MODIFY,
            timeout_ms=timeout_ms,
        )
        if set(data) != {"bytesProgrammed", "sectorsProgrammed"}:
            raise _response_error()
        values = (data["bytesProgrammed"], data["sectorsProgrammed"])
        if any(
            value is not None
            and (type(value) is not int or value < 0 or value > 0x7FFF_FFFF)
            for value in values
        ):
            raise _response_error()
        return FlashBackendReport(
            bytes_programmed=values[0],
            sectors_programmed=values[1],
        )

    async def read_memory(
        self,
        address: int,
        length: int,
        *,
        timeout_ms: int = 5_000,
    ) -> bytes:
        data = await self.request(
            "memory.read",
            {"address": address, "length": length},
            timeout_ms=timeout_ms,
        )
        encoded = data.get("bytes")
        try:
            if not isinstance(encoded, str):
                raise ValueError
            return bytes.fromhex(encoded)
        except ValueError as error:
            raise ProbeClientError(
                "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
            ) from error

    async def read_registers(self, names: tuple[str, ...]) -> dict[str, int]:
        data = await self.request("register.read", {"names": list(names)})
        values = data.get("values")
        if not isinstance(values, dict) or not all(
            isinstance(name, str) and type(value) is int
            for name, value in values.items()
        ):
            raise ProbeClientError(
                "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
            )
        return values

    @staticmethod
    def _closed_result(data: dict[str, object], fields: set[str]) -> dict[str, object]:
        if set(data) != fields:
            raise _response_error()
        return data

    @staticmethod
    def _decode_canonical_base64(value: object) -> bytes:
        try:
            if not isinstance(value, str):
                raise ValueError
            module = __import__("base64")
            raw = module.b64decode(value, validate=True)
            if module.b64encode(raw).decode("ascii") != value:
                raise ValueError
            return raw
        except (ValueError, TypeError) as error:
            raise _response_error() from error

    @staticmethod
    def _artifact(value: object, *, kind: str, size: int) -> dict[str, object]:
        try:
            artifact = ArtifactRef.from_dict(value)
        except (EvidenceValidationError, TypeError, ValueError) as error:
            raise _response_error() from error
        if (
            artifact.kind != kind
            or artifact.media_type != "application/octet-stream"
            or artifact.size_bytes != size
        ):
            raise _response_error()
        return artifact.to_dict()

    async def target_identity(self) -> dict[str, object]:
        data = await self.request("target.identity.read", {})
        self._closed_result(data, {"board_id", "mcu", "target_id", "probe_serial_hash"})
        if (
            any(not isinstance(data[key], str) or not data[key] for key in ("board_id", "mcu", "target_id"))
            or not isinstance(data["probe_serial_hash"], str)
            or len(data["probe_serial_hash"]) != 64
            or any(character not in "0123456789abcdef" for character in data["probe_serial_hash"])
        ):
            raise _response_error()
        return data

    async def target_state(self) -> dict[str, object]:
        data = await self.request("target.state.read", {})
        self._closed_result(data, {"state", "reason"})
        if data["state"] not in {"running", "halted", "reset", "faulted"} or data["reason"] not in {
            "requested", "breakpoint", "watchpoint", "fault", "exception", "reset"
        }:
            raise _response_error()
        return data

    async def target_control(
        self, operation: str, arguments: Mapping[str, object], authorization: str
    ) -> dict[str, object]:
        if operation not in {
            "target.halt", "target.resume", "target.reset", "target.step",
            "target.breakpoint.set", "target.breakpoint.clear",
        }:
            raise ProbeClientError("PROBE_PROTOCOL_INVALID", "Target control operation is invalid")
        result = await self.request(
            operation, {**dict(arguments), "authorization": authorization},
            operation_level=OperationLevel.CONTROL,
            timeout_ms=5_000 if operation == "target.step" else 30_000,
        )
        expected: dict[str, set[str]] = {
            "target.halt": {"state", "reason"},
            "target.resume": {"state"},
            "target.step": {"state", "reason", "pc_before", "pc_after"},
            "target.breakpoint.set": {"breakpoint_id", "address", "kind", "size"},
            "target.breakpoint.clear": {"breakpoint_id", "cleared"},
        }
        if operation == "target.reset":
            if set(result) not in ({"state"}, {"state", "reason"}):
                raise _response_error()
        else:
            self._closed_result(result, expected[operation])
        if operation == "target.halt" and result != {"state": "halted", "reason": "requested"}:
            raise _response_error()
        if operation == "target.resume" and result != {"state": "running"}:
            raise _response_error()
        if operation == "target.reset" and result not in (
            {"state": "running"}, {"state": "halted", "reason": "reset"}
        ):
            raise _response_error()
        if operation == "target.step" and (
            result.get("state") != "halted"
            or result.get("reason") != "requested"
            or type(result.get("pc_before")) is not int
            or type(result.get("pc_after")) is not int
            or not 0 <= result["pc_before"] < 1 << 64
            or not 0 <= result["pc_after"] < 1 << 64
        ):
            raise _response_error()
        if operation == "target.breakpoint.set" and (
            result.get("kind") != "temporary"
            or type(result.get("address")) is not int
            or type(result.get("size")) is not int
            or result.get("address") != arguments.get("address")
            or result.get("size") != arguments.get("size")
            or not isinstance(result.get("breakpoint_id"), str)
            or _IDENTIFIER.fullmatch(result["breakpoint_id"]) is None
        ):
            raise _response_error()
        if operation == "target.breakpoint.clear" and (
            result.get("breakpoint_id") != arguments.get("breakpoint_id")
            or result.get("cleared") is not True
        ):
            raise _response_error()
        return result

    async def target_memory(self, address: int, length: int, *, timeout_ms: int = 5_000) -> bytes:
        data = await self.request("target.memory.read", {"address": address, "length": length}, timeout_ms=timeout_ms)
        self._closed_result(data, {"address", "length", "data_base64", "sha256"})
        raw = self._decode_canonical_base64(data["data_base64"])
        if (
            type(data["address"]) is not int
            or type(data["length"]) is not int
            or data["address"] != address
            or data["length"] != length
            or len(raw) != length
            or not isinstance(data["sha256"], str)
            or sha256(raw).hexdigest() != data["sha256"]
        ):
            raise _response_error()
        return raw

    async def target_registers(self, names: tuple[str, ...]) -> tuple[dict[str, object], ...]:
        data = await self.request("target.registers.read", {"names": list(names)})
        self._closed_result(data, {"registers"})
        registers = data["registers"]
        if (
            not isinstance(registers, list)
            or len(registers) != len(names)
            or any(
                not isinstance(item, dict)
                or set(item) != {"name", "value", "width_bits"}
                or item["name"] != names[index]
                or type(item["value"]) is not int
                or not 0 <= item["value"] < 1 << 64
                or item["width_bits"] not in (32, 64)
                or (item["width_bits"] == 32 and item["value"] > 0xFFFF_FFFF)
                for index, item in enumerate(registers)
            )
        ):
            raise _response_error()
        return tuple(dict(item) for item in registers if isinstance(item, dict))

    async def target_transport_open(self, transport: str, config: Mapping[str, object], deadline_ms: int) -> dict[str, object]:
        data = await self.request(
            "target.transport.open", {"transport": transport, "config": dict(config), "deadline_ms": deadline_ms},
            timeout_ms=deadline_ms,
        )
        self._closed_result(data, {"transport_id", "identity"})
        if (
            not isinstance(data["transport_id"], str)
            or _IDENTIFIER.fullmatch(data["transport_id"]) is None
            or not isinstance(data["identity"], dict)
        ):
            raise _response_error()
        identity = data["identity"]
        if (
            not identity
            or any(not isinstance(key, str) or not isinstance(value, str) or not value for key, value in identity.items())
        ):
            raise _response_error()
        return data

    async def target_transport_read(self, transport_id: str, max_bytes: int, deadline_ms: int) -> tuple[bytes, bool]:
        data = await self.request(
            "target.transport.read", {"transport_id": transport_id, "max_bytes": max_bytes, "deadline_ms": deadline_ms},
            timeout_ms=deadline_ms,
        )
        self._closed_result(data, {"data_base64", "eof"})
        if type(data["eof"]) is not bool:
            raise _response_error()
        raw = self._decode_canonical_base64(data["data_base64"])
        if len(raw) > max_bytes:
            raise _response_error()
        return raw, data["eof"]

    async def target_transport_close(self, transport_id: str) -> None:
        data = await self.request("target.transport.close", {"transport_id": transport_id})
        self._closed_result(data, {"transport_id", "closed"})
        if data != {"transport_id": transport_id, "closed": True}:
            raise _response_error()

    async def target_fault(self, max_stack_bytes: int) -> dict[str, object]:
        data = await self.request("target.fault.capture", {"max_stack_bytes": max_stack_bytes})
        self._closed_result(data, {"fault_registers", "stack_artifact", "stack_bytes", "truncated"})
        registers = data["fault_registers"]
        if (
            not isinstance(registers, dict)
            or set(registers) != {"cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr"}
            or any(type(value) is not int or not 0 <= value <= 0xFFFF_FFFF for value in registers.values())
            or type(data["stack_bytes"]) is not int
            or not 0 <= data["stack_bytes"] <= max_stack_bytes
            or type(data["truncated"]) is not bool
        ):
            raise _response_error()
        if data["stack_bytes"] == 0:
            if data["stack_artifact"] is not None:
                raise _response_error()
        else:
            data["stack_artifact"] = self._artifact(
                data["stack_artifact"], kind="fault-stack", size=data["stack_bytes"]
            )
        return data

    async def target_logs(self, channel: str, max_bytes: int, duration_ms: int) -> dict[str, object]:
        data = await self.request(
            "target.logs.capture", {"channel": channel, "max_bytes": max_bytes, "duration_ms": duration_ms},
            timeout_ms=duration_ms,
        )
        self._closed_result(data, {"channel", "artifact", "bytes", "duration_ms", "truncated"})
        if data["channel"] != channel or data["duration_ms"] != duration_ms or type(data["bytes"]) is not int or not 0 <= data["bytes"] <= max_bytes or type(data["truncated"]) is not bool:
            raise _response_error()
        data["artifact"] = self._artifact(
            data["artifact"], kind="target-logs", size=data["bytes"]
        )
        return data

    async def close(self) -> None:
        if self._session is None or self._session.closed:
            return
        await self._session.close()


class ControlAuthorizationClient:
    """Prepare through the same persistent store consumed by Probe Service."""

    def __init__(self, store: ControlAuthorizationStore, probe: object) -> None:
        if not isinstance(store, ControlAuthorizationStore):
            raise TypeError("Control authorization client requires the service authorization store")
        self._store = store
        self._probe = probe

    async def prepare(self, *, now: datetime | None = None, **binding: object) -> PreparedControlAuthorization:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ProbeClientError("PROBE_PROTOCOL_INVALID", "Authorization time must be UTC aware")
        operation = binding.get("operation")
        arguments = binding.get("arguments")
        if operation not in {"target.halt", "target.resume", "target.reset", "target.step", "target.breakpoint.set", "target.breakpoint.clear"} or not isinstance(arguments, Mapping):
            raise ProbeClientError("PROBE_PROTOCOL_INVALID", "Control authorization binding is invalid")
        identity = await self._probe.target_identity()
        state = await self._probe.target_state()
        try:
            return self._store.prepare(
                {**binding, "identity_snapshot": identity, "state_snapshot": state},
                now=instant,
            )
        except ControlAuthorizationError as error:
            raise ProbeClientError(error.code, error.message) from error

    async def execute(
        self, prepared: PreparedControlAuthorization, authorized_digest: str,
        *, now: datetime | None = None,
    ) -> dict[str, object]:
        try:
            return await self._probe.target_control(
                str(prepared.binding["operation"]),
                dict(prepared.binding["arguments"]),
                authorized_digest,
            )
        finally:
            await self._probe.close()


__all__ = [
    "PROBE_PROTOCOL_VERSION",
    "ProbeClient",
    "ProbeClientError",
    "ControlAuthorizationClient",
    "PreparedControlAuthorization",
    "load_probe_endpoint",
]
