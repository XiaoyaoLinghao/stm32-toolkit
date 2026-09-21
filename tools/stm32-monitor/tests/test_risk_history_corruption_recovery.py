from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from stm32_monitor.exports import ExportRequest, HistoryExporter
from stm32_monitor.history import HistoryQuery, HistoryStore, flatten_history_page
from test_history import _batch, _compact, _paths, _wide_batch


def _history_state(database: Path) -> tuple[object, ...]:
    with sqlite3.connect(database) as connection:
        batches = tuple(
            connection.execute(
                "SELECT batch_id,session_id,run_id,sequence,captured_ns,"
                "payload_json,payload_bytes,payload_sha256,value_count "
                "FROM history_batches ORDER BY batch_id"
            )
        )
        values = tuple(
            connection.execute(
                "SELECT batch_id,ordinal,selector_kind,selector,value_json,"
                "value_bytes,value_sha256 FROM history_values "
                "ORDER BY batch_id,ordinal"
            )
        )
        accounting = connection.execute(
            "SELECT singleton,logical_bytes FROM monitor_history_accounting"
        ).fetchone()
    return batches, values, accounting


def _files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_invalid_append_recovers_through_public_store(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        rejected = store.append_batches((object(),))  # type: ignore[arg-type]
        assert not rejected.ok
        assert rejected.code == "MONITOR_REQUEST_INVALID"
        assert rejected.message == "sample batch collection is invalid"
        assert not paths.monitor_root.exists()

        appended = store.append_batch(_batch(paths, 1, captured_ns=100))
        assert appended.ok
        queried = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert queried.ok and queried.data is not None
        assert [row["sequence"] for row in flatten_history_page(queried.data)] == [1]
    finally:
        store.close()


def test_wrong_watch_payload_refuses_and_reuses_after_exact_restore(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    database = paths.monitor_root / "monitor.sqlite3"
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        before = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert before.ok

        with sqlite3.connect(database) as connection:
            original_raw, original_bytes, original_digest = connection.execute(
                "SELECT payload_json,payload_bytes,payload_sha256 "
                "FROM history_batches WHERE batch_id = 1"
            ).fetchone()
            assert type(original_raw) is bytes
            payload = json.loads(original_raw)
            payload["values"][0]["watch"] = {
                "kind": "variable",
                "registerPath": "R0",
            }
            corrupted = _compact(payload)
            connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ? WHERE batch_id = 1",
                (corrupted, len(corrupted), sha256(corrupted).hexdigest()),
            )
            connection.commit()

        corrupted_state = _history_state(database)
        refused = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert not refused.ok
        assert refused.code == "MONITOR_STORAGE_CORRUPT"
        assert refused.message == "monitor history is corrupt"
        assert _history_state(database) == corrupted_state

        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ? WHERE batch_id = 1",
                (original_raw, original_bytes, original_digest),
            )
            connection.commit()
        restored = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert restored.ok and restored.data is not None
        assert [row["sequence"] for row in flatten_history_page(restored.data)] == [1]
    finally:
        store.close()


def test_shortened_cursor_batch_refuses_and_resumes_after_restore(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    database = paths.monitor_root / "monitor.sqlite3"
    query = HistoryQuery("monitor-1", 0, 1_000, limit=2)
    try:
        assert store.append_batch(_wide_batch(paths, 1, captured_ns=100, count=2)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        first = store.query_history(query)
        assert (
            first.ok and first.data is not None and first.data.next_cursor is not None
        )
        assert first.data.value_count == 2
        cursor = first.data.next_cursor

        with sqlite3.connect(database) as connection:
            original_batch = connection.execute(
                "SELECT payload_json,payload_bytes,payload_sha256,value_count "
                "FROM history_batches WHERE batch_id = 1"
            ).fetchone()
            original_values = tuple(
                connection.execute(
                    "SELECT batch_id,ordinal,selector_kind,selector,value_json,"
                    "value_bytes,value_sha256 FROM history_values "
                    "WHERE batch_id = 1 ORDER BY ordinal"
                )
            )
            assert original_batch is not None and len(original_values) == 2
            original_payload = json.loads(original_batch[0])
            original_payload["values"] = original_payload["values"][:1]
            shortened = _compact(original_payload)
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "DELETE FROM history_values WHERE batch_id = 1 AND ordinal = 1"
            )
            connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ?, value_count = 1 WHERE batch_id = 1",
                (shortened, len(shortened), sha256(shortened).hexdigest()),
            )
            connection.commit()

        corrupted_state = _history_state(database)
        resumed = store.query_history(replace(query, cursor=cursor))
        assert not resumed.ok
        assert resumed.code == "MONITOR_STORAGE_CORRUPT"
        assert resumed.message == "monitor history is corrupt"
        assert _history_state(database) == corrupted_state

        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ?, value_count = ? WHERE batch_id = 1",
                original_batch,
            )
            connection.execute("DELETE FROM history_values WHERE batch_id = 1")
            connection.executemany(
                "INSERT INTO history_values(batch_id,ordinal,selector_kind,selector,"
                "value_json,value_bytes,value_sha256) VALUES (?,?,?,?,?,?,?)",
                original_values,
            )
            connection.commit()
        restored = store.query_history(replace(query, cursor=cursor))
        assert restored.ok and restored.data is not None
        assert [row["sequence"] for row in flatten_history_page(restored.data)] == [2]
    finally:
        store.close()


def test_export_rejects_non_bytes_payload_and_reuses_after_restore(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    exporter: HistoryExporter | None = None
    database = paths.monitor_root / "monitor.sqlite3"
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        exporter = HistoryExporter(paths, store)
        with sqlite3.connect(database) as connection:
            original_raw, original_bytes, original_digest = connection.execute(
                "SELECT payload_json,payload_bytes,payload_sha256 "
                "FROM history_batches WHERE batch_id = 1"
            ).fetchone()
            connection.execute(
                "UPDATE history_batches SET payload_json = 42 WHERE batch_id = 1"
            )
            connection.commit()

        corrupted_state = _history_state(database)
        failed = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"),
            authorized=True,
        )
        assert not failed.ok
        assert failed.code == "MONITOR_STORAGE_CORRUPT"
        assert failed.message == "monitor history is corrupt"
        assert _history_state(database) == corrupted_state
        with sqlite3.connect(database) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM export_records WHERE format LIKE 'PENDING:%'"
                ).fetchone()[0]
                == 0
            )
        assert not _files(paths.monitor_root / "exports")

        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ? WHERE batch_id = 1",
                (original_raw, original_bytes, original_digest),
            )
            connection.commit()
        restored = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"),
            authorized=True,
        )
        assert restored.ok and restored.data is not None
        assert restored.data.data_path.is_file()
        assert restored.data.manifest_path.is_file()
    finally:
        if exporter is not None:
            exporter.close()
        store.close()
