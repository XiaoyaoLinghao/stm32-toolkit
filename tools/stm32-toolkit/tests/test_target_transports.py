from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import struct
import time

import pytest

from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.service import ProbeEndpoint
from stm32_toolkit.testing import target as target_module

from stm32_toolkit.testing.model import TestProtocolError as ProtocolError
from stm32_toolkit.testing.transports import (
    MailboxTransport,
    PyOcdRttAdapter,
    PyOcdSemihostingAdapter,
    RttTransport,
    SemihostingTransport,
    UartTransport,
)
from stm32_toolkit.testing.transports.base import (
    MAX_TRANSPORT_READ_BYTES,
    TransportBase,
    check_deadline,
    closed_config,
    default_clock,
    identity_from,
    ram_regions,
    range_in_ram,
)
from stm32_toolkit.testing.transports.uart import pyserial_factory


ADMISSION = Path(__file__).parent / "fixtures" / "component-admission" / "target-transports"
ATTRIBUTES = Path(__file__).parents[3] / ".gitattributes"
RAM = ({"start": 0x20000000, "size": 0x8000},)
PROFILE = {
    "ram": list(RAM),
    "mailbox": {"address": 0x20000000, "size": 4096},
    "rtt": {"channel": 0},
    "uart": {"port": "COM7", "baud": 115200},
    "semihosting": {"declared": True},
}
BASE_ID = {"target_id": "stm32:fixture", "probe_id": "probe:fixture"}


def test_mailbox_production_reader_uses_only_public_probe_v2(monkeypatch, tmp_path: Path):
    calls = []
    identity = {"board_id": "board-a", "mcu": "stm32f407vg", "target_id": "target-a", "probe_serial_hash": "a" * 64}

    class PublicClient:
        def __init__(self, endpoint): calls.append(("client", endpoint.protocol))
        async def target_identity(self): calls.append(("identity",)); return dict(identity)
        async def target_memory(self, address, size, *, timeout_ms): calls.append(("memory", address, size, timeout_ms)); return b"ABCD"
        async def close(self): calls.append(("close",))

    monkeypatch.setattr(target_module, "ProbeClient", PublicClient)
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2", toolkit_version="0.5.0", host="127.0.0.1", port=1,
        token="0" * 64, workspace_id="workspace-a", session_id="session-a", lease_id="lease-a",
        probe_id="probe-a", operation_level=OperationLevel.OBSERVE, record_path=tmp_path / "endpoint.json",
    )
    reader_type = getattr(target_module, "ProbeV2MemoryReader")
    reader = reader_type(endpoint, identity)
    assert reader.read_memory(0x20000000, 4, time.monotonic() + 1) == b"ABCD"
    assert calls[0:3] == [("client", "stm32-toolkit-probe/2"), ("identity",), ("memory", 0x20000000, 4, calls[2][3])]
    assert 1 <= calls[2][3] <= 1000
    assert calls[-1] == ("close",)
    with pytest.raises(TypeError):
        reader_type(object(), identity)
    reader.close()
    with pytest.raises(RuntimeError):
        reader.read_memory(0x20000000, 4, time.monotonic() + 1)

    fresh = reader_type(endpoint, identity)
    with pytest.raises(TimeoutError):
        fresh.read_memory(0x20000000, 4, time.monotonic() - 1)

    class ChangedClient(PublicClient):
        async def target_identity(self): return {**identity, "target_id": "changed"}
    monkeypatch.setattr(target_module, "ProbeClient", ChangedClient)
    changed = reader_type(endpoint, identity)
    with pytest.raises(RuntimeError):
        changed.read_memory(0x20000000, 4, time.monotonic() + 1)


def assert_code(code: str, function) -> None:
    with pytest.raises(ProtocolError) as caught:
        function()
    assert caught.value.code == code


class FakeMailboxReader:
    def __init__(self, producer: int = 4, consumer: int = 0, data: bytes = b"test") -> None:
        self.header = producer.to_bytes(8, "little") + consumer.to_bytes(8, "little")
        self.data = data
        self.calls: list[tuple[int, int, float]] = []
        self.closed = False
        self._data_cursor = 0

    def read_memory(self, address: int, size: int, deadline: float) -> bytes:
        self.calls.append((address, size, deadline))
        if address == 0x20000000:
            return self.header
        result = self.data[self._data_cursor : self._data_cursor + size]
        self._data_cursor += size
        return result

    def close(self) -> None:
        self.closed = True


class FailingReader(FakeMailboxReader):
    def read_memory(self, address: int, size: int, deadline: float) -> bytes:
        raise OSError("disconnected")


class FakeRttBackend:
    def __init__(self) -> None:
        self.opened: dict[str, object] | None = None
        self.closed = False
        self.reads: list[tuple[int, float]] = []

    def open(self, *, channel: int, control_block_address: int | None, ram_regions, deadline: float) -> None:
        self.opened = {"channel": channel, "control_block_address": control_block_address, "ram_regions": ram_regions, "deadline": deadline}

    def read(self, max_bytes: int, deadline: float) -> bytes:
        self.reads.append((max_bytes, deadline))
        return b"rtt"

    def identity(self) -> dict[str, str]:
        return {"control_block_address": "0x20000100"}

    def close(self) -> None:
        self.closed = True


class FakeSerial:
    def __init__(self, data: bytes = b"uart") -> None:
        self.data = data
        self.closed = False

    def read(self, size: int) -> bytes:
        return self.data[:size]

    def close(self) -> None:
        self.closed = True


