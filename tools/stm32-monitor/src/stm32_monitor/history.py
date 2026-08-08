from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator, Mapping as MappingABC, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, cast
from uuid import UUID

from stm32_toolkit.paths import WorkspacePaths

from .models import (
    MAX_SIGNED_INT64,
    HistoryBatchSlice,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchItem,
    unix_ns_to_utc,
)
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
    batches: tuple[HistoryBatchSlice, ...]
    value_count: int
    next_cursor: str | None
    serialized_bytes: int

    def __post_init__(self) -> None:
        batches = tuple(self.batches)
        if any(type(batch) is not HistoryBatchSlice for batch in batches):
            raise ValueError("history page batches are invalid")
        if type(self.value_count) is not int or self.value_count < 0:
            raise ValueError("history page value count is invalid")
        actual_count = sum(len(batch.values) for batch in batches)
        if self.value_count != actual_count:
            raise ValueError("history page value count does not match its batches")
        if actual_count > MAX_HISTORY_VALUES:
            raise ValueError("history page exceeds the 10,000 value limit")
        if self.next_cursor is not None:
            _cursor(self.next_cursor, require_canonical=True)

        previous_key: tuple[object, ...] | None = None
        previous_evidence: tuple[object, ...] | None = None
        next_ordinal = -1
        closed_keys: set[tuple[object, ...]] = set()
        for batch in batches:
            key = (
                batch.binding.workspace_id,
                batch.binding.session_id,
                batch.run_id,
                batch.sequence,
            )
            evidence = _batch_evidence(batch)
            if key == previous_key:
                if evidence != previous_evidence or batch.start_ordinal != next_ordinal:
                    raise ValueError("history batch slices are not contiguous")
            elif key in closed_keys:
                raise ValueError("history batch slices are not contiguous")
            else:
                if previous_key is not None:
                    closed_keys.add(previous_key)
            previous_key = key
            previous_evidence = evidence
            next_ordinal = batch.start_ordinal + len(batch.values)

        if type(self.serialized_bytes) is not int or self.serialized_bytes < 0:
            raise ValueError("history page serialized byte count is invalid")
        expected_bytes = _encoded_history_page_size(
            batches, actual_count, self.next_cursor
        )
        if self.serialized_bytes != expected_bytes:
            raise ValueError("history page serialized byte count is inconsistent")
        if batches and expected_bytes > MAX_HISTORY_PAGE_BYTES:
            raise ValueError("history page exceeds the 4 MiB serialized limit")
        object.__setattr__(self, "batches", batches)

    @classmethod
    def create(
        cls,
        batches: Sequence[HistoryBatchSlice],
        *,
        next_cursor: str | None,
    ) -> "HistoryPage":
        snapshot = tuple(batches)
        if any(type(batch) is not HistoryBatchSlice for batch in snapshot):
            raise ValueError("history page batches are invalid")
        value_count = sum(len(batch.values) for batch in snapshot)
        if value_count > MAX_HISTORY_VALUES:
            raise ValueError("history page exceeds the 10,000 value limit")
        serialized_bytes = _encoded_history_page_size(
            snapshot, value_count, next_cursor
        )
        return cls(snapshot, value_count, next_cursor, serialized_bytes)

    @property
    def values(self) -> tuple[Mapping[str, object], ...]:
        """Temporary internal compatibility view; public JSON is batch-normalized."""
        return tuple(flatten_history_page(self))

    def to_dict(self) -> dict[str, object]:
        return {
            "batches": [batch.to_dict() for batch in self.batches],
            "valueCount": self.value_count,
            "nextCursor": self.next_cursor,
            "serializedBytes": self.serialized_bytes,
        }


def _batch_evidence(batch: HistoryBatchSlice) -> tuple[object, ...]:
    return (
        batch.binding,
        batch.group_id,
        batch.group_revision,
        batch.run_id,
        batch.sequence,
        batch.scheduled_unix_ns,
        batch.captured_unix_ns,
        batch.latency_ns,
        batch.actual_rate_hz,
        batch.subscriber_drops,
        batch.history_drops,
        batch.deadline_drops,
        batch.batch_value_count,
    )


