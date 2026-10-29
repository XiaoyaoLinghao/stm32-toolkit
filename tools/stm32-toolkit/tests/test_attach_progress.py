from __future__ import annotations

import asyncio
import json
import threading
import time
from functools import partial
from pathlib import Path
from types import MappingProxyType

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.probe.attach_diagnostics import (
    append_attach_progress,
    append_cleanup,
    append_late_attach,
    attach_details,
    extract_attach_diagnostic,
    legacy_stage_matches_attach_diagnostic,
    make_attach_diagnostic,
    make_cleanup_entry,
    make_primary,
    validate_attach_diagnostic,
)
from stm32_toolkit.probe.attach_progress import (
    MAX_PROGRESS_ELAPSED_MS,
    PROGRESS_CLOCK,
    PROGRESS_STAGES,
    PROGRESS_VERSION,
    make_attach_progress,
    validate_attach_progress,
)
from stm32_toolkit.probe.backend import ProbeAttachmentEvidence, ProbeBackendError
from stm32_toolkit.probe.model import OperationLevel, ProbeRequest, ProbeResponse
from stm32_toolkit.probe.protocol import encode_response
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend
from stm32_toolkit.probe.worker import ProbeBackendWorker, ProbeWorkerError
from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe
from test_probe_service import make_service, run


_HALT_STAGES = (
    "worker-dispatch",
    "driver-acquire",
    "probe-enumeration",
    "prior-attachment-close",
    "session-create",
    "target-resolve-before-open",
    "session-open",
    "target-resolve-after-open",
    "target-identity",
    "halt-verify",
)
_RESUME_STAGES = _HALT_STAGES[:-1] + ("resume", "resume-verify")
_BACKEND_STAGES = (
    "driver-acquire",
    "probe-enumeration",
    "prior-attachment-close",
    "session-create",
    "target-resolve-before-open",
    "session-open",
    "target-resolve-after-open",
    "target-identity",
    "resume",
    "resume-verify",
)


def _snapshot(stages: tuple[str, ...], elapsed_ms: int = 1000) -> dict[str, object]:
    events = [
        {
            "stage": stage,
            "elapsedMs": 0 if index == 0 else min(index, elapsed_ms),
        }
        for index, stage in enumerate(stages)
    ]
    return make_attach_progress(events, elapsed_ms)


def _legacy_diagnostic() -> dict[str, object]:
    return {
        "version": 1,
        "primary": make_primary("session-open", "unknown", "UNTYPED"),
        "lateAttach": None,
        "cleanup": [],
        "lastVerifiedTargetState": None,
    }


def _late_payload() -> dict[str, object]:
    late = make_attach_diagnostic(make_primary("session-open", "unknown", "UNTYPED"))
    return {
        "primary": late["primary"],
        "cleanup": late["cleanup"],
        "lastVerifiedTargetState": late["lastVerifiedTargetState"],
    }


def _hostile_progress_values() -> list[object]:
    valid = _snapshot(("worker-dispatch", "driver-acquire"))
    return [
        {**valid, "extra": True},
        {key: value for key, value in valid.items() if key != "clock"},
        {**valid, "version": 2},
        {**valid, "version": True},
        {**valid, "version": "1"},
        {**valid, "clock": "worker-receipt"},
        {**valid, "clock": None},
        {**valid, "elapsedMs": True},
        {**valid, "elapsedMs": -1},
        {**valid, "elapsedMs": MAX_PROGRESS_ELAPSED_MS + 1},
        {**valid, "elapsedMs": 1.5},
        {**valid, "elapsedMs": float("nan")},
        {**valid, "elapsedMs": "1"},
        {**valid, "events": []},
        {**valid, "events": None},
        {**valid, "events": tuple(valid["events"])},
        {**valid, "events": [{"stage": "driver-acquire", "elapsedMs": 1}]},
        {**valid, "events": [{"stage": "unknown", "elapsedMs": 0}]},
        {**valid, "events": [{"stage": 7, "elapsedMs": 0}]},
        {**valid, "events": [{"stage": "worker-dispatch", "elapsedMs": 5}]},
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0, "extra": 1}
            ],
        },
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "driver-acquire", "elapsedMs": True},
            ],
        },
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "driver-acquire", "elapsedMs": 5},
                {"stage": "probe-enumeration", "elapsedMs": 4},
            ],
        },
        {
            **valid,
            "elapsedMs": 1,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "driver-acquire", "elapsedMs": 2},
            ],
        },
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "driver-acquire", "elapsedMs": 1},
                {"stage": "driver-acquire", "elapsedMs": 2},
            ],
        },
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "session-open", "elapsedMs": 1},
                {"stage": "driver-acquire", "elapsedMs": 2},
            ],
        },
        {
            **valid,
            "elapsedMs": 50,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "halt-verify", "elapsedMs": 1},
                {"stage": "resume", "elapsedMs": 2},
            ],
        },
        {
            **valid,
            "events": [
                {"stage": "worker-dispatch", "elapsedMs": 0},
                {"stage": "resume-verify", "elapsedMs": 1},
            ],
        },
        {
            **valid,
            "events": [
                {"stage": stage, "elapsedMs": index}
                for index, stage in enumerate(
                    PROGRESS_STAGES + ("resume-verify",)
                )
            ],
        },
        {"events": valid["events"]},
        "private",
        None,
        [],
        7,
    ]