class FakeSerialFactory:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None
        self.port = FakeSerial()

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self.port


class FakeSemihostBackend:
    def __init__(self) -> None:
        self.opened: dict[str, object] | None = None
        self.closed = False

    def open(self, *, elf_path: str, deadline: float) -> None:
        self.opened = {"elf_path": elf_path, "deadline": deadline}

    def read(self, max_bytes: int, deadline: float) -> bytes:
        return b"semi"

    def close(self) -> None:
        self.closed = True


def mailbox_config(**changes) -> dict[str, object]:
    result: dict[str, object] = {"address": 0x20000000, "size": 4096, "ram": list(RAM), **BASE_ID}
    result.update(changes)
    return result


def rtt_config(**changes) -> dict[str, object]:
    result: dict[str, object] = {"channel": 0, "control_block_address": None, "ram": list(RAM), **BASE_ID}
    result.update(changes)
    return result


def uart_config(**changes) -> dict[str, object]:
    result: dict[str, object] = {"port": "COM7", "baud": 115200, "data_bits": 8, "parity": "N", "stop_bits": 1, **BASE_ID}
    result.update(changes)
    return result


def semihost_config(**changes) -> dict[str, object]:
    result: dict[str, object] = {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "a" * 64, "host_files": False, **BASE_ID}
    result.update(changes)
    return result


def test_mailbox_is_read_only_bounded_and_identity_bound() -> None:
    reader = FakeMailboxReader()
    transport = MailboxTransport(reader, PROFILE, clock=lambda: 1.0)
    transport.open(mailbox_config(), 2.0)
    assert transport.read(4, 2.0) == b"test"
    assert reader.calls == [(0x20000000, 16, 2.0), (0x20000010, 4, 2.0)]
    assert not hasattr(reader, "write_memory")
    identity = transport.identity()
    assert set(identity) == {"probe_id", "target_id", "transport", "config_digest", "address", "ring_size", "ram_bounds"}
    assert identity["address"] == "0x20000000" and identity["ring_size"] == "4096"
    transport.close()
    assert reader.closed


def test_mailbox_wrap_and_counters_are_bounded() -> None:
    reader = FakeMailboxReader(producer=4098, consumer=4094, data=b"abcd")
    transport = MailboxTransport(reader, PROFILE, clock=lambda: 1.0)
    transport.open(mailbox_config(), 2.0)
    assert transport.read(4, 2.0) == b"abcd"
    assert reader.calls[1:][0][:2] == (0x20000000 + 16 + 4094, 2)
    assert reader.calls[2][:2] == (0x20000000 + 16, 2)

    for producer, consumer in ((0, 1), (4097, 0)):
        reader = FakeMailboxReader(producer, consumer)
        bad = MailboxTransport(reader, PROFILE, clock=lambda: 1.0)
        bad.open(mailbox_config(), 2.0)
        assert_code("TEST_PROTOCOL_INVALID", lambda bad=bad: bad.read(4, 2.0))
        assert reader.closed
        assert_code("TEST_TRANSPORT_UNAVAILABLE", bad.identity)


@pytest.mark.parametrize("address,size", [(0x1FFFFFFF, 4096), (0x20000000, 32753), (0x20008000, 1), (0x20000000, 0)])
def test_mailbox_ram_and_ring_bounds(address: int, size: int) -> None:
    transport = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(mailbox_config(address=address, size=size), 2.0))


def test_rtt_uses_declared_channel_and_explicit_ram_only() -> None:
    backend = FakeRttBackend()
    transport = RttTransport(backend, PROFILE, clock=lambda: 1.0)
    transport.open(rtt_config(), 2.0)
    assert backend.opened == {"channel": 0, "control_block_address": None, "ram_regions": ((0x20000000, 0x8000),), "deadline": 2.0}
    assert transport.read(4, 2.0) == b"rtt"
    assert transport.identity()["transport"] == "rtt"
    transport.close()
    assert backend.closed


@pytest.mark.parametrize("channel", [-1, 16, 1])
def test_rtt_channel_is_closed_and_profile_declared(channel: int) -> None:
    transport = RttTransport(FakeRttBackend(), PROFILE, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(rtt_config(channel=channel), 2.0))


def test_rtt_control_block_must_be_in_ram() -> None:
    transport = RttTransport(FakeRttBackend(), {**PROFILE, "rtt": {"channel": 0, "control_block_address": 0x20000100}}, clock=lambda: 1.0)
    transport.open(rtt_config(control_block_address=0x20000100), 2.0)
    bad = RttTransport(FakeRttBackend(), {**PROFILE, "rtt": {"channel": 0, "control_block_address": 0x1000}}, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: bad.open(rtt_config(control_block_address=0x1000), 2.0))


@pytest.mark.parametrize("baud", [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600])
def test_uart_allows_exact_eight_baud_values(baud: int) -> None:
    profile = {**PROFILE, "uart": {"port": "COM7", "baud": baud}}
    factory = FakeSerialFactory()
    transport = UartTransport(factory, profile, clock=lambda: 1.0)
    transport.open(uart_config(baud=baud), 2.0)
    assert factory.kwargs == {"port": "COM7", "baudrate": baud, "bytesize": 8, "parity": "N", "stopbits": 1, "xonxoff": False, "rtscts": False, "dsrdtr": False, "timeout": 0}
    assert transport.read(4, 2.0) == b"uart"
    assert "authorization" not in transport.identity()
    transport.close()
    assert factory.port.closed


