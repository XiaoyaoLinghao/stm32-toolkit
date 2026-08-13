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
from stm32_monitor.storage import BUSY_TIMEOUT_MS, MonitorDatabase, StorageFailure
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_fresh_database_uses_normalized_history_schema_v2(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    try:
        version, batch_columns, value_columns = database.write(
            lambda connection: (
                connection.execute("PRAGMA user_version").fetchone()[0],
                [row[1] for row in connection.execute("PRAGMA table_info(history_batches)")],
                [row[1] for row in connection.execute("PRAGMA table_info(history_values)")],
            )
        )
    finally:
        database.close()

    assert version == 2
    assert batch_columns == [
        "batch_id", "session_id", "run_id", "sequence", "captured_ns",
        "payload_json", "payload_bytes", "payload_sha256", "value_count",
    ]
    assert value_columns == [
        "batch_id", "ordinal", "selector_kind", "selector", "value_json",
        "value_bytes", "value_sha256",
    ]


@pytest.mark.parametrize(
    ("application_id", "version", "expected_code"),
    [
        (1, 0, "MONITOR_STORAGE_INVALID"),
        (0, 99, "MONITOR_STORAGE_VERSION_UNSUPPORTED"),
        (0, 1, "MONITOR_STORAGE_INVALID"),
    ],
)
def test_initialize_rechecks_sqlite_identity_and_version_inside_exclusive_transaction(
    tmp_path: Path,
    application_id: int,
    version: int,
    expected_code: str,
) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(f"PRAGMA application_id = {application_id}")
        connection.execute(f"PRAGMA user_version = {version}")
        with pytest.raises(StorageFailure) as rejected:
            database._initialize(connection)
        assert rejected.value.code == expected_code
        assert not connection.in_transaction
    finally:
        connection.close()
        database.close()


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
        timeout_ms=200,
    ) <= 200
    with pytest.raises(StorageFailure, match="sentinel"):
        database.try_write(
            lambda connection: (_ for _ in ()).throw(StorageFailure("MONITOR_STORAGE_INVALID", "sentinel")),
            timeout_ms=50,
        )
    database.close()


def test_try_write_cancelled_before_invoke_skips_open_and_releases_writer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    assert database.write(lambda connection: connection.execute("SELECT 1").fetchone()[0]) == 1
    worker_started = threading.Event()
    release_worker = threading.Event()
    operation_ran = threading.Event()
    opened = 0
    submitted = []
    original_submit = database._writer.executor.submit
    original_open = database._open_write

    def delayed_submit(function, *args, **kwargs):
        def delayed():
            worker_started.set()
            assert release_worker.wait(timeout=5)
            return function(*args, **kwargs)

        future = original_submit(delayed)
        submitted.append(future)
        return future

    def observed_open(*, busy_timeout_ms=BUSY_TIMEOUT_MS):
        nonlocal opened
        opened += 1
        return original_open(busy_timeout_ms=busy_timeout_ms)

    monkeypatch.setattr(database._writer.executor, "submit", delayed_submit)
    monkeypatch.setattr(database, "_open_write", observed_open)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            attempt = executor.submit(
                database.try_write,
                lambda connection: operation_ran.set(),
                timeout_ms=25,
            )
            assert worker_started.wait(timeout=5)
            with pytest.raises(StorageFailure) as raised:
                attempt.result(timeout=5)
        assert raised.value.code == "MONITOR_STORAGE_BUSY"

        monkeypatch.setattr(database._writer.executor, "submit", original_submit)
        release_worker.set()
        with pytest.raises(StorageFailure) as cancelled:
            submitted[0].result(timeout=5)
        assert cancelled.value.code == "MONITOR_STORAGE_BUSY"
        assert not operation_ran.is_set()
        assert opened == 0
        assert submitted[0].done()
        with database._admission_lock:
            assert submitted[0] not in database._accepted

        started = time.monotonic()
        assert database.try_write(
            lambda connection: connection.execute("SELECT 1").fetchone()[0],
            timeout_ms=200,
        ) == 1
        assert time.monotonic() - started < 0.1
    finally:
        release_worker.set()
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


