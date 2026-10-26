from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.models import (
    FirmwareStatus,
    HistoryBatchSlice,
    LiveEvent,
    MonitorConfig,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchItem,
)
from stm32_monitor.probe_session import ProbeSession
from stm32_monitor.protocol import success
from stm32_monitor.runtime import MonitorRuntime, _firmware_status
from stm32_monitor.service import MONITOR_VERSION
from stm32_toolkit.debug import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.result import OperationResult


WORKSPACE_ID = "c" * 64
LOGICAL_PROJECT_ID = "33333333-3333-4333-8333-333333333333"
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
SOURCE_BASELINE = "input-snapshot-v1"
HEAD_EVIDENCE = {
    "status": "unavailable",
    "code": "BUILD_GIT_INVALID",
    "rule": "head",
}
STATUS_EVIDENCE = HEAD_EVIDENCE | {"rule": "status"}

FIRMWARE_FIELDS = (
    "buildId",
    "elfSha256",
    "inputSnapshotSha256",
    "gitHead",
    "gitDirty",
    "targetDevice",
)
BINDING_FIELDS = frozenset(
    {
        "workspaceId",
        "logicalProjectId",
        "sessionId",
        "probeId",
        "targetDevice",
        "physicalTarget",
        "buildId",
        "elfSha256",
        "inputSnapshotSha256",
        "gitHead",
        "gitDirty",
        "flashSessionId",
        "leaseId",
        "dwarfSha256",
        "svdSha256",
    }
)
PROVENANCE_FIELDS = frozenset({"sourceBaseline", "gitEvidence"})


def _legacy_firmware(**overrides: object) -> FirmwareStatus:
    fields: dict[str, object] = {
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "f" * 64,
        "git_head": "a" * 40,
        "git_dirty": False,
        "target_device": "STM32F407VGTx",
    }
    fields.update(overrides)
    return FirmwareStatus(**fields)  # type: ignore[arg-type]


def _snapshot_firmware(**overrides: object) -> FirmwareStatus:
    fields: dict[str, object] = {
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "9" * 64,
        "git_head": None,
        "git_dirty": None,
        "target_device": "STM32F407VGTx",
        "source_baseline": SOURCE_BASELINE,
        "git_evidence": dict(HEAD_EVIDENCE),
    }
    fields.update(overrides)
    return FirmwareStatus(**fields)  # type: ignore[arg-type]


def _legacy_binding(**overrides: object) -> ObservationBinding:
    fields: dict[str, object] = {
        "workspace_id": WORKSPACE_ID,
        "logical_project_id": LOGICAL_PROJECT_ID,
        "session_id": "monitor-1",
        "probe_id": "probe-serial-1",
        "target_device": "STM32F407VGTx",
        "physical_target": "stm32f407vg",
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "f" * 64,
        "git_head": "a" * 40,
        "git_dirty": False,
        "flash_session_id": "flash-1",
        "lease_id": "lease-1",
        "dwarf_sha256": "d" * 64,
        "svd_sha256": "a" * 64,
    }
    fields.update(overrides)
    return ObservationBinding(**fields)  # type: ignore[arg-type]


def _snapshot_binding(**overrides: object) -> ObservationBinding:
    fields: dict[str, object] = {
        "workspace_id": WORKSPACE_ID,
        "logical_project_id": LOGICAL_PROJECT_ID,
        "session_id": "monitor-1",
        "probe_id": "probe-serial-1",
        "target_device": "STM32F407VGTx",
        "physical_target": "stm32f407vg",
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "9" * 64,
        "git_head": None,
        "git_dirty": None,
        "flash_session_id": "flash-1",
        "lease_id": "lease-1",
        "dwarf_sha256": "d" * 64,
        "svd_sha256": None,
        "source_baseline": SOURCE_BASELINE,
        "git_evidence": dict(HEAD_EVIDENCE),
    }
    fields.update(overrides)
    return ObservationBinding(**fields)  # type: ignore[arg-type]


def _live_status(firmware: dict[str, object] | None) -> dict[str, object]:
    return {
        "workspaceId": WORKSPACE_ID,
        "sessionId": "monitor-1",
        "project": {
            "logicalProjectId": LOGICAL_PROJECT_ID,
            "name": "fixture",
            "targetDevice": "STM32F407VGTx",
        },
        "firmware": firmware,
        "probe": {"connected": False, "probeId": None},
        "sampling": {
            "state": "IDLE",
            "active": False,
            "blockedCode": None,
            "groupId": None,
            "groupRevision": None,
            "runId": None,
            "lastSequence": None,
            "bindingEpoch": 0,
            "subscriberDrops": 0,
            "historyDrops": 0,
            "deadlineDrops": 0,
            "serviceDrops": 0,
        },
        "probeConnected": False,
        "samplingActive": False,
    }


def _sample_batch(binding: ObservationBinding) -> SampleBatch:
    return SampleBatch(
        binding=binding,
        group_id=GROUP_ID,
        group_revision=1,
        run_id=RUN_ID,
        sequence=0,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=0,
        history_drops=0,
        deadline_drops=0,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value=7),),
    )


