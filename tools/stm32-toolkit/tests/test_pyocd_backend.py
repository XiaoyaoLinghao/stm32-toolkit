from __future__ import annotations

import os
import subprocess
import sys

import pytest

from fakes.fake_pyocd import (
    FakeBoardInfo,
    FakePyOCDDriver,
    FakePyOCDProbe,
    FakePyOCDTarget,
)
from stm32_toolkit.probe.backend import FlashBackendReport, ProbeBackendError
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend, _DefaultPyOCDDriver


def backend_with_probes(*probe_ids: str) -> tuple[PyOCDBackend, FakePyOCDDriver]:
    driver = FakePyOCDDriver(
        tuple(FakePyOCDProbe(probe_id) for probe_id in probe_ids)
    )
    return PyOCDBackend(driver), driver


def test_list_probes_returns_bounded_deterministic_descriptors():
    driver = FakePyOCDDriver(
        (
            FakePyOCDProbe(
                "probe-z",
                vendor_name="STMicroelectronics",
                product_name="ST-LINK/V3",
                board_info=FakeBoardInfo(
                    name="NUCLEO-F429ZI",
                    target="stm32f429zi",
                    binary=None,
                    vendor="STMicroelectronics",
                ),
            ),
            FakePyOCDProbe(
                "probe-a",
                vendor_name="Arm",
                product_name="CMSIS-DAP",
                board_info=None,
            ),
        )
    )

    assert [item.to_dict() for item in PyOCDBackend(driver).list_probes()] == [
        {
            "probeId": "probe-a",
            "vendor": "Arm",
            "product": "CMSIS-DAP",
            "boardName": None,
        },
        {
            "probeId": "probe-z",
            "vendor": "STMicroelectronics",
            "product": "ST-LINK/V3",
            "boardName": None,
        },
    ]


@pytest.mark.parametrize("probe_id", ("", "*", "probe-*", " probe-a"))
def test_wildcard_or_malformed_probe_id_is_rejected_before_enumeration(probe_id):
    backend, driver = backend_with_probes("probe-a")
    driver.list_error = AssertionError("enumeration must not run")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(probe_id, "stm32f407vg")

    assert error.value.code == "PROBE_SELECTION_REQUIRED"
    assert driver.created_sessions == []


@pytest.mark.parametrize("probe_id", ("probe", "PROBE-A", "probe-a-extra"))
def test_partial_or_case_changed_probe_id_never_selects_a_probe(probe_id):
    backend, driver = backend_with_probes("probe-a", "probe-b")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(probe_id, "stm32f407vg")

    assert error.value.code == "PROBE_NOT_FOUND"
    assert driver.created_sessions == []


def test_duplicate_exact_ids_are_ambiguous_and_open_nothing():
    backend, driver = backend_with_probes("probe-a", "probe-a")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_SELECTION_AMBIGUOUS"
    assert driver.created_sessions == []


def test_enumeration_failure_is_stable_and_does_not_leak_raw_exception_text():
    driver = FakePyOCDDriver()
    driver.list_error = RuntimeError(r"USB failed at C:\Users\secret\probe.txt")

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).list_probes()

    assert error.value.code == "PROBE_ENUMERATION_FAILED"
    assert error.value.message == "Debug probe enumeration failed"
    assert error.value.details == {}
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "bad_probe",
    (
        FakePyOCDProbe(""),
        FakePyOCDProbe("probe with spaces"),
        FakePyOCDProbe("p" * 129),
        FakePyOCDProbe(1234),
    ),
)
def test_malformed_hardware_descriptor_fails_closed(bad_probe):
    driver = FakePyOCDDriver((bad_probe,))

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).list_probes()

    assert error.value.code == "PROBE_DESCRIPTOR_INVALID"
    assert error.value.details == {}