def test_hot_writes_amortize_sql_validation_until_the_storage_fingerprint_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)

    monkeypatch.setattr(database, "_validate", observed_validate)
    try:
        def owned_change(connection: sqlite3.Connection, value: int) -> int:
            connection.execute(
                "UPDATE watch_groups SET description = ?",
                (f"owned change {value}",),
            )
            connection.commit()
            return value

        for value in (1, 2, 3):
            assert database.write(
                lambda connection, value=value: owned_change(connection, value)
            ) == value
        validations_before_change = [
            statement
            for statement in statements
            if "quick_check" in statement
        ]
        assert validations_before_change == ["PRAGMA quick_check(1)"]

        with sqlite3.connect(main) as external:
            external.execute(
                "UPDATE watch_groups SET description = 'external fingerprint change'"
            )
            external.commit()
        assert database.write(
            lambda connection: connection.execute(
                "SELECT description FROM watch_groups"
            ).fetchone()[0]
        ) == "external fingerprint change"
    finally:
        database.close()

    validations_after_change = [
        statement
        for statement in statements
        if "quick_check" in statement
    ]
    assert validations_after_change == [
        "PRAGMA quick_check(1)",
        "PRAGMA quick_check(1)",
    ]


def test_hot_write_trust_rejects_a_byte_valid_main_database_replacement(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    replacement = tmp_path / "replacement.sqlite3"
    try:
        assert database.write(
            lambda connection: connection.execute("SELECT 1").fetchone()[0]
        ) == 1
        external = sqlite3.connect(main)
        try:
            external.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            external.close()
        shutil.copy2(main, replacement)
        before = replacement.read_bytes()
        os.replace(replacement, main)

        with pytest.raises(StorageFailure) as rejected:
            database.write(
                lambda connection: connection.execute(
                    "UPDATE watch_groups SET description = 'must not mutate replacement'"
                )
            )
        assert rejected.value.code == "MONITOR_STORAGE_INVALID"
        assert main.read_bytes() == before
    finally:
        database.close()


def test_write_does_not_trust_a_fingerprint_changed_after_integrity_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate
    changed = False

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        nonlocal changed
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)
        if not changed:
            changed = True
            metadata = main.stat()
            os.utime(
                main,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
            )

    monkeypatch.setattr(database, "_validate", observed_validate)
    try:
        assert database.write(
            lambda connection: connection.execute("SELECT 1").fetchone()[0]
        ) == 1
        assert database.write(
            lambda connection: connection.execute("SELECT 2").fetchone()[0]
        ) == 2
    finally:
        database.close()

    assert [statement for statement in statements if "quick_check" in statement] == [
        "PRAGMA quick_check(1)",
        "PRAGMA quick_check(1)",
    ]


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


def test_read_validates_and_queries_through_one_read_only_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    real_connect = sqlite3.connect
    read_only_connections = 0

    def observed_connect(database_path, *args, **kwargs):
        nonlocal read_only_connections
        if kwargs.get("uri") is True and str(database_path).endswith("?mode=ro"):
            read_only_connections += 1
        return real_connect(database_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    try:
        assert database.read(
            lambda connection: connection.execute("SELECT 1").fetchone()[0],
            empty=0,
        ) == 1
    finally:
        database.close()

    assert read_only_connections == 1


@pytest.mark.parametrize("missing_inspection", [1, 2, 3, 4])
def test_read_rejects_a_missing_main_file_at_every_snapshot_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_inspection: int,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    real_inspect = database._inspect_storage_files
    inspections = 0
    operation_called = False

    def observed_inspect():
        nonlocal inspections
        inspections += 1
        if inspections == missing_inspection:
            return {}
        return real_inspect()

    def operation(connection: sqlite3.Connection) -> int:
        nonlocal operation_called
        operation_called = True
        return connection.execute("SELECT 1").fetchone()[0]

    monkeypatch.setattr(database, "_inspect_storage_files", observed_inspect)
    try:
        with pytest.raises(StorageFailure) as rejected:
            database.read(operation, empty=0)
        assert rejected.value.code == "MONITOR_STORAGE_INVALID"
        assert operation_called is (missing_inspection == 4)
    finally:
        database.close()


def test_external_file_identity_change_requires_a_new_integrity_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)

    monkeypatch.setattr(database, "_validate", observed_validate)
    try:
        assert database.read(lambda connection: 1, empty=0) == 1
        external = sqlite3.connect(main)
        try:
            external.execute(
                "UPDATE watch_groups SET description = 'externally changed'"
            )
            external.commit()
        finally:
            external.close()
        assert database.read(lambda connection: 2, empty=0) == 2
    finally:
        database.close()

    assert [statement for statement in statements if "quick_check" in statement] == [
        "PRAGMA quick_check(1)",
        "PRAGMA quick_check(1)",
    ]