def test_progress_schema_accepts_only_closed_ordered_branches() -> None:
    halt = _snapshot(_HALT_STAGES)
    resume = _snapshot(_RESUME_STAGES)
    minimal = _snapshot(("worker-dispatch",))

    assert validate_attach_progress(halt) == halt
    assert validate_attach_progress(resume) == resume
    assert validate_attach_progress(minimal) == minimal
    assert halt["version"] == PROGRESS_VERSION
    assert halt["clock"] == PROGRESS_CLOCK
    assert halt["events"][0] == {"stage": "worker-dispatch", "elapsedMs": 0}

    # Detached copy: mutating the source never changes the validated result.
    source = _snapshot(_HALT_STAGES)
    copied = validate_attach_progress(source)
    assert copied is not None
    source["events"][1]["elapsedMs"] = 77
    source["elapsedMs"] = 5000
    assert copied["events"][1] == {"stage": "driver-acquire", "elapsedMs": 1}
    assert copied["elapsedMs"] == 1000

    with pytest.raises(ValueError):
        make_attach_progress([], 10)
    with pytest.raises(ValueError):
        make_attach_progress([{"stage": "private", "elapsedMs": 0}], 10)


@pytest.mark.parametrize("value", _hostile_progress_values())
def test_progress_schema_rejects_hostile_values(value: object) -> None:
    assert validate_attach_progress(value) is None


def test_attach_diagnostic_progress_is_optional_detached_and_worker_rejected() -> None:
    legacy = _legacy_diagnostic()
    validated = validate_attach_diagnostic(legacy)
    assert validated == legacy
    assert set(validated) == {
        "version", "primary", "lateAttach", "cleanup", "lastVerifiedTargetState"
    }

    progress = _snapshot(("worker-dispatch", "driver-acquire", "probe-enumeration"))
    diagnostic = make_attach_diagnostic(
        make_primary("service-attach-deadline", "timeout", "PROBE_TIMEOUT"),
        progress=progress,
    )
    assert set(diagnostic) == {
        "version", "primary", "lateAttach", "cleanup",
        "lastVerifiedTargetState", "progress",
    }
    assert diagnostic["progress"] == progress

    # Progress is parent-only: raw child diagnostics must never carry it.
    assert validate_attach_diagnostic(diagnostic, worker=True) is None

    hostile = {**diagnostic, "progress": {"version": 1, "clock": "x"}}
    assert validate_attach_diagnostic(hostile) is None
    assert append_attach_progress(diagnostic, hostile) == diagnostic
    assert append_attach_progress(legacy, None) == legacy