def _history_slice(binding: ObservationBinding) -> HistoryBatchSlice:
    return HistoryBatchSlice(
        binding=binding,
        group_id=GROUP_ID,
        group_revision=1,
        run_id=RUN_ID,
        sequence=0,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=0,
        history_drops=0,
        deadline_drops=0,
        start_ordinal=0,
        batch_value_count=1,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value=7),),
    )


def test_firmware_status_legacy_form_keeps_old_canonical_bytes_and_lowercases_git() -> None:
    status = _legacy_firmware(git_head="A" * 40)

    assert status.git_head == "a" * 40
    assert status.git_dirty is False
    assert status.source_baseline is None and status.git_evidence is None
    document = status.to_dict()
    assert tuple(document) == FIRMWARE_FIELDS
    assert document == {
        "buildId": "b" * 64,
        "elfSha256": "e" * 64,
        "inputSnapshotSha256": "f" * 64,
        "gitHead": "a" * 40,
        "gitDirty": False,
        "targetDevice": "STM32F407VGTx",
    }
    assert json.dumps(document, separators=(",", ":")) == (
        '{"buildId":"%s","elfSha256":"%s","inputSnapshotSha256":"%s",'
        '"gitHead":"%s","gitDirty":false,"targetDevice":"STM32F407VGTx"}'
        % ("b" * 64, "e" * 64, "f" * 64, "a" * 40)
    )
    assert FirmwareStatus.from_dict(document) == status


def test_firmware_status_snapshot_form_serializes_null_git_and_immutable_evidence() -> None:
    raw_evidence = dict(HEAD_EVIDENCE)
    status = _snapshot_firmware(git_evidence=raw_evidence)
    raw_evidence["rule"] = "status"

    assert status.git_head is None and status.git_dirty is None
    assert status.git_evidence == HEAD_EVIDENCE
    assert isinstance(status.git_evidence, MappingProxyType)
    with pytest.raises(TypeError):
        status.git_evidence["rule"] = "status"  # type: ignore[index]

    document = status.to_dict()
    assert tuple(document) == FIRMWARE_FIELDS + ("sourceBaseline", "gitEvidence")
    assert document["gitHead"] is None
    assert document["gitDirty"] is None
    assert document["sourceBaseline"] == SOURCE_BASELINE
    assert document["gitEvidence"] == HEAD_EVIDENCE
    document["gitEvidence"]["rule"] = "status"  # type: ignore[index]
    document["gitEvidence"]["code"] = "OTHER"  # type: ignore[index]
    assert status.to_dict()["gitEvidence"] == HEAD_EVIDENCE

    decoded = FirmwareStatus.from_dict(status.to_dict())
    assert decoded == status
    assert decoded.git_evidence == HEAD_EVIDENCE


