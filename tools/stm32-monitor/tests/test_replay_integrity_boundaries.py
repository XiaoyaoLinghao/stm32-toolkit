"""Offline Replay publication and persisted-evidence integrity boundaries.

These cases stay inside authored synthetic evidence stores and immutable
reruns.  They never copy user firmware, open a probe or publish remotely.
"""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor import replay as replay_module
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    ENVIRONMENT_FAILURE,
    OPERATION_CONFLICT,
    MonitorReplayError,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceValidationError
from stm32_toolkit.evidence.gc import RootRecord, get_root
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.monitor_replay_contract import ReplayContractError
from test_physical_publication import (
    _monitor_manifest_operations,
    _monitor_root_files,
    _physical_context,
    _physical_evidence_state,
    _physical_request,
    _publish_physical_test_run,
)
from test_replay import (
    _evidence,
    _fixture,
    _history_batches,
    _operation,
    _paths,
)


def _replay_manifest_count(evidence: EvidenceStore, operation: str) -> int:
    directory = evidence.root / "manifests"
    if not directory.exists():
        return 0
    return sum(
        1
        for path in directory.glob("*.json")
        if json.loads(path.read_bytes().decode("utf-8")).get("operation")
        == operation
    )


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "expected_message", "planted_root"),
    [
        (
            "conflict",
            OPERATION_CONFLICT,
            "operation root changed before publication",
            True,
        ),
        (
            "generic",
            ENVIRONMENT_FAILURE,
            "monitor run root publication failed",
            False,
        ),
    ],
)
def test_ingest_transcript_root_publication_errors_preserve_prefix_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: str,
    expected_code: str,
    expected_message: str,
    planted_root: bool,
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    other_operation = _operation("fixed-after")
    ingest_monitor_replay(paths, evidence, other_operation, _fixture("fixed-after"))
    other_root = get_root(evidence, "monitor-run", other_operation)
    manifests_before = _replay_manifest_count(evidence, "monitor-replay-import")
    reference_roots_before = _monitor_root_files(evidence, "monitor-run-ref")
    real_put_root = replay_module.put_root

    def conflicted_put_root(store: EvidenceStore, candidate: RootRecord) -> None:
        if candidate.root_type == "monitor-run" and candidate.root_id == operation:
            if provider_error == "conflict":
                real_put_root(
                    store,
                    RootRecord(
                        root_type="monitor-run",
                        root_id=operation,
                        manifest_id=other_root.manifest_id,
                        metadata=other_root.metadata,
                    ),
                )
                raise EvidenceValidationError(
                    "EVIDENCE_CORRUPT",
                    "root identity already has different canonical bytes",
                )
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT", "transcript store rejected the operation root"
            )
        real_put_root(store, candidate)

    monkeypatch.setattr(replay_module, "put_root", conflicted_put_root)
    with pytest.raises(MonitorReplayError) as refused:
        ingest_monitor_replay(
            paths, EvidenceStore(evidence.root), operation, _fixture("failed-before")
        )

    assert refused.value.code == expected_code
    assert refused.value.message == expected_message
    assert _replay_manifest_count(evidence, "monitor-replay-import") == (
        manifests_before + 1
    )
    assert _monitor_root_files(evidence, "monitor-run-ref") == reference_roots_before
    assert _history_batches(paths, UUID(operation)) == ()
    if planted_root:
        winner = get_root(evidence, "monitor-run", operation)
        assert winner.manifest_id == other_root.manifest_id
        assert winner.metadata == other_root.metadata
        assert len(_monitor_root_files(evidence, "monitor-run")) == 2
    else:
        with pytest.raises(EvidenceValidationError):
            get_root(evidence, "monitor-run", operation)
        assert len(_monitor_root_files(evidence, "monitor-run")) == 1


