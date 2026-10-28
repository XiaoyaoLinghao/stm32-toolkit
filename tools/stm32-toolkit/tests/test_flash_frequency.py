"""Explicit flash frequency, selected-configuration details and recovery hints.

All tests are offline: fake supervisors/backends, loopback fake hardware and
monkeypatched public dispatch.  No test enumerates or touches real hardware.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.hardware_workflows as hardware_mod
import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main
from stm32_toolkit.hardware_workflows import (
    FlashImportedWorkflowRequest,
    FlashWorkflowRequest,
    HardwareWorkflowSeams,
    flash_imported_workflow,
    flash_workflow,
)
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.probe.attach_diagnostics import (
    make_attach_diagnostic,
    make_primary,
)
from stm32_toolkit.probe.worker import (
    NORMAL_CONNECTION_POLICY,
    UNDER_RESET_RECOVERY_CONNECTION_POLICY,
    ProbeWorkerConfig,
)
from stm32_toolkit.result import OperationResult

from test_cli_hardware import _context, _pins
from test_external_firmware_workflow import (
    _backend,
    _prepare_import,
    _seams as _imported_seams,
)
from test_hardware_workflows import (
    BUILD_ID,
    ELF_SHA,
    _Recorder,
    _capturing_worker_seams,
    _project,
    _run,
    _seams,
)
from test_mcp_hardware import _runtime, _schemas
from test_mcp_roots import _RootSession


def _flash(
    project: Path,
    data_root: Path,
    *,
    frequency_hz: object = None,
    recovery: object = False,
    seams: HardwareWorkflowSeams | None = None,
    session: str = "session-a",
) -> object:
    selected_seams = seams if seams is not None else _seams(_Recorder())
    return _run(
        flash_workflow(
            FlashWorkflowRequest(
                project,
                data_root,
                session,
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                True,
                recovery,
                frequency_hz=frequency_hz,
            ),
            _seams=selected_seams,
        )
    )


def _options(result: object) -> dict[str, object]:
    assert result.ok is True, result.to_dict()  # type: ignore[attr-defined]
    return result.details["flashOptions"]  # type: ignore[attr-defined]


def _failure_operation(
    code: str, details: dict[str, object] | None = None
):
    async def operation(_request: object, _client: object) -> OperationResult[object]:
        return OperationResult.failure(
            "stm32_flash", code, "simulated failure", details or {}
        )

    return operation


# ---------------------------------------------------------------------------
# managed configuration selection
# ---------------------------------------------------------------------------


def test_managed_omitted_frequency_keeps_default_and_reports_configuration(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(project, tmp_path / "data", seams=_seams(recorder))

    assert result.details["flashOptions"] == {
        "requestedFrequencyHz": None,
        "configuredFrequencyHz": 1_000_000,
        "connectionPolicy": NORMAL_CONNECTION_POLICY,
        "preProgramReset": "sysresetreq",
        "preProgramHaltRequired": True,
        "automaticRetry": False,
    }
    assert result.details["postFlash"] == {
        "targetState": "unknown",
        "runVerified": False,
    }
    assert "recoverySuggestion" not in result.details
    assert recorder.events.count("operation") == 1


def test_managed_explicit_frequency_reaches_worker_config_and_preserves_profile(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    captured: list[object] = []
    base = ProbeWorkerConfig(target_profile={"mcu": "stm32f407vgtx"})

    result = _flash(
        project,
        tmp_path / "data",
        frequency_hz=4_000_000,
        seams=_capturing_worker_seams(recorder, captured, worker_config=base),
    )

    assert len(captured) == 1
    selected = captured[0]
    assert type(selected) is ProbeWorkerConfig
    assert selected.frequency_hz == 4_000_000
    assert selected.connection_policy == NORMAL_CONNECTION_POLICY
    assert selected.transport_provider == base.transport_provider
    assert selected.target_profile() == {"mcu": "stm32f407vgtx"}
    assert selected is not base
    assert base.frequency_hz == 1_000_000
    assert result.details["flashOptions"] == {
        "requestedFrequencyHz": 4_000_000,
        "configuredFrequencyHz": 4_000_000,
        "connectionPolicy": NORMAL_CONNECTION_POLICY,
        "preProgramReset": "sysresetreq",
        "preProgramHaltRequired": True,
        "automaticRetry": False,
    }
    assert recorder.events.count("operation") == 1


def test_non_default_frequency_reaches_fake_pyocd_session_options() -> None:
    from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    backend = PyOCDBackend(driver, frequency_hz=4_000_000)

    backend.open_attach("probe-a", "stm32f407vg")

    assert len(driver.created_sessions) == 1
    assert driver.created_sessions[0].options["frequency"] == 4_000_000
    backend.close()


@pytest.mark.parametrize("value", [100_000, 50_000_000])
def test_managed_frequency_boundaries_are_accepted(
    tmp_path: Path, value: int
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project, tmp_path / "data", frequency_hz=value, seams=_seams(recorder)
    )

    assert _options(result)["requestedFrequencyHz"] == value
    assert _options(result)["configuredFrequencyHz"] == value


@pytest.mark.parametrize("value", [True, False, 1.0, 999_999.0, "1000000", [1], {}])
def test_managed_frequency_type_errors_precede_every_effect(
    tmp_path: Path, value: object
) -> None:
    project = _project(tmp_path / "project")
    data_root = tmp_path / "data"
    recorder = _Recorder()

    result = _flash(
        project, data_root, frequency_hz=value, seams=_seams(recorder)
    )

    assert result.ok is False
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "frequencyHz"
    assert result.details["rule"] == "type"
    assert "flashOptions" not in result.details
    assert recorder.events == []
    assert recorder.configs == []
    assert not data_root.exists()


@pytest.mark.parametrize("value", [99_999, 50_000_001, -1, 0])
def test_managed_frequency_range_errors_precede_every_effect(
    tmp_path: Path, value: int
) -> None:
    project = _project(tmp_path / "project")
    data_root = tmp_path / "data"
    recorder = _Recorder()

    result = _flash(
        project, data_root, frequency_hz=value, seams=_seams(recorder)
    )

    assert result.ok is False
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "frequencyHz"
    assert result.details["rule"] == "range"
    assert result.details["minimumHz"] == 100_000
    assert result.details["maximumHz"] == 50_000_000
    assert recorder.events == []
    assert not data_root.exists()


def test_managed_authorization_precedes_frequency_validation(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                False,
                False,
                frequency_hz="bad",
            ),
            _seams=_seams(recorder),
        )
    )

    assert result.code == "AUTHORIZATION_REQUIRED"
    assert recorder.events == []


# ---------------------------------------------------------------------------
# under-reset compatibility
# ---------------------------------------------------------------------------


def test_managed_recovery_omitted_frequency_keeps_fixed_policy(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    captured: list[object] = []

    result = _flash(
        project,
        tmp_path / "data",
        recovery=True,
        seams=_capturing_worker_seams(recorder, captured),
    )

    selected = captured[0]
    assert selected.frequency_hz == 100_000
    assert selected.connection_policy == UNDER_RESET_RECOVERY_CONNECTION_POLICY
    assert result.details["flashOptions"] == {
        "requestedFrequencyHz": None,
        "configuredFrequencyHz": 100_000,
        "connectionPolicy": UNDER_RESET_RECOVERY_CONNECTION_POLICY,
        "preProgramReset": "under-reset-connect",
        "preProgramHaltRequired": True,
        "automaticRetry": False,
    }
    assert "recoverySuggestion" not in result.details


def test_managed_recovery_accepts_explicit_100000(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    captured: list[object] = []

    result = _flash(
        project,
        tmp_path / "data",
        frequency_hz=100_000,
        recovery=True,
        seams=_capturing_worker_seams(recorder, captured),
    )

    assert captured[0].frequency_hz == 100_000
    assert captured[0].connection_policy == UNDER_RESET_RECOVERY_CONNECTION_POLICY
    assert _options(result)["requestedFrequencyHz"] == 100_000


@pytest.mark.parametrize("value", [100_001, 1_000_000, 50_000_000])
def test_managed_recovery_conflicting_frequency_fails_before_effects(
    tmp_path: Path, value: int
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        frequency_hz=value,
        recovery=True,
        seams=_seams(recorder),
    )

    assert result.ok is False
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "frequencyHz"
    assert result.details["rule"] == "conflict"
    assert "flashOptions" not in result.details
    assert recorder.events == []
    assert recorder.configs == []


# ---------------------------------------------------------------------------
# recovery suggestion gates
# ---------------------------------------------------------------------------


def test_program_failure_without_diagnostic_gets_bounded_suggestion(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(recorder, operation=_failure_operation("PROBE_PROGRAM_FAILED")),
    )

    assert result.ok is False
    assert result.code == "PROBE_PROGRAM_FAILED"
    suggestion = result.details["recoverySuggestion"]
    assert suggestion == {
        "kind": "under-reset",
        "frequencyHz": 100_000,
        "cliOption": "--recovery-under-reset",
        "mcpArgument": "recoveryUnderReset",
        "requiresNewAuthorization": True,
        "automaticRetry": False,
        "guidance": suggestion["guidance"],
    }
    assert "Stop here" in suggestion["guidance"]
    assert "separately authorized" in suggestion["guidance"]
    assert "halted" in suggestion["guidance"]
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 1_000_000
    assert "postFlash" not in result.details


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        ("session-open", "probe-disconnected"),
        ("session-open", "probe-io"),
        ("halt-verify", "target-register"),
        ("halt-verify", "postcondition-failed"),
    ],
)
def test_eligible_attach_diagnostic_gets_suggestion(
    tmp_path: Path, stage: str, reason: str
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    diagnostic = make_attach_diagnostic(make_primary(stage, reason, "UNTYPED"))

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(
            recorder,
            operation=_failure_operation(
                "PROBE_ATTACH_FAILED", {"attachDiagnostic": diagnostic}
            ),
        ),
    )

    assert result.details["attachDiagnostic"]["primary"] == {
        "stage": stage,
        "reason": reason,
        "sourceCode": "UNTYPED",
    }
    assert result.details["recoverySuggestion"]["kind"] == "under-reset"


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        ("session-open", "target-unsupported"),
        ("session-open", "permission-denied"),
        ("halt-verify", "identity-mismatch"),
        ("resume-verify", "postcondition-failed"),
        ("target-identity", "probe-disconnected"),
    ],
)
def test_ineligible_attach_diagnostic_gets_no_suggestion_and_keeps_guidance(
    tmp_path: Path, stage: str, reason: str
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    diagnostic = make_attach_diagnostic(make_primary(stage, reason, "UNTYPED"))

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(
            recorder,
            operation=_failure_operation(
                "PROBE_ATTACH_FAILED", {"attachDiagnostic": diagnostic}
            ),
        ),
    )

    assert result.code == "PROBE_ATTACH_FAILED"
    assert "recoverySuggestion" not in result.details
    if reason == "target-unsupported":
        assert result.details["requestedTarget"] == "stm32f407vg"
        assert "pyocd list --targets" in result.details["guidance"]
    if stage == "resume-verify" and reason == "postcondition-failed":
        assert result.details["lastVerifiedTargetState"] is None
        assert "run and reset conditions" in result.details["guidance"]


@pytest.mark.parametrize(
    "code",
    [
        "PROBE_ATTACH_FAILED",
        "PROBE_FLASH_IDENTITY_MISMATCH",
        "FIRMWARE_STALE",
        "FIRMWARE_INPUT_CHANGED",
        "AUTHORIZATION_REQUIRED",
        "PROBE_FLASH_VERIFY_FAILED",
        "HARDWARE_INTERNAL_ERROR",
    ],
)
def test_other_failures_get_no_suggestion(tmp_path: Path, code: str) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(recorder, operation=_failure_operation(code)),
    )

    assert result.ok is False
    assert "recoverySuggestion" not in result.details
    assert result.details["flashOptions"]["automaticRetry"] is False


def test_cleanup_failure_takes_precedence_over_recovery_suggestion(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(
            recorder,
            operation=_failure_operation("PROBE_PROGRAM_FAILED"),
            stop_error=True,
        ),
    )

    assert result.code == "HARDWARE_CLEANUP_FAILED"
    assert "recoverySuggestion" not in result.details
    assert result.details["flashOptions"]["automaticRetry"] is False


def test_success_gets_no_suggestion(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(project, tmp_path / "data", seams=_seams(recorder))

    assert result.ok is True
    assert "recoverySuggestion" not in result.details


def test_custom_non_normal_configuration_is_not_advertised_as_normal(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    captured: list[object] = []
    recovery_config = ProbeWorkerConfig().for_under_reset_recovery()
    seams = replace(
        _capturing_worker_seams(
            recorder, captured, worker_config=recovery_config
        ),
        flash=_failure_operation("PROBE_PROGRAM_FAILED"),
    )

    result = _flash(project, tmp_path / "data", seams=seams)

    assert len(captured) == 1
    assert captured[0] is recovery_config
    assert result.code == "PROBE_PROGRAM_FAILED"
    assert result.details["flashOptions"] == {
        "requestedFrequencyHz": None,
        "configuredFrequencyHz": 100_000,
        "connectionPolicy": UNDER_RESET_RECOVERY_CONNECTION_POLICY,
        "preProgramReset": "under-reset-connect",
        "preProgramHaltRequired": True,
        "automaticRetry": False,
    }
    assert "recoverySuggestion" not in result.details


def test_malformed_attach_diagnostic_gets_no_suggestion(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(
            recorder,
            operation=_failure_operation(
                "PROBE_ATTACH_FAILED", {"attachDiagnostic": {"version": 1}}
            ),
        ),
    )

    assert result.code == "PROBE_ATTACH_FAILED"
    assert "recoverySuggestion" not in result.details


def test_eligible_failure_preserves_message_details_and_one_operation(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    program_diagnostic = {"stage": "program", "reason": "target-response"}

    async def failed(
        _request: object, _client: object
    ) -> OperationResult[object]:
        recorder.events.append("operation")
        return OperationResult.failure(
            "stm32_flash",
            "PROBE_PROGRAM_FAILED",
            "exact program failure",
            {"programDiagnostic": program_diagnostic},
        )

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(recorder, operation=failed),
    )

    assert result.ok is False
    assert result.code == "PROBE_PROGRAM_FAILED"
    assert result.message == "exact program failure"
    assert result.details["programDiagnostic"] == program_diagnostic
    assert result.details["recoverySuggestion"]["kind"] == "under-reset"
    assert recorder.events.count("operation") == 1


def test_cancellation_stops_without_retry_or_suggestion(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    async def cancelled(
        _request: object, _client: object
    ) -> OperationResult[object]:
        recorder.events.append("operation")
        raise asyncio.CancelledError

    seams = _seams(recorder, operation=cancelled)
    with pytest.raises(asyncio.CancelledError):
        _flash(project, tmp_path / "data", seams=seams)

    assert recorder.events.count("operation") == 1
    assert "client.close" in recorder.events
    assert "supervisor.stop" in recorder.events


def test_already_recovery_failure_gets_no_suggestion(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    result = _flash(
        project,
        tmp_path / "data",
        recovery=True,
        seams=_seams(recorder, operation=_failure_operation("PROBE_PROGRAM_FAILED")),
    )

    assert result.code == "PROBE_PROGRAM_FAILED"
    assert "recoverySuggestion" not in result.details
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 100_000


# ---------------------------------------------------------------------------
# imported route
# ---------------------------------------------------------------------------


def test_imported_success_reports_frequency_and_keeps_post_flash_receipt(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path
    )
    backend = _backend(admission)

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                import_id,
                source_sha,
                True,
                frequency_hz=2_000_000,
            ),
            _seams=_imported_seams(backend),
        )
    )

    assert result.ok is True, result.to_dict()
    assert result.details["flashOptions"] == {
        "requestedFrequencyHz": 2_000_000,
        "configuredFrequencyHz": 2_000_000,
        "connectionPolicy": NORMAL_CONNECTION_POLICY,
        "preProgramReset": "sysresetreq",
        "preProgramHaltRequired": True,
        "automaticRetry": False,
    }
    assert result.details["postFlash"] == {
        "targetState": "unknown",
        "runVerified": False,
    }
    assert "recoverySuggestion" not in result.details
    assert result.data["importId"] == import_id
    assert list((data_root / "projects").glob("*/flash-receipts/*.json"))


def test_imported_omitted_frequency_keeps_default(tmp_path: Path) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path
    )
    backend = _backend(admission)

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project, data_root, "session-a", "probe-a", import_id, source_sha, True
            ),
            _seams=_imported_seams(backend),
        )
    )

    assert result.ok is True
    assert result.details["flashOptions"]["requestedFrequencyHz"] is None
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 1_000_000


def test_imported_failure_has_flash_options_but_no_recovery_suggestion(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"readback-failure"
    )
    backend = _backend(admission, mutate=b"\x00")

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                import_id,
                source_sha,
                True,
                frequency_hz=3_000_000,
            ),
            _seams=_imported_seams(backend),
        )
    )

    assert result.ok is False
    assert result.code == "FIRMWARE_FLASH_VERIFY_FAILED"
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 3_000_000
    assert "recoverySuggestion" not in result.details
    assert list((data_root / "projects").glob("*/flash-receipts/*.json")) == []


# ---------------------------------------------------------------------------
# selected pre-program preparation policy
# ---------------------------------------------------------------------------


def test_managed_normal_reports_sysresetreq_preparation_policy(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")

    result = _flash(project, tmp_path / "data", seams=_seams(_Recorder()))

    options = _options(result)
    assert options["connectionPolicy"] == NORMAL_CONNECTION_POLICY
    assert options["preProgramReset"] == "sysresetreq"
    assert options["preProgramHaltRequired"] is True


def test_managed_recovery_reports_under_reset_connect_policy(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")

    result = _flash(
        project, tmp_path / "data", recovery=True, seams=_seams(_Recorder())
    )

    options = _options(result)
    assert options["connectionPolicy"] == UNDER_RESET_RECOVERY_CONNECTION_POLICY
    assert options["preProgramReset"] == "under-reset-connect"
    assert options["preProgramHaltRequired"] is True


def test_imported_reports_sysresetreq_policy_and_never_under_reset(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path
    )

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project, data_root, "session-a", "probe-a", import_id, source_sha, True
            ),
            _seams=_imported_seams(_backend(admission)),
        )
    )

    assert result.ok is True
    options = result.details["flashOptions"]
    assert options["connectionPolicy"] == NORMAL_CONNECTION_POLICY
    assert options["preProgramReset"] == "sysresetreq"
    assert options["preProgramHaltRequired"] is True


def test_preparation_policy_is_reported_for_a_preparation_failure(
    tmp_path: Path,
) -> None:
    """Selected policy appears even when attach/reset never happened.

    A failure with no diagnostic and no backend effect still describes the
    configuration that was selected; it is never evidence the reset ran.
    """

    project = _project(tmp_path / "project")

    result = _flash(
        project,
        tmp_path / "data",
        seams=_seams(_Recorder(), operation=_failure_operation("PROBE_PROGRAM_FAILED")),
    )

    assert result.ok is False
    options = result.details["flashOptions"]
    assert options["preProgramReset"] == "sysresetreq"
    assert options["preProgramHaltRequired"] is True
    assert "preparationVerified" not in options
    assert "resetVerified" not in options


@pytest.mark.parametrize(
    "code", ["FIRMWARE_FLASH_VERIFY_FAILED", "PROBE_PROGRAM_FAILED"]
)
def test_imported_explicit_frequency_selects_worker_config(
    tmp_path: Path, code: str
) -> None:
    project, data_root, _payload, import_id, source_sha, _admission = _prepare_import(
        tmp_path
    )
    recorder = _Recorder()
    captured: list[object] = []

    async def refused(
        _request: object, _client: object
    ) -> OperationResult[object]:
        return OperationResult.failure(
            "stm32_flash_imported",
            code,
            "simulated imported failure",
            {},
        )

    seams = replace(
        _capturing_worker_seams(recorder, captured), flash_imported=refused
    )
    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                import_id,
                source_sha,
                True,
                frequency_hz=5_000_000,
            ),
            _seams=seams,
        )
    )

    assert result.ok is False
    assert result.code == code
    assert len(captured) == 1
    assert captured[0].frequency_hz == 5_000_000
    assert captured[0].connection_policy == NORMAL_CONNECTION_POLICY
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 5_000_000
    assert "recoverySuggestion" not in result.details


def test_imported_invalid_frequency_fails_before_admission_and_effects(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                "a" * 64,
                "b" * 64,
                True,
                frequency_hz="4000000",
            ),
            _seams=HardwareWorkflowSeams(),
        )
    )

    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "frequencyHz"
    assert result.details["rule"] == "type"
    assert "flashOptions" not in result.details
    assert not data_root.exists()


def test_imported_frequency_conflict_guidance_is_route_neutral(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    recorder = _Recorder()
    seams = replace(
        _seams(recorder),
        worker_config=ProbeWorkerConfig().for_under_reset_recovery(),
    )

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                "a" * 64,
                "b" * 64,
                True,
                frequency_hz=4_000_000,
            ),
            _seams=seams,
        )
    )

    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "frequencyHz"
    assert result.details["rule"] == "conflict"
    guidance = result.details["guidance"].lower()
    assert "under-reset" not in guidance
    assert "recovery" not in guidance
    assert recorder.events == []
    assert recorder.configs == []
    assert not data_root.exists()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("integrity", "FIRMWARE_INPUT_CHANGED"),
        ("receipt", "EXTERNAL_FLASH_RECEIPT_FAILED"),
    ],
)
def test_imported_post_cleanup_failures_keep_flash_options_and_no_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path
    )
    backend = _backend(admission)
    if failure == "integrity":
        monkeypatch.setattr(hardware_mod, "admission_matches", lambda *_args: False)
    else:

        def refuse_receipt(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("receipt commit failure")

        monkeypatch.setattr(hardware_mod, "write_flash_receipt", refuse_receipt)

    result = _run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project,
                data_root,
                "session-a",
                "probe-a",
                import_id,
                source_sha,
                True,
                frequency_hz=6_000_000,
            ),
            _seams=_imported_seams(backend),
        )
    )

    assert result.ok is False
    assert result.code == expected_code
    assert result.details["flashOptions"]["configuredFrequencyHz"] == 6_000_000
    assert result.details["flashOptions"]["automaticRetry"] is False
    assert "recoverySuggestion" not in result.details
    assert list((data_root / "projects").glob("*/flash-receipts/*.json")) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_flash_cli_forwards_decimal_frequency(monkeypatch, tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        calls.append(request)
        return OperationResult.success("stm32_flash", {})

    monkeypatch.setattr("stm32_toolkit.cli.flash_workflow", accepted)
    assert main(
        [
            "flash",
            *_context(project, tmp_path / "data"),
            *_pins(),
            "--authorized",
            "--frequency",
            "4000000",
        ]
    ) == 0

    assert capsys.readouterr().err == ""
    assert type(calls[0]) is FlashWorkflowRequest
    assert calls[0].frequency_hz == 4_000_000


def test_flash_imported_cli_forwards_frequency(monkeypatch, tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        calls.append(request)
        return OperationResult.success("stm32_flash_imported", {})

    monkeypatch.setattr("stm32_toolkit.cli.flash_imported_workflow", accepted)
    assert main(
        [
            "flash-imported",
            *_context(project, tmp_path / "data"),
            "--probe",
            "probe-a",
            "--import-id",
            "a" * 64,
            "--expected-sha256",
            "b" * 64,
            "--authorized",
            "--frequency",
            "3000000",
        ]
    ) == 0

    assert capsys.readouterr().err == ""
    assert type(calls[0]) is FlashImportedWorkflowRequest
    assert calls[0].frequency_hz == 3_000_000


def _frequency_argv(
    route: str,
    project: Path,
    data_root: Path,
    values: list[str],
) -> list[str]:
    argv = [route, *_context(project, data_root)]
    if route == "flash":
        argv += [*_pins(), "--authorized"]
    else:
        argv += [
            "--probe", "probe-a",
            "--import-id", "a" * 64,
            "--expected-sha256", "b" * 64,
            "--authorized",
        ]
    for value in values:
        argv += ["--frequency", value]
    return argv


_INVALID_FREQUENCIES = [
    "100000.5",
    "1e6",
    "99999",
    "50000001",
    "-1",
    "0x100000",
    "1_000_000",
    "+100000",
    " 100000",
    pytest.param("9" * 5000, id="oversized-decimal"),
]


@pytest.mark.parametrize("route", ["flash", "flash-imported"])
@pytest.mark.parametrize("value", _INVALID_FREQUENCIES)
def test_cli_routes_reject_invalid_frequency_before_any_workflow(
    monkeypatch, tmp_path: Path, capsys, route: str, value: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    calls: list[object] = []

    async def unexpected(request: object) -> OperationResult[object]:
        calls.append(request)
        return OperationResult.success(route, {})

    monkeypatch.setattr("stm32_toolkit.cli.flash_workflow", unexpected)
    monkeypatch.setattr("stm32_toolkit.cli.flash_imported_workflow", unexpected)

    exit_code = main(_frequency_argv(route, project, data_root, [value]))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "invalid arguments" in captured.err
    assert calls == []
    assert not data_root.exists()


@pytest.mark.parametrize("route", ["flash", "flash-imported"])
def test_cli_routes_reject_duplicate_frequency_before_any_workflow(
    monkeypatch, tmp_path: Path, capsys, route: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    calls: list[object] = []

    async def unexpected(request: object) -> OperationResult[object]:
        calls.append(request)
        return OperationResult.success(route, {})

    monkeypatch.setattr("stm32_toolkit.cli.flash_workflow", unexpected)
    monkeypatch.setattr("stm32_toolkit.cli.flash_imported_workflow", unexpected)

    exit_code = main(
        _frequency_argv(route, project, data_root, ["1000000", "2000000"])
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "invalid arguments" in captured.err
    assert calls == []
    assert not data_root.exists()


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


def _integer_constraints(
    root: dict[str, object], schema: dict[str, object]
) -> dict[str, object]:
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        schema = root["$defs"][reference.rsplit("/", 1)[-1]]  # type: ignore[index]
    candidates = schema.get("anyOf")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                resolved = _integer_constraints(root, candidate)
                if resolved.get("type") == "integer":
                    return resolved
    return schema


def test_mcp_schemas_expose_bounded_optional_frequency(tmp_path: Path) -> None:
    schemas = _schemas(tmp_path)
    for name in ("stm32_flash", "stm32_flash_imported"):
        root = schemas[name]
        frequency = root["properties"]["frequencyHz"]
        assert frequency.get("default") is None
        constraints = _integer_constraints(root, frequency)
        assert constraints["type"] == "integer"
        assert constraints["minimum"] == 100_000
        assert constraints["maximum"] == 50_000_000


def test_registered_flash_forwards_frequency_and_null_default(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = _runtime(tmp_path)
    received: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        received.append(request)
        return OperationResult.success("stm32_flash", {})

    monkeypatch.setattr(mcp_mod, "flash_workflow", accepted)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)

    explicit = asyncio.run(
        server.call_tool(
            "stm32_flash",
            {
                "probeId": "probe-a",
                "expectedBuildId": "a" * 64,
                "expectedElfSha256": "b" * 64,
                "authorized": True,
                "frequencyHz": 4_000_000,
            },
        )
    )
    assert explicit[1]["ok"] is True
    omitted = asyncio.run(
        server.call_tool(
            "stm32_flash",
            {
                "probeId": "probe-a",
                "expectedBuildId": "a" * 64,
                "expectedElfSha256": "b" * 64,
                "authorized": True,
            },
        )
    )
    assert omitted[1]["ok"] is True
    assert [request.frequency_hz for request in received] == [4_000_000, None]


_MCP_FREQUENCY_REQUESTS = [
    (
        "stm32_flash",
        "flash_workflow",
        {
            "probeId": "probe-a",
            "expectedBuildId": "a" * 64,
            "expectedElfSha256": "b" * 64,
            "authorized": True,
        },
    ),
    (
        "stm32_flash_imported",
        "flash_imported_workflow",
        {
            "probeId": "probe-a",
            "importId": "a" * 64,
            "expectedSha256": "b" * 64,
            "authorized": True,
        },
    ),
]


@pytest.mark.parametrize(
    ("tool_name", "workflow_name", "arguments"), _MCP_FREQUENCY_REQUESTS
)
@pytest.mark.parametrize(
    "value", [True, False, 4_000_000.0, "4000000", 99_999, 50_000_001]
)
def test_registered_flash_tools_reject_non_integer_or_out_of_range_frequency(
    monkeypatch,
    tmp_path: Path,
    tool_name: str,
    workflow_name: str,
    arguments: dict[str, object],
    value: object,
) -> None:
    runtime = _runtime(tmp_path)
    calls = 0

    async def forbidden(_request: object) -> OperationResult[object]:
        nonlocal calls
        calls += 1
        return OperationResult.success(tool_name, {})

    monkeypatch.setattr(mcp_mod, workflow_name, forbidden)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                tool_name, {**arguments, "frequencyHz": value}
            )
        )
    assert calls == 0


def test_root_rejection_precedes_frequency_workflow(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[other]])
    context = SimpleNamespace(session=session)
    calls = 0

    async def forbidden(_request: object) -> OperationResult[object]:
        nonlocal calls
        calls += 1
        return OperationResult.success("stm32_flash", {})

    monkeypatch.setattr(mcp_mod, "flash_workflow", forbidden)
    result = asyncio.run(
        mcp_mod.tool_flash_for_request(
            runtime,
            context,
            "probe-a",
            "a" * 64,
            "b" * 64,
            True,
            False,
            frequency_hz=4_000_000,
        )
    )

    assert result["ok"] is False
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert calls == 0
    assert session.list_roots_calls == 1


def test_registered_imported_flash_forwards_frequency(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = _runtime(tmp_path)
    received: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        received.append(request)
        return OperationResult.success("stm32_flash_imported", {})

    monkeypatch.setattr(mcp_mod, "flash_imported_workflow", accepted)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    _content, result = asyncio.run(
        server.call_tool(
            "stm32_flash_imported",
            {
                "probeId": "probe-a",
                "importId": "a" * 64,
                "expectedSha256": "b" * 64,
                "authorized": True,
                "frequencyHz": 3_000_000,
            },
        )
    )

    assert result["ok"] is True
    assert received[0].frequency_hz == 3_000_000
