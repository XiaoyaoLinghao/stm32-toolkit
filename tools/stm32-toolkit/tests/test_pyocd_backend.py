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


ATK_RAW = "ATK 20210914"
ATK_FINGERPRINT = "91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c"
ATK_SELECTOR = f"pyocd:{ATK_FINGERPRINT}"
LEGACY_RAW = "pyocd:legacy"
LEGACY_FINGERPRINT = "bd0fce68dc31a926e34b66a939564f46d56e0a6f835cf4ce453d69189e0a6bfb"
LEGACY_SELECTOR = f"pyocd:{LEGACY_FINGERPRINT}"
PUNCTUATION_RAW = r"CMSIS-DAP_QM Rev.B #001 / \\ port *"
PUNCTUATION_FINGERPRINT = "4e5935ae758f5ba95bbad47253a8cf23e1bdedd44731aba13da92ac38277446f"
PUNCTUATION_SELECTOR = f"pyocd:{PUNCTUATION_FINGERPRINT}"


def backend_with_probes(*probe_ids: str) -> tuple[PyOCDBackend, FakePyOCDDriver]:
    driver = FakePyOCDDriver(
        tuple(FakePyOCDProbe(probe_id) for probe_id in probe_ids)
    )
    return PyOCDBackend(driver), driver


class ConnectionPolicyTarget(FakePyOCDTarget):
    def __init__(
        self,
        *,
        part_number: object = "stm32f407vg",
        state: object = "halted",
        resume_error: BaseException | None = None,
        resume_state: object = "running",
        resume_states: tuple[object, ...] | None = None,
    ) -> None:
        super().__init__(part_number=part_number, state=state)
        self.resume_error = resume_error
        self.resume_states = (
            tuple(resume_states) if resume_states is not None else (resume_state,)
        )
        self._resume_count = 0

    def resume(self) -> None:
        self.calls.append(("resume",))
        if self.resume_error is not None:
            raise self.resume_error
        state_index = min(self._resume_count, len(self.resume_states) - 1)
        self.state = self.resume_states[state_index]
        self._resume_count += 1


class _StagedInventoryDriver(FakePyOCDDriver):
    """Return a prescribed inventory on each enumeration call."""

    def __init__(self, inventories: tuple[tuple[FakePyOCDProbe, ...], ...]) -> None:
        super().__init__(inventories[0])
        self._inventories = inventories
        self.list_calls = 0

    def list_probes(self) -> tuple[FakePyOCDProbe, ...]:
        index = min(self.list_calls, len(self._inventories) - 1)
        self.list_calls += 1
        return self._inventories[index]


@pytest.mark.parametrize("transport", ("mailbox", "rtt", "uart", "semihosting"))
def test_live_target_transport_empty_read_is_explicitly_not_eof(transport: str) -> None:
    class LiveHandle:
        def read(self, maximum: int, deadline: float) -> bytes:
            return b""

    backend, _driver = backend_with_probes()
    transport_id = f"transport-{transport}"
    backend._transports[transport_id] = LiveHandle()

    assert backend.read_target_transport(transport_id, 1024, 1000) == {
        "data": b"",
        "eof": False,
    }


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
            "hardwareId": "probe-a",
            "probeFingerprint": "6794af8371f2ba4c09d5fdb157bde8cfa7666c27897128d8ce23a9bddbfb6811",
            "vendor": "Arm",
            "product": "CMSIS-DAP",
            "boardName": None,
        },
        {
            "probeId": "probe-z",
            "hardwareId": "probe-z",
            "probeFingerprint": "d6e2bddde98194a914c470d8f788dc01f80af265c644f44f958d05c64aa4bb9f",
            "vendor": "STMicroelectronics",
            "product": "ST-LINK/V3",
            "boardName": None,
        },
    ]


