from __future__ import annotations

import base64
import asyncio
import json
from hashlib import sha256
from pathlib import Path

import jsonschema
import pytest

from stm32_toolkit import __version__
from stm32_toolkit.evidence import canonical_json_bytes
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
         "target.reset",
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
        ("target.transport.open", "observe", {"transport": "mailbox", "config": {"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096}}, "deadline_ms": 1}, 1),
        ("target.transport.read", "observe", {"transport_id": "transport-a", "max_bytes": 65_536, "deadline_ms": 300_000}, 300_000),
        ("target.transport.close", "observe", {"transport_id": "transport-a"}, 5_000),
        ("target.identity.read", "observe", {}, 5_000),
        ("target.state.read", "observe", {}, 5_000),
         ("target.halt", "control", {"authorization": "a" * 64}, 5_000),
         ("target.resume", "control", {"authorization": "a" * 64}, 5_000),
         ("target.reset", "control", {"authorization": "a" * 64}, 5_000),
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


@pytest.mark.parametrize(
    ("transport", "config"),
    [
        ("mailbox", {}),
        ("mailbox", {"kind": "rtt", "options": {"channel": 0}}),
        ("rtt", {"kind": "rtt", "options": {"channel": True}}),
        ("uart", {"kind": "uart", "options": {"port": "COM3", "baud": 123}}),
        ("semihosting", {"kind": "semihosting", "options": {"hostFile": True}}),
    ],
)
def test_target_transport_config_is_the_closed_project_v3_union(transport, config):
    with pytest.raises(ProbeProtocolError) as caught:
        decode(request("target.transport.open", "observe", {
            "transport": transport, "config": config, "deadline_ms": 100,
        }))
    assert caught.value.code == "PROBE_PROTOCOL_INVALID"


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
            self.identity_reads = 0
            self.malformed = ""
        def target_observation_policy(self):
            return {
                "readable_regions": [{"start": 0x20000000, "size": 4}],
                "register_allowlist": ["pc", "r0", "wide"],
            }
        def target_identity(self):
            self.identity_reads += 1
            if self.identity_error is not None: raise self.identity_error
            return {"board_id": "board-a", "mcu": "stm32f407vg", "target_id": "target-a", "probe_serial_hash": "a" * 64}
        def target_state(self):
            return {
                "state": (
                    "running" if self.malformed == "halt"
                    else "halted" if self.malformed == "resume"
                    else "halted" if self.halted else "running"
                ),
                "reason": "requested",
            }
        def set_temporary_breakpoint(self, address, size):
            return {"breakpoint_id": "bp-1", "address": address + (1 if self.malformed == "breakpoint" else 0), "kind": "temporary", "size": size}
        def clear_temporary_breakpoint(self, breakpoint_id):
            return {"breakpoint_id": breakpoint_id, "cleared": self.malformed != "clear"}
        def read_memory(self, address, length): return b"x" if self.partial_memory else super().read_memory(address, length)
        def read_core_registers(self, names):
            if self.malformed == "step-register": return {}
            if self.malformed == "register": return {name: True for name in names}
            return super().read_core_registers(names)
        def target_read_memory(self, address, length):
            return self.read_memory(address, length)
        def target_read_core_registers(self, names):
            return self.read_core_registers(names)
        def capture_fault(self, maximum):
            if self.malformed == "fault-shape": return {"stack": b"", "truncated": False}
            return {"fault_registers": {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}, "stack": "bad" if self.bad_fault else b"" if maximum == 0 else b"abcd", "truncated": False}
        def capture_logs(self, channel, maximum, duration):
            result = {"data": "bad" if self.bad_logs else b"log", "truncated": 1 if self.malformed == "logs-truncated" else False}
            if self.malformed == "logs-extra": result["extra"] = True
            return result
        def open_target_transport(self, transport, config, deadline):
            return {"transport_id": 1 if self.malformed == "transport-open" else "transport-1", "identity": self.target_identity()}
        def read_target_transport(self, transport_id, maximum, deadline):
            data, self.transport = self.transport, b""
            result = {"data": "bad" if self.bad_transport else data, "eof": 1 if self.malformed == "transport-read" else False}
            if self.malformed == "transport-extra": result["extra"] = True
            return result
        def close_target_transport(self, transport_id):
            return {"transport_id": transport_id, "closed": self.malformed != "transport-close"}

    async def scenario():
        from stm32_toolkit.probe.authorization import ControlAuthorizationStore

        backend = Backend()
        authorizations = ControlAuthorizationStore((tmp_path / "control").absolute())
        service = make_service(
            tmp_path,
            level=OperationLevel.CONTROL,
            backend=backend,
            control_authorizations=authorizations,
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        def authorize(operation, arguments):
            identity = backend.target_identity()
            return authorizations.prepare(
                {
                    "workspace_id": "workspace-a", "project_id": "project-a",
                    "session_id": "session-a", "revision": "rev-a", "target": identity,
                    "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
                    "operation": operation, "arguments": arguments,
                    "identity_snapshot": identity, "state_snapshot": backend.target_state(),
                }
            ).action_digest
        try:
            await client.attach("probe-a", "stm32f407vg")
            assert (await client.target_identity())["target_id"] == "target-a"
            assert (await client.target_state())["state"] == "running"
            assert await client.target_memory(0x20000000, 4) == b"abcd"
            assert (await client.target_registers(("r0", "pc")))[0]["value"] == 7
            identity_reads = backend.identity_reads
            with pytest.raises(Exception) as unknown:
                await client.target_control("target.halt", {}, "1" * 64)
            assert unknown.value.code == "PROBE_AUTHORIZATION_INVALID"
            assert backend.identity_reads == identity_reads
            halt = authorize("target.halt", {})
            assert (await client.target_control("target.halt", {}, halt))["state"] == "halted"
            stepped = await client.target_control("target.step", {}, authorize("target.step", {}))
            assert stepped["pc_before"] == stepped["pc_after"]
            bp_args = {"address": 0x08000100, "kind": "temporary", "size": 2}
            bp = await client.target_control("target.breakpoint.set", bp_args, authorize("target.breakpoint.set", bp_args))
            clear_args = {"breakpoint_id": bp["breakpoint_id"]}
            assert (await client.target_control("target.breakpoint.clear", clear_args, authorize("target.breakpoint.clear", clear_args)))["cleared"] is True
            assert (await client.target_control("target.resume", {}, authorize("target.resume", {}))) == {"state": "running"}
            assert (await client.target_registers(("wide",)))[0]["width_bits"] == 64
            mailbox_config = {"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096}}
            opened = await client.target_transport_open("mailbox", mailbox_config, 100)
            raw, eof = await client.target_transport_read(opened["transport_id"], 16, 100)
            assert (raw, eof) == (b"xyz", False)
            await client.target_transport_close(opened["transport_id"])
            assert (await client.target_fault(0))["stack_artifact"] is None
            stack = (await client.target_fault(4))["stack_artifact"]
            assert stack == {
                "sha256": "88d4266fd4e6338d13b845fcf289579d209c897823b9217da3e161936f031589",
                "size_bytes": 4,
                "relative_path": f"objects/sha256/88/{'88d4266fd4e6338d13b845fcf289579d209c897823b9217da3e161936f031589'}",
                "kind": "fault-stack",
                "media_type": "application/octet-stream",
            }
            logs = await client.target_logs("rtt", 16, 100)
            assert logs["bytes"] == logs["artifact"]["size_bytes"] == 3
            assert set(logs["artifact"]) == {
                "sha256", "size_bytes", "relative_path", "kind", "media_type"
            }
            with pytest.raises(Exception) as oversized_logs:
                await client.target_logs("rtt", 1, 100)
            assert oversized_logs.value.code == "PROBE_BACKEND_ERROR"
            with pytest.raises(Exception) as reused:
                await client.target_control("target.halt", {}, halt)
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
            opened = await client.target_transport_open("mailbox", mailbox_config, 100)
            with pytest.raises(Exception) as bad_transport:
                await client.target_transport_read(opened["transport_id"], 16, 100)
            assert bad_transport.value.code == "PROBE_BACKEND_ERROR"
            backend.bad_transport = False
            for malformed, action in (
                ("halt", lambda: client.target_control("target.halt", {}, authorize("target.halt", {}))),
                ("resume", lambda: client.target_control("target.resume", {}, authorize("target.resume", {}))),
                ("step-register", lambda: client.target_control("target.step", {}, authorize("target.step", {}))),
                ("register", lambda: client.target_registers(("r0",))),
                ("breakpoint", lambda: client.target_control("target.breakpoint.set", bp_args, authorize("target.breakpoint.set", bp_args))),
                ("clear", lambda: client.target_control("target.breakpoint.clear", clear_args, authorize("target.breakpoint.clear", clear_args))),
                ("fault-shape", lambda: client.target_fault(0)),
                ("logs-truncated", lambda: client.target_logs("rtt", 16, 100)),
                ("transport-open", lambda: client.target_transport_open("mailbox", mailbox_config, 100)),
            ):
                backend.malformed = malformed
                with pytest.raises(Exception) as invalid_result:
                    await action()
                assert invalid_result.value.code == "PROBE_BACKEND_ERROR"
                backend.malformed = ""
            backend.transport = b"x"
            opened = await client.target_transport_open("mailbox", mailbox_config, 100)
            backend.malformed = "transport-read"
            with pytest.raises(Exception) as invalid_read:
                await client.target_transport_read(opened["transport_id"], 16, 100)
            assert invalid_read.value.code == "PROBE_BACKEND_ERROR"
            backend.malformed = ""
            backend.transport = b"xyz"
            opened = await client.target_transport_open("mailbox", mailbox_config, 100)
            with pytest.raises(Exception) as oversized_transport:
                await client.target_transport_read(opened["transport_id"], 1, 100)
            assert oversized_transport.value.code == "PROBE_BACKEND_ERROR"
            for malformed in ("logs-extra", "transport-extra"):
                backend.malformed = malformed
                backend.transport = b"x"
                with pytest.raises(Exception) as extra_output:
                    if malformed == "logs-extra":
                        await client.target_logs("rtt", 16, 100)
                    else:
                        opened = await client.target_transport_open("mailbox", mailbox_config, 100)
                        await client.target_transport_read(opened["transport_id"], 16, 100)
                assert extra_output.value.code == "PROBE_BACKEND_ERROR"
            backend.malformed = "transport-close"
            with pytest.raises(Exception) as invalid_close:
                await client.target_transport_close(opened["transport_id"])
            assert invalid_close.value.code == "PROBE_BACKEND_ERROR"
            backend.malformed = ""
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

    class Target(FakePyOCDTarget):
        def set_breakpoint(self, address): self.calls.append(("set_breakpoint", address)); return True
        def remove_breakpoint(self, address): self.calls.append(("remove_breakpoint", address))

    class Channel:
        def __init__(self): self.values = [b"rtt", b""]
        def read(self): return self.values.pop(0)

    class Block:
        def __init__(self):
            self.up_channels = [Channel()]
            self.control_block_address = 0x20000000
        def start(self): pass

    def transport_factory(kind, attached_target, profile):
        from stm32_toolkit.testing.transports.rtt import PyOcdRttAdapter, RttTransport
        assert kind == "rtt" and attached_target is target
        return RttTransport(
            PyOcdRttAdapter(attached_target, control_block_factory=lambda *args, **kwargs: Block()),
            profile,
        )

    registers = {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}
    registers.update({"sp": 0x20000000, "pc": 0x08000100})
    target = Target(memory={0x20000000: b"abcd"}, registers=registers)
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile={
            "board_id": "board-a", "mcu": "stm32f407vg", "target_id": "target-a",
            "ram": [{"start": 0x20000000, "size": 0x10000}],
            "registers": list(registers),
            "rtt": {"channel": 0, "control_block_address": 0x20000000},
            "log_transport": {"kind": "rtt", "options": {"channel": 0, "controlBlockAddress": 0x20000000}},
        },
        target_transport_factory=transport_factory,
    )
    backend.open_attach("probe-a", "stm32f407vg")
    assert backend.target_identity()["target_id"] == "target-a"
    assert backend.target_state() == {"state": "halted", "reason": "requested"}
    breakpoint = backend.set_temporary_breakpoint(0x08000100, 2)
    assert backend.clear_temporary_breakpoint(breakpoint["breakpoint_id"])["cleared"] is True
    assert backend.capture_fault(4)["stack"] == b"abcd"
    assert backend.capture_logs("rtt", 4, 100)["data"] == b"rtt"
    opened = backend.open_target_transport(
        "rtt", {
            "channel": 0, "control_block_address": 0x20000000,
            "ram": [{"start": 0x20000000, "size": 0x10000}],
            "target_id": "target-a", "probe_id": sha256(b"probe-a").hexdigest(),
        }, 100
    )
    assert backend.read_target_transport(opened["transport_id"], 4, 1)["data"] == b"rtt"
    assert backend.close_target_transport(opened["transport_id"])["closed"] is True
    backend.close()


@pytest.mark.parametrize("channel,options", [("swo", {"baud": 2_000_000}), ("probe", {})])
def test_pyocd_swo_and_probe_logs_use_the_admitted_closed_provider_port(channel, options):
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    calls = []
    class Port:
        def open(self, config, deadline): calls.append(("open", dict(config))); self.opened = True
        def read(self, maximum, deadline):
            calls.append(("read", maximum)); return b"native" if len(calls) == 2 else b""
        def identity(self): return {"provider": channel}
        def close(self): calls.append(("close",))

    profile = {
        "board_id": "b", "mcu": "stm32f407vg", "target_id": "t",
        channel: options, "log_transport": {"kind": channel, "options": options},
    }
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=FakePyOCDTarget()),
        target_profile=profile,
        target_transport_factory=lambda kind, target, declared: Port(),
    )
    backend.preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    backend.open_attach("probe-a", "stm32f407vg")
    assert backend.capture_logs(channel, 16, 100) == {"data": b"native", "truncated": False}
    assert calls[0][0] == "open"
    assert calls[0][1]["target_id"] == "t"
    assert calls[-1] == ("close",)
    backend.close()


@pytest.mark.parametrize(
    "transport,config",
    [
        ("mailbox", {"address": 0x20000000, "size": 64, "ram": [{"start": 0x20000000, "size": 0x1000}]}),
        ("rtt", {"channel": 0, "control_block_address": None, "ram": [{"start": 0x20000000, "size": 0x1000}]}),
        ("uart", {"port": "COM3", "baud": 115200, "data_bits": 8, "parity": "N", "stop_bits": 1}),
        ("semihosting", {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64, "host_files": False}),
    ],
)
def test_pyocd_transport_contract_compares_the_hash_of_the_attached_raw_serial(
    transport, config,
):
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    raw_serial = "066EFF515056805087013719"
    serial_hash = sha256(raw_serial.encode("utf-8")).hexdigest()
    opened = []

    class Port:
        def open(self, value, deadline): opened.append(dict(value))
        def read(self, maximum, deadline): return b""
        def identity(self): return {"provider": transport}
        def close(self): pass

    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe(raw_serial),), target=FakePyOCDTarget()),
        target_profile={"target_id": "target-a"},
        target_transport_factory=lambda *args: Port(),
    )
    backend.open_attach(raw_serial, "stm32f407vg")
    effective = {**config, "target_id": "target-a", "probe_id": serial_hash}
    result = backend.open_target_transport(transport, effective, 100)
    assert opened == [effective]
    assert result["identity"]["probe_serial_hash"] == serial_hash
    assert raw_serial not in result["identity"].values()
    backend.close_target_transport(result["transport_id"])
    backend.close()