def test_progress_survives_cleanup_late_merge_and_public_extraction() -> None:
    progress = _snapshot(
        ("worker-dispatch", "driver-acquire", "session-create", "session-open")
    )
    deadline = make_attach_diagnostic(
        make_primary("service-attach-deadline", "timeout", "PROBE_TIMEOUT"),
        progress=progress,
    )
    merged = append_cleanup(
        deadline, (make_cleanup_entry("service-terminal-wait", "succeeded"),)
    )
    assert merged["progress"] == progress
    merged = append_late_attach(merged, _late_payload())
    assert merged["progress"] == progress
    assert merged["lateAttach"] is not None

    details = attach_details(merged)
    assert details["attachDiagnostic"]["progress"] == progress
    extracted = extract_attach_diagnostic(details)
    assert extracted == merged
    assert json.loads(json.dumps(extracted))["progress"] == progress

    frozen = MappingProxyType({
        "attachDiagnostic": MappingProxyType({
            "version": 1,
            "primary": MappingProxyType(dict(merged["primary"])),
            "lateAttach": None,
            "cleanup": tuple(
                MappingProxyType(dict(entry)) for entry in merged["cleanup"]
            ),
            "lastVerifiedTargetState": None,
            "progress": MappingProxyType({
                "version": 1,
                "clock": PROGRESS_CLOCK,
                "elapsedMs": progress["elapsedMs"],
                "events": tuple(
                    MappingProxyType(dict(entry)) for entry in progress["events"]
                ),
            }),
        })
    })
    assert extract_attach_diagnostic(frozen)["progress"] == progress

    response = ProbeResponse.failure(
        "request-1", "probe.attach", "PROBE_TIMEOUT", "timed out", details
    )
    encoded = encode_response(response)
    assert b'"progress"' in encoded
    assert json.loads(encoded)["details"]["attachDiagnostic"]["progress"] == progress


def test_legacy_projection_remains_exact_with_progress_present() -> None:
    progress = _snapshot(("worker-dispatch", "session-open"))
    diagnostic = make_attach_diagnostic(
        make_primary("session-open", "unknown", "UNTYPED"), progress=progress
    )
    assert attach_details(diagnostic, legacy_stage="session-open") == {
        "stage": "session-open",
        "attachDiagnostic": diagnostic,
    }
    assert legacy_stage_matches_attach_diagnostic("session-open", diagnostic)


def test_backend_emits_ordered_resume_stages_without_extra_enumeration() -> None:
    stages: list[str] = []
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    backend = PyOCDBackend(driver, stage_callback=stages.append)

    evidence = backend.open_attach("probe-a", "stm32f407vg")

    assert evidence.core_count == 1
    assert stages == list(_BACKEND_STAGES)
    assert len(driver.created_sessions) == 1
    assert [call[0] for call in driver.target.calls].count("get_state") == 1
    assert [call[0] for call in driver.target.calls].count("resume") == 1


def test_backend_emits_halt_stage_without_resume_control() -> None:
    stages: list[str] = []
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    backend = PyOCDBackend(driver, stage_callback=stages.append)

    backend.open_attach("probe-a", "stm32f407vg", halt_on_connect=True)

    assert stages == [
        *_BACKEND_STAGES[:-2], "halt-verify",
    ]
    assert [call[0] for call in driver.target.calls].count("resume") == 0
    assert [call[0] for call in driver.target.calls].count("get_state") == 1


def test_backend_preserve_policy_emits_no_control_branch() -> None:
    stages: list[str] = []
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    backend = PyOCDBackend(
        driver,
        frequency_hz=100_000,
        connection_policy="observe-preserve",
        stage_callback=stages.append,
    )

    backend.open_attach("probe-a", "stm32f407vg")

    assert stages == [*_BACKEND_STAGES[:-2]]
    assert driver.target.calls == []


def test_backend_callback_failure_is_isolated_from_attach_and_errors() -> None:
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))

    def failing_callback(stage: str) -> None:
        raise RuntimeError(f"private transport failure for {stage}")

    backend = PyOCDBackend(driver, stage_callback=failing_callback)
    evidence = backend.open_attach("probe-a", "stm32f407vg")
    assert evidence.probe_id == "probe-a"
    assert len(driver.created_sessions) == 1

    failing_driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),))
    failing_driver.create_error = RuntimeError("private create failure")
    failing_backend = PyOCDBackend(failing_driver, stage_callback=failing_callback)
    with pytest.raises(ProbeBackendError) as caught:
        failing_backend.open_attach("probe-a", "stm32f407vg")
    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert caught.value.message == "Debug probe attach failed"
    diagnostic = caught.value.details["attachDiagnostic"]
    assert validate_attach_diagnostic(diagnostic) == diagnostic
    assert diagnostic["primary"]["stage"] == "session-create"
    assert "private" not in str(caught.value)
    assert "private" not in str(caught.value.details)

    with pytest.raises(ValueError):
        PyOCDBackend(driver, stage_callback=object())