@pytest.mark.parametrize("probe_id", ("", "*", "probe-*", " probe-a", ATK_RAW))
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
        FakePyOCDProbe(1234),
        FakePyOCDProbe(None),
        FakePyOCDProbe("a" * 513),
        FakePyOCDProbe("contains\x00nul"),
        FakePyOCDProbe("contains\nnewline"),
        FakePyOCDProbe("contains\ttab"),
        FakePyOCDProbe("contains\x1bescape"),
        FakePyOCDProbe("contains\u202ebidi"),
        FakePyOCDProbe("\ud800"),
    ),
)
def test_malformed_hardware_descriptor_fails_closed(bad_probe):
    driver = FakePyOCDDriver((bad_probe,))

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).list_probes()

    assert error.value.code == "PROBE_DESCRIPTOR_INVALID"
    assert error.value.details == {}
    assert driver.created_sessions == []


def test_opaque_atk_hardware_id_is_listed_with_portable_selector_and_confirmation_fields():
    probe = FakePyOCDProbe(
        ATK_RAW,
        vendor_name="ATK",
        product_name="ATK-HS-V3-CMSIS-DAP",
    )

    descriptor = PyOCDBackend(FakePyOCDDriver((probe,))).list_probes()[0]

    assert descriptor.to_dict() == {
        "probeId": ATK_SELECTOR,
        "hardwareId": ATK_RAW,
        "probeFingerprint": ATK_FINGERPRINT,
        "vendor": "ATK",
        "product": "ATK-HS-V3-CMSIS-DAP",
        "boardName": None,
    }


def test_open_attach_reenumerates_and_rejects_stale_then_accepts_fresh_atk_selector():
    stale = FakePyOCDProbe(ATK_RAW)
    fresh = FakePyOCDProbe(ATK_RAW)
    driver = _StagedInventoryDriver(
        (
            (stale,),
            (FakePyOCDProbe("probe-a"),),
            (fresh,),
            (fresh,),
        )
    )
    backend = PyOCDBackend(driver)

    first_listing = backend.list_probes()
    assert first_listing[0].probe_id == ATK_SELECTOR

    with pytest.raises(ProbeBackendError) as stale_error:
        backend.open_attach(ATK_SELECTOR, "stm32f407vg")

    assert stale_error.value.code == "PROBE_NOT_FOUND"
    assert driver.list_calls == 2
    assert driver.created_sessions == []

    fresh_listing = backend.list_probes()
    assert fresh_listing[0].probe_id == ATK_SELECTOR
    evidence = backend.open_attach(ATK_SELECTOR, "stm32f407vg")

    assert driver.list_calls == 4
    assert driver.created_sessions[0].probe is fresh
    assert evidence.to_dict()["probeId"] == ATK_SELECTOR
    backend.close()


def test_open_attach_rejects_invalid_candidate_alongside_valid_without_session():
    valid = FakePyOCDProbe("probe-a")
    invalid = FakePyOCDProbe(
        "secret\nhardware", vendor_name="Vendor", product_name="Product"
    )
    driver = FakePyOCDDriver((valid, invalid))

    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(driver).open_attach("probe-a", "stm32f407vg")

    assert error.value.code == "PROBE_DESCRIPTOR_INVALID"
    assert error.value.details == {}
    assert "secret" not in str(error.value)
    assert driver.created_sessions == []


def test_utf8_hardware_id_boundary_is_enforced_by_backend():
    accepted_raw = "Ω" * 256
    rejected_raw = "Ω" * 257
    accepted_probe = FakePyOCDProbe(accepted_raw)
    accepted_driver = FakePyOCDDriver((accepted_probe,))

    descriptor = PyOCDBackend(accepted_driver).list_probes()[0]

    assert len(accepted_raw.encode("utf-8")) == 512
    descriptor_record = descriptor.to_dict()
    assert descriptor_record["hardwareId"] == accepted_raw
    assert len(descriptor_record["probeFingerprint"]) == 64
    assert descriptor_record["probeId"].startswith("pyocd:")

    rejected_driver = FakePyOCDDriver((FakePyOCDProbe(rejected_raw),))
    with pytest.raises(ProbeBackendError) as error:
        PyOCDBackend(rejected_driver).list_probes()

    assert len(rejected_raw.encode("utf-8")) == 514
    assert error.value.code == "PROBE_DESCRIPTOR_INVALID"
    assert rejected_driver.created_sessions == []


