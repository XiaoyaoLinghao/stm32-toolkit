from __future__ import annotations

import base64
import asyncio
import json
from pathlib import Path

import jsonschema
import pytest

from stm32_toolkit import __version__
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe import protocol as probe_protocol

PROBE_PROTOCOL_VERSION = probe_protocol.PROBE_PROTOCOL_VERSION
ProbeProtocolError = probe_protocol.ProbeProtocolError
decode_request = probe_protocol.decode_request


ROOT = Path(__file__).parents[3]
ROOT_SCHEMA = ROOT / "schemas" / "probe-protocol.schema.json"
PACKAGED_SCHEMA = ROOT / "tools" / "stm32-toolkit" / "src" / "stm32_toolkit" / "schemas" / "probe-protocol.schema.json"


def request(operation: str, level: str, data: dict[str, object], timeout: int = 5_000) -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-probe/2",
        "toolkitVersion": __version__,
        "requestId": "request-v2",
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "leaseId": "lease-a",
        "operationLevel": level,
        "operation": operation,
        "timeoutMs": timeout,
        "data": data,
    }


def decode(payload: dict[str, object]):
    return decode_request(json.dumps(payload).encode("utf-8"), __version__)


def test_v2_schema_mirrors_and_closed_operation_matrix():
    assert PROBE_PROTOCOL_VERSION == "stm32-toolkit-probe/2"
    assert ROOT_SCHEMA.read_bytes() == PACKAGED_SCHEMA.read_bytes()
    schema = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert set(schema["properties"]["operation"]["enum"]) == {
        "probe.list", "probe.attach", "memory.read", "register.read", "probe.close", "flash.program",
        "target.transport.open", "target.transport.read", "target.transport.close", "target.identity.read",
        "target.state.read", "target.halt", "target.resume", "target.step",
        "target.breakpoint.set", "target.breakpoint.clear", "target.registers.read",
        "target.memory.read", "target.fault.capture", "target.logs.capture",
    }
    assert getattr(probe_protocol, "TARGET_ERROR_CODES", None) == {
        "PROBE_PROTOCOL_INVALID", "PROBE_VERSION_MISMATCH", "PROBE_OPERATION_UNAVAILABLE",
        "PROBE_LEASE_INVALID", "PROBE_AUTHORIZATION_REQUIRED", "PROBE_AUTHORIZATION_INVALID",
        "PROBE_IDENTITY_MISMATCH", "PROBE_LIMIT_EXCEEDED", "PROBE_TIMEOUT",
        "PROBE_BACKPRESSURE", "PROBE_BACKEND_ERROR",
    }


@pytest.mark.parametrize(
    ("operation", "level", "data", "timeout"),
    [
        ("target.transport.open", "observe", {"transport": "mailbox", "config": {}, "deadline_ms": 1}, 1),
        ("target.transport.read", "observe", {"transport_id": "transport-a", "max_bytes": 65_536, "deadline_ms": 300_000}, 300_000),
        ("target.transport.close", "observe", {"transport_id": "transport-a"}, 5_000),
        ("target.identity.read", "observe", {}, 5_000),
        ("target.state.read", "observe", {}, 5_000),
        ("target.halt", "control", {"authorization": "a" * 64}, 5_000),
        ("target.resume", "control", {"authorization": "a" * 64}, 5_000),
        ("target.step", "control", {"authorization": "a" * 64}, 5_000),
        ("target.breakpoint.set", "control", {"address": 0x08000100, "kind": "temporary", "size": 4, "authorization": "a" * 64}, 5_000),
        ("target.breakpoint.clear", "control", {"breakpoint_id": "bp-1", "authorization": "a" * 64}, 5_000),
        ("target.registers.read", "observe", {"names": ["r0", "pc"]}, 5_000),
        ("target.memory.read", "observe", {"address": 0x20000000, "length": 4}, 5_000),
        ("target.fault.capture", "observe", {"max_stack_bytes": 4096}, 5_000),
        ("target.logs.capture", "observe", {"channel": "rtt", "max_bytes": 10_485_760, "duration_ms": 300_000}, 300_000),
    ],
)
def test_every_target_request_has_exact_closed_shape(operation, level, data, timeout):
    decoded = decode(request(operation, level, data, timeout))
    assert decoded.operation == operation
    assert decoded.operation_level.value == level
    mutated = request(operation, level, {**data, "unexpected": True}, timeout)
    with pytest.raises(ProbeProtocolError) as caught:
        decode(mutated)
    assert caught.value.code == "PROBE_PROTOCOL_INVALID"


