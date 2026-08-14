from __future__ import annotations

import base64
import hmac
import json
import re
import secrets
import sqlite3
import struct
import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping as MappingABC, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping, cast
from uuid import UUID

from stm32_toolkit.paths import WorkspacePaths

from .models import (
    _TRUSTED_HISTORY_SIZE,
    _TRUSTED_HISTORY_SLICE,
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
_CURSOR_PAGE_FIXED_BYTES = (
    len(b'{"batches":[')
    + len(b'],"valueCount":')
    + len(b',"nextCursor":')
    + len(b'"v1.')
    + 107
    + len(b'"')
    + len(b',"serializedBytes":')
    + len(b"}")
)
# A persisted batch must fit within one maximum history response.  Migration
# checks SQLite's BLOB length against this ceiling before fetching the payload.
MAX_HISTORY_BATCH_BYTES = MAX_HISTORY_PAGE_BYTES
RETENTION_AGE_NS = 7 * 24 * 60 * 60 * 1_000_000_000
RETENTION_LOGICAL_BYTES = 256 * 1024 * 1024
RETENTION_DELETE_BATCHES = 100
RETENTION_DELETE_VALUES = 512
RETENTION_TIME_BUDGET_NS = 90 * 1_000_000
# Executor admission and scheduling receive a separate bounded allowance so
# they cannot consume the retention operation's own cancellation budget.
RETENTION_STORAGE_TIMEOUT_MS = 2 * (RETENTION_TIME_BUDGET_NS // 1_000_000)

_LEGACY_HISTORY_CURSOR = re.compile(
    r"(?:[1-9][0-9]{0,18}):(?:0|[1-9][0-9]{0,18})\Z", re.ASCII
)
_HISTORY_CURSOR = re.compile(r"v1\.[A-Za-z0-9_-]{107}\Z", re.ASCII)
_TRUSTED_HISTORY_PAGE = object()
_VERIFIED_HISTORY_CACHE_BATCHES = 512


@dataclass(frozen=True)
class _VerifiedHistoryBatch:
    key: tuple[object, ...]
    batch: SampleBatch
    indexed: tuple[tuple[object, ...], ...]
    encoded_value_lengths: tuple[int, ...]
    encoded_slice_base_bytes: int


class _InvalidHistoryCursor(Exception):
    pass


@dataclass(frozen=True)
class HistoryQuery:
    session_id: str
    start_ns: int
    end_ns: int
    limit: int = MAX_HISTORY_VALUES
    cursor: str | None = None
    run_id: UUID | None = None
    group_id: UUID | None = None
    selector_kind: str | None = None
    selector: str | None = None


@dataclass(frozen=True)
class HistoryPage:
    batches: tuple[HistoryBatchSlice, ...]
    value_count: int
    next_cursor: str | None
    serialized_bytes: int
    _verified_marker: object | None = field(
        default=None, init=False, repr=False, compare=False
    )

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
            _, cursor_ordinal = _page_cursor_position(self.next_cursor)
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
        if self._verified_marker is _TRUSTED_HISTORY_PAGE:
            object.__setattr__(self, "_verified_marker", None)
            return self
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


@dataclass(frozen=True)
class _VerifiedHistoryPageCache:
    key: tuple[object, ...]
    snapshot: tuple[tuple[str, int, int, int, int], ...]
    page: HistoryPage
    batch_sizes: tuple[int, ...]


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


def _verified_history_slice(
    batch: SampleBatch,
    start_ordinal: int,
    values: Sequence[SampleValue],
    serialized_bytes: int,
    *,
    isolate_outer: bool = True,
) -> HistoryBatchSlice:
    source_values = tuple(values)
    if (
        type(batch) is not SampleBatch
        or type(batch.binding) is not ObservationBinding
        or type(batch.values) is not tuple
        or type(start_ordinal) is not int
        or start_ordinal < 0
        or start_ordinal + len(source_values) > len(batch.values)
        or not source_values
        or any(
            type(value) is not SampleValue or type(value.watch) is not WatchItem
            for value in source_values
        )
        or any(
            value is not batch.values[start_ordinal + offset]
            for offset, value in enumerate(source_values)
        )
        or type(serialized_bytes) is not int
        or serialized_bytes < 1
    ):
        raise TypeError("verified history slice is invalid")
    snapshot = (
        tuple([_isolated_verified_value(value) for value in source_values])
        if isolate_outer
        else source_values
    )
    result = object.__new__(HistoryBatchSlice)
    object.__setattr__(result, "binding", _isolated_verified_binding(batch.binding) if isolate_outer else batch.binding)
    object.__setattr__(result, "group_id", UUID(int=batch.group_id.int) if isolate_outer else batch.group_id)
    object.__setattr__(result, "group_revision", batch.group_revision)
    object.__setattr__(result, "run_id", UUID(int=batch.run_id.int) if isolate_outer else batch.run_id)
    object.__setattr__(result, "sequence", batch.sequence)
    object.__setattr__(result, "scheduled_unix_ns", batch.scheduled_unix_ns)
    object.__setattr__(result, "captured_unix_ns", batch.captured_unix_ns)
    object.__setattr__(result, "latency_ns", batch.latency_ns)
    object.__setattr__(result, "actual_rate_hz", float(batch.actual_rate_hz))
    object.__setattr__(result, "subscriber_drops", batch.subscriber_drops)
    object.__setattr__(result, "history_drops", batch.history_drops)
    object.__setattr__(result, "deadline_drops", batch.deadline_drops)
    object.__setattr__(result, "start_ordinal", start_ordinal)
    object.__setattr__(result, "batch_value_count", len(batch.values))
    object.__setattr__(result, "values", tuple(snapshot))
    object.__setattr__(
        result,
        "_verified_serialized_bytes",
        (_TRUSTED_HISTORY_SIZE, serialized_bytes),
    )
    object.__setattr__(result, "_verified_marker", _TRUSTED_HISTORY_SLICE)
    return result


def _isolated_verified_binding(binding: ObservationBinding) -> ObservationBinding:
    """Copy the outer binding node while sharing only immutable leaves.

    The accepted binding fields (identifiers, target/build/ELF strings, booleans)
    are all immutable, so a shallow instance copy gives callers an independent
    node without re-serializing/rebuilding the model. This is a hot per-batch
    isolation path (39 slices per 10k-value page).
    """
    result = object.__new__(ObservationBinding)
    object.__setattr__(result, "__dict__", binding.__dict__.copy())
    return result


def _isolated_verified_value(value: SampleValue) -> SampleValue:
    """Copy mutable outer model nodes while sharing only frozen JSON leaves."""
    # Callers validate the complete source sequence once before entering this
    # hot copy loop.  object.__new__ avoids repeating dataclass allocation
    # dispatch while the independent dictionaries preserve forged-setattr
    # isolation from the canonical verified cache.
    watch = object.__new__(WatchItem)
    object.__setattr__(watch, "__dict__", value.watch.__dict__.copy())
    result = object.__new__(SampleValue)
    fields = {
        "watch": watch,
        "status": value.status,
        "typed_value": value.typed_value,
        "code": value.code,
        "definition": value.definition,
    }
    object.__setattr__(result, "__dict__", fields)
    return result


def _isolated_verified_page(
    page: HistoryPage,
    batch_sizes: Sequence[int],
) -> HistoryPage:
    if (
        type(page) is not HistoryPage
        or type(page.batches) is not tuple
        or len(page.batches) != len(batch_sizes)
        or any(type(batch) is not HistoryBatchSlice for batch in page.batches)
        or any(type(size) is not int or size < 1 for size in batch_sizes)
    ):
        raise TypeError("verified history page cache is invalid")
    batches: list[HistoryBatchSlice] = []
    for batch, serialized_bytes in zip(page.batches, batch_sizes, strict=True):
        if (
            type(batch.binding) is not ObservationBinding
            or type(batch.group_id) is not UUID
            or type(batch.run_id) is not UUID
            or type(batch.values) is not tuple
            or any(
                type(value) is not SampleValue or type(value.watch) is not WatchItem
                for value in batch.values
            )
        ):
            raise TypeError("verified history page cache is invalid")
        clone = object.__new__(HistoryBatchSlice)
        object.__setattr__(clone, "binding", _isolated_verified_binding(batch.binding))
        object.__setattr__(clone, "group_id", UUID(int=batch.group_id.int))
        object.__setattr__(clone, "group_revision", batch.group_revision)
        object.__setattr__(clone, "run_id", UUID(int=batch.run_id.int))
        object.__setattr__(clone, "sequence", batch.sequence)
        object.__setattr__(clone, "scheduled_unix_ns", batch.scheduled_unix_ns)
        object.__setattr__(clone, "captured_unix_ns", batch.captured_unix_ns)
        object.__setattr__(clone, "latency_ns", batch.latency_ns)
        object.__setattr__(clone, "actual_rate_hz", float(batch.actual_rate_hz))
        object.__setattr__(clone, "subscriber_drops", batch.subscriber_drops)
        object.__setattr__(clone, "history_drops", batch.history_drops)
        object.__setattr__(clone, "deadline_drops", batch.deadline_drops)
        object.__setattr__(clone, "start_ordinal", batch.start_ordinal)
        object.__setattr__(clone, "batch_value_count", batch.batch_value_count)
        object.__setattr__(
            clone,
            "values",
            tuple(_isolated_verified_value(value) for value in batch.values),
        )
        object.__setattr__(
            clone,
            "_verified_serialized_bytes",
            (_TRUSTED_HISTORY_SIZE, serialized_bytes),
        )
        object.__setattr__(clone, "_verified_marker", _TRUSTED_HISTORY_SLICE)
        batches.append(clone)
    result = object.__new__(HistoryPage)
    object.__setattr__(result, "batches", tuple(batches))
    object.__setattr__(result, "value_count", page.value_count)
    object.__setattr__(result, "next_cursor", page.next_cursor)
    object.__setattr__(result, "serialized_bytes", page.serialized_bytes)
    object.__setattr__(result, "_verified_marker", _TRUSTED_HISTORY_PAGE)
    return result


def _isolated_verified_batch(batch: SampleBatch) -> SampleBatch:
    if (
        type(batch) is not SampleBatch
        or type(batch.binding) is not ObservationBinding
        or type(batch.values) is not tuple
        or any(
            type(value) is not SampleValue or type(value.watch) is not WatchItem
            for value in batch.values
        )
    ):
        raise TypeError("verified history batch is invalid")
    return SampleBatch(
        binding=_isolated_verified_binding(batch.binding),
        group_id=UUID(int=batch.group_id.int),
        group_revision=batch.group_revision,
        run_id=UUID(int=batch.run_id.int),
        sequence=batch.sequence,
        scheduled_unix_ns=batch.scheduled_unix_ns,
        captured_unix_ns=batch.captured_unix_ns,
        latency_ns=batch.latency_ns,
        actual_rate_hz=batch.actual_rate_hz,
        subscriber_drops=batch.subscriber_drops,
        history_drops=batch.history_drops,
        deadline_drops=batch.deadline_drops,
        values=tuple([_isolated_verified_value(value) for value in batch.values]),
    )


def _encoded_slice_base_bytes(
    batch: SampleBatch,
    encoded_value_lengths: Sequence[int],
) -> int:
    """Return exact one-value slice bytes excluding its encoded value."""
    if not encoded_value_lengths or len(encoded_value_lengths) != len(batch.values):
        raise TypeError("verified history value lengths are invalid")
    candidate = _history_slice(batch, 0, (batch.values[0],))
    encoded = len(
        json.dumps(
            candidate.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    base = encoded - encoded_value_lengths[0]
    if base < 1:
        raise TypeError("verified history slice size is invalid")
    return base


def _verified_history_page(
    batches: Sequence[HistoryBatchSlice],
    *,
    value_count: int,
    next_cursor: str | None,
    serialized_bytes: int,
) -> HistoryPage:
    snapshot = tuple(batches)
    if (
        any(type(batch) is not HistoryBatchSlice for batch in snapshot)
        or value_count != sum(len(batch.values) for batch in snapshot)
        or value_count > MAX_HISTORY_VALUES
        or (snapshot and serialized_bytes > MAX_HISTORY_PAGE_BYTES)
    ):
        raise TypeError("verified history page is invalid")
    result = HistoryPage(snapshot, value_count, next_cursor, serialized_bytes)
    object.__setattr__(result, "_verified_marker", _TRUSTED_HISTORY_PAGE)
    return result


def _encoded_history_page_size(
    batches: Sequence[HistoryBatchSlice],
    value_count: int,
    next_cursor: str | None,
) -> int:
    verified_sizes: list[int] = []
    for batch in batches:
        verified_size = batch._verified_serialized_bytes
        if (
            type(verified_size) is not tuple
            or len(verified_size) != 2
            or verified_size[0] is not _TRUSTED_HISTORY_SIZE
            or type(verified_size[1]) is not int
            or verified_size[1] < 1
        ):
            verified_sizes = []
            break
        verified_sizes.append(verified_size[1])
    if verified_sizes:
        for batch in batches:
            object.__setattr__(batch, "_verified_serialized_bytes", None)
        batch_bytes = sum(verified_sizes)
    else:
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
        + len(str(value_count))
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
        size = fixed_bytes + len(str(candidate))
        if size == candidate:
            return size
        candidate = size


_EMPTY_HISTORY_PAGE_BYTES = _encoded_history_page_size_from_batch_bytes(
    0, 0, None
)


def _filter_digest(query: HistoryQuery) -> bytes:
    canonical = json.dumps(
        [
            query.start_ns,
            query.end_ns,
            str(query.run_id) if query.run_id is not None else None,
            str(query.group_id) if query.group_id is not None else None,
            query.selector_kind,
            query.selector,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(canonical).digest()


def _encode_cursor(
    batch_id: int,
    ordinal: int,
    filter_digest: bytes,
    authentication_key: bytes,
) -> str:
    bound = struct.pack(">QQ32s", batch_id, ordinal, filter_digest)
    payload = bound + hmac.digest(authentication_key, bound, "sha256")
    return "v1." + base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _cursor_payload(value: str) -> tuple[int, int, bytes, bytes]:
    if _HISTORY_CURSOR.fullmatch(value) is None:
        raise ValueError("history cursor is invalid")
    try:
        encoded = value.removeprefix("v1.")
        payload = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii") != encoded:
            raise ValueError("history cursor is invalid")
        batch_id, ordinal, filter_digest, authentication_tag = struct.unpack(
            ">QQ32s32s", payload
        )
    except (ValueError, struct.error):
        raise ValueError("history cursor is invalid") from None
    if (
        batch_id < 1
        or batch_id > MAX_SIGNED_INT64
        or ordinal > MAX_SIGNED_INT64
    ):
        raise ValueError("history cursor is invalid")
    return batch_id, ordinal, filter_digest, authentication_tag


def _decode_cursor(
    value: str,
    authentication_key: bytes,
) -> tuple[int, int, bytes]:
    batch_id, ordinal, filter_digest, actual_tag = _cursor_payload(value)
    bound = struct.pack(">QQ32s", batch_id, ordinal, filter_digest)
    expected_tag = hmac.digest(authentication_key, bound, "sha256")
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise ValueError("history cursor is invalid")
    return batch_id, ordinal, filter_digest


def _cursor(
    value: str | None,
    expected_filter_digest: bytes,
    authentication_key: bytes,
) -> tuple[int, int]:
    if value is None:
        return 0, -1
    if type(value) is not str:
        raise ValueError("history cursor is invalid")
    batch_id, ordinal, actual_filter_digest = _decode_cursor(
        value, authentication_key
    )
    if actual_filter_digest != expected_filter_digest:
        raise ValueError("history cursor is invalid")
    return batch_id, ordinal


def _page_cursor_position(value: str) -> tuple[int, int]:
    if _LEGACY_HISTORY_CURSOR.fullmatch(value) is not None:
        batch, ordinal = value.split(":")
        return int(batch), int(ordinal)
    batch_id, ordinal, _, _ = _cursor_payload(value)
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


def _canonical_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if (
            (not key.isascii() and unicodedata.normalize("NFC", key) != key)
            or key in result
        ):
            raise ValueError("history JSON object key is not canonical")
        result[key] = value
    return result


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
    value_evidence: list[tuple[str, str, bytes, str]] | None = None,
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
        decoded = json.loads(
            raw.decode("utf-8"),
            parse_constant=_invalid_json_constant,
            object_pairs_hook=_canonical_json_object,
        )
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
        decoded_value_evidence: list[tuple[str, str, bytes, str]] = []
        for value in values_value:
            if type(value) is not dict or set(value) != {
                "watch", "status", "typedValue", "code", "definition"
            }:
                raise ValueError("history value shape is invalid")
            watch = value["watch"]
            if type(watch) is not dict:
                raise TypeError("history watch payload is invalid")
            sample = SampleValue(
                WatchItem.from_dict(watch),
                cast(str, value["status"]),
                typed_value=value["typedValue"],
                code=cast(str | None, value["code"]),
                definition=cast(Mapping[str, object] | None, value["definition"]),
            )
            selector_field = (
                "expression" if sample.watch.kind == "variable" else "registerPath"
            )
            if (
                watch.get(selector_field) != sample.watch.selector
                or value["status"] != sample.status
                or value["code"] != sample.code
            ):
                raise ValueError("history value is not canonical")
            values.append(sample)
            if value_evidence is not None:
                value_raw = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                decoded_value_evidence.append(
                    (
                        sample.watch.kind,
                        sample.watch.selector,
                        value_raw,
                        sha256(value_raw).hexdigest(),
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
        expected_static = {
            "binding": binding.to_dict(),
            "groupId": str(batch.group_id),
            "groupRevision": batch.group_revision,
            "runId": str(batch.run_id),
            "sequence": batch.sequence,
            "scheduledUnixNs": batch.scheduled_unix_ns,
            "scheduledAtUtc": unix_ns_to_utc(batch.scheduled_unix_ns),
            "capturedUnixNs": batch.captured_unix_ns,
            "capturedAtUtc": unix_ns_to_utc(batch.captured_unix_ns),
            "latencyNs": batch.latency_ns,
            "actualRateHz": float(batch.actual_rate_hz),
            "subscriberDrops": batch.subscriber_drops,
            "historyDrops": batch.history_drops,
            "deadlineDrops": batch.deadline_drops,
        }
        actual_static = {
            key: item for key, item in decoded.items() if key != "values"
        }
        if (
            len(batch.values) != value_count
            or binding.workspace_id != workspace_id
            or binding.session_id != session_id
            or str(batch.run_id) != run_id
            or batch.sequence != sequence
            or batch.captured_unix_ns != captured_ns
            or actual_static != expected_static
        ):
            raise ValueError("history batch does not match its evidence")
        if value_evidence is not None:
            value_evidence.extend(decoded_value_evidence)
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
        self._cursor_key = secrets.token_bytes(32)
        self._verified_cache_lock = threading.Lock()
        self._verified_cache_snapshot: tuple[tuple[str, int, int, int, int], ...] | None = None
        self._verified_cache: OrderedDict[tuple[object, ...], _VerifiedHistoryBatch] = OrderedDict()
        self._verified_page_cache: _VerifiedHistoryPageCache | None = None

    def _observed_storage_snapshot(
        self,
    ) -> tuple[
        tuple[tuple[str, int, int, int, int], ...],
        bool,
    ] | None:
        fingerprint = self._database._integrity_fingerprint(  # noqa: SLF001
            self._database._inspect_storage_files()  # noqa: SLF001
        )
        if not self._database._fingerprint_is_certain(fingerprint):  # noqa: SLF001
            return None
        with self._database._integrity_lock:  # noqa: SLF001
            trusted = self._database._integrity_identity == fingerprint  # noqa: SLF001
        return fingerprint, trusted

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
            if len(encoded_batch) > MAX_HISTORY_BATCH_BYTES:
                raise ValueError("sample batch exceeds the history batch byte limit")
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

    def _validate_query(self, query: HistoryQuery) -> tuple[int, int, bytes]:
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
            or (query.run_id is not None and type(query.run_id) is not UUID)
            or (query.group_id is not None and type(query.group_id) is not UUID)
            or ((query.selector_kind is None) != (query.selector is None))
            or (
                query.selector_kind is not None
                and (
                    query.selector_kind not in {"variable", "register"}
                    or type(query.selector) is not str
                )
            )
        ):
            raise ValueError("history query is invalid")
        if query.selector_kind is not None:
            WatchItem(query.selector_kind, cast(str, query.selector))
        filter_digest = _filter_digest(query)
        cursor_batch, cursor_ordinal = _cursor(
            query.cursor, filter_digest, self._cursor_key
        )
        return cursor_batch, cursor_ordinal, filter_digest

    def query_history(self, query: HistoryQuery) -> ProtocolResult[HistoryPage]:
        return self._query_history(query, cache_verified=True)

    def _query_history_uncached(
        self,
        query: HistoryQuery,
        *,
        transient_cache: dict[str, object] | None = None,
    ) -> ProtocolResult[HistoryPage]:
        return self._query_history(
            query,
            cache_verified=False,
            transient_cache=transient_cache,
        )

    def _query_history(
        self,
        query: HistoryQuery,
        *,
        cache_verified: bool,
        transient_cache: dict[str, object] | None = None,
    ) -> ProtocolResult[HistoryPage]:
        operation = "history.query"
        try:
            cursor_batch, cursor_ordinal, filter_digest = self._validate_query(query)
        except ValueError:
            return failure(operation, "MONITOR_HISTORY_QUERY_INVALID", "history query is invalid")
        effective_limit = min(query.limit, MAX_HISTORY_VALUES)
        page_cache_key = (
            query.session_id,
            query.start_ns,
            query.end_ns,
            effective_limit,
            query.cursor,
            query.run_id,
            query.group_id,
            query.selector_kind,
            query.selector,
        )
        observed_snapshot: tuple[tuple[str, int, int, int, int], ...] | None = None
        pending_cache: list[_VerifiedHistoryBatch] = []
        page_batch_sizes: tuple[int, ...] = ()

        if cache_verified:
            try:
                before = self._observed_storage_snapshot()
                with self._verified_cache_lock:
                    cached_page = self._verified_page_cache
                if (
                    before is not None
                    and before[1]
                    and cached_page is not None
                    and cached_page.key == page_cache_key
                    and cached_page.snapshot == before[0]
                ):
                    page = _isolated_verified_page(
                        cached_page.page,
                        cached_page.batch_sizes,
                    )
                    after = self._observed_storage_snapshot()
                    if after == before:
                        return success(operation, page)
            except StorageFailure as error:
                return _storage_failure(operation, error)

        def read(connection: sqlite3.Connection) -> HistoryPage:
            nonlocal observed_snapshot, page_batch_sizes
            snapshot = self._observed_storage_snapshot()
            if snapshot is None:
                trusted_cache: dict[tuple[object, ...], _VerifiedHistoryBatch] = {}
            elif not cache_verified and transient_cache is not None:
                observed_snapshot, trusted = snapshot
                cached_snapshot = transient_cache.get("snapshot")
                cached_batches = transient_cache.get("batches")
                trusted_cache = (
                    dict(cast(dict[tuple[object, ...], _VerifiedHistoryBatch], cached_batches))
                    if (
                        trusted
                        and cached_snapshot == observed_snapshot
                        and type(cached_batches) is dict
                    )
                    else {}
                )
            elif not cache_verified:
                trusted_cache = {}
            else:
                observed_snapshot, trusted = snapshot
                with self._verified_cache_lock:
                    trusted_cache = (
                        dict(self._verified_cache)
                        if trusted and self._verified_cache_snapshot == observed_snapshot
                        else {}
                    )
            clauses = [
                "b.session_id = ?",
                "b.captured_ns >= ?",
                "b.captured_ns < ?",
                "b.batch_id >= ?",
            ]
            parameters: list[object] = [
                query.session_id,
                query.start_ns,
                query.end_ns,
                max(1, cursor_batch),
            ]
            if query.run_id is not None:
                clauses.append("b.run_id = ?")
                parameters.append(str(query.run_id))
            if query.selector_kind is not None:
                clauses.append(
                    "EXISTS (SELECT 1 FROM history_values AS f "
                    "WHERE f.batch_id = b.batch_id "
                    "AND f.selector_kind = ? AND f.selector = ?)"
                )
                parameters.extend((query.selector_kind, query.selector))
            payload_projection = ",b.payload_json" if not cache_verified else ""
            records = connection.execute(
                f"""
                SELECT b.batch_id,b.session_id,b.run_id,b.sequence,b.captured_ns,
                       {payload_projection.removeprefix(',') + ',' if payload_projection else ''}
                       b.payload_bytes,b.payload_sha256,b.value_count
                FROM history_batches AS b
                WHERE {' AND '.join(clauses)}
                ORDER BY b.batch_id
                """,
                parameters,
            )
            payload_records: sqlite3.Cursor | None = None
            indexed_records: sqlite3.Cursor | None = None
            selected: list[tuple[SampleBatch, int, list[SampleValue], int]] = []
            selected_batch_bytes = 0
            selected_count = 0
            cached_batch_ids: set[int] = set()
            last_batch_id: int | None = None
            last_ordinal: int | None = None
            more = False
            cursor_validated = query.cursor is None
            while True:
                record = records.fetchone()
                if record is None:
                    break
                if cache_verified:
                    (
                        batch_id, session_id, run_id, sequence, captured_ns,
                        payload_bytes, payload_digest, batch_value_count,
                    ) = record
                    raw: object | None = None
                else:
                    (
                        batch_id, session_id, run_id, sequence, captured_ns, raw,
                        payload_bytes, payload_digest, batch_value_count,
                    ) = record
                if type(batch_id) is not int or batch_id < 1:
                    raise _history_corrupt()
                cache_key = (
                    self._paths.workspace_id,
                    session_id,
                    run_id,
                    batch_id,
                    payload_digest,
                    batch_value_count,
                    sequence,
                    captured_ns,
                    payload_bytes,
                )
                cached = trusted_cache.get(cache_key) if indexed_records is None else None
                if cached is not None:
                    batch = cached.batch
                    cached_batch_ids.add(id(batch))
                    indexed = list(cached.indexed)
                    encoded_value_lengths = list(cached.encoded_value_lengths)
                    encoded_slice_base_bytes = cached.encoded_slice_base_bytes
                else:
                    if indexed_records is None:
                        value_parameters = list(parameters)
                        value_parameters[3] = batch_id
                        if cache_verified:
                            payload_records = connection.execute(
                                f"""
                                SELECT b.batch_id,b.payload_json
                                FROM history_batches AS b
                                WHERE {' AND '.join(clauses)}
                                ORDER BY b.batch_id
                                """,
                                value_parameters,
                            )
                        indexed_records = connection.execute(
                            f"""
                            SELECT v.batch_id,v.ordinal,v.selector_kind,v.selector,
                                   v.value_json,v.value_bytes,v.value_sha256
                            FROM history_values AS v
                            JOIN history_batches AS b ON b.batch_id = v.batch_id
                            WHERE {' AND '.join(clauses)}
                            ORDER BY v.batch_id,v.ordinal
                            """,
                            value_parameters,
                        )
                    if cache_verified:
                        if payload_records is None:
                            raise _history_corrupt()
                        payload_row = payload_records.fetchone()
                        if (
                            payload_row is None
                            or len(payload_row) != 2
                            or payload_row[0] != batch_id
                            or type(payload_row[1]) is not bytes
                        ):
                            raise _history_corrupt()
                        raw = payload_row[1]
                    if type(raw) is not bytes:
                        raise _history_corrupt()
                    decoded_value_evidence: list[tuple[str, str, bytes, str]] = []
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
                        value_evidence=decoded_value_evidence,
                    )
                    indexed = []
                    encoded_value_lengths = []
                    index_rows = indexed_records.fetchmany(len(batch.values))
                    if len(index_rows) != len(batch.values):
                        raise _history_corrupt()
                    for ordinal, index_row in enumerate(index_rows):
                        if len(index_row) != 7:
                            raise _history_corrupt()
                        (
                            indexed_batch_id, stored_ordinal, kind, selector,
                            value_raw, value_bytes, value_digest,
                        ) = index_row
                        (
                            expected_kind,
                            expected_selector,
                            expected_raw,
                            expected_digest,
                        ) = decoded_value_evidence[ordinal]
                        if (
                            indexed_batch_id != batch_id
                            or stored_ordinal != ordinal
                            or kind != expected_kind
                            or selector != expected_selector
                            or type(value_raw) is not bytes
                            or type(value_bytes) is not int
                            or value_bytes != len(value_raw)
                            or type(value_digest) is not str
                            or value_raw != expected_raw
                            or value_digest != expected_digest
                        ):
                            raise _history_corrupt()
                        indexed.append(tuple(index_row[1:]))
                        encoded_value_lengths.append(len(expected_raw))
                    encoded_slice_base_bytes = _encoded_slice_base_bytes(
                        batch,
                        encoded_value_lengths,
                    )
                    if (
                        (cache_verified or transient_cache is not None)
                        and observed_snapshot is not None
                    ):
                        pending_cache.append(
                            _VerifiedHistoryBatch(
                                cache_key,
                                batch,
                                tuple(indexed),
                                tuple(encoded_value_lengths),
                                encoded_slice_base_bytes,
                            )
                        )

                if not cursor_validated and batch_id != cursor_batch:
                    raise _InvalidHistoryCursor

                if query.group_id is not None and batch.group_id != query.group_id:
                    if batch_id == cursor_batch and query.cursor is not None:
                        raise _InvalidHistoryCursor
                    continue

                start = cursor_ordinal + 1 if batch_id == cursor_batch else 0
                if start < 0 or start > len(batch.values):
                    raise _history_corrupt()
                if not cursor_validated:
                    if not 0 <= cursor_ordinal < len(indexed):
                        raise _InvalidHistoryCursor
                    cursor_index = indexed[cursor_ordinal]
                    if query.selector_kind is not None and (
                        cursor_index[1] != query.selector_kind
                        or cursor_index[2] != query.selector
                    ):
                        raise _InvalidHistoryCursor
                    cursor_validated = True
                ordinals = (
                    range(start, len(batch.values))
                    if query.selector_kind is None
                    else (
                        ordinal
                        for ordinal in range(start, len(batch.values))
                        if indexed[ordinal][1] == query.selector_kind
                        and indexed[ordinal][2] == query.selector
                    )
                )
                if (
                    query.selector_kind is None
                    and start < len(batch.values)
                    and selected_count < effective_limit
                ):
                    take = min(
                        len(batch.values) - start,
                        effective_limit - selected_count,
                    )
                    slice_bytes = (
                        encoded_slice_base_bytes
                        - 1
                        + len(str(start))
                        + encoded_value_lengths[start]
                    )
                    whole_slice_bytes = slice_bytes + sum(
                        1 + encoded_value_lengths[ordinal]
                        for ordinal in range(start + 1, start + take)
                    )
                    whole_batch_bytes = (
                        selected_batch_bytes
                        + (1 if selected else 0)
                        + whole_slice_bytes
                    )
                    whole_count = selected_count + take
                    whole_fixed_bytes = (
                        whole_batch_bytes
                        + _CURSOR_PAGE_FIXED_BYTES
                        + len(str(whole_count))
                    )
                    whole_size = whole_fixed_bytes + len(
                        str(whole_fixed_bytes + 8)
                    )
                    if whole_size <= MAX_HISTORY_PAGE_BYTES:
                        selected.append(
                            (
                                batch,
                                start,
                                list(batch.values[start : start + take]),
                                whole_slice_bytes,
                            )
                        )
                        selected_batch_bytes = whole_batch_bytes
                        selected_count = whole_count
                        last_batch_id = batch_id
                        last_ordinal = start + take - 1
                        if start + take < len(batch.values):
                            more = True
                            break
                        continue
                for ordinal in ordinals:
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
                    # Cursor tokens have one fixed encoded length.  Reserve that
                    # exact JSON budget while selecting, then authenticate only
                    # the final returned position once.
                    candidate_count = selected_count + 1
                    fixed_bytes = (
                        candidate_batch_bytes
                        + _CURSOR_PAGE_FIXED_BYTES
                        + len(str(candidate_count))
                    )
                    candidate_size = fixed_bytes + len(str(fixed_bytes + 8))
                    if candidate_size > MAX_HISTORY_PAGE_BYTES:
                        terminal_without_cursor = False
                        if (
                            query.selector_kind is None
                            and query.group_id is None
                            and ordinal + 1 == len(batch.values)
                            and records.fetchone() is None
                        ):
                            no_cursor_fixed = (
                                len(b'{"batches":[')
                                + candidate_batch_bytes
                                + len(b'],"valueCount":')
                                + len(str(candidate_count))
                                + len(b',"nextCursor":null')
                                + len(b',"serializedBytes":')
                                + len(b"}")
                            )
                            no_cursor_size = no_cursor_fixed + 1
                            while True:
                                exact_size = no_cursor_fixed + len(str(no_cursor_size))
                                if exact_size == no_cursor_size:
                                    break
                                no_cursor_size = exact_size
                            terminal_without_cursor = (
                                no_cursor_size <= MAX_HISTORY_PAGE_BYTES
                            )
                        if not terminal_without_cursor:
                            more = True
                            break
                    if (
                        selected
                        and selected[-1][0] is batch
                        and ordinal == selected[-1][1] + len(selected[-1][2])
                    ):
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
                    last_batch_id = batch_id
                    last_ordinal = ordinal
                if more:
                    break
            else:
                raise AssertionError("unreachable")
            if record is None and indexed_records is not None:
                if indexed_records.fetchone() is not None:
                    raise _history_corrupt()
                if cache_verified and (
                    payload_records is None or payload_records.fetchone() is not None
                ):
                    raise _history_corrupt()
            if not selected:
                if not cursor_validated:
                    raise _InvalidHistoryCursor
                if more:
                    raise _history_corrupt()
                return HistoryPage.create((), next_cursor=None)
            next_cursor = None
            if more:
                if last_batch_id is None or last_ordinal is None:
                    raise _history_corrupt()
                next_cursor = _encode_cursor(
                    last_batch_id, last_ordinal, filter_digest, self._cursor_key
                )
            final_batches = tuple(
                _verified_history_slice(
                    batch,
                    start_ordinal,
                    values,
                    serialized_bytes,
                    isolate_outer=(
                        cache_verified or id(batch) in cached_batch_ids
                    ),
                )
                for batch, start_ordinal, values, serialized_bytes in selected
            )
            serialized_bytes = _encoded_history_page_size_from_batch_bytes(
                selected_batch_bytes,
                selected_count,
                next_cursor,
            )
            page_batch_sizes = tuple(item[3] for item in selected)
            return _verified_history_page(
                final_batches,
                value_count=selected_count,
                next_cursor=next_cursor,
                serialized_bytes=serialized_bytes,
            )

        try:
            page = self._database.read(
                read,
                empty=_verified_history_page(
                    (),
                    value_count=0,
                    next_cursor=None,
                    serialized_bytes=_EMPTY_HISTORY_PAGE_BYTES,
                ),
            )
            if cache_verified and observed_snapshot is not None:
                with self._database._integrity_lock:  # noqa: SLF001
                    stable = self._database._integrity_identity == observed_snapshot  # noqa: SLF001
                with self._verified_cache_lock:
                    if stable:
                        if self._verified_cache_snapshot != observed_snapshot:
                            self._verified_cache.clear()
                            self._verified_cache_snapshot = observed_snapshot
                        for evidence in pending_cache:
                            self._verified_cache[evidence.key] = evidence
                            self._verified_cache.move_to_end(evidence.key)
                        while len(self._verified_cache) > _VERIFIED_HISTORY_CACHE_BATCHES:
                            self._verified_cache.popitem(last=False)
                        if page_batch_sizes:
                            self._verified_page_cache = _VerifiedHistoryPageCache(
                                page_cache_key,
                                observed_snapshot,
                                page,
                                page_batch_sizes,
                            )
                    else:
                        self._verified_cache.clear()
                        self._verified_cache_snapshot = None
                        self._verified_page_cache = None
                if stable and page_batch_sizes:
                    page = _isolated_verified_page(page, page_batch_sizes)
            if transient_cache is not None and observed_snapshot is not None:
                with self._database._integrity_lock:  # noqa: SLF001
                    stable = self._database._integrity_identity == observed_snapshot  # noqa: SLF001
                if stable:
                    cached_snapshot = transient_cache.get("snapshot")
                    cached_batches = transient_cache.get("batches")
                    if (
                        cached_snapshot != observed_snapshot
                        or type(cached_batches) is not dict
                    ):
                        cached_batches = {}
                        transient_cache.clear()
                        transient_cache["snapshot"] = observed_snapshot
                        transient_cache["batches"] = cached_batches
                    typed_batches = cast(
                        dict[tuple[object, ...], _VerifiedHistoryBatch],
                        cached_batches,
                    )
                    for evidence in pending_cache[-2:]:
                        typed_batches[evidence.key] = _VerifiedHistoryBatch(
                            evidence.key,
                            _isolated_verified_batch(evidence.batch),
                            evidence.indexed,
                            evidence.encoded_value_lengths,
                            evidence.encoded_slice_base_bytes,
                        )
                    while len(typed_batches) > 2:
                        del typed_batches[next(iter(typed_batches))]
                else:
                    transient_cache.clear()
            return success(operation, page)
        except StorageFailure as error:
            return _storage_failure(operation, error)
        except _InvalidHistoryCursor:
            return failure(
                operation,
                "MONITOR_HISTORY_QUERY_INVALID",
                "history query is invalid",
            )

    def _stream_verified_batches(
        self,
        query: HistoryQuery,
        callback: Callable[[SampleBatch], None],
    ) -> ProtocolResult[int]:
        """Stream exact verified batches for the internal JSONL exporter."""
        operation = "history.stream"
        try:
            cursor_batch, cursor_ordinal, _ = self._validate_query(query)
            if (
                cursor_batch != 0
                or cursor_ordinal != -1
                or query.limit != MAX_HISTORY_VALUES
                or query.run_id is not None
                or query.group_id is not None
                or query.selector_kind is not None
                or not callable(callback)
            ):
                raise ValueError("history stream query is invalid")
        except ValueError:
            return failure(
                operation,
                "MONITOR_HISTORY_QUERY_INVALID",
                "history query is invalid",
            )

        def read(connection: sqlite3.Connection) -> int:
            parameters = (query.session_id, query.start_ns, query.end_ns)
            records = connection.execute(
                """
                SELECT batch_id,session_id,run_id,sequence,captured_ns,
                       payload_json,payload_bytes,payload_sha256,value_count
                FROM history_batches
                WHERE session_id = ? AND captured_ns >= ? AND captured_ns < ?
                ORDER BY batch_id
                """,
                parameters,
            )
            indexed_records = connection.execute(
                """
                SELECT v.batch_id,v.ordinal,v.selector_kind,v.selector,
                       v.value_json,v.value_bytes,v.value_sha256
                FROM history_values AS v
                JOIN history_batches AS b ON b.batch_id = v.batch_id
                WHERE b.session_id = ? AND b.captured_ns >= ? AND b.captured_ns < ?
                ORDER BY v.batch_id,v.ordinal
                """,
                parameters,
            )
            value_count = 0
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
                decoded_value_evidence: list[tuple[str, str, bytes, str]] = []
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
                    value_evidence=decoded_value_evidence,
                )
                index_rows = indexed_records.fetchmany(len(batch.values))
                if len(index_rows) != len(batch.values):
                    raise _history_corrupt()
                for ordinal, value in enumerate(batch.values):
                    index_row = index_rows[ordinal]
                    if len(index_row) != 7:
                        raise _history_corrupt()
                    (
                        indexed_batch_id, stored_ordinal, kind, selector,
                        value_raw, value_bytes, value_digest,
                    ) = index_row
                    (
                        expected_kind,
                        expected_selector,
                        expected_raw,
                        expected_digest,
                    ) = decoded_value_evidence[ordinal]
                    if (
                        indexed_batch_id != batch_id
                        or stored_ordinal != ordinal
                        or kind != expected_kind
                        or selector != expected_selector
                        or type(value_raw) is not bytes
                        or type(value_bytes) is not int
                        or value_bytes != len(value_raw)
                        or type(value_digest) is not str
                        or value_raw != expected_raw
                        or value_digest != expected_digest
                    ):
                        raise _history_corrupt()
                callback(batch)
                value_count += len(batch.values)
            if indexed_records.fetchone() is not None:
                raise _history_corrupt()
            return value_count

        try:
            count = self._database.read(read, empty=0)
            return success(operation, count)
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
                    "SELECT batch_id,value_count FROM history_batches WHERE captured_ns < ? ORDER BY captured_ns, batch_id LIMIT ?",
                    (cutoff, maximum + 1),
                ).fetchall()
                candidates = expired
                if not candidates and logical_before > RETENTION_LOGICAL_BYTES:
                    candidates = connection.execute(
                        "SELECT batch_id,value_count FROM history_batches ORDER BY captured_ns, batch_id LIMIT ?",
                        (maximum + 1,),
                    ).fetchall()
                require_budget()
                selected: list[int] = []
                selected_values = 0
                for row in candidates[:maximum]:
                    if (
                        len(row) != 2
                        or type(row[0]) is not int
                        or row[0] < 1
                        or type(row[1]) is not int
                        or row[1] < 0
                    ):
                        raise _history_corrupt()
                    if selected and selected_values + row[1] > RETENTION_DELETE_VALUES:
                        break
                    selected.append(row[0])
                    selected_values += row[1]
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
