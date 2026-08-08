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


@pytest.mark.parametrize("kind", ["foreign", "future", "legacy", "wrong-workspace"])
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
        elif kind == "legacy":
            connection.execute("PRAGMA user_version = 0")
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
    calls_by_path: dict[Path, int] = {}

    def changed_identity(path: Path):
        identity = real_identity(path)
        calls_by_path[path] = calls_by_path.get(path, 0) + 1
        if path == race_paths.data_root.parent and calls_by_path[path] % 2 == 0:
            return identity[0], identity[1] + 1
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


def test_replaced_data_root_is_rejected_before_foreign_database_access(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "victim")
    _seed_database(paths)
    foreign_paths = WorkspacePaths.from_roots(
        tmp_path / "foreign-state",
        paths.project_root,
        LOGICAL_ID,
        "monitor-1",
    )
    foreign_store = GroupStore(foreign_paths)
    try:
        assert _create(foreign_store, "Foreign").ok
    finally:
        foreign_store.close()

    store = GroupStore(paths)
    original_root = tmp_path / "original-state"
    paths.data_root.replace(original_root)
    foreign_paths.data_root.replace(paths.data_root)
    before = _inventory(paths.monitor_root)
    try:
        listed = store.list_groups()
        mutated = _create(store, "Must Not Land")
    finally:
        store.close()

    assert not listed.ok and listed.code == "MONITOR_STORAGE_INVALID"
    assert not mutated.ok and mutated.code == "MONITOR_STORAGE_INVALID"
    assert _inventory(paths.monitor_root) == before


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


def test_timed_out_started_write_releases_the_shared_writer_promptly(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))

    def seed(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE slow_rows(value INTEGER NOT NULL)")
        connection.executemany(
            "INSERT INTO slow_rows(value) VALUES (?)",
            ((value,) for value in range(100)),
        )

    database.write(seed)

    def slow_read(connection: sqlite3.Connection) -> None:
        connection.create_function(
            "monitor_test_delay",
            1,
            lambda value: (time.sleep(0.01), value)[1],
        )
        connection.execute("SELECT monitor_test_delay(value) FROM slow_rows").fetchall()

    try:
        with pytest.raises(StorageFailure) as timed_out:
            database.try_write(slow_read, timeout_ms=20)
        assert timed_out.value.code == "MONITOR_STORAGE_BUSY"
        started = time.monotonic()
        assert database.write(lambda connection: connection.execute("SELECT 1").fetchone()[0]) == 1
        assert time.monotonic() - started < 0.3
    finally:
        database.close()


def test_hot_reads_do_not_run_full_quick_check_for_every_connection(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)

    monkeypatch.setattr(database, "_validate", observed_validate)
    try:
        assert database.read(lambda connection: 1, empty=0) == 1
        assert database.read(lambda connection: 2, empty=0) == 2
    finally:
        database.close()

    assert [statement for statement in statements if "quick_check" in statement] == [
        "PRAGMA quick_check(1)"
    ]


def test_storage_filesystem_error_boundaries_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    file_root_paths = _paths(tmp_path / "root-file")
    file_root_paths.workspace_root.mkdir(parents=True)
    file_root_paths.monitor_root.write_bytes(b"not-a-directory")
    rooted = GroupStore(file_root_paths)
    try:
        assert _create(rooted).code == "MONITOR_STORAGE_INVALID"
    finally:
        rooted.close()

    orphan_paths = _paths(tmp_path / "orphan")
    orphan_paths.monitor_root.mkdir(parents=True)
    orphan_paths.monitor_root.joinpath("monitor.sqlite3-wal").write_bytes(b"orphan")
    orphan = GroupStore(orphan_paths)
    try:
        assert orphan.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        orphan.close()

    full_paths = _paths(tmp_path / "full")
    monkeypatch.setattr(storage_module, "MAX_DATABASE_BYTES", -1)
    full = GroupStore(full_paths)
    try:
        assert _create(full).code == "MONITOR_STORAGE_FULL"
    finally:
        full.close()

    denied = tmp_path / "denied"
    denied.write_bytes(b"x")
    real_open = Path.open

    def denied_open(path: Path, *args, **kwargs):
        if path == denied:
            raise PermissionError("secret")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)
    with pytest.raises(StorageFailure) as opened:
        storage_module._opened_identity(denied)
    assert opened.value.code == "MONITOR_STORAGE_INVALID"