@pytest.mark.parametrize(
    ("operation", "level", "data"),
    [
        ("target.debug.capture", "observe", {}),
        ("target.log.capture", "observe", {}),
        ("target.step", "control", {"count": 1, "authorization": "a" * 64}),
        ("target.memory.read", "observe", {"address": 0, "length": True}),
        ("target.memory.read", "observe", {"address": 0, "length": 4097}),
        ("target.registers.read", "observe", {"names": ["r0", "R0"]}),
        ("target.registers.read", "observe", {"names": ["r0"] * 65}),
        ("target.fault.capture", "observe", {"max_stack_bytes": -1}),
        ("target.logs.capture", "observe", {"channel": "file", "max_bytes": 1, "duration_ms": 1}),
        ("target.breakpoint.set", "control", {"address": 1, "kind": "permanent", "size": 1, "authorization": "a" * 64}),
    ],
)
def test_v2_rejects_aliases_bool_limits_and_casefold_duplicates(operation, level, data):
    with pytest.raises(ProbeProtocolError) as caught:
        decode(request(operation, level, data))
    assert caught.value.code == "PROBE_PROTOCOL_INVALID"


def test_v1_is_rejected_before_schema_or_backend_work():
    payload = request("target.state.read", "observe", {})
    payload["protocol"] = "stm32-toolkit-probe/1"
    with pytest.raises(ProbeProtocolError) as caught:
        decode(payload)
    assert caught.value.code == "PROBE_VERSION_MISMATCH"


def test_canonical_base64_rule_is_strict():
    encoded = base64.b64encode(b"abc").decode("ascii")
    assert base64.b64decode(encoded, validate=True) == b"abc"
    with pytest.raises(Exception):
        base64.b64decode("YWJj\n", validate=True)


