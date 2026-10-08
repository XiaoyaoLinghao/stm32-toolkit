"""Offline recovery refusal and pure acceptance value contracts.

The final test is an internal-pure-unit check.  Its model values are syntax
examples, not authenticated evidence or proof of a public physical journey.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.acceptance.finalization import (
    FinalizationValidationError,
    PhysicalFinalizationProof,
)
from stm32_toolkit.acceptance.recovery import (
    AcceptanceRecoveryValidationError,
    SourceChangeIntent,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    _canonical_hash,
    _canonical_utc,
    _canonical_uuid,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    show_acceptance_attempt,
)
from test_acceptance_finalization import _finalization_proof_wire
from test_risk_recovery_public_producers import (
    ATTEMPT_ID,
    _assert_failure,
    _persistence_snapshot,
    _prepare_prefix,
)


SCENARIO = {"scenario_id": "legacy-keil-migration", "scenario_version": "1"}


def _begin(context: object) -> object:
    return begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, **SCENARIO)


def test_public_recovery_context_refusals_preserve_real_attempt(tmp_path: Path) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=False)
    context = replace(prefix.context, clock=lambda: "2026-10-08T03:00:00.000000Z")
    opened = _begin(context)
    assert opened.ok is True, opened.to_dict()
    assert opened.to_dict()["data"]["attempt"]["revision"] == 0
    baseline = _persistence_snapshot(prefix.project_root, prefix.data_root)

    for invalid in (
        None,
        replace(context, project_root="project"),
        replace(context, session_id="../escape"),
    ):
        refused = _begin(invalid)
        _assert_failure(
            refused,
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
            operation="acceptance.attempt.begin",
        )
        assert _persistence_snapshot(prefix.project_root, prefix.data_root) == baseline

    shown = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert shown.ok is True, shown.to_dict()
    assert shown.to_dict()["data"]["attempt"] == opened.to_dict()["data"]["attempt"]
    assert _begin(context).to_dict() == opened.to_dict()
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == baseline


def test_public_checkpoint_reference_shapes_refuse_before_write(tmp_path: Path) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=False)
    context = replace(prefix.context, clock=lambda: "2026-10-08T03:00:00.000000Z")
    opened = _begin(context)
    assert opened.ok is True, opened.to_dict()
    baseline = _persistence_snapshot(prefix.project_root, prefix.data_root)

    cases = (
        {"stage": "project-materialized", "test_run_id": ATTEMPT_ID},
        {"stage": "diagnosis-completed"},
        {"stage": "target-fix-verified"},
    )
    for case in cases:
        refused = checkpoint_acceptance_attempt(
            context, attempt_id=ATTEMPT_ID, expected_revision=0, **case
        )
        _assert_failure(
            refused,
            "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
            operation="acceptance.attempt.checkpoint",
        )
        assert _persistence_snapshot(prefix.project_root, prefix.data_root) == baseline

    accepted = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert accepted.ok is True, accepted.to_dict()
    assert accepted.to_dict()["data"]["attempt"]["revision"] == 1
    shown = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert shown.ok is True, shown.to_dict()
    assert shown.to_dict()["data"]["attempt"] == accepted.to_dict()["data"]["attempt"]


def test_internal_pure_recovery_and_finalization_value_guards() -> None:
    # internal-pure-unit: no store, authority, target, or public reachability claim.
    canonical_id = "123e4567-e89b-42d3-a456-426614174000"
    canonical_hash = "a" * 64
    canonical_time = "2026-10-08T03:00:00.000000Z"
    assert _canonical_uuid("attemptId", canonical_id) == canonical_id
    assert _canonical_hash("checkpointId", canonical_hash) == canonical_hash
    assert _canonical_utc("observedAt", canonical_time) == canonical_time

    for validator, value in (
        (_canonical_uuid, canonical_id.upper()),
        (_canonical_hash, canonical_hash.upper()),
        (_canonical_utc, "2026-10-08T03:00:00Z"),
    ):
        with pytest.raises(AcceptanceRecoveryValidationError):
            validator("value", value)

    proof = PhysicalFinalizationProof.from_value(_finalization_proof_wire())
    original = proof.to_dict()
    assert PhysicalFinalizationProof.from_value(original) == proof
    partial_intent = SourceChangeIntent.new(changes=original["sourceChangeIntent"]["changes"])
    for alteration, expected in (
        ({"diagnostic_revision": True}, "diagnosticRevision is invalid"),
        ({"source_change_intent": original["sourceChangeIntent"]}, "sourceChangeIntent is invalid"),
        ({"source_change_intent": partial_intent}, "sourceChangeIntent is not expanded"),
    ):
        with pytest.raises(FinalizationValidationError, match=expected):
            replace(proof, **alteration)
        assert proof.to_dict() == original