@pytest.mark.parametrize(
    "overrides",
    (
        {"git_evidence": None},
        {"source_baseline": None},
        {"source_baseline": "git"},
        {"git_head": "a" * 40},
        {"git_dirty": False},
        {"git_evidence": dict(STATUS_EVIDENCE) | {"rule": "branch"}},
        {"git_evidence": dict(STATUS_EVIDENCE) | {"code": "OTHER"}},
        {"git_evidence": dict(STATUS_EVIDENCE) | {"extra": "value"}},
    ),
)
def test_firmware_status_rejects_partial_unknown_and_mixed_snapshot_fields(
    overrides: dict[str, object]
) -> None:
    fields: dict[str, object] = {
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "9" * 64,
        "git_head": None,
        "git_dirty": None,
        "target_device": "STM32F407VGTx",
        "source_baseline": SOURCE_BASELINE,
        "git_evidence": dict(HEAD_EVIDENCE),
    }
    fields.update(overrides)
    with pytest.raises(ValueError):
        FirmwareStatus(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "document",
    (
        {**_legacy_firmware().to_dict(), "sourceBaseline": SOURCE_BASELINE},
        {**_legacy_firmware().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE)},
        {**_legacy_firmware().to_dict(), "sourceBaseline": None, "gitEvidence": None},
        {**_legacy_firmware().to_dict(), "gitHead": None},
        {**_legacy_firmware().to_dict(), "gitDirty": None},
        {**_legacy_firmware().to_dict(), "extra": True},
        {**_snapshot_firmware().to_dict(), "gitHead": "a" * 40},
        {**_snapshot_firmware().to_dict(), "gitDirty": False},
        {**_snapshot_firmware().to_dict(), "sourceBaseline": None},
        {**_snapshot_firmware().to_dict(), "sourceBaseline": "git"},
        {**_snapshot_firmware().to_dict(), "gitEvidence": None},
        {
            **_snapshot_firmware().to_dict(),
            "gitEvidence": dict(STATUS_EVIDENCE) | {"extra": "value"},
        },
    ),
)
def test_firmware_status_decoder_rejects_partial_present_null_unknown_and_mixed(
    document: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        FirmwareStatus.from_dict(document)


def test_observation_binding_legacy_form_preserves_case_and_exact_bytes() -> None:
    binding = _legacy_binding(git_head="A" * 40)

    assert binding.git_head == "A" * 40
    assert binding.git_dirty is False
    assert binding.source_baseline is None and binding.git_evidence is None
    document = binding.to_dict()
    assert set(document) == BINDING_FIELDS
    assert document["gitHead"] == "A" * 40
    assert document["gitDirty"] is False
    assert "sourceBaseline" not in document and "gitEvidence" not in document
    canonical = json.dumps(document, separators=(",", ":"))
    assert canonical == json.dumps(
        {
            "workspaceId": WORKSPACE_ID,
            "logicalProjectId": LOGICAL_PROJECT_ID,
            "sessionId": "monitor-1",
            "probeId": "probe-serial-1",
            "targetDevice": "STM32F407VGTx",
            "physicalTarget": "stm32f407vg",
            "buildId": "b" * 64,
            "elfSha256": "e" * 64,
            "inputSnapshotSha256": "f" * 64,
            "gitHead": "A" * 40,
            "gitDirty": False,
            "flashSessionId": "flash-1",
            "leaseId": "lease-1",
            "dwarfSha256": "d" * 64,
            "svdSha256": "a" * 64,
        },
        separators=(",", ":"),
    )
    assert ObservationBinding.from_dict(dict(document)) == binding


def test_observation_binding_snapshot_form_roundtrips_and_keeps_evidence_immutable() -> None:
    raw_evidence = dict(STATUS_EVIDENCE)
    binding = _snapshot_binding(git_evidence=raw_evidence)
    raw_evidence["rule"] = "head"

    assert binding.git_head is None and binding.git_dirty is None
    assert binding.source_baseline == SOURCE_BASELINE
    assert binding.git_evidence == STATUS_EVIDENCE
    assert isinstance(binding.git_evidence, MappingProxyType)
    with pytest.raises(TypeError):
        binding.git_evidence["rule"] = "head"  # type: ignore[index]

    document = binding.to_dict()
    assert set(document) == BINDING_FIELDS | PROVENANCE_FIELDS
    assert document["gitHead"] is None
    assert document["gitDirty"] is None
    assert document["sourceBaseline"] == SOURCE_BASELINE
    assert document["gitEvidence"] == STATUS_EVIDENCE
    document["gitEvidence"]["rule"] = "head"  # type: ignore[index]
    assert binding.to_dict()["gitEvidence"] == STATUS_EVIDENCE

    decoded = ObservationBinding.from_dict(binding.to_dict())
    assert decoded == binding
    assert decoded.git_evidence == STATUS_EVIDENCE


@pytest.mark.parametrize(
    "overrides",
    (
        {"git_evidence": None},
        {"source_baseline": None},
        {"source_baseline": "git"},
        {"git_head": "a" * 40},
        {"git_dirty": False},
        {"git_evidence": dict(HEAD_EVIDENCE) | {"rule": "branch"}},
        {"git_evidence": dict(HEAD_EVIDENCE) | {"status": "available"}},
    ),
)
def test_observation_binding_rejects_partial_unknown_and_mixed_snapshot_fields(
    overrides: dict[str, object]
) -> None:
    fields: dict[str, object] = {
        "workspace_id": WORKSPACE_ID,
        "logical_project_id": LOGICAL_PROJECT_ID,
        "session_id": "monitor-1",
        "probe_id": "probe-serial-1",
        "target_device": "STM32F407VGTx",
        "physical_target": "stm32f407vg",
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "input_snapshot_sha256": "9" * 64,
        "git_head": None,
        "git_dirty": None,
        "flash_session_id": "flash-1",
        "lease_id": "lease-1",
        "dwarf_sha256": "d" * 64,
        "svd_sha256": None,
        "source_baseline": SOURCE_BASELINE,
        "git_evidence": dict(HEAD_EVIDENCE),
    }
    fields.update(overrides)
    with pytest.raises(ValueError):
        ObservationBinding(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "document",
    (
        {**_legacy_binding().to_dict(), "sourceBaseline": SOURCE_BASELINE},
        {**_legacy_binding().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE)},
        {**_legacy_binding().to_dict(), "sourceBaseline": None, "gitEvidence": None},
        {**_legacy_binding().to_dict(), "gitHead": None},
        {**_legacy_binding().to_dict(), "gitDirty": None},
        {**_legacy_binding().to_dict(), "extra": True},
        {**_snapshot_binding().to_dict(), "gitHead": "a" * 40},
        {**_snapshot_binding().to_dict(), "gitDirty": False},
        {**_snapshot_binding().to_dict(), "sourceBaseline": None},
        {**_snapshot_binding().to_dict(), "sourceBaseline": "git"},
        {**_snapshot_binding().to_dict(), "gitEvidence": None},
        {
            **_snapshot_binding().to_dict(),
            "gitEvidence": dict(HEAD_EVIDENCE) | {"rule": "branch"},
        },
        {**_snapshot_binding().to_dict(), "extra": True},
    ),
)
def test_observation_binding_decoder_rejects_partial_present_null_unknown_and_mixed(
    document: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        ObservationBinding.from_dict(document)


@pytest.mark.parametrize(
    "firmware",
    (_legacy_firmware().to_dict(), _snapshot_firmware().to_dict()),
    ids=("legacy", "snapshot"),
)
def test_live_state_decoding_accepts_both_firmware_provenance_forms(
    firmware: dict[str, object]
) -> None:
    event = LiveEvent(
        1, "state", {"stateRevision": 1, "gap": False, "status": _live_status(firmware)}
    )

    assert event.to_dict()["data"]["status"]["firmware"] == firmware


@pytest.mark.parametrize(
    "firmware",
    (
        {**_legacy_firmware().to_dict(), "sourceBaseline": SOURCE_BASELINE},
        {**_legacy_firmware().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE)},
        {**_legacy_firmware().to_dict(), "sourceBaseline": None, "gitEvidence": None},
        {**_legacy_firmware().to_dict(), "gitHead": None},
        {**_legacy_firmware().to_dict(), "extra": True},
        {**_snapshot_firmware().to_dict(), "gitHead": "a" * 40},
        {**_snapshot_firmware().to_dict(), "gitDirty": False},
        {**_snapshot_firmware().to_dict(), "sourceBaseline": "git"},
        {**_snapshot_firmware().to_dict(), "gitEvidence": None},
        {**_snapshot_firmware().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE, rule="branch")},
        "not-a-firmware-document",
    ),
)
def test_live_state_decoding_rejects_malformed_firmware_pairs(firmware: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        LiveEvent(
            1, "state", {"stateRevision": 1, "gap": False, "status": _live_status(firmware)}
        )


@pytest.mark.parametrize(
    "binding",
    (_legacy_binding(), _snapshot_binding()),
    ids=("legacy", "snapshot"),
)
def test_live_sample_decoding_accepts_both_binding_provenance_forms(
    binding: ObservationBinding,
) -> None:
    event = LiveEvent(
        1,
        "sample",
        {"batch": _sample_batch(binding).to_dict(), "serviceSubscriberDrops": 0},
    )

    assert event.to_dict()["data"]["batch"]["binding"] == binding.to_dict()


@pytest.mark.parametrize(
    "document",
    (
        {**_legacy_binding().to_dict(), "sourceBaseline": SOURCE_BASELINE},
        {**_legacy_binding().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE)},
        {**_legacy_binding().to_dict(), "sourceBaseline": None, "gitEvidence": None},
        {**_snapshot_binding().to_dict(), "gitHead": "a" * 40},
        {**_snapshot_binding().to_dict(), "gitDirty": False},
        {**_snapshot_binding().to_dict(), "gitEvidence": None},
        {**_snapshot_binding().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE, rule="branch")},
        {**_snapshot_binding().to_dict(), "extra": True},
        "not-a-binding-document",
    ),
)
def test_live_sample_decoding_rejects_malformed_binding_pairs(document: object) -> None:
    payload = {
        "batch": _sample_batch(_legacy_binding()).to_dict(),
        "serviceSubscriberDrops": 0,
    }
    payload["batch"]["binding"] = document
    with pytest.raises((TypeError, ValueError)):
        LiveEvent(1, "sample", payload)


