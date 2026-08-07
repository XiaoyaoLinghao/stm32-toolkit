"""Strict decoding and deterministic encoding for Probe Service messages."""

from __future__ import annotations

import json
from importlib import resources
from typing import Mapping

import jsonschema

from .model import OperationLevel, ProbeRequest, ProbeResponse

PROBE_PROTOCOL_VERSION = "stm32-toolkit-probe/1"
MAX_REQUEST_BYTES = 65_536
MAX_READ_BYTES = 65_536
MAX_BATCH_ITEMS = 256


class ProbeProtocolError(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeProtocolError(
                "PROBE_REQUEST_INVALID",
                "Probe request contains a duplicate field",
                {"field": key, "rule": "unique"},
            )
        result[key] = value
    return result


def _load_schema() -> dict[str, object]:
    text = (
        resources.files("stm32_toolkit.schemas")
        .joinpath("probe-protocol.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _validation_details(error: jsonschema.ValidationError) -> dict[str, object]:
    field = ".".join(str(item) for item in error.absolute_path)
    if error.validator == "additionalProperties":
        field = field or "request"
    return {"field": field or "request", "rule": str(error.validator)}


def _validate_operation_data(payload: dict[str, object]) -> None:
    operation = payload["operation"]
    data = payload["data"]
    if not isinstance(data, dict):
        return
    if operation == "memory.read":
        address = data["address"]
        length = data["length"]
        if isinstance(address, int) and isinstance(length, int):
            if address + length > 0x1_0000_0000:
                raise ProbeProtocolError(
                    "PROBE_REQUEST_INVALID",
                    "Memory read exceeds the target address space",
                    {"field": "data.length", "rule": "addressRange"},
                )


def decode_request(body: bytes, expected_toolkit_version: str) -> ProbeRequest:
    if len(body) > MAX_REQUEST_BYTES:
        raise ProbeProtocolError(
            "PROBE_REQUEST_TOO_LARGE",
            "Probe request exceeds the body limit",
            {"limit": MAX_REQUEST_BYTES},
        )
    try:
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ProbeProtocolError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeProtocolError(
            "PROBE_REQUEST_INVALID",
            "Probe request is not valid UTF-8 JSON",
            {"field": "request", "rule": "json"},
        ) from error
    if not isinstance(payload, dict):
        raise ProbeProtocolError(
            "PROBE_REQUEST_INVALID",
            "Probe request must be a JSON object",
            {"field": "request", "rule": "type"},
        )

    if payload.get("protocol") != PROBE_PROTOCOL_VERSION:
        raise ProbeProtocolError(
            "PROBE_PROTOCOL_INCOMPATIBLE",
            "Probe protocol version is incompatible",
            {"field": "protocol", "rule": "const"},
        )
    if payload.get("toolkitVersion") != expected_toolkit_version:
        raise ProbeProtocolError(
            "PROBE_TOOLKIT_INCOMPATIBLE",
            "Toolkit version is incompatible with the Probe Service",
            {"field": "toolkitVersion", "rule": "const"},
        )

    try:
        jsonschema.Draft202012Validator(_load_schema()).validate(payload)
    except jsonschema.ValidationError as error:
        raise ProbeProtocolError(
            "PROBE_REQUEST_INVALID",
            "Probe request does not match the protocol schema",
            _validation_details(error),
        ) from error

    _validate_operation_data(payload)
    return ProbeRequest(
        protocol=str(payload["protocol"]),
        toolkit_version=str(payload["toolkitVersion"]),
        request_id=str(payload["requestId"]),
        workspace_id=str(payload["workspaceId"]),
        session_id=str(payload["sessionId"]),
        lease_id=str(payload["leaseId"]),
        operation_level=OperationLevel(str(payload["operationLevel"])),
        operation=str(payload["operation"]),
        timeout_ms=int(payload["timeoutMs"]),
        data=payload["data"],
    )


def encode_response(response: ProbeResponse) -> bytes:
    try:
        return json.dumps(
            response.to_dict(),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TypeError("Probe response must contain only JSON-safe values") from error
