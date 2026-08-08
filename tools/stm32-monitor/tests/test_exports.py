from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from types import SimpleNamespace
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.exports import ExportRequest, HistoryExporter
from stm32_monitor.history import HistoryPage, HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.protocol import failure, success
from stm32_monitor.storage import StorageFailure
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
        assert artifact.to_dict() == {
            "exportId": str(artifact.export_id),
            "format": "jsonl",
            "sha256": artifact.sha256,
            "bytes": artifact.byte_count,
            "valueCount": 1,
        }
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


@pytest.mark.parametrize("phase", ["data", "manifest"])
def test_export_exclusive_creation_never_truncates_a_raced_hardlink(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    sentinel = tmp_path / f"external-{phase}.txt"
    sentinel.write_bytes(b"external-sentinel")
    before = sentinel.read_bytes()
    try:
        _append(paths, history)
        real_stream = exporter._stream_history

        def raced_stream(request: ExportRequest, target: Path):
            if phase == "data":
                os.link(sentinel, target)
                return real_stream(request, target)
            result = real_stream(request, target)
            os.link(sentinel, target.parent / "manifest.json")
            return result

        monkeypatch.setattr(exporter, "_stream_history", raced_stream)
        result = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"),
            authorized=True,
        )
        assert not result.ok and result.code == "MONITOR_EXPORT_FAILED"
        assert sentinel.read_bytes() == before
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
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 0, 2**63, "jsonl")


def test_exporter_constructor_and_create_reject_wrong_public_types(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    try:
        with pytest.raises(TypeError):
            HistoryExporter(paths, object())
        exporter = HistoryExporter(paths, history)
        try:
            assert exporter.create_export(object(), authorized=True).code == "MONITOR_REQUEST_INVALID"
        finally:
            exporter.close()
    finally:
        history.close()


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


def test_csv_export_and_get_stream_without_path_read_bytes(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "safe")

        def forbidden_read_bytes(self: Path) -> bytes:
            raise AssertionError(f"unbounded read_bytes used for {self.name}")

        monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True)
        assert created.ok
        loaded = exporter.get_export(created.data.export_id)
        assert loaded.ok and loaded.data.byte_count == created.data.byte_count
    finally:
        exporter.close()
        history.close()


def test_workspace_export_count_and_byte_quotas_are_enforced(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "quota")
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORTS", 1)
        first = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert first.ok
        count_limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert count_limited.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"

        with sqlite3.connect(paths.monitor_root / "monitor.sqlite3") as connection:
            connection.execute("DELETE FROM export_records")
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORTS", 100)
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORT_BYTES", first.data.byte_count - 1)
        byte_limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert byte_limited.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"
    finally:
        exporter.close()
        history.close()


def test_pending_exports_reserve_workspace_bytes_before_streaming(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    request = ExportRequest("monitor-1", 0, 1_000, "jsonl")
    monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 100)
    monkeypatch.setattr(exports_module, "MAX_MANIFEST_BYTES", 10)
    monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORT_BYTES", 110)
    try:
        first = UUID("11111111-1111-4111-8111-111111111111")
        second = UUID("22222222-2222-4222-8222-222222222222")
        exporter._reserve_pending(
            first,
            request,
            f"exports/monitor-1/{first}/history.jsonl",
            f"exports/monitor-1/{first}/manifest.json",
            "2026-08-08T00:00:00.000000Z",
        )
        with pytest.raises(StorageFailure) as full:
            exporter._reserve_pending(
                second,
                request,
                f"exports/monitor-1/{second}/history.jsonl",
                f"exports/monitor-1/{second}/manifest.json",
                "2026-08-08T00:00:01.000000Z",
            )
        assert full.value.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"
    finally:
        exporter.close()
        history.close()


