"""Contract tests for durable Target replay TestRun publication and reload."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceValidationError
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestRunManifest as RunManifest,
)
from stm32_toolkit.testing.publication import (
    TestRunPublisher as Publisher,
    TestRunRepository as Repository,
)
from stm32_toolkit.testing.replay import load_target_replay_fixture
from stm32_toolkit.testing.target import TargetFrameDecoder


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
UTC_0 = "2026-08-21T00:00:00.000000Z"
IMPORT_WORKSPACE_ID = sha256(b"local-import-workspace").hexdigest()


def _fixture(name: str):
    return load_target_replay_fixture(FIXTURES / f"{name}.json", FIXTURES / f"{name}.hex")


def _bundle(
    tmp_path: Path,
    *,
    name: str,
    operation_id: str,
    import_workspace_id: str = IMPORT_WORKSPACE_ID,
):
    fixture = _fixture(name)
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(tmp_path / "evidence")
    results_root = tmp_path / "results"

    descriptor_source = project_root / f"{name}.json"
    descriptor_source.write_bytes((FIXTURES / f"{name}.json").read_bytes())
    descriptor_artifact = store.ingest_file(
        descriptor_source,
        kind="target-replay-descriptor",
        media_type="application/json",
    )
    stream_source = project_root / f"{name}.bin"
    stream_source.write_bytes(fixture.stream_bytes)
    descriptor_stream_artifact = store.ingest_file(
        stream_source,
        kind="target-replay-stream",
        media_type="application/octet-stream",
    )
    descriptor_envelope = EvidenceEnvelope(
        identity=fixture.descriptor.identity,
        operation="target-replay-input",
        produced_at_utc=UTC_0,
        parents=(),
        artifacts=(descriptor_artifact, descriptor_stream_artifact),
        metadata={
            "replay_id": fixture.descriptor.replay_id,
            "scenario_role": fixture.descriptor.scenario_role,
            "stream_sha256": fixture.descriptor.stream.sha256,
            "stream_size_bytes": fixture.descriptor.stream.size_bytes,
            "execution_source": "replay",
            "physical_transport_evidence": False,
            "origin_workspace_id": fixture.descriptor.identity.workspace_id,
            "import_workspace_id": import_workspace_id,
        },
    )

    decoder = TargetFrameDecoder()
    frames = decoder.feed(fixture.stream_bytes)
    decoder.finish()
    case_starts = {
        str(frame.payload["case_id"]): frame.payload
        for frame in frames
        if frame.kind == 3
    }
    cases = tuple(
        CaseResult(
            str(frame.payload["case_id"]),
            str(frame.payload["state"]),
            str(case_starts[str(frame.payload["case_id"])].get("started_at_utc")),
            str(frame.payload["ended_at_utc"]),
            int(frame.payload["duration_ms"]),
            frame.payload["message"],
            None,
            None,
        )
        for frame in frames
        if frame.kind == 4
    )
    raw_source = project_root / f"{operation_id}.bin"
    raw_source.write_bytes(fixture.stream_bytes)
    raw_artifact = store.ingest_file(
        raw_source,
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    terminal = frames[-1].payload
    run_start = frames[1].payload
    manifest = RunManifest(
        "stm32-test/1",
        operation_id,
        "target",
        str(terminal["state"]),
        fixture.descriptor.identity,
        "replay",
        cases,
        str(run_start["started_at_utc"]),
        str(terminal["ended_at_utc"]),
        int(terminal["duration_ms"]),
        None,
        None,
        raw_artifact,
    )
    return fixture, store, project_root, results_root, descriptor_envelope, manifest


def test_target_replay_publisher_exposes_the_public_publication_entrypoint():
    assert callable(getattr(Publisher, "publish_target_replay", None))


def test_target_replay_publishes_origin_manifest_and_import_metadata(tmp_path: Path):
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publish = getattr(Publisher, "publish_target_replay", None)
    assert callable(publish)

    published = Publisher(store, project_root, results_root).publish_target_replay(
        manifest, descriptor, IMPORT_WORKSPACE_ID
    )

    assert published.manifest == manifest
    assert published.envelope.operation == "target-test-replay"
    assert published.envelope.identity == fixture.descriptor.identity
    assert published.envelope.parents == (str(descriptor.evidence_id),)
    assert published.envelope.metadata == {
        "descriptor_evidence_id": str(descriptor.evidence_id),
        "execution_source": "replay",
        "import_workspace_id": IMPORT_WORKSPACE_ID,
        "origin_workspace_id": fixture.descriptor.identity.workspace_id,
        "operation_id": manifest.run_id,
        "operation_intent_sha256": published.envelope.metadata["operation_intent_sha256"],
        "physical_transport_evidence": False,
        "test_manifest_sha256": published.manifest_artifact.sha256,
        "test_run_id": manifest.run_id,
    }
    assert published.root.metadata == {
        "mode": "target",
        "state": "failed",
        "execution_source": "replay",
        "physical_transport_evidence": False,
        "origin_workspace_id": fixture.descriptor.identity.workspace_id,
        "import_workspace_id": IMPORT_WORKSPACE_ID,
    }
    assert fixture.descriptor.identity.workspace_id != IMPORT_WORKSPACE_ID
    assert published.public_data() == {
        "run": {
            "run_id": manifest.run_id,
            "mode": "target",
            "state": "failed",
            "identity": fixture.descriptor.identity.to_dict(),
            "transport": "replay",
            "case_counts": {"passed": 0, "failed": 1, "skipped": 0, "error": 0, "timeout": 0},
            "started_at_utc": manifest.started_at_utc,
            "ended_at_utc": manifest.ended_at_utc,
            "duration_ms": manifest.duration_ms,
        },
        "test_manifest": published.manifest_artifact.to_dict(),
        "evidence_id": published.envelope.evidence_id,
        "execution_source": "replay",
        "physical_transport_evidence": False,
        "origin_workspace_id": fixture.descriptor.identity.workspace_id,
        "import_workspace_id": IMPORT_WORKSPACE_ID,
    }
    parent = store.get_envelope(str(descriptor.evidence_id))
    assert parent == descriptor
    assert store.read_artifact(parent.artifacts[0], maximum_bytes=256 * 1024) == (
        FIXTURES / "failed-before.json"
    ).read_bytes()
    assert store.read_artifact(parent.artifacts[1], maximum_bytes=2**20) == fixture.stream_bytes

    loaded = Repository(store).load(manifest.run_id)
    assert loaded.manifest == manifest
    assert loaded.envelope == published.envelope
    assert loaded.root == published.root
    assert loaded.public_data(authoritative=True) == {
        **published.public_data(),
        "authoritative": True,
    }


def test_target_replay_retry_is_idempotent_and_conflict_is_stable(tmp_path: Path):
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    first = publisher.publish_target_replay(manifest, descriptor, IMPORT_WORKSPACE_ID)
    retry_fixture, retry_store, retry_project, retry_results, retry_descriptor, retry_manifest = _bundle(
        tmp_path / "retry", name="failed-before", operation_id=manifest.run_id
    )
    retry = publisher.publish_target_replay(manifest, retry_descriptor, IMPORT_WORKSPACE_ID)
    assert retry.envelope.evidence_id == first.envelope.evidence_id
    assert retry.public_data() == first.public_data()

    alternate_import = sha256(b"alternate-import-workspace").hexdigest()
    _alternate_fixture, _alternate_store, _alternate_project, _alternate_results, alternate_descriptor, alternate_manifest = _bundle(
        tmp_path / "conflict",
        name="failed-before",
        operation_id=manifest.run_id,
        import_workspace_id=alternate_import,
    )
    with pytest.raises(EvidenceValidationError) as conflict:
        publisher.publish_target_replay(
            alternate_manifest, alternate_descriptor, alternate_import
        )
    assert conflict.value.code == "EVIDENCE_CORRUPT"
    assert Repository(store).load(manifest.run_id).envelope.evidence_id == first.envelope.evidence_id


@pytest.mark.parametrize(
    "bad_import",
    ["not-a-workspace", ""],
)
def test_target_replay_publication_rejects_invalid_import_identity(
    tmp_path: Path, bad_import: str
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    with pytest.raises(Exception):
        Publisher(store, project_root, results_root).publish_target_replay(
            manifest, descriptor, bad_import
        )


def test_target_replay_publication_preserves_origin_and_import_identity_alias(tmp_path: Path):
    alias_workspace_id = _fixture("failed-before").descriptor.identity.workspace_id
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path,
        name="failed-before",
        operation_id="vs03-failed-before",
        import_workspace_id=alias_workspace_id,
    )
    published = Publisher(store, project_root, results_root).publish_target_replay(
        manifest, descriptor, alias_workspace_id
    )
    assert alias_workspace_id == fixture.descriptor.identity.workspace_id
    assert published.envelope.metadata["origin_workspace_id"] == alias_workspace_id
    assert published.envelope.metadata["import_workspace_id"] == alias_workspace_id
    assert published.root.metadata["origin_workspace_id"] == alias_workspace_id
    assert published.root.metadata["import_workspace_id"] == alias_workspace_id
    assert published.public_data()["execution_source"] == "replay"
    assert published.public_data()["physical_transport_evidence"] is False


def test_target_replay_publication_rejects_manifest_run_id_mismatch_before_root(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    mismatched = replace(manifest, run_id="caller-selected-run")

    with pytest.raises(EvidenceValidationError) as failure:
        Publisher(store, project_root, results_root).publish_target_replay(
            mismatched, descriptor, IMPORT_WORKSPACE_ID
        )

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert not (store.root / "roots" / "test-run").exists() or not any(
        (store.root / "roots" / "test-run").glob("*.json")
    )


def test_target_replay_publication_rejects_raw_events_mismatch_before_root(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    wrong_source = project_root / "wrong-target-events.bin"
    wrong_source.write_bytes(b"not-the-decoded-target-stream")
    wrong_raw_events = store.ingest_file(
        wrong_source,
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    mismatched = replace(manifest, raw_events=wrong_raw_events)

    with pytest.raises(EvidenceValidationError) as failure:
        Publisher(store, project_root, results_root).publish_target_replay(
            mismatched, descriptor, IMPORT_WORKSPACE_ID
        )

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert not (store.root / "roots" / "test-run").exists() or not any(
        (store.root / "roots" / "test-run").glob("*.json")
    )
