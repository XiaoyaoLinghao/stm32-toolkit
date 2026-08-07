from __future__ import annotations

import threading

import pytest

from stm32_toolkit.probe.backend import (
    FlashBackendReport,
    ProbeBackend,
    ProbeBackendError,
    ProbeDescriptor,
)
from fakes.fake_probe import FakeProbeBackend


def descriptors() -> tuple[ProbeDescriptor, ...]:
    return (
        ProbeDescriptor(
            probe_id="probe-a",
            vendor="STMicroelectronics",
            product="ST-LINK/V3",
            board_name="NUCLEO-F429ZI",
        ),
        ProbeDescriptor(
            probe_id="probe-b",
            vendor="STMicroelectronics",
            product="ST-LINK/V2",
            board_name=None,
        ),
    )


def fake() -> FakeProbeBackend:
    return FakeProbeBackend(
        probes=descriptors(),
        memory={
            0x20000000: b"\x01\x02\x03\x04",
            0x20000010: b"hello",
        },
        registers={"r0": 1, "pc": 0x08000101, "xpsr": 0x21000000},
    )


def test_fake_probe_satisfies_the_runtime_backend_contract():
    backend = fake()

    assert isinstance(backend, ProbeBackend)
    assert [item.to_dict() for item in backend.list_probes()] == [
        {
            "probeId": "probe-a",
            "vendor": "STMicroelectronics",
            "product": "ST-LINK/V3",
            "boardName": "NUCLEO-F429ZI",
        },
        {
            "probeId": "probe-b",
            "vendor": "STMicroelectronics",
            "product": "ST-LINK/V2",
            "boardName": None,
        },
    ]


def test_attach_requires_an_exact_probe_and_target_without_halting():
    backend = fake()

    backend.open_attach("probe-a", "STM32F429ZITx")

    assert backend.attached_probe_id == "probe-a"
    assert backend.attached_target == "STM32F429ZITx"
    assert backend.halted is False
    assert backend.events == [
        ("list_probes",),
        ("open_attach", "probe-a", "STM32F429ZITx", False),
    ]


@pytest.mark.parametrize(
    ("probe_id", "target", "code"),
    [
        ("", "STM32F429ZITx", "PROBE_SELECTION_REQUIRED"),
        ("missing", "STM32F429ZITx", "PROBE_NOT_FOUND"),
        ("probe-a", "", "PROBE_TARGET_INVALID"),
    ],
)
def test_attach_fails_closed_for_ambiguous_or_invalid_selection(probe_id, target, code):
    backend = fake()

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(probe_id, target)

    assert error.value.code == code
    assert backend.attached_probe_id is None


def test_read_memory_and_registers_require_attach_and_return_exact_values():
    backend = fake()

    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0x20000000, 4)
    assert error.value.code == "PROBE_NOT_ATTACHED"

    backend.open_attach("probe-a", "STM32F429ZITx")

    assert backend.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
    assert backend.read_core_registers(("r0", "pc")) == {
        "r0": 1,
        "pc": 0x08000101,
    }


def test_partial_read_failure_is_item_scoped_and_does_not_disconnect():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")
    backend.fail_memory_read(
        0x20000010, "PROBE_READ_UNAVAILABLE", "Selected memory is unavailable"
    )

    assert backend.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0x20000010, 5)

    assert error.value.code == "PROBE_READ_UNAVAILABLE"
    assert error.value.details == {"address": 0x20000010, "length": 5}
    assert backend.attached_probe_id == "probe-a"


def test_read_bounds_and_unknown_registers_fail_without_raw_exceptions():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")

    with pytest.raises(ProbeBackendError) as memory_error:
        backend.read_memory(0x20000003, 4)
    assert memory_error.value.code == "PROBE_READ_UNAVAILABLE"

    with pytest.raises(ProbeBackendError) as register_error:
        backend.read_core_registers(("r0", "secret"))
    assert register_error.value.code == "PROBE_REGISTER_UNAVAILABLE"
    assert register_error.value.details == {"name": "secret"}


def test_disconnect_and_reconnect_are_deterministic():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")
    backend.disconnect()

    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0x20000000, 4)
    assert error.value.code == "PROBE_DISCONNECTED"

    backend.reconnect()
    backend.open_attach("probe-b", "STM32F407VGTx")
    assert backend.attached_probe_id == "probe-b"


def test_blocked_read_can_be_released_without_wall_clock_sleep():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")
    entered = threading.Event()
    release = threading.Event()
    backend.block_next_read(entered=entered, release=release)
    result: list[bytes] = []

    worker = threading.Thread(
        target=lambda: result.append(backend.read_memory(0x20000000, 4)),
        daemon=True,
    )
    worker.start()
    assert entered.wait(timeout=2)
    assert worker.is_alive()
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert result == [b"\x01\x02\x03\x04"]


def test_control_and_modify_calls_change_state_but_do_not_bypass_contract():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")

    backend.halt()
    assert backend.halted is True
    backend.step()
    assert backend.halted is True
    backend.resume()
    assert backend.halted is False
    backend.reset()
    assert backend.reset_count == 1
    report = backend.flash_file("build/arm-debug/firmware.elf")

    assert report == FlashBackendReport(bytes_programmed=1024, sectors_programmed=2)
    assert backend.flashed_paths == ["build/arm-debug/firmware.elf"]


def test_close_is_idempotent_and_clears_target_state():
    backend = fake()
    backend.open_attach("probe-a", "STM32F429ZITx")

    backend.close()
    backend.close()

    assert backend.closed is True
    assert backend.attached_probe_id is None
    assert backend.attached_target is None