@pytest.mark.parametrize("channel", ["swo", "probe"])
def test_admitted_swo_and_probe_adapters_use_only_bounded_frozen_pyocd_apis(channel):
    from stm32_toolkit.probe.pyocd_backend import admitted_target_transport_factory
    from stm32_toolkit.probe.worker import ProbeBackendWorker, ProbeWorkerConfig

    calls = []

    class Probe:
        def swo_start(self, baud): calls.append(("probe.start", baud))
        def swo_read(self): calls.append(("probe.read",)); return bytearray(b"native")
        def swo_stop(self): calls.append(("probe.stop",))

    class Session:
        probe = Probe()

    class Target:
        session = Session()
        def trace_start(self): calls.append(("target.start",))
        def trace_stop(self): calls.append(("target.stop",))

    options = {"baud": 2_000_000} if channel == "swo" else {}
    profile = {channel: options}
    adapter = admitted_target_transport_factory(channel, Target(), profile)
    config = {**options, "target_id": "target-a", "probe_id": "a" * 64}
    adapter.open(config, float("inf"))
    assert adapter.read(16, float("inf")) == b"native"
    adapter.close()
    assert ("probe.read",) in calls
    assert calls[-1] == ("probe.stop",)
    if channel == "swo":
        assert calls[0] == ("probe.start", 2_000_000)
        assert ("target.stop",) in calls
    else:
        assert not any(call[0].startswith("target.") for call in calls)

    # Exercise the production construction branch too: the serializable worker
    # configuration must retain the same fixed provider instead of advertising a
    # channel that only the in-process factory can construct.
    worker_profile = {
        "backend": "pyocd", "board_id": "board-a", "mcu": "stm32f407vg",
        "target_id": "target-a", channel: options,
        "log_transport": {"kind": channel, "options": options},
    }
    worker = ProbeBackendWorker(config=ProbeWorkerConfig(target_profile=worker_profile))
    try:
        worker.preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    finally:
        worker.close()


