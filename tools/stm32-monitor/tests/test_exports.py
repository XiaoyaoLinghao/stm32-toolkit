from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.exports import ExportRequest, HistoryExporter
from stm32_monitor.history import HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, LOGICAL_ID, "monitor-1")


def _append(paths: WorkspacePaths, history: HistoryStore, value: object = 7) -> None:
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id=str(LOGICAL_ID),
        session_id="monitor-1",
        probe_id="probe-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256=None,
    )
    batch = SampleBatch(
        binding=binding,
        group_id=GROUP_ID,
        group_revision=1,
        run_id=RUN_ID,
        sequence=1,
        scheduled_unix_ns=100,
        captured_unix_ns=200,
        latency_ns=100,
        actual_rate_hz=4.0,
        subscriber_drops=0,
        history_drops=0,
        deadline_drops=0,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value={"type": "string", "value": value}),),
    )
    assert history.append_batch(batch).ok


def test_export_requires_exact_authorization_and_uses_server_owned_path(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        denied = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized="true")
        assert not denied.ok and denied.code == "MONITOR_AUTH_REQUIRED"
        assert not paths.monitor_root.exists()

        _append(paths, history)
        result = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert result.ok
        artifact = result.data
        assert artifact.directory.parent == paths.monitor_root / "exports" / "monitor-1"
        assert artifact.data_path.is_file() and artifact.manifest_path.is_file()
        assert paths.project_root.joinpath("export.jsonl").exists() is False
    finally:
        exporter.close()
        history.close()


def test_jsonl_export_manifest_binds_sha_size_count_and_protocol(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        data = artifact.data_path.read_bytes()
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        assert manifest["protocol"] == "stm32-toolkit-monitor/1"
        assert manifest["workspaceId"] == paths.workspace_id
        assert manifest["sha256"] == hashlib.sha256(data).hexdigest()
        assert manifest["bytes"] == len(data)
        assert manifest["valueCount"] == 1
        assert len(data.splitlines()) == 1
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("dangerous", ["=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tformula", "\rformula"])
def test_csv_export_neutralizes_formula_cells(tmp_path: Path, dangerous: str) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, dangerous)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True).data
        rows = list(csv.DictReader(artifact.data_path.open(encoding="utf-8", newline="")))
        typed_value = json.loads(rows[0]["typedValue"])
        assert typed_value["value"].startswith("'")
        assert typed_value["value"][1:] == dangerous
    finally:
        exporter.close()
        history.close()


def test_export_size_and_value_quotas_fail_without_published_directory(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "x" * 200)
        monkeypatch.setattr(exports_module, "MAX_EXPORT_VALUES", 0)
        too_many = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not too_many.ok and too_many.code == "MONITOR_EXPORT_TOO_LARGE"

        monkeypatch.setattr(exports_module, "MAX_EXPORT_VALUES", 10)
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 32)
        too_large = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not too_large.ok and too_large.code == "MONITOR_EXPORT_TOO_LARGE"
        export_root = paths.monitor_root / "exports" / "monitor-1"
        assert not export_root.exists() or list(export_root.iterdir()) == []
    finally:
        exporter.close()
        history.close()


def test_export_replace_failure_is_atomic_and_returns_stable_failure(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        monkeypatch.setattr(exports_module, "_replace", lambda source, target: (_ for _ in ()).throw(OSError("secret path")))
        failed = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not failed.ok and failed.code == "MONITOR_EXPORT_FAILED"
        assert "secret" not in failed.message and failed.details == {}
        export_root = paths.monitor_root / "exports" / "monitor-1"
        assert not export_root.exists() or list(export_root.iterdir()) == []
    finally:
        exporter.close()
        history.close()


def test_export_request_rejects_bad_format_range_and_session() -> None:
    with pytest.raises(ValueError):
        ExportRequest("../bad", 0, 1, "jsonl")
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 2, 1, "jsonl")
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 0, 1, "xlsx")


def test_export_metadata_is_retrieved_only_by_id_and_detects_tampering(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        loaded = exporter.get_export(created.export_id)
        assert loaded.ok and loaded.data == created
        assert exporter.get_export("not-a-uuid").code == "MONITOR_REQUEST_INVALID"
        assert exporter.get_export(UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")).code == "MONITOR_EXPORT_FAILED"

        created.data_path.write_bytes(b"tampered")
        assert exporter.get_export(created.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()