@pytest.mark.parametrize("change", [{"baud": 14400}, {"port": "COM8"}, {"data_bits": 7}, {"parity": "E"}, {"stop_bits": 2}])
def test_uart_rejects_guessing_and_non_8n1(change: dict[str, object]) -> None:
    transport = UartTransport(FakeSerialFactory(), PROFILE, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(uart_config(**change), 2.0))


def test_semihost_host_file_denial_precedes_backend() -> None:
    backend = FakeSemihostBackend()
    transport = SemihostingTransport(backend, PROFILE, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(semihost_config(host_files=True), 2.0))
    assert backend.opened is None
    transport.open(semihost_config(), 2.0)
    assert backend.opened == {"elf_path": "C:\\fixture\\app.elf", "deadline": 2.0}
    assert transport.read(4, 2.0) == b"semi"


def test_missing_profile_capability_is_unavailable_not_skip() -> None:
    constructors = [
        lambda p: MailboxTransport(FakeMailboxReader(), p, clock=lambda: 1.0),
        lambda p: RttTransport(FakeRttBackend(), p, clock=lambda: 1.0),
        lambda p: UartTransport(FakeSerialFactory(), p, clock=lambda: 1.0),
        lambda p: SemihostingTransport(FakeSemihostBackend(), p, clock=lambda: 1.0),
    ]
    configs = [mailbox_config(), rtt_config(), uart_config(), semihost_config()]
    names = ["mailbox", "rtt", "uart", "semihosting"]
    for constructor, config, name in zip(constructors, configs, names):
        profile = dict(PROFILE)
        profile.pop(name)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda constructor=constructor, profile=profile, config=config: constructor(profile).open(config, 2.0))


def test_deadlines_read_limits_open_state_disconnect_cleanup() -> None:
    assert_code("TEST_TIMEOUT", lambda: MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 2.0).open(mailbox_config(), 2.0))
    closed = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: closed.read(1, 2.0))
    active = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    active.open(mailbox_config(), 2.0)
    for count in (0, MAX_TRANSPORT_READ_BYTES + 1):
        assert_code("TEST_PROTOCOL_INVALID", lambda count=count: active.read(count, 2.0))
    failing = FailingReader()
    disconnected = MailboxTransport(failing, PROFILE, clock=lambda: 1.0)
    disconnected.open(mailbox_config(), 2.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: disconnected.read(1, 2.0))
    assert failing.closed


def test_configs_are_closed_and_typed() -> None:
    for constructor, config in [
        (lambda: MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0), mailbox_config()),
        (lambda: RttTransport(FakeRttBackend(), PROFILE, clock=lambda: 1.0), rtt_config()),
        (lambda: UartTransport(FakeSerialFactory(), PROFILE, clock=lambda: 1.0), uart_config()),
        (lambda: SemihostingTransport(FakeSemihostBackend(), PROFILE, clock=lambda: 1.0), semihost_config()),
    ]:
        config["unknown"] = True
        assert_code("TEST_PROTOCOL_INVALID", lambda constructor=constructor, config=config: constructor().open(config, 2.0))


