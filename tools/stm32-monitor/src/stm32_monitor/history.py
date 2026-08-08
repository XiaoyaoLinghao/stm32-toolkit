from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, cast
from uuid import UUID

from stm32_toolkit.paths import WorkspacePaths

from .models import ObservationBinding, SampleBatch, SampleValue, WatchItem, unix_ns_to_utc
from .protocol import ProtocolResult, failure, success
from .storage import MonitorDatabase, StorageFailure


MAX_HISTORY_VALUES = 10_000
MAX_HISTORY_PAGE_BYTES = 4 * 1024 * 1024
RETENTION_AGE_NS = 7 * 24 * 60 * 60 * 1_000_000_000
RETENTION_LOGICAL_BYTES = 256 * 1024 * 1024
RETENTION_DELETE_BATCHES = 100
RETENTION_TIME_BUDGET_NS = 90 * 1_000_000
RETENTION_STORAGE_TIMEOUT_MS = 95

_HISTORY_ROW_FIELDS = {
    "binding",
    "groupId",
    "groupRevision",
    "runId",
    "sequence",
    "scheduledUnixNs",
    "scheduledAtUtc",
    "capturedUnixNs",
    "capturedAtUtc",
    "latencyNs",
    "actualRateHz",
    "subscriberDrops",
    "historyDrops",
    "deadlineDrops",
    "watch",
    "status",
    "typedValue",
    "code",
    "definition",
    "valueOrdinal",
}


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


def _invalid_json_constant(_: str) -> object:
    raise ValueError("non-finite JSON number")


def _history_corrupt() -> StorageFailure:
    return StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor history is corrupt")


