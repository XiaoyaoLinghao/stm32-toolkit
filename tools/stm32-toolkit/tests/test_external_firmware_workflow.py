"""Imported-image programming through the real loopback service (fake hardware)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from fakes.fake_probe import FakeProbeBackend
from fakes.fake_pyocd import (
    FakeMemoryMap,
    FakeMemoryRegion,
    FakePyOCDDriver,
    FakePyOCDProbe,
    FakePyOCDTarget,
)
from stm32_toolkit.external_firmware import (
    FirmwareImportRequest,
    ImportedFlashRequest,
    external_workspace_paths,
    firmware_import_workflow,
    load_admission,
)
from stm32_toolkit.hardware_workflows import (
    FlashImportedWorkflowRequest,
    HardwareWorkflowSeams,
    flash_imported_workflow,
)
from stm32_toolkit.probe.backend import (
    ProbeBackendError,
    ProbeDescriptor,
    make_program_diagnostic,
)
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend
from stm32_toolkit.probe.supervisor import ProbeServiceConfig, ProbeServiceSupervisor
from stm32_toolkit.probe.worker import ProbeBackendWorker
from test_external_firmware import _elf

TARGET = "stm32f407vg"
PROBE = "probe-a"
BASE = 0x0800_0000
REGIONS = ((0x0800_0000, 0x1_0000),)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prepare_import(
    tmp_path: Path, payload: bytes = b"external-payload"
) -> tuple[Path, Path, bytes, str, str, object]:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    (project / "fw.bin").write_bytes(payload)
    plan = firmware_import_workflow(
        FirmwareImportRequest(
            project, data_root, "session-a", "fw.bin", _sha(payload),
            "bin", TARGET, REGIONS, BASE, None, False,
        )
    )
    assert plan.ok is True, plan.to_dict()
    applied = firmware_import_workflow(
        FirmwareImportRequest(
            project, data_root, "session-a", "fw.bin", _sha(payload),
            "bin", TARGET, REGIONS, BASE, plan.data["planId"], True,
        )
    )
    assert applied.ok is True, applied.to_dict()
    import_id = str(applied.data["importId"])
    admission = load_admission(
        project, data_root, import_id=import_id, expected_sha256=_sha(payload)
    )
    return project, data_root, payload, import_id, _sha(payload), admission


def _receipts(data_root: Path) -> list[Path]:
    return list((data_root / "projects").glob("*/flash-receipts/*.json"))


def _backend(admission: object, *, mutate: bytes | None = None) -> FakeProbeBackend:
    memory: dict[int, bytes] = {}
    for segment in admission.segments:  # type: ignore[attr-defined]
        data = bytes(segment.data)
        if memory == {} and mutate is not None:
            data = mutate + data[len(mutate):]
        memory[segment.address] = data
    return FakeProbeBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory=memory,
        registers={},
    )


def _seams(backend: FakeProbeBackend) -> HardwareWorkflowSeams:
    return replace(
        HardwareWorkflowSeams(), _test_backend_factory=lambda: backend
    )


def _run(
    project: Path,
    data_root: Path,
    import_id: str,
    source_sha: str,
    backend: FakeProbeBackend,
):
    return asyncio.run(
        flash_imported_workflow(
            FlashImportedWorkflowRequest(
                project, data_root, "session-a", PROBE, import_id, source_sha, True
            ),
            _seams=_seams(backend),
        )
    )


def test_imported_flash_loopback_programs_verifies_and_commits_external_receipt(
    tmp_path: Path,
) -> None:
    project, data_root, payload, import_id, source_sha, admission = _prepare_import(
        tmp_path
    )
    backend = _backend(admission)

    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is True, result.to_dict()
    assert result.details["postFlash"] == {
        "targetState": "unknown",
        "runVerified": False,
    }
    assert result.data["importId"] == import_id
    assert result.data["sourceSha256"] == source_sha
    assert result.data["sourceSha256"] != result.data["imageSha256"]
    assert result.data["verifiedBytes"] == len(payload)
    assert result.data["hardwareVerified"] is True
    assert result.data["runVerified"] is False
    assert any(event[0] == "open_attach" for event in backend.events)
    assert ("flash_imported_elf", len(backend.flashed_images[0])) in backend.events
    assert backend.closed is True

    receipts = _receipts(data_root)
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["kind"] == "stm32-external-flash-receipt"
    assert receipt["status"] == "success"
    assert receipt["importId"] == import_id
    assert receipt["sourceSha256"] == source_sha
    assert receipt["imageSha256"] == result.data["imageSha256"]
    assert receipt["probeSelectorDigest"] == _sha(PROBE.encode("utf-8"))
    assert receipt["verifiedBytes"] == len(payload)
    assert receipt["buildIdentity"] is None
    assert receipt["gitVerified"] is False
    assert receipt["runVerified"] is False
    assert result.data["receiptPath"].startswith("flash-receipts/")
    assert not (project / "artifacts" / "migration" / "flash-result.json").exists()


def test_imported_flash_readback_mismatch_reports_no_success_or_receipt(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"readback-payload"
    )
    backend = _backend(admission, mutate=b"\x00")

    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is False
    assert result.code == "FIRMWARE_FLASH_VERIFY_FAILED"
    assert _receipts(data_root) == []
    assert backend.closed is True
    # Exactly one programming attempt; no retry or fallback.
    assert sum(event[0] == "flash_imported_elf" for event in backend.events) == 1


@pytest.mark.parametrize("stage", ("pre-program-reset", "pre-program-halt"))
def test_imported_preparation_failure_stops_readback_receipt_and_retry(
    tmp_path: Path, stage: str
) -> None:
    """A pre-program failure crosses the real loopback service boundary intact.

    The owned cleanup must still run, and the workflow must not read memory,
    publish a success receipt, or attempt a second program call.
    """

    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"preparation-failure"
    )
    diagnostic = make_program_diagnostic(stage, OSError(5, "preparation failed"))

    class UnpreparedBackend(FakeProbeBackend):
        def flash_imported_elf(self, image: bytes):
            self.events.append(("flash_imported_elf", len(image)))
            raise ProbeBackendError(
                "PROBE_PROGRAM_FAILED",
                "Firmware programming failed",
                {"programDiagnostic": diagnostic},
            )

    backend = UnpreparedBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory={
            segment.address: bytes(segment.data)
            for segment in admission.segments
        },
        registers={},
    )

    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is False
    assert result.code == "PROBE_PROGRAM_FAILED"
    assert result.details["programDiagnostic"] == diagnostic
    assert result.details["programDiagnostic"]["stage"] == stage
    assert result.details["flashOptions"]["preProgramReset"] == "sysresetreq"
    assert result.details["flashOptions"]["preProgramHaltRequired"] is True
    # No readback and no success receipt followed the failed preparation.
    assert not any(event[0] == "read_memory" for event in backend.events)
    assert _receipts(data_root) == []
    # Exactly one programming attempt and the existing owned cleanup ran.
    assert sum(event[0] == "flash_imported_elf" for event in backend.events) == 1
    assert backend.closed is True
    assert ("close",) in backend.events


def test_close_time_store_tamper_blocks_receipt_publication(tmp_path: Path) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"close-tamper"
    )
    record_path = next(
        (data_root / "projects").glob(
            f"*/firmware-imports/{import_id}/record.json"
        )
    )
    tampered = json.loads(record_path.read_text(encoding="utf-8"))
    tampered["image"]["segments"][0]["length"] += 1

    class CloseTamperingBackend(FakeProbeBackend):
        def close(self) -> None:
            super().close()
            record_path.write_text(json.dumps(tampered), encoding="utf-8")

    backend = CloseTamperingBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory={
            segment.address: bytes(segment.data)
            for segment in admission.segments
        },
        registers={},
    )
    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is False
    assert result.code in {"FIRMWARE_IMPORT_INVALID", "FIRMWARE_INPUT_CHANGED"}
    assert _receipts(data_root) == []
    # No automatic retry after the integrity failure.
    assert sum(event[0] == "flash_imported_elf" for event in backend.events) == 1


def test_imported_flash_requires_exact_true_before_any_service_effect(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"

    seams = replace(
        HardwareWorkflowSeams(),
        _test_backend_factory=lambda: (_ for _ in ()).throw(
            AssertionError("no backend may be constructed")
        ),
    )
    for value in (False, "true", 1, None):
        result = asyncio.run(
            flash_imported_workflow(
                FlashImportedWorkflowRequest(
                    project, data_root, "session-a", PROBE, "a" * 64, "b" * 64, value
                ),
                _seams=seams,
            )
        )
        assert result.code == "AUTHORIZATION_REQUIRED"
    assert not data_root.exists()


def test_store_change_during_attach_blocks_every_program_call(tmp_path: Path) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"attach-race"
    )
    record_path = next(
        (data_root / "projects").glob(
            f"*/firmware-imports/{import_id}/record.json"
        )
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["image"]["segments"][0]["length"] += 1

    class MutatingBackend(FakeProbeBackend):
        def open_attach(self, probe_id, target, *, halt_on_connect=False):
            evidence = super().open_attach(
                probe_id, target, halt_on_connect=halt_on_connect
            )
            record_path.write_text(json.dumps(record), encoding="utf-8")
            return evidence

    backend = MutatingBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory={
            segment.address: bytes(segment.data)
            for segment in admission.segments
        },
        registers={},
    )
    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is False
    assert result.code == "FIRMWARE_IMPORT_INVALID"
    assert not any(event[0] == "flash_imported_elf" for event in backend.events)
    assert _receipts(data_root) == []
    assert backend.closed is True


def test_owned_cleanup_failure_never_commits_a_receipt(tmp_path: Path) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"cleanup-failure"
    )

    class CloseFailingBackend(FakeProbeBackend):
        def close(self) -> None:
            super().close()
            raise RuntimeError("close failed")

    backend = CloseFailingBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory={
            segment.address: bytes(segment.data)
            for segment in admission.segments
        },
        registers={},
    )
    result = _run(project, data_root, import_id, source_sha, backend)

    assert result.ok is False
    assert result.code == "HARDWARE_CLEANUP_FAILED"
    assert _receipts(data_root) == []


def test_cancellation_during_programming_cleans_up_without_receipt(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"cancelled"
    )

    class BlockingBackend(FakeProbeBackend):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # type: ignore[arg-type]
            self.started = threading.Event()

        def flash_imported_elf(self, image: bytes):
            self.started.set()
            time.sleep(0.2)
            return super().flash_imported_elf(image)

    backend = BlockingBackend(
        probes=(ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None),),
        memory={
            segment.address: bytes(segment.data)
            for segment in admission.segments
        },
        registers={},
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            flash_imported_workflow(
                FlashImportedWorkflowRequest(
                    project, data_root, "session-a", PROBE, import_id, source_sha, True
                ),
                _seams=_seams(backend),
            )
        )
        await asyncio.to_thread(backend.started.wait, 5.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert _receipts(data_root) == []
    assert backend.closed is True


def _service(
    project: Path,
    data_root: Path,
    import_id: str,
    backend: FakeProbeBackend,
    *,
    level: OperationLevel,
) -> ProbeServiceSupervisor:
    paths = external_workspace_paths(project, data_root, "session-a")
    import_dir = next(
        (data_root / "projects").glob(f"*/firmware-imports/{import_id}")
    )
    config = ProbeServiceConfig(
        probe_id=PROBE,
        workspace_id=paths.workspace_id,
        session_id="session-a",
        operation_level=level,
        session_root=paths.session_root,
        project_root=project,
        programming_root=import_dir,
    )
    return ProbeServiceSupervisor(
        config=config,
        lease_manager=ProbeLeaseManager(data_root),
        backend_factory=lambda: backend,
    )


def test_imported_session_rejects_legacy_rpc_and_only_programs_image_elf(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, source_sha, admission = _prepare_import(
        tmp_path, b"service-authority"
    )
    backend = _backend(admission)
    supervisor = _service(project, data_root, import_id, backend, level=OperationLevel.MODIFY)

    async def scenario() -> None:
        endpoint = await supervisor.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach(PROBE, TARGET)
            with pytest.raises(ProbeClientError) as legacy:
                await client.program_verified_elf(
                    "build/arm-debug/firmware.elf", "a" * 64, 8
                )
            assert legacy.value.code == "PROBE_OPERATION_UNAVAILABLE"
            assert not any(event[0] == "flash_elf" for event in backend.events)

            with pytest.raises(ProbeClientError) as wrong_path:
                await client.program_verified_imported_elf(
                    "other.elf", admission.image_sha256, admission.image_size
                )
            assert wrong_path.value.code in {
                "PROBE_REQUEST_INVALID",
                "FIRMWARE_PATH_INVALID",
            }

            report = await client.program_verified_imported_elf(
                "image.elf", admission.image_sha256, admission.image_size
            )
            assert report.bytes_programmed == 1024
            assert sum(
                event[0] == "flash_imported_elf" for event in backend.events
            ) == 1
        finally:
            await client.close()
            await supervisor.stop()

    asyncio.run(scenario())
    assert backend.closed is True


def test_imported_session_enforces_modify_level_from_real_client(
    tmp_path: Path,
) -> None:
    project, data_root, _payload, import_id, _source_sha, admission = _prepare_import(
        tmp_path, b"observe-authority"
    )
    backend = _backend(admission)
    supervisor = _service(project, data_root, import_id, backend, level=OperationLevel.OBSERVE)

    async def scenario() -> None:
        endpoint = await supervisor.start()
        client = ProbeClient(endpoint)
        try:
            with pytest.raises(ProbeClientError) as denied:
                await client.program_verified_imported_elf(
                    "image.elf", admission.image_sha256, admission.image_size
                )
            assert denied.value.code == "PROBE_OPERATION_LEVEL_DENIED"
            assert not any(
                event[0] == "flash_imported_elf" for event in backend.events
            )
        finally:
            await client.close()
            await supervisor.stop()

    asyncio.run(scenario())


def _flash_backend(
    regions: tuple[FakeMemoryRegion, ...],
) -> tuple[PyOCDBackend, FakePyOCDDriver]:
    driver = FakePyOCDDriver(
        (FakePyOCDProbe(PROBE),),
        target=FakePyOCDTarget(
            memory_map=FakeMemoryMap(tuple(regions)),
            part_number="STM32F429ZI",
        ),
    )
    backend = PyOCDBackend(driver)
    backend.open_attach(PROBE, TARGET, halt_on_connect=True)
    return backend, driver


F429_BANK = (
    FakeMemoryRegion(0x0800_0000, 0x1_0000),
    FakeMemoryRegion(0x0801_0000, 0x1_0000),
    FakeMemoryRegion(0x0802_0000, 0xE_0000),
)


def test_native_map_accepts_segment_crossing_contiguous_64k_regions() -> None:
    backend, driver = _flash_backend(F429_BANK)
    image = _elf(((0x0800_F000, b"\x5A" * 0x3000),))

    report = backend.flash_imported_elf(image)

    assert report.bytes_programmed is None
    assert len(driver.program_calls) == 1
    assert driver.program_calls[0][1] == image


@pytest.mark.parametrize(
    ("regions", "segments", "code"),
    [
        # Tail of the last segment falls in a gap after the declared banks.
        (
            (
                FakeMemoryRegion(0x0800_0000, 0x1_0000),
                FakeMemoryRegion(0x0801_0000, 0x1_0000),
                FakeMemoryRegion(0x0802_0000, 0x8000),
            ),
            ((0x0800_0000, b"\x01" * 16), (0x0802_8000, b"\x02" * 16)),
            "PROBE_PROGRAM_INVALID",
        ),
        # A later segment addresses RAM, which is not Flash coverage.
        (
            F429_BANK + (FakeMemoryRegion(0x2000_0000, 0x1_0000, is_flash=False),),
            ((0x0800_0000, b"\x01" * 16), (0x2000_0000, b"\x02" * 16)),
            "PROBE_PROGRAM_INVALID",
        ),
        # Overlapping native Flash intervals are ambiguous.
        (
            (
                FakeMemoryRegion(0x0800_0000, 0x2_0000),
                FakeMemoryRegion(0x0801_0000, 0x1_0000),
            ),
            ((0x0800_0000, b"\x01" * 16),),
            "PROBE_BACKEND_ERROR",
        ),
        # A later segment inside a non-Flash entry that overlaps Flash is
        # rejected as an ambiguous map, with no driver call.
        (
            (
                FakeMemoryRegion(0x0800_0000, 0x2_0000),
                FakeMemoryRegion(0x0801_0000, 0x1000, is_flash=False),
            ),
            ((0x0800_0000, b"\x01" * 16), (0x0801_0000, b"\x02" * 16)),
            "PROBE_BACKEND_ERROR",
        ),
    ],
)
def test_native_map_later_gap_nonflash_or_overlap_rejects_before_driver(
    regions: tuple[FakeMemoryRegion, ...],
    segments: tuple[tuple[int, bytes], ...],
    code: str,
) -> None:
    backend, driver = _flash_backend(regions)
    image = _elf(segments)

    with pytest.raises(Exception) as error:
        backend.flash_imported_elf(image)

    assert getattr(error.value, "code", None) == code
    assert driver.program_calls == []


def test_imported_rpc_request_type_is_a_closed_fake_hardware_contract() -> None:
    """The programming routine never accepts a caller-chosen target or path."""

    request = ImportedFlashRequest(
        Path("project"), Path("data"), PROBE, "a" * 64, "b" * 64, True
    )
    assert request.authorized is True
    assert request.timeout_ms == 30_000


WORKER_PROBE_DESCRIPTOR = ProbeDescriptor(PROBE, "Arm", "CMSIS-DAP", None)


def _worker_backend():
    return FakeProbeBackend(
        probes=(WORKER_PROBE_DESCRIPTOR,), memory={}, registers={}
    )


class _RejectingWorkerBackend(FakeProbeBackend):
    def flash_imported_elf(self, image: bytes):
        raise ProbeBackendError(
            "PROBE_PROGRAM_INVALID", "raw C:\\private token=secret"
        )


def _rejecting_worker_backend():
    return _RejectingWorkerBackend(
        probes=(WORKER_PROBE_DESCRIPTOR,), memory={}, registers={}
    )


def test_spawned_worker_dispatches_imported_program_and_sanitizes_failure() -> None:
    """The owned worker allowlist carries flash_imported_elf and no raw text."""

    image = _elf(((0x0800_0000, b"\x01\x02"),))
    worker = ProbeBackendWorker(_test_backend_factory=_worker_backend)
    try:
        worker.open_attach(PROBE, TARGET, halt_on_connect=True)
        report = worker.flash_imported_elf(image)
        assert report.bytes_programmed == 1024
        assert report.sectors_programmed == 2
    finally:
        worker.close()
    assert worker.is_alive is False

    rejecting = ProbeBackendWorker(_test_backend_factory=_rejecting_worker_backend)
    try:
        rejecting.open_attach(PROBE, TARGET, halt_on_connect=True)
        with pytest.raises(ProbeBackendError) as error:
            rejecting.flash_imported_elf(image)
        assert error.value.code == "PROBE_PROGRAM_INVALID"
        assert "secret" not in str(error.value)
        assert "C:\\private" not in str(error.value)
    finally:
        rejecting.close()
    assert rejecting.is_alive is False