def test_public_client_executes_every_v2_adapter_through_one_service(tmp_path: Path):
    from fakes.fake_probe import FakeProbeBackend
    from stm32_toolkit.probe.backend import ProbeDescriptor
    from stm32_toolkit.probe.client import ProbeClient
    from test_probe_service import make_service

    class Backend(FakeProbeBackend):
        def __init__(self):
            super().__init__(
                probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
                memory={0x20000000: b"abcd"}, registers={"r0": 7, "pc": 0x08000100, "wide": 1 << 40},
            )
            self.transport = b"xyz"
            self.partial_memory = False
            self.bad_fault = False
            self.bad_logs = False
            self.bad_transport = False
            self.identity_error = None
        def target_identity(self):
            if self.identity_error is not None: raise self.identity_error
            return {"board_id": "board-a", "mcu": "stm32f407vg", "target_id": "target-a", "probe_serial_hash": "a" * 64}
        def target_state(self): return {"state": "halted" if self.halted else "running", "reason": "requested"}
        def set_temporary_breakpoint(self, address, size): return {"breakpoint_id": "bp-1", "address": address, "kind": "temporary", "size": size}
        def clear_temporary_breakpoint(self, breakpoint_id): return {"breakpoint_id": breakpoint_id, "cleared": True}
        def read_memory(self, address, length): return b"x" if self.partial_memory else super().read_memory(address, length)
        def capture_fault(self, maximum): return {"fault_registers": {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}, "stack": "bad" if self.bad_fault else b"" if maximum == 0 else b"abcd", "truncated": False}
        def capture_logs(self, channel, maximum, duration): return {"data": "bad" if self.bad_logs else b"log", "truncated": False}
        def open_target_transport(self, transport, config, deadline): return {"transport_id": "transport-1", "identity": self.target_identity()}
        def read_target_transport(self, transport_id, maximum, deadline): data, self.transport = self.transport, b""; return {"data": "bad" if self.bad_transport else data, "eof": False}
        def close_target_transport(self, transport_id): return {"transport_id": transport_id, "closed": True}

    async def scenario():
        backend = Backend()
        service = make_service(tmp_path, level=OperationLevel.CONTROL, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "stm32f407vg")
            assert (await client.target_identity())["target_id"] == "target-a"
            assert (await client.target_state())["state"] == "running"
            assert await client.target_memory(0x20000000, 4) == b"abcd"
            assert (await client.target_registers(("r0", "pc")))[0]["value"] == 7
            assert (await client.target_control("target.halt", {}, "1" * 64))["state"] == "halted"
            stepped = await client.target_control("target.step", {}, "3" * 64)
            assert stepped["pc_before"] == stepped["pc_after"]
            bp = await client.target_control("target.breakpoint.set", {"address": 0x08000100, "kind": "temporary", "size": 2}, "4" * 64)
            assert (await client.target_control("target.breakpoint.clear", {"breakpoint_id": bp["breakpoint_id"]}, "5" * 64))["cleared"] is True
            assert (await client.target_control("target.resume", {}, "2" * 64)) == {"state": "running"}
            assert (await client.target_registers(("wide",)))[0]["width_bits"] == 64
            opened = await client.target_transport_open("mailbox", {}, 100)
            raw, eof = await client.target_transport_read(opened["transport_id"], 16, 100)
            assert (raw, eof) == (b"xyz", False)
            await client.target_transport_close(opened["transport_id"])
            assert (await client.target_fault(0))["stack_artifact"] is None
            assert (await client.target_fault(4))["stack_artifact"]["bytes"] == 4
            assert (await client.target_logs("rtt", 16, 100))["bytes"] == 3
            with pytest.raises(Exception) as reused:
                await client.target_control("target.halt", {}, "1" * 64)
            assert reused.value.code == "PROBE_AUTHORIZATION_INVALID"
            backend.partial_memory = True
            with pytest.raises(Exception) as partial:
                await client.target_memory(0x20000000, 4)
            assert partial.value.code == "PROBE_BACKPRESSURE"
            backend.partial_memory = False
            backend.bad_fault = True
            with pytest.raises(Exception) as bad_fault:
                await client.target_fault(1)
            assert bad_fault.value.code == "PROBE_BACKEND_ERROR"
            backend.bad_fault = False
            backend.bad_logs = True
            with pytest.raises(Exception) as bad_logs:
                await client.target_logs("rtt", 16, 100)
            assert bad_logs.value.code == "PROBE_BACKEND_ERROR"
            backend.bad_logs = False
            backend.transport = b"x"
            backend.bad_transport = True
            opened = await client.target_transport_open("mailbox", {}, 100)
            with pytest.raises(Exception) as bad_transport:
                await client.target_transport_read(opened["transport_id"], 16, 100)
            assert bad_transport.value.code == "PROBE_BACKEND_ERROR"
            from stm32_toolkit.probe.backend import ProbeBackendError
            backend.identity_error = ProbeBackendError(
                "PRIVATE_BACKEND_CODE", "secret C:/private", {"secret": "value"}
            )
            with pytest.raises(Exception) as sanitized:
                await client.target_identity()
            assert (sanitized.value.code, sanitized.value.message, sanitized.value.details) == (
                "PROBE_BACKEND_ERROR", "Probe backend operation failed", {}
            )
        finally:
            await client.close()
            await service.stop()

    asyncio.run(scenario())