def test_storage_creation_and_inspection_races_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path / "appear")
    database = MonitorDatabase(paths)
    real_open = Path.open

    def appeared(path: Path, mode="r", *args, **kwargs):
        if path == database.path and mode == "xb":
            raise FileExistsError("raced")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", appeared)
    try:
        with pytest.raises(StorageFailure) as raced:
            database.write(lambda connection: None)
        assert raced.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()

    stable_paths = _paths(tmp_path / "inspect")
    main = _seed_database(stable_paths)
    inspected = MonitorDatabase(stable_paths)
    real_opened = storage_module._opened_identity

    def vanished(path: Path):
        if path == main:
            raise FileNotFoundError(path)
        return real_opened(path)

    monkeypatch.setattr(storage_module, "_opened_identity", vanished)
    try:
        with pytest.raises(StorageFailure) as changed:
            inspected.read(lambda connection: None, empty=None)
        assert changed.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        inspected.close()


def test_validation_and_open_failures_are_stable_storage_results(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    connection = sqlite3.connect(f"file:{main.as_posix()}?mode=ro&immutable=1", uri=True)
    before = storage_module._identity(main)
    real_identity = storage_module._identity
    monkeypatch.setattr(
        storage_module,
        "_identity",
        lambda path: (before[0], before[1] + 1, before[2]) if path == main else real_identity(path),
    )
    try:
        with pytest.raises(StorageFailure) as changed:
            database._validate(connection, before=before)
        assert changed.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        connection.close()
        database.close()

    corrupt_paths = _paths(tmp_path / "connect")
    _seed_database(corrupt_paths)
    corrupt = MonitorDatabase(corrupt_paths)
    real_connect = sqlite3.connect

    def broken_connect(database_path, *args, **kwargs):
        if isinstance(database_path, str) and "immutable=1" in database_path:
            raise sqlite3.DatabaseError("secret")
        return real_connect(database_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", broken_connect)
    try:
        with pytest.raises(StorageFailure) as broken:
            corrupt.read(lambda connection: None, empty=None)
        assert broken.value.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        corrupt.close()


def test_invalid_try_write_timeout_and_failing_owned_close_are_bounded(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    for timeout in (True, 0, 251):
        with pytest.raises(StorageFailure) as invalid:
            database.try_write(lambda connection: None, timeout_ms=timeout)
        assert invalid.value.code == "MONITOR_STORAGE_INVALID"

    entered = threading.Event()
    release = threading.Event()

    def failing(connection):
        entered.set()
        assert release.wait(timeout=5)
        raise StorageFailure("MONITOR_STORAGE_INVALID", "expected")

    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(database.write, failing)
        assert entered.wait(timeout=5)
        closing = executor.submit(database.close)
        assert not closing.done()
        release.set()
        with pytest.raises(StorageFailure):
            writing.result(timeout=5)
        closing.result(timeout=5)


def test_path_component_creation_and_file_inspection_failures_are_stable(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    linked = tmp_path / "linked"
    linked.write_bytes(b"private")
    linked_alias = tmp_path / "linked-alias"
    os.link(linked, linked_alias)
    with pytest.raises(StorageFailure) as unsafe_open:
        storage_module._opened_identity(linked)
    assert unsafe_open.value.code == "MONITOR_STORAGE_INVALID"

    component_paths = _paths(tmp_path / "component")
    component_paths.workspace_root.parent.mkdir(parents=True)
    component_paths.workspace_root.write_bytes(b"not-a-directory")
    component = GroupStore(component_paths)
    try:
        assert component.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        component.close()

    snapshot_paths = _paths(tmp_path / "snapshot")
    snapshot = MonitorDatabase(snapshot_paths)
    try:
        captured = snapshot._directory_snapshot(snapshot_paths.monitor_root / "missing" / "child")
        assert captured
    finally:
        snapshot.close()

    denied_paths = _paths(tmp_path / "denied-create")
    denied = MonitorDatabase(denied_paths)
    real_mkdir = Path.mkdir

    def denied_mkdir(path: Path, *args, **kwargs):
        if path == denied_paths.data_root:
            raise PermissionError("secret")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied_mkdir)
    try:
        with pytest.raises(StorageFailure) as creation:
            denied.write(lambda connection: None)
        assert creation.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        denied.close()


def test_read_validation_and_write_open_errors_are_classified(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)

    class Cursor:
        def fetchone(self):
            return ("broken",)

    class BadQuickCheck:
        def execute(self, statement):
            assert statement == "PRAGMA quick_check(1)"
            return Cursor()

    with pytest.raises(StorageFailure) as quick:
        database._validate(BadQuickCheck(), before=storage_module._identity(main))  # type: ignore[arg-type]
    assert quick.value.code == "MONITOR_STORAGE_CORRUPT"

    with pytest.raises(StorageFailure) as read_error:
        database.read(
            lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("other")),
            empty=None,
        )
    assert read_error.value.code == "MONITOR_STORAGE_CORRUPT"
    database.close()

    open_paths = _paths(tmp_path / "write-open")
    _seed_database(open_paths)
    opening = MonitorDatabase(open_paths)
    real_connect = sqlite3.connect

    def denied_connect(database_path, *args, **kwargs):
        if database_path == opening.path:
            raise sqlite3.DatabaseError("secret")
        return real_connect(database_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", denied_connect)
    try:
        with pytest.raises(StorageFailure) as denied:
            opening.write(lambda connection: None)
        assert denied.value.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        opening.close()


def test_history_logical_byte_accounting_is_constant_time_transactional_and_cascading(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))

    def exercise(connection: sqlite3.Connection) -> None:
        def count() -> int:
            return connection.execute(
                "SELECT logical_bytes FROM monitor_history_accounting WHERE singleton = 1"
            ).fetchone()[0]

        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes) VALUES (?,?,?,?,?,?)",
            ("session", "run-rollback", 0, 1, b"{}", 10),
        )
        connection.execute(
            "INSERT INTO history_values(batch_id,ordinal,row_json,payload_bytes) VALUES (?,?,?,?)",
            (cursor.lastrowid, 0, b"{}", 3),
        )
        assert count() == 13
        connection.rollback()
        assert count() == 0

        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes) VALUES (?,?,?,?,?,?)",
            ("session", "run-commit", 0, 2, b"{}", 11),
        )
        connection.executemany(
            "INSERT INTO history_values(batch_id,ordinal,row_json,payload_bytes) VALUES (?,?,?,?)",
            ((cursor.lastrowid, 0, b"{}", 3), (cursor.lastrowid, 1, b"{}", 5)),
        )
        connection.commit()
        assert count() == 19
        connection.execute("DELETE FROM history_batches WHERE batch_id = ?", (cursor.lastrowid,))
        assert count() == 0

    try:
        database.write(exercise)
    finally:
        database.close()


@pytest.mark.parametrize("malformation", ["missing", "negative", "text"])
def test_invalid_history_accounting_is_storage_corrupt(tmp_path: Path, malformation: str) -> None:
    paths = _paths(tmp_path / malformation)
    main = _seed_database(paths)
    connection = sqlite3.connect(main)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        if malformation == "missing":
            connection.execute("DELETE FROM monitor_history_accounting")
        elif malformation == "negative":
            connection.execute("UPDATE monitor_history_accounting SET logical_bytes = -1")
        else:
            connection.execute("UPDATE monitor_history_accounting SET logical_bytes = 'bad'")
        connection.commit()
    finally:
        connection.close()

    database = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure) as corrupt:
            database.read(lambda current: None, empty=None)
        assert corrupt.value.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        database.close()
