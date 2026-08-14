from __future__ import annotations

import base64
import json
import os
import sqlite3
import struct
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.groups import GroupStore
from stm32_monitor.history import (
    MAX_HISTORY_VALUES,
    HistoryPage,
    HistoryQuery,
    HistoryStore,
    flatten_history_page,
)
from stm32_monitor.models import (
    MAX_SAMPLE_VALUES,
    HistoryBatchSlice,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchGroup,
    WatchItem,
    unix_ns_to_utc,
)
from stm32_monitor.storage import APPLICATION_ID, StorageFailure
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


def _wide_batch(paths: WorkspacePaths, sequence: int, *, captured_ns: int, count: int) -> SampleBatch:
    batch = _batch(paths, sequence, captured_ns=captured_ns)
    return replace(
        batch,
        values=tuple(
            SampleValue(
                WatchItem.variable(f"counter_{ordinal}"),
                "OK",
                typed_value={"type": "uint32", "value": ordinal},
            )
            for ordinal in range(count)
        ),
    )


def _history_slice(paths: WorkspacePaths) -> HistoryBatchSlice:
    batch = _batch(paths, 1, captured_ns=100)
    return HistoryBatchSlice(
        binding=batch.binding,
        group_id=batch.group_id,
        group_revision=batch.group_revision,
        run_id=batch.run_id,
        sequence=batch.sequence,
        scheduled_unix_ns=batch.scheduled_unix_ns,
        captured_unix_ns=batch.captured_unix_ns,
        latency_ns=batch.latency_ns,
        actual_rate_hz=batch.actual_rate_hz,
        subscriber_drops=batch.subscriber_drops,
        history_drops=batch.history_drops,
        deadline_drops=batch.deadline_drops,
        start_ordinal=0,
        batch_value_count=len(batch.values),
        values=batch.values,
    )


