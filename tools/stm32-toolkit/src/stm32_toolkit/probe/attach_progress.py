"""Closed, bounded attach stage progress evidence.

This module is intentionally independent of the backend, worker, service and
public workflow layers so every producer can share one small vocabulary without
introducing a dependency cycle.  It owns only the public snapshot schema and the
pure validation/copy helpers; parent-receipt timestamps and private request
tokens stay in the worker and service layers.
"""

from __future__ import annotations

PROGRESS_VERSION = 1
PROGRESS_CLOCK = "parent-receipt"
MAX_PROGRESS_ELAPSED_MS = 600_000

# Closed ordered vocabulary.  ``worker-dispatch`` is created by the parent after
# a successful request send; every later stage is an ordered subsequence.
PROGRESS_STAGES: tuple[str, ...] = (
    "worker-dispatch",
    "driver-acquire",
    "probe-enumeration",
    "prior-attachment-close",
    "session-create",
    "target-resolve-before-open",
    "session-open",
    "target-resolve-after-open",
    "target-identity",
    "halt-verify",
    "resume",
    "resume-verify",
)
STAGE_INDEX: dict[str, int] = {
    stage: index for index, stage in enumerate(PROGRESS_STAGES)
}
HALT_STAGE = "halt-verify"
RESUME_STAGES = ("resume", "resume-verify")
_MAX_EVENTS = len(PROGRESS_STAGES)


def _exact_dict(value: object) -> bool:
    return type(value) is dict


def _exact_list(value: object) -> bool:
    return type(value) is list


def _exact_string(value: object) -> bool:
    return type(value) is str


def _valid_milliseconds(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_PROGRESS_ELAPSED_MS


def validate_attach_progress(value: object) -> dict[str, object] | None:
    """Return a detached copy of an exact valid progress snapshot, or ``None``."""

    if not _exact_dict(value) or set(value) != {
        "version", "clock", "elapsedMs", "events"
    }:
        return None
    if (
        type(value["version"]) is not int
        or value["version"] != PROGRESS_VERSION
        or not _exact_string(value["clock"])
        or value["clock"] != PROGRESS_CLOCK
        or not _valid_milliseconds(value["elapsedMs"])
        or not _exact_list(value["events"])
    ):
        return None
    entries = value["events"]
    if not 1 <= len(entries) <= _MAX_EVENTS:
        return None
    elapsed_ms = value["elapsedMs"]
    copied: list[dict[str, object]] = []
    seen: set[str] = set()
    previous_index = -1
    previous_ms = -1
    for entry in entries:
        if not _exact_dict(entry) or set(entry) != {"stage", "elapsedMs"}:
            return None
        stage = entry["stage"]
        milliseconds = entry["elapsedMs"]
        if (
            not _exact_string(stage)
            or stage not in STAGE_INDEX
            or not _valid_milliseconds(milliseconds)
            or milliseconds > elapsed_ms
            or milliseconds < previous_ms
        ):
            return None
        index = STAGE_INDEX[stage]
        if index <= previous_index:
            return None
        previous_index = index
        previous_ms = milliseconds
        seen.add(stage)
        copied.append({"stage": stage, "elapsedMs": milliseconds})
    if copied[0] != {"stage": "worker-dispatch", "elapsedMs": 0}:
        return None
    if HALT_STAGE in seen and RESUME_STAGES[0] in seen:
        return None
    if RESUME_STAGES[1] in seen and RESUME_STAGES[0] not in seen:
        return None
    return {
        "version": PROGRESS_VERSION,
        "clock": PROGRESS_CLOCK,
        "elapsedMs": elapsed_ms,
        "events": copied,
    }


def make_attach_progress(
    events: object, elapsed_ms: object
) -> dict[str, object]:
    """Build a validated snapshot from parent-receipt events."""

    candidate = {
        "version": PROGRESS_VERSION,
        "clock": PROGRESS_CLOCK,
        "elapsedMs": elapsed_ms,
        "events": events,
    }
    valid = validate_attach_progress(candidate)
    if valid is None:
        raise ValueError("attach progress is invalid")
    return valid


__all__ = [
    "HALT_STAGE",
    "MAX_PROGRESS_ELAPSED_MS",
    "PROGRESS_CLOCK",
    "PROGRESS_STAGES",
    "PROGRESS_VERSION",
    "RESUME_STAGES",
    "STAGE_INDEX",
    "make_attach_progress",
    "validate_attach_progress",
]
