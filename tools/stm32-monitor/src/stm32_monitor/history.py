from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Iterator, Mapping as MappingABC, Sequence
from dataclasses import dataclass
from hashlib import sha256
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
# A persisted batch must fit within one maximum history response.  Migration
# checks SQLite's BLOB length against this ceiling before fetching the payload.
MAX_HISTORY_BATCH_BYTES = MAX_HISTORY_PAGE_BYTES
RETENTION_AGE_NS = 7 * 24 * 60 * 60 * 1_000_000_000
RETENTION_LOGICAL_BYTES = 256 * 1024 * 1024
RETENTION_DELETE_BATCHES = 100
RETENTION_TIME_BUDGET_NS = 90 * 1_000_000
RETENTION_STORAGE_TIMEOUT_MS = 95

_HISTORY_CURSOR = re.compile(
    r"(?:[1-9][0-9]{0,18}):(?:0|[1-9][0-9]{0,18})\Z", re.ASCII
)


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
        supplied_batches = tuple(self.batches)
        if any(type(batch) is not HistoryBatchSlice for batch in supplied_batches):
            raise ValueError("history page batches are invalid")
        batches = tuple(batch.immutable_snapshot() for batch in supplied_batches)
        if type(self.value_count) is not int or self.value_count < 0:
            raise ValueError("history page value count is invalid")
        actual_count = sum(len(batch.values) for batch in batches)
        if self.value_count != actual_count:
            raise ValueError("history page value count does not match its batches")
        if actual_count > MAX_HISTORY_VALUES:
            raise ValueError("history page exceeds the 10,000 value limit")
        if self.next_cursor is not None:
            _, cursor_ordinal = _cursor(self.next_cursor)
            if not batches or cursor_ordinal != (
                batches[-1].start_ordinal + len(batches[-1].values) - 1
            ):
                raise ValueError("history cursor does not identify the last returned value")

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

    def immutable_snapshot(self) -> "HistoryPage":
        if (
            type(self) is not HistoryPage
            or type(self.batches) is not tuple
            or any(type(batch) is not HistoryBatchSlice for batch in self.batches)
        ):
            raise TypeError("history page snapshot type is invalid")
        return HistoryPage(
            self.batches,
            self.value_count,
            self.next_cursor,
            self.serialized_bytes,
        )

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