class _HookStallingBackend:
    """Spawn-safe deterministic backend emitting private stage frames."""

    def __init__(self, mode: str, marker: str) -> None:
        self.mode = mode
        self.marker = Path(marker)
        self._callback = None

    def _set_attach_stage_callback(self, callback: object) -> None:
        self._callback = callback

    def _record(self, event: str) -> None:
        with self.marker.open("a", encoding="utf-8") as stream:
            stream.write(event + "\n")

    def _emit(self, stage: str) -> None:
        self._record(f"stage:{stage}")
        if self._callback is not None:
            self._callback(stage)

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        self._record("attach-entered")
        for stage in (
            "driver-acquire",
            "probe-enumeration",
            "session-create",
            "session-open",
        ):
            self._emit(stage)
            if self.mode == "slow":
                time.sleep(0.02)
        if self.mode == "stall":
            time.sleep(5.0)
            self._record("late-attach-returned")
        self._record("attach-returned")
        return ProbeAttachmentEvidence(probe_id, target, target, 1)

    def resume(self) -> None:
        self._record("resume")

    def target_state(self):
        return {"state": "running", "reason": "requested"}

    def flash_elf(self, image: bytes):
        self._record("program")
        raise AssertionError("no programming is authorized in this slice")

    def close(self) -> None:
        self._record("close")


def _hook_factory(mode: str, marker: str) -> _HookStallingBackend:
    return _HookStallingBackend(mode, marker)


class _ProgressDetailsBackend:
    """Spawn-safe seam returning a raw child diagnostic containing progress."""

    def __init__(self, details: object) -> None:
        self.details = details

    def open_attach(self, probe_id, target, *, halt_on_connect=False):
        error = ProbeBackendError("PROBE_ATTACH_FAILED", "private detail", {})
        error.details = self.details  # type: ignore[assignment]
        raise error

    def close(self) -> None:
        return None


def _progress_details_factory(details: object) -> _ProgressDetailsBackend:
    return _ProgressDetailsBackend(details)


def _frame(stage: object, *, request_id: int = 1) -> dict[str, object]:
    from stm32_toolkit.probe import worker as worker_module

    return {
        "version": worker_module._VERSION,
        "progress": stage,
        "id": request_id,
    }


def _wait_for_marker(path: Path, needle: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and needle in path.read_text(encoding="utf-8"):
            return
        time.sleep(0.01)
    raise AssertionError(f"{needle!r} was not observed in {path}")


def test_worker_records_worker_dispatch_only_after_successful_send(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "fast-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "fast", str(marker))
    )
    try:
        evidence = worker.open_attach_with_progress(
            "probe-a", "stm32f407vg", request_token="token-a"
        )
        assert evidence.core_count == 1
        snapshot = worker.attach_progress_snapshot("token-a")
        assert validate_attach_progress(snapshot) == snapshot
        assert [entry["stage"] for entry in snapshot["events"]] == [
            "worker-dispatch",
            "driver-acquire",
            "probe-enumeration",
            "session-create",
            "session-open",
        ]
        assert snapshot["events"][0]["elapsedMs"] == 0
        assert snapshot["clock"] == "parent-receipt"
        assert snapshot["elapsedMs"] >= snapshot["events"][-1]["elapsedMs"]
        # The public attach entry points keep their original signatures/results.
        assert worker.open_attach("probe-a", "stm32f407vg").core_count == 1
        assert worker.attach_progress_snapshot("token-a") is None
    finally:
        worker.close()


@pytest.mark.parametrize(
    "frames",
    [
        [_frame("driver-acquire", request_id=999)],
        [_frame("driver-acquire"), _frame("driver-acquire")],
        [_frame("session-create"), _frame("driver-acquire")],
        [_frame("private-stage")],
        [_frame(7)],
        [{**_frame("driver-acquire"), "secret": "private"}],
        [_frame("halt-verify"), _frame("resume")],
        [_frame("resume-verify")],
        [
            _frame(stage)
            for stage in PROGRESS_STAGES[1:]
        ]
        + [_frame("resume-verify")],
    ],
)
def test_worker_ipc_rejects_malformed_or_out_of_order_progress_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frames: list[dict[str, object]]
) -> None:
    marker = tmp_path / "frame-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "fast", str(marker))
    )
    replies = iter(frames)
    monkeypatch.setattr(worker, "_receive", lambda _deadline: next(replies))
    try:
        with pytest.raises(ProbeWorkerError) as caught:
            worker.open_attach("probe-a", "stm32f407vg")
        assert caught.value.code == "PROBE_BACKEND_ERROR"
        assert caught.value.message == "Probe worker response is invalid"
        assert caught.value.details == {}
        assert not worker.is_alive
    finally:
        if worker.is_alive:
            worker.close()