def _compact(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _create_v1_history_database(paths: WorkspacePaths, batches: tuple[SampleBatch, ...]) -> Path:
    paths.monitor_root.mkdir(parents=True)
    database = paths.monitor_root / "monitor.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE monitor_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                workspace_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE monitor_history_accounting (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                logical_bytes INTEGER NOT NULL CHECK (typeof(logical_bytes) = 'integer' AND logical_bytes >= 0)
            );
            INSERT INTO monitor_history_accounting(singleton, logical_bytes) VALUES (1, 0);
            CREATE TABLE history_batches (
                batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                captured_ns INTEGER NOT NULL,
                payload_json BLOB NOT NULL,
                payload_bytes INTEGER NOT NULL,
                UNIQUE (run_id, sequence)
            );
            CREATE INDEX history_session_time ON history_batches(session_id, captured_ns, batch_id);
            CREATE INDEX history_retention_time ON history_batches(captured_ns, batch_id);
            CREATE TABLE history_values (
                batch_id INTEGER NOT NULL REFERENCES history_batches(batch_id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                row_json BLOB NOT NULL,
                payload_bytes INTEGER NOT NULL,
                PRIMARY KEY (batch_id, ordinal)
            );
            CREATE TRIGGER history_batches_account_insert AFTER INSERT ON history_batches
              BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + NEW.payload_bytes WHERE singleton = 1; END;
            CREATE TRIGGER history_batches_account_delete AFTER DELETE ON history_batches
              BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes - OLD.payload_bytes WHERE singleton = 1; END;
            CREATE TRIGGER history_values_account_insert AFTER INSERT ON history_values
              BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + NEW.payload_bytes WHERE singleton = 1; END;
            CREATE TRIGGER history_values_account_delete AFTER DELETE ON history_values
              BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes - OLD.payload_bytes WHERE singleton = 1; END;
            """
        )
        connection.execute(
            "INSERT INTO monitor_metadata(singleton, workspace_id, schema_version) VALUES (1, ?, 1)",
            (paths.workspace_id,),
        )
        for batch in batches:
            payload = batch.to_dict()
            encoded_batch = _compact(payload)
            cursor = connection.execute(
                "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes) VALUES (?,?,?,?,?,?)",
                (
                    batch.binding.session_id,
                    str(batch.run_id),
                    batch.sequence,
                    batch.captured_unix_ns,
                    encoded_batch,
                    len(encoded_batch),
                ),
            )
            evidence = {key: value for key, value in payload.items() if key != "values"}
            rows = []
            for ordinal, value in enumerate(payload["values"]):
                row = dict(evidence)
                row.update(value)
                row["valueOrdinal"] = ordinal
                encoded_row = _compact(row)
                rows.append((cursor.lastrowid, ordinal, encoded_row, len(encoded_row)))
            connection.executemany(
                "INSERT INTO history_values(batch_id,ordinal,row_json,payload_bytes) VALUES (?,?,?,?)",
                rows,
            )
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()
    return database


def _file_inventory(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.name: (path.read_bytes(), os.lstat(path).st_nlink)
        for path in root.iterdir()
        if path.is_file()
    }


def _rewrite_v1_payloads(connection: sqlite3.Connection, corruption: str) -> None:
    batch_raw = connection.execute("SELECT payload_json FROM history_batches").fetchone()[0]
    batch_payload = json.loads(batch_raw)
    row_payloads = [
        (ordinal, json.loads(raw))
        for ordinal, raw in connection.execute(
            "SELECT ordinal,row_json FROM history_values ORDER BY ordinal"
        )
    ]
    if corruption == "workspace":
        batch_payload["binding"]["workspaceId"] = "c" * 24
        for _, row in row_payloads:
            row["binding"]["workspaceId"] = "c" * 24
    elif corruption == "sequence":
        batch_payload["sequence"] = 99
        for _, row in row_payloads:
            row["sequence"] = 99
    elif corruption == "timestamps":
        batch_payload["scheduledAtUtc"] = "2000-01-01T00:00:00.000000Z"
        for _, row in row_payloads:
            row["scheduledAtUtc"] = "2000-01-01T00:00:00.000000Z"
    else:
        raise AssertionError("unknown v1 corruption")
    encoded_batch = _compact(batch_payload)
    connection.execute(
        "UPDATE history_batches SET payload_json = ?, payload_bytes = ?",
        (encoded_batch, len(encoded_batch)),
    )
    for ordinal, row in row_payloads:
        encoded_row = _compact(row)
        connection.execute(
            "UPDATE history_values SET row_json = ?, payload_bytes = ? WHERE ordinal = ?",
            (encoded_row, len(encoded_row), ordinal),
        )


def test_v1_history_migrates_to_normalized_v2_without_changing_flattened_semantics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    batches = (
        _wide_batch(paths, 4, captured_ns=400, count=2),
        _wide_batch(paths, 5, captured_ns=500, count=3),
    )
    database = _create_v1_history_database(paths, batches)
    expected = tuple(
        (row["sequence"], row["valueOrdinal"], row["watch"])
        for batch in batches
        for row in (
            dict({key: value for key, value in batch.to_dict().items() if key != "values"}, **value, valueOrdinal=ordinal)
            for ordinal, value in enumerate(batch.to_dict()["values"])
        )
    )

    store = HistoryStore(paths)
    try:
        store._database.write(lambda connection: None)
        result = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert result.ok
        assert tuple(
            (row["sequence"], row["valueOrdinal"], row["watch"])
            for row in flatten_history_page(result.data)
        ) == expected
    finally:
        store.close()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT schema_version FROM monitor_metadata"
        ).fetchone()[0] == 2
        assert [row[1] for row in connection.execute("PRAGMA table_info(history_batches)")] == [
            "batch_id", "session_id", "run_id", "sequence", "captured_ns",
            "payload_json", "payload_bytes", "payload_sha256", "value_count",
        ]
        assert [row[1] for row in connection.execute("PRAGMA table_info(history_values)")] == [
            "batch_id", "ordinal", "selector_kind", "selector", "value_json",
            "value_bytes", "value_sha256",
        ]
        rows = connection.execute(
            "SELECT batch_id,ordinal,selector_kind,selector,value_json,value_bytes,value_sha256 "
            "FROM history_values ORDER BY batch_id,ordinal"
        ).fetchall()
        assert [(row[0], row[1], row[2], row[3]) for row in rows] == [
            (1, 0, "variable", "counter_0"),
            (1, 1, "variable", "counter_1"),
            (2, 0, "variable", "counter_0"),
            (2, 1, "variable", "counter_1"),
            (2, 2, "variable", "counter_2"),
        ]
        assert all(row[5] == len(row[4]) and row[6] == sha256(row[4]).hexdigest() for row in rows)
        assert all(set(json.loads(row[4])) == {"watch", "status", "typedValue", "code", "definition"} for row in rows)
        selector_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT batch_id,ordinal FROM history_values "
                "WHERE selector_kind = ? AND selector = ? ORDER BY batch_id,ordinal",
                ("variable", "counter_1"),
            )
        )
        assert "history_selector_values" in selector_plan
        assert "TEMP B-TREE" not in selector_plan
        logical = connection.execute(
            "SELECT logical_bytes FROM monitor_history_accounting"
        ).fetchone()[0]
        exact = connection.execute(
            "SELECT COALESCE(SUM(payload_bytes),0) FROM history_batches"
        ).fetchone()[0] + connection.execute(
            "SELECT COALESCE(SUM(value_bytes),0) FROM history_values"
        ).fetchone()[0]
        assert logical == exact
    finally:
        connection.close()

    monkeypatch.setattr(history_module, "RETENTION_AGE_NS", 10_000)
    monkeypatch.setattr(history_module, "RETENTION_LOGICAL_BYTES", 0)
    monkeypatch.setattr(history_module, "RETENTION_DELETE_BATCHES", 1)
    store = HistoryStore(paths)
    try:
        retained = store.run_retention(now_ns=1_000)
        assert retained.ok and retained.data["deletedBatches"] == 1
        remaining = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert remaining.ok
        assert [row["sequence"] for row in flatten_history_page(remaining.data)] == [5, 5, 5]
    finally:
        store.close()


def test_reading_v1_history_never_migrates_or_mutates_it(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    database = _create_v1_history_database(paths, (_batch(paths, 1),))
    before = _file_inventory(paths.monitor_root)

    store = HistoryStore(paths)
    try:
        result = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
    finally:
        store.close()

    assert _file_inventory(paths.monitor_root) == before
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        connection.close()


def test_v1_migration_rejects_oversized_batch_before_loading_payload(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    batch = replace(
        _batch(paths, 1),
        values=tuple(
            SampleValue(
                WatchItem.variable(f"counter_{ordinal}"),
                "OK",
                typed_value={"type": "text", "value": "x" * 20_000},
            )
            for ordinal in range(256)
        ),
    )
    database = _create_v1_history_database(paths, (batch,))
    assert len(_compact(batch.to_dict())) > 4 * 1024 * 1024
    before = _file_inventory(paths.monitor_root)

    store = HistoryStore(paths)
    try:
        result = store.append_batch(_batch(paths, 2))
        assert not result.ok and result.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()

    assert _file_inventory(paths.monitor_root) == before
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        connection.close()


def test_v1_migration_stores_canonical_batch_bytes_digest_and_accounting(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    batch = _wide_batch(paths, 1, captured_ns=1_000, count=2)
    database = _create_v1_history_database(paths, (batch,))
    noncanonical = json.dumps(
        batch.to_dict(),
        ensure_ascii=False,
        sort_keys=False,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")
    canonical = _compact(batch.to_dict())
    assert noncanonical != canonical
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE history_batches SET payload_json = ?, payload_bytes = ?",
            (noncanonical, len(noncanonical)),
        )
        connection.execute(
            "UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + ?",
            (len(noncanonical) - len(canonical),),
        )
        connection.commit()
    finally:
        connection.close()

    store = HistoryStore(paths)
    try:
        store._database.write(lambda current: None)
    finally:
        store.close()

    connection = sqlite3.connect(database)
    try:
        raw, byte_count, digest = connection.execute(
            "SELECT payload_json,payload_bytes,payload_sha256 FROM history_batches"
        ).fetchone()
        assert raw == canonical
        assert byte_count == len(canonical)
        assert digest == sha256(canonical).hexdigest()
        logical = connection.execute(
            "SELECT logical_bytes FROM monitor_history_accounting"
        ).fetchone()[0]
        exact = connection.execute(
            "SELECT SUM(payload_bytes) FROM history_batches"
        ).fetchone()[0] + connection.execute(
            "SELECT SUM(value_bytes) FROM history_values"
        ).fetchone()[0]
        assert logical == exact
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    [
        ("row_ordinal", "MONITOR_STORAGE_CORRUPT"),
        ("payload_bytes", "MONITOR_STORAGE_CORRUPT"),
        ("batch_json", "MONITOR_STORAGE_CORRUPT"),
        ("workspace", "MONITOR_STORAGE_CORRUPT"),
        ("sequence", "MONITOR_STORAGE_CORRUPT"),
        ("timestamps", "MONITOR_STORAGE_CORRUPT"),
        ("metadata_workspace", "MONITOR_WORKSPACE_MISMATCH"),
        ("metadata_schema", "MONITOR_STORAGE_CORRUPT"),
        ("application_id", "MONITOR_STORAGE_INVALID"),
        ("accounting", "MONITOR_STORAGE_CORRUPT"),
        ("accounting_missing", "MONITOR_STORAGE_CORRUPT"),
        ("accounting_negative", "MONITOR_STORAGE_CORRUPT"),
        ("accounting_text", "MONITOR_STORAGE_CORRUPT"),
        ("metadata_missing", "MONITOR_STORAGE_CORRUPT"),
        ("excess_rows", "MONITOR_STORAGE_CORRUPT"),
    ],
)
def test_v1_migration_corruption_rolls_back_original_bytes_schema_and_inventory(
    tmp_path: Path,
    corruption: str,
    expected_code: str,
) -> None:
    paths = _paths(tmp_path)
    database = _create_v1_history_database(
        paths,
        (_wide_batch(paths, 4, captured_ns=400, count=2),),
    )
    connection = sqlite3.connect(database)
    try:
        if corruption == "row_ordinal":
            connection.execute(
                "UPDATE history_values SET ordinal = 7 WHERE ordinal = 1"
            )
        elif corruption == "payload_bytes":
            connection.execute(
                "UPDATE history_batches SET payload_bytes = payload_bytes + 1"
            )
        elif corruption == "batch_json":
            connection.execute(
                "UPDATE history_batches SET payload_json = X'7B7D', payload_bytes = 2"
            )
        elif corruption == "metadata_workspace":
            connection.execute(
                "UPDATE monitor_metadata SET workspace_id = 'other-workspace'"
            )
        elif corruption == "metadata_schema":
            connection.execute("UPDATE monitor_metadata SET schema_version = 2")
        elif corruption == "application_id":
            connection.execute("PRAGMA application_id = 0")
        elif corruption == "accounting":
            connection.execute(
                "UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + 1"
            )
        elif corruption == "accounting_missing":
            connection.execute("DELETE FROM monitor_history_accounting")
        elif corruption in {"accounting_negative", "accounting_text"}:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "UPDATE monitor_history_accounting SET logical_bytes = ?",
                (-1 if corruption == "accounting_negative" else "bad",),
            )
        elif corruption == "metadata_missing":
            connection.execute("DELETE FROM monitor_metadata")
        elif corruption == "excess_rows":
            row_raw = connection.execute(
                "SELECT row_json FROM history_values WHERE ordinal = 0"
            ).fetchone()[0]
            connection.executemany(
                "INSERT INTO history_values(batch_id,ordinal,row_json,payload_bytes) VALUES (1,?,?,?)",
                ((ordinal, row_raw, len(row_raw)) for ordinal in range(2, 257)),
            )
        else:
            _rewrite_v1_payloads(connection, corruption)
        connection.commit()
    finally:
        connection.close()
    before = _file_inventory(paths.monitor_root)

    store = HistoryStore(paths)
    try:
        result = store.append_batch(_batch(paths, 9, captured_ns=900))
        assert not result.ok
        assert result.code == expected_code
    finally:
        store.close()

    assert _file_inventory(paths.monitor_root) == before
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert [row[1] for row in connection.execute("PRAGMA table_info(history_values)")] == [
            "batch_id", "ordinal", "row_json", "payload_bytes"
        ]
        assert connection.execute("SELECT COUNT(*) FROM history_batches").fetchone()[0] == 1
        expected_rows = 257 if corruption == "excess_rows" else 2
        assert connection.execute("SELECT COUNT(*) FROM history_values").fetchone()[0] == expected_rows
    finally:
        connection.close()


@pytest.mark.parametrize(
    "corruption",
    [
        "batch_length", "batch_digest", "value_length", "value_digest", "value_count",
        "selector_kind", "selector", "workspace", "session", "run", "sequence",
        "captured_ns", "scheduled_timestamp", "captured_timestamp", "semantic_payload",
        "noncanonical_key",
    ],
)
def test_v2_query_rejects_payload_and_sqlite_identity_mismatches(
    tmp_path: Path,
    corruption: str,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok

        def corrupt(connection: sqlite3.Connection) -> None:
            if corruption == "batch_length":
                connection.execute("UPDATE history_batches SET payload_bytes = payload_bytes + 1")
            elif corruption == "batch_digest":
                connection.execute("UPDATE history_batches SET payload_sha256 = ?", ("0" * 64,))
            elif corruption == "value_length":
                connection.execute("UPDATE history_values SET value_bytes = value_bytes + 1")
            elif corruption == "value_digest":
                connection.execute("UPDATE history_values SET value_sha256 = ?", ("0" * 64,))
            elif corruption == "value_count":
                connection.execute("UPDATE history_batches SET value_count = value_count + 1")
            elif corruption == "selector_kind":
                connection.execute("UPDATE history_values SET selector_kind = 'register'")
            elif corruption == "selector":
                connection.execute("UPDATE history_values SET selector = 'other'")
            elif corruption == "session":
                connection.execute("UPDATE history_batches SET session_id = 'other-session'")
            elif corruption == "run":
                connection.execute(
                    "UPDATE history_batches SET run_id = ?",
                    ("33333333-3333-4333-8333-333333333333",),
                )
            elif corruption == "sequence":
                connection.execute("UPDATE history_batches SET sequence = 2")
            elif corruption == "captured_ns":
                connection.execute("UPDATE history_batches SET captured_ns = 999999999")
            else:
                raw = connection.execute(
                    "SELECT payload_json FROM history_batches"
                ).fetchone()[0]
                payload = json.loads(raw)
                if corruption == "workspace":
                    payload["binding"]["workspaceId"] = "c" * 24
                elif corruption == "scheduled_timestamp":
                    payload["scheduledAtUtc"] = "2000-01-01T00:00:00.000000Z"
                elif corruption == "captured_timestamp":
                    payload["capturedAtUtc"] = "2000-01-01T00:00:00.000000Z"
                elif corruption == "semantic_payload":
                    payload["groupId"] = "not-a-uuid"
                elif corruption == "noncanonical_key":
                    payload["values"][0]["typedValue"] = {"e\u0301": 1}
                else:
                    raise AssertionError("unknown v2 corruption")
                invalid = _compact(payload)
                connection.execute(
                    "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, payload_sha256 = ?",
                    (invalid, len(invalid), sha256(invalid).hexdigest()),
                )

        store._database.write(corrupt)
        session_id = "other-session" if corruption == "session" else "monitor-1"
        result = store.query_history(HistoryQuery(session_id, 0, 2_000_000_000))
        assert not result.ok
        assert result.code == "MONITOR_STORAGE_CORRUPT"
        streamed = store._stream_verified_batches(
            HistoryQuery(session_id, 0, 2_000_000_000), lambda _batch: None
        )
        assert not streamed.ok and streamed.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_private_verified_stream_rejects_non_export_queries_and_propagates_callback(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    base = HistoryQuery("monitor-1", 0, 2_000_000_000)
    try:
        invalid = (
            replace(base, cursor="1:0"),
            replace(base, limit=1),
            replace(base, run_id=RUN_ID),
            replace(base, group_id=GROUP_ID),
            replace(base, selector_kind="variable", selector="counter"),
        )
        for query in invalid:
            result = store._stream_verified_batches(query, lambda _batch: None)
            assert not result.ok and result.code == "MONITOR_HISTORY_QUERY_INVALID"
        not_callable = store._stream_verified_batches(base, None)  # type: ignore[arg-type]
        assert not not_callable.ok and not_callable.code == "MONITOR_HISTORY_QUERY_INVALID"
        empty = store._stream_verified_batches(
            base,
            lambda _batch: (_ for _ in ()).throw(AssertionError("empty callback")),
        )
        assert empty.ok and empty.data == 0

        assert store.append_batch(_batch(paths, 1)).ok
        with pytest.raises(RuntimeError, match="callback failed"):
            store._stream_verified_batches(
                base,
                lambda _batch: (_ for _ in ()).throw(RuntimeError("callback failed")),
            )
    finally:
        store.close()


def test_private_verified_stream_rejects_unclaimed_value_index_row(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        empty_batch = replace(_batch(paths, 1), values=())
        raw = _compact(empty_batch.to_dict())
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, "
                "payload_sha256 = ?, value_count = 0 WHERE batch_id = 1",
                (raw, len(raw), sha256(raw).hexdigest()),
            )
        )
        result = store._stream_verified_batches(
            HistoryQuery("monitor-1", 0, 2_000_000_000), lambda _batch: None
        )
        assert not result.ok and result.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_mid_batch_cursor_resumes_256_values_without_gap_and_decodes_batch_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_wide_batch(paths, 1, captured_ns=1_000, count=256)).ok
        first = store.query_history(HistoryQuery("monitor-1", 0, 2_000, limit=128))
        assert first.ok and first.data.next_cursor is not None

        calls = 0
        real_decode = history_module._decode_history_batch

        def observed_decode(*args, **kwargs):
            nonlocal calls
            calls += 1
            return real_decode(*args, **kwargs)

        monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
        second = store.query_history(
            HistoryQuery("monitor-1", 0, 2_000, limit=128, cursor=first.data.next_cursor)
        )
        assert second.ok and second.data.next_cursor is None
        assert [row["valueOrdinal"] for row in flatten_history_page(second.data)] == list(
            range(128, 256)
        )
        assert calls == 0
    finally:
        store.close()


def test_ten_thousand_value_query_normalizes_and_serializes_final_page_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        for sequence in range(40):
            assert store.append_batch(
                _wide_batch(
                    paths,
                    sequence,
                    captured_ns=1_000 + sequence,
                    count=250,
                )
            ).ok

        calls = 0
        observed = {
            "sql": 0,
            "decode": 0,
            "evidence_values": 0,
            "encode_value": 0,
            "cursor": 0,
            "size": 0,
        }
        real_create = HistoryPage.create.__func__

        def observed_create(cls, batches, *, next_cursor):
            nonlocal calls
            calls += 1
            if calls > 3:
                raise AssertionError("history page was repeatedly normalized")
            return real_create(cls, batches, next_cursor=next_cursor)

        monkeypatch.setattr(HistoryPage, "create", classmethod(observed_create))
        real_read = store._database.read

        class CountingConnection:
            def __init__(self, connection):
                self._connection = connection

            def __getattr__(self, name):
                return getattr(self._connection, name)

            def execute(self, *args, **kwargs):
                observed["sql"] += 1
                return self._connection.execute(*args, **kwargs)

        def counted_read(operation, *, empty):
            return real_read(lambda connection: operation(CountingConnection(connection)), empty=empty)

        monkeypatch.setattr(store._database, "read", counted_read)
        history_module = __import__("stm32_monitor.history", fromlist=["history"])
        real_decode = history_module._decode_history_batch

        def counted_decode(*args, **kwargs):
            observed["decode"] += 1
            evidence = kwargs.get("value_evidence")
            if evidence is None:
                evidence = kwargs.get("indexed_value_evidence")
            result = real_decode(*args, **kwargs)
            if evidence is not None:
                observed["evidence_values"] += len(evidence)
            return result

        monkeypatch.setattr(history_module, "_decode_history_batch", counted_decode)
        for name, key in (
            ("_encode_history_value", "encode_value"),
            ("_encode_cursor", "cursor"),
            ("_encoded_history_page_size_from_batch_bytes", "size"),
        ):
            original = getattr(history_module, name)

            def counted(*args, __original=original, __key=key, **kwargs):
                observed[__key] += 1
                return __original(*args, **kwargs)

            monkeypatch.setattr(history_module, name, counted)
        result = store.query_history(
            HistoryQuery("monitor-1", 0, 2_000_000_000, limit=10_000)
        )
        assert result.ok
        assert result.data.value_count == 10_000
        assert result.data.next_cursor is None
        assert result.data.serialized_bytes <= 4 * 1024 * 1024
        assert calls <= 3
        assert observed == {
            # Public cacheable queries fetch batch metadata first, then keep
            # payload and per-value evidence in independently ordered cursors.
            "sql": 3,
            "decode": 40,
            "evidence_values": 10_000,
            "encode_value": 0,
            "cursor": 0,
            "size": 3,
        }
        observed.update({key: 0 for key in observed})
        warm = store.query_history(
            HistoryQuery("monitor-1", 0, 2_000_000_000, limit=10_000)
        )
        assert warm.ok and warm.data == result.data
        assert observed == {
            "sql": 0,
            "decode": 0,
            "evidence_values": 0,
            "encode_value": 0,
            "cursor": 0,
            "size": 0,
        }
    finally:
        store.close()


def test_verified_history_cache_is_bounded_and_invalidated_by_append_wal_and_reopen(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    calls = {"decode": 0, "evidence": 0}
    real_decode = history_module._decode_history_batch

    def observed_decode(*args, **kwargs):
        calls["decode"] += 1
        evidence = kwargs.get("value_evidence")
        if evidence is None:
            evidence = kwargs.get("indexed_value_evidence")
        result = real_decode(*args, **kwargs)
        if evidence is not None:
            calls["evidence"] += len(evidence)
        return result

    monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
    try:
        for sequence in range(513):
            assert store.append_batch(
                _batch(paths, sequence, captured_ns=1_000 + sequence)
            ).ok
        calls.update(decode=0, evidence=0)
        cold = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000, limit=513))
        assert cold.ok and cold.data.value_count == 513
        assert calls == {"decode": 513, "evidence": 513}

        calls.update(decode=0, evidence=0)
        evicted = store.query_history(HistoryQuery("monitor-1", 1_000, 1_001))
        assert evicted.ok and calls == {"decode": 1, "evidence": 1}
        calls.update(decode=0, evidence=0)
        retained = store.query_history(HistoryQuery("monitor-1", 1_512, 1_513))
        assert retained.ok and calls == {"decode": 0, "evidence": 0}

        calls.update(decode=0, evidence=0)
        assert store.append_batch(_batch(paths, 513, captured_ns=1_513)).ok
        calls.update(decode=0, evidence=0)
        appended = store.query_history(HistoryQuery("monitor-1", 1_512, 1_514))
        assert appended.ok and appended.data.value_count == 2
        assert calls == {"decode": 2, "evidence": 2}

        calls.update(decode=0, evidence=0)
        external = HistoryStore(paths)
        database = store._database.path
        keeper = sqlite3.connect(database)
        try:
            wal_path = database.with_name(database.name + "-wal")
            keeper.execute("PRAGMA journal_mode = WAL").fetchone()
            keeper.execute("BEGIN")
            keeper.execute("SELECT COUNT(*) FROM history_batches").fetchone()
            wal_before = wal_path.stat() if wal_path.exists() else None
            assert external.append_batch(_batch(paths, 514, captured_ns=1_514)).ok
            calls.update(decode=0, evidence=0)
            wal_after = wal_path.stat()
            assert wal_before is None or (
                wal_after.st_ino,
                wal_after.st_size,
                wal_after.st_mtime_ns,
            ) != (wal_before.st_ino, wal_before.st_size, wal_before.st_mtime_ns)
            external_commit = store.query_history(HistoryQuery("monitor-1", 1_513, 1_515))
            assert external_commit.ok and external_commit.data.value_count == 2
            assert calls == {"decode": 2, "evidence": 2}
        finally:
            keeper.rollback()
            keeper.close()
            external.close()
    finally:
        store.close()

    calls.update(decode=0, evidence=0)
    reopened = HistoryStore(paths)
    try:
        result = reopened.query_history(HistoryQuery("monitor-1", 1_514, 1_515))
        assert result.ok and result.data.value_count == 1
        assert calls == {"decode": 1, "evidence": 1}
    finally:
        reopened.close()


def test_verified_history_page_cache_never_publishes_an_older_read_snapshot_after_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    snapshot_established = threading.Event()
    writer_finished = threading.Event()
    writer_results = []
    writer_errors: list[BaseException] = []
    real_read = store._database.read
    pause_lock = threading.Lock()
    pause_next_read = True

    def coordinated_read(operation, *, empty):
        def paused_operation(connection):
            nonlocal pause_next_read
            with pause_lock:
                should_pause = pause_next_read
                pause_next_read = False
            if should_pause:
                snapshot_established.set()
                assert writer_finished.wait(10), "owned append did not finish"
            return operation(connection)

        return real_read(paused_operation, empty=empty)

    def append_after_snapshot() -> None:
        try:
            assert snapshot_established.wait(10), "reader did not establish a snapshot"
            writer_results.append(
                store.append_batch(_batch(paths, 2, captured_ns=1_002))
            )
        except BaseException as error:  # pragma: no cover - asserted in reader thread
            writer_errors.append(error)
        finally:
            writer_finished.set()

    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=1_001)).ok
        monkeypatch.setattr(store._database, "read", coordinated_read)
        writer = threading.Thread(target=append_after_snapshot)
        writer.start()

        first = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))
        writer.join(10)
        assert not writer.is_alive()
        assert writer_errors == []
        assert len(writer_results) == 1 and writer_results[0].ok
        assert first.ok and first.data.value_count == 1

        refreshed = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))
        assert refreshed.ok and refreshed.data.value_count == 2
    finally:
        store.close()


def test_verified_history_page_cache_requires_one_fingerprint_across_the_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=1_001)).ok
        initial = store._observed_storage_snapshot()
        assert initial is not None and initial[1]
        before = initial[0]
        changed_tail = (*before[-1][:-1], before[-1][-1] + 1)
        during = (*before[:-1], changed_tail)
        observations = 0

        def changing_snapshot():
            nonlocal observations
            observations += 1
            if observations == 1:
                return before, True
            with store._database._integrity_lock:
                store._database._integrity_identity = during
            return during, True

        monkeypatch.setattr(store, "_observed_storage_snapshot", changing_snapshot)
        result = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))

        assert result.ok and result.data.value_count == 1
        assert store._verified_page_cache is None
        assert store._verified_cache == {}
    finally:
        store.close()


def test_uncached_verified_query_does_not_retain_batches_and_normal_queries_still_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    decoded = 0
    real_decode = history_module._decode_history_batch

    def observed_decode(*args, **kwargs):
        nonlocal decoded
        decoded += 1
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
    try:
        for sequence in range(1, 4):
            assert store.append_batch(
                _batch(paths, sequence, captured_ns=1_000 + sequence)
            ).ok
        decoded = 0
        uncached = store._query_history_uncached(
            HistoryQuery("monitor-1", 1_000, 2_000, limit=3)
        )
        assert uncached.ok and uncached.data.value_count == 3
        assert decoded == 3
        assert store._verified_cache == {}

        decoded = 0
        cold = store.query_history(
            HistoryQuery("monitor-1", 1_000, 2_000, limit=3)
        )
        assert cold.ok and cold.data == uncached.data
        assert decoded == 3
        assert len(store._verified_cache) == 3

        decoded = 0
        warm = store.query_history(
            HistoryQuery("monitor-1", 1_000, 2_000, limit=3)
        )
        assert warm.ok and warm.data == cold.data
        assert decoded == 0
        assert len(store._verified_cache) == 3
    finally:
        store.close()


def test_returned_history_page_cannot_poison_the_verified_batch_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    decoded = 0
    real_decode = history_module._decode_history_batch

    def observed_decode(*args, **kwargs):
        nonlocal decoded
        decoded += 1
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
    value = SampleValue(
        WatchItem.variable("counter"),
        "OK",
        typed_value={
            "type": "packet",
            "value": {"items": [7, {"label": "original"}]},
        },
        definition={
            "typeName": "Packet",
            "fields": [{"name": "items", "kind": "array"}],
        },
    )
    batch = replace(_batch(paths, 1, captured_ns=1_001), values=(value,))
    original = batch.to_dict()
    try:
        assert store.append_batch(batch).ok
        cold = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))
        assert cold.ok and decoded == 1

        cached = next(iter(store._verified_cache.values())).batch
        returned_slice = cold.data.batches[0]
        returned_value = returned_slice.values[0]
        cached_value = cached.values[0]

        assert returned_slice.binding is not cached.binding
        assert returned_slice.group_id is not cached.group_id
        assert returned_slice.run_id is not cached.run_id
        assert returned_value is not cached_value
        assert returned_value.watch is not cached_value.watch

        with pytest.raises(TypeError):
            returned_value.typed_value["value"]["items"][0] = 999
        with pytest.raises(TypeError):
            returned_value.definition["fields"][0]["name"] = "poisoned"

        object.__setattr__(returned_slice.binding, "probe_id", "poisoned")
        object.__setattr__(returned_slice.group_id, "int", 0)
        object.__setattr__(returned_slice.run_id, "int", 0)
        object.__setattr__(returned_value.watch, "selector", "poisoned")
        object.__setattr__(returned_value, "typed_value", 999)
        object.__setattr__(returned_value, "definition", {"poisoned": True})

        assert cached.to_dict() == original
        decoded = 0
        warm = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))
        assert warm.ok and decoded == 0
        warm_slice = warm.data.batches[0]
        assert warm_slice.binding.to_dict() == original["binding"]
        assert str(warm_slice.group_id) == original["groupId"]
        assert str(warm_slice.run_id) == original["runId"]
        assert [item.to_dict() for item in warm_slice.values] == original["values"]
        assert next(iter(store._verified_cache.values())).batch.to_dict() == original

        transient_cache: dict[str, object] = {}
        transient = store._query_history_uncached(
            HistoryQuery("monitor-1", 1_000, 2_000),
            transient_cache=transient_cache,
        )
        assert transient.ok
        transient_batches = transient_cache["batches"]
        assert type(transient_batches) is dict
        transient_cached = next(iter(transient_batches.values())).batch
        transient_slice = transient.data.batches[0]
        transient_value = transient_slice.values[0]
        assert transient_slice.binding is not transient_cached.binding
        assert transient_slice.group_id is not transient_cached.group_id
        assert transient_slice.run_id is not transient_cached.run_id
        assert transient_value is not transient_cached.values[0]
        assert transient_value.watch is not transient_cached.values[0].watch

        object.__setattr__(transient_slice.binding, "probe_id", "poisoned")
        object.__setattr__(transient_slice.group_id, "int", 0)
        object.__setattr__(transient_slice.run_id, "int", 0)
        object.__setattr__(transient_value.watch, "selector", "poisoned")
        object.__setattr__(transient_value, "typed_value", 999)
        object.__setattr__(transient_value, "definition", {"poisoned": True})

        transient_warm = store._query_history_uncached(
            HistoryQuery("monitor-1", 1_000, 2_000),
            transient_cache=transient_cache,
        )
        assert transient_warm.ok
        assert transient_cached.to_dict() == original
        assert transient_warm.data.batches[0].binding.to_dict() == original["binding"]
        assert [
            item.to_dict() for item in transient_warm.data.batches[0].values
        ] == original["values"]
    finally:
        store.close()


def test_export_page_cache_is_bounded_and_invalidated_by_an_owned_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    transient_cache: dict[str, object] = {}
    try:
        for sequence in range(80):
            assert store.append_batch(
                _wide_batch(
                    paths,
                    sequence,
                    captured_ns=1_000 + sequence,
                    count=256,
                )
            ).ok
        first = store._query_history_uncached(
            HistoryQuery(
                "monitor-1",
                0,
                2_000_000_000,
                limit=MAX_HISTORY_VALUES,
            ),
            transient_cache=transient_cache,
        )
        assert first.ok and first.data.value_count == MAX_HISTORY_VALUES
        assert first.data.next_cursor is not None
        cached = transient_cache["batches"]
        assert type(cached) is dict and len(cached) == 2
        previous_snapshot = transient_cache["snapshot"]

        assert store.append_batch(
            _wide_batch(paths, 80, captured_ns=1_080, count=256)
        ).ok
        decoded = 0
        real_decode = history_module._decode_history_batch

        def observed_decode(*args, **kwargs):
            nonlocal decoded
            decoded += 1
            return real_decode(*args, **kwargs)

        monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
        second = store._query_history_uncached(
            HistoryQuery(
                "monitor-1",
                0,
                2_000_000_000,
                limit=MAX_HISTORY_VALUES,
                cursor=first.data.next_cursor,
            ),
            transient_cache=transient_cache,
        )
        assert second.ok and second.data.value_count == MAX_HISTORY_VALUES
        assert second.data.next_cursor is not None
        assert decoded == 40
        assert transient_cache["snapshot"] != previous_snapshot
        refreshed = transient_cache["batches"]
        assert type(refreshed) is dict and len(refreshed) == 2
        assert store._verified_cache == {}
    finally:
        store.close()


@pytest.mark.parametrize("corruption", ["recomputed_payload", "digest", "index"])
def test_verified_history_cache_never_hides_committed_payload_or_index_corruption(
    tmp_path: Path,
    monkeypatch,
    corruption: str,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    real_decode = history_module._decode_history_batch
    real_encode = history_module._encode_history_value
    calls = {"decode": 0, "encode": 0}

    def observed_decode(*args, **kwargs):
        calls["decode"] += 1
        return real_decode(*args, **kwargs)

    def observed_encode(*args, **kwargs):
        calls["encode"] += 1
        return real_encode(*args, **kwargs)

    monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
    monkeypatch.setattr(history_module, "_encode_history_value", observed_encode)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=1_001)).ok
        assert store.query_history(HistoryQuery("monitor-1", 1_000, 2_000)).ok
        calls.update(decode=0, encode=0)
        assert store.query_history(HistoryQuery("monitor-1", 1_000, 2_000)).ok
        assert calls == {"decode": 0, "encode": 0}

        database = store._database.path
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if corruption == "recomputed_payload":
                raw = connection.execute(
                    "SELECT payload_json FROM history_batches WHERE batch_id = 1"
                ).fetchone()[0]
                payload = json.loads(raw)
                payload["sequence"] = 2
                changed = _compact(payload)
                assert len(changed) == len(raw)
                connection.execute(
                    "UPDATE history_batches SET payload_json = ?, payload_sha256 = ? "
                    "WHERE batch_id = 1",
                    (changed, sha256(changed).hexdigest()),
                )
            elif corruption == "digest":
                connection.execute(
                    "UPDATE history_values SET value_sha256 = ? WHERE batch_id = 1",
                    ("0" * 64,),
                )
            else:
                connection.execute(
                    "UPDATE history_values SET selector = 'countez' WHERE batch_id = 1"
                )
            connection.commit()

        result = store.query_history(HistoryQuery("monitor-1", 1_000, 2_000))
        assert not result.ok and result.code == "MONITOR_STORAGE_CORRUPT"
        assert calls["decode"] > 0
    finally:
        store.close()


def test_oversized_batch_append_is_rejected_before_mutating_readable_history(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    oversized = replace(
        _batch(paths, 2),
        values=tuple(
            SampleValue(
                WatchItem.variable(f"counter_{ordinal}"),
                "OK",
                typed_value={"type": "text", "value": "x" * 20_000},
            )
            for ordinal in range(256)
        ),
    )
    assert len(_compact(oversized.to_dict())) > 4 * 1024 * 1024

    store = HistoryStore(paths)
    try:
        first = store.append_batch(_batch(paths, 1))
        assert first.ok and first.data["batchId"] == 1

        rejected = store.append_batch(oversized)
        assert not rejected.ok and rejected.code == "MONITOR_REQUEST_INVALID"

        after_rejection = store.query_history(
            HistoryQuery("monitor-1", 0, 2_000_000_000)
        )
        assert after_rejection.ok
        assert [row["sequence"] for row in flatten_history_page(after_rejection.data)] == [1]

        subsequent = store.append_batch(_batch(paths, 3))
        assert subsequent.ok and subsequent.data["batchId"] == 2
        final = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert final.ok
        assert [row["sequence"] for row in flatten_history_page(final.data)] == [1, 3]
    finally:
        store.close()


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
        assert result.ok and result.data.value_count == 1
        assert len(result.data.batches) == 1
        row = tuple(flatten_history_page(result.data))[0]
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


def test_history_filters_run_group_and_exact_symbolic_selector_with_bound_cursor(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    other_group = UUID("33333333-3333-4333-8333-333333333333")
    other_run = UUID("44444444-4444-4444-8444-444444444444")
    try:
        first = replace(
            _batch(paths, 1, captured_ns=100),
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": 1},
                ),
                SampleValue(
                    WatchItem.register("GPIOA.ODR"),
                    "OK",
                    typed_value={"type": "uint32", "value": 2},
                ),
            ),
        )
        second = replace(
            _batch(paths, 2, captured_ns=200),
            group_id=other_group,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": 3},
                ),
            ),
        )
        third = replace(
            _batch(paths, 1, captured_ns=300),
            run_id=other_run,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": 4},
                ),
            ),
        )
        for batch in (first, second, third):
            assert store.append_batch(batch).ok

        by_run = store.query_history(
            HistoryQuery("monitor-1", 0, 1_000, run_id=other_run)
        )
        by_group = store.query_history(
            HistoryQuery("monitor-1", 0, 1_000, group_id=other_group)
        )
        by_selector = store.query_history(
            HistoryQuery(
                "monitor-1",
                0,
                1_000,
                selector_kind="register",
                selector="GPIOA.ODR",
            )
        )
        first_page = store.query_history(
            HistoryQuery(
                "monitor-1",
                0,
                1_000,
                limit=1,
                selector_kind="variable",
                selector="counter",
            )
        )

        assert [row["runId"] for row in flatten_history_page(by_run.data)] == [
            str(other_run)
        ]
        assert [row["groupId"] for row in flatten_history_page(by_group.data)] == [
            str(other_group)
        ]
        assert [row["watch"] for row in flatten_history_page(by_selector.data)] == [
            {"kind": "register", "registerPath": "GPIOA.ODR"}
        ]
        assert first_page.ok and first_page.data.next_cursor is not None
        resumed = store.query_history(
            HistoryQuery(
                "monitor-1",
                0,
                1_000,
                cursor=first_page.data.next_cursor,
                selector_kind="variable",
                selector="counter",
            )
        )
        assert [row["typedValue"]["value"] for row in flatten_history_page(resumed.data)] == [
            3,
            4,
        ]

        mismatched = store.query_history(
            HistoryQuery(
                "monitor-1",
                0,
                1_000,
                cursor=first_page.data.next_cursor,
                selector_kind="register",
                selector="GPIOA.ODR",
            )
        )
        assert not mismatched.ok and mismatched.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


@pytest.mark.parametrize(
    ("source_changes", "resume_changes"),
    [
        ({}, {"start_ns": 1}),
        ({}, {"end_ns": 999}),
        ({}, {"run_id": None}),
        ({"run_id": None}, {"run_id": RUN_ID}),
        ({}, {"group_id": None}),
        ({"group_id": None}, {"group_id": GROUP_ID}),
        ({}, {"selector_kind": None, "selector": None}),
        (
            {"selector_kind": None, "selector": None},
            {"selector_kind": "variable", "selector": "counter"},
        ),
    ],
)
def test_history_cursor_rejects_any_filter_tuple_change_while_row_still_matches(
    tmp_path: Path,
    source_changes: dict[str, object],
    resume_changes: dict[str, object],
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        source_query = replace(
            HistoryQuery(
                "monitor-1",
                0,
                1_000,
                limit=1,
                run_id=RUN_ID,
                group_id=GROUP_ID,
                selector_kind="variable",
                selector="counter",
            ),
            **source_changes,
        )
        first = store.query_history(source_query)
        assert first.ok and first.data.next_cursor is not None

        resumed = store.query_history(
            replace(
                source_query,
                limit=10,
                cursor=first.data.next_cursor,
                **resume_changes,
            )
        )

        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_history_cursor_is_bounded_opaque_and_rejects_legacy_malformed_and_tampered(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
        first = store.query_history(query)
        assert first.ok and first.data.next_cursor is not None
        cursor = first.data.next_cursor
        assert cursor.startswith("v1.")
        assert len(cursor.encode("ascii")) <= 128
        assert ":" not in cursor

        replacement = "A" if cursor[-1] != "A" else "B"
        position_replacement = "I" if cursor[13] != "I" else "E"
        invalid_cursors = (
            "1:0",
            "v1.",
            "v2." + cursor.removeprefix("v1."),
            cursor[:-1] + replacement,
            cursor[:13] + position_replacement + cursor[14:],
        )
        for invalid_cursor in invalid_cursors:
            invalid = store.query_history(replace(query, cursor=invalid_cursor))
            assert not invalid.ok
            assert invalid.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_history_cursor_rejects_noncanonical_equivalent_padding_bits(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        filter_digest = history_module._filter_digest(query)
        for byte in range(256):
            key = bytes((byte,)) * 32
            cursor = history_module._encode_cursor(1, 0, filter_digest, key)
            if cursor.endswith("A"):
                store._cursor_key = key
                break
        else:
            raise AssertionError("failed to construct canonical A-suffixed cursor")
        first = store.query_history(query)
        assert first.ok and first.data.next_cursor == cursor
        equivalent = cursor[:-1] + "B"
        assert base64.urlsafe_b64decode(cursor.removeprefix("v1.") + "=") == (
            base64.urlsafe_b64decode(equivalent.removeprefix("v1.") + "=")
        )
        rejected = store.query_history(replace(query, cursor=equivalent))
        assert not rejected.ok and rejected.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_history_cursor_rejects_forged_position_with_recomputed_public_checksum(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
        first = store.query_history(query)
        assert first.ok and first.data.next_cursor is not None
        encoded = first.data.next_cursor.removeprefix("v1.")
        payload = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        )
        _, _, filter_digest = struct.unpack(">QQ32s", payload[:48])
        forged_bound = struct.pack(">QQ32s", 2, 0, filter_digest)
        public_tag = sha256(forged_bound).digest()[: len(payload) - len(forged_bound)]
        forged = "v1." + base64.urlsafe_b64encode(
            forged_bound + public_tag
        ).rstrip(b"=").decode("ascii")

        resumed = store.query_history(replace(query, cursor=forged))

        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_history_cursor_is_stable_within_store_and_invalid_after_store_restart(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    first_store = HistoryStore(paths)
    query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
    try:
        assert first_store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert first_store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        first = first_store.query_history(query)
        repeated = first_store.query_history(query)
        assert first.ok and first.data.next_cursor is not None
        assert repeated.ok and repeated.data.next_cursor == first.data.next_cursor
        cursor = first.data.next_cursor
    finally:
        first_store.close()

    restarted_store = HistoryStore(paths)
    try:
        resumed = restarted_store.query_history(replace(query, cursor=cursor))
        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        restarted_store.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "22222222-2222-4222-8222-222222222222"},
        {"group_id": "11111111-1111-4111-8111-111111111111"},
        {"selector_kind": "variable"},
        {"selector": "counter"},
        {"selector_kind": "memory", "selector": "counter"},
    ],
)
def test_history_filter_model_rejects_wrong_types_and_incomplete_selector_pair(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        result = store.query_history(
            replace(HistoryQuery("monitor-1", 0, 1_000), **changes)
        )
        assert not result.ok and result.code == "MONITOR_HISTORY_QUERY_INVALID"
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
        first_payload = first.data.to_dict()
        assert first_payload["serializedBytes"] == len(
            json.dumps(first_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        assert set(first_payload) == {"batches", "valueCount", "nextCursor", "serializedBytes"}
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
        for cursor in (
            "bad",
            "01:000",
            "１:０",
            "1" * 20 + ":0",
            f"{2**63}:0",
        ):
            assert store.query_history(
                HistoryQuery("monitor-1", 0, 2_000_000_000, cursor=cursor)
            ).code == "MONITOR_HISTORY_QUERY_INVALID"

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
                "UPDATE history_values SET value_json = ?, value_bytes = ?",
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
    ("location", "field", "replacement"),
    [
        ("batch", "binding", []),
        ("value", "watch", []),
        ("value", "status", 1),
        ("value", "definition", []),
        ("ordinal", "ordinal", 1),
        ("batch", "scheduledAtUtc", "1970-01-01T00:00:00.000000Z"),
        ("batch", "capturedAtUtc", "1970-01-01T00:00:00.000000Z"),
        ("batch", "actualRateHz", "5.0"),
    ],
)
def test_each_history_model_semantic_mismatch_is_storage_corruption(
    tmp_path: Path,
    location: str,
    field: str,
    replacement: object,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        if location == "ordinal":
            store._database.write(
                lambda connection: connection.execute(
                    "UPDATE history_values SET ordinal = ?",
                    (replacement,),
                )
            )
        else:
            table, json_column, bytes_column, digest_column = (
                ("history_batches", "payload_json", "payload_bytes", "payload_sha256")
                if location == "batch"
                else ("history_values", "value_json", "value_bytes", "value_sha256")
            )
            raw = store._database.read(
                lambda connection: connection.execute(
                    f"SELECT {json_column} FROM {table}"
                ).fetchone()[0],
                empty=None,
            )
            decoded = json.loads(bytes(raw).decode("utf-8"))
            decoded[field] = replacement
            invalid = _compact(decoded)
            store._database.write(
                lambda connection: connection.execute(
                    f"UPDATE {table} SET {json_column} = ?, {bytes_column} = ?, {digest_column} = ?",
                    (invalid, len(invalid), sha256(invalid).hexdigest()),
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
        for sequence in range(1, 5):
            assert store.append_batch(_batch(paths, sequence)).ok
        one_value = store.query_history(
            HistoryQuery("monitor-1", 0, 2_000_000_000, limit=1)
        )
        assert one_value.ok and one_value.data.next_cursor is not None
        monkeypatch.setattr(
            history_module,
            "MAX_HISTORY_PAGE_BYTES",
            one_value.data.serialized_bytes,
        )
        page = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert page.ok and len(page.data.values) == 1 and page.data.next_cursor is not None
    finally:
        store.close()


def test_final_value_uses_exact_no_cursor_page_budget(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        exact = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert exact.ok and exact.data.next_cursor is None
        monkeypatch.setattr(
            history_module,
            "MAX_HISTORY_PAGE_BYTES",
            exact.data.serialized_bytes,
        )
        bounded = store.query_history(HistoryQuery("monitor-1", 0, 2_000_000_000))
        assert bounded.ok
        assert bounded.data.value_count == 1
        assert bounded.data.next_cursor is None
        assert bounded.data.serialized_bytes == exact.data.serialized_bytes
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


def test_retention_caller_timeout_includes_executor_scheduling_margin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=2_000)).ok
        monkeypatch.setattr(history_module, "RETENTION_AGE_NS", 1_000)
        monkeypatch.setattr(history_module, "RETENTION_DELETE_BATCHES", 1)

        clock_calls = 0

        def near_budget_clock() -> int:
            nonlocal clock_calls
            clock_calls += 1
            if clock_calls == 1:
                return 0
            return history_module.RETENTION_TIME_BUDGET_NS - 1

        monkeypatch.setattr(history_module.time, "monotonic_ns", near_budget_clock)
        required_timeout_ms = (
            history_module.RETENTION_TIME_BUDGET_NS // 1_000_000 + 10
        )

        class ScheduledFuture(Future):
            def __init__(self, function, args, kwargs) -> None:
                super().__init__()
                self._function = function
                self._args = args
                self._kwargs = kwargs

            def result(self, timeout=None):
                if not self.done():
                    if timeout is not None and timeout * 1_000 < required_timeout_ms:
                        raise FutureTimeout
                    try:
                        result = self._function(*self._args, **self._kwargs)
                    except BaseException as error:
                        self.set_exception(error)
                    else:
                        self.set_result(result)
                return super().result(timeout=0)

        def scheduled_submit(function, *args, **kwargs):
            return ScheduledFuture(function, args, kwargs)

        monkeypatch.setattr(store._database._writer.executor, "submit", scheduled_submit)

        retained = store.run_retention(now_ns=3_000)

        assert retained.ok
        assert retained.data["deletedBatches"] == 1
        assert retained.data["earliestCapturedUnixNs"] == 2_000
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


def test_retention_chunks_one_hundred_thousand_values_within_live_deadlines(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    stop = threading.Event()
    ticks: list[int] = []

    def ticker() -> None:
        while not stop.wait(0.001):
            ticks.append(time.perf_counter_ns())

    try:
        remaining = 100_000
        sequence = 1
        while remaining:
            count = min(256, remaining)
            assert store.append_batch(
                _wide_batch(paths, sequence, captured_ns=sequence + 100, count=count)
            ).ok
            remaining -= count
            sequence += 1
        thread = threading.Thread(target=ticker)
        thread.start()
        started = time.perf_counter_ns()
        retained = store.run_retention(now_ns=10**18)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
        stop.set()
        thread.join(timeout=1)
        gaps = [(right - left) / 1_000_000 for left, right in zip(ticks, ticks[1:])]

        assert retained.ok
        assert retained.data["deletedBatches"] == 2
        assert retained.data["moreWork"] is True
        assert elapsed < 2
        assert max(gaps, default=0) < 100
    finally:
        stop.set()
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
                "SELECT payload_json FROM history_batches"
            ).fetchone()[0],
            empty=None,
        )
        decoded = json.loads(bytes(raw).decode("utf-8"))
        decoded["groupId"] = "not-a-uuid"
        invalid = json.dumps(decoded, separators=(",", ":")).encode("utf-8")
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, payload_sha256 = ?",
                (invalid, len(invalid), sha256(invalid).hexdigest()),
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


def test_verified_slice_iso_batch_and_slice_base_reject_invalid_inputs(
    tmp_path: Path,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    batch = _batch(paths, 1)
    with pytest.raises(TypeError):
        history_module._verified_history_slice(batch, 0, (), 100)
    with pytest.raises(TypeError):
        history_module._verified_history_slice(batch, 0, batch.values, 0)
    with pytest.raises(TypeError):
        history_module._isolated_verified_batch("not-a-batch")
    with pytest.raises(TypeError):
        history_module._encoded_slice_base_bytes(batch, ())
    with pytest.raises(TypeError):
        history_module._encoded_slice_base_bytes(batch, (1, 2))
    with pytest.raises(TypeError):
        history_module._encoded_slice_base_bytes(batch, (10**9,))


def test_verified_history_page_rejects_mismatched_value_count(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    with pytest.raises(TypeError):
        history_module._verified_history_page(
            (), value_count=1, next_cursor=None, serialized_bytes=10
        )


def test_cursor_helpers_reject_invalid_positions_and_types(tmp_path: Path) -> None:
    import base64
    import hmac
    import struct

    import stm32_monitor.history as history_module

    bound = struct.pack(">QQ32s", 0, 0, b"\0" * 32)
    payload = bound + hmac.digest(b"key", bound, "sha256")
    zero_batch_cursor = "v1." + base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    with pytest.raises(ValueError):
        history_module._cursor_payload(zero_batch_cursor)
    with pytest.raises(ValueError):
        history_module._cursor(123, b"\0" * 32, b"key")


def test_decode_history_batch_rejects_wrong_types_and_shapes(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    batch = _batch(paths, 1, captured_ns=1_000_000_001)
    raw = json.dumps(
        batch.to_dict(), ensure_ascii=False, separators=(",", ":")
    ).encode()
    good = {
        "raw": raw,
        "payload_bytes": len(raw),
        "payload_sha256": sha256(raw).hexdigest(),
        "value_count": 1,
        "workspace_id": paths.workspace_id,
        "session_id": "monitor-1",
        "run_id": str(RUN_ID),
        "sequence": 1,
        "captured_ns": 1_000_000_001,
    }
    with pytest.raises(StorageFailure):
        history_module._decode_history_batch(
            b"raw", b"bad", "digest", 1, workspace_id=good["workspace_id"],
            session_id="monitor-1", run_id=str(RUN_ID), sequence=1, captured_ns=1,
        )

    payload = json.loads(raw)
    payload["values"] = [{"watch": {"kind": "variable", "expression": "counter"}}]
    missing_fields = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    with pytest.raises(StorageFailure):
        history_module._decode_history_batch(
            missing_fields, len(missing_fields), sha256(missing_fields).hexdigest(),
            value_count=1, **{k: good[k] for k in ("workspace_id", "session_id", "run_id", "sequence", "captured_ns")},
        )

    payload2 = json.loads(raw)
    payload2["values"] = [dict(payload2["values"][0], watch="not-a-dict")]
    watch_not_dict = json.dumps(payload2, ensure_ascii=False, separators=(",", ":")).encode()
    with pytest.raises(StorageFailure):
        history_module._decode_history_batch(
            watch_not_dict, len(watch_not_dict), sha256(watch_not_dict).hexdigest(),
            value_count=1, **{k: good[k] for k in ("workspace_id", "session_id", "run_id", "sequence", "captured_ns")},
        )

    payload3 = json.loads(raw)
    # "e" followed by U+0301 combining acute (non-NFC) so WatchItem normalizes it.
    nfd_expression = "caf" + chr(0x65) + chr(0x301)
    payload3["values"] = [
        dict(
            payload3["values"][0],
            watch={"kind": "variable", "expression": nfd_expression},
        )
    ]
    non_canonical = json.dumps(payload3, ensure_ascii=False, separators=(",", ":")).encode()
    with pytest.raises(StorageFailure):
        history_module._decode_history_batch(
            non_canonical, len(non_canonical), sha256(non_canonical).hexdigest(),
            value_count=1, **{k: good[k] for k in ("workspace_id", "session_id", "run_id", "sequence", "captured_ns")},
        )


def test_normalize_v1_batch_rejects_invalid_evidence(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    batch = _batch(paths, 1, captured_ns=1_000_000_001)
    raw = json.dumps(
        batch.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    decoded = json.loads(raw)
    evidence = {key: value for key, value in decoded.items() if key != "values"}
    row = dict(evidence)
    row.update(decoded["values"][0])
    row["valueOrdinal"] = 0
    row_raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    value_rows = ((0, row_raw, len(row_raw)),)
    batch_row = (1, "monitor-1", str(RUN_ID), 1, 1_000_000_001, raw, len(raw))

    assert history_module._normalize_v1_batch(
        workspace_id=paths.workspace_id, batch_row=batch_row, value_rows=value_rows
    )[0] == raw

    with pytest.raises(StorageFailure):
        history_module._normalize_v1_batch(
            workspace_id=paths.workspace_id,
            batch_row=(0, "monitor-1", str(RUN_ID), 1, 1_000_000_001, raw, len(raw)),
            value_rows=value_rows,
        )
    with pytest.raises(StorageFailure):
        history_module._normalize_v1_batch(
            workspace_id=paths.workspace_id, batch_row=batch_row, value_rows=()
        )
    with pytest.raises(StorageFailure):
        history_module._normalize_v1_batch(
            workspace_id=paths.workspace_id,
            batch_row=batch_row,
            value_rows=((0, b"[]", 2),),
        )
    bad_row = dict(row)
    bad_row["sequence"] = 99
    bad_row_raw = json.dumps(bad_row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(StorageFailure):
        history_module._normalize_v1_batch(
            workspace_id=paths.workspace_id,
            batch_row=batch_row,
            value_rows=((0, bad_row_raw, len(bad_row_raw)),),
        )


def test_retention_with_nothing_to_delete_is_an_empty_pass(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        evidence = store.run_retention(now_ns=200)
        assert evidence.ok
        assert evidence.data["deletedBatches"] == 0
        assert evidence.data["passes"] == 0
        assert evidence.data["moreWork"] is False
    finally:
        store.close()


def test_private_stream_counts_verified_batches(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        received: list[object] = []
        result = store._stream_verified_batches(
            HistoryQuery("monitor-1", 0, 1_000), received.append
        )
        assert result.ok
        assert result.data == 2
        assert len(received) == 2
    finally:
        store.close()


def test_group_filter_cursor_rejects_batch_group_mutation(tmp_path: Path) -> None:
    from dataclasses import replace as _replace

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    other_group = UUID("33333333-3333-4333-8333-333333333333")
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(
            _replace(_wide_batch(paths, 2, captured_ns=200, count=2), group_id=other_group)
        ).ok
        group_query = HistoryQuery("monitor-1", 0, 1_000, group_id=other_group, limit=1)
        first = store.query_history(group_query)
        assert first.ok and first.data.next_cursor is not None
        cursor = first.data.next_cursor

        raw = store._database.read(
            lambda connection: connection.execute(
                "SELECT payload_json FROM history_batches WHERE batch_id = 2"
            ).fetchone()[0],
            empty=None,
        )
        payload = json.loads(raw)
        payload["groupId"] = str(GROUP_ID)
        changed = _compact(payload)
        store._database.write(
            lambda connection: connection.execute(
                "UPDATE history_batches SET payload_json = ?, payload_bytes = ?, payload_sha256 = ? "
                "WHERE batch_id = 2",
                (changed, len(changed), sha256(changed).hexdigest()),
            )
        )

        resumed = store.query_history(replace(group_query, cursor=cursor))
        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_query_cursor_past_last_batch_is_invalid(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
        cursor = history_module._encode_cursor(
            5, 0, history_module._filter_digest(query), store._cursor_key
        )
        resumed = store.query_history(replace(query, cursor=cursor))
        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_stream_rejects_corrupt_batch_identity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        database = store._database.path
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("UPDATE history_batches SET batch_id = 0 WHERE batch_id = 1")
            connection.execute("UPDATE history_values SET batch_id = 0 WHERE batch_id = 1")
            connection.commit()
        received: list[object] = []
        result = store._stream_verified_batches(
            HistoryQuery("monitor-1", 0, 1_000), received.append
        )
        assert not result.ok
        assert result.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_retention_rejects_missing_accounting_row(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        database = store._database.path
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM monitor_history_accounting")
            connection.commit()
        evidence = store.run_retention(now_ns=1_000)
        assert not evidence.ok
        assert evidence.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_query_rejects_non_bytes_payload_corruption(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        database = store._database.path
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE history_batches SET payload_json = 42 WHERE batch_id = 1"
            )
            connection.commit()
        result = store.query_history(HistoryQuery("monitor-1", 0, 1_000))
        assert not result.ok
        assert result.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        store.close()


def test_cursor_to_deleted_batch_is_rejected(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=200)).ok
        query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
        first = store.query_history(query)
        assert first.ok and first.data.next_cursor is not None
        database = store._database.path
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM history_batches WHERE batch_id = 1")
            connection.execute("DELETE FROM history_values WHERE batch_id = 1")
            connection.commit()
        resumed = store.query_history(replace(query, cursor=first.data.next_cursor))
        assert not resumed.ok
        assert resumed.code == "MONITOR_HISTORY_QUERY_INVALID"
    finally:
        store.close()


def test_decode_rejects_mismatched_index_evidence_count(tmp_path: Path) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    batch = _batch(paths, 1, captured_ns=100)
    raw = _compact(batch.to_dict())

    with pytest.raises(StorageFailure):
        history_module._decode_history_batch(
            raw,
            len(raw),
            sha256(raw).hexdigest(),
            len(batch.values),
            workspace_id=paths.workspace_id,
            session_id=batch.binding.session_id,
            run_id=str(batch.run_id),
            sequence=batch.sequence,
            captured_ns=batch.captured_unix_ns,
            indexed_value_evidence=(),
        )


@pytest.mark.parametrize("limit", [True, 1, 513])
def test_uncached_query_rejects_invalid_transient_cache_limits(
    tmp_path: Path,
    limit: object,
) -> None:
    store = HistoryStore(_paths(tmp_path))
    try:
        with pytest.raises(ValueError, match="transient history cache limit is invalid"):
            store._query_history_uncached(
                HistoryQuery("monitor-1", 0, 1_000),
                transient_cache={},
                transient_cache_limit=limit,
            )
    finally:
        store.close()


def test_transient_cache_stays_bounded_across_stable_pagination(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    transient_cache: dict[str, object] = {}
    try:
        for sequence in range(1, 4):
            assert store.append_batch(
                _batch(paths, sequence, captured_ns=100 + sequence)
            ).ok

        query = HistoryQuery("monitor-1", 0, 1_000, limit=1)
        for expected_sequence in range(1, 4):
            page = store._query_history_uncached(
                query,
                transient_cache=transient_cache,
                transient_cache_limit=2,
            )
            assert page.ok
            assert [batch.sequence for batch in page.data.batches] == [expected_sequence]
            query = replace(query, cursor=page.data.next_cursor)

        cached = transient_cache["batches"]
        assert type(cached) is dict
        assert len(cached) == 2
    finally:
        store.close()


def test_transient_cache_clears_when_storage_identity_changes_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    transient_cache: dict[str, object] = {"stale": object()}
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        initial = store._observed_storage_snapshot()
        assert initial is not None and initial[1]
        before = initial[0]
        changed_tail = (*before[-1][:-1], before[-1][-1] + 1)
        during = (*before[:-1], changed_tail)

        def changing_snapshot():
            with store._database._integrity_lock:
                store._database._integrity_identity = during
            return before, True

        monkeypatch.setattr(store, "_observed_storage_snapshot", changing_snapshot)
        result = store._query_history_uncached(
            HistoryQuery("monitor-1", 0, 1_000),
            transient_cache=transient_cache,
        )

        assert result.ok and result.data.value_count == 1
        assert transient_cache == {}
    finally:
        store.close()


@pytest.mark.parametrize(
    ("invalid_model", "exception", "message"),
    [
        (
            lambda paths: replace(_binding(paths), git_head="not-a-git-sha"),
            ValueError,
            "Git HEAD is invalid",
        ),
        (
            lambda paths: replace(_binding(paths), git_dirty=1),
            ValueError,
            "Git dirty state is invalid",
        ),
        (
            lambda _paths_value: replace(
                WatchGroup.create("group", "", 100, (WatchItem.variable("counter"),)),
                group_id="not-a-uuid",
            ),
            ValueError,
            "group ID must be a UUID",
        ),
        (
            lambda _paths_value: replace(
                WatchGroup.create("group", "", 100, (WatchItem.variable("counter"),)),
                items=("not-a-watch",),
            ),
            ValueError,
            "group items are invalid",
        ),
        (
            lambda _paths_value: SampleValue("not-a-watch", "OK", typed_value=1),
            ValueError,
            "sample watch is invalid",
        ),
        (
            lambda _paths_value: SampleValue(
                WatchItem.variable("counter"),
                "OK",
                typed_value=1,
                definition=[],
            ),
            TypeError,
            "sample definition must be a JSON object",
        ),
        (
            lambda _paths_value: SampleValue(
                WatchItem.variable("counter"),
                "OK",
                typed_value={"value": float("nan")},
            ),
            ValueError,
            "JSON number must be finite",
        ),
        (
            lambda _paths_value: unix_ns_to_utc(-1),
            ValueError,
            "Unix nanoseconds must be a non-negative signed 64-bit integer",
        ),
        (
            lambda paths: replace(_batch(paths, 1), group_id="not-a-uuid"),
            ValueError,
            "batch identifiers must be UUIDs",
        ),
        (
            lambda paths: replace(_history_slice(paths), binding=object()),
            ValueError,
            "history batch binding is invalid",
        ),
        (
            lambda paths: replace(_history_slice(paths), run_id="not-a-uuid"),
            ValueError,
            "history batch identifiers must be UUIDs",
        ),
        (
            lambda paths: replace(
                _history_slice(paths),
                scheduled_unix_ns=101,
                captured_unix_ns=100,
            ),
            ValueError,
            "captured time precedes scheduled time",
        ),
        (
            lambda paths: replace(_history_slice(paths), actual_rate_hz=-1),
            ValueError,
            "actual rate is invalid",
        ),
        (
            lambda paths: replace(
                _history_slice(paths),
                batch_value_count=MAX_SAMPLE_VALUES + 1,
            ),
            ValueError,
            "history batch value count exceeds the batch limit",
        ),
    ],
)
def test_history_related_models_reject_invalid_state(
    tmp_path: Path,
    invalid_model,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        invalid_model(_paths(tmp_path))


def test_history_trusted_preflight_fails_closed_when_the_main_file_disappears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.query_history(HistoryQuery("monitor-1", 0, 1_000)).ok
        assert store._database._integrity_identity is not None
        database_path = store._database.path
        real_lstat = storage_module.os.lstat

        def disappearing_lstat(path: Path):
            if Path(path) == database_path:
                raise FileNotFoundError(database_path)
            return real_lstat(path)

        monkeypatch.setattr(storage_module.os, "lstat", disappearing_lstat)
        with pytest.raises(StorageFailure, match="monitor storage database is missing"):
            store._database._preflight_existing(
                busy_timeout_ms=1_000,
                trusted_hot_path=True,
            )
    finally:
        store.close()


def test_history_file_inspection_marks_a_disappearing_wal_as_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        wal_path = store._database.path.with_name(store._database.path.name + "-wal")
        real_identity = storage_module._identity
        real_lstat = storage_module.os.lstat

        def disappearing_identity(path: Path):
            if path == wal_path:
                raise StorageFailure(
                    "MONITOR_STORAGE_INVALID",
                    "WAL disappeared during identity validation",
                )
            return real_identity(path)

        def disappearing_lstat(path: Path):
            if Path(path) == wal_path:
                raise FileNotFoundError(wal_path)
            return real_lstat(path)

        monkeypatch.setattr(storage_module, "_identity", disappearing_identity)
        monkeypatch.setattr(storage_module.os, "lstat", disappearing_lstat)

        inspected = store._database._inspect_storage_files()
        assert inspected[wal_path] == (-1, -1, -1)
    finally:
        store.close()
