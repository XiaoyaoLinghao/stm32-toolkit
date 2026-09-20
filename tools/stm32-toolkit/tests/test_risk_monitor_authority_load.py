"""Persisted software fixtures only: these tests never access physical hardware."""

import json
from pathlib import Path

import pytest
from stm32_toolkit.acceptance import recovery_workflows
from stm32_toolkit.diagnostic_workflows import (
    diagnostic_add_plan,
    diagnostic_assess_hypothesis,
    diagnostic_run_plan,
    diagnostic_show,
)
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DiagnosticValidationError,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from test_continuation_monitor import (
    _ok,
    _supplementary_physical_fact_fixture,
)


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Capture every regular file under one diagnostic or evidence tree."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _diagnostic_evidence_snapshot(fixture: object) -> dict[str, bytes]:
    pair = fixture.pair
    snapshot: dict[str, bytes] = {}
    for prefix, root in (
        ("diagnostics", pair.workspace.diagnostics_root),
        ("evidence", pair.evidence.root),
    ):
        snapshot.update(
            {
                f"{prefix}/{relative}": raw
                for relative, raw in _tree_snapshot(root).items()
            }
        )
    return snapshot


def _different_digest(previous: object) -> str:
    assert isinstance(previous, str)
    for candidate in ("0" * 64, "1" * 64, "2" * 64):
        if candidate != previous:
            return candidate
    raise AssertionError("the prior digest unexpectedly matches every replacement")


def _assert_valid_v2_session(fixture: object, store: DiagnosticStore) -> dict[str, object]:
    loaded = store.load(fixture.diagnostic_session_id)
    assert loaded.revision == 6
    assert loaded.observation_results[0].observed_value == 3
    assert loaded.observation_results[0].selector["kind"] == "physical-monitor-fact/2"
    assert loaded.observation_results[0].evidence_id == fixture.refs[0].transcript_evidence_id

    shown = _ok(
        diagnostic_show(
            fixture.pair.diagnostic,
            diagnostic_session_id=fixture.diagnostic_session_id,
        )
    )
    assert shown["session"]["revision"] == 6
    assert shown["session"]["observation_results"][0]["observed_value"] == 3
    assert (
        shown["session"]["observation_results"][0]["evidence_id"]
        == fixture.refs[0].transcript_evidence_id
    )
    return shown


@pytest.mark.parametrize(
    ("root_type", "field", "replacement"),
    [
        pytest.param(
            "monitor-run-ref",
            "scenario_role",
            "fixed-after",
            id="monitor-run-ref-scenario-role",
        ),
        pytest.param(
            "monitor-run-ref",
            "source_record_sha256",
            "0" * 64,
            id="monitor-run-ref-source-record",
        ),
        pytest.param(
            "monitor-run-ref",
            "origin_workspace_id",
            "tampered-workspace",
            id="monitor-run-ref-origin-workspace",
        ),
        pytest.param(
            "monitor-run-ref",
            "run_ref_sha256",
            None,
            id="monitor-run-ref-run-ref-digest",
        ),
        pytest.param(
            "monitor-run",
            "source_record_sha256",
            "0" * 64,
            id="monitor-run-source-record",
        ),
        pytest.param(
            "monitor-run",
            "run_ref_sha256",
            None,
            id="monitor-run-run-ref-digest",
        ),
    ],
)
def test_fresh_diagnostic_monitor_root_metadata_corruption_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_type: str,
    field: str,
    replacement: str | None,
) -> None:
    """Fresh Diagnostic readers reject six Monitor authority mutations read-only."""

    fixture = _supplementary_physical_fact_fixture(tmp_path, monkeypatch)
    selector = dict(fixture.selectors[0])
    selector["kind"] = "physical-monitor-fact/2"
    selector.pop("continuation_evidence_id")
    plan = _ok(
        diagnostic_add_plan(
            fixture.pair.diagnostic,
            operation_id="authority-load-plan",
            diagnostic_session_id=fixture.diagnostic_session_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "physical-register-fact-v2",
                    "selector": selector,
                    "expected_value": 3,
                    "purpose": "verify the current failed-before physical register bit",
                }
            ],
        )
    )["observation_plan"]
    plan_id = str(plan["plan_id"])
    run = _ok(
        diagnostic_run_plan(
            fixture.pair.diagnostic,
            operation_id="authority-load-run",
            diagnostic_session_id=fixture.diagnostic_session_id,
            expected_revision=4,
            plan_id=plan_id,
        )
    )
    assert run["observation_results"][0]["observed_value"] == 3
    assert run["observation_results"][0]["evidence_id"] == fixture.refs[0].transcript_evidence_id
    assessed = _ok(
        diagnostic_assess_hypothesis(
            fixture.pair.diagnostic,
            operation_id="authority-load-assess",
            diagnostic_session_id=fixture.diagnostic_session_id,
            expected_revision=5,
            hypothesis_id=fixture.hypothesis_id,
            plan_id=plan_id,
            step_id="physical-register-fact-v2",
            polarity="supports",
            rationale="the current failed-before physical samples contain both bit values",
        )
    )
    assert assessed["assessment"]["evidence_id"] == fixture.refs[0].transcript_evidence_id

    fresh_store = DiagnosticStore(
        fixture.pair.workspace.diagnostics_root,
        EvidenceStore(fixture.pair.evidence.root),
    )
    baseline_show = _assert_valid_v2_session(fixture, fresh_store)
    baseline_snapshot = _diagnostic_evidence_snapshot(fixture)

    operation_id = str(fixture.refs[0].operation_id)
    root_path = recovery_workflows._typed_root_path(
        fixture.pair.evidence,
        operation_id,
        root_type,
    )
    original_root = root_path.read_bytes()
    try:
        document = json.loads(original_root.decode("utf-8"))
        assert isinstance(document, dict)
        metadata = document.get("metadata")
        assert isinstance(metadata, dict)
        original_value = metadata.get(field)
        if replacement is None:
            replacement = _different_digest(original_value)
        assert original_value != replacement
        metadata[field] = replacement
        mutated_root = canonical_json_bytes(document)
        assert mutated_root != original_root
        root_path.write_bytes(mutated_root)

        injected_snapshot = _diagnostic_evidence_snapshot(fixture)
        assert injected_snapshot != baseline_snapshot

        with pytest.raises(DiagnosticValidationError) as raised:
            fresh_store.load(fixture.diagnostic_session_id)
        assert raised.value.code == DIAGNOSTIC_CHAIN_CORRUPT
        assert _diagnostic_evidence_snapshot(fixture) == injected_snapshot

        shown = diagnostic_show(
            fixture.pair.diagnostic,
            diagnostic_session_id=fixture.diagnostic_session_id,
        )
        assert shown.ok is False
        assert shown.code == DIAGNOSTIC_CHAIN_CORRUPT
        assert _diagnostic_evidence_snapshot(fixture) == injected_snapshot

        assert fresh_store.load_durable(fixture.diagnostic_session_id).revision == 6
        assert _diagnostic_evidence_snapshot(fixture) == injected_snapshot
    finally:
        root_path.write_bytes(original_root)

    assert root_path.read_bytes() == original_root
    assert _assert_valid_v2_session(fixture, fresh_store) == baseline_show
    assert _diagnostic_evidence_snapshot(fixture) == baseline_snapshot
