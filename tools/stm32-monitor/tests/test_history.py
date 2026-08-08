from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.groups import GroupStore
from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchGroup, WatchItem
from stm32_monitor.storage import StorageFailure
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, LOGICAL_ID, "monitor-1")


def _binding(paths: WorkspacePaths) -> ObservationBinding:
    return ObservationBinding(
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
        svd_sha256="a" * 64,
    )


def _batch(paths: WorkspacePaths, sequence: int, *, captured_ns: int | None = None, value: object = 7) -> SampleBatch:
    captured = captured_ns if captured_ns is not None else 1_000_000_000 + sequence
    return SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=sequence,
        scheduled_unix_ns=captured - 100,
        captured_unix_ns=captured,
        latency_ns=100,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value={"type": "uint32", "value": value}),),
    )


def test_missing_history_is_empty_and_does_not_create_database(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        result = store.query_history(HistoryQuery(session_id="monitor-1", start_ns=0, end_ns=2_000_000_000))
        assert result.ok and result.data.values == () and result.data.next_cursor is None
        assert not paths.monitor_root.exists()
    finally:
        store.close()


def test_append_and_half_open_query_preserve_full_immutable_evidence(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        result = store.query_history(HistoryQuery(session_id="monitor-1", start_ns=100, end_ns=200))
        assert result.ok and len(result.data.values) == 1
        row = result.data.values[0]
        assert row["binding"]["elfSha256"] == "e" * 64
        assert row["groupId"] == str(GROUP_ID)
        assert row["groupRevision"] == 3
        assert row["runId"] == str(RUN_ID)
        assert row["sequence"] == 1
        assert row["subscriberDrops"] == 1
        assert row["historyDrops"] == 2
        assert row["deadlineDrops"] == 3
        assert row["watch"] == {"kind": "variable", "expression": "counter"}
    finally:
        store.close()


def test_history_survives_group_rename_and_delete(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    groups = GroupStore(paths)
    history = HistoryStore(paths)
    try:
        created = groups.create_group("Original", "", 250, (), authorized=True).data
        batch = _batch(paths, 1)
        batch = SampleBatch(
            binding=batch.binding,
            group_id=created.group_id,
            group_revision=created.revision,
            run_id=batch.run_id,
            sequence=batch.sequence,
            scheduled_unix_ns=batch.scheduled_unix_ns,
            captured_unix_ns=batch.captured_unix_ns,
            latency_ns=batch.latency_ns,
            actual_rate_hz=batch.actual_rate_hz,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=batch.values,
        )
        assert history.append_batch(batch).ok
        assert groups.delete_group(created.group_id, expected_revision=1, authorized=True).ok
        result = history.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert len(result.data.values) == 1
    finally:
        groups.close()
        history.close()


def test_history_paging_caps_values_and_serialized_bytes(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        for sequence in range(5):
            assert store.append_batch(_batch(paths, sequence, value="x" * 80)).ok
        monkeypatch.setattr(history_module, "MAX_HISTORY_VALUES", 2)
        monkeypatch.setattr(history_module, "MAX_HISTORY_PAGE_BYTES", 3_000)
        first = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000, limit=10))
        assert first.ok and len(first.data.values) == 2 and first.data.next_cursor is not None
        second = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000, limit=10, cursor=first.data.next_cursor))
        assert second.ok and second.data.values[0]["sequence"] > first.data.values[-1]["sequence"]
    finally:
        store.close()


def test_invalid_query_and_workspace_mismatch_fail_closed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        invalid = store.query_history(HistoryQuery("monitor-1", 10, 10))
        assert not invalid.ok and invalid.code == "MONITOR_HISTORY_QUERY_INVALID"
        wrong_binding = _binding(paths).to_dict()
        wrong_binding["workspaceId"] = "x" * 64
        with pytest.raises(ValueError):
            ObservationBinding.from_dict(wrong_binding)
    finally:
        store.close()


