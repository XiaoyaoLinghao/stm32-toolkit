"""Backend-level controlled pre-program reset and halt preparation.

These tests drive ``PyOCDBackend`` directly with deterministic doubles.  They
cover the shared normal reset/halt preparation, the under-reset recovery reuse,
the observe-preserve refusal and the bounded diagnostic stages.  No real
Session, probe enumeration or hardware is involved.  Public workflow fields,
IPC integration and documentation belong to the subsequent feature phase.
"""

from __future__ import annotations

import struct

import pytest

from fakes.fake_pyocd import (
    FakeMemoryMap,
    FakeMemoryRegion,
    FakePyOCDDriver,
    FakePyOCDProbe,
    FakePyOCDTarget,
)
from stm32_toolkit.probe.backend import (
    PROGRAM_DIAGNOSTIC_STAGES,
    ProbeBackendError,
    validate_program_diagnostic,
)
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

TARGET = "stm32f407vg"
PROBE = "probe-a"
FLASH_BASE = 0x0800_0000
FLASH_REGIONS = FakeMemoryMap((FakeMemoryRegion(FLASH_BASE, 0x1_0000),))


def _sysresetreq() -> object:
    return pytest.importorskip("pyocd.core.target").Target.ResetType.SYSRESETREQ


def _elf(segments: tuple[tuple[int, bytes], ...]) -> bytes:
    """Build a minimal ELF32 little-endian ARM image from exact segments."""

    count = len(segments)
    offset = 52 + 32 * count
    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + b"\x00" * 8
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH", 2, 40, 1, 0, 52, 0, 0, 52, 32, count, 0, 0, 0
    )
    headers = bytearray()
    payload = bytearray()
    cursor = offset
    for address, data in segments:
        headers.extend(
            struct.pack(
                "<IIIIIIII", 1, cursor, address, address, len(data), len(data), 5, 1
            )
        )
        payload.extend(data)
        cursor += len(data)
    return bytes(header + headers + payload)


class _NoResetTarget(FakePyOCDTarget):
    """A target that does not expose the reset-and-halt capability at all."""

    reset_and_halt = None


def _managed(
    target: FakePyOCDTarget | None = None,
) -> tuple[PyOCDBackend, FakePyOCDDriver]:
    driver = FakePyOCDDriver(
        (FakePyOCDProbe(PROBE),), target=target or FakePyOCDTarget()
    )
    backend = PyOCDBackend(driver)
    backend.open_attach(PROBE, TARGET)
    assert driver.target.calls  # attach resumed an observation target
    driver.target.calls.clear()
    return backend, driver


def _imported(
    target: FakePyOCDTarget | None = None,
) -> tuple[PyOCDBackend, FakePyOCDDriver]:
    attached = target or FakePyOCDTarget(memory_map=FLASH_REGIONS)
    driver = FakePyOCDDriver((FakePyOCDProbe(PROBE),), target=attached)
    backend = PyOCDBackend(driver)
    backend.open_attach(PROBE, TARGET, halt_on_connect=True)
    driver.target.calls.clear()
    return backend, driver


def _stage(error: ProbeBackendError) -> str:
    diagnostic = error.details["programDiagnostic"]
    assert validate_program_diagnostic(diagnostic) == diagnostic
    return diagnostic["stage"]


def test_program_diagnostic_stage_schema_is_closed_and_extended() -> None:
    assert PROGRAM_DIAGNOSTIC_STAGES == frozenset(
        {
            "driver-acquire",
            "pre-program-reset",
            "pre-program-halt",
            "programmer-create",
            "program-call",
        }
    )


def test_managed_flash_resets_once_with_sysresetreq_then_programs_halted() -> None:
    backend, driver = _managed()

    report = backend.flash_elf(b"ELF")

    assert report.bytes_programmed is None
    assert report.sectors_programmed is None
    assert driver.target.calls == [
        ("reset_and_halt", _sysresetreq()),
        ("get_state",),
    ]
    assert len(driver.program_calls) == 1
    assert driver.program_calls[0][1] == b"ELF"
    assert driver.program_calls[0][2] == {
        "chipErase": "sector",
        "trustCrc": False,
        "keepUnwritten": True,
        "progress": None,
        "fileFormat": "elf",
    }


def test_imported_flash_admits_native_map_then_resets_before_programming() -> None:
    backend, driver = _imported()
    image = _elf(((FLASH_BASE + 0x1000, b"\x5A" * 32),))

    report = backend.flash_imported_elf(image)

    assert report.bytes_programmed is None
    assert driver.target.calls == [
        ("reset_and_halt", _sysresetreq()),
        ("get_state",),
    ]
    assert [call[1] for call in driver.program_calls] == [image]


def test_imported_image_outside_native_map_fails_before_reset_or_program() -> None:
    backend, driver = _imported()
    image = _elf(((0x2000_0000, b"\x01" * 16),))

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_imported_elf(image)

    assert caught.value.code == "PROBE_PROGRAM_INVALID"
    assert driver.target.calls == []
    assert driver.program_calls == []


def test_invalid_managed_image_fails_before_reset_or_program() -> None:
    backend, driver = _managed()

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"")

    assert caught.value.code == "PROBE_PROGRAM_INVALID"
    assert driver.target.calls == []
    assert driver.program_calls == []