def test_admitted_pyocd_adapter_exposes_closed_target_operations():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    class Handle:
        def read(self, maximum, deadline): return b"rtt"
        def close(self): pass

    class Target(FakePyOCDTarget):
        def set_breakpoint(self, address): self.calls.append(("set_breakpoint", address)); return True
        def remove_breakpoint(self, address): self.calls.append(("remove_breakpoint", address))
        def capture_logs(self, channel, maximum, duration): return b"log"
        def open_transport(self, transport, config, deadline): return Handle()

    registers = {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}
    registers.update({"sp": 0x20000000, "pc": 0x08000100})
    target = Target(memory={0x20000000: b"abcd"}, registers=registers)
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile={"board_id": "board-a", "mcu": "stm32f407vg", "target_id": "target-a"},
    )
    backend.open_attach("probe-a", "stm32f407vg")
    assert backend.target_identity()["target_id"] == "target-a"
    assert backend.target_state() == {"state": "halted", "reason": "requested"}
    breakpoint = backend.set_temporary_breakpoint(0x08000100, 2)
    assert backend.clear_temporary_breakpoint(breakpoint["breakpoint_id"])["cleared"] is True
    assert backend.capture_fault(4)["stack"] == b"abcd"
    assert backend.capture_logs("rtt", 4, 1)["data"] == b"log"
    opened = backend.open_target_transport("rtt", {}, 1)
    assert backend.read_target_transport(opened["transport_id"], 4, 1)["data"] == b"rtt"
    assert backend.close_target_transport(opened["transport_id"])["closed"] is True
    backend.close()


def test_public_client_rejects_malformed_target_success_objects():
    from stm32_toolkit.probe.client import ProbeClient, ProbeClientError

    async def scenario():
        client = ProbeClient(object())

        async def returns(value):
            async def request(*args, **kwargs): return value
            client.request = request  # type: ignore[method-assign]

        await returns({"board_id": "b", "mcu": "m", "target_id": "t"})
        with pytest.raises(ProbeClientError): await client.target_identity()
        await returns({"state": "sleeping", "reason": "requested"})
        with pytest.raises(ProbeClientError): await client.target_state()
        with pytest.raises(ProbeClientError): await client.target_control("target.reset", {}, "a" * 64)
        await returns({"address": 1, "length": 1, "data_base64": "***", "sha256": "0" * 64})
        with pytest.raises(ProbeClientError): await client.target_memory(1, 1)
        await returns({"registers": [{"name": "pc", "value": 1, "width_bits": 32}]})
        with pytest.raises(ProbeClientError): await client.target_registers(("r0",))
        await returns({"transport_id": 1, "identity": {}})
        with pytest.raises(ProbeClientError): await client.target_transport_open("mailbox", {}, 1)
        await returns({"data_base64": base64.b64encode(b"too long").decode(), "eof": False})
        with pytest.raises(ProbeClientError): await client.target_transport_read("transport-a", 1, 1)
        await returns({"transport_id": "other", "closed": True})
        with pytest.raises(ProbeClientError): await client.target_transport_close("transport-a")
        await returns({"fault_registers": {}, "stack_artifact": None, "stack_bytes": 0, "truncated": False})
        with pytest.raises(ProbeClientError): await client.target_fault(0)
        await returns({"channel": "rtt", "artifact": {}, "bytes": True, "duration_ms": 1, "truncated": False})
        with pytest.raises(ProbeClientError): await client.target_logs("rtt", 1, 1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("identity", {"board_id": "", "mcu": "m", "target_id": "t", "probe_serial_hash": "a" * 64}),
        ("memory", {"address": 1, "length": 1, "data_base64": 7, "sha256": "0" * 64}),
        ("memory", {"address": 1, "length": 1, "data_base64": base64.b64encode(b"x").decode(), "sha256": "0" * 64}),
        ("registers", {"registers": "not-a-list"}),
        ("transport_read", {"data_base64": 7, "eof": False}),
        ("transport_read", {"data_base64": "***", "eof": False}),
        ("transport_read", {"data_base64": "", "eof": 1}),
        ("logs", {"channel": "uart", "artifact": {}, "bytes": 0, "duration_ms": 1, "truncated": False}),
    ],
)
def test_public_client_rejects_each_malformed_v2_result_branch(method: str, value: object):
    from stm32_toolkit.probe.client import ProbeClient, ProbeClientError

    async def scenario():
        client = ProbeClient(object())

        async def request(*args, **kwargs):
            return value

        client.request = request  # type: ignore[method-assign]
        with pytest.raises(ProbeClientError):
            if method == "identity":
                await client.target_identity()
            elif method == "memory":
                await client.target_memory(1, 1)
            elif method == "registers":
                await client.target_registers(("r0",))
            elif method == "transport_read":
                await client.target_transport_read("transport-a", 1, 1)
            else:
                await client.target_logs("rtt", 1, 1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("list", {"probes": "bad"}),
        ("attach", {"probeId": "p"}),
        ("attach", {"probeId": "p", "requestedTarget": "t", "resolvedPartNumber": "bad value", "coreCount": 1}),
        ("memory", {"bytes": 7}),
        ("registers", {"values": {"r0": True}}),
    ],
)
def test_public_client_rejects_legacy_adapter_results_at_each_closed_boundary(
    method: str, value: object
) -> None:
    from stm32_toolkit.probe.client import ProbeClient, ProbeClientError

    async def scenario() -> None:
        client = ProbeClient(object())

        async def request(*args, **kwargs):
            return value

        client.request = request  # type: ignore[method-assign]
        with pytest.raises(ProbeClientError):
            if method == "list":
                await client.list_probes()
            elif method == "attach":
                await client.attach("p", "t")
            elif method == "memory":
                await client.read_memory(0, 1)
            else:
                await client.read_registers(("r0",))
        await client.close()

    asyncio.run(scenario())


