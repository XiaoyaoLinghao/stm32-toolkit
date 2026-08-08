from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, cast

from stm32_toolkit.paths import WorkspacePaths

from .models import SampleBatch
from .protocol import ProtocolResult, failure, success
from .storage import MonitorDatabase, StorageFailure


MAX_HISTORY_VALUES = 10_000
MAX_HISTORY_PAGE_BYTES = 4 * 1024 * 1024
RETENTION_AGE_NS = 7 * 24 * 60 * 60 * 1_000_000_000
RETENTION_LOGICAL_BYTES = 256 * 1024 * 1024
RETENTION_DELETE_BATCHES = 100


@dataclass(frozen=True)
class HistoryQuery:
    session_id: str
    start_ns: int
    end_ns: int
    limit: int = MAX_HISTORY_VALUES
    cursor: str | None = None


@dataclass(frozen=True)
class HistoryPage:
    values: tuple[Mapping[str, object], ...]
    next_cursor: str | None
    serialized_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "values": [dict(value) for value in self.values],
            "nextCursor": self.next_cursor,
            "serializedBytes": self.serialized_bytes,
        }


def _cursor(value: str | None) -> tuple[int, int]:
    if value is None:
        return 0, -1
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("history cursor is invalid")
    return int(parts[0]), int(parts[1])


def _storage_failure(operation: str, error: StorageFailure) -> ProtocolResult[None]:
    return failure(operation, error.code, error.public_message)


