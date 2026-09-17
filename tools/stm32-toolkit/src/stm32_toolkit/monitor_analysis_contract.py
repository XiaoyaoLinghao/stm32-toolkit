"""Shared bounded native Monitor analysis contract.

The module deliberately contains only JSON shaped inputs and outputs.  Monitor
adapts its immutable sample models to these mappings, while Toolkit readers
feed authenticated transcript mappings into the same implementation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
import unicodedata

from .monitor_replay_contract import ReplayContractError, validate_run_reference


NATIVE_ANALYSIS_REQUEST_SCHEMA = "stm32-monitor-analysis-request/2"
NATIVE_ANALYSIS_COMPUTATION_SCHEMA = "stm32-monitor-analysis-computation/1"
NATIVE_SCALAR_POLICY = "native-uint-register/1"
NATIVE_ALIGNMENT = "bounded-run-relative"
NATIVE_SELECTOR_KIND = "register"
NATIVE_REGISTER_WIDTHS = frozenset({8, 16, 32})
NATIVE_MIN_PAIRING_SKEW_NS = 1
NATIVE_MAX_PAIRING_SKEW_NS = 5_000_000
NATIVE_MAX_BATCHES = 1024
NATIVE_MAX_VALUES = 10_000
NATIVE_MAX_POSITIONS = 2048

_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "before_run",
        "after_run",
        "selector_kind",
        "selector",
        "alignment",
        "minimum_valid_pairs",
        "scalar_policy",
        "max_pairing_skew_ns",
    }
)
_NATIVE_TYPED_FIELDS = frozenset({
    "bitWidth",
    "expression",
    "rawHex",
    "typeName",
    "value",
})
_NATIVE_WATCH_FIELDS = frozenset({"kind", "registerPath"})
_HEX = re.compile(r"\A0x[0-9a-f]+\Z")
_VARIABLE_WATCH_FIELDS = frozenset({"kind", "expression"})
_FACT_KINDS = frozenset({"value-varies", "bit-values-mask"})

_COMPUTATION_FIELDS = (
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
)


class NativeAnalysisContractError(ValueError):
    """A bounded violation of the native analysis contract."""


def _fail(message: str) -> None:
    raise NativeAnalysisContractError(message)


def _text(value: object, label: str, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail(f"{label} is invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise NativeAnalysisContractError(f"{label} is invalid") from error
    return value


def _physical_reference(value: object, label: str) -> dict[str, object]:
    try:
        reference = validate_run_reference(value)
    except (ReplayContractError, TypeError, ValueError, OverflowError) as error:
        raise NativeAnalysisContractError(f"{label} is invalid") from error
    if (
        reference["schema"] != "stm32-monitor-run-ref/2"
        or reference["execution_source"] != "physical"
        or reference["physical_transport_evidence"] is not True
    ):
        _fail(f"{label} provenance is invalid")
    return reference


def validate_native_request(
    value: object,
    *,
    expected_before: Mapping[str, object] | None = None,
    expected_after: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate and return one canonical-shaped native request mapping.

    Run references are intentionally checked for physical v2 provenance here;
    their transcript and digest authenticity remains the responsibility of the
    Monitor producer or Toolkit evidence adapter.
    """

    if type(value) is not dict or set(value) != _REQUEST_FIELDS:
        _fail("native analysis request fields are not closed")
    request = value
    if request["schema"] != NATIVE_ANALYSIS_REQUEST_SCHEMA:
        _fail("native analysis request schema is invalid")
    before = _physical_reference(request["before_run"], "before_run")
    after = _physical_reference(request["after_run"], "after_run")
    if expected_before is not None and before != dict(expected_before):
        _fail("native analysis before reference differs")
    if expected_after is not None and after != dict(expected_after):
        _fail("native analysis after reference differs")
    if request["selector_kind"] != NATIVE_SELECTOR_KIND:
        _fail("native analysis selector kind is invalid")
    _text(request["selector"], "native analysis selector")
    if request["alignment"] != NATIVE_ALIGNMENT:
        _fail("native analysis alignment is invalid")
    if request["scalar_policy"] != NATIVE_SCALAR_POLICY:
        _fail("native analysis scalar policy is invalid")
    minimum = request["minimum_valid_pairs"]
    if type(minimum) is not int or isinstance(minimum, bool) or not 2 <= minimum <= NATIVE_MAX_VALUES:
        _fail("native analysis minimum pair count is invalid")
    skew = request["max_pairing_skew_ns"]
    if (
        type(skew) is not int
        or isinstance(skew, bool)
        or not NATIVE_MIN_PAIRING_SKEW_NS <= skew <= NATIVE_MAX_PAIRING_SKEW_NS
    ):
        _fail("native analysis pairing skew is invalid")
    return request