def _history_slice(
    batch: SampleBatch,
    start_ordinal: int,
    values: Sequence[SampleValue],
) -> HistoryBatchSlice:
    return HistoryBatchSlice(
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
        start_ordinal=start_ordinal,
        batch_value_count=len(batch.values),
        values=tuple(values),
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
    return _encoded_history_page_size_from_batch_bytes(
        batch_bytes, value_count, next_cursor
    )


def _encoded_history_page_size_from_batch_bytes(
    batch_bytes: int,
    value_count: int,
    next_cursor: str | None,
) -> int:
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


def _cursor(value: str | None) -> tuple[int, int]:
    if value is None:
        return 0, -1
    if type(value) is not str or _HISTORY_CURSOR.fullmatch(value) is None:
        raise ValueError("history cursor is invalid")
    parts = value.split(":")
    batch_id, ordinal = int(parts[0]), int(parts[1])
    if (
        batch_id > MAX_SIGNED_INT64
        or ordinal > MAX_SIGNED_INT64
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


def _decode_history_batch(
    raw: object,
    payload_bytes: object,
    payload_sha256: object,
    value_count: object,
    *,
    workspace_id: str,
    session_id: object,
    run_id: object,
    sequence: object,
    captured_ns: object,
) -> SampleBatch:
    try:
        if (
            type(raw) is not bytes
            or type(payload_bytes) is not int
            or type(payload_sha256) is not str
            or type(value_count) is not int
        ):
            raise TypeError("history batch payload types are invalid")
        if (
            not raw
            or len(raw) > MAX_HISTORY_BATCH_BYTES
            or payload_bytes != len(raw)
            or sha256(raw).hexdigest() != payload_sha256
            or value_count < 0
        ):
            raise ValueError("history batch payload evidence is invalid")
        decoded = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
        if type(decoded) is not dict or set(decoded) != {
            "binding", "groupId", "groupRevision", "runId", "sequence",
            "scheduledUnixNs", "scheduledAtUtc", "capturedUnixNs", "capturedAtUtc",
            "latencyNs", "actualRateHz", "subscriberDrops", "historyDrops",
            "deadlineDrops", "values",
        }:
            raise ValueError("history batch shape is invalid")
        binding_value = decoded["binding"]
        values_value = decoded["values"]
        if type(binding_value) is not dict or type(values_value) is not list:
            raise TypeError("history batch model payload is invalid")
        values: list[SampleValue] = []
        for value in values_value:
            if type(value) is not dict or set(value) != {
                "watch", "status", "typedValue", "code", "definition"
            }:
                raise ValueError("history value shape is invalid")
            watch = value["watch"]
            if type(watch) is not dict:
                raise TypeError("history watch payload is invalid")
            values.append(
                SampleValue(
                    WatchItem.from_dict(watch),
                    cast(str, value["status"]),
                    typed_value=value["typedValue"],
                    code=cast(str | None, value["code"]),
                    definition=cast(Mapping[str, object] | None, value["definition"]),
                )
            )
        binding = ObservationBinding.from_dict(binding_value)
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
            values=tuple(values),
        )
        if (
            len(batch.values) != value_count
            or binding.workspace_id != workspace_id
            or binding.session_id != session_id
            or str(batch.run_id) != run_id
            or batch.sequence != sequence
            or batch.captured_unix_ns != captured_ns
            or decoded["scheduledAtUtc"] != unix_ns_to_utc(batch.scheduled_unix_ns)
            or decoded["capturedAtUtc"] != unix_ns_to_utc(batch.captured_unix_ns)
            or decoded != batch.to_dict()
        ):
            raise ValueError("history batch does not match its evidence")
        return batch
    except (
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        OSError,
        RecursionError,
    ) as error:
        raise _history_corrupt() from error


def _encode_history_value(value: SampleValue) -> tuple[str, str, bytes, str]:
    raw = json.dumps(
        value.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return value.watch.kind, value.watch.selector, raw, sha256(raw).hexdigest()


def _normalize_v1_batch(
    *,
    workspace_id: str,
    batch_row: Sequence[object],
    value_rows: Sequence[Sequence[object]],
) -> tuple[bytes, str, tuple[tuple[int, str, str, bytes, str], ...]]:
    try:
        batch_id, session_id, run_id, sequence, captured_ns, raw, payload_bytes = batch_row
        if type(batch_id) is not int or batch_id < 1 or type(raw) is not bytes:
            raise ValueError("history batch identity is invalid")
        batch = _decode_history_batch(
            raw,
            payload_bytes,
            sha256(raw).hexdigest(),
            len(value_rows),
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            sequence=sequence,
            captured_ns=captured_ns,
        )
        if len(value_rows) != len(batch.values):
            raise ValueError("history value count is invalid")
        evidence = {key: value for key, value in batch.to_dict().items() if key != "values"}
        normalized: list[tuple[int, str, str, bytes, str]] = []
        for expected_ordinal, (ordinal, row_raw, row_bytes) in enumerate(value_rows):
            if (
                ordinal != expected_ordinal
                or type(row_raw) is not bytes
                or type(row_bytes) is not int
                or not row_raw
                or row_bytes != len(row_raw)
                or len(row_raw) > MAX_HISTORY_PAGE_BYTES
            ):
                raise ValueError("history row evidence is invalid")
            decoded = json.loads(
                row_raw.decode("utf-8"),
                parse_constant=_invalid_json_constant,
            )
            if type(decoded) is not dict:
                raise ValueError("history row shape is invalid")
            expected = dict(evidence)
            expected.update(batch.values[expected_ordinal].to_dict())
            expected["valueOrdinal"] = expected_ordinal
            if decoded != expected:
                raise ValueError("history row does not match canonical batch evidence")
            kind, selector, value_raw, value_digest = _encode_history_value(
                batch.values[expected_ordinal]
            )
            normalized.append((expected_ordinal, kind, selector, value_raw, value_digest))
        canonical = json.dumps(
            batch.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return canonical, sha256(canonical).hexdigest(), tuple(normalized)
    except (
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
    ) as error:
        raise _history_corrupt() from error


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
            batch_digest = sha256(encoded_batch).hexdigest()
            rows = tuple(_encode_history_value(value) for value in batch.values)
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "sample batch is invalid")

        def write(connection: sqlite3.Connection) -> dict[str, object]:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,"
                    "payload_bytes,payload_sha256,value_count) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        batch.binding.session_id,
                        str(batch.run_id),
                        batch.sequence,
                        batch.captured_unix_ns,
                        encoded_batch,
                        len(encoded_batch),
                        batch_digest,
                        len(rows),
                    ),
                )
                batch_id = cursor.lastrowid
                connection.executemany(
                    "INSERT INTO history_values(batch_id,ordinal,selector_kind,selector,value_json,"
                    "value_bytes,value_sha256) VALUES (?,?,?,?,?,?,?)",
                    (
                        (batch_id, ordinal, kind, selector, raw, len(raw), digest)
                        for ordinal, (kind, selector, raw, digest) in enumerate(rows)
                    ),
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
                SELECT b.batch_id,b.session_id,b.run_id,b.sequence,b.captured_ns,
                       b.payload_json,b.payload_bytes,b.payload_sha256,b.value_count
                FROM history_batches AS b
                WHERE b.session_id = ? AND b.captured_ns >= ? AND b.captured_ns < ?
                  AND b.batch_id >= ?
                ORDER BY b.batch_id
                """,
                (query.session_id, query.start_ns, query.end_ns, max(1, cursor_batch)),
            )
            selected: list[tuple[SampleBatch, int, list[SampleValue], int]] = []
            selected_batch_bytes = 0
            selected_count = 0
            last_cursor: str | None = None
            more = False
            while True:
                record = records.fetchone()
                if record is None:
                    break
                (
                    batch_id, session_id, run_id, sequence, captured_ns, raw,
                    payload_bytes, payload_digest, batch_value_count,
                ) = record
                if type(batch_id) is not int or batch_id < 1:
                    raise _history_corrupt()
                batch = _decode_history_batch(
                    raw,
                    payload_bytes,
                    payload_digest,
                    batch_value_count,
                    workspace_id=self._paths.workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    captured_ns=captured_ns,
                )
                indexed = connection.execute(
                    "SELECT ordinal,selector_kind,selector,value_json,value_bytes,value_sha256 "
                    "FROM history_values WHERE batch_id = ? ORDER BY ordinal",
                    (batch_id,),
                ).fetchall()
                if len(indexed) != len(batch.values):
                    raise _history_corrupt()
                encoded_value_lengths: list[int] = []
                for ordinal, index_row in enumerate(indexed):
                    stored_ordinal, kind, selector, value_raw, value_bytes, value_digest = index_row
                    expected_kind, expected_selector, expected_raw, expected_digest = _encode_history_value(
                        batch.values[ordinal]
                    )
                    if (
                        stored_ordinal != ordinal
                        or kind != expected_kind
                        or selector != expected_selector
                        or type(value_raw) is not bytes
                        or type(value_bytes) is not int
                        or value_bytes != len(value_raw)
                        or type(value_digest) is not str
                        or sha256(value_raw).hexdigest() != value_digest
                        or value_digest != expected_digest
                        or value_raw != expected_raw
                    ):
                        raise _history_corrupt()
                    encoded_value_lengths.append(len(expected_raw))

                has_later_batch = connection.execute(
                    "SELECT 1 FROM history_batches WHERE session_id = ? "
                    "AND captured_ns >= ? AND captured_ns < ? AND batch_id > ? LIMIT 1",
                    (query.session_id, query.start_ns, query.end_ns, batch_id),
                ).fetchone() is not None

                start = cursor_ordinal + 1 if batch_id == cursor_batch else 0
                if start < 0 or start > len(batch.values):
                    raise _history_corrupt()
                for ordinal in range(start, len(batch.values)):
                    if selected_count >= effective_limit:
                        more = True
                        break
                    value = batch.values[ordinal]
                    if selected and selected[-1][0] is batch:
                        previous_batch, previous_start, previous_values, previous_bytes = selected[-1]
                        candidate_batch_bytes = (
                            selected_batch_bytes
                            + 1
                            + encoded_value_lengths[ordinal]
                        )
                    else:
                        candidate_slice = _history_slice(batch, ordinal, (value,))
                        slice_bytes = len(
                            json.dumps(
                                candidate_slice.to_dict(),
                                ensure_ascii=False,
                                separators=(",", ":"),
                                allow_nan=False,
                            ).encode("utf-8")
                        )
                        candidate_batch_bytes = (
                            selected_batch_bytes
                            + (1 if selected else 0)
                            + slice_bytes
                        )
                    candidate_more = (
                        ordinal + 1 < len(batch.values) or has_later_batch
                    )
                    candidate_cursor = f"{batch_id}:{ordinal}" if candidate_more else None
                    if _encoded_history_page_size_from_batch_bytes(
                        candidate_batch_bytes,
                        selected_count + 1,
                        candidate_cursor,
                    ) > MAX_HISTORY_PAGE_BYTES:
                        more = True
                        break
                    if selected and selected[-1][0] is batch:
                        previous_values.append(value)
                        selected[-1] = (
                            previous_batch,
                            previous_start,
                            previous_values,
                            previous_bytes + 1 + encoded_value_lengths[ordinal],
                        )
                    else:
                        selected.append((batch, ordinal, [value], slice_bytes))
                    selected_batch_bytes = candidate_batch_bytes
                    selected_count += 1
                    last_cursor = f"{batch_id}:{ordinal}"
                if more:
                    break
            if not selected:
                if more:
                    raise _history_corrupt()
                return HistoryPage.create((), next_cursor=None)
            next_cursor = last_cursor if more else None
            final_batches = tuple(
                _history_slice(batch, start_ordinal, values)
                for batch, start_ordinal, values, _ in selected
            )
            return HistoryPage(
                final_batches,
                selected_count,
                next_cursor,
                _encoded_history_page_size_from_batch_bytes(
                    selected_batch_bytes,
                    selected_count,
                    next_cursor,
                ),
            )

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
