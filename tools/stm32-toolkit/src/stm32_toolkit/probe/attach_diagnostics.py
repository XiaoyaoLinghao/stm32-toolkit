"""Closed, non-recursive diagnostics for probe attachment failures.

This module is deliberately independent of the backend, worker, service, and
public workflow layers.  It owns the wire-safe vocabulary and the small set of
pure operations used to construct and merge an attach diagnostic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


PRIMARY_STAGES = frozenset(
    {
        "prior-attachment-close",
        "session-create",
        "target-resolve-before-open",
        "session-open",
        "target-resolve-after-open",
        "target-identity",
        "halt-verify",
        "resume",
        "resume-verify",
        "service-backend-queue",
        "service-target-identity",
        "service-attach-deadline",
        "service-attach-cancelled",
    }
)
BACKEND_PRIMARY_STAGES = frozenset(
    {
        "prior-attachment-close",
        "session-create",
        "target-resolve-before-open",
        "session-open",
        "target-resolve-after-open",
        "target-identity",
        "halt-verify",
        "resume",
        "resume-verify",
    }
)
LEGACY_ATTACH_STAGES = frozenset(
    {
        "session-create",
        "session-open",
        "target-resolve",
        "halt-verify",
        "resume",
        "resume-verify",
        "cleanup-resume",
    }
)

BACKEND_CLEANUP_STAGES = (
    "candidate-resume",
    "candidate-resume-verify",
    "session-close",
    "probe-open-check-before-close",
    "probe-close",
    "probe-open-check-after-close",
    "worker-parent-abort",
)
IDENTITY_CLEANUP_STAGES = (
    "service-identity-resume",
    "service-identity-resume-verify",
    "service-identity-close",
)
SERVICE_OUTER_CLEANUP_STAGES = (
    "service-terminal-wait",
    "service-worker-abort",
    "service-late-resume",
    "service-late-resume-verify",
    "service-late-close",
    "service-runner-cleanup",
    "service-stop-backend-close",
    "service-lease-release",
    "workflow-client-close",
    "workflow-service-stop",
    "monitor-client-close",
    "monitor-service-stop",
    "monitor-root-guard-close",
)
CLEANUP_STAGES = frozenset(
    BACKEND_CLEANUP_STAGES + IDENTITY_CLEANUP_STAGES + SERVICE_OUTER_CLEANUP_STAGES
)

REASONS = frozenset(
    {
        "backend-code",
        "permission-denied",
        "probe-disconnected",
        "probe-io",
        "transport-timeout",
        "transport-protocol",
        "transport-fault",
        "transport-error",
        "target-unsupported",
        "target-response",
        "target-register",
        "debug-command",
        "debug-operation",
        "backend-internal",
        "timeout",
        "postcondition-failed",
        "identity-mismatch",
        "cancelled",
        "unknown",
    }
)

# Keep this list closed and independent from worker.py.  It is the source of
# truth for the public diagnostic sourceCode field.
SOURCE_CODES = frozenset(
    {
        "UNTYPED",
        "CALLER_CANCELLED",
        "PROBE_ATTACH_FAILED",
        "PROBE_BACKEND_ERROR",
        "PROBE_BACKEND_UNAVAILABLE",
        "PROBE_BACKPRESSURE",
        "PROBE_CLOSE_FAILED",
        "PROBE_CONTROL_FAILED",
        "PROBE_DESCRIPTOR_INVALID",
        "PROBE_ENUMERATION_FAILED",
        "PROBE_IDENTITY_MISMATCH",
        "PROBE_LIMIT_EXCEEDED",
        "PROBE_NOT_ATTACHED",
        "PROBE_NOT_FOUND",
        "PROBE_OPERATION_LEVEL_DENIED",
        "PROBE_OPERATION_UNAVAILABLE",
        "PROBE_PARTIAL_READ",
        "PROBE_PROGRAM_FAILED",
        "PROBE_PROGRAM_INVALID",
        "PROBE_PROTOCOL_INVALID",
        "PROBE_READ_INVALID",
        "PROBE_READ_UNAVAILABLE",
        "PROBE_REGISTER_INVALID",
        "PROBE_REGISTER_UNAVAILABLE",
        "PROBE_SELECTION_AMBIGUOUS",
        "PROBE_SELECTION_REQUIRED",
        "PROBE_TARGET_AMBIGUOUS",
        "PROBE_TARGET_IDENTITY_UNAVAILABLE",
        "PROBE_TARGET_INVALID",
        "PROBE_TARGET_UNAVAILABLE",
        "PROBE_TIMEOUT",
    }
)
TARGET_STATES = frozenset({None, "running", "halted", "reset", "faulted"})
OUTCOMES = frozenset({"succeeded", "failed", "timed-out"})
_DEADLINE_PRIMARY_STAGES = frozenset(
    {"service-attach-deadline", "service-attach-cancelled"}
)
_SERVICE_STOP_CLEANUP_STAGES = frozenset(
    {"service-runner-cleanup", "service-stop-backend-close", "service-lease-release"}
)
_WORKFLOW_CLEANUP_STAGES = frozenset({"workflow-client-close", "workflow-service-stop"})
_MONITOR_CLEANUP_STAGES = frozenset(
    {"monitor-client-close", "monitor-service-stop", "monitor-root-guard-close"}
)
_LATER_OUTER_CLEANUP_STAGES = frozenset(
    _SERVICE_STOP_CLEANUP_STAGES | _WORKFLOW_CLEANUP_STAGES | _MONITOR_CLEANUP_STAGES
)
_SERVICE_LATE_CLEANUP_STAGES = frozenset(SERVICE_OUTER_CLEANUP_STAGES[:5])
_SERVICE_LATE_CLEANUP_ORDER = SERVICE_OUTER_CLEANUP_STAGES[:5]
_SERVICE_STOP_CLEANUP_ORDER = SERVICE_OUTER_CLEANUP_STAGES[5:8]
_WORKFLOW_CLEANUP_ORDER = SERVICE_OUTER_CLEANUP_STAGES[8:10]
_MONITOR_CLEANUP_ORDER = SERVICE_OUTER_CLEANUP_STAGES[10:13]

# Cleanup lists may contain nested producer groups.  The groups retain their
# own execution order while the enclosing layers interleave them (for example,
# a workflow closes its client, then receives the service-stop fragment, then
# records workflow-service-stop).  There is intentionally no invented global
# order between these groups.
_CLEANUP_ORDER_GROUPS = (
    BACKEND_CLEANUP_STAGES,
    IDENTITY_CLEANUP_STAGES,
    _SERVICE_LATE_CLEANUP_ORDER,
    _SERVICE_STOP_CLEANUP_ORDER,
    _WORKFLOW_CLEANUP_ORDER,
    _MONITOR_CLEANUP_ORDER,
)
_FRAGMENT_STAGE_SCOPES = (
    frozenset(BACKEND_CLEANUP_STAGES),
    frozenset(IDENTITY_CLEANUP_STAGES),
    _SERVICE_LATE_CLEANUP_STAGES,
    _SERVICE_STOP_CLEANUP_STAGES,
    _SERVICE_STOP_CLEANUP_STAGES | _WORKFLOW_CLEANUP_STAGES,
    _SERVICE_STOP_CLEANUP_STAGES | _MONITOR_CLEANUP_STAGES,
)


def _exact_dict(value: object) -> bool:
    return type(value) is dict


def _exact_list(value: object) -> bool:
    return type(value) is list


def _exact_string(value: object, allowed: frozenset[str]) -> bool:
    return type(value) is str and value in allowed


def _valid_target_state(value: object) -> bool:
    return value is None or (type(value) is str and value in TARGET_STATES)


def _cleanup_groups_are_ordered(entries: Iterable[Mapping[str, object]]) -> bool:
    """Check each producer group's relative order without imposing a global order."""

    stages = [entry.get("stage") for entry in entries]
    for group in _CLEANUP_ORDER_GROUPS:
        previous = -1
        for stage in stages:
            if stage not in group:
                continue
            index = group.index(stage)
            if index <= previous:
                return False
            previous = index
    return True