def test_component_admission_manifest_is_closed_hash_bound_and_honest() -> None:
    manifest = json.loads((ADMISSION / "admission-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"captured_at_utc", "components", "decision", "execution", "integration", "schema"}
    assert manifest["schema"] == "stm32tk-component-admission/1"
    assert manifest["decision"] == "ADMITTED_SOFTWARE_ONLY"
    assert manifest["execution"]["hardware_body_executed"] is False
    assert manifest["execution"]["physical_transport_evidence"] is False
    for component in manifest["components"].values():
        for key in ("version_observation", "api_observation"):
            record = component[key]
            data = (ADMISSION / record["path"]).read_bytes()
            assert len(data) == record["bytes"]
            assert sha256(data).hexdigest() == record["sha256"]
    for name in ("pyocd-fake-api-observation.json", "pyserial-loopback-observation.json", "semihosting-fake-api-observation.json"):
        assert json.loads((ADMISSION / name).read_text(encoding="utf-8"))["physical_transport_evidence"] is False
    semihost = json.loads((ADMISSION / "semihosting-fake-api-observation.json").read_text(encoding="utf-8"))
    assert semihost["api"] == "pyocd.debug.semihost.ConsoleIOHandler.write"
    assert semihost["bounded_fake_session"]["native_agent_call"] == "agent.get_data(0x20000000, 8)"
    assert {semihost["bounded_fake_session"][key] for key in ("partial_output", "oversize_output", "target_read_error")} == {"closed-error"}
    assert "/tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/** text eol=lf" in ATTRIBUTES.read_text(encoding="utf-8").splitlines()


def test_installed_component_versions_and_apis_match_admission() -> None:
    import pyocd
    from pyocd.debug.rtt import RTTControlBlock
    from pyocd.debug.semihost import SemihostIOHandler
    import serial

    assert pyocd.__version__ == (ADMISSION / "pyocd-version.txt").read_text(encoding="utf-8").strip()
    assert serial.VERSION == (ADMISSION / "pyserial-version.txt").read_text(encoding="utf-8").strip()
    assert RTTControlBlock.__abstractmethods__
    with pytest.raises(NotImplementedError):
        SemihostIOHandler().open(0, 0, "r")


def test_base_validation_closes_invalid_shapes_and_state() -> None:
    assert default_clock() > 0
    for deadline in ("x", True, float("nan")):
        assert_code("TEST_PROTOCOL_INVALID", lambda deadline=deadline: check_deadline(deadline, lambda: 0.0))
    assert_code("TEST_PROTOCOL_INVALID", lambda: closed_config([], {"x"}))
    for change in ({"target_id": ""}, {"probe_id": 1}):
        config = dict(BASE_ID)
        config.update(change)
        assert_code("TEST_PROTOCOL_INVALID", lambda config=config: identity_from(config, "x"))
    invalid_regions = [None, [], [{"start": 1}], [{"start": -1, "size": 1}], [{"start": 1, "size": 0}], [{"start": 2, "size": 2}, {"start": 1, "size": 1}], [{"start": 1, "size": 2}, {"start": 2, "size": 2}]]
    for regions in invalid_regions:
        assert_code("TEST_PROTOCOL_INVALID", lambda regions=regions: ram_regions(regions))
    assert range_in_ram(0x20000000, 1, ((0x20000000, 2),))
    assert not range_in_ram("x", 1, ((0, 2),))
    base = TransportBase("x", lambda: 1.0)
    base._commit_open({"probe_id": "p", "target_id": "t", "transport": "x"})
    assert_code("TEST_PROTOCOL_INVALID", lambda: base._begin_open(BASE_ID, 2.0))
    base._mark_closed()
    assert_code("TEST_TRANSPORT_UNAVAILABLE", base.identity)


def test_transport_constructors_reject_non_ports_and_mailbox_write_surface() -> None:
    assert_code("TEST_PROTOCOL_INVALID", lambda: MailboxTransport(object(), PROFILE))
    class Writable(FakeMailboxReader):
        def write_memory(self):
            pass
    assert_code("TEST_PROTOCOL_INVALID", lambda: MailboxTransport(Writable(), PROFILE))
    assert_code("TEST_PROTOCOL_INVALID", lambda: RttTransport(object(), PROFILE))
    assert_code("TEST_PROTOCOL_INVALID", lambda: UartTransport(None, PROFILE))
    assert_code("TEST_PROTOCOL_INVALID", lambda: SemihostingTransport(object(), PROFILE))
    assert_code("TEST_PROTOCOL_INVALID", lambda: RttTransport(FakeSemihostBackend(), PROFILE))


def test_mailbox_profile_ram_partial_empty_and_local_cursor_fail_closed() -> None:
    mismatch = {**PROFILE, "ram": [{"start": 0x20000000, "size": 0x9000}]}
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: MailboxTransport(FakeMailboxReader(), mismatch, clock=lambda: 1.0).open(mailbox_config(), 2.0))
    partial = FakeMailboxReader()
    partial.header = b"short"
    transport = MailboxTransport(partial, PROFILE, clock=lambda: 1.0)
    transport.open(mailbox_config(), 2.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.read(1, 2.0))
    empty = MailboxTransport(FakeMailboxReader(producer=0, consumer=0, data=b""), PROFILE, clock=lambda: 1.0)
    empty.open(mailbox_config(), 2.0)
    assert empty.read(1, 2.0) == b""
    moved = MailboxTransport(FakeMailboxReader(producer=4, consumer=0), PROFILE, clock=lambda: 1.0)
    moved.open(mailbox_config(), 2.0)
    assert moved.read(1, 2.0) == b"t"
    moved._reader.header = (5000).to_bytes(8, "little") + (4999).to_bytes(8, "little")
    assert_code("TEST_PROTOCOL_INVALID", lambda: moved.read(1, 2.0))
    assert moved._reader.closed
    assert_code("TEST_TRANSPORT_UNAVAILABLE", moved.identity)

    class InvalidAndCloseFailure(FakeMailboxReader):
        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    reader = InvalidAndCloseFailure(producer=4097, consumer=0)
    invalid = MailboxTransport(reader, PROFILE, clock=lambda: 1.0)
    invalid.open(mailbox_config(), 2.0)
    with pytest.raises(ProtocolError) as caught:
        invalid.read(1, 2.0)
    assert caught.value.code == "TEST_PROTOCOL_INVALID"
    assert "secret" not in caught.value.message and "credential" not in caught.value.message
    assert_code("TEST_TRANSPORT_UNAVAILABLE", invalid.identity)


class FaultBackend:
    def __init__(self, *, fail_open=False, fail_read=False, invalid=None) -> None:
        self.fail_open = fail_open
        self.fail_read = fail_read
        self.invalid = invalid
        self.closed = False

    def open(self, **kwargs) -> None:
        if self.fail_open:
            raise OSError("open")

    def read(self, *args):
        if self.fail_read:
            raise OSError("read")
        return self.invalid if self.invalid is not None else b"ok"

    def identity(self) -> dict[str, str]:
        return {"control_block_address": "0x20000100"}

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("kind", ["rtt", "semihosting"])
@pytest.mark.parametrize("mode", ["open", "read", "invalid"])
def test_external_backend_failures_close_and_map_unavailable(kind: str, mode: str) -> None:
    backend = FaultBackend(fail_open=mode == "open", fail_read=mode == "read", invalid="bad" if mode == "invalid" else None)
    if kind == "rtt":
        transport = RttTransport(backend, PROFILE, clock=lambda: 1.0)
        config = rtt_config()
    else:
        transport = SemihostingTransport(backend, PROFILE, clock=lambda: 1.0)
        config = semihost_config()
    if mode == "open":
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(config, 2.0))
    else:
        transport.open(config, 2.0)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.read(2, 2.0))
    assert backend.closed