def test_fixed_pyocd_trace_adapters_reject_invalid_deadlines_output_and_partial_start(
    monkeypatch: pytest.MonkeyPatch,
):
    from stm32_toolkit.probe import pyocd_backend as module

    calls = []

    class Probe:
        output: object = bytearray(b"ok")
        start_error: Exception | None = None
        stop_error: Exception | None = None
        def swo_start(self, baud):
            calls.append(("probe.start", baud))
            if self.start_error: raise self.start_error
        def swo_read(self): calls.append(("probe.read",)); return self.output
        def swo_stop(self):
            calls.append(("probe.stop",))
            if self.stop_error: raise self.stop_error

    probe = Probe()

    class Session:
        pass

    session = Session()
    session.probe = probe

    class Target:
        trace_error: Exception | None = None
        stop_error: Exception | None = None
        def __init__(self): self.session = session
        def trace_start(self):
            calls.append(("target.start",))
            if self.trace_error: raise self.trace_error
        def trace_stop(self):
            calls.append(("target.stop",))
            if self.stop_error: raise self.stop_error

    target = Target()
    monkeypatch.setattr(module.time, "monotonic", lambda: 10.0)
    for config in (
        {"baud": True, "target_id": "t", "probe_id": "a" * 64},
        {"baud": 2_000_000, "target_id": "t", "probe_id": "a" * 64, "extra": True},
    ):
        with pytest.raises(RuntimeError):
            module._PyOCDProbeTracePort(target, configure_target=True).open(config, 11.0)
    with pytest.raises(RuntimeError):
        module._PyOCDProbeTracePort(target, configure_target=True).open(
            {"baud": 2_000_000, "target_id": "t", "probe_id": "a" * 64}, 10.0
        )

    target.trace_error = RuntimeError("private path")
    port = module._PyOCDProbeTracePort(target, configure_target=True)
    with pytest.raises(RuntimeError):
        port.open({"baud": 2_000_000, "target_id": "t", "probe_id": "a" * 64}, 11.0)
    assert calls[-2:] == [("target.stop",), ("probe.stop",)]
    target.trace_error = None

    port = module._PyOCDProbeTracePort(target, configure_target=False)
    port.open({"target_id": "t", "probe_id": "a" * 64}, 11.0)
    for output in ("not-bytes", bytearray(b"oversize")):
        probe.output = output
        with pytest.raises(RuntimeError): port.read(2, 11.0)
    with pytest.raises(RuntimeError): port.read(True, 11.0)
    with pytest.raises(RuntimeError): port.read(1, 10.0)
    probe.output = bytearray(b"ok")
    assert port.identity() == {"provider": "pyocd-probe"}
    port.close()
    with pytest.raises(RuntimeError): port.identity()

    port = module._PyOCDProbeTracePort(target, configure_target=True)
    port.open({"baud": 2_000_000, "target_id": "t", "probe_id": "a" * 64}, 11.0)
    target.stop_error = RuntimeError("private target")
    probe.stop_error = RuntimeError("private probe")
    with pytest.raises(RuntimeError): port.close()
    assert calls[-2:] == [("target.stop",), ("probe.stop",)]
    port.close()