def test_history_slice_preserves_both_provenance_forms_through_serialization() -> None:
    snapshot = _history_slice(_snapshot_binding())
    snapshot_document = snapshot.to_dict()
    assert snapshot_document["binding"] == _snapshot_binding().to_dict()
    assert set(snapshot_document["binding"]) == BINDING_FIELDS | PROVENANCE_FIELDS
    assert snapshot_document["binding"]["gitHead"] is None
    assert snapshot_document["binding"]["gitDirty"] is None
    assert snapshot_document["binding"]["sourceBaseline"] == SOURCE_BASELINE
    assert snapshot_document["binding"]["gitEvidence"] == HEAD_EVIDENCE
    snapshot_document["binding"]["gitEvidence"]["rule"] = "status"
    assert snapshot.to_dict()["binding"]["gitEvidence"] == HEAD_EVIDENCE

    isolated = snapshot.immutable_snapshot()
    assert isolated == snapshot
    assert isolated.binding.git_evidence == HEAD_EVIDENCE
    assert isinstance(isolated.binding.git_evidence, MappingProxyType)

    legacy = _history_slice(_legacy_binding())
    legacy_document = legacy.to_dict()
    assert set(legacy_document["binding"]) == BINDING_FIELDS
    assert legacy_document["binding"] == _legacy_binding().to_dict()
    assert legacy.immutable_snapshot() == legacy


def test_history_decode_uses_the_new_binding_decoder_for_both_forms() -> None:
    # History decoding delegates binding shape to ObservationBinding.from_dict;
    # this pins the exact accepted/rejected surface it relies on.
    assert ObservationBinding.from_dict(_snapshot_binding().to_dict()) == _snapshot_binding()
    assert (
        ObservationBinding.from_dict(_legacy_binding().to_dict()) == _legacy_binding()
    )
    for document in (
        {**_snapshot_binding().to_dict(), "sourceBaseline": None},
        {**_legacy_binding().to_dict(), "gitEvidence": dict(HEAD_EVIDENCE)},
        {**_snapshot_binding().to_dict(), "extra": True},
    ):
        with pytest.raises(ValueError):
            ObservationBinding.from_dict(document)


# --- Runtime firmware projection -------------------------------------------------


