from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
from dataclasses import replace
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
        name=name,
        description="core counters",
        interval_ms=250,
        items=(WatchItem.variable("counter"), WatchItem.register("GPIOA.IDR")),
        authorized=True,
    )


def test_fresh_workspace_lists_zero_groups_without_creating_storage(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = GroupStore(paths)
    try:
        result = store.list_groups()
        assert result.ok and result.data == ()
        assert not paths.monitor_root.exists()
        assert not paths.project_root.joinpath(".stm32-monitor.yaml").exists()
    finally:
        store.close()


def test_authorized_create_persists_only_under_workspace_monitor_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = GroupStore(paths)
    try:
        result = _create(store)
        assert result.ok and result.data.revision == 1
        assert paths.monitor_root.joinpath("monitor.sqlite3").is_file()
        assert list(paths.project_root.iterdir()) == []
        assert store.get_group(result.data.group_id).data == result.data
        json.dumps(store.list_groups().to_dict())
    finally:
        store.close()


def test_false_like_authorization_never_creates_or_mutates(tmp_path: Path) -> None:
    for authorized in (False, "true", 1, None, [], {}):
        paths = _paths(tmp_path / str(type(authorized).__name__) / str(len(str(authorized))))
        store = GroupStore(paths)
        try:
            result = store.create_group("Core", "", 250, (), authorized=authorized)
            assert not result.ok and result.code == "MONITOR_AUTH_REQUIRED"
            assert not paths.monitor_root.exists()
        finally:
            store.close()


def test_update_and_delete_require_exact_revision_cas(tmp_path: Path) -> None:
    store = GroupStore(_paths(tmp_path))
    try:
        created = _create(store).data
        stale = store.update_group(
            created.group_id,
            expected_revision=2,
            name="Renamed",
            authorized=True,
        )
        assert not stale.ok and stale.code == "MONITOR_GROUP_CONFLICT"

        updated = store.update_group(
            created.group_id,
            expected_revision=1,
            name="Renamed",
            authorized=True,
        )
        assert updated.ok and updated.data.revision == 2 and updated.data.name == "Renamed"
        stale_delete = store.delete_group(created.group_id, expected_revision=1, authorized=True)
        assert not stale_delete.ok and stale_delete.code == "MONITOR_GROUP_CONFLICT"
        deleted = store.delete_group(created.group_id, expected_revision=2, authorized=True)
        assert deleted.ok and store.list_groups().data == ()
    finally:
        store.close()


def test_name_uniqueness_uses_nfc_and_casefold(tmp_path: Path) -> None:
    store = GroupStore(_paths(tmp_path))
    try:
        assert _create(store, "Caf\u00e9").ok
        duplicate = _create(store, "CAFE\u0301")
        assert not duplicate.ok and duplicate.code == "MONITOR_GROUP_CONFLICT"
    finally:
        store.close()


def test_group_and_item_limits_fail_without_partial_writes(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.groups as groups

    monkeypatch.setattr(groups, "MAX_GROUPS", 2)
    monkeypatch.setattr(groups, "MAX_ITEMS_PER_GROUP", 2)
    monkeypatch.setattr(groups, "MAX_TOTAL_ITEMS", 3)
    store = GroupStore(_paths(tmp_path))
    try:
        assert _create(store, "One").ok
        too_many_items = store.create_group(
            "TooMany",
            "",
            250,
            tuple(WatchItem.variable(f"v{i}") for i in range(3)),
            authorized=True,
        )
        assert not too_many_items.ok and too_many_items.code == "MONITOR_GROUP_LIMIT_EXCEEDED"
        assert store.create_group("Two", "", 250, (WatchItem.variable("other"),), authorized=True).ok
        full = store.create_group("Three", "", 250, (), authorized=True)
        assert not full.ok and full.code == "MONITOR_GROUP_LIMIT_EXCEEDED"
        assert len(store.list_groups().data) == 2
    finally:
        store.close()


def test_import_is_bounded_explicit_atomic_and_conflict_safe(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = GroupStore(paths)
    document = json.dumps(
        {
            "schemaVersion": 1,
            "groups": [
                {"name": "One", "description": "", "intervalMs": 250, "items": []},
                {"name": "Two", "description": "", "intervalMs": 500, "items": [{"kind": "variable", "expression": "counter"}]},
            ],
        }
    ).encode()
    try:
        denied = store.import_groups(document, authorized=False)
        assert denied.code == "MONITOR_AUTH_REQUIRED" and not paths.monitor_root.exists()
        imported = store.import_groups(document, authorized=True)
        assert imported.ok and len(imported.data) == 2

        conflict = store.import_groups(document, authorized=True)
        assert not conflict.ok and conflict.code == "MONITOR_IMPORT_CONFLICT"
        assert len(store.list_groups().data) == 2

        oversized = store.import_groups(b"{" + b" " * (1024 * 1024), authorized=True)
        assert not oversized.ok and oversized.code == "MONITOR_IMPORT_INVALID"
    finally:
        store.close()


def test_two_writers_serialize_without_lost_groups(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = GroupStore(paths)
    second = GroupStore(paths)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda args: args[0].create_group(args[1], "", 250, (), authorized=True), ((first, "A"), (second, "B"))))
        assert all(result.ok for result in results)
        assert {group.name for group in first.list_groups().data} == {"A", "B"}
    finally:
        first.close()
        second.close()


def test_readers_progress_while_bounded_writer_serializes_mutations(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    stores = [GroupStore(paths) for _ in range(4)]
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            mutations = [
                executor.submit(stores[index % 4].create_group, f"G{index}", "", 250, (), authorized=True)
                for index in range(12)
            ]
            reads = [executor.submit(stores[index % 4].list_groups) for index in range(24)]
        assert all(future.result().ok for future in mutations)
        assert all(future.result().ok for future in reads)
        assert len(stores[0].list_groups().data) == 12
    finally:
        for store in stores:
            store.close()


def test_writer_close_waits_for_owned_mutation_to_finish(tmp_path: Path) -> None:
    database = MonitorDatabase(_paths(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    def mutation(connection):
        entered.set()
        assert release.wait(timeout=5)
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(database.write, mutation)
        assert entered.wait(timeout=5)
        closing = executor.submit(database.close)
        assert not closing.done()
        release.set()
        assert writing.result(timeout=5) == "committed"
        closing.result(timeout=5)


def test_wrong_workspace_future_version_and_corruption_are_stable_failures(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    store = GroupStore(paths)
    assert _create(store).ok
    store.close()
    database = paths.monitor_root / "monitor.sqlite3"

    connection = sqlite3.connect(database)
    connection.execute("UPDATE monitor_metadata SET workspace_id = ?", ("other",))
    connection.commit()
    connection.close()
    wrong = GroupStore(paths)
    try:
        assert wrong.list_groups().code == "MONITOR_WORKSPACE_MISMATCH"
    finally:
        wrong.close()

    other_paths = _paths(tmp_path / "future")
    other = GroupStore(other_paths)
    assert _create(other).ok
    other.close()
    connection = sqlite3.connect(other_paths.monitor_root / "monitor.sqlite3")
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    future = GroupStore(other_paths)
    try:
        assert future.list_groups().code == "MONITOR_STORAGE_VERSION_UNSUPPORTED"
    finally:
        future.close()

    corrupt_paths = _paths(tmp_path / "corrupt")
    corrupt_paths.monitor_root.mkdir(parents=True)
    corrupt_paths.monitor_root.joinpath("monitor.sqlite3").write_bytes(b"not sqlite")
    corrupt = GroupStore(corrupt_paths)
    try:
        assert corrupt.list_groups().code == "MONITOR_STORAGE_CORRUPT"
    finally:
        corrupt.close()


def test_redirected_monitor_root_is_rejected_before_database_open(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    paths.workspace_root.mkdir(parents=True)
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(paths.monitor_root), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert created.returncode == 0, created.stderr
    else:
        paths.monitor_root.symlink_to(outside, target_is_directory=True)

    store = GroupStore(paths)
    try:
        result = _create(store)
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
        assert list(outside.iterdir()) == []
    finally:
        store.close()


def test_get_update_and_delete_missing_or_invalid_groups_are_stable(tmp_path: Path) -> None:
    store = GroupStore(_paths(tmp_path))
    missing = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    try:
        assert store.get_group("bad").code == "MONITOR_REQUEST_INVALID"
        assert store.get_group(missing).code == "MONITOR_GROUP_NOT_FOUND"
        assert store.update_group(missing, expected_revision=1, name="new", authorized=True).code == "MONITOR_GROUP_NOT_FOUND"
        assert store.update_group(missing, expected_revision=True, authorized=True).code == "MONITOR_REQUEST_INVALID"
        assert store.update_group(missing, expected_revision=1, authorized=False).code == "MONITOR_AUTH_REQUIRED"
        assert store.delete_group(missing, expected_revision=1, authorized=True).code == "MONITOR_GROUP_NOT_FOUND"
        assert store.delete_group(missing, expected_revision=True, authorized=True).code == "MONITOR_REQUEST_INVALID"
        assert store.delete_group(missing, expected_revision=1, authorized=False).code == "MONITOR_AUTH_REQUIRED"
    finally:
        store.close()


def test_update_revalidates_name_item_and_workspace_limits(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.groups as groups_module

    store = GroupStore(_paths(tmp_path))
    try:
        one = _create(store, "One").data
        two = store.create_group("Two", "", 250, (), authorized=True).data
        assert store.update_group(one.group_id, expected_revision=1, name="TWO", authorized=True).code == "MONITOR_GROUP_CONFLICT"
        assert store.update_group(one.group_id, expected_revision=1, interval_ms=1, authorized=True).code == "MONITOR_REQUEST_INVALID"
        monkeypatch.setattr(groups_module, "MAX_ITEMS_PER_GROUP", 1)
        assert store.update_group(two.group_id, expected_revision=1, items=(WatchItem.variable("a"), WatchItem.variable("b")), authorized=True).code == "MONITOR_GROUP_LIMIT_EXCEEDED"
        monkeypatch.setattr(groups_module, "MAX_ITEMS_PER_GROUP", 256)
        monkeypatch.setattr(groups_module, "MAX_TOTAL_ITEMS", 2)
        assert store.update_group(two.group_id, expected_revision=1, items=(WatchItem.variable("a"),), authorized=True).code == "MONITOR_GROUP_LIMIT_EXCEEDED"
    finally:
        store.close()


@pytest.mark.parametrize(
    "document",
    [
        b'{"schemaVersion":2,"groups":[]}',
        b'{"schemaVersion":1,"groups":[{"name":"G"}]}',
        b'{"schemaVersion":1,"groups":[{"name":"G","description":"","intervalMs":250,"items":[{"kind":"address","address":"0"}]}]}',
        b'{"schemaVersion":1,"groups":[{"name":"Same","description":"","intervalMs":250,"items":[]},{"name":"same","description":"","intervalMs":250,"items":[]}]}',
    ],
)
def test_import_rejects_wrong_schema_partial_items_and_internal_conflicts(tmp_path: Path, document: bytes) -> None:
    store = GroupStore(_paths(tmp_path))
    try:
        result = store.import_groups(document, authorized=True)
        assert not result.ok and result.code == "MONITOR_IMPORT_INVALID"
        assert store.list_groups().data == ()
    finally:
        store.close()


def test_storage_rejects_escaped_nonregular_and_replaced_database(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    escaped = replace(paths, monitor_root=tmp_path / "escaped")
    escaped_store = GroupStore(escaped)
    try:
        assert escaped_store.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        escaped_store.close()

    paths.monitor_root.mkdir(parents=True)
    paths.monitor_root.joinpath("monitor.sqlite3").mkdir()
    nonregular = GroupStore(paths)
    try:
        assert nonregular.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        nonregular.close()

    swap_paths = _paths(tmp_path / "swap")
    seeded = GroupStore(swap_paths)
    assert _create(seeded).ok
    seeded.close()
    real_identity = storage_module._identity
    calls = 0

    def changed_identity(path):
        nonlocal calls
        calls += 1
        device, inode, size = real_identity(path)
        return (device, inode + 1, size) if calls == 2 else (device, inode, size)

    monkeypatch.setattr(storage_module, "_identity", changed_identity)
    swapped = GroupStore(swap_paths)
    try:
        assert swapped.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        swapped.close()


def test_storage_identity_schema_and_error_mapping_are_stable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    database.write(lambda connection: None)
    file_path = paths.monitor_root / "monitor.sqlite3"

    connection = sqlite3.connect(file_path)
    connection.execute("PRAGMA application_id = 0")
    connection.close()
    with pytest.raises(StorageFailure, match="identity") as invalid_identity:
        database.read(lambda connection: None, empty=None)
    assert invalid_identity.value.code == "MONITOR_STORAGE_INVALID"
    connection = sqlite3.connect(file_path)
    connection.execute("PRAGMA application_id = 1398033741")
    connection.close()

    for exception, code in (
        (sqlite3.IntegrityError("constraint"), "MONITOR_STORAGE_INVALID"),
        (sqlite3.OperationalError("database is locked"), "MONITOR_STORAGE_BUSY"),
        (sqlite3.OperationalError("other"), "MONITOR_STORAGE_INVALID"),
        (sqlite3.DatabaseError("broken"), "MONITOR_STORAGE_CORRUPT"),
    ):
        with pytest.raises(StorageFailure) as raised:
            database.write(lambda connection, error=exception: (_ for _ in ()).throw(error))
        assert raised.value.code == code
    with pytest.raises(StorageFailure) as busy_read:
        database.read(lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("locked")), empty=None)
    assert busy_read.value.code == "MONITOR_STORAGE_BUSY"
    database.close()
    database.close()
    with pytest.raises(StorageFailure) as closed:
        database.write(lambda connection: None)
    assert closed.value.code == "MONITOR_STORAGE_INVALID"


def test_storage_constructor_queue_schema_and_inspection_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    with pytest.raises(TypeError, match="WorkspacePaths"):
        MonitorDatabase(object())

    paths = _paths(tmp_path)
    database = MonitorDatabase(paths)
    database.write(lambda connection: None)
    with pytest.raises(StorageFailure) as corrupt_read:
        database.read(lambda connection: (_ for _ in ()).throw(sqlite3.DatabaseError("broken")), empty=None)
    assert corrupt_read.value.code == "MONITOR_STORAGE_CORRUPT"

    for _ in range(128):
        assert database._writer.slots.acquire(blocking=False)
    try:
        with pytest.raises(StorageFailure) as full_queue:
            database.write(lambda connection: None)
        assert full_queue.value.code == "MONITOR_STORAGE_BUSY"
    finally:
        for _ in range(128):
            database._writer.slots.release()
    database.close()

    inspect_paths = _paths(tmp_path / "inspect")
    monkeypatch.setattr(storage_module, "_is_redirect", lambda path: (_ for _ in ()).throw(PermissionError("denied")))
    inspected = GroupStore(inspect_paths)
    try:
        assert inspected.list_groups().code == "MONITOR_STORAGE_INVALID"
    finally:
        inspected.close()


def test_store_rejects_workspace_state_inside_project_before_any_write(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    paths = WorkspacePaths.from_roots(project / ".state", project, LOGICAL_ID, "monitor-1")
    store = GroupStore(paths)
    try:
        result = store.create_group("G", "", 250, (), authorized=True)
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
        assert not (project / ".state").exists()
    finally:
        store.close()


def test_schema_initialization_rolls_back_every_statement_on_failure(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.storage as storage_module

    paths = _paths(tmp_path)
    statements = storage_module._SCHEMA_STATEMENTS
    monkeypatch.setattr(
        storage_module,
        "_SCHEMA_STATEMENTS",
        statements[:2] + ("THIS IS NOT SQL",) + statements[2:],
    )
    database = MonitorDatabase(paths)
    try:
        with pytest.raises(StorageFailure):
            database.write(lambda connection: None)
    finally:
        database.close()
    connection = sqlite3.connect(paths.monitor_root / "monitor.sqlite3")
    try:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        assert tables == []
    finally:
        connection.close()