def test_pyocd_log_capture_maps_fixed_trace_cleanup_failure_to_closed_backend_error():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.backend import ProbeBackendError
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend, admitted_target_transport_factory

    class Probe:
        def swo_start(self, baud): pass
        def swo_read(self): return bytearray(b"ok")
        def swo_stop(self): raise RuntimeError("C:\\private\\credential")

    class Session:
        probe = Probe()

    class Target(FakePyOCDTarget):
        session = Session()

    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("raw-serial"),), target=Target()),
        target_profile={
            "board_id": "b", "mcu": "stm32f407vg", "target_id": "t",
            "probe": {}, "log_transport": {"kind": "probe", "options": {}},
        },
        target_transport_factory=admitted_target_transport_factory,
    )
    backend.open_attach("raw-serial", "stm32f407vg")
    with pytest.raises(ProbeBackendError) as caught:
        backend.capture_logs("probe", 16, 100)
    assert caught.value.code == "PROBE_BACKEND_ERROR"
    assert "private" not in str(caught.value).lower()
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
        for operation, arguments, value in (
            ("target.halt", {}, {"state": "running", "reason": "requested"}),
            ("target.resume", {}, {"state": "halted"}),
            ("target.step", {}, {"state": "halted", "reason": "requested", "pc_before": True, "pc_after": 2}),
            ("target.breakpoint.set", {"address": 1, "kind": "temporary", "size": 2},
             {"breakpoint_id": "bp-1", "address": True, "kind": "temporary", "size": 2}),
            ("target.breakpoint.clear", {"breakpoint_id": "bp-1"},
             {"breakpoint_id": "bp-1", "cleared": 1}),
        ):
            await returns(value)
            with pytest.raises(ProbeClientError):
                await client.target_control(operation, arguments, "a" * 64)
        await returns({"address": 1, "length": 1, "data_base64": "***", "sha256": "0" * 64})
        with pytest.raises(ProbeClientError): await client.target_memory(1, 1)
        await returns({"address": 1, "length": 1, "data_base64": "AB==", "sha256": "0" * 64})
        with pytest.raises(ProbeClientError): await client.target_memory(1, 1)
        await returns({"address": True, "length": True, "data_base64": base64.b64encode(b"x").decode(), "sha256": __import__("hashlib").sha256(b"x").hexdigest()})
        with pytest.raises(ProbeClientError): await client.target_memory(1, 1)
        await returns({"registers": [{"name": "pc", "value": 1, "width_bits": 32}]})
        with pytest.raises(ProbeClientError): await client.target_registers(("r0",))
        await returns({"transport_id": 1, "identity": {}})
        with pytest.raises(ProbeClientError): await client.target_transport_open("mailbox", {}, 1)
        await returns({"transport_id": "transport-a", "identity": {"board_id": 1, "mcu": "m", "target_id": "t", "probe_serial_hash": "a" * 64}})
        with pytest.raises(ProbeClientError): await client.target_transport_open("mailbox", {}, 1)
        await returns({"data_base64": base64.b64encode(b"too long").decode(), "eof": False})
        with pytest.raises(ProbeClientError): await client.target_transport_read("transport-a", 1, 1)
        await returns({"transport_id": "other", "closed": True})
        with pytest.raises(ProbeClientError): await client.target_transport_close("transport-a")
        await returns({"fault_registers": {}, "stack_artifact": None, "stack_bytes": 0, "truncated": False})
        with pytest.raises(ProbeClientError): await client.target_fault(0)
        registers = {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}
        await returns({"fault_registers": registers, "stack_artifact": {"unexpected": True}, "stack_bytes": 0, "truncated": False})
        with pytest.raises(ProbeClientError): await client.target_fault(0)
        await returns({"channel": "rtt", "artifact": {}, "bytes": True, "duration_ms": 1, "truncated": False})
        with pytest.raises(ProbeClientError): await client.target_logs("rtt", 1, 1)

    asyncio.run(scenario())