def test_runtime_firmware_projection_keeps_snapshot_nulls_and_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_evidence = dict(HEAD_EVIDENCE)
    facts = SimpleNamespace(
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="9" * 64,
        git_commit=None,
        git_dirty=None,
        target_device="STM32F407VGTx",
        source_baseline=SOURCE_BASELINE,
        git_evidence=raw_evidence,
    )
    monkeypatch.setattr(
        "stm32_toolkit.probe.flash.load_fresh_firmware_facts",
        lambda _root: facts,
    )

    status = _firmware_status(tmp_path)

    assert status.git_head is None and status.git_dirty is None
    assert status.source_baseline == SOURCE_BASELINE
    assert status.git_evidence == HEAD_EVIDENCE
    document = status.to_dict()
    assert document["gitHead"] is None and document["gitDirty"] is None
    assert document["gitHead"] != "None" and document["gitDirty"] is not False
    assert document["sourceBaseline"] == SOURCE_BASELINE
    assert document["gitEvidence"] == HEAD_EVIDENCE
    assert FirmwareStatus.from_dict(document) == status

    raw_evidence["rule"] = "status"
    assert status.git_evidence == HEAD_EVIDENCE
    assert status.to_dict()["gitEvidence"] == HEAD_EVIDENCE


def test_runtime_firmware_projection_keeps_legacy_git_form_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = SimpleNamespace(
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_commit="a" * 40,
        git_dirty=True,
        target_device="STM32F407VGTx",
        source_baseline=None,
        git_evidence=None,
    )
    monkeypatch.setattr(
        "stm32_toolkit.probe.flash.load_fresh_firmware_facts",
        lambda _root: facts,
    )

    status = _firmware_status(tmp_path)

    assert status.git_head == "a" * 40 and status.git_dirty is True
    assert status.source_baseline is None and status.git_evidence is None
    document = status.to_dict()
    assert tuple(document) == FIRMWARE_FIELDS
    assert document == {
        "buildId": "b" * 64,
        "elfSha256": "e" * 64,
        "inputSnapshotSha256": "f" * 64,
        "gitHead": "a" * 40,
        "gitDirty": True,
        "targetDevice": "STM32F407VGTx",
    }
    assert FirmwareStatus.from_dict(document) == status


# --- Probe-session projection and invalidation -----------------------------------


def _debug_binding(project: Path, **overrides: object) -> DebugFirmwareBinding:
    fields: dict[str, object] = {
        "logical_project_id": LOGICAL_PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "observation_session_id": "monitor-1",
        "flash_session_id": "flash-1",
        "lease_id": "lease-1",
        "probe_id": "probe-serial-1",
        "target_device": "STM32F407VGTx",
        "debug_target": "stm32f407vg",
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "elf_size": 4096,
        "elf_path": "build/firmware.elf",
        "input_snapshot_sha256": "9" * 64,
        "git_head": None,
        "git_dirty": None,
        "confirmed_at_utc": "2026-08-08T01:02:03.000000Z",
        "memory_regions": (MemoryRegionBinding("FLASH", 0x08000000, 1024, "r-x"),),
        "project_root": project.resolve(),
        "source_baseline": SOURCE_BASELINE,
        "git_evidence": dict(HEAD_EVIDENCE),
    }
    fields.update(overrides)
    return DebugFirmwareBinding(**fields)  # type: ignore[arg-type]


def _legacy_debug_binding(project: Path, **overrides: object) -> DebugFirmwareBinding:
    fields: dict[str, object] = {
        "source_baseline": None,
        "git_evidence": None,
        "git_head": "A" * 40,
        "git_dirty": False,
    }
    fields.update(overrides)
    return _debug_binding(project, **fields)


class _FakeObservedSession:
    def __init__(self, binding: DebugFirmwareBinding) -> None:
        self.binding = binding
        self.catalog = SimpleNamespace(elf_sha256=binding.elf_sha256)
        self.svd = SimpleNamespace(sha256="a" * 64)
        self.revalidate_result = OperationResult.success("revalidate", binding)
        self.lightweight_result: object | None = None
        self._admission_token: object | None = object()
        self.reset_calls = 0
        self.resume_calls = 0
        self.halt_calls = 0

    def _invalidate_read_plan(self) -> None:
        self._admission_token = None

    def _read_plan_admission(self):
        return self._admission_token

    async def _read_batch(self, variables, registers):
        raise AssertionError("probe-session invalidation must not read")

    async def revalidate(self):
        result = self.revalidate_result
        if result.ok and isinstance(result.data, DebugFirmwareBinding):
            self._admission_token = object()
        else:
            self._invalidate_read_plan()
        return result

    async def _revalidate_lightweight(self):
        if self.lightweight_result is not None:
            return self.lightweight_result
        return self.revalidate_result

    def reset(self) -> None:
        self.reset_calls += 1
        raise AssertionError("observer reset fallback is forbidden")

    def resume(self) -> None:
        self.resume_calls += 1
        raise AssertionError("observer resume fallback is forbidden")

    def halt(self) -> None:
        self.halt_calls += 1
        raise AssertionError("observer halt fallback is forbidden")


