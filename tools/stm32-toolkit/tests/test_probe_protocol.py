from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from stm32_toolkit.probe.model import (
    OperationLevel,
    ProbeOwnerEvidence,
    ProbeRequest,
    ProbeResponse,
)
from stm32_toolkit.probe.protocol import (
    MAX_BATCH_ITEMS,
    MAX_READ_BYTES,
    MAX_REQUEST_BYTES,
    PROBE_PROTOCOL_VERSION,
    ProbeProtocolError,
    decode_request,
    encode_response,
)


TOOLKIT_VERSION = "0.3.0"
REQUEST_ID = "request-123"
WORKSPACE_ID = "workspace-123"
SESSION_ID = "session-123"
LEASE_ID = "lease-123"


def valid_request_dict() -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-probe/1",
        "toolkitVersion": TOOLKIT_VERSION,
        "requestId": REQUEST_ID,
        "workspaceId": WORKSPACE_ID,
        "sessionId": SESSION_ID,
        "leaseId": LEASE_ID,
        "operationLevel": "observe",
        "operation": "memory.read",
        "timeoutMs": 5000,
        "data": {"address": 0x20000000, "length": 16},
    }


def test_probe_protocol_schema_root_and_package_are_byte_identical():
    repo_root = Path(__file__).resolve().parents[3]
    root_schema = repo_root / "schemas" / "probe-protocol.schema.json"
    packaged_schema = (
        repo_root
        / "tools"
        / "stm32-toolkit"
        / "src"
        / "stm32_toolkit"
        / "schemas"
        / "probe-protocol.schema.json"
    )

    assert root_schema.read_bytes() == packaged_schema.read_bytes()


def test_probe_request_schema_accepts_the_protocol_contract():
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "schemas"
            / "probe-protocol.schema.json"
        ).read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator(schema).validate(valid_request_dict())


def test_probe_request_schema_rejects_unknown_fields():
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "schemas"
            / "probe-protocol.schema.json"
        ).read_text(encoding="utf-8")
    )
    request = valid_request_dict()
    request["unexpected"] = True

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(request)


def test_decode_request_returns_an_immutable_typed_snapshot():
    payload = valid_request_dict()

    request = decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)
    payload["data"]["length"] = 999

    assert request == ProbeRequest(
        protocol=PROBE_PROTOCOL_VERSION,
        toolkit_version=TOOLKIT_VERSION,
        request_id=REQUEST_ID,
        workspace_id=WORKSPACE_ID,
        session_id=SESSION_ID,
        lease_id=LEASE_ID,
        operation_level=OperationLevel.OBSERVE,
        operation="memory.read",
        timeout_ms=5000,
        data={"address": 0x20000000, "length": 16},
    )
    with pytest.raises(TypeError):
        request.data["length"] = 8


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("protocol", "stm32-toolkit-probe/2", "PROBE_PROTOCOL_INCOMPATIBLE"),
        ("toolkitVersion", "0.4.0", "PROBE_TOOLKIT_INCOMPATIBLE"),
        ("operationLevel", "admin", "PROBE_REQUEST_INVALID"),
        ("operation", "memory.write", "PROBE_REQUEST_INVALID"),
        ("timeoutMs", 0, "PROBE_REQUEST_INVALID"),
        ("timeoutMs", 30_001, "PROBE_REQUEST_INVALID"),
        ("requestId", "x" * 129, "PROBE_REQUEST_INVALID"),
        ("workspaceId", "../escape", "PROBE_REQUEST_INVALID"),
    ],
)
def test_decode_request_fails_closed_for_invalid_envelope_values(field, value, code):
    payload = valid_request_dict()
    payload[field] = value

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == code
    assert error.value.details["field"] == field
    assert "../escape" not in error.value.message


def test_decode_request_rejects_oversized_body_before_json_parsing():
    body = b"{" + (b" " * MAX_REQUEST_BYTES) + b"}"

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(body, TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_TOO_LARGE"
    assert error.value.details == {"limit": MAX_REQUEST_BYTES}


@pytest.mark.parametrize(
    "data",
    [
        {"address": 0x20000000, "length": 0},
        {"address": 0x20000000, "length": MAX_READ_BYTES + 1},
        {"address": -1, "length": 4},
        {"address": 0x1_0000_0000, "length": 4},
        {"address": 0xFFFF_FFFF, "length": 2},
    ],
)
def test_memory_read_bounds_are_validated_before_backend_dispatch(data):
    payload = valid_request_dict()
    payload["data"] = data

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_INVALID"
    assert error.value.details["field"].startswith("data.")


def test_register_read_batch_is_bounded():
    payload = valid_request_dict()
    payload["operation"] = "register.read"
    payload["data"] = {"names": [f"r{index}" for index in range(MAX_BATCH_ITEMS + 1)]}

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_INVALID"
    assert error.value.details == {"field": "data.names", "rule": "maxItems"}


@pytest.mark.parametrize("operation", ["probe.list", "probe.close"])
def test_parameterless_operations_reject_data_fields(operation):
    payload = valid_request_dict()
    payload["operation"] = operation
    payload["data"] = {"unexpected": True}

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_INVALID"
    assert error.value.details["field"].startswith("data")


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"probeId": "probe-a"},
        {"target": "STM32F429ZITx"},
        {"probeId": "../probe", "target": "STM32F429ZITx"},
        {"probeId": "probe-a", "target": "STM32 F429"},
        {"probeId": "probe-a", "target": "STM32F429ZITx", "halt": True},
    ],
)
def test_attach_requires_only_exact_portable_probe_and_target(data):
    payload = valid_request_dict()
    payload["operation"] = "probe.attach"
    payload["data"] = data

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_INVALID"
    assert error.value.details["field"].startswith("data")