def _cleanup_scope_is_ordered(
    entries: Iterable[Mapping[str, object]], allowed_order: tuple[str, ...]
) -> bool:
    """Check the single local scope used by a late attach diagnostic."""

    previous = -1
    for entry in entries:
        stage = entry.get("stage")
        if stage not in allowed_order:
            return False
        index = allowed_order.index(stage)
        if index <= previous:
            return False
        previous = index
    return True


def _cleanup_scope(primary_stage: str) -> frozenset[str]:
    if primary_stage in _DEADLINE_PRIMARY_STAGES:
        return frozenset(SERVICE_OUTER_CLEANUP_STAGES)
    if primary_stage in BACKEND_PRIMARY_STAGES:
        return frozenset(BACKEND_CLEANUP_STAGES) | _LATER_OUTER_CLEANUP_STAGES
    if primary_stage == "service-target-identity":
        return frozenset(IDENTITY_CLEANUP_STAGES) | _LATER_OUTER_CLEANUP_STAGES
    if primary_stage == "service-backend-queue":
        return _LATER_OUTER_CLEANUP_STAGES
    return frozenset()


def _validate_primary(value: object) -> bool:
    return (
        _exact_dict(value)
        and set(value) == {"stage", "reason", "sourceCode"}
        and _exact_string(value["stage"], PRIMARY_STAGES)
        and _exact_string(value["reason"], REASONS)
        and _exact_string(value["sourceCode"], SOURCE_CODES)
    )