def test_worker_rejects_progress_frames_outside_open_attach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "nonattach-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "fast", str(marker))
    )
    monkeypatch.setattr(
        worker, "_receive", lambda _deadline: _frame("driver-acquire")
    )
    try:
        with pytest.raises(ProbeWorkerError) as caught:
            worker.target_identity()
        assert caught.value.code == "PROBE_BACKEND_ERROR"
        assert caught.value.message == "Probe worker response is invalid"
        assert not worker.is_alive
    finally:
        if worker.is_alive:
            worker.close()


def test_worker_progress_frames_never_extend_the_absolute_deadline(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "deadline-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "stall", str(marker))
    )
    started = time.monotonic()
    try:
        with pytest.raises(ProbeWorkerError) as caught:
            worker.call(
                "open_attach",
                "probe-a",
                "stm32f407vg",
                deadline=time.monotonic() + 0.3,
            )
        assert caught.value.code == "PROBE_TIMEOUT"
        assert time.monotonic() - started < 1.5
        assert not worker.is_alive
    finally:
        if worker.is_alive:
            worker.close()


def test_worker_snapshot_is_token_scoped_detached_and_reset(tmp_path: Path) -> None:
    marker = tmp_path / "token-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "fast", str(marker))
    )
    try:
        worker.open_attach_with_progress(
            "probe-a", "stm32f407vg", request_token="token-a"
        )
        first = worker.attach_progress_snapshot("token-a")
        assert first is not None
        first["events"].append({"stage": "resume", "elapsedMs": 9})
        first["events"][0]["elapsedMs"] = 99
        again = worker.attach_progress_snapshot("token-a")
        assert again is not None
        assert [entry["stage"] for entry in again["events"]] == [
            "worker-dispatch",
            "driver-acquire",
            "probe-enumeration",
            "session-create",
            "session-open",
        ]
        assert again["events"][0]["elapsedMs"] == 0
        assert worker.attach_progress_snapshot("token-b") is None
        assert worker.attach_progress_snapshot("") is None
        assert worker.attach_progress_snapshot(7) is None  # type: ignore[arg-type]

        worker.open_attach_with_progress(
            "probe-a", "stm32f407vg", request_token="token-b"
        )
        assert worker.attach_progress_snapshot("token-a") is None
        second = worker.attach_progress_snapshot("token-b")
        assert second is not None
        assert validate_attach_progress(second) == second
        with pytest.raises(ProbeWorkerError):
            worker.open_attach_with_progress(
                "probe-a", "stm32f407vg", request_token=""
            )
    finally:
        worker.close()


def test_worker_snapshot_survives_owned_abort_without_late_actions(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "abort-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "stall", str(marker))
    )
    failures: list[BaseException] = []

    def invoke() -> None:
        try:
            worker.open_attach_with_progress(
                "probe-a", "stm32f407vg", request_token="token-abort"
            )
        except BaseException as error:
            failures.append(error)

    caller = threading.Thread(target=invoke)
    caller.start()
    try:
        _wait_for_marker(marker, "stage:session-open")
        time.sleep(0.1)
        live_snapshot = worker.attach_progress_snapshot("token-abort")
        assert live_snapshot is not None
        assert validate_attach_progress(live_snapshot) == live_snapshot

        worker.abort_owned_execution()
        caller.join(2.0)
        assert not caller.is_alive()
        assert len(failures) == 1
        # A parent-pipe close can surface as EOF/OSError exactly as before; the
        # scheduler guarantee is that the call has terminated.
        assert isinstance(failures[0], (ProbeWorkerError, EOFError, OSError))
        assert not worker.is_alive

        snapshot = worker.attach_progress_snapshot("token-abort")
        assert snapshot is not None
        assert validate_attach_progress(snapshot) == snapshot
        assert [entry["stage"] for entry in snapshot["events"]] == [
            "worker-dispatch",
            "driver-acquire",
            "probe-enumeration",
            "session-create",
            "session-open",
        ]
        assert worker.attach_progress_snapshot("token-other") is None

        time.sleep(0.2)
        events = marker.read_text(encoding="utf-8").splitlines()
        assert "attach-entered" in events
        assert "late-attach-returned" not in events
        assert "attach-returned" not in events
        assert "program" not in events
        assert "resume" not in events
    finally:
        if caller.is_alive:
            caller.join(1.0)
        if worker.is_alive:
            worker.abort_owned_execution()