@pytest.mark.parametrize(
    "left_state", ("running", "reset", "lockedup", "sleeping", None, object())
)
def test_every_nonhalted_post_reset_state_fails_closed(left_state: object) -> None:
    target = FakePyOCDTarget()
    target.reset_and_halt_state = left_state
    backend, driver = _managed(target)

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert caught.value.code == "PROBE_PROGRAM_FAILED"
    assert caught.value.message == "Firmware programming failed"
    assert _stage(caught.value) == "pre-program-halt"
    assert driver.target.calls == [
        ("reset_and_halt", _sysresetreq()),
        ("get_state",),
    ]
    assert driver.program_calls == []


def test_unreadable_target_state_fails_at_the_halt_stage() -> None:
    backend, driver = _managed()
    driver.target.state_error = RuntimeError("state unavailable")

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert _stage(caught.value) == "pre-program-halt"
    assert driver.program_calls == []


def test_reset_exception_fails_at_the_reset_stage_without_programming() -> None:
    target = FakePyOCDTarget()
    target.reset_and_halt_error = RuntimeError(r"reset failed C:\private\pack")
    backend, driver = _managed(target)

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert caught.value.code == "PROBE_PROGRAM_FAILED"
    assert _stage(caught.value) == "pre-program-reset"
    assert driver.target.calls == [("reset_and_halt", _sysresetreq())]
    assert driver.program_calls == []
    assert "private" not in str(caught.value)


def test_missing_reset_capability_fails_closed_before_programming() -> None:
    backend, driver = _managed(_NoResetTarget())

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert _stage(caught.value) == "pre-program-reset"
    assert driver.target.calls == []
    assert driver.program_calls == []


@pytest.mark.parametrize("entry", ("managed", "imported"))
def test_under_reset_recovery_reuses_connect_state_without_another_reset(
    entry: str,
) -> None:
    target = FakePyOCDTarget(state="halted", memory_map=FLASH_REGIONS)
    target.reset_and_halt_error = AssertionError("recovery must not reset again")
    driver = FakePyOCDDriver((FakePyOCDProbe(PROBE),), target=target)
    backend = PyOCDBackend(
        driver,
        frequency_hz=100_000,
        connection_policy="under-reset-recovery",
    )
    backend.open_attach(PROBE, TARGET, halt_on_connect=True)
    target.calls.clear()

    if entry == "managed":
        backend.flash_elf(b"ELF")
    else:
        backend.flash_imported_elf(_elf(((FLASH_BASE, b"\x02" * 16),)))

    assert target.calls == [("get_state",)]
    assert len(driver.program_calls) == 1


def test_under_reset_recovery_not_halted_fails_without_a_duplicate_reset() -> None:
    target = FakePyOCDTarget(state="halted")
    driver = FakePyOCDDriver((FakePyOCDProbe(PROBE),), target=target)
    backend = PyOCDBackend(
        driver,
        frequency_hz=100_000,
        connection_policy="under-reset-recovery",
    )
    backend.open_attach(PROBE, TARGET, halt_on_connect=True)
    target.calls.clear()
    target.state = "running"

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert _stage(caught.value) == "pre-program-halt"
    assert target.calls == [("get_state",)]
    assert driver.program_calls == []


@pytest.mark.parametrize("entry", ("managed", "imported"))
def test_observe_preserve_policy_refuses_programming_before_reset(entry: str) -> None:
    target = FakePyOCDTarget(memory_map=FLASH_REGIONS)
    driver = FakePyOCDDriver((FakePyOCDProbe(PROBE),), target=target)
    backend = PyOCDBackend(
        driver,
        frequency_hz=100_000,
        connection_policy="observe-preserve",
    )
    backend.open_attach(PROBE, TARGET)
    target.calls.clear()

    with pytest.raises(ProbeBackendError) as caught:
        if entry == "managed":
            backend.flash_elf(b"ELF")
        else:
            backend.flash_imported_elf(_elf(((FLASH_BASE, b"\x03" * 16),)))

    assert caught.value.code == "PROBE_OPERATION_UNAVAILABLE"
    assert target.calls == []
    assert driver.program_calls == []


def test_driver_acquire_failure_precedes_the_shared_preparation() -> None:
    class Backend(PyOCDBackend):
        def _get_driver(self):
            raise OSError(111, "driver acquire failed")

    target = FakePyOCDTarget()
    backend = Backend()
    backend._session = object()
    backend._target = target

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    assert _stage(caught.value) == "driver-acquire"
    assert target.calls == []
    assert caught.value.details["programDiagnostic"]["exceptions"][0]["errno"] == 111


def test_preparation_failure_returns_no_report_and_no_readback() -> None:
    target = FakePyOCDTarget()
    target.reset_and_halt_state = "running"
    backend, driver = _managed(target)

    with pytest.raises(ProbeBackendError) as caught:
        backend.flash_elf(b"ELF")

    details = caught.value.details
    assert set(details) == {"programDiagnostic"}
    assert details["programDiagnostic"]["schemaVersion"] == 1
    assert driver.program_calls == []
    assert not any(
        call[0] in {"read_memory_block8", "read_core_registers_raw"}
        for call in driver.target.calls
    )
