from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import test_acceptance_continuation as continuation_fixture
import test_acceptance_physical_recovery as physical_fixture
from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import (
    INCOMPATIBLE_IDENTITY,
    AnalysisPublication,
    AnalysisWorkflowError,
    compare_monitor_runs,
)
from stm32_monitor.replay import (
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.acceptance.continuation import authenticate_continuation
from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
)
from stm32_toolkit.acceptance.recovery_workflows import begin_acceptance_attempt
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.testing.publication import TestRunPublisher

ORIGINAL_BEFORE_MONITOR_ID = "11111111-1111-4111-8111-111111111101"
ORIGINAL_AFTER_MONITOR_ID = "11111111-1111-4111-8111-111111111102"
ALIAS_BEFORE_MONITOR_ID = "11111111-1111-4111-8111-111111111121"
ALIAS_AFTER_MONITOR_ID = "11111111-1111-4111-8111-111111111122"
ALIAS_BEFORE_TEST_RUN_ID = "target-v2-alias-before-t10-cont"
ALIAS_AFTER_TEST_RUN_ID = "target-v2-alias-after-t10-cont"
CONTINUATION_ATTEMPT_ID = "00000000-0000-4000-8000-000000000111"


def _ok(result: object) -> dict[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    data = getattr(result, "data", None)
    assert isinstance(data, Mapping)
    return dict(data)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _publish_monitor_reference(
    fixture: object,
    *,
    workspace: object,
    identity: object,
    test_run_id: str,
    monitor_run_id: str,
    scenario_role: str,
    value_offset: int,
) -> object:
    published = fixture.repository.load(test_run_id)  # type: ignore[attr-defined]
    metadata = published.envelope.metadata
    batches = physical_fixture._append_physical_monitor_history(
        workspace,
        identity,
        physical_fixture.PHYSICAL_RAW_PROBE,
        str(metadata["flash_session_id"]),
        str(metadata["lease_id"]),
        monitor_run_id,
        value_offset=value_offset,
    )
    reference = publish_physical_monitor_run(
        workspace,
        fixture.evidence,  # type: ignore[attr-defined]
        scenario_role=scenario_role,
        test_run_id=test_run_id,
        run_id=monitor_run_id,
        group_id=str(batches[0].group_id),
        start_sequence=batches[0].sequence,
        end_sequence_exclusive=batches[-1].sequence + 1,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=physical_fixture.PHYSICAL_RAW_PROBE,
    )
    fresh = load_monitor_run_reference(
        workspace, fixture.evidence, monitor_run_id  # type: ignore[attr-defined]
    )
    assert fresh == reference
    assert fresh.origin_run_id == test_run_id
    return fresh


def _publish_test_run_alias(
    fixture: object,
    tmp_path: Path,
    *,
    source_run_id: str,
    alias_run_id: str,
) -> object:
    original = fixture.repository.load(source_run_id)  # type: ignore[attr-defined]
    manifest = replace(original.manifest, run_id=alias_run_id)
    manifest_path = tmp_path / f"{alias_run_id}-canonical-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = fixture.evidence.ingest_file(  # type: ignore[attr-defined]
        manifest_path,
        kind="test-manifest",
        media_type="application/json",
    )
    envelope = EvidenceEnvelope(
        identity=manifest.identity,
        operation=original.envelope.operation,
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, manifest.raw_events),
        metadata=dict(original.envelope.metadata),
    )
    fixture.evidence.put_envelope(envelope)  # type: ignore[attr-defined]
    TestRunPublisher(
        fixture.evidence,  # type: ignore[attr-defined]
        fixture.project_root,  # type: ignore[attr-defined]
        tmp_path / f"{alias_run_id}-results",
    ).publish_target_physical(manifest, envelope)
    fresh = fixture.repository.load(alias_run_id)  # type: ignore[attr-defined]
    assert fresh.manifest == manifest
    assert fresh.manifest.identity == original.manifest.identity
    assert fresh.manifest.cases == original.manifest.cases
    assert fresh.manifest.state == original.manifest.state
    assert fresh.manifest.transport == original.manifest.transport
    assert fresh.manifest.raw_events == original.manifest.raw_events
    assert fresh.envelope.metadata == original.envelope.metadata
    assert fresh.envelope.artifacts[1] == original.manifest.raw_events
    assert fixture.repository.load(source_run_id) == original  # type: ignore[attr-defined]
    return fresh


def _analysis_request(before: object, after: object) -> AnalysisRequest:
    request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=before,
        after_run=after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    )
    assert AnalysisRequest.from_value(request.to_dict()) == request
    assert request.watch_item.to_dict() == {
        "kind": "variable",
        "selector": "counter",
    }
    return request


