from __future__ import annotations

import os

import pytest

from fakes.fake_pyocd import (
    FakeBoardInfo,
    FakePyOCDDriver,
    FakePyOCDProbe,
    FakePyOCDTarget,
)
from stm32_toolkit.probe.backend import ProbeBackendError
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend


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
            "boardName": "NUCLEO-F429ZI",
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

    backend.open_attach("probe-a", "stm32f407vg")

    assert len(driver.created_sessions) == 1
    session = driver.created_sessions[0]
    assert session.open_count == 1
    assert session.options == {
        "auto_unlock": False,
        "connect_mode": "attach",
        "frequency": 1_000_000,
        "no_config": True,
        "project_dir": os.getcwd(),
        "resume_on_disconnect": False,
        "target_override": "stm32f407vg",
        "user_script": os.devnull,
    }
    assert target.calls == []


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
        ("read_core_registers_raw", ("r0",)),
        ("read_core_registers_raw", ("pc",)),
    ]
    target.register_errors.clear()
    assert backend.read_core_registers(("pc",)) == {"pc": 0x08000101}


def test_control_methods_delegate_but_flash_fails_closed():
    target = FakePyOCDTarget()
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    backend.halt()
    backend.resume()
    backend.step()
    backend.reset()
    with pytest.raises(ProbeBackendError) as error:
        backend.flash_file("build/firmware.elf")

    assert error.value.code == "PROBE_MODIFY_UNAVAILABLE"
    assert target.calls == [("halt",), ("resume",), ("step",), ("reset",)]


def test_close_is_idempotent_and_external_close_failure_does_not_retain_state():
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    driver.session_close_error = RuntimeError(r"close failed C:\secret")
    backend = PyOCDBackend(driver)
    backend.open_attach("probe-a", "stm32f407vg")

    backend.close()
    backend.close()

    assert driver.created_sessions[0].close_count == 1
    with pytest.raises(ProbeBackendError) as error:
        backend.read_memory(0, 1)
    assert error.value.code == "PROBE_NOT_ATTACHED"
