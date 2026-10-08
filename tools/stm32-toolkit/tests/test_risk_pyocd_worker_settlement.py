from __future__ import annotations

import hashlib
import json
from functools import partial
from pathlib import Path

import pytest
from coverage import Coverage
from fakes.fake_pyocd import FakePyOCDDriver, FakePyOCDProbe, FakePyOCDTarget
from stm32_toolkit.probe.backend import (
    FlashBackendReport,
    ProbeAttachmentEvidence,
    ProbeBackendError,
)
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend
from stm32_toolkit.probe.worker import ProbeBackendWorker
from test_probe_supervisor import make_supervisor, run

_PROBE_ID = "probe-a"
_TARGET = "stm32f407vg"
_FIXTURE_BYTES = b"offline firmware fixture bytes"
_FIXTURE_SHA256 = hashlib.sha256(_FIXTURE_BYTES).hexdigest()

_PREEXISTING_PROGRAM_DIAGNOSTIC = {
    "schemaVersion": 1,
    "stage": "program-call",
    "exceptions": [
        {
            "type": "builtins.OSError",
            "message": "program failed",
            "errno": 5,
            "winerror": 5,
            "address": None,
            "resultCode": None,
        }
    ],
}


class _ConfiguredFakePyOCDDriver(FakePyOCDDriver):
    """An external PyOCD driver double configured inside the spawned worker."""

    def __init__(self, mode: str) -> None:
        if mode == "attach-session-open":
            super().__init__(
                (FakePyOCDProbe(_PROBE_ID),),
                target=None,
            )
            self.session_open_error = RuntimeError("session open failed")
        else:
            super().__init__(
                (FakePyOCDProbe(_PROBE_ID),),
                target=FakePyOCDTarget(),
            )
        self.mode = mode

    def program_file(
        self, session: object, image: bytes, *, options: dict[str, object]
    ) -> None:
        if self.mode == "program-preexisting-diagnostic":
            raise ProbeBackendError(
                "PROBE_PROGRAM_FAILED",
                "program failure",
                {"programDiagnostic": _PREEXISTING_PROGRAM_DIAGNOSTIC},
            )
        if self.mode == "program-typed-cause":
            try:
                raise OSError("program failed")
            except OSError as cause:
                raise ProbeBackendError(
                    "PROBE_PROGRAM_FAILED", "typed program failure"
                ) from cause
        if self.mode == "program-typed-without-cause":
            raise ProbeBackendError("PROBE_PROGRAM_FAILED", "typed program failure")
        super().program_file(session, image, options=options)


class _CoverageFlushingPyOCDBackend(PyOCDBackend):
    """Flush the active child collector before the worker reports an outcome."""

    @staticmethod
    def _flush_active_coverage() -> None:
        collector = Coverage.current()
        if collector is not None:
            collector.save()

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        try:
            return super().open_attach(
                probe_id, target, halt_on_connect=halt_on_connect
            )
        finally:
            self._flush_active_coverage()

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        try:
            return super().flash_elf(image)
        finally:
            self._flush_active_coverage()


def _make_pyocd_backend(mode: str) -> PyOCDBackend:
    return _CoverageFlushingPyOCDBackend(
        _ConfiguredFakePyOCDDriver(mode),
        target_profile={},
    )


def _make_pyocd_worker(mode: str) -> ProbeBackendWorker:
    return ProbeBackendWorker(
        _test_backend_factory=partial(_make_pyocd_backend, mode),
    )


class _ParentWorkerFactory:
    """Create parent-visible worker proxies without inspecting child state."""

    def __init__(self, mode: str, workers: list[ProbeBackendWorker]) -> None:
        self._mode = mode
        self._workers = workers

    def __call__(self) -> ProbeBackendWorker:
        worker = _make_pyocd_worker(self._mode)
        self._workers.append(worker)
        return worker


def _assert_released(data_root: Path, endpoint) -> None:
    assert not endpoint.record_path.exists()
    record = json.loads(
        ProbeLeaseManager(data_root).record_path(_PROBE_ID).read_text(encoding="utf-8")
    )
    assert record["state"] == "released"


def _assert_terminal_worker(worker: ProbeBackendWorker, pid: int) -> None:
    assert pid > 0
    assert worker.is_terminal is True
    assert worker.is_alive is False