def test_duplicate_batch_is_rejected_without_duplicate_values(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        duplicate = store.append_batch(_batch(paths, 1))
        assert not duplicate.ok and duplicate.code == "MONITOR_STORAGE_INVALID"
        page = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert len(page.data.values) == 1
    finally:
        store.close()


def test_retention_removes_expired_and_budget_excess_in_bounded_chunks(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        monkeypatch.setattr(history_module, "RETENTION_AGE_NS", 1_000)
        monkeypatch.setattr(history_module, "RETENTION_LOGICAL_BYTES", 1_200)
        monkeypatch.setattr(history_module, "RETENTION_DELETE_BATCHES", 2)
        for sequence, captured in enumerate((100, 200, 9_500, 9_600, 9_700)):
            assert store.append_batch(_batch(paths, sequence, captured_ns=captured, value="x" * 250)).ok
        retained = store.run_retention(now_ns=10_000)
        assert retained.ok and retained.data["deletedBatches"] == 2
        assert retained.data["moreWork"] is True
        assert retained.data["earliestCapturedUnixNs"] == 9_500
        page = store.query_history(HistoryQuery("monitor-1", 0, 20_000))
        assert all(row["capturedUnixNs"] >= 9_000 for row in page.data.values)
        assert len(page.data.values) == 3
        assert retained.data["passes"] == 1
    finally:
        store.close()


def test_database_plus_wal_hard_stop_prevents_new_batch(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        monkeypatch.setattr(storage_module, "MAX_DATABASE_BYTES", 1)
        full = store.append_batch(_batch(paths, 2))
        assert not full.ok and full.code == "MONITOR_STORAGE_FULL"
    finally:
        store.close()


def test_database_limit_crossing_rolls_back_the_admitted_batch(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        size_before = store._database._size()
        monkeypatch.setattr(storage_module, "MAX_DATABASE_BYTES", size_before + 1)

        full = store.append_batch(_batch(paths, 2, value="x" * 100_000))
        assert not full.ok and full.code == "MONITOR_STORAGE_FULL"
        page = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert page.ok
        assert [row["sequence"] for row in page.data.values] == [1]
    finally:
        store.close()


def test_wrong_workspace_batch_invalid_cursor_and_oversized_row_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        wrong = _binding(paths).to_dict()
        wrong["workspaceId"] = "c" * 24
        batch = _batch(paths, 1)
        foreign = SampleBatch(
            binding=ObservationBinding.from_dict(wrong), group_id=batch.group_id,
            group_revision=batch.group_revision, run_id=batch.run_id, sequence=batch.sequence,
            scheduled_unix_ns=batch.scheduled_unix_ns, captured_unix_ns=batch.captured_unix_ns,
            latency_ns=batch.latency_ns, actual_rate_hz=batch.actual_rate_hz,
            subscriber_drops=0, history_drops=0, deadline_drops=0, values=batch.values,
        )
        assert store.append_batch(foreign).code == "MONITOR_WORKSPACE_MISMATCH"
        assert store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000, cursor="bad")).code == "MONITOR_HISTORY_QUERY_INVALID"

        assert store.append_batch(batch).ok
        monkeypatch.setattr(history_module, "MAX_HISTORY_PAGE_BYTES", 1)
        assert store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000)).code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_invalid_retention_and_empty_retention_do_not_create_storage(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.run_retention(now_ns=-1).code == "MONITOR_REQUEST_INVALID"
        result = store.run_retention(now_ns=10_000)
        assert result.ok and result.data == {
            "deletedBatches": 0,
            "logicalBytes": 0,
            "passes": 0,
            "moreWork": False,
            "earliestCapturedUnixNs": None,
        }
        assert not paths.monitor_root.exists()
    finally:
        store.close()


@pytest.mark.parametrize(
    "replacement",
    [
        b"\xff",
        b"[]",
        b'{"actualRateHz":NaN}',
        7,
    ],
)
def test_corrupt_history_row_never_leaks_json_unicode_or_type_errors(
    tmp_path: Path,
    replacement: object,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_values SET row_json = ?, payload_bytes = ?",
                (replacement, len(replacement) if isinstance(replacement, bytes) else 1),
            )
        )
        result = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert not result.ok
        assert result.code == "MONITOR_STORAGE_CORRUPT"
        assert result.message == "monitor history is corrupt"
        assert result.details == {}
    finally:
        store.close()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("binding", []),
        ("watch", []),
        ("status", 1),
        ("definition", []),
        ("valueOrdinal", 1),
        ("scheduledAtUtc", "1970-01-01T00:00:00.000000Z"),
        ("capturedAtUtc", "1970-01-01T00:00:00.000000Z"),
        ("actualRateHz", "5.0"),
    ],
)
def test_each_history_model_semantic_mismatch_is_storage_corruption(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        raw = store._database.read(
            lambda connection: connection.execute(
                "SELECT row_json FROM history_values"
            ).fetchone()[0],
            empty=None,
        )
        decoded = json.loads(bytes(raw).decode("utf-8"))
        decoded[field] = replacement
        invalid = json.dumps(decoded, separators=(",", ":")).encode("utf-8")
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_values SET row_json = ?, payload_bytes = ?",
                (invalid, len(invalid)),
            )
        )
        assert store.query_history(
            HistoryQuery("monitor-1", 0, 2_000_000_000)
        ).code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_history_page_stops_before_crossing_byte_limit(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        assert store.append_batch(_batch(paths, 2)).ok
        row_size = store._database.read(
            lambda connection: connection.execute(
                "SELECT payload_bytes FROM history_values ORDER BY batch_id LIMIT 1"
            ).fetchone()[0],
            empty=0,
        )
        monkeypatch.setattr(history_module, "MAX_HISTORY_PAGE_BYTES", row_size + 1)
        page = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert page.ok and len(page.data.values) == 1 and page.data.next_cursor is not None
    finally:
        store.close()


def test_retention_budget_deadline_and_failure_mapping_are_bounded(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=9_500)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=9_600)).ok
        monkeypatch.setattr(history_module, "RETENTION_AGE_NS", 100_000)
        monkeypatch.setattr(history_module, "RETENTION_LOGICAL_BYTES", 1)
        monkeypatch.setattr(history_module, "RETENTION_DELETE_BATCHES", 1)
        monkeypatch.setattr(history_module.time, "monotonic_ns", lambda: 0)
        retained = store.run_retention(now_ns=10_000)
        assert retained.ok
        assert retained.data["deletedBatches"] == 1
        assert retained.data["moreWork"] is True

        monkeypatch.setattr(
            store._database,
            "try_write",
            lambda operation, timeout_ms: (_ for _ in ()).throw(
                StorageFailure("MONITOR_RETENTION_FAILED", "internal")
            ),
        )
        failed = store.run_retention(now_ns=10_000)
        assert failed.code == "MONITOR_RETENTION_FAILED"
        assert failed.message == "history retention failed"
    finally:
        store.close()