def test_printable_hostile_hardware_text_is_data_and_not_a_path_or_match_expression():
    probe = FakePyOCDProbe(
        PUNCTUATION_RAW,
        vendor_name="ATK",
        product_name="CMSIS-DAP",
    )
    driver = FakePyOCDDriver((probe,))
    backend = PyOCDBackend(driver)

    descriptor = backend.list_probes()[0]
    evidence = backend.open_attach(PUNCTUATION_SELECTOR, "stm32f407vg")

    assert descriptor.to_dict() == {
        "probeId": PUNCTUATION_SELECTOR,
        "hardwareId": PUNCTUATION_RAW,
        "probeFingerprint": PUNCTUATION_FINGERPRINT,
        "vendor": "ATK",
        "product": "CMSIS-DAP",
        "boardName": None,
    }
    assert driver.created_sessions[0].probe is probe
    assert evidence.to_dict()["probeId"] == PUNCTUATION_SELECTOR


@pytest.mark.parametrize(
    "probe_id",
    (
        "probe",
        "PROBE-A",
        "probe-a-extra",
        ATK_SELECTOR[:-1],
        ATK_SELECTOR.upper(),
        "pyocd:" + "0" * 64,
    ),
)
def test_stale_partial_case_changed_or_missing_generated_selector_opens_no_session(probe_id):
    backend, driver = backend_with_probes(ATK_RAW, "probe-a")

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(probe_id, "stm32f407vg")

    assert error.value.code == "PROBE_NOT_FOUND"
    assert driver.created_sessions == []


def test_duplicate_generated_selector_is_ambiguous_and_opens_no_session():
    backend, driver = backend_with_probes(ATK_RAW, ATK_RAW)

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(ATK_SELECTOR, "stm32f407vg")

    assert error.value.code == "PROBE_SELECTION_AMBIGUOUS"
    assert driver.created_sessions == []


def test_reserved_prefix_hardware_id_is_not_accepted_as_its_own_public_selector():
    raw = "pyocd:" + "a" * 64
    backend, driver = backend_with_probes(raw)

    with pytest.raises(ProbeBackendError) as error:
        backend.open_attach(raw, "stm32f407vg")

    assert error.value.code == "PROBE_NOT_FOUND"
    assert driver.created_sessions == []


def test_raw_pyocd_legacy_is_remapped_and_only_generated_selector_attaches():
    probe = FakePyOCDProbe(LEGACY_RAW)
    driver = FakePyOCDDriver((probe,))
    backend = PyOCDBackend(driver)

    descriptor = backend.list_probes()[0]
    assert descriptor.to_dict() == {
        "probeId": LEGACY_SELECTOR,
        "hardwareId": LEGACY_RAW,
        "probeFingerprint": LEGACY_FINGERPRINT,
        "vendor": "STMicroelectronics",
        "product": "ST-LINK/V3",
        "boardName": None,
    }

    with pytest.raises(ProbeBackendError) as raw_error:
        backend.open_attach(LEGACY_RAW, "stm32f407vg")

    assert raw_error.value.code == "PROBE_NOT_FOUND"
    assert driver.created_sessions == []

    evidence = backend.open_attach(LEGACY_SELECTOR, "stm32f407vg")
    assert driver.created_sessions[0].probe is probe
    assert evidence.to_dict()["probeId"] == LEGACY_SELECTOR
    backend.close()


def test_exact_legacy_selector_still_selects_only_the_matching_probe_object():
    selected = FakePyOCDProbe("probe-a")
    other = FakePyOCDProbe("probe-b")
    driver = FakePyOCDDriver((selected, other))

    evidence = PyOCDBackend(driver).open_attach("probe-a", "stm32f407vg")

    assert driver.created_sessions[0].probe is selected
    assert evidence.to_dict()["probeId"] == "probe-a"


def test_observation_attach_uses_pinned_halt_policy_then_returns_running():
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
        "connect_mode": "halt",
        "dap_protocol": "swd",
        "frequency": 1_000_000,
        "no_config": True,
        "pack.debug_sequences.enable": True,
        "primary_core": 0,
        "project_dir": os.getcwd(),
        "resume_on_disconnect": False,
        "target_override": "stm32f407vg",
        "user_script": os.devnull,
    }
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
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
    assert driver.target.calls == [("resume",), ("get_state",)]
    assert driver.target.state == "running"
    driver.target.calls.clear()

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


