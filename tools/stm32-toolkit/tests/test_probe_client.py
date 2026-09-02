from __future__ import annotations

import json
from pathlib import Path

import pytest

from stm32_toolkit import __version__
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
        "protocol": "stm32-toolkit-probe/2",
        "toolkitVersion": __version__,
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
        "protocol": "stm32-toolkit-probe/2",
        "toolkitVersion": __version__,
        "requestId": "request-a",
        "ok": True,
        "operation": "probe.list",
        "code": "OK",
        "message": "",
        "data": {"probes": []},
        "details": {},
    }


ATK_RAW = "ATK 20210914"
ATK_FINGERPRINT = "91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c"
ATK_SELECTOR = f"pyocd:{ATK_FINGERPRINT}"


def probe_descriptor_record() -> dict[str, object]:
    return {
        "probeId": ATK_SELECTOR,
        "hardwareId": ATK_RAW,
        "probeFingerprint": ATK_FINGERPRINT,
        "vendor": "ATK",
        "product": "ATK-HS-V3-CMSIS-DAP",
        "boardName": None,
    }


def test_program_verified_elf_forces_modify_and_validates_telemetry(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
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
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
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
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
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
                "protocol": "stm32-toolkit-probe/2",
                "toolkitVersion": __version__,
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


@pytest.mark.parametrize(
    ("field", "value"),
    [("token", "bad"), ("workspaceId", ""), ("operationLevel", "invalid")],
)
def test_endpoint_loader_rejects_each_closed_credential_and_binding_boundary(
    field: str, value: object, tmp_path: Path,
) -> None:
    record = endpoint_record()
    record[field] = value
    path = tmp_path / f"invalid-{field}.json"
    path.write_bytes(json.dumps(record, sort_keys=True).encode("utf-8"))
    with pytest.raises(ProbeClientError) as caught:
        load_probe_endpoint(path)
    assert caught.value.code == "PROBE_ENDPOINT_INVALID"


def test_endpoint_loader_rejects_non_exact_probe_binding(tmp_path: Path):
    record = endpoint_record()
    record["probeId"] = "../probe"
    path = tmp_path / "probe-endpoint.json"
    path.write_bytes(json.dumps(record, sort_keys=True).encode("utf-8"))

    with pytest.raises(ProbeClientError) as error:
        load_probe_endpoint(path)
    assert error.value.code == "PROBE_ENDPOINT_INVALID"


def test_list_probes_accepts_the_closed_six_field_descriptor_shape(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    record = probe_descriptor_record()

    async def request(*args, **kwargs):
        return {"probes": [record]}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    assert asyncio.run(client.list_probes()) == [record]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_key",
        "extra_key",
        "nonportable_probe_id",
        "invalid_hardware_id",
        "non_hex_fingerprint",
        "wrong_fingerprint",
        "fingerprint_not_matching_hardware_id",
        "malformed_vendor",
        "malformed_product",
        "malformed_board_name",
        "inconsistent_legacy_selector_mapping",
    ],
)
def test_list_probes_rejects_every_malformed_closed_descriptor(
    monkeypatch, mutation: str
) -> None:
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    record = probe_descriptor_record()
    if mutation == "missing_key":
        del record["hardwareId"]
    elif mutation == "extra_key":
        record["unexpected"] = True
    elif mutation == "nonportable_probe_id":
        record["probeId"] = ATK_RAW
    elif mutation == "invalid_hardware_id":
        record["hardwareId"] = None
    elif mutation == "non_hex_fingerprint":
        record["probeFingerprint"] = "g" * 64
    elif mutation == "wrong_fingerprint":
        record["probeFingerprint"] = "0" * 64
    elif mutation == "fingerprint_not_matching_hardware_id":
        record["probeId"] = "probe-b"
        record["hardwareId"] = "probe-b"
    elif mutation == "malformed_vendor":
        record["vendor"] = " \n"
    elif mutation == "malformed_product":
        record["product"] = "p" * 129
    elif mutation == "malformed_board_name":
        record["boardName"] = 123
    elif mutation == "inconsistent_legacy_selector_mapping":
        record["probeId"] = "probe-b"
        record["hardwareId"] = "probe-a"
        record["probeFingerprint"] = "6794af8371f2ba4c09d5fdb157bde8cfa7666c27897128d8ce23a9bddbfb6811"
    else:
        raise AssertionError(f"unknown mutation {mutation}")

    async def request(*args, **kwargs):
        return {"probes": [record]}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    with pytest.raises(ProbeClientError) as error:
        asyncio.run(client.list_probes())
    assert error.value.code == "PROBE_RESPONSE_INVALID"
    assert error.value.message == "Probe Service response is invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor", ""),
        ("vendor", " Arm"),
        ("vendor", "Arm "),
        ("vendor", "A\nrm"),
        ("vendor", "v" * 129),
        ("product", ""),
        ("product", " CMSIS-DAP"),
        ("product", "CMSIS-DAP "),
        ("product", "C\tMSIS-DAP"),
        ("product", "p" * 129),
        ("boardName", ""),
        ("boardName", " Board"),
        ("boardName", "Board "),
        ("boardName", "B\x1bOARD"),
        ("boardName", "b" * 129),
    ],
)
def test_list_probes_rejects_each_malformed_display_field(
    monkeypatch, field: str, value: str
) -> None:
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    record = probe_descriptor_record()
    record[field] = value

    async def request(*args, **kwargs):
        return {"probes": [record]}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    with pytest.raises(ProbeClientError) as error:
        asyncio.run(client.list_probes())
    assert error.value.code == "PROBE_RESPONSE_INVALID"
    assert error.value.message == "Probe Service response is invalid"