def test_exact_attach_uses_observation_only_session_options_without_halting():
    target = FakePyOCDTarget(
        memory={0x20000000: b"\x01\x02\x03\x04"},
        registers={"pc": 0x08000101},
    )
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)

    evidence = backend.open_attach("probe-a", "stm32f407vg")

    assert len(driver.created_sessions) == 1
    session = driver.created_sessions[0]
    assert session.open_count == 1
    assert session.options == {
        "auto_unlock": False,
        "connect_mode": "attach",
        "dap_protocol": "swd",
        "frequency": 1_000_000,
        "no_config": True,
        "pack.debug_sequences.enable": False,
        "primary_core": 0,
        "project_dir": os.getcwd(),
        "resume_on_disconnect": False,
        "target_override": "stm32f407vg",
        "user_script": os.devnull,
    }
    assert target.calls == []
    assert evidence.to_dict() == {
        "probeId": "probe-a",
        "requestedTarget": "stm32f407vg",
        "resolvedPartNumber": "stm32f407vg",
        "coreCount": 1,
    }


@pytest.mark.parametrize(
    "part_number", (None, "", "unknown\npart", r"C:\\private", 1234)
)
def test_attach_fails_closed_without_stable_physical_target_identity(part_number):
    target = FakePyOCDTarget(part_number=part_number)
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_TARGET_IDENTITY_UNAVAILABLE"


def test_flash_elf_uses_sector_only_file_programmer_options():
    backend, driver = backend_with_probes("probe-a")
    backend.open_attach("probe-a", "stm32f407vg")

    report = backend.flash_elf(b"ELF")

    assert report == FlashBackendReport(
        bytes_programmed=None, sectors_programmed=None
    )
    assert driver.program_calls == [
        (
            driver.created_sessions[0],
            b"ELF",
            {
                "chipErase": "sector",
                "trustCrc": False,
                "keepUnwritten": True,
                "progress": None,
                "fileFormat": "elf",
            },
        )
    ]
    assert driver.target.calls == []


def test_default_driver_programs_in_memory_elf_without_reset_or_progress():
    calls = []

    class Programmer:
        def __init__(self, session, **options):
            calls.append(("init", session, options))

        def program(self, stream, *, file_format):
            calls.append(("program", stream.read(), file_format))

    driver = object.__new__(_DefaultPyOCDDriver)
    driver._programmer_type = Programmer
    session = object()
    driver.program_file(
        session,
        b"ELF bytes",
        options={
            "chipErase": "sector",
            "trustCrc": False,
            "keepUnwritten": True,
            "progress": None,
            "fileFormat": "elf",
        },
    )

    assert calls == [
        (
            "init",
            session,
            {
                "progress": None,
                "chip_erase": "sector",
                "trust_crc": False,
                "keep_unwritten": True,
            },
        ),
        ("program", b"ELF bytes", "elf"),
    ]


def test_flash_elf_failure_has_stable_error_and_no_success_telemetry():
    backend, driver = backend_with_probes("probe-a")
    backend.open_attach("probe-a", "stm32f407vg")
    driver.program_error = RuntimeError(r"program failed at C:\\private\\fw.elf")

    with pytest.raises(ProbeBackendError) as error:
        backend.flash_elf(b"ELF")

    assert error.value.code == "PROBE_PROGRAM_FAILED"
    assert error.value.message == "Firmware programming failed"
    assert error.value.details == {}
    assert "private" not in str(error.value)


def test_halt_on_connect_is_rejected_before_hardware_enumeration():
    backend, driver = backend_with_probes("probe-a")
    driver.list_error = AssertionError("enumeration must not run")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-a", "stm32f407vg", halt_on_connect=True)

    assert error.value.code == "PROBE_OPERATION_LEVEL_DENIED"
    assert driver.created_sessions == []


@pytest.mark.parametrize("target", ("", "*", "stm32 f407", "t" * 129))
def test_invalid_target_is_rejected_before_hardware_enumeration(target):
    backend, driver = backend_with_probes("probe-a")
    driver.list_error = AssertionError("enumeration must not run")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-a", target)

    assert error.value.code == "PROBE_TARGET_INVALID"
    assert driver.created_sessions == []