def test_v2_models_reject_non_json_keys_bad_owner_and_lower_access():
    from stm32_toolkit.probe.model import ProbeOwnerEvidence, ProbeRequest

    assert OperationLevel.OBSERVE.allows(OperationLevel.CONTROL) is False
    with pytest.raises(TypeError):
        ProbeRequest("p", "t", "r", "w", "s", "l", OperationLevel.OBSERVE, "op", 1, {1: "bad"})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        ProbeOwnerEvidence("../probe", "w", "s", "l", 1, OperationLevel.OBSERVE, "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z")
    with pytest.raises(ValueError):
        ProbeOwnerEvidence("p", "w", "s", "l", 1, OperationLevel.OBSERVE, "not-utc", "2026-08-16T00:00:00.000000Z")


def test_v2_decoder_rejects_duplicate_members_and_u32_wrap():
    duplicated = json.dumps(request("target.state.read", "observe", {})).replace(
        '"data": {}', '"data": {}, "data": {}'
    ).encode()
    with pytest.raises(ProbeProtocolError):
        decode_request(duplicated, __version__)
    payload = request("memory.read", "observe", {"address": 0xFFFFFFFF, "length": 2})
    with pytest.raises(ProbeProtocolError):
        decode(payload)


def test_v2_decoder_rejects_a_nonobject_json_document():
    with pytest.raises(ProbeProtocolError) as caught:
        decode_request(b"[]", __version__)
    assert caught.value.code == "PROBE_REQUEST_INVALID"