def test_startup_recovers_atomically_published_pending_export(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = ? WHERE export_id = ?",
                ("PENDING:jsonl", str(created.export_id)),
            )
        )
        recovered = HistoryExporter(paths, history)
        loaded = recovered.get_export(created.export_id)
        assert loaded.ok and loaded.data == created
        with sqlite3.connect(paths.monitor_root / "monitor.sqlite3") as connection:
            assert connection.execute(
                "SELECT format FROM export_records WHERE export_id = ?",
                (str(created.export_id),),
            ).fetchone() == ("jsonl",)
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_recovery_progresses_past_ten_records_and_removes_poison_head(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        artifacts = [
            exporter.create_export(
                ExportRequest("monitor-1", 0, 1_000, "jsonl"),
                authorized=True,
            ).data
            for _ in range(12)
        ]

        def make_pending(connection: sqlite3.Connection) -> None:
            connection.execute("UPDATE export_records SET format = 'PENDING:jsonl'")
            connection.execute(
                "INSERT INTO export_records(export_id,session_id,format,relative_data_path,"
                "relative_manifest_path,sha256,byte_count,value_count,created_at_utc) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "not-a-uuid", "monitor-1", "PENDING:jsonl", "invalid", "invalid",
                    "0" * 64, 0, 0, "0001-01-01T00:00:00.000000Z",
                ),
            )

        exporter._database.write(make_pending)
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(artifacts[-1].export_id).ok
        pending = recovered._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records WHERE format LIKE 'PENDING:%'"
            ).fetchone()[0],
            empty=-1,
        )
        poison = recovered._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records WHERE export_id = 'not-a-uuid'"
            ).fetchone()[0],
            empty=-1,
        )
        assert pending == 0 and poison == 0
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_get_export_rejects_manifest_shape_recorded_path_and_multiple_links(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        first = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        manifest["unexpected"] = True
        first.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert exporter.get_export(first.export_id).code == "MONITOR_EXPORT_FAILED"

        second = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET relative_data_path = relative_manifest_path WHERE export_id = ?",
                (str(second.export_id),),
            )
        )
        assert exporter.get_export(second.export_id).code == "MONITOR_EXPORT_FAILED"

        third = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        extra_link = third.directory / "extra-link.jsonl"
        os.link(third.data_path, extra_link)
        assert exporter.get_export(third.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


def test_export_propagates_history_failure_and_rejects_stalled_cursor(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        monkeypatch.setattr(
            history,
            "query_history",
            lambda query: failure("history.query", "MONITOR_STORAGE_CORRUPT", "monitor history is corrupt"),
        )
        corrupt = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert corrupt.code == "MONITOR_STORAGE_CORRUPT"

        monkeypatch.setattr(
            history,
            "query_history",
            lambda query: success("history.query", HistoryPage((), "1:0", 0)),
        )
        stalled = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert stalled.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        exporter.close()
        history.close()


def test_get_export_enforces_limit_nonfinite_manifest_and_record_digest(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", limited.byte_count - 1)
        assert exporter.get_export(limited.export_id).code == "MONITOR_EXPORT_FAILED"
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 64 * 1024 * 1024)

        nonfinite = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        manifest_text = nonfinite.manifest_path.read_text(encoding="utf-8")
        manifest_text = manifest_text.replace(f'"bytes":{nonfinite.byte_count}', '"bytes":NaN')
        nonfinite.manifest_path.write_text(manifest_text, encoding="utf-8")
        assert exporter.get_export(nonfinite.export_id).code == "MONITOR_EXPORT_FAILED"

        record = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET sha256 = ? WHERE export_id = ?",
                ("0" * 64, str(record.export_id)),
            )
        )
        assert exporter.get_export(record.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("phase", ["opened", "after"])
def test_get_export_rejects_file_identity_change_during_bounded_read(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        real_fstat = os.fstat
        calls = 0

        def changed_fstat(descriptor: int):
            nonlocal calls
            metadata = real_fstat(descriptor)
            calls += 1
            change_now = (phase == "opened" and calls == 1) or (phase == "after" and calls == 2)
            if not change_now:
                return metadata
            return SimpleNamespace(
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino + 1,
                st_size=metadata.st_size,
                st_nlink=metadata.st_nlink,
            )

        monkeypatch.setattr(exports_module.os, "fstat", changed_fstat)
        with pytest.raises(ValueError):
            exports_module._read_regular_limited(
                artifact.data_path,
                limit=exports_module.MAX_EXPORT_BYTES,
                keep=False,
            )
    finally:
        exporter.close()
        history.close()


def test_bounded_reader_revalidates_the_recorded_name_after_hashing(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    target = tmp_path / "artifact.jsonl"
    target.write_bytes(b"one line\n")
    real_lstat = os.lstat
    calls = 0

    def replaced_name(path: Path):
        nonlocal calls
        metadata = real_lstat(path)
        calls += 1
        if calls == 1:
            return metadata
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino + 1,
            st_size=metadata.st_size,
            st_nlink=metadata.st_nlink,
            st_file_attributes=getattr(metadata, "st_file_attributes", 0),
        )

    monkeypatch.setattr(exports_module.os, "lstat", replaced_name)
    with pytest.raises(ValueError):
        exports_module._read_regular_limited(target, limit=1024, keep=False)


def test_failed_ready_transition_remains_pending_and_recovers(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        original_mark_ready = exporter._mark_ready
        monkeypatch.setattr(
            exporter,
            "_mark_ready",
            lambda artifact, format_name, created_at_utc: (_ for _ in ()).throw(
                StorageFailure("MONITOR_EXPORT_FAILED", "interrupted")
            ),
        )
        failed = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert failed.code == "MONITOR_EXPORT_FAILED"
        pending_id = UUID(
            exporter._database.read(
                lambda connection: connection.execute(
                    "SELECT export_id FROM export_records WHERE format = 'PENDING:jsonl'"
                ).fetchone()[0],
                empty=None,
            )
        )
        monkeypatch.setattr(exporter, "_mark_ready", original_mark_ready)
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(pending_id).ok
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_startup_discards_incomplete_pending_export_and_bounds_recovery(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    bounded = None
    try:
        _append(paths, history)
        incomplete = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = 'PENDING:jsonl' WHERE export_id = ?",
                (str(incomplete.export_id),),
            )
        )
        incomplete.manifest_path.unlink()
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(incomplete.export_id).code == "MONITOR_EXPORT_FAILED"
        assert not incomplete.directory.exists()

        waiting = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = 'PENDING:jsonl' WHERE export_id = ?",
                (str(waiting.export_id),),
            )
        )
        ticks = iter((0, exports_module.RECOVERY_TIME_BUDGET_NS))
        monkeypatch.setattr(exports_module.time, "monotonic_ns", lambda: next(ticks))
        bounded = HistoryExporter(paths, history)
        pending_format = bounded._database.read(
            lambda connection: connection.execute(
                "SELECT format FROM export_records WHERE export_id = ?",
                (str(waiting.export_id),),
            ).fetchone()[0],
            empty=None,
        )
        assert pending_format == "PENDING:jsonl"
    finally:
        if bounded is not None:
            bounded.close()
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_get_export_maps_storage_failure_without_raw_exception(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        monkeypatch.setattr(
            exporter._database,
            "read",
            lambda operation, empty: (_ for _ in ()).throw(
                StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is unavailable")
            ),
        )
        assert exporter.get_export(artifact.export_id).code == "MONITOR_STORAGE_INVALID"
    finally:
        exporter.close()
        history.close()