def test_persistent_wal_commit_is_visible_and_revalidated_before_return(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)

    monkeypatch.setattr(database, "_validate", observed_validate)
    writer = sqlite3.connect(main)
    try:
        assert database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM watch_groups"
            ).fetchone()[0],
            empty=0,
        ) == 1
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "INSERT INTO watch_groups(group_id,name,name_key,description,interval_ms,revision,created_at_utc,updated_at_utc) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                "22222222-2222-4222-8222-222222222222",
                "WAL Visible",
                "wal visible",
                "",
                250,
                1,
                "2026-08-08T00:00:00.000000Z",
                "2026-08-08T00:00:00.000000Z",
            ),
        )
        writer.commit()
        wal = main.with_name(main.name + "-wal")
        assert wal.exists() and wal.stat().st_size > 0

        assert database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM watch_groups"
            ).fetchone()[0],
            empty=0,
        ) == 2
    finally:
        writer.close()
        database.close()

    assert [statement for statement in statements if "quick_check" in statement] == [
        "PRAGMA quick_check(1)",
        "PRAGMA quick_check(1)",
    ]


def test_uncertain_persistent_wal_cannot_alias_cached_no_wal_trust(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    statements: list[str] = []
    real_validate = database._validate
    real_opened_identity = storage_module._opened_identity

    def observed_validate(connection: sqlite3.Connection, **kwargs) -> None:
        connection.set_trace_callback(statements.append)
        real_validate(connection, **kwargs)

    monkeypatch.setattr(database, "_validate", observed_validate)
    writer = sqlite3.connect(main)
    try:
        assert database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM watch_groups"
            ).fetchone()[0],
            empty=0,
        ) == 1
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "INSERT INTO watch_groups(group_id,name,name_key,description,interval_ms,revision,created_at_utc,updated_at_utc) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                "22222222-2222-4222-8222-222222222222",
                "Uncertain WAL",
                "uncertain wal",
                "",
                250,
                1,
                "2026-08-08T00:00:00.000000Z",
                "2026-08-08T00:00:00.000000Z",
            ),
        )
        writer.commit()
        wal = main.with_name(main.name + "-wal")
        assert wal.stat().st_size > 0

        def uncertain_wal_identity(path: Path):
            identity = real_opened_identity(path)
            if path == wal:
                return identity[0], identity[1] + 1, identity[2]
            return identity

        monkeypatch.setattr(
            storage_module,
            "_opened_identity",
            uncertain_wal_identity,
        )
        assert database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM watch_groups"
            ).fetchone()[0],
            empty=0,
        ) == 2
    finally:
        writer.close()
        database.close()

    quick_checks = [statement for statement in statements if "quick_check" in statement]
    assert len(quick_checks) >= 2
    assert set(quick_checks) == {"PRAGMA quick_check(1)"}


def test_malformed_database_version_probe_maps_to_storage_corrupt(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.monitor_root.mkdir(parents=True)
    paths.monitor_root.joinpath("monitor.sqlite3").write_bytes(b"not sqlite")
    database = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure) as corrupt:
            database.read(lambda connection: None, empty=None)
        assert corrupt.value.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        database.close()


def test_identity_change_during_preflight_is_revalidated_before_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    main = _seed_database(paths)
    database = MonitorDatabase(paths)
    real_validate = database._validate
    changed = False

    def change_during_validation(connection: sqlite3.Connection, **kwargs) -> None:
        nonlocal changed
        real_validate(connection, **kwargs)
        if not changed:
            changed = True
            external = sqlite3.connect(main)
            try:
                external.execute(
                    "UPDATE watch_groups SET description = 'changed during preflight'"
                )
                external.commit()
            finally:
                external.close()

    monkeypatch.setattr(database, "_validate", change_during_validation)
    try:
        description = database.read(
            lambda connection: connection.execute(
                "SELECT description FROM watch_groups"
            ).fetchone()[0],
            empty=None,
        )
        assert description == "changed during preflight"
    finally:
        database.close()


