from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    MonitorReplayError,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence import EvidenceEnvelope
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.monitor_replay_contract import ReplayContractError
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository as _TestRunRepository
from test_physical_publication import (
    _monitor_root_files,
    _physical_context,
    _physical_request,
    _publish_physical_test_run,
)

_CORRUPTION_CASES = (
    "reference-operation",
    "reference-metadata-role",
    "reference-transcript-evidence-id",
    "reference-group-revision",
    "reference-manifest-missing",
)
_EXPECTED_CAUSES = {
    "reference-operation": "physical reference envelope is invalid",
    "reference-metadata-role": "physical reference envelope metadata is invalid",
    "reference-transcript-evidence-id": "physical transcript evidence ID differs from reference",
    "reference-group-revision": "physical transcript and reference windows differ",
}


def _full_tree_state(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    candidates = []
    for path in _monitor_root_files(evidence, root_type):
        document = json.loads(path.read_bytes().decode("utf-8"))
        if document.get("root_id") == root_id:
            candidates.append(path)
    assert len(candidates) == 1
    return candidates[0]


def _replace_root(
    evidence: EvidenceStore,
    original: RootRecord,
    *,
    manifest_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> RootRecord:
    replacement = RootRecord(
        root_type=original.root_type,
        root_id=original.root_id,
        manifest_id=original.manifest_id if manifest_id is None else manifest_id,
        metadata=original.metadata if metadata is None else metadata,
    )
    _root_path(evidence, original.root_type, original.root_id).unlink()
    put_root(evidence, replacement)
    return replacement


def _changed_reference(
    original: MonitorRunRefV2,
    corruption: str,
    *,
    target_test_run_manifest_id: str,
) -> MonitorRunRefV2:
    payload = original.to_dict()
    if corruption == "reference-transcript-evidence-id":
        assert target_test_run_manifest_id != original.transcript_evidence_id
        payload["transcript_evidence_id"] = target_test_run_manifest_id
    elif corruption == "reference-group-revision":
        assert original.group_revision == 1
        payload["group_revision"] = 2
    else:
        raise AssertionError(f"reference payload is not changed for {corruption}")

    unsigned = {key: value for key, value in payload.items() if key != "run_ref_sha256"}
    payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    changed = MonitorRunRefV2.from_value(payload)
    assert changed.to_dict() == payload
    return changed


def _publish_changed_reference(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    *,
    original_reference_envelope: EvidenceEnvelope,
    changed_reference: MonitorRunRefV2,
    source_name: str,
    parent_ids: tuple[str, ...] | None = None,
) -> EvidenceEnvelope:
    raw = canonical_replay_json_bytes(changed_reference.to_dict())
    source = paths.project_root / source_name
    source.write_bytes(raw)
    artifact = evidence.ingest_file(
        source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    metadata = dict(original_reference_envelope.metadata)
    metadata.update(
        {
            "operation_id": changed_reference.operation_id,
            "run_ref_sha256": changed_reference.run_ref_sha256,
            "source_record_sha256": changed_reference.source_record_sha256,
            "scenario_role": changed_reference.scenario_role,
            "origin_workspace_id": changed_reference.origin_workspace_id,
            "import_workspace_id": changed_reference.import_workspace_id,
            "execution_source": changed_reference.execution_source,
            "physical_transport_evidence": changed_reference.physical_transport_evidence,
        }
    )
    envelope = EvidenceEnvelope(
        identity=original_reference_envelope.identity,
        operation=original_reference_envelope.operation,
        produced_at_utc=original_reference_envelope.produced_at_utc,
        parents=(
            original_reference_envelope.parents if parent_ids is None else parent_ids
        ),
        artifacts=(artifact,),
        metadata=metadata,
    )
    assert envelope.operation == original_reference_envelope.operation
    assert envelope.parents == (
        original_reference_envelope.parents if parent_ids is None else parent_ids
    )
    return envelope


def _fresh_reference(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    monitor_run_id: UUID,
) -> MonitorRunRefV2:
    return load_monitor_run_reference(
        WorkspacePaths.from_roots(
            paths.data_root,
            paths.project_root,
            UUID("123e4567-e89b-42d3-a456-426614174000"),
            paths.session_id,
        ),
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    )


@pytest.mark.parametrize(
    "corruption",
    _CORRUPTION_CASES,
    ids=_CORRUPTION_CASES,
)
def test_persisted_physical_reference_refuses_corruption_without_writes_then_restores(
    tmp_path: Path,
    corruption: str,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = (
        _physical_context(tmp_path)
    )
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    original_reference = publish_physical_monitor_run(paths, evidence, **request)
    original_wire = original_reference.to_dict()
    original_reference_root = get_root(
        evidence,
        "monitor-run-ref",
        str(monitor_run_id),
    )
    original_transcript_root = get_root(
        evidence,
        "monitor-run",
        str(monitor_run_id),
    )
    original_reference_envelope = evidence.get_envelope(
        original_reference_root.manifest_id
    )
    original_transcript_envelope = evidence.get_envelope(
        original_transcript_root.manifest_id
    )
    original_transcript_bytes = evidence.read_artifact(
        original_transcript_envelope.artifacts[0],
        maximum_bytes=64 * 1024 * 1024,
    )
    assert original_reference_envelope.parents == (
        original_transcript_root.manifest_id,
    )
    assert _fresh_reference(paths, evidence, monitor_run_id).to_dict() == original_wire

    if corruption == "reference-operation":
        corrupted_envelope = EvidenceEnvelope(
            identity=original_reference_envelope.identity,
            operation="monitor-physical-window",
            produced_at_utc=original_reference_envelope.produced_at_utc,
            parents=original_reference_envelope.parents,
            artifacts=original_reference_envelope.artifacts,
            metadata=dict(original_reference_envelope.metadata),
        )
        assert corrupted_envelope.identity == original_reference_envelope.identity
        assert (
            corrupted_envelope.produced_at_utc
            == original_reference_envelope.produced_at_utc
        )
        assert corrupted_envelope.parents == original_reference_envelope.parents
        assert corrupted_envelope.artifacts == original_reference_envelope.artifacts
        assert corrupted_envelope.metadata == original_reference_envelope.metadata
        evidence.put_envelope(corrupted_envelope)
        _replace_root(
            evidence,
            original_reference_root,
            manifest_id=str(corrupted_envelope.evidence_id),
        )
    elif corruption == "reference-metadata-role":
        metadata = dict(original_reference_envelope.metadata)
        metadata["scenario_role"] = "fixed-after"
        assert metadata["scenario_role"] != original_reference.scenario_role
        corrupted_envelope = EvidenceEnvelope(
            identity=original_reference_envelope.identity,
            operation=original_reference_envelope.operation,
            produced_at_utc=original_reference_envelope.produced_at_utc,
            parents=original_reference_envelope.parents,
            artifacts=original_reference_envelope.artifacts,
            metadata=metadata,
        )
        assert corrupted_envelope.identity == original_reference_envelope.identity
        assert corrupted_envelope.operation == original_reference_envelope.operation
        assert (
            corrupted_envelope.produced_at_utc
            == original_reference_envelope.produced_at_utc
        )
        assert corrupted_envelope.parents == original_reference_envelope.parents
        assert corrupted_envelope.artifacts == original_reference_envelope.artifacts
        assert corrupted_envelope.metadata != original_reference_envelope.metadata
        evidence.put_envelope(corrupted_envelope)
        _replace_root(
            evidence,
            original_reference_root,
            manifest_id=str(corrupted_envelope.evidence_id),
        )
    elif corruption in {
        "reference-transcript-evidence-id",
        "reference-group-revision",
    }:
        target_test_run = _TestRunRepository(evidence).load(test_run_id)
        target_test_run_manifest_id = target_test_run.root.manifest_id
        assert target_test_run_manifest_id == str(target_test_run.envelope.evidence_id)
        assert target_test_run_manifest_id != original_transcript_root.manifest_id
        changed_reference = _changed_reference(
            original_reference,
            corruption,
            target_test_run_manifest_id=target_test_run_manifest_id,
        )
        changed_envelope = _publish_changed_reference(
            paths,
            evidence,
            original_reference_envelope=original_reference_envelope,
            changed_reference=changed_reference,
            source_name=f"{corruption}.json",
            parent_ids=original_reference_envelope.parents,
        )
        evidence.put_envelope(changed_envelope)
        _replace_root(
            evidence,
            original_reference_root,
            manifest_id=str(changed_envelope.evidence_id),
            metadata={
                **dict(original_reference_root.metadata),
                "run_ref_sha256": changed_reference.run_ref_sha256,
            },
        )
        _replace_root(
            evidence,
            original_transcript_root,
            metadata={
                **dict(original_transcript_root.metadata),
                "run_ref_sha256": changed_reference.run_ref_sha256,
            },
        )
        assert (
            evidence.get_envelope(original_transcript_root.manifest_id).to_dict()
            == original_transcript_envelope.to_dict()
        )
        assert (
            evidence.read_artifact(
                original_transcript_envelope.artifacts[0],
                maximum_bytes=64 * 1024 * 1024,
            )
            == original_transcript_bytes
        )
    elif corruption == "reference-manifest-missing":
        reference_manifest_path = (
            evidence.root / "manifests" / f"{original_reference_root.manifest_id}.json"
        )
        assert reference_manifest_path.is_file()
        reference_manifest_path.unlink()
    else:
        raise AssertionError(f"unknown corruption case: {corruption}")

    corrupted_state = _full_tree_state(tmp_path)
    with pytest.raises(MonitorReplayError) as error:
        _fresh_reference(paths, evidence, monitor_run_id)
    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "physical Monitor Evidence is corrupt"
    cause = error.value.__cause__
    if corruption == "reference-manifest-missing":
        assert isinstance(cause, FileNotFoundError)
    else:
        assert type(cause) is ReplayContractError
        assert str(cause) == _EXPECTED_CAUSES[corruption]
    assert _full_tree_state(tmp_path) == corrupted_state

    if corruption in {
        "reference-operation",
        "reference-metadata-role",
    }:
        _replace_root(evidence, original_reference_root)
    elif corruption in {
        "reference-transcript-evidence-id",
        "reference-group-revision",
    }:
        _replace_root(evidence, original_reference_root)
        _replace_root(evidence, original_transcript_root)
    elif corruption == "reference-manifest-missing":
        evidence.put_envelope(original_reference_envelope)

    restored = _fresh_reference(paths, evidence, monitor_run_id)
    assert restored.to_dict() == original_wire
    assert restored.schema == original_wire["schema"]
    assert restored.physical_transport_evidence is True
    assert restored.probe_id == original_wire["probe_id"]
    assert restored.group_id == original_wire["group_id"]
    assert restored.group_revision == original_wire["group_revision"]
    assert restored.source_record_sha256 == original_wire["source_record_sha256"]
    assert restored.lease_id == original_wire["lease_id"]