@pytest.mark.parametrize("frequency_hz", (0, 99_999, 50_000_001, True, 1.5))
def test_invalid_debug_clock_is_rejected(frequency_hz):
    with pytest.raises(ValueError, match="frequency"):
        PyOCDBackend(FakePyOCDDriver(), frequency_hz=frequency_hz)


def test_session_open_failure_closes_once_and_leaves_backend_detached():
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    driver.session_open_error = RuntimeError(r"access failed C:\Users\secret")
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_ATTACH_FAILED"
    assert error.value.details == {"probeId": "probe-a", "target": "stm32f407vg"}
    assert "secret" not in str(error.value)
    assert driver.created_sessions[0].close_count == 1
    assert driver.probes[0].close_count == 1
    assert driver.probes[0].is_open is False
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


def test_missing_target_after_open_closes_session_and_fails_closed():
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=None)
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_TARGET_UNAVAILABLE"
    assert driver.created_sessions[0].open_count == 1
    assert driver.created_sessions[0].close_count == 1


def test_replacing_an_attachment_closes_the_previous_session():
    driver = FakePyOCDDriver(
        (FakePyOCDProbe("probe-a"), FakePyOCDProbe("probe-b"))
    )
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")
    first = driver.created_sessions[0]

    backend.open_attach("probe-b", "stm32f429zi")

    assert first.close_count == 1
    assert len(driver.created_sessions) == 2
    assert driver.created_sessions[1].open_count == 1


def test_failed_cleanup_prevents_opening_a_replacement_session():
    driver = FakePyOCDDriver(
        (FakePyOCDProbe("probe-a"), FakePyOCDProbe("probe-b"))
    )
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")
    driver.created_sessions[0].close_error = RuntimeError("close failed")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach("probe-b", "stm32f429zi")

    assert error.value.code == "PROBE_CLOSE_FAILED"
    assert len(driver.created_sessions) == 1


def test_failed_open_and_failed_direct_probe_cleanup_report_close_failure():
    probe = FakePyOCDProbe("probe-a")
    probe.close_error = RuntimeError("probe close failed")
    driver = FakePyOCDDriver((probe,))
    driver.session_open_error = RuntimeError("session open failed")

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_CLOSE_FAILED"
    assert probe.is_open is True


def test_multicore_target_is_rejected_instead_of_selecting_an_implicit_core():
    target = FakePyOCDTarget()
    target.cores[1] = object()
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).open_attach("probe-a", "stm32h745xi")

    assert error.value.code == "PROBE_TARGET_AMBIGUOUS"
    assert driver.created_sessions[0].close_count == 1


@pytest.mark.parametrize(
    ("address", "length"),
    (
        (-1, 1),
        (0x1_0000_0000, 1),
        (0, 0),
        (0, 65_537),
        (0xFFFF_FFFF, 2),
        (True, 1),
        (0, True),
    ),
)
def test_memory_bounds_are_enforced_again_at_the_backend(address, length):
    backend, _ = backend_with_probes("probe-a")
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(address, length)

    assert error.value.code == "PROBE_READ_INVALID"


def test_exact_memory_bytes_are_returned_without_transformation():
    target = FakePyOCDTarget(memory={0: b"\x00\x7f\x80\xff"})
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    assert backend.read_memory(0, 4) == b"\x00\x7f\x80\xff"
    assert target.calls == [("read_memory_block8", 0, 4)]


@pytest.mark.parametrize("result", ([1, 2, 3], [1, 2, 3, 256], None))
def test_partial_or_malformed_memory_result_is_structured(result):
    target = FakePyOCDTarget()
    target.memory_result = result
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0x20000000, 4)

    assert error.value.code == "PROBE_PARTIAL_READ"
    assert error.value.details["address"] == 0x20000000
    assert error.value.details["expectedLength"] == 4
    assert set(error.value.details) <= {"address", "expectedLength", "actualLength"}