def test_rtt_profile_and_control_variants_fail_closed() -> None:
    mismatch = {**PROFILE, "ram": [{"start": 0x20000000, "size": 0x9000}]}
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: RttTransport(FakeRttBackend(), mismatch, clock=lambda: 1.0).open(rtt_config(), 2.0))
    profile = {**PROFILE, "rtt": {"channel": 0, "control_block_address": 0x20000100}}
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: RttTransport(FakeRttBackend(), profile, clock=lambda: 1.0).open(rtt_config(), 2.0))

    class InvalidIdentity(FakeRttBackend):
        def __init__(self, value: object) -> None:
            super().__init__()
            self.value = value

        def identity(self):
            return {"control_block_address": self.value}

    for value in ("not-hex", "0x1000", None):
        backend = InvalidIdentity(value)
        invalid = RttTransport(backend, PROFILE, clock=lambda: 1.0)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda invalid=invalid: invalid.open(rtt_config(), 2.0))
        assert backend.closed

    class ReadAndCloseFailure(FakeRttBackend):
        def read(self, max_bytes: int, deadline: float) -> bytes:
            raise OSError("disconnect")

        def close(self) -> None:
            raise OSError("cleanup")

    backend = ReadAndCloseFailure()
    transport = RttTransport(backend, PROFILE, clock=lambda: 1.0)
    transport.open(rtt_config(), 2.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.read(1, 2.0))
    assert_code("TEST_TRANSPORT_UNAVAILABLE", transport.identity)


class FaultSerial(FakeSerial):
    def __init__(self, *, fail=False, invalid=None) -> None:
        super().__init__()
        self.fail = fail
        self.invalid = invalid

    def read(self, size: int):
        if self.fail:
            raise OSError("read")
        return self.invalid if self.invalid is not None else super().read(size)


def test_uart_factory_open_read_and_invalid_port_failures(monkeypatch) -> None:
    def raising(**kwargs):
        raise OSError("open")
    for factory in (raising, lambda **kwargs: object()):
        transport = UartTransport(factory, PROFILE, clock=lambda: 1.0)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda transport=transport: transport.open(uart_config(), 2.0))
    for port in (FaultSerial(fail=True), FaultSerial(invalid="bad")):
        transport = UartTransport(lambda **kwargs: port, PROFILE, clock=lambda: 1.0)
        transport.open(uart_config(), 2.0)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda transport=transport: transport.read(2, 2.0))
        assert port.closed

    import serial
    observed = {}
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: observed.setdefault("port", FakeSerial()))
    assert isinstance(pyserial_factory(port="COM7"), FakeSerial)
    monkeypatch.setattr(serial, "VERSION", "other")
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: pyserial_factory(port="COM7"))


def test_semihost_path_digest_and_capability_shapes_fail_closed() -> None:
    for change in ({"elf_path": "relative.elf"}, {"elf_sha256": "bad"}):
        transport = SemihostingTransport(FakeSemihostBackend(), PROFILE, clock=lambda: 1.0)
        assert_code("TEST_PROTOCOL_INVALID", lambda transport=transport, change=change: transport.open(semihost_config(**change), 2.0))
    transport = SemihostingTransport(FakeSemihostBackend(), {**PROFILE, "semihosting": {"declared": False}}, clock=lambda: 1.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: transport.open(semihost_config(), 2.0))
    active = SemihostingTransport(FakeSemihostBackend(), PROFILE, clock=lambda: 1.0)
    active.open(semihost_config(), 2.0)
    active.close()


def test_transport_identity_binds_exact_effective_configuration() -> None:
    mailbox = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    mailbox.open(mailbox_config(), 2.0)
    assert mailbox.identity()["address"] == "0x20000000"
    assert mailbox.identity()["ring_size"] == "4096"

    rtt_backend = FakeRttBackend()
    rtt_backend.control_block_address = 0x20000100
    rtt = RttTransport(rtt_backend, PROFILE, clock=lambda: 1.0)
    rtt.open(rtt_config(), 2.0)
    assert rtt.identity()["channel"] == "0"
    assert rtt.identity()["control_block_address"] == "0x20000100"

    uart = UartTransport(FakeSerialFactory(), PROFILE, clock=lambda: 1.0)
    uart.open(uart_config(), 2.0)
    assert set(uart.identity()) == {"baud", "config_digest", "data_bits", "flow_control", "parity", "port", "probe_id", "stop_bits", "target_id", "transport"}

    semi = SemihostingTransport(FakeSemihostBackend(), PROFILE, clock=lambda: 1.0)
    semi.open(semihost_config(elf_path="C:\\fixture\\app.elf"), 2.0)
    assert semi.identity()["elf_path"] == "C:\\fixture\\app.elf"
    assert semi.identity()["elf_sha256"] == "a" * 64