def test_list_probes_rejects_duplicate_public_selectors(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    records = [probe_descriptor_record(), probe_descriptor_record()]

    async def request(*args, **kwargs):
        return {"probes": records}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    with pytest.raises(ProbeClientError) as error:
        asyncio.run(client.list_probes())
    assert error.value.code == "PROBE_RESPONSE_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol", "stm32-toolkit-probe/1"),
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
                "protocol": "stm32-toolkit-probe/2",
                "toolkitVersion": __version__,
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
        ("protocol", "stm32-toolkit-probe/1"),
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


def test_response_decoder_rejects_body_over_bounded_10_mib_envelope_before_json_use():
    payload = response_record()
    payload["data"] = {"value": "x" * (11 * 1_048_576)}
    raw = json.dumps(payload).encode("utf-8")
    assert len(raw) > 11 * 1_048_576

    with pytest.raises(ProbeClientError) as error:
        _decode_response(raw)

    assert error.value.code == "PROBE_RESPONSE_INVALID"


@pytest.mark.parametrize(
    "mutation",
    [
        {"ok": False, "code": "OK", "message": "failed", "data": None},
        {"ok": False, "code": "PROBE_BACKEND_ERROR", "message": "failed", "data": {}},
    ],
)
def test_response_decoder_rejects_internally_contradictory_failure(mutation: dict[str, object]) -> None:
    payload = {**response_record(), **mutation}
    with pytest.raises(ProbeClientError) as caught:
        _decode_response(json.dumps(payload).encode("utf-8"))
    assert caught.value.code == "PROBE_RESPONSE_INVALID"


def test_close_is_transport_only_and_never_requests_backend_close():
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    events: list[str] = []

    class Transport:
        closed = False

        async def close(self):
            events.append("transport.close")
            self.closed = True

    client._session = Transport()  # type: ignore[assignment]

    import asyncio

    asyncio.run(client.close())

    assert events == ["transport.close"]


def test_client_transport_timeout_covers_the_300_second_protocol_limit():
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2", toolkit_version=__version__,
        host="127.0.0.1", port=43123, token="11" * 32,
        workspace_id="workspace-a", session_id="session-a", lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    import asyncio

    async def scenario():
        session = await client._session_for_request()
        try:
            assert session.timeout.total == 305
        finally:
            await client.close()

    asyncio.run(scenario())