@pytest.mark.parametrize(
    ("outcome", "expected_code", "expected_message"),
    [
        (
            "different-intent",
            OPERATION_CONFLICT,
            "operation root has a different intent",
        ),
        (
            "vanished",
            ENVIRONMENT_FAILURE,
            "physical Monitor transcript root disappeared",
        ),
    ],
)
def test_physical_transcript_root_publication_errors_preserve_history_and_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_code: str,
    expected_message: str,
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
        paths, raw_probe, monitor_run_id, group_id, test_run_id
    )
    history_before = _history_batches(paths, monitor_run_id)
    assert history_before
    real_put_root = replay_module.put_root
    operation = str(monitor_run_id)

    def conflicted_put_root(store: EvidenceStore, candidate: RootRecord) -> None:
        if candidate.root_type == "monitor-run" and candidate.root_id == operation:
            if outcome == "different-intent":
                real_put_root(
                    store,
                    replace(
                        candidate,
                        metadata={
                            **candidate.metadata,
                            "source_record_sha256": "0" * 64,
                        },
                    ),
                )
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT",
                "root identity already has different canonical bytes",
            )
        real_put_root(store, candidate)

    monkeypatch.setattr(replay_module, "put_root", conflicted_put_root)
    with pytest.raises(MonitorReplayError) as refused:
        publish_physical_monitor_run(paths, EvidenceStore(evidence.root), **request)

    assert refused.value.code == expected_code
    assert refused.value.message == expected_message
    assert _history_batches(paths, monitor_run_id) == history_before
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()
    assert _monitor_manifest_operations(evidence) == ("monitor-physical-window",)
    if outcome == "different-intent":
        winner = get_root(evidence, "monitor-run", operation)
        assert winner.metadata["source_record_sha256"] == "0" * 64
        assert len(_monitor_root_files(evidence, "monitor-run")) == 1
    else:
        assert _monitor_root_files(evidence, "monitor-run") == ()


def _published_physical_reference(
    tmp_path: Path,
) -> tuple[object, EvidenceStore, MonitorRunRefV2, UUID]:
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
        paths, raw_probe, monitor_run_id, group_id, test_run_id
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    assert load_monitor_run_reference(
        paths, EvidenceStore(evidence.root), str(monitor_run_id)
    ).to_dict() == reference.to_dict()
    return paths, evidence, reference, monitor_run_id


def _persisted_transcript_raw(evidence: EvidenceStore) -> bytes:
    root_path = _monitor_root_files(evidence, "monitor-run")[0]
    root = json.loads(root_path.read_bytes().decode("utf-8"))
    envelope = evidence.get_envelope(root["manifest_id"])
    return evidence.read_artifact(
        envelope.artifacts[0], maximum_bytes=64 * 1024 * 1024
    )