def test_retention_query_plan_uses_time_index_without_temporary_sort(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        plan = store._database.read(
            lambda connection: connection.execute(
                "EXPLAIN QUERY PLAN SELECT batch_id FROM history_batches "
                "WHERE captured_ns < ? ORDER BY captured_ns, batch_id LIMIT ?",
                (1_000, 101),
            ).fetchall(),
            empty=(),
        )
        plan_text = " ".join(str(row[3]) for row in plan)
        assert "history_retention_time" in plan_text
        assert "TEMP B-TREE" not in plan_text
    finally:
        store.close()


def test_retention_deadline_aborts_before_mutation(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        monkeypatch.setattr(history_module, "RETENTION_AGE_NS", 1)
        ticks = iter((0, history_module.RETENTION_TIME_BUDGET_NS))
        monkeypatch.setattr(history_module.time, "monotonic_ns", lambda: next(ticks))
        expired = store.run_retention(now_ns=1_000)
        assert not expired.ok and expired.code == "MONITOR_STORAGE_BUSY"
        page = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert page.ok and len(page.data.values) == 1
    finally:
        store.close()


def test_history_integer_binding_failures_map_to_stable_protocol_results(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        batch = _batch(paths, 1)
        object.__setattr__(batch, "sequence", 2**63)
        appended = store.append_batch(batch)
        assert not appended.ok and appended.code == "MONITOR_STORAGE_INVALID"

        queried = store.query_history(
            HistoryQuery("monitor-1", 2**63, 2**63 + 1)
        )
        assert not queried.ok and queried.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_history_wrong_query_type_and_storage_failure_fail_stably(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    assert store.query_history(object()).code == "MONITOR_HISTORY_QUERY_INVALID"
    assert store.append_batch(_batch(paths, 1)).ok
    monkeypatch.setattr(
        store._database,
        "read",
        lambda operation, empty: (_ for _ in ()).throw(
            StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is unavailable")
        ),
    )
    assert store.run_retention(now_ns=10_000).code == "MONITOR_STORAGE_INVALID"
    store.close()


def test_semantically_invalid_and_oversized_history_rows_are_storage_corruption(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        raw = store._database.read(
            lambda connection: connection.execute(
                "SELECT row_json FROM history_values"
            ).fetchone()[0],
            empty=None,
        )
        decoded = json.loads(bytes(raw).decode("utf-8"))
        decoded["groupId"] = "not-a-uuid"
        invalid = json.dumps(decoded, separators=(",", ":")).encode("utf-8")
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_values SET row_json = ?, payload_bytes = ?",
                (invalid, len(invalid)),
            )
        )
        semantic = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert semantic.code == "MONITOR_STORAGE_CORRUPT"

        assert store.append_batch(_batch(paths, 2)).ok
        monkeypatch.setattr(history_module, "MAX_HISTORY_PAGE_BYTES", 1)
        oversized = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert oversized.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()