def test_continuation_analysis_requires_the_original_published_testruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = continuation_fixture.prepare_pair(tmp_path, monkeypatch)

    bound = _ok(
        begin_acceptance_attempt(
            fixture.context,
            attempt_id=CONTINUATION_ATTEMPT_ID,
            scenario_id=PHYSICAL_SCENARIO_ID,
            scenario_version=PHYSICAL_SCENARIO_VERSION,
            continuation=deepcopy(fixture.bind_request),
        )
    )["attempt"]
    assert isinstance(bound, Mapping)
    continuation_evidence_id = str(bound["continuationEvidenceId"])
    association = authenticate_continuation(
        fixture.evidence,
        fixture.workspace.diagnostics_root,
        continuation_evidence_id,
        expected_workspace_id=fixture.workspace.workspace_id,
        expected_project_id=str(fixture.model.logical_project_id),
        expected_session_id=fixture.before_session_id,
        expected_fixed_after_test_run_id=fixture.fixed_run_id,
        expected_fixed_after_evidence_id=str(
            fixture.fixed_physical.envelope.evidence_id
        ),
    )
    assert association.proof.failed_before_test_run_id == fixture.failed_run_id
    assert association.proof.fixed_after_test_run_id == fixture.fixed_run_id
    assert association.diagnostic.declaration == fixture.declaration
    assert fixture.hypothesis_id in {
        hypothesis.hypothesis_id for hypothesis in fixture.diagnostic_session.hypotheses
    }

    original_before = _publish_monitor_reference(
        fixture,
        workspace=fixture.before_workspace,
        identity=fixture.before_identity,
        test_run_id=fixture.failed_run_id,
        monitor_run_id=ORIGINAL_BEFORE_MONITOR_ID,
        scenario_role="failed-before",
        value_offset=0,
    )
    original_after = _publish_monitor_reference(
        fixture,
        workspace=fixture.after_workspace,
        identity=fixture.after_identity,
        test_run_id=fixture.fixed_run_id,
        monitor_run_id=ORIGINAL_AFTER_MONITOR_ID,
        scenario_role="fixed-after",
        value_offset=10,
    )
    request = _analysis_request(original_before, original_after)
    original_test_runs = {
        fixture.failed_run_id: fixture.repository.load(fixture.failed_run_id),
        fixture.fixed_run_id: fixture.repository.load(fixture.fixed_run_id),
    }

    original_publication = compare_monitor_runs(
        fixture.workspace,
        fixture.evidence,
        request,
        fixture.diagnostic_session_id,
        fixture.hypothesis_id,
        "supports",
        "the failed physical run supports the hypothesis",
        fixture.declaration,
        continuation_evidence_id,
    )
    publication_wire = original_publication.to_dict()
    assert AnalysisPublication.from_value(publication_wire).to_dict() == publication_wire
    assert set(publication_wire) == {
        "schema",
        "analysis_result",
        "analysis_evidence_ref",
        "diagnostic_marker",
        "diagnostic_marker_ref",
    }
    result_wire = publication_wire["analysis_result"]
    assert isinstance(result_wire, Mapping)
    assert result_wire["before_run_id"] == original_before.run_ref_sha256
    assert result_wire["after_run_id"] == original_after.run_ref_sha256
    lineage = result_wire["identity"]
    assert isinstance(lineage, Mapping)
    assert lineage["continuation_evidence_id"] == continuation_evidence_id

    _publish_test_run_alias(
        fixture,
        tmp_path,
        source_run_id=fixture.failed_run_id,
        alias_run_id=ALIAS_BEFORE_TEST_RUN_ID,
    )
    _publish_test_run_alias(
        fixture,
        tmp_path,
        source_run_id=fixture.fixed_run_id,
        alias_run_id=ALIAS_AFTER_TEST_RUN_ID,
    )
    alias_before = _publish_monitor_reference(
        fixture,
        workspace=fixture.before_workspace,
        identity=fixture.before_identity,
        test_run_id=ALIAS_BEFORE_TEST_RUN_ID,
        monitor_run_id=ALIAS_BEFORE_MONITOR_ID,
        scenario_role="failed-before",
        value_offset=0,
    )
    alias_after = _publish_monitor_reference(
        fixture,
        workspace=fixture.after_workspace,
        identity=fixture.after_identity,
        test_run_id=ALIAS_AFTER_TEST_RUN_ID,
        monitor_run_id=ALIAS_AFTER_MONITOR_ID,
        scenario_role="fixed-after",
        value_offset=10,
    )

    combinations = (
        ("before-only", alias_before, original_after),
        ("after-only", original_before, alias_after),
        ("both", alias_before, alias_after),
    )
    for label, before, after in combinations:
        refusal_request = _analysis_request(before, after)
        authority_before = _tree_bytes(fixture.workspace.workspace_root)
        with pytest.raises(AnalysisWorkflowError) as error:
            compare_monitor_runs(
                fixture.workspace,
                fixture.evidence,
                refusal_request,
                fixture.diagnostic_session_id,
                fixture.hypothesis_id,
                "supports",
                "the failed physical run supports the hypothesis",
                fixture.declaration,
                continuation_evidence_id,
            )
        assert error.value.code == INCOMPATIBLE_IDENTITY, label
        assert error.value.message == "Monitor TestRuns differ from continuation", label
        assert _tree_bytes(fixture.workspace.workspace_root) == authority_before, label

        assert load_monitor_run_reference(
            fixture.before_workspace, fixture.evidence, before.operation_id
        ) == before
        assert load_monitor_run_reference(
            fixture.after_workspace, fixture.evidence, after.operation_id
        ) == after
        assert fixture.repository.load(before.origin_run_id).manifest.run_id == before.origin_run_id
        assert fixture.repository.load(after.origin_run_id).manifest.run_id == after.origin_run_id
        for run_id, expected in original_test_runs.items():
            assert fixture.repository.load(run_id) == expected

        still_original = compare_monitor_runs(
            fixture.workspace,
            fixture.evidence,
            request,
            fixture.diagnostic_session_id,
            fixture.hypothesis_id,
            "supports",
            "the failed physical run supports the hypothesis",
            fixture.declaration,
            continuation_evidence_id,
        )
        assert still_original.to_dict() == publication_wire, label