def test_transport_identity_digest_is_canonical_complete_and_profile_sensitive() -> None:
    mailbox = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    mailbox.open(dict(reversed(list(mailbox_config().items()))), 2.0)
    first = mailbox.identity()
    assert len(first["config_digest"]) == 64
    assert first["ram_bounds"] == "0x20000000+0x00008000"

    same = MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0)
    same.open(mailbox_config(), 2.0)
    assert same.identity()["config_digest"] == first["config_digest"]

    alternate_profile = {**PROFILE, "mailbox": {"address": 0x20001000, "size": 2048}}
    alternate = MailboxTransport(FakeMailboxReader(), alternate_profile, clock=lambda: 1.0)
    alternate.open(mailbox_config(address=0x20001000, size=2048), 2.0)
    assert alternate.identity()["config_digest"] != first["config_digest"]

    rtt = RttTransport(FakeRttBackend(), PROFILE, clock=lambda: 1.0)
    rtt.open(rtt_config(), 2.0)
    assert rtt.identity()["ram_bounds"] == "0x20000000+0x00008000"
    assert len(rtt.identity()["config_digest"]) == 64

    uart = UartTransport(FakeSerialFactory(), PROFILE, clock=lambda: 1.0)
    uart.open(uart_config(), 2.0)
    assert uart.identity()["flow_control"] == "xonxoff=0,rtscts=0,dsrdtr=0"
    assert len(uart.identity()["config_digest"]) == 64

    semi = SemihostingTransport(FakeSemihostBackend(), PROFILE, clock=lambda: 1.0)
    semi.open(semihost_config(), 2.0)
    assert semi.identity()["host_file_policy"] == "deny"
    assert len(semi.identity()["config_digest"]) == 64


@pytest.mark.parametrize("path", [
    "C:/fixture/app.elf", "c:\\fixture\\app.elf", "C:\\Fixture\\app.elf",
    "C:\\fixture\\.\\app.elf", "C:\\fixture\\..\\app.elf", "\\\\?\\C:\\fixture\\app.elf",
    "C:\\fixture\\name. \\app.elf", "C:\\fixture\\name.\\app.elf", "C:\\fixture\\app.elf:stream",
    "C:\\fixture\\bad<name>.elf", "C:\\fixture\\bad>name.elf", "C:\\fixture\\bad\"name.elf",
    "C:\\fixture\\bad|name.elf", "C:\\fixture\\bad?name.elf", "C:\\fixture\\bad*name.elf",
    "C:\\fixture\\bad\x00name.elf", "C:\\fixture\\bad\x1fname.elf", "C:\\fixture\\bad\ud800name.elf",
    "C:\\fixture\\CON.elf",
    "C:\\fixture\\prn", "C:\\fixture\\aux.txt", "C:\\fixture\\nul", "C:\\fixture\\COM1.elf",
    "C:\\fixture\\lpt9.bin",
])
def test_semihost_requires_one_canonical_absolute_windows_path(path: str) -> None:
    backend = FakeSemihostBackend()
    transport = SemihostingTransport(backend, PROFILE, clock=lambda: 1.0)
    assert_code("TEST_PROTOCOL_INVALID", lambda: transport.open(semihost_config(elf_path=path), 2.0))
    assert backend.opened is None


@pytest.mark.parametrize(
    "constructor,config",
    [
        (lambda: MailboxTransport(FakeMailboxReader(), PROFILE, clock=lambda: 1.0), mailbox_config(address=True)),
        (lambda: MailboxTransport(FakeMailboxReader(), {**PROFILE, "mailbox": {"address": True, "size": 4096}}, clock=lambda: 1.0), mailbox_config(address=True)),
        (lambda: MailboxTransport(FakeMailboxReader(), {**PROFILE, "mailbox": {"address": 0x20000000, "size": True}}, clock=lambda: 1.0), mailbox_config(size=True)),
        (lambda: RttTransport(FakeRttBackend(), {**PROFILE, "rtt": {"channel": False}}, clock=lambda: 1.0), rtt_config(channel=0)),
        (lambda: RttTransport(FakeRttBackend(), {**PROFILE, "rtt": {"channel": 0, "control_block_address": True}}, clock=lambda: 1.0), rtt_config(control_block_address=True)),
        (lambda: UartTransport(FakeSerialFactory(), PROFILE, clock=lambda: 1.0), uart_config(stop_bits=True)),
        (lambda: UartTransport(FakeSerialFactory(), {**PROFILE, "uart": {"port": "COM7", "baud": True}}, clock=lambda: 1.0), uart_config(baud=True)),
    ],
)
def test_transport_integer_contracts_reject_bool(constructor, config) -> None:
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: constructor().open(config, 2.0))


def test_timeout_and_close_failures_always_cleanup_and_are_sanitized() -> None:
    mailbox_backend = FakeMailboxReader()
    rtt_backend = FakeRttBackend()
    uart_factory = FakeSerialFactory()
    semihost_backend = FakeSemihostBackend()
    for transport, config, backend in [
        (MailboxTransport(mailbox_backend, PROFILE, clock=lambda: 1.0), mailbox_config(), mailbox_backend),
        (RttTransport(rtt_backend, PROFILE, clock=lambda: 1.0), rtt_config(), rtt_backend),
        (UartTransport(uart_factory, PROFILE, clock=lambda: 1.0), uart_config(), uart_factory.port),
        (SemihostingTransport(semihost_backend, PROFILE, clock=lambda: 1.0), semihost_config(elf_path="C:\\fixture\\app.elf"), semihost_backend),
    ]:
        transport.open(config, 2.0)
        assert_code("TEST_TIMEOUT", lambda transport=transport: transport.read(1, 1.0))
        assert backend.closed
        assert_code("TEST_TRANSPORT_UNAVAILABLE", transport.identity)

    class CloseFailure(FakeRttBackend):
        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")
    failing = RttTransport(CloseFailure(), PROFILE, clock=lambda: 1.0)
    failing.open(rtt_config(), 2.0)
    with pytest.raises(ProtocolError) as caught:
        failing.close()
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert "secret" not in caught.value.message and "credential" not in caught.value.message