def _validate_cleanup_entry(value: object) -> bool:
    if not _exact_dict(value) or set(value) - {"stage", "outcome", "reason", "sourceCode"}:
        return False
    if not _exact_string(value.get("stage"), CLEANUP_STAGES):
        return False
    if not _exact_string(value.get("outcome"), OUTCOMES):
        return False
    if value["outcome"] == "succeeded":
        return set(value) == {"stage", "outcome"}
    return (
        set(value) == {"stage", "outcome", "reason", "sourceCode"}
        and _exact_string(value["reason"], REASONS)
        and _exact_string(value["sourceCode"], SOURCE_CODES)
    )


def _validate_late_attach(value: object) -> bool:
    if not _exact_dict(value) or set(value) != {
        "primary", "cleanup", "lastVerifiedTargetState"
    }:
        return False
    primary = value["primary"]
    cleanup = value["cleanup"]
    if (
        not _validate_primary(primary)
        or primary["stage"] not in BACKEND_PRIMARY_STAGES | {"service-target-identity"}
        or not _exact_list(cleanup)
        or len(cleanup) > len(BACKEND_CLEANUP_STAGES) + len(IDENTITY_CLEANUP_STAGES)
        or not _valid_target_state(value["lastVerifiedTargetState"])
    ):
        return False
    allowed_order = (
        BACKEND_CLEANUP_STAGES
        if primary["stage"] in BACKEND_PRIMARY_STAGES
        else IDENTITY_CLEANUP_STAGES
    )
    allowed = frozenset(allowed_order)
    stages: set[str] = set()
    for entry in cleanup:
        if not _validate_cleanup_entry(entry) or entry["stage"] not in allowed:
            return False
        if entry["stage"] in stages:
            return False
        stages.add(entry["stage"])
    if not _cleanup_scope_is_ordered(cleanup, allowed_order):
        return False
    return True


def validate_attach_diagnostic(
    value: object,
    *,
    worker: bool = False,
) -> dict[str, object] | None:
    """Return a detached copy when *value* is an exact valid diagnostic."""

    if not _exact_dict(value) or set(value) != {
        "version", "primary", "lateAttach", "cleanup", "lastVerifiedTargetState"
    }:
        return None
    if (
        type(value["version"]) is not int
        or value["version"] != 1
        or not _validate_primary(value["primary"])
        or not _exact_list(value["cleanup"])
        or not _valid_target_state(value["lastVerifiedTargetState"])
    ):
        return None
    primary_stage = value["primary"]["stage"]
    late = value["lateAttach"]
    if late is not None and not _validate_late_attach(late):
        return None
    if late is not None and primary_stage not in _DEADLINE_PRIMARY_STAGES:
        return None
    if worker and (late is not None or primary_stage not in BACKEND_PRIMARY_STAGES):
        return None

    allowed = _cleanup_scope(primary_stage)
    stages: set[str] = set()
    cleanup: list[dict[str, object]] = []
    for entry in value["cleanup"]:
        if (
            not _validate_cleanup_entry(entry)
            or entry["stage"] not in allowed
            or (worker and entry["stage"] not in BACKEND_CLEANUP_STAGES[:-1])
        ):
            return None
        stage = entry["stage"]
        if stage in stages:
            return None
        stages.add(stage)
        cleanup.append(dict(entry))
    if not _cleanup_groups_are_ordered(cleanup):
        return None
    if len(cleanup) > len(allowed):
        return None

    late_copy: dict[str, object] | None = None
    if late is not None:
        late_copy = {
            "primary": dict(late["primary"]),
            "cleanup": [dict(item) for item in late["cleanup"]],
            "lastVerifiedTargetState": late["lastVerifiedTargetState"],
        }
        for item in late_copy["cleanup"]:
            if item["stage"] in stages:
                return None
            stages.add(item["stage"])
        late_order = (
            BACKEND_CLEANUP_STAGES
            if late_copy["primary"]["stage"] in BACKEND_PRIMARY_STAGES
            else IDENTITY_CLEANUP_STAGES
        )
        if not _cleanup_scope_is_ordered(late_copy["cleanup"], late_order):
            return None
    if len(stages) > len(CLEANUP_STAGES):
        return None
    return {
        "version": 1,
        "primary": dict(value["primary"]),
        "lateAttach": late_copy,
        "cleanup": cleanup,
        "lastVerifiedTargetState": value["lastVerifiedTargetState"],
    }


