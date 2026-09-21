from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType

import pytest
from stm32_toolkit.probe.attach_diagnostics import (
    CleanupFragment,
    append_cleanup,
    append_late_attach,
    attach_details,
    extract_attach_diagnostic,
    legacy_stage_for_primary,
    legacy_stage_matches_attach_diagnostic,
    make_attach_diagnostic,
    make_cleanup_entry,
    make_primary,
    primary_stage_from_legacy,
    promote_legacy_details,
    update_last_verified_target_state,
    validate_attach_diagnostic,
)


def _diagnostic(
    stage: str = "session-open",
    *,
    cleanup: list[dict[str, object]] | None = None,
    state: str | None = None,
) -> dict[str, object]:
    return make_attach_diagnostic(
        make_primary(stage, "unknown", "UNTYPED"),
        cleanup=(
            [make_cleanup_entry("session-close", "succeeded")]
            if cleanup is None
            else cleanup
        ),
        last_verified_target_state=state,
    )


def _late_diagnostic() -> dict[str, object]:
    return {
        "primary": make_primary(
            "target-identity", "identity-mismatch", "PROBE_IDENTITY_MISMATCH"
        ),
        "cleanup": [make_cleanup_entry("service-identity-close", "succeeded")],
        "lastVerifiedTargetState": "running",
    }


def test_public_wire_rejection_is_detached_and_non_mutating() -> None:
    original = _diagnostic()
    baseline = deepcopy(original)

    malformed = [
        {
            **original,
            "cleanup": [
                {"stage": "session-close", "outcome": "succeeded", "extra": True}
            ],
        },
        {
            **original,
            "cleanup": [{"stage": "unknown-stage", "outcome": "succeeded"}],
        },
        {
            **original,
            "cleanup": [{"stage": "session-close", "outcome": "unknown"}],
        },
        {
            **original,
            "cleanup": [
                {"stage": "probe-close", "outcome": "succeeded"},
                {"stage": "session-close", "outcome": "succeeded"},
            ],
        },
    ]
    for candidate in malformed:
        snapshot = deepcopy(candidate)
        assert validate_attach_diagnostic(candidate) is None
        assert extract_attach_diagnostic({"attachDiagnostic": candidate}) is None
        assert candidate == snapshot
        assert original == baseline

    late = _late_diagnostic()
    invalid_late_scope = {
        **original,
        "lateAttach": {
            **late,
            "cleanup": [make_cleanup_entry("session-close", "succeeded")],
        },
    }
    invalid_late_duplicate = {
        **original,
        "lateAttach": {
            **late,
            "cleanup": [
                make_cleanup_entry("service-identity-close", "succeeded"),
                make_cleanup_entry("service-identity-close", "succeeded"),
            ],
        },
    }
    non_deadline_late = {**original, "lateAttach": late}
    for candidate in (invalid_late_scope, invalid_late_duplicate, non_deadline_late):
        snapshot = deepcopy(candidate)
        assert validate_attach_diagnostic(candidate) is None
        assert extract_attach_diagnostic({"attachDiagnostic": candidate}) is None
        assert candidate == snapshot
        assert original == baseline

    recursive: list[object] = []
    recursive.append(recursive)
    recursive_candidate = {**original, "cleanup": recursive}
    assert extract_attach_diagnostic({"attachDiagnostic": recursive_candidate}) is None
    assert original == baseline

    external_wire = {
        "version": original["version"],
        "primary": MappingProxyType(dict(original["primary"])),
        "lateAttach": None,
        "cleanup": (MappingProxyType(dict(original["cleanup"][0])),),
        "lastVerifiedTargetState": original["lastVerifiedTargetState"],
    }
    detached = extract_attach_diagnostic(
        {"attachDiagnostic": MappingProxyType(external_wire)}
    )
    assert detached == original
    assert detached is not original
    assert detached["primary"] is not original["primary"]
    detached["primary"]["stage"] = "session-create"
    assert original["primary"]["stage"] == "session-open"

    deadline = _diagnostic(
        "service-attach-deadline",
        cleanup=[make_cleanup_entry("service-terminal-wait", "succeeded")],
    )
    with_late = append_late_attach(deadline, late)
    assert with_late is not None
    assert with_late["primary"] == deadline["primary"]
    assert with_late["lateAttach"] == late
    assert deadline["lateAttach"] is None