def test_modify_attach_returns_only_after_target_is_proven_halted():
    target = ConnectionPolicyTarget(state="halted")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    evidence = PyOCDBackend(driver).open_attach(
        "probe-a", "stm32f407vg", halt_on_connect=True
    )

    assert evidence.resolved_part_number == "stm32f407vg"
    assert target.calls == [("get_state",)]
    assert target.state == "halted"
    assert driver.program_calls == []


def test_observation_resume_failure_closes_candidate_and_publishes_nothing():
    target = ConnectionPolicyTarget(
        resume_error=RuntimeError(r"resume failed C:\private\target")
    )
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg")

    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert "private" not in str(caught.value)
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


def test_partial_open_failure_after_halt_restores_before_close_and_publishes_nothing():
    target = FakePyOCDTarget(state="running")
    probe = FakePyOCDProbe("probe-a")
    driver = FakePyOCDDriver((probe,), target=target)
    driver.session_halt_before_open_error = True
    driver.session_open_error = RuntimeError(r"post-connect failed C:\private\pack")
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg")

    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert "private" not in str(caught.value)
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    assert driver.created_sessions[0].close_count == 1
    assert probe.close_count == 1
    assert driver.program_calls == []
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


@pytest.mark.parametrize(
    "part_number",
    (None, "", "unknown\npart", r"C:\private", 1234),
)
def test_invalid_identity_resumes_and_closes_halted_candidate(part_number):
    target = ConnectionPolicyTarget(part_number=part_number)
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    with pytest.raises(ProbeBackendError) as caught:
        PyOCDBackend(driver).open_attach(
            "probe-a", "stm32f407vg", halt_on_connect=True
        )

    assert caught.value.code == "PROBE_TARGET_IDENTITY_UNAVAILABLE"
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1


@pytest.mark.parametrize("resume_state", ("halted", "reset", "unknown"))
def test_observation_rejects_unproven_running_state_after_resume(resume_state):
    target = ConnectionPolicyTarget(resume_states=(resume_state, resume_state))
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg")

    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert target.calls == [
        ("resume",),
        ("get_state",),
        ("resume",),
        ("get_state",),
    ]
    assert target.state == resume_state
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
    assert driver.probes[0].is_open is False
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


def test_modify_attach_rejects_candidate_that_reports_running():
    target = ConnectionPolicyTarget(state="running", resume_states=("running",))
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg", halt_on_connect=True)

    assert caught.value.code == "PROBE_BACKEND_ERROR"
    assert target.calls == [
        ("get_state",),
        ("resume",),
        ("get_state",),
    ]
    assert target.state == "running"
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
    assert driver.probes[0].is_open is False
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


def test_invalid_identity_close_failure_is_authoritative_after_candidate_resume():
    target = ConnectionPolicyTarget(part_number=None)
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    driver.session_close_error = RuntimeError(r"close failed C:\private\target")
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach(
            "probe-a", "stm32f407vg", halt_on_connect=True
        )

    assert caught.value.code == "PROBE_CLOSE_FAILED"
    assert "private" not in str(caught.value)
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
    assert driver.probes[0].is_open is False
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


def test_candidate_close_failure_chains_only_the_initiating_sanitized_error():
    target = ConnectionPolicyTarget(
        part_number=None,
        resume_error=RuntimeError(r"resume failed C:\private\target"),
    )
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    driver.session_close_error = RuntimeError(r"close failed C:\private\probe")

    with pytest.raises(ProbeBackendError) as caught:
        PyOCDBackend(driver).open_attach(
            "probe-a", "stm32f407vg", halt_on_connect=True
        )

    assert caught.value.code == "PROBE_CLOSE_FAILED"
    cause = caught.value.__cause__
    assert isinstance(cause, ProbeBackendError)
    assert cause.code == "PROBE_TARGET_IDENTITY_UNAVAILABLE"
    assert cause.message == "Selected target identity is unavailable"
    assert cause.details == {}
    assert "private" not in str(caught.value)
    assert "private" not in str(cause)
    assert target.calls == [("resume",)]
    assert driver.program_calls == []


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
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    target.calls.clear()

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
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    target.calls.clear()
    target.state = "halted"

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
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    target.calls.clear()

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
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    target.calls.clear()

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
