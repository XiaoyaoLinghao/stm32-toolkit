"""Strict asynchronous client for the authenticated loopback Probe Service."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import aiohttp

from stm32_toolkit import __version__

from .backend import FlashBackendReport, ProbeAttachmentEvidence
from .model import OperationLevel
from .protocol import PROBE_PROTOCOL_VERSION
from .service import ProbeEndpoint

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
MAX_RESPONSE_BYTES = 1_048_576
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


def _decode_response(
    raw: bytes,
    *,
    expected_request_id: str | None = None,
    expected_operation: str | None = None,
) -> dict[str, object]:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise _response_error()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _response_error() from error
    if not isinstance(payload, dict) or set(payload) != _RESPONSE_FIELDS:
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
    elif payload["code"] in ("", "OK") or payload["data"] is not None:
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
            timeout = aiohttp.ClientTimeout(total=31)
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
                try:
                    raw = await response.content.readexactly(MAX_RESPONSE_BYTES + 1)
                except asyncio.IncompleteReadError as error:
                    raw = error.partial
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
        if not isinstance(probes, list) or not all(isinstance(item, dict) for item in probes):
            raise ProbeClientError(
                "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
            )
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

    async def read_memory(self, address: int, length: int) -> bytes:
        data = await self.request("memory.read", {"address": address, "length": length})
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
            isinstance(name, str) and isinstance(value, int)
            for name, value in values.items()
        ):
            raise ProbeClientError(
                "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
            )
        return values

    async def close(self) -> None:
        if self._session is None or self._session.closed:
            return
        try:
            await self.request("probe.close", {})
        finally:
            await self._session.close()


__all__ = [
    "PROBE_PROTOCOL_VERSION",
    "ProbeClient",
    "ProbeClientError",
    "load_probe_endpoint",
]
