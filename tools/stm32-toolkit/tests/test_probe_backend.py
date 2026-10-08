from __future__ import annotations

import threading
from types import MappingProxyType

import pytest

from stm32_toolkit.probe.backend import (
    DebugHandoffMetadata,
    FlashBackendReport,
    ProbeBackend,
    ProbeBackendError,
    ProbeDescriptor,
    extract_program_diagnostic,
    make_program_diagnostic,
    program_diagnostic_details,
    validate_program_diagnostic,
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


def _copy_program_diagnostic(value: dict[str, object]) -> dict[str, object]:
    """Copy one factory-produced diagnostic without relying on private code."""

    copied = dict(value)
    copied["exceptions"] = [dict(entry) for entry in value["exceptions"]]
    return copied


def _snapshot_program_diagnostic(value: dict[str, object]) -> dict[str, object]:
    """Snapshot a non-recursive wire candidate without invoking private helpers."""

    snapshot = dict(value)
    exceptions = value.get("exceptions")
    if isinstance(exceptions, list):
        snapshot["exceptions"] = [
            dict(entry) if isinstance(entry, dict) else entry for entry in exceptions
        ]
    return snapshot


def test_fake_probe_satisfies_the_runtime_backend_contract():
    backend = fake()

    assert isinstance(backend, ProbeBackend)
    assert [item.to_dict() for item in backend.list_probes()] == [
        {
            "probeId": "probe-a",
            "hardwareId": "probe-a",
            "probeFingerprint": "6794af8371f2ba4c09d5fdb157bde8cfa7666c27897128d8ce23a9bddbfb6811",
            "vendor": "STMicroelectronics",
            "product": "ST-LINK/V3",
            "boardName": "NUCLEO-F429ZI",
        },
        {
            "probeId": "probe-b",
            "hardwareId": "probe-b",
            "probeFingerprint": "3e2c743bc9431b093422c1056976079b4eff185192b90106a4d75def15ab90e7",
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


@pytest.mark.parametrize(
    "case",
    [
        "suppressed-chain-and-empty-redactions",
        "scalar-redaction",
        "non-string-redaction-token",
        "iterator-budget-eight-of-nine",
        "invalid-stage",
        "invalid-error",
        "validator-top-shape",
        "validator-header",
        "validator-entry-shape",
        "validator-integer",
    ],
    ids=lambda case: case,
)
def test_program_diagnostic_factory_and_validation_boundaries(case):
    if case == "suppressed-chain-and-empty-redactions":
        try:
            try:
                raise ValueError("hidden context")
            except ValueError:
                raise RuntimeError("outer failure") from None
        except RuntimeError as error:
            details = program_diagnostic_details("program-call", error)

        value = details["programDiagnostic"]
        entry = value["exceptions"][0]
        assert value["schemaVersion"] == 1
        assert value["stage"] == "program-call"
        assert len(value["exceptions"]) == 1
        assert entry == {
            "type": "builtins.RuntimeError",
            "message": "outer failure",
            "errno": None,
            "winerror": None,
            "address": None,
            "resultCode": None,
        }
        extracted = extract_program_diagnostic(details)
        assert extracted == value
        assert extracted is not value
        assert extracted["exceptions"] is not value["exceptions"]
        return

    if case == "scalar-redaction":
        details = program_diagnostic_details(
            "program-call",
            RuntimeError("token-value leaked"),
            redactions="token-value",
        )
        message = details["programDiagnostic"]["exceptions"][0]["message"]
        assert "token-value" not in message
        assert "[redacted]" in message
        return

    if case == "non-string-redaction-token":
        details = program_diagnostic_details(
            "program-call",
            RuntimeError("token-value leaked"),
            redactions=("", 17, "token-value"),
        )
        message = details["programDiagnostic"]["exceptions"][0]["message"]
        assert "token-value" not in message
        assert "[redacted]" in message
        return

    if case == "iterator-budget-eight-of-nine":
        class RedactionBudget:
            def __init__(self, values):
                self._values = iter(values)
                self.next_calls = 0

            def __iter__(self):
                return self

            def __next__(self):
                self.next_calls += 1
                return next(self._values)

        budget = RedactionBudget(
            (
                "budget-secret",
                "second",
                "third",
                "fourth",
                "fifth",
                "sixth",
                "seventh",
                "eighth",
                "ninth",
            )
        )
        details = program_diagnostic_details(
            "program-call",
            RuntimeError("budget-secret leaked"),
            redactions=budget,
        )
        message = details["programDiagnostic"]["exceptions"][0]["message"]
        assert budget.next_calls == 8
        assert "budget-secret" not in message
        assert "[redacted]" in message
        return

    if case == "invalid-stage":
        with pytest.raises(ValueError) as error:
            make_program_diagnostic("unknown-stage", RuntimeError("failure"))
        assert str(error.value) == "program diagnostic stage is invalid"
        return

    if case == "invalid-error":
        with pytest.raises(TypeError) as error:
            make_program_diagnostic("program-call", object())
        assert str(error.value) == "program diagnostic exception is invalid"
        return

    diagnostic = make_program_diagnostic("program-call", RuntimeError("stable"))
    candidate = _copy_program_diagnostic(diagnostic)
    if case == "validator-top-shape":
        candidate["extra"] = "refused"
    elif case == "validator-header":
        candidate["schemaVersion"] = 2
    elif case == "validator-entry-shape":
        candidate["exceptions"][0] = None
    elif case == "validator-integer":
        candidate["exceptions"][0]["errno"] = True
    else:
        raise AssertionError(f"unknown diagnostic case: {case}")

    before = _snapshot_program_diagnostic(candidate)
    assert validate_program_diagnostic(candidate) is None
    assert candidate == before


@pytest.mark.parametrize(
    "case",
    [
        "missing-candidate",
        "recursive-mapping",
        "recursive-sequence",
        "mapping-proxy-roundtrip",
    ],
    ids=lambda case: case,
)
def test_extract_program_diagnostic_public_nested_wire_boundaries(case):
    details = program_diagnostic_details("program-call", RuntimeError("stable"))

    if case == "missing-candidate":
        submitted: dict[str, object] = {}
        before = dict(submitted)
        assert extract_program_diagnostic(submitted) is None
        assert submitted == before
        assert details["programDiagnostic"] is not None
        return

    if case == "recursive-mapping":
        source = details["programDiagnostic"]
        candidate = _copy_program_diagnostic(source)
        candidate["loop"] = candidate
        submitted = {"programDiagnostic": candidate}
        exceptions = candidate["exceptions"]
        assert extract_program_diagnostic(submitted) is None
        assert candidate["loop"] is candidate
        assert candidate["schemaVersion"] == source["schemaVersion"]
        assert candidate["stage"] == source["stage"]
        assert candidate["exceptions"] is exceptions
        return

    if case == "recursive-sequence":
        cycle: list[object] = []
        cycle.append(cycle)
        candidate = {
            "schemaVersion": 1,
            "stage": "program-call",
            "exceptions": cycle,
        }
        submitted = {"programDiagnostic": candidate}
        assert extract_program_diagnostic(submitted) is None
        assert candidate["schemaVersion"] == 1
        assert candidate["stage"] == "program-call"
        assert candidate["exceptions"] is cycle
        assert cycle[0] is cycle
        return

    if case == "mapping-proxy-roundtrip":
        source = details["programDiagnostic"]
        proxy_candidate = MappingProxyType(source)
        proxy_details = MappingProxyType({"programDiagnostic": proxy_candidate})
        extracted = extract_program_diagnostic(proxy_details)
        assert extracted == _copy_program_diagnostic(source)
        assert type(extracted) is dict
        assert extracted is not source
        assert source == _copy_program_diagnostic(source)
        return

    raise AssertionError(f"unknown diagnostic extraction case: {case}")


@pytest.mark.parametrize(
    "case",
    [
        "invalid-hardware-id",
        "selector-mismatch",
        "fingerprint-mismatch",
        "valid-default-identity",
    ],
    ids=lambda case: case,
)
def test_probe_descriptor_identity_validation_preserves_inputs(case):
    expected = descriptors()[0]
    arguments = {
        "probe_id": expected.probe_id,
        "vendor": expected.vendor,
        "product": expected.product,
        "board_name": expected.board_name,
    }

    if case == "invalid-hardware-id":
        with pytest.raises(ValueError) as error:
            ProbeDescriptor(**arguments, hardware_id="")
        assert str(error.value) == "probe descriptor hardware identifier is invalid"
        return

    if case == "selector-mismatch":
        with pytest.raises(ValueError) as error:
            ProbeDescriptor(**arguments, hardware_id="probe-b")
        assert str(error.value) == "probe descriptor selector is invalid"
        return

    if case == "fingerprint-mismatch":
        with pytest.raises(ValueError) as error:
            ProbeDescriptor(**arguments, probe_fingerprint="0" * 64)
        assert str(error.value) == "probe descriptor fingerprint is invalid"
        return

    descriptor = ProbeDescriptor(**arguments)
    assert descriptor.to_dict() == expected.to_dict()


@pytest.mark.parametrize(
    "case",
    ["constructor-invalid", "from-value-invalid", "valid-from-value"],
    ids=lambda case: case,
)
def test_debug_handoff_metadata_model_boundaries(case):
    value = {
        "probeId": "probe-a",
        "target": "STM32F429ZITx",
        "boardId": "probe-a",
    }

    if case == "constructor-invalid":
        with pytest.raises(ValueError) as error:
            DebugHandoffMetadata("probe-a", "STM32F429ZITx", "probe-b")
        assert str(error.value) == "debug handoff metadata is invalid"
        return

    if case == "from-value-invalid":
        candidate = dict(value)
        candidate["target"] = 1
        before = dict(candidate)
        with pytest.raises(ValueError) as error:
            DebugHandoffMetadata.from_value(candidate)
        assert str(error.value) == "debug handoff metadata is invalid"
        assert candidate == before
        return

    metadata = DebugHandoffMetadata.from_value(value)
    assert metadata.to_dict() == value
    assert value == {
        "probeId": "probe-a",
        "target": "STM32F429ZITx",
        "boardId": "probe-a",
    }
