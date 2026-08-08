from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.groups import GroupStore
from stm32_monitor.models import WatchItem
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _paths(tmp_path: Path, *, logical_id: UUID = LOGICAL_ID) -> WorkspacePaths:
    project = tmp_path / f"project-{logical_id}"
    project.mkdir()
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
    try:
        paths.monitor_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory redirects")

    store = GroupStore(paths)
    try:
        result = _create(store)
        assert not result.ok and result.code == "MONITOR_STORAGE_INVALID"
        assert list(outside.iterdir()) == []
    finally:
        store.close()

