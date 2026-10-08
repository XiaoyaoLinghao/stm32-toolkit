from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from uuid import UUID

import pytest
from stm32_monitor.analysis_workflows import (
    ANALYSIS_WORKFLOW_INVALID,
    INCOMPATIBLE_IDENTITY,
    AnalysisBundleRef,
    AnalysisPublication,
    AnalysisWorkflowError,
    export_analysis_bundle,
)
from stm32_toolkit.evidence import ArtifactRef
from stm32_toolkit.testing.publication import TestRunRepository
from test_analysis_workflows import (
    _data_tree,
    _declaration,
    _evidence_tree,
    _physical_pair,
    _publish,
    _request,
)
from test_physical_publication import _publish_physical_test_run


def _assert_publication_unchanged(
    publication: AnalysisPublication,
    publication_wire: dict[str, object],
    evidence,
    evidence_before: dict[str, bytes],
) -> None:
    assert publication.to_dict() == publication_wire
    assert AnalysisPublication.from_value(publication_wire) == publication
    assert _evidence_tree(evidence) == evidence_before


def test_public_analysis_models_reject_malformed_components_without_mutation(
    tmp_path,
) -> None:
    (
        paths,
        evidence,
        _failed_test_run_id,
        _fixed_test_run_id,
        _raw_probe,
        before,
        after,
    ) = _physical_pair(tmp_path)
    declaration = _declaration(tmp_path, evidence, before, after)
    publication = _publish(paths, evidence, before, after, declaration)
    publication_wire = publication.to_dict()
    evidence_before = _evidence_tree(evidence)

    malformed_components = (
        ("analysis_result", "analysis result is invalid"),
        ("analysis_evidence_ref", "analysis evidence reference is invalid"),
        ("diagnostic_marker", "diagnostic marker is invalid"),
        ("diagnostic_marker_ref", "diagnostic marker reference is invalid"),
    )
    for field_name, expected_message in malformed_components:
        with pytest.raises(AnalysisWorkflowError) as error:
            replace(publication, **{field_name: object()})
        assert error.value.code == ANALYSIS_WORKFLOW_INVALID
        assert error.value.message == expected_message
        _assert_publication_unchanged(
            publication, publication_wire, evidence, evidence_before
        )

    bundle_payload = b'{"schema":"stm32-monitor-analysis-bundle/1"}'
    bundle_id = sha256(bundle_payload).hexdigest()
    artifact = ArtifactRef(
        sha256=bundle_id,
        size_bytes=len(bundle_payload),
        relative_path=f"objects/sha256/{bundle_id[:2]}/{bundle_id}",
        kind="monitor-analysis-bundle",
        media_type="application/json",
    )
    bundle_ref = AnalysisBundleRef(
        "stm32-monitor-analysis-bundle-ref/1", bundle_id, "a" * 64, artifact
    )
    bundle_wire = bundle_ref.to_dict()
    assert AnalysisBundleRef.from_value(bundle_wire) == bundle_ref

    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisBundleRef(
            "stm32-monitor-analysis-bundle-ref/1", bundle_id, "a" * 64, object()
        )
    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "analysis bundle reference is invalid"
    assert AnalysisBundleRef.from_value(bundle_wire) == bundle_ref
    _assert_publication_unchanged(
        publication, publication_wire, evidence, evidence_before
    )

    invalid_evidence_id = dict(bundle_wire)
    invalid_evidence_id["evidence_id"] = "A" * 64
    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisBundleRef.from_value(invalid_evidence_id)
    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "analysis bundle reference is invalid"
    assert AnalysisBundleRef.from_value(bundle_wire) == bundle_ref
    _assert_publication_unchanged(
        publication, publication_wire, evidence, evidence_before
    )

    invalid_shape = dict(bundle_wire)
    invalid_shape["unexpected"] = None
    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisBundleRef.from_value(invalid_shape)
    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "analysis bundle reference is invalid"
    assert AnalysisBundleRef.from_value(bundle_wire) == bundle_ref
    _assert_publication_unchanged(
        publication, publication_wire, evidence, evidence_before
    )


def test_physical_export_rejects_independent_test_run_and_recovers(
    tmp_path,
) -> None:
    (
        paths,
        evidence,
        failed_test_run_id,
        fixed_test_run_id,
        raw_probe,
        before,
        after,
    ) = _physical_pair(tmp_path)
    declaration = _declaration(tmp_path, evidence, before, after)
    request = _request(before, after)
    publication = _publish(paths, evidence, before, after, declaration)

    first_payload, first_ref = export_analysis_bundle(
        paths,
        evidence,
        request,
        publication,
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    assert first_ref.bundle_id == sha256(first_payload).hexdigest()
    assert first_payload

    extra_test_run_id = "physical-test-run-independent"
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=extra_test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=UUID("55555555-5555-4555-8555-555555555555"),
    )
    independently_published = TestRunRepository(evidence).load(extra_test_run_id)
    assert independently_published.manifest.run_id == extra_test_run_id
    assert independently_published.root.metadata["execution_source"] == "physical"

    evidence_before_refusal = _evidence_tree(evidence)
    data_before_refusal = _data_tree(paths)
    with pytest.raises(AnalysisWorkflowError) as error:
        export_analysis_bundle(
            paths,
            evidence,
            request,
            publication,
            extra_test_run_id,
            fixed_test_run_id,
            declaration,
        )
    assert error.value.code == INCOMPATIBLE_IDENTITY
    assert error.value.message == "TestRun does not match physical reference"
    assert _evidence_tree(evidence) == evidence_before_refusal
    assert _data_tree(paths) == data_before_refusal

    restored_payload, restored_ref = export_analysis_bundle(
        paths,
        evidence,
        request,
        publication,
        failed_test_run_id,
        fixed_test_run_id,
        declaration,
    )
    assert (restored_payload, restored_ref) == (first_payload, first_ref)
