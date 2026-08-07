"""Finite, in-memory sampling for typed DWARF variables."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.result import OperationResult

from .dwarf import DwarfCatalog
from .model import DebugFirmwareBinding, SampleReport
from .read import VariableReadRequest, read_variables

_OPERATION = "stm32_debug_sample_variables"
_MIN_INTERVAL_MS = 100
_MAX_INTERVAL_MS = 5_000
_MAX_SAMPLE_COUNT = 10_000
_MAX_DURATION_MS = 3_600_000
_MAX_OUTPUT_ITEMS = 20_000
_MAX_EXPRESSIONS = 256


@dataclass(frozen=True)
class SampleVariablesRequest:
    binding: DebugFirmwareBinding
    catalog: object
    expressions: tuple[str, ...]
    interval_ms: int
    count: int | None = None
    duration_ms: int | None = None


def _invalid() -> OperationResult[None]:
    return OperationResult.failure(
        _OPERATION,
        "DEBUG_SAMPLE_REQUEST_INVALID",
        "Finite sample request is invalid",
        {},
    )


def _validated(
    request: object,
) -> tuple[SampleVariablesRequest, int, int] | None:
    if not isinstance(request, SampleVariablesRequest):
        return None
    if type(request.binding) is not DebugFirmwareBinding:
        return None
    if (
        type(request.expressions) is not tuple
        or not 1 <= len(request.expressions) <= _MAX_EXPRESSIONS
        or len(set(request.expressions)) != len(request.expressions)
        or any(
            not isinstance(expression, str)
            or not expression
            or len(expression) > 512
            or "\x00" in expression
            for expression in request.expressions
        )
        or type(request.catalog) is not DwarfCatalog
    ):
        return None
    if (
        type(request.interval_ms) is not int
        or not 1 <= request.interval_ms <= _MAX_DURATION_MS
    ):
        return None
    if request.count is not None and (
        type(request.count) is not int
        or not 1 <= request.count <= _MAX_SAMPLE_COUNT
    ):
        return None
    if request.duration_ms is not None and (
        type(request.duration_ms) is not int
        or not 1 <= request.duration_ms <= _MAX_DURATION_MS
    ):
        return None
    if request.count is None and request.duration_ms is None:
        return None
    applied = min(_MAX_INTERVAL_MS, max(_MIN_INTERVAL_MS, request.interval_ms))
    duration_slots = (
        math.ceil(request.duration_ms / applied)
        if request.duration_ms is not None
        else _MAX_SAMPLE_COUNT
    )
    slots = min(
        request.count if request.count is not None else _MAX_SAMPLE_COUNT,
        duration_slots,
    )
    if slots < 1 or slots * len(request.expressions) > _MAX_OUTPUT_ITEMS:
        return None
    return request, applied, slots


async def sample_variables(
    request: object,
    client: object,
    *,
    _monotonic: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> OperationResult[SampleReport]:
    """Sample a bounded variable set on monotonic deadlines without persistence."""

    checked = _validated(request)
    if checked is None:
        return _invalid()
    typed, applied_ms, slots = checked
    interval = applied_ms / 1000.0
    start = _monotonic()
    if not isinstance(start, (int, float)) or not math.isfinite(start):
        return OperationResult.failure(
            _OPERATION, "DEBUG_SAMPLE_CLOCK_INVALID", "Sampling clock is invalid", {}
        )
    samples: list[dict[str, object]] = []
    actual_offsets: list[float] = []
    deadline_misses = 0
    dropped = 0
    slot = 0
    try:
        while slot < slots:
            deadline = start + slot * interval
            now = _monotonic()
            if now < deadline:
                await _sleep(deadline - now)
                now = _monotonic()
            if now >= deadline + interval:
                # A nanosecond tolerance prevents binary float representation
                # from placing an exact monotonic deadline in the prior slot.
                due = min(slots, int((now - start + 1e-9) // interval))
                if due > slot:
                    skipped = due - slot
                    dropped += skipped
                    deadline_misses += skipped
                    slot = due
                    if slot >= slots:
                        break
                    deadline = start + slot * interval
            actual = _monotonic()
            if actual > deadline + 1e-9:
                deadline_misses += 1
            result = await read_variables(
                VariableReadRequest(
                    typed.binding, typed.catalog, typed.expressions
                ),
                client,
            )
            finished = _monotonic()
            if not result.ok or result.data is None:
                return OperationResult.failure(
                    _OPERATION,
                    "DEBUG_BINDING_LOST",
                    "Sampling stopped because the debug binding was lost",
                    {"cause": result.code},
                )
            actual_offset = max(0.0, actual - start)
            actual_offsets.append(actual_offset)
            samples.append(
                {
                    "index": slot,
                    "scheduledOffsetMs": int(round((deadline - start) * 1000)),
                    "actualOffsetMs": int(round(actual_offset * 1000)),
                    "latencyMs": int(round(max(0.0, finished - actual) * 1000)),
                    "actualAtUtc": utc_now_rfc3339(),
                    "items": [item.to_dict() for item in result.data.items],
                }
            )
            slot += 1
    except asyncio.CancelledError:
        raise
    except Exception:
        return OperationResult.failure(
            _OPERATION,
            "DEBUG_SAMPLE_FAILED",
            "Finite sampling failed",
            {},
        )

    if len(actual_offsets) > 1 and actual_offsets[-1] > actual_offsets[0]:
        actual_rate = (len(actual_offsets) - 1) / (
            actual_offsets[-1] - actual_offsets[0]
        )
    else:
        actual_rate = 0.0
    return OperationResult.success(
        _OPERATION,
        SampleReport(
            typed.binding,
            typed.interval_ms,
            applied_ms,
            tuple(samples),
            float(actual_rate),
            deadline_misses,
            dropped,
        ),
    )


__all__ = ["SampleVariablesRequest", "sample_variables"]