def test_pyocd_worker_attach_failure_settles_and_recovers_with_fresh_worker(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        failed_workers: list[ProbeBackendWorker] = []
        failed_supervisor = make_supervisor(
            data_root,
            _ParentWorkerFactory("attach-session-open", failed_workers),
            operation_level=OperationLevel.OBSERVE,
        )
        failed_endpoint = await failed_supervisor.start()
        failed_client = ProbeClient(failed_endpoint)
        try:
            failed_pid = failed_workers[0].owned_pid
            with pytest.raises(ProbeClientError) as caught:
                await failed_client.attach(_PROBE_ID, _TARGET)

            assert caught.value.code == "PROBE_ATTACH_FAILED"
            assert caught.value.message == "Probe worker operation failed"
            assert caught.value.details == {
                "stage": "session-open",
                "attachDiagnostic": {
                    "version": 1,
                    "primary": {
                        "stage": "session-open",
                        "reason": "unknown",
                        "sourceCode": "UNTYPED",
                    },
                    "lateAttach": None,
                    "cleanup": [
                        {"stage": "session-close", "outcome": "succeeded"},
                        {
                            "stage": "probe-open-check-before-close",
                            "outcome": "succeeded",
                        },
                        {"stage": "probe-close", "outcome": "succeeded"},
                        {
                            "stage": "probe-open-check-after-close",
                            "outcome": "succeeded",
                        },
                        {"stage": "worker-parent-abort", "outcome": "succeeded"},
                    ],
                    "lastVerifiedTargetState": None,
                },
            }
            _assert_terminal_worker(failed_workers[0], failed_pid)
        finally:
            await failed_client.close()
            await failed_supervisor.stop()

        assert failed_supervisor.endpoint is None
        _assert_released(data_root, failed_endpoint)

        recovered_workers: list[ProbeBackendWorker] = []
        recovered_supervisor = make_supervisor(
            data_root,
            _ParentWorkerFactory("healthy", recovered_workers),
            operation_level=OperationLevel.OBSERVE,
        )
        recovered_endpoint = await recovered_supervisor.start()
        recovered_client = ProbeClient(recovered_endpoint)
        try:
            recovered_pid = recovered_workers[0].owned_pid
            attachment = await recovered_client.attach(_PROBE_ID, _TARGET)
            assert attachment.probe_id == _PROBE_ID
            assert attachment.requested_target == _TARGET
            assert attachment.resolved_part_number == _TARGET
            assert attachment.core_count == 1
            assert recovered_pid != failed_pid
            assert recovered_workers[0].is_terminal is False
            assert recovered_workers[0].is_alive is True
        finally:
            await recovered_client.close()
            await recovered_supervisor.stop()

        assert recovered_supervisor.endpoint is None
        _assert_terminal_worker(recovered_workers[0], recovered_pid)
        _assert_released(data_root, recovered_endpoint)

    run(scenario())


@pytest.mark.parametrize(
    ("mode", "expected_diagnostic"),
    [
        (
            "program-preexisting-diagnostic",
            _PREEXISTING_PROGRAM_DIAGNOSTIC,
        ),
        (
            "program-typed-cause",
            {
                "schemaVersion": 1,
                "stage": "program-call",
                "exceptions": [
                    {
                        "type": "builtins.OSError",
                        "message": "program failed",
                        "errno": None,
                        "winerror": None,
                        "address": None,
                        "resultCode": None,
                    }
                ],
            },
        ),
        (
            "program-typed-without-cause",
            {
                "schemaVersion": 1,
                "stage": "program-call",
                "exceptions": [
                    {
                        "type": "unknown",
                        "message": "typed program failure",
                        "errno": None,
                        "winerror": None,
                        "address": None,
                        "resultCode": None,
                    }
                ],
            },
        ),
    ],
)
def test_pyocd_worker_program_failure_settles_and_recovers_with_fresh_worker(
    tmp_path: Path,
    mode: str,
    expected_diagnostic: dict[str, object],
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "plugin-data"
        project_root = tmp_path / "project"
        project_root.mkdir()
        firmware = project_root / "firmware.elf"
        firmware.write_bytes(_FIXTURE_BYTES)

        failed_workers: list[ProbeBackendWorker] = []
        failed_supervisor = make_supervisor(
            data_root,
            _ParentWorkerFactory(mode, failed_workers),
            operation_level=OperationLevel.MODIFY,
            project_root=project_root,
        )
        failed_endpoint = await failed_supervisor.start()
        failed_client = ProbeClient(failed_endpoint)
        try:
            await failed_client.attach(_PROBE_ID, _TARGET)
            failed_pid = failed_workers[0].owned_pid
            with pytest.raises(ProbeClientError) as caught:
                await failed_client.program_verified_elf(
                    "firmware.elf", _FIXTURE_SHA256, len(_FIXTURE_BYTES)
                )

            assert caught.value.code == "PROBE_PROGRAM_FAILED"
            assert caught.value.message == "Probe worker operation failed"
            assert caught.value.details == {"programDiagnostic": expected_diagnostic}
            assert "attachDiagnostic" not in caught.value.details
            _assert_terminal_worker(failed_workers[0], failed_pid)
        finally:
            await failed_client.close()
            await failed_supervisor.stop()

        assert failed_supervisor.endpoint is None
        _assert_released(data_root, failed_endpoint)

        recovered_workers: list[ProbeBackendWorker] = []
        recovered_supervisor = make_supervisor(
            data_root,
            _ParentWorkerFactory("healthy", recovered_workers),
            operation_level=OperationLevel.MODIFY,
            project_root=project_root,
        )
        recovered_endpoint = await recovered_supervisor.start()
        recovered_client = ProbeClient(recovered_endpoint)
        try:
            recovered_pid = recovered_workers[0].owned_pid
            await recovered_client.attach(_PROBE_ID, _TARGET)
            assert recovered_pid != failed_pid
            assert recovered_workers[0].is_terminal is False
            assert await recovered_client.program_verified_elf(
                "firmware.elf", _FIXTURE_SHA256, len(_FIXTURE_BYTES)
            ) == FlashBackendReport(None, None)
            assert recovered_workers[0].is_terminal is False
            assert recovered_workers[0].is_alive is True
        finally:
            await recovered_client.close()
            await recovered_supervisor.stop()

        assert recovered_supervisor.endpoint is None
        _assert_terminal_worker(recovered_workers[0], recovered_pid)
        _assert_released(data_root, recovered_endpoint)

    run(scenario())