def _replace_persisted_transcript_bytes(
    tmp_path: Path,
    evidence: EvidenceStore,
    reference: MonitorRunRefV2,
    mutated_raw: bytes,
) -> None:
    """Rewrite the persisted graph exactly as an untrusted-input helper does."""
    transcript_root_path = _monitor_root_files(evidence, "monitor-run")[0]
    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    transcript_root = json.loads(transcript_root_path.read_bytes().decode("utf-8"))
    reference_root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    stored_transcript = evidence.get_envelope(transcript_root["manifest_id"])
    source_digest = sha256(mutated_raw).hexdigest()

    transcript_source = tmp_path / "mutated-physical-transcript.json"
    transcript_source.write_bytes(mutated_raw)
    transcript_artifact = evidence.ingest_file(
        transcript_source,
        kind="monitor-physical-transcript",
        media_type="application/json",
    )
    transcript_metadata = dict(stored_transcript.metadata)
    transcript_metadata["source_record_sha256"] = source_digest
    replacement_transcript = EvidenceEnvelope(
        identity=stored_transcript.identity,
        operation=stored_transcript.operation,
        produced_at_utc=stored_transcript.produced_at_utc,
        parents=stored_transcript.parents,
        artifacts=(transcript_artifact,),
        metadata=transcript_metadata,
    )
    evidence.put_envelope(replacement_transcript)

    reference_payload = reference.to_dict()
    reference_payload["source_record_sha256"] = source_digest
    reference_payload["transcript_evidence_id"] = str(
        replacement_transcript.evidence_id
    )
    unsigned_reference = {
        key: value
        for key, value in reference_payload.items()
        if key != "run_ref_sha256"
    }
    reference_payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned_reference)
    ).hexdigest()
    updated_reference = MonitorRunRefV2.from_value(reference_payload)

    stored_reference = evidence.get_envelope(reference_root["manifest_id"])
    reference_source = tmp_path / "mutated-physical-reference.json"
    reference_source.write_bytes(
        canonical_replay_json_bytes(updated_reference.to_dict())
    )
    reference_artifact = evidence.ingest_file(
        reference_source, kind="monitor-run-ref", media_type="application/json"
    )
    reference_metadata = dict(stored_reference.metadata)
    reference_metadata["source_record_sha256"] = updated_reference.source_record_sha256
    reference_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    replacement_reference = EvidenceEnvelope(
        identity=stored_reference.identity,
        operation=stored_reference.operation,
        produced_at_utc=stored_reference.produced_at_utc,
        parents=(str(replacement_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(replacement_reference)

    transcript_root["manifest_id"] = str(replacement_transcript.evidence_id)
    transcript_root_metadata = dict(transcript_root["metadata"])
    transcript_root_metadata["source_record_sha256"] = (
        updated_reference.source_record_sha256
    )
    transcript_root_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    transcript_root["metadata"] = transcript_root_metadata
    transcript_root_path.write_bytes(canonical_json_bytes(transcript_root))

    reference_root["manifest_id"] = str(replacement_reference.evidence_id)
    reference_root["metadata"] = reference_metadata
    reference_root_path.write_bytes(canonical_json_bytes(reference_root))


def test_persisted_physical_transcript_non_finite_number_is_refused(
    tmp_path: Path,
) -> None:
    paths, evidence, reference, monitor_run_id = _published_physical_reference(
        tmp_path
    )
    payload = json.loads(_persisted_transcript_raw(evidence).decode("utf-8"))
    payload["batches"][0]["actualRateHz"] = float("nan")
    mutated_raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
    ).encode("utf-8")
    assert b"NaN" in mutated_raw
    _replace_persisted_transcript_bytes(
        tmp_path, evidence, reference, mutated_raw
    )
    before = _physical_evidence_state(evidence)

    with pytest.raises(MonitorReplayError) as refused:
        load_monitor_run_reference(
            paths, EvidenceStore(evidence.root), str(monitor_run_id)
        )

    assert refused.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert refused.value.message == "physical Monitor transcript is corrupt"
    cause = refused.value.__cause__
    assert isinstance(cause, ReplayContractError)
    assert str(cause) == "physical transcript has a non-finite number: NaN"
    assert _physical_evidence_state(evidence) == before


@pytest.mark.parametrize(
    ("mutation", "replacement"),
    [
        ("target-label", "replay"),
        ("raw-probe", "probe/serial/01"),
    ],
)
def test_persisted_physical_transcript_rejects_physical_replay_binding_labels(
    tmp_path: Path,
    mutation: str,
    replacement: str,
) -> None:
    paths, evidence, reference, monitor_run_id = _published_physical_reference(
        tmp_path
    )
    payload = json.loads(_persisted_transcript_raw(evidence).decode("utf-8"))
    bindings = (payload["binding"], *(item["binding"] for item in payload["batches"]))
    for binding in bindings:
        if mutation == "target-label":
            binding["targetDevice"] = replacement
        else:
            binding["probeId"] = replacement
    mutated_raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    _replace_persisted_transcript_bytes(
        tmp_path, evidence, reference, mutated_raw
    )
    before = _physical_evidence_state(evidence)

    with pytest.raises(MonitorReplayError) as refused:
        load_monitor_run_reference(
            paths, EvidenceStore(evidence.root), str(monitor_run_id)
        )

    assert refused.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert refused.value.message == "physical Monitor transcript is corrupt"
    cause = refused.value.__cause__
    assert isinstance(cause, ReplayContractError)
    assert str(cause) == "physical binding labels are invalid"
    assert _physical_evidence_state(evidence) == before