def test_public_client_rejects_non_allowlisted_target_failure_code():
    from stm32_toolkit.probe.client import ProbeClientError, _decode_response
    from stm32_toolkit.probe.protocol import PROBE_PROTOCOL_VERSION
    from stm32_toolkit import __version__

    raw = canonical_json_bytes({
        "protocol": PROBE_PROTOCOL_VERSION, "toolkitVersion": __version__,
        "requestId": "request-a", "ok": False, "operation": "target.memory.read",
        "code": "PRIVATE_FAILURE", "message": "private path", "data": None, "details": {},
    })
    with pytest.raises(ProbeClientError):
        _decode_response(
            raw, expected_request_id="request-a", expected_operation="target.memory.read",
        )


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
        def __init__(self): self.value: object = b"x"; self.fail = False; self.open_fail = False
        def open(self, config, deadline):
            if self.open_fail: raise RuntimeError("secret C:/private")
        def read(self, maximum, deadline):
            if self.fail: raise RuntimeError("secret C:/private")
            return self.value
        def identity(self): return {"target_id": "t", "probe_id": "probe-a", "transport": "rtt"}
        def close(self):
            if self.fail: raise RuntimeError("secret")

    class Target(FakePyOCDTarget):
        def __init__(self):
            regs = {name: 0 for name in ("cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr")}
            regs["sp"] = 0x20000000
            super().__init__(memory={0x20000000: b"abcd"}, registers=regs)
            self.break_result: object = True
            self.remove_error = False
            self.handle = Handle()
        def set_breakpoint(self, address):
            if isinstance(self.break_result, Exception): raise self.break_result
            return self.break_result
        def remove_breakpoint(self, address):
            if self.remove_error: raise RuntimeError("secret")

    target = Target()
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile={
            "board_id": "b", "mcu": "stm32f407vg", "target_id": "t",
            "ram": [{"start": 0x20000000, "size": 0x10000}],
            "registers": [
                "cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar",
                "shcsr", "icsr", "sp", "pc",
            ],
            "rtt": {"channel": 0},
            "log_transport": {"kind": "rtt", "options": {"channel": 0}},
        },
        target_transport_factory=lambda kind, attached, profile: target.handle,
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
    target.handle.value = "bad"
    with pytest.raises(ProbeBackendError): backend.capture_logs("rtt", 1, 1)
    target.handle.fail = True
    with pytest.raises(ProbeBackendError): backend.capture_logs("rtt", 1, 1)
    target.handle.fail = False
    target.handle.value = b"xx"
    with pytest.raises(ProbeBackendError) as pressure: backend.capture_logs("rtt", 1, 1)
    assert pressure.value.code == "PROBE_BACKPRESSURE"
    with pytest.raises(ProbeBackendError): backend.open_target_transport("bad", {}, 1)
    config = {
        "channel": 0, "control_block_address": None,
        "ram": [{"start": 0x20000000, "size": 0x10000}],
        "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest(),
    }
    target.handle.open_fail = True
    with pytest.raises(ProbeBackendError): backend.open_target_transport("rtt", config, 1)
    target.handle.open_fail = False
    target.handle.value = b"x"
    opened = backend.open_target_transport("rtt", config, 1)
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


