from __future__ import annotations

import json
from pathlib import Path

import pytest

from stm32_toolkit.probe.client import (
    ProbeClient,
    ProbeClientError,
    _decode_response,
    load_probe_endpoint,
)
from stm32_toolkit.probe.backend import FlashBackendReport
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.service import ProbeEndpoint


def endpoint_record() -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-probe/1",
        "toolkitVersion": "0.3.0",
        "url": "http://127.0.0.1:43123",
        "token": "11" * 32,
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "leaseId": "lease-a",
        "probeId": "probe-a",
        "operationLevel": "modify",
    }


def response_record() -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-probe/1",
        "toolkitVersion": "0.3.0",
        "requestId": "request-a",
        "ok": True,
        "operation": "probe.list",
        "code": "OK",
        "message": "",
        "data": {"probes": []},
        "details": {},
    }


def test_program_verified_elf_forces_modify_and_validates_telemetry(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/1",
        toolkit_version="0.3.0",
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    calls = []

    async def request(operation, data, *, operation_level, timeout_ms):
        calls.append((operation, data, operation_level, timeout_ms))
        return {"bytesProgrammed": None, "sectorsProgrammed": 2}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    report = asyncio.run(
        client.program_verified_elf("build/firmware.elf", "ab" * 32, 4096)
    )

    assert report == FlashBackendReport(None, 2)
    assert calls == [
        (
            "flash.program",
            {
                "elfPath": "build/firmware.elf",
                "elfSha256": "ab" * 32,
                "elfSize": 4096,
            },
            OperationLevel.MODIFY,
            30_000,
        )
    ]


def test_attach_returns_strict_physical_target_evidence(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/1",
        toolkit_version="0.3.0",
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
        probe_id="probe-a",
        operation_level=OperationLevel.MODIFY,
    )
    client = ProbeClient(endpoint)

    async def request(*args, **kwargs):
        return {
            "probeId": "probe-a",
            "requestedTarget": "stm32f407vg",
            "resolvedPartNumber": "STM32F407VG",
            "coreCount": 1,
        }

    monkeypatch.setattr(client, "request", request)
    import asyncio

    evidence = asyncio.run(client.attach("probe-a", "stm32f407vg"))
    assert evidence.to_dict() == {
        "probeId": "probe-a",
        "requestedTarget": "stm32f407vg",
        "resolvedPartNumber": "STM32F407VG",
        "coreCount": 1,
    }


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"bytesProgrammed": None},
        {"bytesProgrammed": None, "sectorsProgrammed": None, "extra": 1},
        {"bytesProgrammed": True, "sectorsProgrammed": None},
        {"bytesProgrammed": -1, "sectorsProgrammed": None},
        {"bytesProgrammed": None, "sectorsProgrammed": "2"},
    ],
)
def test_program_verified_elf_rejects_malformed_telemetry(monkeypatch, response):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/1",
        toolkit_version="0.3.0",
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)

    async def request(*args, **kwargs):
        return response

    monkeypatch.setattr(client, "request", request)

    import asyncio

    with pytest.raises(ProbeClientError) as error:
        asyncio.run(client.program_verified_elf("build/fw.elf", "ab" * 32, 1))
    assert error.value.code == "PROBE_RESPONSE_INVALID"


def test_endpoint_loader_rejects_unknown_fields_and_missing_token(tmp_path: Path):
    path = tmp_path / "probe-endpoint.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "stm32-toolkit-probe/1",
                "toolkitVersion": "0.3.0",
                "url": "http://127.0.0.1:43123",
                "token": "11" * 32,
                "workspaceId": "workspace-a",
                "sessionId": "session-a",
                "leaseId": "lease-a",
                "probeId": "probe-a",
                "operationLevel": "modify",
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)

    assert error.value.code == "PROBE_ENDPOINT_INVALID"


def test_endpoint_loader_binds_probe_and_granted_operation_level(tmp_path: Path):
    path = tmp_path / "probe-endpoint.json"
    path.write_bytes(json.dumps(endpoint_record(), sort_keys=True).encode("utf-8"))

    endpoint = load_probe_endpoint(path)

    assert endpoint.probe_id == "probe-a"
    assert endpoint.operation_level is OperationLevel.MODIFY


def test_endpoint_loader_rejects_non_exact_probe_binding(tmp_path: Path):
    record = endpoint_record()
    record["probeId"] = "../probe"
    path = tmp_path / "probe-endpoint.json"
    path.write_bytes(json.dumps(record, sort_keys=True).encode("utf-8"))

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)
    assert error.value.code == "PROBE_ENDPOINT_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol", "stm32-toolkit-probe/2"),
        ("protocol", 1),
        ("toolkitVersion", "0.4.0"),
        ("toolkitVersion", 3),
    ],
)
def test_endpoint_loader_rejects_incompatible_protocol_and_toolkit_version(
    field: str, value: object, tmp_path: Path
):
    record = endpoint_record()
    record[field] = value
    path = tmp_path / "probe-endpoint.json"
    path.write_bytes(json.dumps(record, sort_keys=True).encode("utf-8"))

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)

    assert error.value.code == "PROBE_ENDPOINT_INVALID"


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:43123",
        "http://localhost:43123",
        "https://127.0.0.1:43123",
        "http://127.0.0.1:43123/path",
    ],
)
def test_endpoint_loader_accepts_only_exact_ipv4_loopback(url: str, tmp_path: Path):
    path = tmp_path / "probe-endpoint.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "stm32-toolkit-probe/1",
                "toolkitVersion": "0.3.0",
                "url": url,
                "token": "11" * 32,
                "workspaceId": "workspace-a",
                "sessionId": "session-a",
                "leaseId": "lease-a",
                "probeId": "probe-a",
                "operationLevel": "modify",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)

    assert error.value.code == "PROBE_ENDPOINT_INVALID"


def test_endpoint_loader_does_not_leak_raw_json_errors(tmp_path: Path):
    path = tmp_path / "probe-endpoint.json"
    path.write_bytes(b'{"token":"secret C:\\\\private"')

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)

    assert error.value.code == "PROBE_ENDPOINT_INVALID"
    assert "private" not in error.value.message.lower()
    assert "token" not in error.value.message.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol", "stm32-toolkit-probe/2"),
        ("toolkitVersion", "0.4.0"),
        ("requestId", "request-b"),
        ("operation", "memory.read"),
        ("ok", 1),
        ("code", 7),
        ("details", []),
        ("data", None),
    ],
)
def test_response_decoder_rejects_unrelated_or_malformed_success(
    field: str, value: object
):
    payload = response_record()
    payload[field] = value

    with pytest.raises(ProbeClientError) as error:
        _decode_response(
            json.dumps(payload).encode("utf-8"),
            expected_request_id="request-a",
            expected_operation="probe.list",
        )

    assert error.value.code == "PROBE_RESPONSE_INVALID"


def test_response_decoder_rejects_body_over_one_mebibyte_before_json_use():
    payload = response_record()
    payload["data"] = {"value": "x" * 1_048_576}
    raw = json.dumps(payload).encode("utf-8")
    assert len(raw) > 1_048_576

    with pytest.raises(ProbeClientError) as error:
        _decode_response(raw)

    assert error.value.code == "PROBE_RESPONSE_INVALID"