def make_primary(stage: str, reason: str, source_code: str) -> dict[str, str]:
    value = {"stage": stage, "reason": reason, "sourceCode": source_code}
    if not _validate_primary(value):
        raise ValueError("attach diagnostic primary is invalid")
    return value


def make_cleanup_entry(
    stage: str,
    outcome: str,
    *,
    reason: str | None = None,
    source_code: str | None = None,
) -> dict[str, str]:
    value: dict[str, str] = {"stage": stage, "outcome": outcome}
    if outcome != "succeeded":
        if reason is None or source_code is None:
            raise ValueError("failed cleanup requires reason and sourceCode")
        value.update(reason=reason, sourceCode=source_code)
    elif reason is not None or source_code is not None:
        raise ValueError("successful cleanup cannot contain failure fields")
    if not _validate_cleanup_entry(value):
        raise ValueError("attach diagnostic cleanup entry is invalid")
    return value


def legacy_stage_for_primary(stage: str) -> str | None:
    if stage in LEGACY_ATTACH_STAGES:
        return stage
    if stage in {"target-resolve-before-open", "target-resolve-after-open", "target-identity"}:
        return "target-resolve"
    return None


def primary_stage_from_legacy(stage: str) -> str | None:
    if stage == "target-resolve":
        return "target-resolve-after-open"
    if stage in LEGACY_ATTACH_STAGES - {"cleanup-resume"}:
        return stage
    if stage == "cleanup-resume":
        return "resume"
    return None


def legacy_stage_matches_attach_diagnostic(
    stage: object,
    diagnostic: object,
    *,
    worker: bool = False,
) -> bool:
    """Validate the frozen compatibility projection for a paired envelope."""

    if type(stage) is not str or stage not in LEGACY_ATTACH_STAGES:
        return False
    valid = validate_attach_diagnostic(diagnostic, worker=worker)
    if valid is None:
        return False
    if stage == "cleanup-resume":
        return any(
            entry["stage"] in {"candidate-resume", "candidate-resume-verify"}
            and entry["outcome"] in {"failed", "timed-out"}
            for entry in valid["cleanup"]
        )
    return legacy_stage_for_primary(valid["primary"]["stage"]) == stage


def make_attach_diagnostic(
    primary: Mapping[str, object],
    *,
    cleanup: Iterable[Mapping[str, object]] = (),
    last_verified_target_state: str | None = None,
    late_attach: Mapping[str, object] | None = None,
) -> dict[str, object]:
    value = {
        "version": 1,
        "primary": dict(primary),
        "lateAttach": None if late_attach is None else dict(late_attach),
        "cleanup": [dict(item) for item in cleanup],
        "lastVerifiedTargetState": last_verified_target_state,
    }
    valid = validate_attach_diagnostic(value)
    if valid is None:
        raise ValueError("attach diagnostic is invalid")
    return valid


def promote_legacy_details(details: object) -> dict[str, object] | None:
    """Promote one accepted legacy ``stage`` detail to a closed diagnostic."""

    if not _exact_dict(details) or set(details) != {"stage"}:
        return None
    stage = details["stage"]
    precise = primary_stage_from_legacy(stage) if type(stage) is str else None
    if precise is None:
        return None
    return make_attach_diagnostic(
        make_primary(precise, "backend-code", "PROBE_ATTACH_FAILED")
    )


def extract_attach_diagnostic(details: object) -> dict[str, object] | None:
    if type(details) not in {dict, MappingProxyType}:
        return None
    candidate = details.get("attachDiagnostic")
    if candidate is None:
        return None

    def thaw(value: object, active: frozenset[int] = frozenset()) -> object:
        if type(value) in {dict, MappingProxyType}:
            identity = id(value)
            if identity in active:
                raise ValueError("recursive attach diagnostic")
            next_active = active | {identity}
            return {key: thaw(item, next_active) for key, item in value.items()}
        if type(value) in {list, tuple}:
            identity = id(value)
            if identity in active:
                raise ValueError("recursive attach diagnostic")
            next_active = active | {identity}
            return [thaw(item, next_active) for item in value]
        return value

    try:
        return validate_attach_diagnostic(thaw(candidate))
    except (RecursionError, TypeError, ValueError):
        return None


def _fragment_entries(value: object) -> tuple[dict[str, object], ...] | None:
    if isinstance(value, CleanupFragment):
        return tuple(dict(item) for item in value.entries)
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return None
    result: list[dict[str, object]] = []
    try:
        for item in value:
            if not _exact_dict(item):
                return None
            result.append(dict(item))
    except (TypeError, ValueError):
        return None
    return tuple(result)