def _mapping_field(value: object, *names: str) -> object:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        try:
            return getattr(value, name)
        except AttributeError:
            continue
    return None


def _native_sample(batch: object, selector: str) -> tuple[int, int] | None:
    values = _mapping_field(batch, "values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        _fail("native analysis batch values are invalid")
    matches: list[object] = []
    for sample in values:
        watch = _mapping_field(sample, "watch")
        if not isinstance(watch, Mapping) or set(watch) != _NATIVE_WATCH_FIELDS:
            continue
        if watch.get("kind") == NATIVE_SELECTOR_KIND and watch.get("registerPath") == selector:
            matches.append(sample)
    if len(matches) != 1:
        return None
    sample = matches[0]
    if _mapping_field(sample, "status") != "OK":
        return None
    typed = _mapping_field(sample, "typedValue")
    if not isinstance(typed, Mapping) or set(typed) != _NATIVE_TYPED_FIELDS:
        return None
    if typed.get("expression") != selector:
        return None
    width = typed.get("bitWidth")
    if type(width) is not int or isinstance(width, bool) or width not in NATIVE_REGISTER_WIDTHS:
        return None
    if typed.get("typeName") != f"uint{width}_register":
        return None
    value = typed.get("value")
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= (1 << width) - 1:
        return None
    raw_hex = typed.get("rawHex")
    if type(raw_hex) is not str or len(raw_hex) != 2 + width // 4 or _HEX.fullmatch(raw_hex) is None:
        return None
    if int(raw_hex[2:], 16) != value:
        return None
    return width, value


def _strict_monitor_fact_sample(
    batch: object,
    *,
    selector_kind: str,
    selector: str,
) -> tuple[int, int]:
    """Read one selected scalar without the permissive analysis exclusions.

    ``_native_sample`` intentionally returns ``None`` for a malformed native
    analysis position so that the historical before/after pairing contract can
    report excluded positions.  Supplementary Monitor facts have a different
    contract: every selected sample must be present, successful and exactly
    typed.  Keep this parser separate so the two behaviours cannot silently
    converge.
    """

    values = _mapping_field(batch, "values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        _fail("physical monitor fact batch values are invalid")
    matches: list[object] = []
    for sample in values:
        watch = _mapping_field(sample, "watch")
        if not isinstance(watch, Mapping):
            continue
        if selector_kind == "variable":
            if (
                watch.get("kind") == "variable"
                and watch.get("expression") == selector
            ):
                matches.append(sample)
        elif selector_kind == "register":
            if (
                watch.get("kind") == "register"
                and watch.get("registerPath") == selector
            ):
                matches.append(sample)
        else:
            _fail("physical monitor fact selector kind is invalid")
    if len(matches) != 1:
        _fail("physical monitor fact selected sample is missing or ambiguous")

    sample = matches[0]
    watch = _mapping_field(sample, "watch")
    expected_watch_fields = (
        _VARIABLE_WATCH_FIELDS if selector_kind == "variable" else _NATIVE_WATCH_FIELDS
    )
    if not isinstance(watch, Mapping) or set(watch) != expected_watch_fields:
        _fail("physical monitor fact selected watch fields are not closed")
    if isinstance(sample, Mapping) and set(sample) != {"watch", "status", "typedValue", "code", "definition"}:
        _fail("physical monitor fact sample fields are not closed")
    if _mapping_field(sample, "status") != "OK" or _mapping_field(sample, "code") is not None:
        _fail("physical monitor fact selected sample is not successful")

    typed = _mapping_field(sample, "typedValue")
    if not isinstance(typed, Mapping) or set(typed) != _NATIVE_TYPED_FIELDS:
        _fail("physical monitor fact typed value fields are not closed")
    if typed.get("expression") != selector:
        _fail("physical monitor fact typed expression differs")
    width = typed.get("bitWidth")
    if type(width) is not int or isinstance(width, bool) or width not in NATIVE_REGISTER_WIDTHS:
        _fail("physical monitor fact scalar width is invalid")
    if selector_kind == "variable":
        if width != 32 or typed.get("typeName") != "long unsigned int":
            _fail("physical monitor fact variable type is invalid")
    elif typed.get("typeName") != f"uint{width}_register":
        _fail("physical monitor fact register type is invalid")

    value = typed.get("value")
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= (1 << width) - 1:
        _fail("physical monitor fact scalar value is invalid")
    raw_hex = typed.get("rawHex")
    expected_hex = 2 + width // 4
    if (
        type(raw_hex) is not str
        or len(raw_hex) != expected_hex
        or re.fullmatch(rf"0x[0-9a-f]{{{width // 4}}}", raw_hex) is None
        or int(raw_hex[2:], 16) != value
    ):
        _fail("physical monitor fact raw scalar does not match value")

    definition = _mapping_field(sample, "definition")
    if (
        not isinstance(definition, Mapping)
        or set(definition) != {"kind", "selector"}
        or definition.get("kind") != selector_kind
        or definition.get("selector") != selector
    ):
        _fail("physical monitor fact definition differs")
    return width, value


def evaluate_physical_monitor_fact(
    batches: object,
    *,
    selector_kind: str,
    selector: str,
    fact: str,
    minimum_valid_samples: int,
    bit_index: int | None = None,
) -> int:
    """Recompute one strict physical Monitor fact from authenticated batches.

    The result is an explicit integer suitable for the Diagnostic plan model:
    ``value-varies`` yields 0/1 and ``bit-values-mask`` yields 1/2/3.
    """

    if selector_kind not in {"variable", "register"}:
        _fail("physical monitor fact selector kind is invalid")
    _text(selector, "physical monitor fact selector")
    if fact not in _FACT_KINDS:
        _fail("physical monitor fact kind is invalid")
    if (
        type(minimum_valid_samples) is not int
        or isinstance(minimum_valid_samples, bool)
        or not 1 <= minimum_valid_samples <= NATIVE_MAX_BATCHES
    ):
        _fail("physical monitor fact minimum sample count is invalid")
    if fact == "value-varies":
        if bit_index is not None:
            _fail("value-varies does not accept a bit index")
    else:
        if selector_kind != "register":
            _fail("bit-values-mask requires a register selector")
        if (
            type(bit_index) is not int
            or isinstance(bit_index, bool)
            or bit_index < 0
            or bit_index >= 32
        ):
            _fail("physical monitor fact bit index is invalid")

    if not isinstance(batches, Sequence) or isinstance(batches, (str, bytes, bytearray)):
        _fail("physical monitor fact batches are invalid")
    if not batches or len(batches) > NATIVE_MAX_BATCHES:
        _fail("physical monitor fact batch window is invalid")
    if len(batches) < minimum_valid_samples:
        _fail("physical monitor fact has insufficient valid samples")

    selected: list[int] = []
    widths: list[int] = []
    for batch in batches:
        width, value = _strict_monitor_fact_sample(
            batch,
            selector_kind=selector_kind,
            selector=selector,
        )
        widths.append(width)
        selected.append(value)
    if len(set(widths)) != 1:
        _fail("physical monitor fact scalar widths conflict")

    if fact == "value-varies":
        return int(any(value != selected[0] for value in selected[1:]))
    assert bit_index is not None
    width = widths[0]
    if bit_index >= width:
        _fail("physical monitor fact bit index exceeds scalar width")
    mask = 0
    for value in selected:
        mask |= 1 << ((value >> bit_index) & 1)
    return mask


def _timestamps(batches: object, label: str) -> tuple[tuple[object, int], ...]:
    if not isinstance(batches, Sequence) or isinstance(batches, (str, bytes, bytearray)):
        _fail(f"{label} batches are invalid")
    if not batches or len(batches) > NATIVE_MAX_BATCHES:
        _fail(f"{label} batch window is invalid")
    total_values = 0
    result: list[tuple[object, int]] = []
    previous: int | None = None
    for batch in batches:
        scheduled = _mapping_field(batch, "scheduledUnixNs", "scheduled_unix_ns")
        if type(scheduled) is not int or isinstance(scheduled, bool) or scheduled < 0:
            _fail(f"{label} scheduled timestamp is invalid")
        if previous is not None and scheduled <= previous:
            _fail(f"{label} scheduled timestamps are not strictly increasing")
        values = _mapping_field(batch, "values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            _fail(f"{label} batch values are invalid")
        total_values += len(values)
        if total_values > NATIVE_MAX_VALUES:
            _fail(f"{label} values exceed their limit")
        result.append((batch, scheduled))
        previous = scheduled
    return tuple(result)


def _stats(values: list[int]) -> tuple[int, int, int, int]:
    return values[0], values[-1], min(values), max(values)


def native_statistics(
    before_batches: object,
    after_batches: object,
    *,
    selector: str,
    max_pairing_skew_ns: int,
    minimum_valid_pairs: int,
    request_digest: str,
) -> dict[str, object]:
    """Recompute bounded native alignment and statistics from transcript data."""

    _text(selector, "native analysis selector")
    if (
        type(max_pairing_skew_ns) is not int
        or isinstance(max_pairing_skew_ns, bool)
        or not NATIVE_MIN_PAIRING_SKEW_NS <= max_pairing_skew_ns <= NATIVE_MAX_PAIRING_SKEW_NS
    ):
        _fail("native analysis pairing skew is invalid")
    if (
        type(minimum_valid_pairs) is not int
        or isinstance(minimum_valid_pairs, bool)
        or not 2 <= minimum_valid_pairs <= NATIVE_MAX_VALUES
    ):
        _fail("native analysis minimum pair count is invalid")
    if type(request_digest) is not str or len(request_digest) != 64:
        _fail("native analysis request digest is invalid")
    before = _timestamps(before_batches, "before")
    after = _timestamps(after_batches, "after")
    if len(before) + len(after) > NATIVE_MAX_POSITIONS:
        _fail("native analysis positions exceed their limit")

    before_zero = before[0][1]
    after_zero = after[0][1]
    before_offsets = tuple(timestamp - before_zero for _, timestamp in before)
    after_offsets = tuple(timestamp - after_zero for _, timestamp in after)
    edges: list[tuple[int, int]] = []
    for before_index, before_offset in enumerate(before_offsets):
        for after_index, after_offset in enumerate(after_offsets):
            if abs(before_offset - after_offset) <= max_pairing_skew_ns:
                edges.append((before_index, after_index))
    before_degree = [0] * len(before)
    after_degree = [0] * len(after)
    for before_index, after_index in edges:
        before_degree[before_index] += 1
        after_degree[after_index] += 1
    pairs = tuple(
        (before_index, after_index)
        for before_index, after_index in edges
        if before_degree[before_index] == 1 and after_degree[after_index] == 1
    )

    position_count = len(before) + len(after) - len(pairs)
    pair_values: list[tuple[int, int]] = []
    for before_index, after_index in pairs:
        before_value = _native_sample(before[before_index][0], selector)
        after_value = _native_sample(after[after_index][0], selector)
        if (
            before_value is None
            or after_value is None
            or before_value[0] != after_value[0]
        ):
            continue
        pair_values.append((before_value[1], after_value[1]))

    pair_count = len(pair_values)
    excluded_count = position_count - pair_count
    if pair_count < minimum_valid_pairs:
        return {
            "schema": NATIVE_ANALYSIS_COMPUTATION_SCHEMA,
            "request_digest": request_digest,
            "quality": "INVALID",
            "conclusion": "INCONCLUSIVE",
            "reason_code": "INSUFFICIENT_VALID_PAIRS",
            "aligned_position_count": position_count,
            "aligned_pair_count": pair_count,
            "excluded_position_count": excluded_count,
            "before_first": None,
            "before_last": None,
            "before_min": None,
            "before_max": None,
            "after_first": None,
            "after_last": None,
            "after_min": None,
            "after_max": None,
            "delta_first": None,
            "delta_last": None,
            "changed": None,
        }

    before_values = [pair[0] for pair in pair_values]
    after_values = [pair[1] for pair in pair_values]
    before_first, before_last, before_min, before_max = _stats(before_values)
    after_first, after_last, after_min, after_max = _stats(after_values)
    deltas = [after_value - before_value for before_value, after_value in pair_values]
    changed = any(
        before_value != after_value
        for before_value, after_value in pair_values
    )
    excluded = excluded_count > 0
    return {
        "schema": NATIVE_ANALYSIS_COMPUTATION_SCHEMA,
        "request_digest": request_digest,
        "quality": "DEGRADED" if excluded else "VALID",
        "conclusion": "COMPLETED",
        "reason_code": (
            "VALUES_CHANGED_WITH_EXCLUSIONS"
            if changed and excluded
            else "VALUES_UNCHANGED_WITH_EXCLUSIONS"
            if excluded
            else "VALUES_CHANGED"
            if changed
            else "VALUES_UNCHANGED"
        ),
        "aligned_position_count": position_count,
        "aligned_pair_count": pair_count,
        "excluded_position_count": excluded_count,
        "before_first": before_first,
        "before_last": before_last,
        "before_min": before_min,
        "before_max": before_max,
        "after_first": after_first,
        "after_last": after_last,
        "after_min": after_min,
        "after_max": after_max,
        "delta_first": deltas[0],
        "delta_last": deltas[-1],
        "changed": changed,
    }


def computation_fields(value: Mapping[str, object]) -> dict[str, object]:
    """Return only the stable computation fields for an equality check."""

    return {field: value[field] for field in _COMPUTATION_FIELDS}


__all__ = [
    "NATIVE_ALIGNMENT",
    "NATIVE_ANALYSIS_COMPUTATION_SCHEMA",
    "NATIVE_ANALYSIS_REQUEST_SCHEMA",
    "NATIVE_MAX_BATCHES",
    "NATIVE_MAX_PAIRING_SKEW_NS",
    "NATIVE_MAX_POSITIONS",
    "NATIVE_MAX_VALUES",
    "NATIVE_MIN_PAIRING_SKEW_NS",
    "NATIVE_REGISTER_WIDTHS",
    "NATIVE_SCALAR_POLICY",
    "NATIVE_SELECTOR_KIND",
    "NativeAnalysisContractError",
    "computation_fields",
    "evaluate_physical_monitor_fact",
    "native_statistics",
    "validate_native_request",
]