def test_probe_session_projects_the_complete_snapshot_pair(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    session = ProbeSession(_FakeObservedSession(_debug_binding(project)))

    binding = session.binding
    assert binding.git_head is None and binding.git_dirty is None
    assert binding.source_baseline == SOURCE_BASELINE
    assert binding.git_evidence == HEAD_EVIDENCE
    assert isinstance(binding.git_evidence, MappingProxyType)
    assert (
        binding.build_id,
        binding.elf_sha256,
        binding.input_snapshot_sha256,
        binding.target_device,
        binding.physical_target,
        binding.session_id,
        binding.probe_id,
        binding.flash_session_id,
        binding.lease_id,
    ) == (
        "b" * 64,
        "e" * 64,
        "9" * 64,
        "STM32F407VGTx",
        "stm32f407vg",
        "monitor-1",
        "probe-serial-1",
        "flash-1",
        "lease-1",
    )
    document = binding.to_dict()
    assert document["gitHead"] is None and document["gitDirty"] is None
    assert document["sourceBaseline"] == SOURCE_BASELINE
    assert document["gitEvidence"] == HEAD_EVIDENCE
    with pytest.raises(TypeError):
        binding.git_evidence["rule"] = "status"  # type: ignore[index]


def test_probe_session_projection_preserves_legacy_git_form(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    session = ProbeSession(_FakeObservedSession(_legacy_debug_binding(project)))

    binding = session.binding
    assert binding.git_head == "A" * 40 and binding.git_dirty is False
    assert binding.source_baseline is None and binding.git_evidence is None
    document = binding.to_dict()
    assert set(document) == BINDING_FIELDS
    assert document["gitHead"] == "A" * 40
    assert "sourceBaseline" not in document and "gitEvidence" not in document


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    (
        ({"git_evidence": dict(HEAD_EVIDENCE, rule="status")}, "MONITOR_FIRMWARE_CHANGED"),
        (
            {
                "source_baseline": None,
                "git_evidence": None,
                "git_head": "a" * 40,
                "git_dirty": False,
            },
            "MONITOR_FIRMWARE_CHANGED",
        ),
        ({"input_snapshot_sha256": "8" * 64}, "MONITOR_FIRMWARE_CHANGED"),
        ({"elf_sha256": "7" * 64}, "MONITOR_FIRMWARE_CHANGED"),
        ({"build_id": "b" * 63 + "c"}, "MONITOR_FIRMWARE_CHANGED"),
        ({"flash_session_id": "flash-2"}, "MONITOR_FIRMWARE_CHANGED"),
        ({"observation_session_id": "monitor-2"}, "MONITOR_PROVENANCE_CHANGED"),
        ({"probe_id": "probe-serial-2"}, "MONITOR_PROVENANCE_CHANGED"),
        ({"lease_id": "lease-2"}, "MONITOR_PROVENANCE_CHANGED"),
        ({"target_device": "STM32F429ZITx"}, "MONITOR_PROVENANCE_CHANGED"),
        ({"debug_target": "stm32f429zi"}, "MONITOR_PROVENANCE_CHANGED"),
    ),
    ids=(
        "changed-evidence",
        "snapshot-to-legacy",
        "changed-input-snapshot",
        "changed-elf",
        "changed-build",
        "changed-flash-session",
        "changed-session",
        "changed-probe",
        "changed-lease",
        "changed-target",
        "changed-physical-target",
    ),
)
def test_probe_session_revalidation_rejects_changed_source_identity(
    tmp_path: Path, overrides: dict[str, object], expected_code: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observation = _FakeObservedSession(_debug_binding(project))
    session = ProbeSession(observation)
    changed = _debug_binding(project, **overrides)
    observation.revalidate_result = OperationResult.success("revalidate", changed)
    observation.lightweight_result = OperationResult.success("revalidate", changed)

    full = asyncio.run(session.revalidate())
    assert not full.ok and full.code == expected_code
    assert session._read_plan is None and session._admission_token is None

    lightweight = asyncio.run(session._revalidate_lightweight())
    assert not lightweight.ok and lightweight.code == expected_code
    assert (observation.reset_calls, observation.resume_calls, observation.halt_calls) == (
        0,
        0,
        0,
    )


def test_probe_session_legacy_identity_change_is_provenance_not_firmware(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observation = _FakeObservedSession(_legacy_debug_binding(project))
    session = ProbeSession(observation)

    unchanged = asyncio.run(session.revalidate())
    assert unchanged.ok

    changed = _legacy_debug_binding(project, observation_session_id="monitor-2")
    observation.revalidate_result = OperationResult.success("revalidate", changed)
    observation.lightweight_result = OperationResult.success("revalidate", changed)

    full = asyncio.run(session.revalidate())
    assert not full.ok and full.code == "MONITOR_PROVENANCE_CHANGED"
    assert session._read_plan is None and session._admission_token is None

    lightweight = asyncio.run(session._revalidate_lightweight())
    assert not lightweight.ok and lightweight.code == "MONITOR_PROVENANCE_CHANGED"
    assert (observation.reset_calls, observation.resume_calls, observation.halt_calls) == (
        0,
        0,
        0,
    )


def test_probe_session_accepts_an_unchanged_snapshot_pair(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observation = _FakeObservedSession(_debug_binding(project))
    session = ProbeSession(observation)

    full = asyncio.run(session.revalidate())
    lightweight = asyncio.run(session._revalidate_lightweight())

    assert full.ok and lightweight.ok
    assert observation._admission_token is not None
    assert (observation.reset_calls, observation.resume_calls, observation.halt_calls) == (
        0,
        0,
        0,
    )


# --- Runtime lifecycle with fake providers ---------------------------------------


MONITOR_PROJECT_MANIFEST = {
    "schemaVersion": 2,
    "logicalProjectId": "12345678-1234-5678-1234-567812345678",
    "generatedBy": {"tool": "stm32-toolkit", "version": "1.0.0"},
    "project": {"name": "monitor-fixture", "origin": "manual"},
    "target": {
        "device": "STM32F407VGTx",
        "core": "cortex-m4",
        "fpu": "fpv4-sp-d16",
        "floatAbi": "hard",
    },
    "framework": {"type": "spl", "version": None},
    "build": {
        "sources": ["Src/main.c"],
        "includePaths": [],
        "defines": [],
        "compileOptions": [],
        "assemblySources": [],
        "presets": ["arm-debug"],
        "elf": "build/arm-debug/firmware.elf",
    },
    "memory": {
        "source": "manual",
        "regions": [
            {
                "name": "FLASH",
                "origin": 134217728,
                "length": 1048576,
                "attributes": "r-x",
            },
            {
                "name": "RAM",
                "origin": 536870912,
                "length": 131072,
                "attributes": "rwx",
            },
        ],
    },
    "debug": {"backend": "pyocd", "target": "stm32f407vg", "svd": None},
    "generation": {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    },
}


def _monitor_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "Src").mkdir(parents=True)
    (project / "Src" / "main.c").write_bytes(b"int main(void){return 0;}\n")
    (project / ".stm32-project.json").write_bytes(
        json.dumps(MONITOR_PROJECT_MANIFEST, sort_keys=True).encode("utf-8")
    )
    return project.resolve()


class _FakeService:
    def __init__(self, _runtime, *, workspace_id, session_id, serve_ui=False, port=0):
        self.endpoint = SimpleNamespace(
            host="127.0.0.1",
            port=port or 39123,
            token="c" * 64,
            workspace_id=workspace_id,
            session_id=session_id,
            monitor_version=MONITOR_VERSION,
        )
        self.stop_calls = 0

    async def start(self):
        return self.endpoint

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeStore:
    def __init__(self, paths) -> None:
        self.paths = paths
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _FakeHistory(_FakeStore):
    def __init__(self, paths) -> None:
        super().__init__(paths)
        self.batches: list[HistoryBatchSlice] = []
        self.queries: list[object] = []

    def query_history(self, query):
        self.queries.append(query)
        return success(
            "history.query",
            {
                "batches": [batch.to_dict() for batch in self.batches],
                "valueCount": sum(len(batch.values) for batch in self.batches),
                "nextCursor": None,
                "serializedBytes": 0,
            },
        )


class _FakeExporter:
    def __init__(self, paths, history) -> None:
        self.paths = paths
        self.history = history
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _FakeMonitorObservation:
    def __init__(self, binding: ObservationBinding) -> None:
        self.binding = binding
        self.close_calls = 0
        self.reset_calls = 0
        self.resume_calls = 0
        self.halt_calls = 0

    async def close(self) -> None:
        self.close_calls += 1

    def reset(self) -> None:
        self.reset_calls += 1
        raise AssertionError("observer reset fallback is forbidden")

    def resume(self) -> None:
        self.resume_calls += 1
        raise AssertionError("observer resume fallback is forbidden")

    def halt(self) -> None:
        self.halt_calls += 1
        raise AssertionError("observer halt fallback is forbidden")


class _FakeSampler:
    def __init__(self, observation: _FakeMonitorObservation) -> None:
        self.observation = observation
        self.state = "IDLE"
        self.blocked_code = None
        self._group = None
        self._run_id = None
        self._sequence = 0
        self.subscriber_drops_total = 0
        self.history_drops_total = 0
        self.deadline_drops_total = 0
        self.close_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0

    async def start(self, group_id, *, expected_revision):
        self._group = SimpleNamespace(group_id=group_id, revision=expected_revision)
        self.state = "RUNNING"
        self._sequence = 1
        return success("sampling.start", {"started": True})

    async def subscribe_deliveries(self):
        yield SimpleNamespace(
            batch=_sample_batch(self.observation.binding), subscriber_drops=0
        )

    async def close(self) -> None:
        self.close_calls += 1

    def resume(self):
        self.resume_calls += 1
        raise AssertionError("sampler resume is not part of an observer fallback")

    def stop(self):
        self.stop_calls += 1
        raise AssertionError("sampler stop is not part of an observer fallback")


async def _next_event(stream, kind: str, *, attempts: int = 4):
    for _ in range(attempts):
        event = await asyncio.wait_for(stream.__anext__(), 2)
        if event["type"] == kind:
            return event
    raise AssertionError(f"no {kind} event was published")


def test_snapshot_status_connect_sample_history_and_release_stay_bound(
    tmp_path: Path,
) -> None:
    groups: list[_FakeStore] = []
    histories: list[_FakeHistory] = []
    exporters: list[_FakeExporter] = []
    samplers: list[_FakeSampler] = []
    observations: list[_FakeMonitorObservation] = []
    requests: list[object] = []
    services: list[_FakeService] = []

    def group_factory(paths):
        store = _FakeStore(paths)
        groups.append(store)
        return store

    def history_factory(paths):
        store = _FakeHistory(paths)
        histories.append(store)
        return store

    def exporter_factory(paths, history):
        exporter = _FakeExporter(paths, history)
        exporters.append(exporter)
        return exporter

    def service_factory(*args, **kwargs):
        service = _FakeService(*args, **kwargs)
        services.append(service)
        return service

    async def observation_factory(request):
        requests.append(request)
        observations.append(
            _FakeMonitorObservation(
                _snapshot_binding(
                    probe_id=request.probe_id,
                    build_id=request.expected_build_id,
                    elf_sha256=request.expected_elf_sha256,
                )
            )
        )
        return OperationResult.success("monitor.observe.open", observations[-1])

    async def probe_list(_request):
        return OperationResult.success(
            "stm32_probe_list",
            {
                "probes": (
                    {
                        "probeId": "probe-serial-1",
                        "vendor": "ST",
                        "product": "ST-LINK",
                        "boardName": None,
                    },
                )
            },
        )

    def sampler_factory(observation, _groups, _history):
        sampler = _FakeSampler(observation)
        samplers.append(sampler)
        return sampler

    project = _monitor_project(tmp_path)
    runtime = MonitorRuntime(
        group_store_factory=group_factory,
        history_store_factory=history_factory,
        exporter_factory=exporter_factory,
        sampler_factory=sampler_factory,
        observation_factory=observation_factory,
        firmware_status_factory=lambda _root: _snapshot_firmware(),
        probe_list_factory=probe_list,
        service_factory=service_factory,
    )
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "monitor-1")

    async def scenario() -> None:
        await runtime.start(config)
        stream = runtime.live_subscribe()
        hello = await asyncio.wait_for(stream.__anext__(), 2)
        boot = await asyncio.wait_for(stream.__anext__(), 2)
        assert hello["type"] == "hello" and boot["type"] == "state"
        assert boot["data"]["status"]["firmware"]["sourceBaseline"] == SOURCE_BASELINE

        status = await runtime.dispatch("monitor.status", {})
        assert status.ok
        assert status.data["firmware"] == _snapshot_firmware().to_dict()
        assert status.data["firmware"]["gitHead"] is None
        assert status.data["firmware"]["gitDirty"] is None
        assert status.data["firmware"]["gitEvidence"] == HEAD_EVIDENCE

        connected = await runtime.dispatch(
            "monitor.probe.connect", {"probeId": "probe-serial-1"}
        )
        assert connected.ok
        assert requests[0].expected_build_id == "b" * 64
        assert requests[0].expected_elf_sha256 == "e" * 64
        assert connected.data["gitHead"] is None
        assert connected.data["gitDirty"] is None
        assert connected.data["sourceBaseline"] == SOURCE_BASELINE
        assert connected.data["gitEvidence"] == HEAD_EVIDENCE
        assert runtime._observation is observations[0]
        assert runtime._sampler is samplers[0]

        connect_state = await _next_event(stream, "state")
        assert connect_state["data"]["status"]["probeConnected"] is True
        assert connect_state["data"]["status"]["firmware"]["gitEvidence"] == HEAD_EVIDENCE

        histories[0].batches = [_history_slice(observations[0].binding)]
        started = await runtime.dispatch(
            "monitor.sampling.start",
            {"groupId": str(GROUP_ID), "expectedRevision": 1},
        )
        assert started.ok
        sample_event = await _next_event(stream, "sample")
        batch = sample_event["data"]["batch"]
        assert batch["binding"]["gitHead"] is None
        assert batch["binding"]["gitDirty"] is None
        assert batch["binding"]["sourceBaseline"] == SOURCE_BASELINE
        assert batch["binding"]["gitEvidence"] == HEAD_EVIDENCE
        assert batch["values"][0]["status"] == "OK"

        running = await runtime.dispatch("monitor.status", {})
        assert running.data["sampling"]["state"] == "RUNNING"
        assert running.data["sampling"]["active"] is True

        history = await runtime.dispatch(
            "monitor.history.query", {}, query={"startNs": "0", "endNs": "2000"}
        )
        assert history.ok
        assert histories[0].queries[-1].session_id == "monitor-1"
        assert history.data["batches"][0]["binding"]["inputSnapshotSha256"] == "9" * 64
        assert history.data["batches"][0]["binding"]["sourceBaseline"] == SOURCE_BASELINE
        assert history.data["batches"][0]["binding"]["gitEvidence"] == HEAD_EVIDENCE

        released = await runtime.dispatch("monitor.probe.release", {})
        assert released.ok and released.data == {"released": True}
        assert observations[0].close_calls == 1
        assert samplers[0].close_calls == 1
        assert runtime._observation is None and runtime._sampler is None
        assert (
            observations[0].reset_calls,
            observations[0].resume_calls,
            observations[0].halt_calls,
        ) == (0, 0, 0)

        release_state = await _next_event(stream, "state")
        assert release_state["data"]["status"]["probeConnected"] is False
        assert release_state["data"]["status"]["sampling"]["state"] == "IDLE"
        assert release_state["data"]["status"]["firmware"]["gitHead"] is None
        assert (
            release_state["data"]["status"]["firmware"]["sourceBaseline"]
            == SOURCE_BASELINE
        )

        await runtime.stop()
        assert services[0].stop_calls == 1
        assert groups[0].close_calls == 1
        assert histories[0].close_calls == 1
        assert exporters[0].close_calls == 1
        assert runtime._paths is None and runtime._lock is None

    asyncio.run(scenario())
