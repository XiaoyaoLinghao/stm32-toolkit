"""Offline storage and history integrity boundaries for Monitor.

Most cases use the real owned SQLite files, real hardlinks and the public
storage/history entry points.  The first-create case deliberately injects
narrow OS creation/``fstat`` failures at the filesystem boundary; it does not
claim a natural filesystem race.  No probe, firmware or network is opened, and
foreign bytes are never mutated or removed.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

import stm32_monitor.history as history_module
from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.storage import MonitorDatabase, StorageFailure
from test_history import _batch, _paths as _history_paths
from test_storage import _paths as _storage_paths, _seed_database


def _storage_authority(database: Path) -> tuple[object, ...]:
    connection = sqlite3.connect(database)
    try:
        return (
            connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0],
            tuple(
                connection.execute(
                    "SELECT singleton, workspace_id, schema_version "
                    "FROM monitor_metadata ORDER BY singleton"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT group_id, name, name_key, description, interval_ms, "
                    "revision, created_at_utc, updated_at_utc "
                    "FROM watch_groups ORDER BY group_id"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT group_id, ordinal, kind, selector "
                    "FROM group_items ORDER BY group_id, ordinal"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT singleton, logical_bytes "
                    "FROM monitor_history_accounting ORDER BY singleton"
                ).fetchall()
            ),
        )
    finally:
        connection.close()


def _history_authority(database: Path) -> tuple[object, ...]:
    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
    )
    try:
        return (
            tuple(
                connection.execute(
                    "SELECT batch_id, session_id, run_id, sequence, captured_ns, "
                    "payload_json, payload_bytes, payload_sha256, value_count "
                    "FROM history_batches ORDER BY batch_id"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT batch_id, ordinal, selector_kind, selector, value_json, "
                    "value_bytes, value_sha256 FROM history_values "
                    "ORDER BY batch_id, ordinal"
                ).fetchall()
            ),
            connection.execute(
                "SELECT singleton, logical_bytes FROM monitor_history_accounting"
            ).fetchone(),
        )
    finally:
        connection.close()


def test_v2_workspace_mismatch_refuses_before_metadata_migration(
    tmp_path: Path,
) -> None:
    paths = _storage_paths(tmp_path)
    database = _seed_database(paths)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE monitor_metadata SET workspace_id = 'other', schema_version = 2"
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    finally:
        connection.close()
    before = _storage_authority(database)
    assert before[1] == 2
    assert before[2] == ((1, "other", 2),)

    store = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure) as refused:
            store.write(lambda current: current.execute("SELECT 1").fetchone())
        assert refused.value.code == "MONITOR_WORKSPACE_MISMATCH"
        assert refused.value.public_message == (
            "monitor storage belongs to another workspace"
        )
    finally:
        store.close()

    assert _storage_authority(database) == before


def test_v3_metadata_version_mismatch_refuses_read_and_write(
    tmp_path: Path,
) -> None:
    paths = _storage_paths(tmp_path)
    database = _seed_database(paths)
    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE monitor_metadata SET schema_version = 2")
        connection.commit()
    finally:
        connection.close()
    before = _storage_authority(database)
    assert before[1] == 3 and before[2] == ((1, paths.workspace_id, 2),)

    store = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure) as read_refused:
            store.read(lambda current: current.execute("SELECT 1").fetchone(), empty=None)
        assert read_refused.value.code == "MONITOR_STORAGE_CORRUPT"
        assert read_refused.value.public_message == (
            "monitor storage metadata version is invalid"
        )

        with pytest.raises(StorageFailure) as write_refused:
            store.write(lambda current: None)
        assert write_refused.value.code == "MONITOR_STORAGE_CORRUPT"
        assert write_refused.value.public_message == (
            "monitor storage metadata version is invalid"
        )
    finally:
        store.close()

    assert _storage_authority(database) == before


@pytest.mark.parametrize(
    ("failure", "expected_message", "main_created", "wal_created", "shm_created"),
    [
        (
            "main-permission",
            "monitor storage cannot be created",
            False,
            False,
            False,
        ),
        (
            "sidecar-exists",
            "monitor storage sidecar appeared during creation",
            True,
            False,
            False,
        ),
        (
            "sidecar-oserror",
            "monitor storage sidecar cannot be created",
            True,
            False,
            False,
        ),
        (
            "sidecar-identity",
            "monitor storage sidecar changed during creation",
            True,
            True,
            False,
        ),
    ],
)
def test_first_create_filesystem_failures_fail_closed_without_foreign_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_message: str,
    main_created: bool,
    wal_created: bool,
    shm_created: bool,
) -> None:
    paths = _storage_paths(tmp_path / failure)
    store = MonitorDatabase(paths)
    database = store.path
    wal = database.with_name(database.name + "-wal")
    shm = database.with_name(database.name + "-shm")
    sentinel = tmp_path / f"{failure}-sentinel.bin"
    sentinel.write_bytes(b"external foreign bytes")
    real_open = Path.open
    real_fstat = os.fstat
    opened_fd: list[int] = []

    def guarded_open(path: Path, mode: str = "r", *args, **kwargs):
        if path == database and mode == "xb" and failure == "main-permission":
            raise PermissionError("denied by offline test injection")
        if path == wal and mode == "xb" and failure in {
            "sidecar-exists",
            "sidecar-oserror",
            "sidecar-identity",
        }:
            if failure == "sidecar-exists":
                raise FileExistsError("raced by offline test injection")
            if failure == "sidecar-oserror":
                raise OSError("denied by offline test injection")
            stream = real_open(path, mode, *args, **kwargs)
            opened_fd.append(stream.fileno())
            return stream
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    if failure == "sidecar-identity":
        def shifted_fstat(fd: int) -> os.stat_result:
            metadata = real_fstat(fd)
            if opened_fd and fd == opened_fd[0]:
                return os.stat_result(
                    (
                        metadata.st_mode,
                        metadata.st_ino + 1,
                        metadata.st_dev,
                        metadata.st_nlink,
                        metadata.st_uid,
                        metadata.st_gid,
                        metadata.st_size,
                        metadata.st_atime,
                        metadata.st_mtime,
                        metadata.st_ctime,
                    )
                )
            return metadata

        monkeypatch.setattr(os, "fstat", shifted_fstat)

    try:
        with pytest.raises(StorageFailure) as refused:
            store.write(lambda current: None)
        assert refused.value.code == "MONITOR_STORAGE_INVALID"
        assert refused.value.public_message == expected_message
    finally:
        store.close()

    assert sentinel.read_bytes() == b"external foreign bytes"
    assert database.exists() is main_created
    assert wal.exists() is wal_created
    assert shm.exists() is shm_created
    if paths.monitor_root.exists():
        assert {path.name for path in paths.monitor_root.iterdir()} <= {
            "monitor.sqlite3",
            "monitor.sqlite3-wal",
            "monitor.sqlite3-shm",
        }
    if main_created:
        connection = sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
        )
        try:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
            assert connection.execute(
                "SELECT workspace_id, schema_version FROM monitor_metadata"
            ).fetchone() == (paths.workspace_id, 3)
        finally:
            connection.close()


def test_history_query_preflight_rejects_a_real_wal_hardlink_and_recovers(
    tmp_path: Path,
) -> None:
    paths = _history_paths(tmp_path)
    store = HistoryStore(paths)
    database = paths.monitor_root / "monitor.sqlite3"
    sidecar = database.with_name(database.name + "-wal")
    shm = database.with_name(database.name + "-shm")
    backup = database.with_name(database.name + "-wal.owned-backup")
    sentinel = tmp_path / "external-wal-sentinel"
    query = HistoryQuery("monitor-1", 0, 1_000)
    linked = False
    backup_moved = False
    wal_identity: tuple[int, int, int, int] | None = None
    wal_bytes: bytes | None = None
    shm_identity: tuple[int, int, int] | None = None

    def restore_owned_wal() -> None:
        nonlocal backup_moved
        assert wal_identity is not None and wal_bytes is not None
        assert not sidecar.exists()
        metadata = os.lstat(backup)
        assert (metadata.st_dev, metadata.st_ino) == (
            wal_identity[0],
            wal_identity[1],
        )
        assert backup.read_bytes() == wal_bytes
        os.replace(backup, sidecar)
        restored_metadata = os.lstat(sidecar)
        assert (
            restored_metadata.st_dev,
            restored_metadata.st_ino,
            restored_metadata.st_size,
            restored_metadata.st_nlink,
        ) == wal_identity
        backup_moved = False

    try:
        assert not backup.exists()
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.query_history(query).ok

        # SQLite may legitimately keep owned sidecars.  Checkpoint through a
        # closed auxiliary connection, then take the durable baseline from the
        # main file before touching any owned sidecar.
        auxiliary = sqlite3.connect(database)
        try:
            checkpoint = auxiliary.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
            assert checkpoint is not None and len(checkpoint) == 3
            busy, log_frames, checkpointed_frames = checkpoint
            assert busy == 0
            assert checkpointed_frames == log_frames
        finally:
            auxiliary.close()
        before = _history_authority(database)
        if shm.exists():
            metadata = os.lstat(shm)
            shm_identity = (metadata.st_dev, metadata.st_ino, metadata.st_size)
        if sidecar.exists():
            metadata = os.lstat(sidecar)
            wal_identity = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_nlink,
            )
            assert wal_identity[3] == 1
            wal_bytes = sidecar.read_bytes()
            # Preserve the owned WAL bytes and identity under an owned rename
            # while no SQLite connection exists; restore it after the probe.
            assert not backup.exists()
            os.replace(sidecar, backup)
            backup_moved = True
            restored_metadata = os.lstat(backup)
            assert (restored_metadata.st_dev, restored_metadata.st_ino) == (
                wal_identity[0],
                wal_identity[1],
            )

        sentinel.write_bytes(b"external WAL sentinel")
        os.link(sentinel, sidecar)
        linked = True
        linked_state = (sentinel.read_bytes(), os.lstat(sentinel).st_nlink)

        refused = store.query_history(query)
        assert not refused.ok
        assert refused.operation == "history.query"
        assert refused.code == "MONITOR_STORAGE_INVALID"
        assert refused.message == "monitor storage is not a private regular file"
        assert _history_authority(database) == before
        assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == linked_state
        assert os.path.samefile(sentinel, sidecar)
        if shm_identity is not None:
            assert shm.exists()
            metadata = os.lstat(shm)
            assert (metadata.st_dev, metadata.st_ino, metadata.st_size) == shm_identity

        assert os.path.samefile(sentinel, sidecar)
        sidecar.unlink()
        linked = False
        if backup_moved:
            restore_owned_wal()

        restored = store.query_history(query)
        assert restored.ok and restored.data is not None
        assert [batch.sequence for batch in restored.data.batches] == [1]
        assert _history_authority(database) == before
    finally:
        store.close()
        if linked and sidecar.exists():
            assert os.path.samefile(sentinel, sidecar)
            sidecar.unlink()
        if backup_moved and not sidecar.exists():
            restore_owned_wal()

    assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == (b"external WAL sentinel", 1)
    reopened = HistoryStore(paths)
    try:
        durable = reopened.query_history(query)
        assert durable.ok and durable.data is not None
        assert [batch.sequence for batch in durable.data.batches] == [1]
    finally:
        reopened.close()


def test_retention_final_time_budget_before_commit_marks_retained_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _history_paths(tmp_path)
    store = HistoryStore(paths)
    database = paths.monitor_root / "monitor.sqlite3"
    now_ns = history_module.RETENTION_AGE_NS + 10_000
    cutoff = now_ns - history_module.RETENTION_AGE_NS
    ticks = [0, 0, 0, history_module.RETENTION_TIME_BUDGET_NS]

    def clock() -> int:
        return (
            ticks.pop(0)
            if ticks
            else history_module.RETENTION_TIME_BUDGET_NS
        )

    try:
        assert store.append_batch(_batch(paths, 1, captured_ns=100)).ok
        assert store.append_batch(_batch(paths, 2, captured_ns=10_500)).ok
        monkeypatch.setattr(history_module.time, "monotonic_ns", clock)

        retained = store.run_retention(now_ns=now_ns)
        assert retained.ok and retained.data is not None
        assert retained.data["deletedBatches"] == 1
        assert retained.data["passes"] == 1
        assert retained.data["moreWork"] is True
        assert retained.data["earliestCapturedUnixNs"] == 10_500
        assert retained.data["logicalBytes"] <= history_module.RETENTION_LOGICAL_BYTES
    finally:
        store.close()

    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
    )
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM history_batches WHERE captured_ns < ?", (cutoff,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT sequence, captured_ns FROM history_batches ORDER BY batch_id"
        ).fetchall() == [(2, 10_500)]
        expected_logical = connection.execute(
            "SELECT COALESCE(SUM(payload_bytes), 0) FROM history_batches"
        ).fetchone()[0] + connection.execute(
            "SELECT COALESCE(SUM(value_bytes), 0) FROM history_values"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT logical_bytes FROM monitor_history_accounting WHERE singleton = 1"
        ).fetchone()[0] == expected_logical
    finally:
        connection.close()
    assert retained.data["logicalBytes"] == expected_logical