def test_all_transport_cleanup_failures_are_closed_and_sanitized() -> None:
    class MailboxCloseFailure(FakeMailboxReader):
        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    class SerialCloseFailure(FakeSerial):
        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    class SemihostCloseFailure(FakeSemihostBackend):
        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    cases = [
        (MailboxTransport(MailboxCloseFailure(), PROFILE, clock=lambda: 1.0), mailbox_config()),
        (UartTransport(lambda **kwargs: SerialCloseFailure(), PROFILE, clock=lambda: 1.0), uart_config()),
        (SemihostingTransport(SemihostCloseFailure(), PROFILE, clock=lambda: 1.0), semihost_config()),
    ]
    for transport, config in cases:
        transport.open(config, 2.0)
        with pytest.raises(ProtocolError) as caught:
            transport.close()
        assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
        assert "secret" not in caught.value.message and "credential" not in caught.value.message
        assert_code("TEST_TRANSPORT_UNAVAILABLE", transport.identity)


def test_concrete_adapters_sanitize_cleanup_failure_during_external_errors() -> None:
    class ExplodingBlock:
        def start(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    rtt = PyOcdRttAdapter(object(), control_block_factory=lambda *args, **kwargs: ExplodingBlock())
    with pytest.raises(ProtocolError) as caught:
        rtt.open(channel=0, control_block_address=None, ram_regions=((0x20000000, 0x8000),), deadline=2.0)
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert "secret" not in caught.value.message and "credential" not in caught.value.message


def test_external_open_failure_wins_over_cleanup_failure() -> None:
    class FailOpenAndClose(FaultBackend):
        def __init__(self) -> None:
            super().__init__(fail_open=True)

        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    for transport, config in (
        (RttTransport(FailOpenAndClose(), PROFILE, clock=lambda: 1.0), rtt_config()),
        (SemihostingTransport(FailOpenAndClose(), PROFILE, clock=lambda: 1.0), semihost_config()),
    ):
        with pytest.raises(ProtocolError) as caught:
            transport.open(config, 2.0)
        assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
        assert "secret" not in caught.value.message and "credential" not in caught.value.message

    class ExplodingSession(FakeSemihostSession):
        def open(self, **kwargs) -> None:
            raise OSError("C:\\secret\\credential.txt")

        def close(self) -> None:
            raise OSError("C:\\secret\\credential.txt")

    semihost = PyOcdSemihostingAdapter(ExplodingSession())
    with pytest.raises(ProtocolError) as caught:
        semihost.open(elf_path="C:\\fixture\\app.elf", deadline=2.0)
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert "secret" not in caught.value.message and "credential" not in caught.value.message


class FakeControlBlock:
    def __init__(self) -> None:
        self.control_block_address = 0x20000100
        self.up_channels = [type("Channel", (), {"read": lambda self: b"pyocd-rtt"})()]
        self.started = False

    def start(self) -> None:
        self.started = True


def test_concrete_pyocd_rtt_adapter_uses_bounded_declared_search() -> None:
    observed = {}
    block = FakeControlBlock()
    def factory(target, *, address, size):
        observed.update(target=target, address=address, size=size)
        return block
    adapter = PyOcdRttAdapter(object(), control_block_factory=factory)
    adapter.open(channel=0, control_block_address=None, ram_regions=((0x20000000, 0x8000),), deadline=2.0)
    assert observed["address"] == 0x20000000 and observed["size"] == 0x8000
    assert block.started and adapter.read(4, 2.0) == b"pyoc"
    assert adapter.identity() == {"control_block_address": "0x20000100"}
    adapter.close()


def test_concrete_pyocd_rtt_adapter_closes_invalid_and_disconnected_shapes() -> None:
    adapter = PyOcdRttAdapter(object(), control_block_factory=lambda *args, **kwargs: FakeControlBlock())
    regions = ((0x20000000, 0x8000),)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: adapter.open(channel=0, control_block_address=None, ram_regions=regions + regions, deadline=2.0))
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: adapter.read(1, 2.0))
    assert_code("TEST_TRANSPORT_UNAVAILABLE", adapter.identity)

    for actual, channels in ((None, []), (0x1000, [object()]), (0x20000100, [])):
        block = FakeControlBlock()
        block.control_block_address = actual
        block.up_channels = channels
        invalid = PyOcdRttAdapter(object(), control_block_factory=lambda *args, block=block, **kwargs: block)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda invalid=invalid: invalid.open(channel=0, control_block_address=0x20000100, ram_regions=regions, deadline=2.0))

    class BrokenChannel:
        def read(self):
            raise OSError("disconnect")

    for result in (BrokenChannel(), type("InvalidChannel", (), {"read": lambda self: "bad"})()):
        block = FakeControlBlock()
        block.up_channels = [result]
        broken = PyOcdRttAdapter(object(), control_block_factory=lambda *args, block=block, **kwargs: block)
        broken.open(channel=0, control_block_address=0x20000100, ram_regions=regions, deadline=2.0)
        assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda broken=broken: broken.read(1, 2.0))
        assert_code("TEST_TRANSPORT_UNAVAILABLE", broken.identity)


