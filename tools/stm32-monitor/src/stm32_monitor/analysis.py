"""Pure, bounded comparison of two already-loaded Monitor replay windows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import math
from types import MappingProxyType
import unicodedata
from typing import cast

from .models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from .replay import MonitorReplayError, MonitorRunRef, canonical_replay_json_bytes


ANALYSIS_REQUEST_SCHEMA = "stm32-monitor-analysis-request/1"
ANALYSIS_COMPUTATION_SCHEMA = "stm32-monitor-analysis-computation/1"
ANALYSIS_REQUEST_INVALID = "ANALYSIS_REQUEST_INVALID"
MAX_ANALYSIS_BATCHES = 1024
MAX_ANALYSIS_VALUES = 10_000
MAX_ANALYSIS_POSITIONS = MAX_ANALYSIS_BATCHES * 2
_MAPPING_PROXY = type(MappingProxyType({}))
_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "before_run",
        "after_run",
        "selector_kind",
        "selector",
        "alignment",
        "minimum_valid_pairs",
    }
)
_COMPUTATION_FIELDS = frozenset(
    {
        "schema",
        "request_digest",
        "quality",
        "conclusion",
        "reason_code",
        "aligned_position_count",
        "aligned_pair_count",
        "excluded_position_count",
        "before_first",
        "before_last",
        "before_min",
        "before_max",
        "after_first",
        "after_last",
        "after_min",
        "after_max",
        "delta_first",
        "delta_last",
        "changed",
    }
)
_QUALITIES = frozenset({"VALID", "DEGRADED", "INVALID"})
_CONCLUSIONS = frozenset({"COMPLETED", "INCONCLUSIVE"})
_REASONS = frozenset(
    {
        "VALUES_CHANGED",
        "VALUES_UNCHANGED",
        "VALUES_CHANGED_WITH_EXCLUSIONS",
        "VALUES_UNCHANGED_WITH_EXCLUSIONS",
        "INSUFFICIENT_VALID_PAIRS",
    }
)
_INTEGER_STAT_NAMES = (
    "aligned_position_count",
    "aligned_pair_count",
    "excluded_position_count",
)
_STAT_NAMES = (
    "before_first",
    "before_last",
    "before_min",
    "before_max",
    "after_first",
    "after_last",
    "after_min",
    "after_max",
    "delta_first",
    "delta_last",
)


class AnalysisError(ValueError):
    """One stable, bounded failure at the pure analysis boundary."""

    def __init__(self, code: str, message: str) -> None:
        if type(code) is not str or code != ANALYSIS_REQUEST_INVALID:
            raise ValueError("unknown analysis error code")
        if type(message) is not str or not message or len(message) > 256:
            raise ValueError("analysis error message is invalid")
        super().__init__(message)
        self._code = code
        self._message = message

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message


def _fail(message: str) -> None:
    raise AnalysisError(ANALYSIS_REQUEST_INVALID, message)


def _reject_tuples(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _fail("analysis value exceeds its nesting limit")
    if isinstance(value, tuple):
        _fail("analysis JSON must not contain tuple containers")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key, depth=depth + 1)
            _reject_tuples(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item, depth=depth + 1)


def _hash(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail(f"{label} is invalid")
    return cast(str, value)


def _text(value: object, label: str, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{label} is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        _fail(f"{label} is invalid")
    if unicodedata.normalize("NFC", value) != value:
        _fail(f"{label} is invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise AnalysisError(ANALYSIS_REQUEST_INVALID, f"{label} is invalid") from error
    return value


def _watch(kind: object, selector: object) -> WatchItem:
    _text(kind, "selector kind", maximum=32)
    _text(selector, "selector")
    try:
        item = WatchItem(cast(str, kind), cast(str, selector))
    except (TypeError, ValueError, OverflowError) as error:
        raise AnalysisError(ANALYSIS_REQUEST_INVALID, "selector is invalid") from error
    if type(item) is not WatchItem or item.kind != kind or item.selector != selector:
        _fail("selector is not canonical")
    return item


def _finite_number(value: object, label: str) -> float | int:
    if type(value) is bool or type(value) not in (int, float):
        _fail(f"{label} is invalid")
    if type(value) is float and not math.isfinite(value):
        _fail(f"{label} is invalid")
    return cast(float | int, value)


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    schema: str
    before_run: MonitorRunRef
    after_run: MonitorRunRef
    selector_kind: str
    selector: str
    alignment: str
    minimum_valid_pairs: int

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != ANALYSIS_REQUEST_SCHEMA:
            _fail("analysis request schema is invalid")
        if type(self.before_run) is not MonitorRunRef or type(self.after_run) is not MonitorRunRef:
            _fail("analysis request runs are invalid")
        _watch(self.selector_kind, self.selector)
        if type(self.alignment) is not str or self.alignment != "run-relative":
            _fail("analysis alignment is invalid")
        if (
            type(self.minimum_valid_pairs) is not int
            or not 2 <= self.minimum_valid_pairs <= MAX_ANALYSIS_VALUES
        ):
            _fail("minimum valid pairs are invalid")

    @property
    def request_digest(self) -> str:
        return sha256(canonical_replay_json_bytes(self.to_dict())).hexdigest()

    @property
    def watch_item(self) -> WatchItem:
        return _watch(self.selector_kind, self.selector)

    @classmethod
    def from_value(cls, value: object) -> "AnalysisRequest":
        if type(value) is cls:
            return value
        _reject_tuples(value)
        if type(value) is not dict or set(value) != _REQUEST_FIELDS:
            _fail("analysis request fields are not closed")
        try:
            before = MonitorRunRef.from_value(value["before_run"])
            after = MonitorRunRef.from_value(value["after_run"])
            return cls(
                schema=value["schema"],
                before_run=before,
                after_run=after,
                selector_kind=value["selector_kind"],
                selector=value["selector"],
                alignment=value["alignment"],
                minimum_valid_pairs=value["minimum_valid_pairs"],
            )
        except AnalysisError:
            raise
        except (MonitorReplayError, TypeError, ValueError, OverflowError) as error:
            raise AnalysisError(ANALYSIS_REQUEST_INVALID, "analysis request is invalid") from error

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "before_run": self.before_run.to_dict(),
            "after_run": self.after_run.to_dict(),
            "selector_kind": self.selector_kind,
            "selector": self.selector,
            "alignment": self.alignment,
            "minimum_valid_pairs": self.minimum_valid_pairs,
        }


def _validate_stat(value: object, label: str) -> None:
    if value is None:
        return
    _finite_number(value, label)


@dataclass(frozen=True, slots=True)
class AnalysisComputation:
    schema: str
    request_digest: str
    quality: str
    conclusion: str
    reason_code: str
    aligned_position_count: int
    aligned_pair_count: int
    excluded_position_count: int
    before_first: float | int | None
    before_last: float | int | None
    before_min: float | int | None
    before_max: float | int | None
    after_first: float | int | None
    after_last: float | int | None
    after_min: float | int | None
    after_max: float | int | None
    delta_first: float | int | None
    delta_last: float | int | None
    changed: bool | None

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != ANALYSIS_COMPUTATION_SCHEMA:
            _fail("analysis computation schema is invalid")
        _hash(self.request_digest, "request digest")
        if (
            type(self.quality) is not str
            or type(self.conclusion) is not str
            or self.quality not in _QUALITIES
            or self.conclusion not in _CONCLUSIONS
        ):
            _fail("analysis state is invalid")
        if type(self.reason_code) is not str or self.reason_code not in _REASONS:
            _fail("analysis reason is invalid")
        for field_name in _INTEGER_STAT_NAMES:
            value = getattr(self, field_name)
            if type(value) is not int or isinstance(value, bool) or not 0 <= value <= MAX_ANALYSIS_POSITIONS:
                _fail(f"{field_name} is invalid")
        if self.aligned_position_count < 1:
            _fail("aligned position count is invalid")
        if self.aligned_pair_count > self.aligned_position_count:
            _fail("analysis pair count is invalid")
        if self.excluded_position_count != self.aligned_position_count - self.aligned_pair_count:
            _fail("analysis exclusion count is invalid")
        for field_name in _STAT_NAMES:
            _validate_stat(getattr(self, field_name), field_name)
        if type(self.changed) is not bool and self.changed is not None:
            _fail("analysis changed state is invalid")
        if self.quality == "INVALID":
            if self.conclusion != "INCONCLUSIVE" or self.reason_code != "INSUFFICIENT_VALID_PAIRS":
                _fail("invalid analysis state is not inconclusive")
            if any(getattr(self, field_name) is not None for field_name in _STAT_NAMES) or self.changed is not None:
                _fail("inconclusive analysis must not expose statistics")
        else:
            if self.conclusion != "COMPLETED" or self.aligned_pair_count < 2 or self.changed is None:
                _fail("completed analysis state is invalid")
            excluded = self.excluded_position_count > 0
            changed = self.changed
            expected_reason = (
                "VALUES_CHANGED_WITH_EXCLUSIONS"
                if changed and excluded
                else "VALUES_UNCHANGED_WITH_EXCLUSIONS"
                if excluded
                else "VALUES_CHANGED"
                if changed
                else "VALUES_UNCHANGED"
            )
            if self.reason_code != expected_reason:
                _fail("analysis reason does not match its state")
            if any(getattr(self, field_name) is None for field_name in _STAT_NAMES):
                _fail("completed analysis must expose all statistics")
            for prefix in ("before", "after"):
                first = cast(float | int, getattr(self, f"{prefix}_first"))
                last = cast(float | int, getattr(self, f"{prefix}_last"))
                minimum = cast(float | int, getattr(self, f"{prefix}_min"))
                maximum = cast(float | int, getattr(self, f"{prefix}_max"))
                try:
                    ordered = minimum <= first <= maximum and minimum <= last <= maximum
                except (TypeError, ValueError, OverflowError):
                    _fail(f"{prefix} statistics are not ordered")
                if not ordered:
                    _fail(f"{prefix} statistics are not ordered")
            try:
                expected_delta_first = self.after_first - self.before_first
                expected_delta_last = self.after_last - self.before_last
            except (TypeError, ValueError, OverflowError):
                _fail("analysis deltas are invalid")
            if (
                type(expected_delta_first) is float
                and not math.isfinite(expected_delta_first)
            ) or (
                type(expected_delta_last) is float
                and not math.isfinite(expected_delta_last)
            ):
                _fail("analysis deltas are invalid")
            if (
                self.delta_first != expected_delta_first
                or self.delta_last != expected_delta_last
            ):
                _fail("analysis deltas are inconsistent")
            if not self.changed and any(
                getattr(self, f"before_{field}") != getattr(self, f"after_{field}")
                for field in ("first", "last", "min", "max")
            ):
                _fail("unchanged analysis statistics are inconsistent")
            if self.quality == "VALID" and excluded:
                _fail("valid analysis cannot contain exclusions")
            if self.quality == "DEGRADED" and not excluded:
                _fail("degraded analysis requires exclusions")

    @classmethod
    def from_value(cls, value: object) -> "AnalysisComputation":
        if type(value) is cls:
            return value
        _reject_tuples(value)
        if type(value) is not dict or set(value) != _COMPUTATION_FIELDS:
            _fail("analysis computation fields are not closed")
        try:
            return cls(**value)
        except AnalysisError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise AnalysisError(ANALYSIS_REQUEST_INVALID, "analysis computation is invalid") from error

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "request_digest": self.request_digest,
            "quality": self.quality,
            "conclusion": self.conclusion,
            "reason_code": self.reason_code,
            "aligned_position_count": self.aligned_position_count,
            "aligned_pair_count": self.aligned_pair_count,
            "excluded_position_count": self.excluded_position_count,
            "before_first": self.before_first,
            "before_last": self.before_last,
            "before_min": self.before_min,
            "before_max": self.before_max,
            "after_first": self.after_first,
            "after_last": self.after_last,
            "after_min": self.after_min,
            "after_max": self.after_max,
            "delta_first": self.delta_first,
            "delta_last": self.delta_last,
            "changed": self.changed,
        }


def _binding_matches(reference: MonitorRunRef, batch: SampleBatch) -> bool:
    binding = batch.binding
    return (
        type(binding) is ObservationBinding
        and binding.workspace_id == reference.import_workspace_id
        and binding.logical_project_id == reference.logical_project_id
        and binding.session_id == reference.projected_session_id
        and binding.probe_id == reference.probe_id
        and binding.target_device == reference.target_device
        and binding.physical_target == reference.physical_target
        and binding.build_id == reference.build_id
        and binding.elf_sha256 == reference.elf_sha256
        and binding.input_snapshot_sha256 == reference.input_snapshot_sha256
        and binding.git_head == reference.git_head
        and binding.git_dirty == reference.git_dirty
        and binding.flash_session_id == reference.flash_session_id
        and binding.lease_id == reference.lease_id
        and binding.dwarf_sha256 == reference.dwarf_sha256
        and binding.svd_sha256 == reference.svd_sha256
    )


def _validate_window(reference: MonitorRunRef, batches: object) -> tuple[SampleBatch, ...]:
    if type(reference) is not MonitorRunRef:
        _fail("analysis run reference is invalid")
    if type(batches) is not tuple or not batches or len(batches) > MAX_ANALYSIS_BATCHES:
        _fail("analysis batch window is invalid")
    values_count = 0
    checked: list[SampleBatch] = []
    if len(reference.projected_batch_sha256s) != len(batches):
        _fail("analysis batch count does not match its run reference")
    previous: SampleBatch | None = None
    for index, batch in enumerate(batches):
        if type(batch) is not SampleBatch or any(
            type(sample) is not SampleValue or type(sample.watch) is not WatchItem
            for sample in batch.values
        ):
            _fail("analysis batch value types are invalid")
        values_count += len(batch.values)
        if values_count > MAX_ANALYSIS_VALUES or not _binding_matches(reference, batch):
            _fail("analysis batch identity is invalid")
        if str(batch.run_id) != reference.projected_run_id:
            _fail("analysis batch run identity is invalid")
        if str(batch.group_id) != reference.group_id or batch.group_revision != reference.group_revision:
            _fail("analysis batch group identity is invalid")
        if previous is not None and (
            batch.sequence != previous.sequence + 1
            or batch.scheduled_unix_ns <= previous.scheduled_unix_ns
            or batch.captured_unix_ns <= previous.captured_unix_ns
        ):
            _fail("analysis batch ordering is invalid")
        try:
            digest = sha256(canonical_replay_json_bytes(batch.to_dict())).hexdigest()
        except (MonitorReplayError, TypeError, ValueError, OverflowError) as error:
            raise AnalysisError(ANALYSIS_REQUEST_INVALID, "analysis batch digest is invalid") from error
        if digest != reference.projected_batch_sha256s[index]:
            _fail("analysis batch digest does not match its run reference")
        checked.append(batch)
        previous = batch
    first = checked[0]
    last = checked[-1]
    if (
        first.sequence != reference.start_sequence
        or last.sequence + 1 != reference.end_sequence_exclusive
        or first.captured_unix_ns != reference.start_captured_unix_ns
        or last.captured_unix_ns + 1 != reference.end_captured_unix_ns_exclusive
    ):
        _fail("analysis batch window does not match its run reference")
    return tuple(checked)


def _vocabulary(batches: tuple[SampleBatch, ...]) -> tuple[WatchItem, ...]:
    result: list[WatchItem] = []
    for batch in batches:
        for sample in batch.values:
            if sample.watch not in result:
                result.append(sample.watch)
    return tuple(result)


def _trusted_sample(batch: SampleBatch, requested: WatchItem) -> tuple[str, float | int] | None:
    matches = [sample for sample in batch.values if sample.watch == requested]
    if len(matches) != 1:
        return None
    sample = matches[0]
    if sample.status != "OK" or type(sample.typed_value) not in (dict, _MAPPING_PROXY):
        return None
    typed = sample.typed_value
    if set(typed) != {"type", "value"}:
        return None
    type_name = typed["type"]
    if type(type_name) is not str or not 1 <= len(type_name) <= 128:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in type_name):
        return None
    if unicodedata.normalize("NFC", type_name) != type_name:
        return None
    try:
        type_name.encode("utf-8")
    except UnicodeEncodeError:
        return None
    value = typed["value"]
    if type(value) is bool or type(value) not in (int, float):
        return None
    if type(value) is float and not math.isfinite(value):
        return None
    return type_name, cast(float | int, value)


def _shared_compatibility(
    before: MonitorRunRef,
    after: MonitorRunRef,
    before_batches: tuple[SampleBatch, ...],
    after_batches: tuple[SampleBatch, ...],
) -> None:
    if (
        before.origin_workspace_id != after.origin_workspace_id
        or before.import_workspace_id != after.import_workspace_id
        or before.logical_project_id != after.logical_project_id
        or before.target_device != after.target_device
        or before.group_id != after.group_id
        or before.group_revision != after.group_revision
        or set(_vocabulary(before_batches)) != set(_vocabulary(after_batches))
    ):
        _fail("analysis run identities are incompatible")


def _stats(values: list[float | int]) -> tuple[float | int, float | int, float | int, float | int]:
    return values[0], values[-1], min(values), max(values)


def analyze_monitor_windows(
    request: AnalysisRequest,
    before_batches: tuple[SampleBatch, ...],
    after_batches: tuple[SampleBatch, ...],
) -> AnalysisComputation:
    """Compare one exact scalar selector at equal run-relative scheduled times."""

    try:
        if type(request) is not AnalysisRequest:
            _fail("analysis request is invalid")
        before = _validate_window(request.before_run, before_batches)
        after = _validate_window(request.after_run, after_batches)
        _shared_compatibility(request.before_run, request.after_run, before, after)
        requested = request.watch_item

        before_zero = before[0].scheduled_unix_ns
        after_zero = after[0].scheduled_unix_ns
        before_by_time = {batch.scheduled_unix_ns - before_zero: batch for batch in before}
        after_by_time = {batch.scheduled_unix_ns - after_zero: batch for batch in after}
        positions = sorted(set(before_by_time) | set(after_by_time))
        pair_values: list[tuple[float | int, float | int]] = []
        for position in positions:
            before_batch = before_by_time.get(position)
            after_batch = after_by_time.get(position)
            if before_batch is None or after_batch is None:
                continue
            before_value = _trusted_sample(before_batch, requested)
            after_value = _trusted_sample(after_batch, requested)
            if (
                before_value is None
                or after_value is None
                or before_value[0] != after_value[0]
            ):
                continue
            pair_values.append((before_value[1], after_value[1]))

        pair_count = len(pair_values)
        position_count = len(positions)
        excluded_count = position_count - pair_count
        if pair_count < request.minimum_valid_pairs:
            return AnalysisComputation(
                schema=ANALYSIS_COMPUTATION_SCHEMA,
                request_digest=request.request_digest,
                quality="INVALID",
                conclusion="INCONCLUSIVE",
                reason_code="INSUFFICIENT_VALID_PAIRS",
                aligned_position_count=position_count,
                aligned_pair_count=pair_count,
                excluded_position_count=excluded_count,
                before_first=None,
                before_last=None,
                before_min=None,
                before_max=None,
                after_first=None,
                after_last=None,
                after_min=None,
                after_max=None,
                delta_first=None,
                delta_last=None,
                changed=None,
            )

        before_values = [pair[0] for pair in pair_values]
        after_values = [pair[1] for pair in pair_values]
        before_first, before_last, before_min, before_max = _stats(before_values)
        after_first, after_last, after_min, after_max = _stats(after_values)
        deltas = [after_value - before_value for before_value, after_value in pair_values]
        changed = any(before_value != after_value for before_value, after_value in pair_values)
        quality = "DEGRADED" if excluded_count else "VALID"
        reason_code = (
            "VALUES_CHANGED_WITH_EXCLUSIONS"
            if changed and excluded_count
            else "VALUES_UNCHANGED_WITH_EXCLUSIONS"
            if excluded_count
            else "VALUES_CHANGED"
            if changed
            else "VALUES_UNCHANGED"
        )
        return AnalysisComputation(
            schema=ANALYSIS_COMPUTATION_SCHEMA,
            request_digest=request.request_digest,
            quality=quality,
            conclusion="COMPLETED",
            reason_code=reason_code,
            aligned_position_count=position_count,
            aligned_pair_count=pair_count,
            excluded_position_count=excluded_count,
            before_first=before_first,
            before_last=before_last,
            before_min=before_min,
            before_max=before_max,
            after_first=after_first,
            after_last=after_last,
            after_min=after_min,
            after_max=after_max,
            delta_first=deltas[0],
            delta_last=deltas[-1],
            changed=changed,
        )
    except AnalysisError:
        raise
    except (MonitorReplayError, TypeError, ValueError, OverflowError, RecursionError) as error:
        raise AnalysisError(ANALYSIS_REQUEST_INVALID, "analysis input is invalid") from error


__all__ = [
    "ANALYSIS_COMPUTATION_SCHEMA",
    "ANALYSIS_REQUEST_INVALID",
    "ANALYSIS_REQUEST_SCHEMA",
    "AnalysisComputation",
    "AnalysisError",
    "AnalysisRequest",
    "analyze_monitor_windows",
]
