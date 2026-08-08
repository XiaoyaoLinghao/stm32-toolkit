from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.groups import GroupStore
from stm32_monitor.models import WatchItem
from stm32_monitor.storage import MonitorDatabase, StorageFailure
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _paths(tmp_path: Path, *, logical_id: UUID = LOGICAL_ID) -> WorkspacePaths:
    project = tmp_path / f"project-{logical_id}"
    project.mkdir(parents=True)
    return WorkspacePaths.from_roots(tmp_path / "state", project, logical_id, "monitor-1")


def _create(store: GroupStore, name: str = "Core"):
    return store.create_group(
        name,
        "",
        250,
        (WatchItem.variable("counter"),),
        authorized=True,
    )


def _inventory(root: Path) -> dict[str, tuple[bytes, int]]:
    if not root.exists():
        return {}
    return {
        path.name: (path.read_bytes(), os.lstat(path).st_nlink)
        for path in root.iterdir()
        if path.is_file()
    }


def _seed_database(paths: WorkspacePaths) -> Path:
    store = GroupStore(paths)
    try:
        assert _create(store).ok
    finally:
        store.close()
    return paths.monitor_root / "monitor.sqlite3"


@pytest.mark.parametrize("kind", ["foreign", "future", "wrong-workspace"])
def test_rejected_existing_database_is_validated_before_any_write(tmp_path: Path, kind: str) -> None:
    paths = _paths(tmp_path / kind)
    database = _seed_database(paths)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        if kind == "foreign":
            connection.execute("PRAGMA application_id = 0")
        elif kind == "future":
            connection.execute("PRAGMA user_version = 99")
        else:
            connection.execute("UPDATE monitor_metadata SET workspace_id = 'other'")
        connection.commit()
    finally:
        connection.close()
    before = _inventory(paths.monitor_root)

    store = GroupStore(paths)
    try:
        result = _create(store, "Rejected")
        assert not result.ok
        assert result.code in {
            "MONITOR_STORAGE_INVALID",
            "MONITOR_STORAGE_VERSION_UNSUPPORTED",
            "MONITOR_WORKSPACE_MISMATCH",
        }
    finally:
        store.close()

    assert _inventory(paths.monitor_root) == before
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    finally:
        connection.close()


def test_main_database_hardlink_is_rejected_without_touching_external_sentinel(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    database = _seed_database(paths)
    sentinel = tmp_path / "external.sqlite3"
    database.replace(sentinel)
    os.link(sentinel, database)
    before = (sentinel.read_bytes(), os.lstat(sentinel).st_nlink)

    store = GroupStore(paths)
    try:
        result = _create(store, "Rejected")
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
    finally:
        store.close()

    assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == before
    assert os.path.samefile(sentinel, database)


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_sidecar_hardlink_is_rejected_before_sqlite_can_touch_it(tmp_path: Path, suffix: str) -> None:
    paths = _paths(tmp_path / suffix.removeprefix("-"))
    database = _seed_database(paths)
    sentinel = tmp_path / f"external{suffix}"
    sentinel.write_bytes(b"external-sidecar-sentinel")
    sidecar = database.with_name(database.name + suffix)
    os.link(sentinel, sidecar)
    before = (sentinel.read_bytes(), os.lstat(sentinel).st_nlink)

    store = GroupStore(paths)
    try:
        result = _create(store, "Rejected")
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
    finally:
        store.close()

    assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == before
    assert os.path.samefile(sentinel, sidecar)


def test_directory_creation_is_componentwise_and_revalidates_ancestor_identity(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    real_mkdir = Path.mkdir
    calls: list[tuple[Path, bool]] = []

    def observed_mkdir(path: Path, mode=0o777, parents=False, exist_ok=False):
        calls.append((path, parents))
        return real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", observed_mkdir)
    database = MonitorDatabase(paths)
    try:
        database.write(lambda connection: None)
    finally:
        database.close()
    created = [parents for path, parents in calls if path.is_relative_to(paths.data_root)]
    assert created and not any(created)

    race_paths = _paths(tmp_path / "race")
    real_identity = storage_module._directory_identity
    identities: dict[Path, tuple[int, int]] = {}

    def changed_identity(path: Path):
        identity = real_identity(path)
        previous = identities.setdefault(path, identity)
        if path == race_paths.data_root.parent and len(identities) > 1:
            return previous[0], previous[1] + 1
        return identity

    monkeypatch.setattr(storage_module, "_directory_identity", changed_identity)
    raced = GroupStore(race_paths)
    try:
        result = _create(raced)
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
    finally:
        raced.close()
    assert not race_paths.monitor_root.exists()


def test_opened_and_named_database_identity_must_match(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    _seed_database(paths)
    real_opened = storage_module._opened_identity

    def changed(path: Path):
        device, inode, size = real_opened(path)
        return device, inode + 1, size

    monkeypatch.setattr(storage_module, "_opened_identity", changed)
    store = GroupStore(paths)
    try:
        result = store.list_groups()
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
    finally:
        store.close()


def test_submit_close_race_is_owned_and_submit_failure_never_leaks_slot(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    original_submit = database._writer.executor.submit
    entered = threading.Event()
    release = threading.Event()

    def delayed_submit(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_submit(*args, **kwargs)

    monkeypatch.setattr(database._writer.executor, "submit", delayed_submit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(database.write, lambda connection: "accepted")
        assert entered.wait(timeout=5)
        closing = executor.submit(database.close)
        time.sleep(0.05)
        release.set()
        assert writing.result(timeout=5) == "accepted"
        closing.result(timeout=5)

    failed = MonitorDatabase(paths)
    monkeypatch.setattr(
        failed._writer.executor,
        "submit",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("executor stopped")),
    )
    try:
        with pytest.raises(StorageFailure) as raised:
            failed.write(lambda connection: None)
        assert raised.value.code == "MONITOR_STORAGE_INVALID"
        acquired = sum(failed._writer.slots.acquire(blocking=False) for _ in range(128))
        assert acquired == 128
        for _ in range(acquired):
            failed._writer.slots.release()
    finally:
        failed.close()


def test_try_write_is_deadline_bounded_cancels_queue_and_uses_attempt_busy_timeout(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    entered = threading.Event()
    release = threading.Event()
    queued_ran = threading.Event()

    def occupied(connection):
        entered.set()
        assert release.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        blocking = executor.submit(database.write, occupied)
        assert entered.wait(timeout=5)
        started = time.monotonic()
        with pytest.raises(StorageFailure) as raised:
            database.try_write(lambda connection: queued_ran.set(), timeout_ms=50)
        elapsed = time.monotonic() - started
        assert raised.value.code == "MONITOR_STORAGE_BUSY"
        assert elapsed < 0.5
        assert not queued_ran.is_set()
        release.set()
        blocking.result(timeout=5)

    assert database.try_write(
        lambda connection: connection.execute("PRAGMA busy_timeout").fetchone()[0],
        timeout_ms=25,
    ) <= 25
    with pytest.raises(StorageFailure, match="sentinel"):
        database.try_write(
            lambda connection: (_ for _ in ()).throw(StorageFailure("MONITOR_STORAGE_INVALID", "sentinel")),
            timeout_ms=50,
        )
    database.close()