def test_hot_readers_progress_while_shared_writer_changes_file_identities(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    stores = [GroupStore(paths) for _ in range(4)]
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            mutations = [
                executor.submit(
                    stores[index % 4].create_group,
                    f"Concurrent {index}",
                    "",
                    250,
                    (),
                    authorized=True,
                )
                for index in range(12)
            ]
            reads = [
                executor.submit(stores[index % 4].list_groups)
                for index in range(24)
            ]
        assert [future.result().code for future in mutations] == ["OK"] * 12
        read_outcomes = [
            (future.result().code, future.result().message) for future in reads
        ]
        assert read_outcomes == [("OK", "")] * 24
    finally:
        for store in stores:
            store.close()


def test_optional_wal_identity_churn_does_not_fail_a_snapshot_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    writer = sqlite3.connect(main)
    database = MonitorDatabase(paths)
    real_opened_identity = storage_module._opened_identity
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "UPDATE watch_groups SET description = 'visible through a changing WAL'"
        )
        writer.commit()
        wal = main.with_name(main.name + "-wal")
        assert wal.stat().st_size > 0

        def changing_optional_identity(path: Path):
            identity = real_opened_identity(path)
            if path == wal:
                return identity[0], identity[1] + 1, identity[2]
            return identity

        monkeypatch.setattr(
            storage_module,
            "_opened_identity",
            changing_optional_identity,
        )
        assert database.read(
            lambda connection: connection.execute(
                "SELECT description FROM watch_groups"
            ).fetchone()[0],
            empty=None,
        ) == "visible through a changing WAL"
    finally:
        database.close()
        writer.close()


def test_optional_wal_fingerprint_churn_invalidates_trust_without_failing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    writer = sqlite3.connect(main)
    database = MonitorDatabase(paths)
    real_lstat = os.lstat
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("UPDATE watch_groups SET description = 'wal fingerprint'")
        writer.commit()
        wal = main.with_name(main.name + "-wal")
        files = database._inspect_storage_files()
        baseline = database._integrity_fingerprint(files)
        main_only = tuple(entry for entry in baseline if entry[0] != wal.name)
        assert len(main_only) + 1 == len(baseline)

        def vanished(path: Path):
            if path == wal:
                raise FileNotFoundError(path)
            return real_lstat(path)

        monkeypatch.setattr(os, "lstat", vanished)
        vanished_fingerprint = database._integrity_fingerprint(files)
        assert vanished_fingerprint != main_only
        assert vanished_fingerprint[-1] == (wal.name, -1, -1, -1, -1)

        def replaced(path: Path):
            metadata = real_lstat(path)
            if path == wal:
                return SimpleNamespace(
                    st_dev=metadata.st_dev,
                    st_ino=metadata.st_ino + 1,
                    st_size=metadata.st_size,
                    st_mtime_ns=metadata.st_mtime_ns,
                )
            return metadata

        monkeypatch.setattr(os, "lstat", replaced)
        replaced_fingerprint = database._integrity_fingerprint(files)
        assert replaced_fingerprint != main_only
        assert replaced_fingerprint[-1] == (wal.name, -1, -1, -1, -1)
    finally:
        database.close()
        writer.close()


def test_continuous_identity_churn_exhausts_bounded_revalidation_as_busy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    real_fingerprint = database._integrity_fingerprint
    calls = 0

    def changing_fingerprint(files):
        nonlocal calls
        calls += 1
        fingerprint = real_fingerprint(files)
        return tuple(
            (*entry[:-1], entry[-1] + calls)
            for entry in fingerprint
        )

    monkeypatch.setattr(database, "_integrity_fingerprint", changing_fingerprint)
    try:
        started = time.monotonic()
        with pytest.raises(StorageFailure) as busy:
            database.read(lambda connection: 1, empty=0)
        assert busy.value.code == "MONITOR_STORAGE_BUSY"
        assert time.monotonic() - started < 0.5
    finally:
        database.close()


def test_transient_identity_churn_beyond_three_snapshots_retries_until_stable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    real_fingerprint = database._integrity_fingerprint
    calls = 0

    def transient_fingerprint(files):
        nonlocal calls
        calls += 1
        fingerprint = real_fingerprint(files)
        if calls <= 9:
            return tuple(
                (*entry[:-1], entry[-1] + calls)
                for entry in fingerprint
            )
        return fingerprint

    monkeypatch.setattr(database, "_integrity_fingerprint", transient_fingerprint)
    try:
        assert database.read(lambda connection: 1, empty=0) == 1
        assert calls > 9
    finally:
        database.close()


def test_storage_private_identity_guards_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    trusted_path, trusted_identity = database._trusted_directories[-1]
    try:
        monkeypatch.setattr(
            storage_module,
            "_directory_identity",
            lambda path: (trusted_identity[0] + 1, trusted_identity[1])
            if path == trusted_path
            else trusted_identity,
        )
        with pytest.raises(StorageFailure) as remembered:
            database._remember_directory(trusted_path)
        assert remembered.value.code == "MONITOR_STORAGE_INVALID"

        with pytest.raises(StorageFailure) as revalidated:
            database._revalidate_directories(((trusted_path, trusted_identity),))
        assert revalidated.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