def _decode_history_row(
    raw: object,
    payload_bytes: object,
    *,
    session_id: object,
    run_id: object,
    sequence: object,
    captured_ns: object,
    ordinal: object,
) -> tuple[Mapping[str, object], int]:
    try:
        if type(raw) is not bytes or type(payload_bytes) is not int:
            raise TypeError("history payload types are invalid")
        if not raw or payload_bytes != len(raw) or len(raw) > MAX_HISTORY_PAGE_BYTES:
            raise ValueError("history payload size is invalid")
        decoded = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
        if type(decoded) is not dict or set(decoded) != _HISTORY_ROW_FIELDS:
            raise ValueError("history row shape is invalid")

        binding_value = decoded["binding"]
        watch_value = decoded["watch"]
        if type(binding_value) is not dict or type(watch_value) is not dict:
            raise TypeError("history model payload is invalid")
        status = decoded["status"]
        code = decoded["code"]
        definition = decoded["definition"]
        value_ordinal = decoded["valueOrdinal"]
        if type(status) is not str or (code is not None and type(code) is not str):
            raise TypeError("history sample status is invalid")
        if definition is not None and type(definition) is not dict:
            raise TypeError("history definition is invalid")
        if type(value_ordinal) is not int or value_ordinal < 0:
            raise ValueError("history ordinal is invalid")
        if (
            decoded["binding"].get("sessionId") != session_id
            or decoded["runId"] != run_id
            or decoded["sequence"] != sequence
            or decoded["capturedUnixNs"] != captured_ns
            or value_ordinal != ordinal
        ):
            raise ValueError("history row does not match its SQLite identity")

        binding = ObservationBinding.from_dict(binding_value)
        sample = SampleValue(
            WatchItem.from_dict(watch_value),
            status,
            typed_value=decoded["typedValue"],
            code=code,
            definition=definition,
        )
        batch = SampleBatch(
            binding=binding,
            group_id=UUID(cast(str, decoded["groupId"])),
            group_revision=cast(int, decoded["groupRevision"]),
            run_id=UUID(cast(str, decoded["runId"])),
            sequence=cast(int, decoded["sequence"]),
            scheduled_unix_ns=cast(int, decoded["scheduledUnixNs"]),
            captured_unix_ns=cast(int, decoded["capturedUnixNs"]),
            latency_ns=cast(int, decoded["latencyNs"]),
            actual_rate_hz=cast(float, decoded["actualRateHz"]),
            subscriber_drops=cast(int, decoded["subscriberDrops"]),
            history_drops=cast(int, decoded["historyDrops"]),
            deadline_drops=cast(int, decoded["deadlineDrops"]),
            values=(sample,),
        )
        if decoded["scheduledAtUtc"] != unix_ns_to_utc(batch.scheduled_unix_ns):
            raise ValueError("scheduled timestamp is inconsistent")
        if decoded["capturedAtUtc"] != unix_ns_to_utc(batch.captured_unix_ns):
            raise ValueError("captured timestamp is inconsistent")

        normalized = batch.to_dict()
        normalized_value = cast(list[dict[str, object]], normalized.pop("values"))[0]
        normalized.update(normalized_value)
        normalized["valueOrdinal"] = value_ordinal
        if decoded != normalized:
            raise ValueError("history row does not match its model")
        return MappingProxyType(decoded), len(raw)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError, OSError, RecursionError) as error:
        raise _history_corrupt() from error


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
                SELECT b.batch_id, v.ordinal, v.row_json, v.payload_bytes,
                       b.session_id, b.run_id, b.sequence, b.captured_ns
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
            for batch_id, ordinal, raw, payload_bytes, session_id, run_id, sequence, captured_ns in records:
                if len(values) >= effective_limit:
                    next_cursor = f"{records[len(values) - 1][0]}:{records[len(values) - 1][1]}"
                    break
                decoded, encoded_size = _decode_history_row(
                    raw,
                    payload_bytes,
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    captured_ns=captured_ns,
                    ordinal=ordinal,
                )
                if size + encoded_size > MAX_HISTORY_PAGE_BYTES:
                    if not values:
                        raise _history_corrupt()
                    next_cursor = f"{records[len(values) - 1][0]}:{records[len(values) - 1][1]}"
                    break
                values.append(decoded)
                size += encoded_size
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
            return success(operation, {
                "deletedBatches": 0,
                "logicalBytes": 0,
                "passes": 0,
                "moreWork": False,
                "earliestCapturedUnixNs": None,
            })

        def write(connection: sqlite3.Connection) -> dict[str, object]:
            started_ns = time.monotonic_ns()
            maximum = min(max(1, RETENTION_DELETE_BATCHES), 100)
            connection.execute("BEGIN IMMEDIATE")
            try:
                logical_before = connection.execute(
                    "SELECT logical_bytes FROM monitor_history_accounting WHERE singleton = 1"
                ).fetchone()
                if logical_before is None:
                    raise _history_corrupt()
                logical_before = logical_before[0]
                if type(logical_before) is not int or logical_before < 0:
                    raise _history_corrupt()
                expired = connection.execute(
                    "SELECT batch_id FROM history_batches WHERE captured_ns < ? ORDER BY captured_ns, batch_id LIMIT ?",
                    (cutoff, maximum + 1),
                ).fetchall()
                candidates = expired
                if not candidates and logical_before > RETENTION_LOGICAL_BYTES:
                    candidates = connection.execute(
                        "SELECT batch_id FROM history_batches ORDER BY captured_ns, batch_id LIMIT ?",
                        (maximum + 1,),
                    ).fetchall()
                selected = [row[0] for row in candidates[:maximum]]
                if any(type(batch_id) is not int or batch_id < 1 for batch_id in selected):
                    raise _history_corrupt()
                if selected:
                    connection.executemany(
                        "DELETE FROM history_batches WHERE batch_id = ?",
                        ((batch_id,) for batch_id in selected),
                    )

                logical_after = connection.execute(
                    "SELECT logical_bytes FROM monitor_history_accounting WHERE singleton = 1"
                ).fetchone()
                if logical_after is None:
                    raise _history_corrupt()
                logical_after = logical_after[0]
                if type(logical_after) is not int or logical_after < 0:
                    raise _history_corrupt()
                earliest_row = connection.execute(
                    "SELECT MIN(captured_ns) FROM history_batches"
                ).fetchone()
                earliest = None if earliest_row is None else earliest_row[0]
                if earliest is not None and (type(earliest) is not int or earliest < 0):
                    raise _history_corrupt()
                more_expired = connection.execute(
                    "SELECT 1 FROM history_batches WHERE captured_ns < ? LIMIT 1",
                    (cutoff,),
                ).fetchone() is not None
                has_rows = earliest is not None
                more_work = more_expired or (logical_after > RETENTION_LOGICAL_BYTES and has_rows)
                if time.monotonic_ns() - started_ns >= RETENTION_TIME_BUDGET_NS and has_rows:
                    more_work = True
                connection.commit()
                return {
                    "deletedBatches": len(selected),
                    "logicalBytes": logical_after,
                    "passes": 1 if selected else 0,
                    "moreWork": more_work,
                    "earliestCapturedUnixNs": earliest,
                }
            except BaseException:
                connection.rollback()
                raise

        try:
            evidence = self._database.try_write(
                write, timeout_ms=RETENTION_STORAGE_TIMEOUT_MS
            )
            return success(operation, evidence)
        except StorageFailure as error:
            if error.code.startswith("MONITOR_STORAGE") or error.code == "MONITOR_WORKSPACE_MISMATCH":
                return _storage_failure(operation, error)
            return failure(operation, "MONITOR_RETENTION_FAILED", "history retention failed")

    def close(self) -> None:
        self._database.close()
