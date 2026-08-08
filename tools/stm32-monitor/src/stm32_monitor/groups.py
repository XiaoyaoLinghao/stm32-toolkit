from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Iterable, cast
from uuid import UUID

from stm32_toolkit.paths import WorkspacePaths

from .models import WatchGroup, WatchItem
from .protocol import ProtocolResult, ProtocolViolation, failure, parse_json_object, success
from .storage import MonitorDatabase, StorageFailure


MAX_GROUPS = 128
MAX_ITEMS_PER_GROUP = 256
MAX_TOTAL_ITEMS = 4_096
MAX_IMPORT_BYTES = 1024 * 1024


def _name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _public_storage_failure(operation: str, error: StorageFailure) -> ProtocolResult[None]:
    return failure(operation, error.code, error.public_message)


class GroupStore:
    def __init__(self, paths: WorkspacePaths) -> None:
        self._database = MonitorDatabase(paths)

    @staticmethod
    def _load_group(connection: sqlite3.Connection, row: tuple[object, ...]) -> WatchGroup:
        item_rows = connection.execute(
            "SELECT kind, selector FROM group_items WHERE group_id = ? ORDER BY ordinal",
            (row[0],),
        ).fetchall()
        return WatchGroup(
            group_id=UUID(cast(str, row[0])),
            name=cast(str, row[1]),
            description=cast(str, row[2]),
            interval_ms=cast(int, row[3]),
            items=tuple(WatchItem(cast(str, kind), cast(str, selector)) for kind, selector in item_rows),
            revision=cast(int, row[4]),
            created_at_utc=_parse_utc(cast(str, row[5])),
            updated_at_utc=_parse_utc(cast(str, row[6])),
        )

    def list_groups(self) -> ProtocolResult[tuple[WatchGroup, ...]]:
        operation = "groups.list"
        try:
            groups = self._database.read(
                lambda connection: tuple(
                    self._load_group(connection, row)
                    for row in connection.execute(
                        "SELECT group_id, name, description, interval_ms, revision, created_at_utc, updated_at_utc FROM watch_groups ORDER BY name_key, group_id"
                    ).fetchall()
                ),
                empty=(),
            )
            return success(operation, groups)
        except StorageFailure as error:
            return _public_storage_failure(operation, error)

    def get_group(self, group_id: UUID) -> ProtocolResult[WatchGroup]:
        operation = "groups.get"
        if not isinstance(group_id, UUID):
            return failure(operation, "MONITOR_REQUEST_INVALID", "group ID is invalid")

        def read(connection: sqlite3.Connection) -> WatchGroup | None:
            row = connection.execute(
                "SELECT group_id, name, description, interval_ms, revision, created_at_utc, updated_at_utc FROM watch_groups WHERE group_id = ?",
                (str(group_id),),
            ).fetchone()
            return None if row is None else self._load_group(connection, row)

        try:
            group = self._database.read(read, empty=None)
        except StorageFailure as error:
            return _public_storage_failure(operation, error)
        if group is None:
            return failure(operation, "MONITOR_GROUP_NOT_FOUND", "watch group was not found")
        return success(operation, group)

    @staticmethod
    def _insert_group(connection: sqlite3.Connection, group: WatchGroup) -> None:
        payload = group.to_dict()
        connection.execute(
            "INSERT INTO watch_groups(group_id,name,name_key,description,interval_ms,revision,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?)",
            (
                str(group.group_id), group.name, _name_key(group.name), group.description,
                group.interval_ms, group.revision, payload["createdAtUtc"], payload["updatedAtUtc"],
            ),
        )
        connection.executemany(
            "INSERT INTO group_items(group_id,ordinal,kind,selector) VALUES (?,?,?,?)",
            ((str(group.group_id), ordinal, item.kind, item.selector) for ordinal, item in enumerate(group.items)),
        )

    @staticmethod
    def _check_limits(connection: sqlite3.Connection, new_groups: Iterable[WatchGroup]) -> None:
        additions = tuple(new_groups)
        group_count = connection.execute("SELECT COUNT(*) FROM watch_groups").fetchone()[0]
        item_count = connection.execute("SELECT COUNT(*) FROM group_items").fetchone()[0]
        if group_count + len(additions) > MAX_GROUPS:
            raise StorageFailure("MONITOR_GROUP_LIMIT_EXCEEDED", "watch group limit was exceeded")
        if any(len(group.items) > MAX_ITEMS_PER_GROUP for group in additions):
            raise StorageFailure("MONITOR_GROUP_LIMIT_EXCEEDED", "watch item limit was exceeded")
        if item_count + sum(len(group.items) for group in additions) > MAX_TOTAL_ITEMS:
            raise StorageFailure("MONITOR_GROUP_LIMIT_EXCEEDED", "workspace watch item limit was exceeded")

    def create_group(
        self,
        name: str,
        description: str,
        interval_ms: int,
        items: Iterable[WatchItem],
        *,
        authorized: object,
    ) -> ProtocolResult[WatchGroup]:
        operation = "groups.create"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        try:
            group = WatchGroup.create(name, description, interval_ms, tuple(items))
        except (TypeError, ValueError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "watch group is invalid")

        def write(connection: sqlite3.Connection) -> WatchGroup:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._check_limits(connection, (group,))
                self._insert_group(connection, group)
                connection.commit()
                return group
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise StorageFailure("MONITOR_GROUP_CONFLICT", "watch group conflicts with existing state") from error
            except BaseException:
                connection.rollback()
                raise

        try:
            return success(operation, self._database.write(write))
        except StorageFailure as error:
            return _public_storage_failure(operation, error)

    def update_group(
        self,
        group_id: UUID,
        *,
        expected_revision: int,
        name: str | None = None,
        description: str | None = None,
        interval_ms: int | None = None,
        items: Iterable[WatchItem] | None = None,
        authorized: object,
    ) -> ProtocolResult[WatchGroup]:
        operation = "groups.update"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        if not isinstance(group_id, UUID) or not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
            return failure(operation, "MONITOR_REQUEST_INVALID", "group revision request is invalid")

        def write(connection: sqlite3.Connection) -> WatchGroup:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT group_id, name, description, interval_ms, revision, created_at_utc, updated_at_utc FROM watch_groups WHERE group_id = ?",
                    (str(group_id),),
                ).fetchone()
                if row is None:
                    raise StorageFailure("MONITOR_GROUP_NOT_FOUND", "watch group was not found")
                current = self._load_group(connection, row)
                if current.revision != expected_revision:
                    raise StorageFailure("MONITOR_GROUP_CONFLICT", "watch group revision changed")
                replacement_items = current.items if items is None else tuple(items)
                updated = WatchGroup(
                    group_id=current.group_id,
                    name=current.name if name is None else name,
                    description=current.description if description is None else description,
                    interval_ms=current.interval_ms if interval_ms is None else interval_ms,
                    items=replacement_items,
                    revision=current.revision + 1,
                    created_at_utc=current.created_at_utc,
                    updated_at_utc=datetime.now(timezone.utc),
                )
                if len(updated.items) > MAX_ITEMS_PER_GROUP:
                    raise StorageFailure("MONITOR_GROUP_LIMIT_EXCEEDED", "watch item limit was exceeded")
                total_without = connection.execute("SELECT COUNT(*) FROM group_items WHERE group_id <> ?", (str(group_id),)).fetchone()[0]
                if total_without + len(updated.items) > MAX_TOTAL_ITEMS:
                    raise StorageFailure("MONITOR_GROUP_LIMIT_EXCEEDED", "workspace watch item limit was exceeded")
                payload = updated.to_dict()
                cursor = connection.execute(
                    "UPDATE watch_groups SET name=?,name_key=?,description=?,interval_ms=?,revision=?,updated_at_utc=? WHERE group_id=? AND revision=?",
                    (updated.name, _name_key(updated.name), updated.description, updated.interval_ms, updated.revision, payload["updatedAtUtc"], str(group_id), expected_revision),
                )
                if cursor.rowcount != 1:
                    raise StorageFailure("MONITOR_GROUP_CONFLICT", "watch group revision changed")
                connection.execute("DELETE FROM group_items WHERE group_id = ?", (str(group_id),))
                connection.executemany(
                    "INSERT INTO group_items(group_id,ordinal,kind,selector) VALUES (?,?,?,?)",
                    ((str(group_id), ordinal, item.kind, item.selector) for ordinal, item in enumerate(updated.items)),
                )
                connection.commit()
                return updated
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise StorageFailure("MONITOR_GROUP_CONFLICT", "watch group conflicts with existing state") from error
            except BaseException:
                connection.rollback()
                raise

        try:
            return success(operation, self._database.write(write))
        except (TypeError, ValueError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "watch group is invalid")
        except StorageFailure as error:
            return _public_storage_failure(operation, error)

    def delete_group(self, group_id: UUID, *, expected_revision: int, authorized: object) -> ProtocolResult[dict[str, object]]:
        operation = "groups.delete"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        if not isinstance(group_id, UUID) or not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
            return failure(operation, "MONITOR_REQUEST_INVALID", "group revision request is invalid")

        def write(connection: sqlite3.Connection) -> dict[str, object]:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM watch_groups WHERE group_id = ? AND revision = ?",
                (str(group_id), expected_revision),
            )
            if cursor.rowcount != 1:
                exists = connection.execute("SELECT 1 FROM watch_groups WHERE group_id = ?", (str(group_id),)).fetchone()
                connection.rollback()
                if exists is None:
                    raise StorageFailure("MONITOR_GROUP_NOT_FOUND", "watch group was not found")
                raise StorageFailure("MONITOR_GROUP_CONFLICT", "watch group revision changed")
            connection.commit()
            return {"groupId": str(group_id), "deleted": True}

        try:
            return success(operation, self._database.write(write))
        except StorageFailure as error:
            return _public_storage_failure(operation, error)

    def import_groups(self, document: bytes, *, authorized: object) -> ProtocolResult[tuple[WatchGroup, ...]]:
        operation = "groups.import"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        try:
            payload = parse_json_object(document, limit=MAX_IMPORT_BYTES, invalid_code="MONITOR_IMPORT_INVALID")
            if set(payload) != {"schemaVersion", "groups"} or payload["schemaVersion"] != 1 or not isinstance(payload["groups"], list):
                raise ValueError("invalid import grammar")
            imported: list[WatchGroup] = []
            names: set[str] = set()
            for raw in payload["groups"]:
                if not isinstance(raw, dict) or set(raw) != {"name", "description", "intervalMs", "items"} or not isinstance(raw["items"], list):
                    raise ValueError("invalid group grammar")
                group = WatchGroup.create(
                    cast(str, raw["name"]), cast(str, raw["description"]), cast(int, raw["intervalMs"]),
                    tuple(WatchItem.from_dict(item) for item in raw["items"] if isinstance(item, dict)),
                )
                if len(group.items) != len(raw["items"]) or _name_key(group.name) in names:
                    raise ValueError("invalid or duplicate group")
                names.add(_name_key(group.name))
                imported.append(group)
        except (ProtocolViolation, TypeError, ValueError):
            return failure(operation, "MONITOR_IMPORT_INVALID", "group import document is invalid")

        def write(connection: sqlite3.Connection) -> tuple[WatchGroup, ...]:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._check_limits(connection, imported)
                existing = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT name_key FROM watch_groups WHERE name_key IN ({','.join('?' for _ in names)})",
                        tuple(names),
                    ).fetchall()
                } if names else set()
                if existing:
                    raise StorageFailure("MONITOR_IMPORT_CONFLICT", "group import conflicts with existing state")
                for group in imported:
                    self._insert_group(connection, group)
                connection.commit()
                return tuple(imported)
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise StorageFailure("MONITOR_IMPORT_CONFLICT", "group import conflicts with existing state") from error
            except BaseException:
                connection.rollback()
                raise

        try:
            return success(operation, self._database.write(write))
        except StorageFailure as error:
            if error.code == "MONITOR_GROUP_LIMIT_EXCEEDED":
                return _public_storage_failure(operation, error)
            if error.code.startswith("MONITOR_STORAGE") or error.code == "MONITOR_WORKSPACE_MISMATCH":
                return _public_storage_failure(operation, error)
            return failure(operation, "MONITOR_IMPORT_CONFLICT", error.public_message)

    def close(self) -> None:
        self._database.close()