def test_storage_path_rejects_an_intermediate_regular_file(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    blocked = paths.workspace_root / "blocked"
    paths.workspace_root.mkdir(parents=True)
    blocked.write_text("not a directory", encoding="utf-8")
    try:
        with pytest.raises(StorageFailure) as rejected:
            database._require_path(blocked / "child")
        assert rejected.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


def test_storage_path_rejects_an_intermediate_redirect(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    redirected = paths.workspace_root / "redirected"
    redirected.mkdir(parents=True)
    redirected_identity = os.lstat(redirected).st_ino
    real_is_redirect = storage_module._metadata_is_redirect
    monkeypatch.setattr(
        storage_module,
        "_metadata_is_redirect",
        lambda metadata: metadata.st_ino == redirected_identity or real_is_redirect(metadata),
    )
    try:
        with pytest.raises(StorageFailure) as rejected:
            database._require_path(redirected / "child")
        assert rejected.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


def test_storage_pinned_main_identity_cannot_be_replaced(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    try:
        database._remember_validated_integrity((1, 2, 3), (("monitor.sqlite3", 1, 2, 3, 4),))
        with pytest.raises(StorageFailure) as replaced:
            database._remember_validated_integrity((1, 3, 3), (("monitor.sqlite3", 1, 3, 3, 4),))
        assert replaced.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


def test_storage_create_and_preflight_reject_inconsistent_file_sets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure) as existing:
            database._create_database_file()
        assert existing.value.code == "MONITOR_STORAGE_INVALID"

        monkeypatch.setattr(database, "_inspect_storage_files", lambda: {})
        with pytest.raises(StorageFailure) as missing:
            database._preflight_existing(busy_timeout_ms=BUSY_TIMEOUT_MS)
        assert missing.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


class _StorageCursor:
    def __init__(self, row) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _RefreshConnection:
    _monitor_data_version = 1

    def execute(self, statement: str) -> _StorageCursor:
        if statement == "PRAGMA wal_checkpoint(TRUNCATE)":
            return _StorageCursor((0, 0, 0))
        if statement == "PRAGMA data_version":
            return _StorageCursor((1,))
        raise AssertionError(statement)


class _UnusableCheckpointConnection(_RefreshConnection):
    def execute(self, statement: str) -> _StorageCursor:
        if statement == "PRAGMA wal_checkpoint(TRUNCATE)":
            return _StorageCursor((1, 0, 0))
        return super().execute(statement)


def test_owned_integrity_refresh_handles_unusable_or_missing_snapshots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    _seed_database(paths)
    database = MonitorDatabase(paths)
    try:
        unusable = _RefreshConnection()
        unusable._monitor_data_version = None
        database._refresh_owned_integrity(unusable)
        database._refresh_owned_integrity(_UnusableCheckpointConnection())

        monkeypatch.setattr(database, "_inspect_storage_files", lambda: {})
        with pytest.raises(StorageFailure) as missing_before:
            database._refresh_owned_integrity(_RefreshConnection())
        assert missing_before.value.code == "MONITOR_STORAGE_INVALID"

        real_inspect = MonitorDatabase._inspect_storage_files.__get__(database)
        snapshots = iter((real_inspect(), {}))
        monkeypatch.setattr(database, "_inspect_storage_files", lambda: next(snapshots))
        with pytest.raises(StorageFailure) as missing_after:
            database._refresh_owned_integrity(_RefreshConnection())
        assert missing_after.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()


def test_invoke_rechecks_cancellation_after_open(tmp_path: Path, monkeypatch) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    cancelled = threading.Event()

    def open_then_cancel(*, busy_timeout_ms: int):
        assert busy_timeout_ms == BUSY_TIMEOUT_MS
        connection = sqlite3.connect(":memory:")
        cancelled.set()
        return connection

    monkeypatch.setattr(database, "_open_write", open_then_cancel)
    try:
        with pytest.raises(StorageFailure) as busy:
            database._invoke(
                lambda connection: pytest.fail("cancelled operation ran"),
                busy_timeout_ms=BUSY_TIMEOUT_MS,
                cancel_event=cancelled,
            )
        assert busy.value.code == "MONITOR_STORAGE_BUSY"
    finally:
        database.close()


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


def test_storage_identity_races_and_metadata_errors_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    main = _seed_database(paths)
    writer = sqlite3.connect(main)
    database = MonitorDatabase(paths)
    real_identity = storage_module._identity
    real_opened_identity = storage_module._opened_identity
    real_lstat = os.lstat
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("UPDATE watch_groups SET description = 'identity-race'")
        writer.commit()
        wal = main.with_name(main.name + "-wal")
        assert wal.exists()

        with monkeypatch.context() as raced:
            wal_identity_calls = 0

            def disappearing_wal_identity(path: Path):
                nonlocal wal_identity_calls
                if path != wal:
                    return real_identity(path)
                wal_identity_calls += 1
                if wal_identity_calls == 1:
                    return real_identity(path)
                raise FileNotFoundError(path)

            raced.setattr(
                storage_module,
                "_opened_identity",
                lambda path: (_ for _ in ()).throw(FileNotFoundError(path))
                if path == wal
                else real_opened_identity(path),
            )
            identities = database._inspect_storage_files()
            assert identities[wal] == storage_module._UNCERTAIN_FILE_IDENTITY

        with monkeypatch.context() as raced:
            raced.setattr(
                storage_module,
                "_opened_identity",
                lambda path: (_ for _ in ()).throw(
                    StorageFailure("MONITOR_STORAGE_INVALID", "raced")
                )
                if path == wal
                else real_opened_identity(path),
            )
            raced.setattr(
                storage_module,
                "_identity",
                disappearing_wal_identity,
            )
            identities = database._inspect_storage_files()
            assert identities[wal] == storage_module._UNCERTAIN_FILE_IDENTITY

        identities = database._inspect_storage_files()
        with monkeypatch.context() as raced:
            raced.setattr(
                os,
                "lstat",
                lambda path: (_ for _ in ()).throw(FileNotFoundError(path))
                if path == main
                else real_lstat(path),
            )
            with pytest.raises(StorageFailure) as vanished:
                database._integrity_fingerprint(identities)
            assert vanished.value.code == "MONITOR_STORAGE_INVALID"

        with monkeypatch.context() as raced:
            raced.setattr(
                os,
                "lstat",
                lambda path: (_ for _ in ()).throw(PermissionError(path))
                if path == main
                else real_lstat(path),
            )
            with pytest.raises(StorageFailure) as denied:
                database._integrity_fingerprint(identities)
            assert denied.value.code == "MONITOR_STORAGE_INVALID"
    finally:
        database.close()
        writer.close()


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
        if isinstance(database_path, str) and database_path.endswith("?mode=ro"):
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

    class IncompleteValidation:
        def execute(self, statement):
            assert "pragma_application_id" in statement
            return type("EmptyCursor", (), {"fetchone": lambda self: None})()

    with pytest.raises(StorageFailure) as incomplete:
        database._validate(  # type: ignore[arg-type]
            IncompleteValidation(),
            before=storage_module._identity(main),
            full_integrity=False,
        )
    assert incomplete.value.code == "MONITOR_STORAGE_CORRUPT"

    class FailedValidation:
        def execute(self, statement):
            raise sqlite3.DatabaseError("broken validation")

    with pytest.raises(StorageFailure) as failed_validation:
        database._validate(  # type: ignore[arg-type]
            FailedValidation(),
            before=storage_module._identity(main),
            full_integrity=False,
        )
    assert failed_validation.value.code == "MONITOR_STORAGE_CORRUPT"

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
            "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes,payload_sha256,value_count) VALUES (?,?,?,?,?,?,?,?)",
            ("session", "run-rollback", 0, 1, b"{}", 10, "a" * 64, 1),
        )
        connection.execute(
            "INSERT INTO history_values(batch_id,ordinal,selector_kind,selector,value_json,value_bytes,value_sha256) VALUES (?,?,?,?,?,?,?)",
            (cursor.lastrowid, 0, "variable", "counter", b"{}", 3, "b" * 64),
        )
        assert count() == 13
        connection.rollback()
        assert count() == 0

        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes,payload_sha256,value_count) VALUES (?,?,?,?,?,?,?,?)",
            ("session", "run-commit", 0, 2, b"{}", 11, "a" * 64, 2),
        )
        connection.executemany(
            "INSERT INTO history_values(batch_id,ordinal,selector_kind,selector,value_json,value_bytes,value_sha256) VALUES (?,?,?,?,?,?,?)",
            (
                (cursor.lastrowid, 0, "variable", "counter", b"{}", 3, "b" * 64),
                (cursor.lastrowid, 1, "register", "R0", b"{}", 5, "c" * 64),
            ),
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