def test_flash_program_accepts_only_modify_level_and_exact_evidence():
    payload = valid_request_dict()
    payload.update(
        {
            "operation": "flash.program",
            "operationLevel": "modify",
            "data": {
                "elfPath": "build/arm-debug/firmware.elf",
                "elfSha256": "ab" * 32,
                "elfSize": 4096,
            },
        }
    )

    request = decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert request.operation_level is OperationLevel.MODIFY
    assert request.operation == "flash.program"
    assert dict(request.data) == payload["data"]


@pytest.mark.parametrize(
    ("operation_level", "data"),
    [
        ("observe", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("control", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "C:/private/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "/private/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build\\fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build/../fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "./build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build/fw.bin", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build/\x00fw.elf", "elfSha256": "ab" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "AB" * 32, "elfSize": 1}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 31, "elfSize": 1}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": True}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 0}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 67_108_865}),
        ("modify", {"elfPath": "build/fw.elf", "elfSha256": "ab" * 32, "elfSize": 1, "extra": 1}),
    ],
)
def test_flash_program_rejects_unsafe_or_ambiguous_evidence(operation_level, data):
    payload = valid_request_dict()
    payload.update(
        {
            "operation": "flash.program",
            "operationLevel": operation_level,
            "data": data,
        }
    )

    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(payload).encode("utf-8"), TOOLKIT_VERSION)

    assert error.value.code == "PROBE_REQUEST_INVALID"


def test_operation_level_order_is_explicit_and_not_string_order():
    assert OperationLevel.OBSERVE.allows(OperationLevel.OBSERVE)
    assert not OperationLevel.OBSERVE.allows(OperationLevel.CONTROL)
    assert OperationLevel.CONTROL.allows(OperationLevel.OBSERVE)
    assert not OperationLevel.CONTROL.allows(OperationLevel.MODIFY)
    assert OperationLevel.MODIFY.allows(OperationLevel.CONTROL)


def test_owner_evidence_is_bounded_and_excludes_secrets_and_host_paths():
    owner = ProbeOwnerEvidence(
        probe_id="probe-123",
        workspace_id=WORKSPACE_ID,
        session_id=SESSION_ID,
        lease_id=LEASE_ID,
        pid=4321,
        operation_level=OperationLevel.OBSERVE,
        created_at_utc="2026-08-07T12:34:56.123456Z",
        heartbeat_at_utc="2026-08-07T12:35:01.123456Z",
    )

    payload = owner.to_dict()

    assert payload == {
        "probeId": "probe-123",
        "workspaceId": WORKSPACE_ID,
        "sessionId": SESSION_ID,
        "leaseId": LEASE_ID,
        "pid": 4321,
        "operationLevel": "observe",
        "createdAtUtc": "2026-08-07T12:34:56.123456Z",
        "heartbeatAtUtc": "2026-08-07T12:35:01.123456Z",
    }
    serialized = json.dumps(payload)
    assert "token" not in serialized.lower()
    assert "C:\\" not in serialized
    assert "/home/" not in serialized


def test_response_encoding_is_deterministic_and_snapshots_payload():
    data = {"values": [{"address": 0x20000000, "value": "0102"}]}
    response = ProbeResponse.success(REQUEST_ID, "memory.read", data)
    data["values"][0]["value"] = "ffff"

    encoded = encode_response(response)

    assert encoded == (
        b'{"code":"OK","data":{"values":[{"address":536870912,"value":"0102"}]},'
        b'"details":{},"message":"","ok":true,"operation":"memory.read",'
        b'"protocol":"stm32-toolkit-probe/1","requestId":"request-123",'
        b'"toolkitVersion":"0.3.0"}'
    )


def test_failure_response_rejects_raw_exception_objects():
    with pytest.raises(TypeError, match="JSON-safe"):
        ProbeResponse.failure(
            request_id=REQUEST_ID,
            operation="memory.read",
            code="PROBE_BACKEND_UNAVAILABLE",
            message="Probe backend is unavailable",
            details={"error": RuntimeError("secret host path C:\\private")},
        )


def test_response_constructor_rejects_invalid_timestamp_in_owner_evidence():
    with pytest.raises(ValueError, match="created_at_utc"):
        ProbeOwnerEvidence(
            probe_id="probe-123",
            workspace_id=WORKSPACE_ID,
            session_id=SESSION_ID,
            lease_id=LEASE_ID,
            pid=4321,
            operation_level=OperationLevel.OBSERVE,
            created_at_utc="2026-08-07 12:34:56",
            heartbeat_at_utc="2026-08-07T12:35:01.123456Z",
        )