def test_concrete_pyocd_rtt_adapter_runs_real_api_against_bounded_fake_target() -> None:
    base = 0x20000000
    memory = bytearray(0x8000)
    control = base + 0x100
    buffer = base + 0x200
    memory[0x100 : 0x100 + 24] = struct.pack("<16sII", b"SEGGER RTT", 1, 0)
    memory[0x118 : 0x118 + 24] = struct.pack("<IIIIII", 0, buffer, 8, 4, 0, 0)
    memory[0x200 : 0x204] = b"real"

    class BoundedFakeTarget:
        def __init__(self) -> None:
            self.reads: list[tuple[int, int]] = []
            self.writes: list[tuple[int, int]] = []

        def _offset(self, address: int, size: int) -> int:
            assert base <= address and address + size <= base + len(memory)
            return address - base

        def read_memory_block8(self, address: int, size: int):
            self.reads.append((address, size))
            offset = self._offset(address, size)
            return list(memory[offset : offset + size])

        def read_memory_block32(self, address: int, count: int):
            offset = self._offset(address, count * 4)
            return list(struct.unpack(f"<{count}I", memory[offset : offset + count * 4]))

        def read32(self, address: int) -> int:
            return self.read_memory_block32(address, 1)[0]

        def write32(self, address: int, value: int) -> None:
            self.writes.append((address, value))
            offset = self._offset(address, 4)
            memory[offset : offset + 4] = struct.pack("<I", value)

    target = BoundedFakeTarget()
    adapter = PyOcdRttAdapter(target)
    adapter.open(channel=0, control_block_address=None, ram_regions=((base, len(memory)),), deadline=2.0)
    assert adapter.identity() == {"control_block_address": "0x20000100"}
    assert adapter.read(8, 2.0) == b"real"
    assert target.reads and max(size for _, size in target.reads) <= 1024
    assert target.writes == [(control + 24 + 16, 4)]
    adapter.close()


class FakeSemihostSession:
    def __init__(self, *, data: bytes = b"semihost", partial: bool = False, read_error: bool = False) -> None:
        self.opened = None
        self.closed = False
        self.data = data
        self.partial = partial
        self.read_error = read_error

    def open(self, *, elf_path, host_io, console, deadline) -> None:
        self.opened = (elf_path, host_io, console, deadline)

    def poll(self, *, agent, deadline) -> None:
        class FakeAgent:
            def get_data(inner_self, ptr, length):
                if self.read_error:
                    raise OSError("C:\\secret\\target-read.bin")
                data = self.data[:length]
                return data[:-1] if self.partial and data else data

        console = self.opened[2]
        console.agent = FakeAgent()
        console.write(1, 0x20000000, len(self.data))

    def close(self) -> None:
        self.closed = True


def test_concrete_pyocd_semihost_adapter_denies_files_and_bounds_fake_session() -> None:
    from pyocd.debug.semihost import ConsoleIOHandler, SemihostIOHandler

    session = FakeSemihostSession()
    adapter = PyOcdSemihostingAdapter(session, max_buffer_bytes=16)
    adapter.open(elf_path="C:\\fixture\\app.elf", deadline=2.0)
    assert isinstance(session.opened[1], SemihostIOHandler)
    assert isinstance(session.opened[2], ConsoleIOHandler)
    assert session.opened[1].open(0, 0, "r") == -1
    assert adapter.read(4, 2.0) == b"semi"
    adapter.close()
    assert session.closed


def test_concrete_pyocd_semihost_adapter_closed_error_and_handler_surfaces() -> None:
    for session, bound in ((object(), 16), (FakeSemihostSession(), 0), (FakeSemihostSession(), 65537)):
        assert_code("TEST_PROTOCOL_INVALID", lambda session=session, bound=bound: PyOcdSemihostingAdapter(session, max_buffer_bytes=bound))

    unopened = PyOcdSemihostingAdapter(FakeSemihostSession())
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: unopened.read(1, 2.0))

    class PollFailure(FakeSemihostSession):
        def poll(self, *, agent, deadline) -> None:
            raise OSError("disconnect")

    failed = PyOcdSemihostingAdapter(PollFailure())
    failed.open(elf_path="C:\\fixture\\app.elf", deadline=2.0)
    assert_code("TEST_TRANSPORT_UNAVAILABLE", lambda: failed.read(1, 2.0))

    session = FakeSemihostSession(data=b"ok")
    bounded = PyOcdSemihostingAdapter(session, max_buffer_bytes=4)
    bounded.open(elf_path="C:\\fixture\\app.elf", deadline=2.0)
    host = session.opened[1]
    assert host.close(1) == -1
    assert host.write(1, 0, 4) == 4
    assert host.read(1, 0, 4) == 4
    assert host.readc() == 0
    assert host.istty(1) == 0
    assert host.seek(1, 0) == -1
    assert host.flen(1) == -1
    assert host.remove(0, 0) == -1
    assert host.rename(0, 0, 0, 0) == -1
    assert bounded.read(4, 2.0) == b"ok"

    for failing_session in (
        FakeSemihostSession(data=b"12345"),
        FakeSemihostSession(data=b"partial", partial=True),
        FakeSemihostSession(data=b"error", read_error=True),
    ):
        failing = PyOcdSemihostingAdapter(failing_session, max_buffer_bytes=4 if failing_session.data == b"12345" else 16)
        failing.open(elf_path="C:\\fixture\\app.elf", deadline=2.0)
        with pytest.raises(ProtocolError) as caught:
            failing.read(16, 2.0)
        assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
        assert "secret" not in caught.value.message
        assert failing_session.closed