def _encoded_history_page_size(
    batches: Sequence[HistoryBatchSlice],
    value_count: int,
    next_cursor: str | None,
) -> int:
    batch_bytes = sum(
        len(
            json.dumps(
                batch.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        for batch in batches
    )
    if batches:
        batch_bytes += len(batches) - 1
    fixed_bytes = (
        len(b'{"batches":[')
        + batch_bytes
        + len(b'],"valueCount":')
        + len(str(value_count).encode("ascii"))
        + len(b',"nextCursor":')
        + len(
            json.dumps(
                next_cursor,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        + len(b',"serializedBytes":')
        + len(b"}")
    )
    candidate = fixed_bytes + 1
    while True:
        size = fixed_bytes + len(str(candidate).encode("ascii"))
        if size == candidate:
            return size
        candidate = size


def _cursor(
    value: str | None, *, require_canonical: bool = False
) -> tuple[int, int]:
    if value is None:
        return 0, -1
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("history cursor is invalid")
    batch_id, ordinal = int(parts[0]), int(parts[1])
    if (
        batch_id < 1
        or batch_id > MAX_SIGNED_INT64
        or ordinal > MAX_SIGNED_INT64
        or (require_canonical and value != f"{batch_id}:{ordinal}")
    ):
        raise ValueError("history cursor is invalid")
    return batch_id, ordinal


def flatten_history_page(page: HistoryPage) -> Iterator[Mapping[str, object]]:
    if type(page) is not HistoryPage:
        raise TypeError("history page is invalid")
    for batch in page.batches:
        payload = batch.to_dict()
        values = cast(list[dict[str, object]], payload.pop("values"))
        start_ordinal = cast(int, payload.pop("startOrdinal"))
        payload.pop("batchValueCount")
        for offset, value in enumerate(values):
            row = dict(payload)
            row.update(value)
            row["valueOrdinal"] = start_ordinal + offset
            yield MappingProxyType(row)


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


def _slice_from_history_row(
    decoded: Mapping[str, object],
    *,
    ordinal: int,
    batch_value_count: int,
) -> HistoryBatchSlice:
    try:
        binding_value = decoded["binding"]
        watch_value = decoded["watch"]
        if type(binding_value) is not dict or type(watch_value) is not dict:
            raise TypeError("history model payload is invalid")
        status = decoded["status"]
        code = decoded["code"]
        definition = decoded["definition"]
        if type(status) is not str or (code is not None and type(code) is not str):
            raise TypeError("history sample status is invalid")
        if definition is not None and type(definition) is not dict:
            raise TypeError("history definition is invalid")
        sample = SampleValue(
            WatchItem.from_dict(watch_value),
            status,
            typed_value=decoded["typedValue"],
            code=code,
            definition=definition,
        )
        return HistoryBatchSlice(
            binding=ObservationBinding.from_dict(binding_value),
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
            start_ordinal=ordinal,
            batch_value_count=batch_value_count,
            values=(sample,),
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as error:
        raise _history_corrupt() from error


def _combine_history_slices(
    rows: Sequence[tuple[int, HistoryBatchSlice]],
) -> tuple[HistoryBatchSlice, ...]:
    combined: list[HistoryBatchSlice] = []
    current_batch_id = -1
    current: HistoryBatchSlice | None = None
    values: list[SampleValue] = []

    def finish() -> None:
        if current is None:
            return
        combined.append(
            HistoryBatchSlice(
                binding=current.binding,
                group_id=current.group_id,
                group_revision=current.group_revision,
                run_id=current.run_id,
                sequence=current.sequence,
                scheduled_unix_ns=current.scheduled_unix_ns,
                captured_unix_ns=current.captured_unix_ns,
                latency_ns=current.latency_ns,
                actual_rate_hz=current.actual_rate_hz,
                subscriber_drops=current.subscriber_drops,
                history_drops=current.history_drops,
                deadline_drops=current.deadline_drops,
                start_ordinal=current.start_ordinal,
                batch_value_count=current.batch_value_count,
                values=tuple(values),
            )
        )

    for batch_id, item in rows:
        if batch_id != current_batch_id:
            finish()
            current_batch_id = batch_id
            current = item
            values = list(item.values)
            continue
        if (
            current is None
            or _batch_evidence(current) != _batch_evidence(item)
            or item.start_ordinal != current.start_ordinal + len(values)
        ):
            raise _history_corrupt()
        values.extend(item.values)
    finish()
    return tuple(combined)


def _take_history_values(
    batches: Sequence[HistoryBatchSlice], value_count: int
) -> tuple[HistoryBatchSlice, ...]:
    selected: list[HistoryBatchSlice] = []
    remaining = value_count
    for batch in batches:
        if remaining <= 0:
            break
        take = min(remaining, len(batch.values))
        selected.append(
            HistoryBatchSlice(
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
                start_ordinal=batch.start_ordinal,
                batch_value_count=batch.batch_value_count,
                values=batch.values[:take],
            )
        )
        remaining -= take
    if remaining:
        raise _history_corrupt()
    return tuple(selected)


class HistoryStore:
    def __init__(self, paths: WorkspacePaths) -> None:
        self._paths = paths
        self._database = MonitorDatabase(paths)

    def append_batch(self, batch: SampleBatch) -> ProtocolResult[dict[str, object]]:
        operation = "history.append"
        if type(batch) is not SampleBatch or batch.binding.workspace_id != self._paths.workspace_id:
            return failure(operation, "MONITOR_WORKSPACE_MISMATCH", "sample batch belongs to another workspace")
        try:
            batch_payload = batch.to_dict()
            encoded_batch = json.dumps(
                batch_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            rows: list[bytes] = []
            for ordinal, value in enumerate(batch_payload["values"]):
                row = {
                    key: item
                    for key, item in batch_payload.items()
                    if key != "values"
                }
                row.update(cast(dict[str, object], value))
                row["valueOrdinal"] = ordinal
                rows.append(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                )
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "sample batch is invalid")

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
            or query.end_ns > MAX_SIGNED_INT64
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
                       b.session_id, b.run_id, b.sequence, b.captured_ns,
                       (SELECT COUNT(*) FROM history_values AS counts
                        WHERE counts.batch_id = b.batch_id) AS batch_value_count
                FROM history_batches AS b
                JOIN history_values AS v ON v.batch_id = b.batch_id
                WHERE b.session_id = ? AND b.captured_ns >= ? AND b.captured_ns < ?
                  AND (b.batch_id > ? OR (b.batch_id = ? AND v.ordinal > ?))
                ORDER BY b.batch_id, v.ordinal
                LIMIT ?
                """,
                (query.session_id, query.start_ns, query.end_ns, cursor_batch, cursor_batch, cursor_ordinal, effective_limit + 1),
            ).fetchall()
            if not records:
                return HistoryPage.create((), next_cursor=None)

            decoded_rows: list[tuple[int, HistoryBatchSlice]] = []
            for (
                batch_id,
                ordinal,
                raw,
                payload_bytes,
                session_id,
                run_id,
                sequence,
                captured_ns,
                batch_value_count,
            ) in records[:effective_limit]:
                if (
                    type(batch_id) is not int
                    or batch_id < 1
                    or type(ordinal) is not int
                    or ordinal < 0
                    or type(batch_value_count) is not int
                    or batch_value_count < 1
                ):
                    raise _history_corrupt()
                decoded, _encoded_size = _decode_history_row(
                    raw,
                    payload_bytes,
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    captured_ns=captured_ns,
                    ordinal=ordinal,
                )
                decoded_rows.append(
                    (
                        batch_id,
                        _slice_from_history_row(
                            decoded,
                            ordinal=ordinal,
                            batch_value_count=batch_value_count,
                        ),
                    )
                )

            batches = _combine_history_slices(decoded_rows)

            def make_page(count: int) -> HistoryPage:
                next_cursor = None
                if len(records) > count:
                    next_cursor = f"{records[count - 1][0]}:{records[count - 1][1]}"
                return HistoryPage.create(
                    _take_history_values(batches, count),
                    next_cursor=next_cursor,
                )

            try:
                return make_page(len(decoded_rows))
            except ValueError as error:
                if "4 MiB" not in str(error):
                    raise _history_corrupt() from error

            low = 1
            high = len(decoded_rows) - 1
            accepted: HistoryPage | None = None
            while low <= high:
                middle = (low + high) // 2
                try:
                    candidate = make_page(middle)
                except ValueError as error:
                    if "4 MiB" not in str(error):
                        raise _history_corrupt() from error
                    high = middle - 1
                else:
                    accepted = candidate
                    low = middle + 1
            if accepted is None:
                raise _history_corrupt()
            return accepted

        try:
            page = self._database.read(
                read, empty=HistoryPage.create((), next_cursor=None)
            )
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

            def require_budget() -> None:
                if time.monotonic_ns() - started_ns >= RETENTION_TIME_BUDGET_NS:
                    raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy")

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
                require_budget()
                selected = [row[0] for row in candidates[:maximum]]
                if any(type(batch_id) is not int or batch_id < 1 for batch_id in selected):
                    raise _history_corrupt()
                if selected:
                    connection.executemany(
                        "DELETE FROM history_batches WHERE batch_id = ?",
                        ((batch_id,) for batch_id in selected),
                    )
                require_budget()

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