def test_pyocd_target_adapter_fails_closed_on_limits_identity_and_partial_output():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.backend import ProbeBackendError
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    class Handle:
        def __init__(self): self.value: object = b"x"; self.fail = False
        def read(self, maximum, deadline):
            if self.fail: raise RuntimeError("secret C:/private")
            return self.value
        def close(self):
            if self.fail: raise RuntimeError("secret")

    class Target(FakePyOCDTarget):
        def __init__(self):
            regs = {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}
            regs["sp"] = 0x20000000
            super().__init__(memory={0x20000000: b"abcd"}, registers=regs)
            self.break_result: object = True
            self.remove_error = False
            self.log_value: object = b"x"
            self.handle = Handle()
        def set_breakpoint(self, address):
            if isinstance(self.break_result, Exception): raise self.break_result
            return self.break_result
        def remove_breakpoint(self, address):
            if self.remove_error: raise RuntimeError("secret")
        def capture_logs(self, channel, maximum, duration):
            if isinstance(self.log_value, Exception): raise self.log_value
            return self.log_value
        def open_transport(self, transport, config, deadline):
            if config.get("fail"): raise RuntimeError("secret")
            return self.handle

    target = Target()
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile={"board_id": "b", "mcu": "stm32f407vg", "target_id": "t"},
    )
    backend.open_attach("probe-a", "stm32f407vg")
    target.state = "reset"
    assert backend.target_state()["state"] == "reset"
    target.state = "lockedup"
    assert backend.target_state()["state"] == "faulted"
    target.state = "unknown"
    with pytest.raises(ProbeBackendError): backend.target_state()
    with pytest.raises(ProbeBackendError): backend.read_core_registers(("pc",))
    target.state = "halted"
    target.registers["invalid"] = True
    with pytest.raises(ProbeBackendError): backend.read_core_registers(("invalid",))
    with pytest.raises(ProbeBackendError): backend.set_temporary_breakpoint(True, 1)
    target.break_result = RuntimeError("secret C:/private")
    with pytest.raises(ProbeBackendError): backend.set_temporary_breakpoint(0x08000000, 2)
    target.break_result = False
    with pytest.raises(ProbeBackendError): backend.set_temporary_breakpoint(0x08000000, 2)
    target.break_result = True
    for index in range(8): backend.set_temporary_breakpoint(0x08000000 + index * 2, 2)
    with pytest.raises(ProbeBackendError) as limited: backend.set_temporary_breakpoint(0x08000100, 2)
    assert limited.value.code == "PROBE_LIMIT_EXCEEDED"
    with pytest.raises(ProbeBackendError): backend.clear_temporary_breakpoint("missing")
    target.remove_error = True
    with pytest.raises(ProbeBackendError): backend.clear_temporary_breakpoint("bp-1")
    with pytest.raises(ProbeBackendError): backend.capture_fault(True)
    target.state = "halted"
    assert backend.capture_fault(0)["stack"] == b""
    target.memory_error = RuntimeError("unavailable")
    with pytest.raises(ProbeBackendError): backend.capture_fault(1)
    target.memory_error = None
    with pytest.raises(ProbeBackendError): backend.capture_logs("file", 1, 1)
    target.log_value = "bad"
    with pytest.raises(ProbeBackendError): backend.capture_logs("rtt", 1, 1)
    target.log_value = RuntimeError("secret C:/private")
    with pytest.raises(ProbeBackendError): backend.capture_logs("rtt", 1, 1)
    target.log_value = b"xx"
    with pytest.raises(ProbeBackendError) as pressure: backend.capture_logs("rtt", 1, 1)
    assert pressure.value.code == "PROBE_BACKPRESSURE"
    with pytest.raises(ProbeBackendError): backend.open_target_transport("bad", {}, 1)
    with pytest.raises(ProbeBackendError): backend.open_target_transport("rtt", {"fail": True}, 1)
    opened = backend.open_target_transport("rtt", {}, 1)
    with pytest.raises(ProbeBackendError): backend.read_target_transport("missing", 1, 1)
    target.handle.fail = True
    with pytest.raises(ProbeBackendError): backend.read_target_transport(opened["transport_id"], 1, 1)
    target.handle.fail = False
    target.handle.value = "bad"
    with pytest.raises(ProbeBackendError): backend.read_target_transport(opened["transport_id"], 1, 1)
    with pytest.raises(ProbeBackendError): backend.close_target_transport("missing")
    target.handle.fail = True
    with pytest.raises(ProbeBackendError): backend.close_target_transport(opened["transport_id"])
    backend.close()

    mismatch = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=Target()),
        target_profile={"board_id": "b", "mcu": "other", "target_id": "t"},
    )
    mismatch.open_attach("probe-a", "stm32f407vg")
    with pytest.raises(ProbeBackendError) as identity_error: mismatch.target_identity()
    assert identity_error.value.code == "PROBE_IDENTITY_MISMATCH"
    mismatch.close()

    invalid_profile = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=Target()),
        target_profile={"board_id": "", "mcu": "stm32f407vg", "target_id": "t"},
    )
    invalid_profile.open_attach("probe-a", "stm32f407vg")
    with pytest.raises(ProbeBackendError): invalid_profile.target_identity()
    invalid_profile.close()

    class StateFailureTarget(Target):
        def get_state(self):
            raise RuntimeError("secret")

    state_failure = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=StateFailureTarget()),
        target_profile={"board_id": "b", "mcu": "stm32f407vg", "target_id": "t"},
    )
    state_failure.open_attach("probe-a", "stm32f407vg")
    with pytest.raises(ProbeBackendError): state_failure.target_state()
    state_failure.close()