def test_pyocd_target_preflight_and_transport_config_are_closed_before_attach():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.backend import ProbeBackendError
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    def rejected(profile, *, factory=lambda *args: object(), probe_id="probe-a", level=OperationLevel.OBSERVE):
        backend = PyOCDBackend(FakePyOCDDriver(()), target_profile=profile, target_transport_factory=factory)
        with pytest.raises(ProbeBackendError):
            backend.preflight_target_capabilities(probe_id, level)

    with pytest.raises(ValueError):
        PyOCDBackend(target_transport_factory=object())
    rejected({}, probe_id="bad value")
    PyOCDBackend(target_profile={}).preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    base = {"board_id": "b", "mcu": "stm32f407vg", "target_id": "t"}
    rejected({**base, "extra": True})
    rejected({**base, "backend": "other"})
    rejected({**base, "board_id": ""})
    rejected({**base, "rtt": {}, "log_transport": {"kind": "rtt", "options": {}}}, factory=None)
    rejected({**base, "rtt": {}, "log_transport": []})
    rejected({**base, "rtt": {}, "log_transport": {"kind": "uart", "options": {}}})
    rejected({**base, "rtt": {}, "log_transport": {"kind": "rtt", "options": []}})
    rejected({**base, "ram": [{"start": 0x20000000, "size": 0x100}, {"start": 0x20000080, "size": 0x100}]})
    rejected({**base, "ram": []})
    rejected({**base, "ram": [{"start": True, "size": 0x100}]})
    rejected({**base, "ram": [{"start": 0x20000000, "size": 0x100}], "mailbox": {"address": 0x20001000, "size": 64}})
    rejected({**base, "uart": {"port": "COM1", "baud": True}})
    rejected({**base, "semihosting": {"declared": False}})
    rejected({**base, "semihosting": {"declared": True}})
    rejected({**base, "semihosting": {"declared": True}, "semihosting_runtime": {"elf_path": "../secret.elf", "elf_sha256": "e" * 64}})
    rejected({**base, "swo": {"baud": True}})
    rejected({**base, "probe": {"unexpected": True}})
    rejected({**base, "rtt": {"channel": 0}, "log_transport": {"kind": "rtt", "options": {"channel": 1}}})
    rejected({
        **base, "ram": [{"start": 0x20000000, "size": 0x1000}],
        "rtt": {"channel": 0}, "log_transport": {"kind": "rtt", "options": {"channel": 0}},
    }, factory=None)
    PyOCDBackend(
        target_profile={**base, "ram": [{"start": 0x20000000, "size": 0x1000}], "rtt": {"channel": 0}, "log_transport": {"kind": "rtt", "options": {"channel": 0}}},
        target_transport_factory=lambda *args: object(),
    ).preflight_target_capabilities("probe-a", OperationLevel.CONTROL)
    for kind, options in (("swo", {"baud": 2_000_000}), ("probe", {})):
        PyOCDBackend(
            target_profile={**base, kind: options, "log_transport": {"kind": kind, "options": options}},
            target_transport_factory=lambda *args: object(),
        ).preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    for kind, options, extra in (
        ("uart", {"port": "COM1", "baud": 115200}, {}),
        ("semihosting", {}, {"semihosting": {"declared": True}, "semihosting_runtime": {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64}}),
    ):
        declared = {kind: options} if kind != "semihosting" else extra
        PyOCDBackend(
            target_profile={**base, **declared, "log_transport": {"kind": kind, "options": options}},
            target_transport_factory=lambda *args: object(),
        ).preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)

    class Port:
        def open(self, config, deadline): self.config = config
        def read(self, maximum, deadline): return b""
        def close(self): pass
        def identity(self): return {}

    target = FakePyOCDTarget()
    profile = {
        **base, "ram": [{"start": 0x20000000, "size": 0x1000}],
        "semihosting": {"declared": True},
        "semihosting_runtime": {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64},
    }
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile=profile, target_transport_factory=lambda *args: Port(),
    )
    detached = PyOCDBackend(target_profile=profile, target_transport_factory=lambda *args: Port())
    with pytest.raises(ProbeBackendError):
        detached._runtime_transport_config("rtt", {
            "channel": 0, "control_block_address": None, "ram": profile["ram"],
            "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest(),
        })
    backend.open_attach("probe-a", "stm32f407vg")
    saved_target = backend._target_profile.pop("target_id")
    with pytest.raises(ProbeBackendError):
        backend._runtime_transport_config("rtt", {
            "channel": 0, "control_block_address": None, "ram": profile["ram"],
            "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest(),
        })
    backend._target_profile["target_id"] = saved_target
    saved_semihost = backend._target_profile.pop("semihosting_runtime")
    with pytest.raises(ProbeBackendError):
        backend._profile_transport_config("semihosting")
    backend._target_profile["semihosting_runtime"] = saved_semihost
    configs = [
        ("mailbox", {"address": 0x20000000, "size": 64, "ram": profile["ram"], "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest()}),
        ("rtt", {"channel": 0, "control_block_address": None, "ram": profile["ram"], "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest()}),
        ("uart", {"port": "COM1", "baud": 115200, "data_bits": 8, "parity": "N", "stop_bits": 1, "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest()}),
        ("semihosting", {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64, "host_files": False, "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest()}),
    ]
    for kind, config in configs:
        transport = backend._new_transport(kind, config, 1)
        assert transport.config["target_id"] == "t"
    for config in ({}, {"kind": "rtt", "options": []}, {"kind": "uart", "options": {}}):
        with pytest.raises(ProbeBackendError):
            backend._runtime_transport_config("rtt", config)
    for deadline in (True, 0, 300_001):
        with pytest.raises(ProbeBackendError):
            backend._new_transport("rtt", configs[1][1], deadline)
    backend._target_transport_factory = None
    with pytest.raises(ProbeBackendError):
        backend._new_transport("rtt", configs[1][1], 1)
    backend._target_transport_factory = lambda *args: object()
    with pytest.raises(ProbeBackendError):
        backend._new_transport("rtt", configs[1][1], 1)
    backend._target_transport_factory = lambda *args: (_ for _ in ()).throw(RuntimeError("private"))
    with pytest.raises(ProbeBackendError):
        backend._new_transport("rtt", configs[1][1], 1)
    backend.close()


def test_pyocd_public_target_transport_accepts_only_task8_effective_config():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.backend import ProbeBackendError
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    class Port:
        def open(self, config, deadline): self.config = dict(config)
        def read(self, maximum, deadline): return b""
        def close(self): pass
        def identity(self): return {}

    profile = {
        "board_id": "b", "mcu": "stm32f407vg", "target_id": "t",
        "ram": [{"start": 0x20000000, "size": 0x1000}],
        "mailbox": {"address": 0x20000000, "size": 64},
    }
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=FakePyOCDTarget()),
        target_profile=profile, target_transport_factory=lambda *args: Port(),
    )
    backend.open_attach("probe-a", "stm32f407vg")
    effective = {
        "address": 0x20000000, "size": 64, "ram": profile["ram"],
        "target_id": "t", "probe_id": sha256(b"probe-a").hexdigest(),
    }
    opened = backend.open_target_transport("mailbox", effective, 1)
    assert backend._transports[opened["transport_id"]].config == effective
    with pytest.raises(ProbeBackendError):
        backend.open_target_transport(
            "mailbox",
            {"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 64}},
            1,
        )
    backend.close()


def test_target_observations_reject_outside_profile_before_backend_read(tmp_path: Path):
    """A syntactically valid v2 request is still bounded by the closed target profile."""
    from fakes.fake_probe import FakeProbeBackend
    from stm32_toolkit.probe.backend import ProbeDescriptor
    from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
    from stm32_toolkit.probe.authorization import ControlAuthorizationStore
    from test_probe_service import make_service

    class PolicyBackend(FakeProbeBackend):
        def __init__(self) -> None:
            super().__init__(
                probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
                memory={0x40000000: b"MMIO"},
                registers={"not_in_profile": 0x1234},
            )

        def target_observation_policy(self):
            return {
                "readable_regions": [{"start": 0x20000000, "size": 0x1000}],
                "register_allowlist": ["r0", "pc"],
            }

    async def scenario() -> None:
        backend = PolicyBackend()
        service = make_service(
            tmp_path,
            level=OperationLevel.OBSERVE,
            backend=backend,
            control_authorizations=ControlAuthorizationStore(
                (tmp_path / "control").absolute()
            ),
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "stm32f407vg")
            backend.events.clear()
            with pytest.raises(ProbeClientError):
                await client.target_memory(0x40000000, 4)
            with pytest.raises(ProbeClientError):
                await client.target_registers(("not_in_profile",))
            assert not any(
                event[0] in {"read_memory", "read_core_registers"}
                for event in backend.events
            )
        finally:
            await client.close()
            await service.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "case,policy",
    [
        ("missing", None),
        ("not-mapping", []),
        (
            "empty-regions",
            {"readable_regions": [], "register_allowlist": ["pc"]},
        ),
        (
            "invalid-region",
            {
                "readable_regions": [{"start": 0x20000000, "size": 0}],
                "register_allowlist": ["pc"],
            },
        ),
        (
            "overlapping-regions",
            {
                "readable_regions": [
                    {"start": 0x20000000, "size": 16},
                    {"start": 0x20000008, "size": 16},
                ],
                "register_allowlist": ["pc"],
            },
        ),
        (
            "invalid-register",
            {
                "readable_regions": [{"start": 0x20000000, "size": 16}],
                "register_allowlist": ["PC"],
            },
        ),
    ],
)
def test_probe_service_rejects_malformed_observation_policy_before_target_io(
    tmp_path: Path, case: str, policy: object,
) -> None:
    """The backend cannot widen OBSERVE by returning an open or malformed policy."""
    from fakes.fake_probe import FakeProbeBackend
    from stm32_toolkit.probe.backend import ProbeBackendError, ProbeDescriptor
    from test_probe_service import make_service

    backend = FakeProbeBackend(
        probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
        memory={0x20000000: b"abcd"},
        registers={"pc": 0x08000100},
    )
    if case == "missing":
        backend.target_observation_policy = None  # type: ignore[attr-defined]
    else:
        backend.target_observation_policy = lambda: policy  # type: ignore[attr-defined]
    service = make_service(tmp_path / case, backend=backend)

    with pytest.raises(ProbeBackendError) as caught:
        service._target_observation_policy()

    assert caught.value.code in {"PROBE_OPERATION_UNAVAILABLE", "PROBE_BACKEND_ERROR"}
    assert backend.events == []


def test_pyocd_isolates_legacy_reads_from_closed_target_observation_policy():
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe.backend import ProbeBackendError
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    target = FakePyOCDTarget(
        memory={0x40000000: b"MMIO"},
        registers={"not_in_profile": 0x1234},
    )
    backend = PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target),
        target_profile={
            "backend": "pyocd",
            "board_id": "board-a",
            "mcu": "stm32f407vg",
            "target_id": "target-a",
            "ram": [{"start": 0x20000000, "size": 0x1000}],
            "registers": ["r0", "pc"],
        },
    )
    backend.preflight_target_capabilities("probe-a", OperationLevel.OBSERVE)
    backend.open_attach("probe-a", "stm32f407vg")
    target.calls.clear()

    assert backend.read_memory(0x40000000, 4) == b"MMIO"
    assert backend.read_core_registers(("not_in_profile",)) == {
        "not_in_profile": 0x1234
    }
    assert target.calls == [
        ("read_memory_block8", 0x40000000, 4),
        ("get_state",),
        ("read_core_registers_raw", ("not_in_profile",)),
    ]
    target.calls.clear()

    with pytest.raises(ProbeBackendError):
        backend.target_read_memory(0x40000000, 4)
    with pytest.raises(ProbeBackendError):
        backend.target_read_core_registers(("not_in_profile",))
    assert target.calls == []
    backend.close()


def test_fixed_pyocd_task8_ports_enforce_deadline_output_and_closed_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
    from stm32_toolkit.probe import pyocd_backend as module
    from stm32_toolkit.probe.backend import ProbeBackendError

    class Target:
        result: object = [1, 2]
        def read_memory_block8(self, address, size): return self.result
        def get_target_context(self): return object()

    target = Target()
    reader = module._AttachedTargetMemoryReader(target)
    deadline = module.time.monotonic() + 10.0
    assert reader.read_memory(0, 2, deadline) == b"\x01\x02"
    for value in ([1], [True, 2], "12"):
        target.result = value
        with pytest.raises(RuntimeError): reader.read_memory(0, 2, deadline)
    monkeypatch.setattr(module.time, "monotonic", lambda: 2.0)
    with pytest.raises(RuntimeError): reader.read_memory(0, 2, 2.0)
    reader.close()
    with pytest.raises(RuntimeError): reader.read_memory(0, 2, 3.0)

    class Agent:
        instances = []
        def __init__(self, context, io_handler, console):
            self.polls = 0; self.cleanups = 0; Agent.instances.append(self)
        def check_and_handle_semihost_request(self): self.polls += 1
        def cleanup(self): self.cleanups += 1

    import pyocd.debug.semihost as semihost
    monkeypatch.setattr(semihost, "SemihostAgent", Agent)
    monkeypatch.setattr(module.time, "monotonic", lambda: 1.0)
    session = module._AttachedTargetSemihostSession(target)
    session.open(elf_path="C:\\fixture\\app.elf", host_io=object(), console=object(), deadline=2.0)
    with pytest.raises(RuntimeError):
        session.open(elf_path="C:\\fixture\\app.elf", host_io=object(), console=object(), deadline=2.0)
    for agent, deadline in ((object(), 2.0), (None, 1.0)):
        with pytest.raises(RuntimeError): session.poll(agent=agent, deadline=deadline)
    session.poll(agent=None, deadline=2.0)
    assert Agent.instances[0].polls == 1
    session.close(); session.close()
    assert Agent.instances[0].cleanups == 1

    with pytest.raises(ProbeBackendError):
        module.admitted_target_transport_factory("dynamic", target, {})

    profile = {
        "board_id": "b", "mcu": "stm32f407vg", "target_id": "t",
        "ram": [{"start": 0x20000000, "size": 0x1000}],
        "rtt": {"channel": 0}, "uart": {"port": "COM3", "baud": 115200},
        "semihosting": {"declared": True},
        "semihosting_runtime": {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64},
    }
    backend = module.PyOCDBackend(
        FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=FakePyOCDTarget()),
        target_profile=profile, target_transport_factory=lambda *args: object(),
    )
    with pytest.raises(ProbeBackendError): backend._profile_transport_config("rtt")
    backend.open_attach("probe-a", "stm32f407vg")
    assert backend._profile_transport_config("rtt")["channel"] == 0
    assert backend._profile_transport_config("uart")["data_bits"] == 8
    assert backend._profile_transport_config("semihosting")["host_files"] is False
    backend._target_profile["swo"] = {"baud": 2_000_000}
    backend._target_profile["probe"] = {}
    assert backend._profile_transport_config("swo")["baud"] == 2_000_000
    assert backend._profile_transport_config("probe")["probe_id"] == sha256(b"probe-a").hexdigest()
    with pytest.raises(ProbeBackendError): backend._profile_transport_config("mailbox")
    with pytest.raises(ProbeBackendError): backend._runtime_transport_config("dynamic", {})
    backend.close()