class HistoryStore:
    def __init__(self, paths: WorkspacePaths) -> None:
        self._paths = paths
        self._database = MonitorDatabase(paths)

    def append_batch(self, batch: SampleBatch) -> ProtocolResult[dict[str, object]]:
        operation = "history.append"
        if not isinstance(batch, SampleBatch) or batch.binding.workspace_id != self._paths.workspace_id:
            return failure(operation, "MONITOR_WORKSPACE_MISMATCH", "sample batch belongs to another workspace")
        batch_payload = batch.to_dict()
        encoded_batch = json.dumps(batch_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        rows: list[bytes] = []
        for ordinal, value in enumerate(batch_payload["values"]):
            row = {
                key: item
                for key, item in batch_payload.items()
                if key != "values"
            }
            row.update(cast(dict[str, object], value))
            row["valueOrdinal"] = ordinal
            rows.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

        def write(connection: sqlite3.Connection) -> dict[str, object]:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,payload_bytes) VALUES (?,?,?,?,?,?)",
                    (batch.binding.session_id, str(batch.run_id), batch.sequence, batch.captured_unix_ns, encoded_batch, len(encoded_batch)),
                )
                batch_id = cursor.lastrowid
                connection.executemany(
                    "INSERT INTO history_values(batch_id,ordinal,row_json,payload_bytes) VALUES (?,?,?,?)",
                    ((batch_id, ordinal, row, len(row)) for ordinal, row in enumerate(rows)),
                )
                connection.commit()
                return {"batchId": batch_id, "valueCount": len(rows)}
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise StorageFailure("MONITOR_STORAGE_INVALID", "sample batch already exists") from error
            except BaseException:
                connection.rollback()
                raise

        try:
            return success(operation, self._database.write(write))
        except StorageFailure as error:
            return _storage_failure(operation, error)

    @staticmethod
    def _validate_query(query: HistoryQuery) -> tuple[int, int]:
        if not isinstance(query, HistoryQuery):
            raise ValueError("history query is invalid")
        if (
            not isinstance(query.session_id, str)
            or not query.session_id
            or not isinstance(query.start_ns, int)
            or isinstance(query.start_ns, bool)
            or not isinstance(query.end_ns, int)
            or isinstance(query.end_ns, bool)
            or query.start_ns < 0
            or query.end_ns <= query.start_ns
            or not isinstance(query.limit, int)
            or isinstance(query.limit, bool)
            or query.limit < 1
        ):
            raise ValueError("history query is invalid")
        return _cursor(query.cursor)

    def query_history(self, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        operation = "history.query"
        try:
            cursor_batch, cursor_ordinal = self._validate_query(query)
        except ValueError:
            return failure(operation, "MONITOR_HISTORY_QUERY_INVALID", "history query is invalid")
        effective_limit = min(query.limit, MAX_HISTORY_VALUES)

        def read(connection: sqlite3.Connection) -> HistoryPage:
            records = connection.execute(
                """
                SELECT b.batch_id, v.ordinal, v.row_json
                FROM history_batches AS b
                JOIN history_values AS v ON v.batch_id = b.batch_id
                WHERE b.session_id = ? AND b.captured_ns >= ? AND b.captured_ns < ?
                  AND (b.batch_id > ? OR (b.batch_id = ? AND v.ordinal > ?))
                ORDER BY b.batch_id, v.ordinal
                LIMIT ?
                """,
                (query.session_id, query.start_ns, query.end_ns, cursor_batch, cursor_batch, cursor_ordinal, effective_limit + 1),
            ).fetchall()
            values: list[Mapping[str, object]] = []
            size = 0
            next_cursor: str | None = None
            for batch_id, ordinal, raw in records:
                encoded = bytes(raw)
                if len(values) >= effective_limit or size + len(encoded) > MAX_HISTORY_PAGE_BYTES:
                    if not values:
                        raise StorageFailure("MONITOR_HISTORY_LIMIT_EXCEEDED", "one history value exceeds the page limit")
                    next_cursor = f"{records[len(values) - 1][0]}:{records[len(values) - 1][1]}"
                    break
                decoded = json.loads(encoded.decode("utf-8"))
                values.append(MappingProxyType(decoded))
                size += len(encoded)
            return HistoryPage(tuple(values), next_cursor, size)

        try:
            page = self._database.read(read, empty=HistoryPage((), None, 0))
            return success(operation, page)
        except StorageFailure as error:
            return _storage_failure(operation, error)

    def run_retention(self, *, now_ns: int) -> ProtocolResult[dict[str, object]]:
        operation = "history.retention"
        if not isinstance(now_ns, int) or isinstance(now_ns, bool) or now_ns < 0:
            return failure(operation, "MONITOR_REQUEST_INVALID", "retention time is invalid")
        cutoff = max(0, now_ns - RETENTION_AGE_NS)
        try:
            storage_exists = self._database.read(lambda connection: True, empty=False)
        except StorageFailure as error:
            return _storage_failure(operation, error)
        if not storage_exists:
            return success(operation, {"deletedBatches": 0, "logicalBytes": 0, "passes": 0})

        def write(connection: sqlite3.Connection) -> dict[str, object]:
            deleted = 0
            passes = 0
            while True:
                connection.execute("BEGIN IMMEDIATE")
                old_ids = [
                    row[0]
                    for row in connection.execute(
                        "SELECT batch_id FROM history_batches WHERE captured_ns < ? ORDER BY batch_id LIMIT ?",
                        (cutoff, RETENTION_DELETE_BATCHES),
                    ).fetchall()
                ]
                if old_ids:
                    connection.executemany("DELETE FROM history_batches WHERE batch_id = ?", ((value,) for value in old_ids))
                    connection.commit()
                    deleted += len(old_ids)
                    passes += 1
                    continue
                logical = connection.execute(
                    "SELECT COALESCE((SELECT SUM(payload_bytes) FROM history_batches),0) + COALESCE((SELECT SUM(payload_bytes) FROM history_values),0)"
                ).fetchone()[0]
                if logical <= RETENTION_LOGICAL_BYTES:
                    connection.rollback()
                    return {"deletedBatches": deleted, "logicalBytes": logical, "passes": passes}
                budget_ids = [
                    row[0]
                    for row in connection.execute(
                        "SELECT batch_id FROM history_batches ORDER BY batch_id LIMIT ?",
                        (RETENTION_DELETE_BATCHES,),
                    ).fetchall()
                ]
                if not budget_ids:
                    connection.rollback()
                    return {"deletedBatches": deleted, "logicalBytes": logical, "passes": passes}
                connection.executemany("DELETE FROM history_batches WHERE batch_id = ?", ((value,) for value in budget_ids))
                connection.commit()
                deleted += len(budget_ids)
                passes += 1

        try:
            return success(operation, self._database.write(write))
        except StorageFailure as error:
            if error.code.startswith("MONITOR_STORAGE") or error.code == "MONITOR_WORKSPACE_MISMATCH":
                return _storage_failure(operation, error)
            return failure(operation, "MONITOR_RETENTION_FAILED", "history retention failed")

    def close(self) -> None:
        self._database.close()