@dataclass(frozen=True)
class CleanupFragment:
    """Immutable ordered cleanup outcomes crossing an internal boundary."""

    entries: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        raw = _fragment_entries(self.entries)
        if raw is None:
            raise ValueError("cleanup fragment is invalid")
        seen: set[str] = set()
        frozen: list[Mapping[str, object]] = []
        for item in raw:
            stage = item.get("stage")
            if (
                not _validate_cleanup_entry(item)
                or stage in seen
                or type(stage) is not str
            ):
                raise ValueError("cleanup fragment is invalid")
            seen.add(stage)
            frozen.append(MappingProxyType(dict(item)))
        if raw and not any(
            frozenset(item["stage"] for item in raw) <= scope
            and _cleanup_groups_are_ordered(raw)
            for scope in _FRAGMENT_STAGE_SCOPES
        ):
            raise ValueError("cleanup fragment is invalid")
        object.__setattr__(self, "entries", tuple(frozen))

    @classmethod
    def from_entries(cls, entries: Iterable[Mapping[str, object]]) -> "CleanupFragment":
        return cls(tuple(entries))

    def to_list(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.entries]


def append_cleanup(
    diagnostic: object,
    incoming: CleanupFragment | Iterable[Mapping[str, object]],
) -> dict[str, object] | None:
    """Append a whole valid fragment, or retain the prior diagnostic unchanged."""

    current = validate_attach_diagnostic(diagnostic)
    entries = _fragment_entries(incoming)
    if current is None or entries is None:
        return current
    primary_stage = current["primary"]["stage"]
    allowed = _cleanup_scope(primary_stage)
    used = {
        item["stage"] for item in current["cleanup"]
    }
    late = current["lateAttach"]
    if late is not None:
        used.update(item["stage"] for item in late["cleanup"])
    candidate_entries: list[dict[str, object]] = []
    for item in entries:
        if (
            not _validate_cleanup_entry(item)
            or item["stage"] not in allowed
            or item["stage"] in used
            or item["stage"] in {entry["stage"] for entry in candidate_entries}
        ):
            return current
        candidate_entries.append(dict(item))
    candidate = dict(current)
    candidate["cleanup"] = [*current["cleanup"], *candidate_entries]
    merged = validate_attach_diagnostic(candidate)
    return merged if merged is not None else current


def append_late_attach(
    diagnostic: object,
    late_attach: object,
) -> dict[str, object] | None:
    current = validate_attach_diagnostic(diagnostic)
    if current is None:
        return None
    if current["lateAttach"] is not None or not _validate_late_attach(late_attach):
        return current
    candidate = dict(current)
    candidate["lateAttach"] = late_attach
    return validate_attach_diagnostic(candidate)


def update_last_verified_target_state(
    diagnostic: object,
    state: object,
) -> dict[str, object] | None:
    current = validate_attach_diagnostic(diagnostic)
    if current is None or type(state) is not str or state not in {
        "running", "halted", "reset", "faulted"
    }:
        return current
    candidate = dict(current)
    candidate["lastVerifiedTargetState"] = state
    return validate_attach_diagnostic(candidate)


def attach_details(
    diagnostic: object,
    *,
    legacy_stage: str | None = None,
) -> dict[str, object]:
    """Build the exact details envelope for a public attach failure."""

    valid = validate_attach_diagnostic(diagnostic)
    if valid is None:
        return {}
    result: dict[str, object] = {"attachDiagnostic": valid}
    if legacy_stage is not None and legacy_stage in LEGACY_ATTACH_STAGES:
        result = {"stage": legacy_stage, **result}
    return result


__all__ = [
    "BACKEND_CLEANUP_STAGES",
    "BACKEND_PRIMARY_STAGES",
    "CLEANUP_STAGES",
    "CleanupFragment",
    "IDENTITY_CLEANUP_STAGES",
    "LEGACY_ATTACH_STAGES",
    "PRIMARY_STAGES",
    "REASONS",
    "SERVICE_OUTER_CLEANUP_STAGES",
    "SOURCE_CODES",
    "append_cleanup",
    "append_late_attach",
    "attach_details",
    "extract_attach_diagnostic",
    "legacy_stage_for_primary",
    "legacy_stage_matches_attach_diagnostic",
    "make_attach_diagnostic",
    "make_cleanup_entry",
    "make_primary",
    "promote_legacy_details",
    "primary_stage_from_legacy",
    "update_last_verified_target_state",
    "validate_attach_diagnostic",
]