def test_child_attach_error_admission_rejects_parent_only_progress() -> None:
    from stm32_toolkit.probe import worker as worker_module

    progress = _snapshot(("worker-dispatch", "driver-acquire"))
    diagnostic = make_attach_diagnostic(
        make_primary("session-open", "unknown", "UNTYPED"), progress=progress
    )
    details = {"attachDiagnostic": diagnostic}
    assert worker_module._safe_attach_error_details(
        "PROBE_ATTACH_FAILED", details
    ) is None

    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_progress_details_factory, details)
    )
    try:
        with pytest.raises(ProbeWorkerError) as caught:
            worker.open_attach("probe-a", "stm32f407vg")
        assert caught.value.code == "PROBE_ATTACH_FAILED"
        assert caught.value.details == {}
        assert not worker.is_alive
    finally:
        if worker.is_alive:
            worker.close()


def _observe_attach_request(*, timeout_ms: int) -> ProbeRequest:
    return ProbeRequest(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        request_id="request-attach-progress",
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-test",
        operation_level=OperationLevel.OBSERVE,
        operation="probe.attach",
        timeout_ms=timeout_ms,
        data={"probeId": "probe-a", "target": "stm32f407vg"},
    )


def test_service_timeout_retains_progress_after_abort_without_late_program(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "service-events.txt"
    worker: ProbeBackendWorker | None = None
    service = None

    async def scenario() -> None:
        nonlocal worker, service
        try:
            worker = ProbeBackendWorker(
                _test_backend_factory=partial(_hook_factory, "stall", str(marker))
            )
            service = make_service(
                tmp_path / "service", level=OperationLevel.OBSERVE, backend=worker
            )
            with pytest.raises(ProbeBackendError) as caught:
                await service._run_backend(
                    _observe_attach_request(timeout_ms=1000)
                )
            assert caught.value.code == "PROBE_CLOSE_FAILED"
            assert caught.value.message == "Probe attach cleanup failed"
            diagnostic = caught.value.details["attachDiagnostic"]
            assert validate_attach_diagnostic(diagnostic) == diagnostic
            assert diagnostic["primary"]["stage"] == "service-attach-deadline"
            assert [entry["stage"] for entry in diagnostic["cleanup"]] == [
                "service-terminal-wait", "service-worker-abort"
            ]
            progress = diagnostic["progress"]
            assert validate_attach_progress(progress) == progress
            assert [entry["stage"] for entry in progress["events"]] == [
                "worker-dispatch",
                "driver-acquire",
                "probe-enumeration",
                "session-create",
                "session-open",
            ]
            assert progress["events"][0]["elapsedMs"] == 0
            assert progress["clock"] == "parent-receipt"
            assert progress["elapsedMs"] >= progress["events"][-1]["elapsedMs"]
            assert "token" not in json.dumps(progress).casefold()
            assert set(progress) == {"version", "clock", "elapsedMs", "events"}
            assert all(
                set(entry) == {"stage", "elapsedMs"}
                for entry in progress["events"]
            )
            assert extract_attach_diagnostic(caught.value.details) == diagnostic
            assert worker.is_alive is False

            await asyncio.sleep(0.2)
            events = marker.read_text(encoding="utf-8").splitlines()
            assert "attach-entered" in events
            assert "late-attach-returned" not in events
            assert "attach-returned" not in events
            assert "program" not in events
            assert "resume" not in events
        finally:
            if worker is not None and worker.is_alive:
                await asyncio.to_thread(worker.abort_owned_execution)
            if service is not None:
                pending = tuple(service._backend_tasks)
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

    run(scenario())


def test_service_success_envelope_is_unchanged_with_frames_present(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "success-events.txt"
    worker = ProbeBackendWorker(
        _test_backend_factory=partial(_hook_factory, "fast", str(marker))
    )
    service = make_service(
        tmp_path / "success-service",
        level=OperationLevel.OBSERVE,
        backend=worker,
    )

    async def scenario() -> None:
        payload = await service._run_backend(
            _observe_attach_request(timeout_ms=5000)
        )
        assert payload == {
            "probeId": "probe-a",
            "requestedTarget": "stm32f407vg",
            "resolvedPartNumber": "stm32f407vg",
            "coreCount": 1,
        }
        assert "progress" not in payload

    try:
        run(scenario())
    finally:
        if worker.is_alive:
            worker.close()
