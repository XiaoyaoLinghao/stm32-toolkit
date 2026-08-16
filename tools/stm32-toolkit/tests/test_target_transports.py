from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from stm32_toolkit.testing.model import TestProtocolError as ProtocolError
from stm32_toolkit.testing.transports import (
    MailboxTransport,
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
    result: dict[str, object] = {"elf_path": "C:/fixture/app.elf", "elf_sha256": "a" * 64, "host_files": False, **BASE_ID}
    result.update(changes)
    return result


def test_mailbox_is_read_only_bounded_and_identity_bound() -> None:
    reader = FakeMailboxReader()
    transport = MailboxTransport(reader, PROFILE, clock=lambda: 1.0)
    transport.open(mailbox_config(), 2.0)
    assert transport.read(4, 2.0) == b"test"
    assert reader.calls == [(0x20000000, 16, 2.0), (0x20000010, 4, 2.0)]
    assert not hasattr(reader, "write_memory")
    assert transport.identity() == {"probe_id": "probe:fixture", "target_id": "stm32:fixture", "transport": "mailbox"}
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
        bad = MailboxTransport(FakeMailboxReader(producer, consumer), PROFILE, clock=lambda: 1.0)
        bad.open(mailbox_config(), 2.0)
        assert_code("TEST_PROTOCOL_INVALID", lambda bad=bad: bad.read(4, 2.0))


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