def test_public_producers_merge_and_project_atomically() -> None:
    with pytest.raises(ValueError, match="attach diagnostic primary is invalid"):
        make_primary("not-a-primary-stage", "unknown", "UNTYPED")
    with pytest.raises(ValueError, match="attach diagnostic is invalid"):
        make_attach_diagnostic({"stage": "session-open"})
    with pytest.raises(
        ValueError, match="failed cleanup requires reason and sourceCode"
    ):
        make_cleanup_entry("probe-close", "failed")
    with pytest.raises(
        ValueError, match="successful cleanup cannot contain failure fields"
    ):
        make_cleanup_entry(
            "probe-close", "succeeded", reason="unknown", source_code="UNTYPED"
        )
    with pytest.raises(ValueError, match="attach diagnostic cleanup entry is invalid"):
        make_cleanup_entry("not-a-cleanup-stage", "succeeded")

    with pytest.raises(ValueError, match="cleanup fragment is invalid"):
        CleanupFragment.from_entries("invalid")
    with pytest.raises(ValueError, match="cleanup fragment is invalid"):
        CleanupFragment.from_entries(
            ({"stage": "session-close", "outcome": "succeeded"}, "invalid")
        )
    with pytest.raises(ValueError, match="cleanup fragment is invalid"):
        CleanupFragment.from_entries(
            (
                {"stage": "session-close", "outcome": "succeeded"},
                {"stage": "session-close", "outcome": "succeeded"},
            )
        )

    diagnostic = _diagnostic()
    valid_fragment = CleanupFragment.from_entries(
        (make_cleanup_entry("probe-close", "succeeded"),)
    )
    merged = append_cleanup(diagnostic, valid_fragment)
    assert merged is not None
    assert merged["primary"] == diagnostic["primary"]
    assert [item["stage"] for item in merged["cleanup"]] == [
        "session-close",
        "probe-close",
    ]
    assert diagnostic["cleanup"] == [{"stage": "session-close", "outcome": "succeeded"}]

    assert append_cleanup({"invalid": True}, valid_fragment) is None
    queue_diagnostic = _diagnostic("service-backend-queue", cleanup=[])
    queue_before = deepcopy(queue_diagnostic)
    out_of_scope = (make_cleanup_entry("candidate-resume", "succeeded"),)
    assert append_cleanup(queue_diagnostic, out_of_scope) == queue_diagnostic
    assert queue_diagnostic == queue_before
    duplicate_before = deepcopy(merged)
    assert (
        append_cleanup(merged, (make_cleanup_entry("probe-close", "succeeded"),))
        == merged
    )
    assert merged == duplicate_before

    deadline = _diagnostic("service-attach-deadline", cleanup=[])
    late = _late_diagnostic()
    assert append_late_attach({"invalid": True}, late) is None
    accepted_late = append_late_attach(deadline, late)
    assert accepted_late is not None
    assert append_late_attach(accepted_late, late) == accepted_late

    updated = update_last_verified_target_state(diagnostic, "halted")
    assert updated is not None
    assert updated["lastVerifiedTargetState"] == "halted"
    assert update_last_verified_target_state(updated, "not-a-target-state") == updated
    assert update_last_verified_target_state({"invalid": True}, "halted") is None

    assert legacy_stage_for_primary("target-resolve-before-open") == "target-resolve"
    assert legacy_stage_for_primary("target-resolve-after-open") == "target-resolve"
    assert legacy_stage_for_primary("resume") is None
    assert primary_stage_from_legacy("target-resolve") == "target-resolve-after-open"
    assert primary_stage_from_legacy("cleanup-resume") == "resume"
    assert primary_stage_from_legacy("not-a-legacy-stage") is None

    assert legacy_stage_matches_attach_diagnostic("session-open", diagnostic) is True
    assert (
        legacy_stage_matches_attach_diagnostic("not-a-legacy-stage", diagnostic)
        is False
    )
    assert (
        legacy_stage_matches_attach_diagnostic("session-open", {"invalid": True})
        is False
    )
    cleanup_resume = _diagnostic(
        cleanup=[
            make_cleanup_entry(
                "candidate-resume",
                "failed",
                reason="backend-code",
                source_code="PROBE_BACKEND_ERROR",
            )
        ]
    )
    assert (
        legacy_stage_matches_attach_diagnostic("cleanup-resume", cleanup_resume) is True
    )
    assert legacy_stage_matches_attach_diagnostic("cleanup-resume", diagnostic) is False

    promoted = promote_legacy_details({"stage": "session-open"})
    assert promoted is not None
    assert promoted["primary"] == make_primary(
        "session-open", "backend-code", "PROBE_ATTACH_FAILED"
    )
    assert promote_legacy_details({"stage": "not-a-legacy-stage"}) is None

    projected = attach_details(diagnostic, legacy_stage="session-open")
    assert projected == {"stage": "session-open", "attachDiagnostic": diagnostic}
    assert attach_details(diagnostic, legacy_stage="not-a-legacy-stage") == {
        "attachDiagnostic": diagnostic
    }
    assert attach_details({"invalid": True}) == {}