def test_memory_failure_is_item_scoped_and_session_remains_attached():
    target = FakePyOCDTarget(memory={0x20000000: b"good"})
    target.memory_error = RuntimeError(r"fault at C:\Users\secret")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0x20000000, 4)
    assert error.value.code == "PROBE_READ_UNAVAILABLE"
    assert error.value.details == {"address": 0x20000000, "length": 4}
    assert "secret" not in str(error.value)

    target.memory_error = None
    assert backend.read_memory(0x20000000, 4) == b"good"


@pytest.mark.parametrize(
    "names",
    (
        (),
        tuple("r0" for _ in range(257)),
        ("bad register",),
        ("*",),
        ("r" * 129,),
    ),
)
def test_register_batch_and_names_are_bounded(names):
    backend, _ = backend_with_probes("probe-a")
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_core_registers(names)

    assert error.value.code == "PROBE_REGISTER_INVALID"


def test_registers_are_read_individually_and_one_failure_does_not_detach():
    target = FakePyOCDTarget(registers={"r0": 7, "pc": 0x08000101})
    target.register_errors["pc"] = RuntimeError(r"register fault C:\secret")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_core_registers(("r0", "pc"))

    assert error.value.code == "PROBE_REGISTER_UNAVAILABLE"
    assert error.value.details == {"name": "pc"}
    assert target.calls == [
        ("get_state",),
        ("read_core_registers_raw", ("r0",)),
        ("read_core_registers_raw", ("pc",)),
    ]
    target.register_errors.clear()
    assert backend.read_core_registers(("pc",)) == {"pc": 0x08000101}


def test_running_target_register_read_fails_without_implicit_halt():
    target = FakePyOCDTarget(registers={"pc": 0x08000101}, state="running")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as error:
        backend.read_core_registers(("pc",))

    assert error.value.code == "PROBE_REGISTER_UNAVAILABLE"
    assert error.value.details == {"state": "running"}
    assert target.calls == [("get_state",)]


def test_control_methods_delegate_without_implicit_extra_operations():
    target = FakePyOCDTarget()
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    backend.halt()
    backend.resume()
    backend.step()
    backend.reset()

    assert target.calls == [("halt",), ("resume",), ("step",), ("reset",)]


def test_close_failure_is_structured_idempotent_and_does_not_retain_state():
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    driver.session_close_error = RuntimeError(r"close failed C:\secret")
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    with pytest.raises(ProbeBackendError) as close_error:
        backend.close()
    backend.close()

    assert close_error.value.code == "PROBE_CLOSE_FAILED"
    assert driver.created_sessions[0].close_count == 1
    assert driver.probes[0].close_count == 1
    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0, 1)
    assert error.value.code == "PROBE_NOT_ATTACHED"


def test_board_metadata_property_is_not_opened_during_passive_enumeration():
    class ProbeWithExplosiveBoardInfo(FakePyOCDProbe):
        @property
        def associated_board_info(self):
            raise RuntimeError("USB must not be opened for board metadata")

        @associated_board_info.setter
        def associated_board_info(self, value):
            pass

    probe = ProbeWithExplosiveBoardInfo("probe-a")

    assert PyOCDBackend(FakePyOCDDriver((probe,))).list_probes()[0].board_name is None


def test_public_probe_import_exports_backend_without_importing_pyocd():
    code = """
import sys
from stm32_toolkit.probe import PyOCDBackend, ProbeServiceConfig, ProbeServiceSupervisor
assert PyOCDBackend.__name__ == "PyOCDBackend"
assert ProbeServiceConfig.__name__ == "ProbeServiceConfig"
assert ProbeServiceSupervisor.__name__ == "ProbeServiceSupervisor"
assert not any(name == "pyocd" or name.startswith("pyocd.") for name in sys.modules)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_missing_optional_dependency_is_a_stable_backend_failure(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pyocd" or name.startswith("pyocd."):
            raise ModuleNotFoundError("blocked optional dependency")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    backend = PyOCDBackend()

    with pytest.raises(ProbeBackendError) as error:
        backend.list_probes()

    assert error.value.code == "PROBE_BACKEND_UNAVAILABLE"
    assert error.value.message == "PyOCD support is not installed"
    assert error.value.details == {}
