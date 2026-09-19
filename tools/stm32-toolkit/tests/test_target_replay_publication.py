"""Contract tests for durable Target replay TestRun publication and reload."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from stm32_toolkit.evidence import (
    EvidenceEnvelope,
    EvidenceValidationError,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestProtocolError as ProtocolError,
    TestRunManifest as RunManifest,
)
from stm32_toolkit.testing.publication import (
    TestRunPublisher as Publisher,
    TestRunRepository as Repository,
)
from stm32_toolkit.testing.replay import (
    TargetReplayDescriptor,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
UTC_0 = "2026-08-21T00:00:00.000000Z"
IMPORT_WORKSPACE_ID = sha256(b"local-import-workspace").hexdigest()


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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


def _public_intent_digest(
    manifest: RunManifest,
    descriptor_evidence_id: str,
    import_workspace_id: str,
) -> str:
    """Derive the closed public intent payload without calling a product helper."""
    payload = {
        "operation_id": manifest.run_id,
        "descriptor_evidence_id": descriptor_evidence_id,
        "manifest": manifest.to_dict(),
        "import_workspace_id": import_workspace_id,
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def _fresh_replay_graph(tmp_path: Path, selector: str):
    """Prepare a fresh public descriptor graph before its first run root."""
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    store.put_envelope(descriptor)
    results_root.mkdir(parents=True, exist_ok=True)
    return fixture, store, project_root, results_root, descriptor, manifest


def _ingest_replay_manifest(
    store: EvidenceStore,
    project_root: Path,
    selector: str,
    manifest: RunManifest,
):
    source = project_root / f"{selector}-manifest.json"
    source.write_bytes(canonical_json_bytes(manifest.to_dict()))
    return store.ingest_file(
        source, kind="test-manifest", media_type="application/json"
    )


def _replay_metadata(
    descriptor: EvidenceEnvelope,
    original_manifest: RunManifest,
    persisted_manifest: RunManifest,
    manifest_artifact,
) -> dict[str, object]:
    descriptor_evidence_id = str(descriptor.evidence_id)
    return {
        "descriptor_evidence_id": descriptor_evidence_id,
        "execution_source": "replay",
        "import_workspace_id": IMPORT_WORKSPACE_ID,
        "origin_workspace_id": descriptor.identity.workspace_id,
        "operation_id": original_manifest.run_id,
        "operation_intent_sha256": _public_intent_digest(
            persisted_manifest, descriptor_evidence_id, IMPORT_WORKSPACE_ID
        ),
        "physical_transport_evidence": False,
        "test_manifest_sha256": manifest_artifact.sha256,
        "test_run_id": original_manifest.run_id,
    }


def _put_replay_graph(
    store: EvidenceStore,
    descriptor: EvidenceEnvelope,
    original_manifest: RunManifest,
    persisted_manifest: RunManifest,
    manifest_artifact,
    *,
    identity=None,
    parents=None,
    artifacts=None,
    produced_at_utc=None,
    metadata=None,
):
    """Commit one explicit public target replay envelope and its first root."""
    descriptor_evidence_id = str(descriptor.evidence_id)
    identity = descriptor.identity if identity is None else identity
    parents = (descriptor_evidence_id,) if parents is None else parents
    artifacts = (
        (manifest_artifact, persisted_manifest.raw_events)
        if artifacts is None
        else artifacts
    )
    produced_at_utc = (
        persisted_manifest.ended_at_utc
        if produced_at_utc is None
        else produced_at_utc
    )
    if metadata is None:
        metadata = _replay_metadata(
            descriptor, original_manifest, persisted_manifest, manifest_artifact
        )
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-replay",
        produced_at_utc=produced_at_utc,
        parents=parents,
        artifacts=artifacts,
        metadata=metadata,
    )
    store.put_envelope(envelope)
    put_root(
        store,
        RootRecord(
            "test-run",
            original_manifest.run_id,
            str(envelope.evidence_id),
            {
                "mode": "target",
                "state": persisted_manifest.state,
                "execution_source": "replay",
                "physical_transport_evidence": False,
                "origin_workspace_id": descriptor.identity.workspace_id,
                "import_workspace_id": IMPORT_WORKSPACE_ID,
            },
        ),
    )
    return envelope


def _replay_store_snapshot(store: EvidenceStore, results_root: Path):
    return _tree_bytes(store.root), _tree_bytes(results_root)


def _assert_replay_load_failure(
    store: EvidenceStore,
    results_root: Path,
    run_id: str,
    message: str,
    before_store: dict[str, bytes],
    before_results: dict[str, bytes],
):
    with pytest.raises(EvidenceValidationError) as failure:
        Repository(store).load(run_id)
    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == message
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def _artifact_path(store: EvidenceStore, artifact) -> Path:
    return store.root.joinpath(*artifact.relative_path.split("/"))


def _ingest_replay_bytes(
    store: EvidenceStore,
    project_root: Path,
    selector: str,
    payload: bytes,
    *,
    kind: str,
    media_type: str,
):
    source = project_root / f"{selector}-{kind}.bin"
    source.write_bytes(payload)
    return store.ingest_file(source, kind=kind, media_type=media_type)


def _descriptor_with_stream(descriptor, stream_artifact):
    value = descriptor.to_dict()
    value["stream"] = stream_artifact.to_dict()
    value.pop("replay_id")
    value["replay_id"] = sha256(canonical_replay_json_bytes(value)).hexdigest()
    return TargetReplayDescriptor.from_value(value)


def _replay_stream_variant(
    tmp_path: Path,
    selector: str,
    mutate,
):
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id=f"vs03-{selector}"
    )
    decoder = TargetFrameDecoder()
    frames = decoder.feed(fixture.stream_bytes)
    decoder.finish()
    encoded_frames = []
    for frame in frames:
        payload = dict(frame.payload)
        mutate(frame.kind, payload)
        encoded_frames.append(
            encode_frame(
                frame.kind,
                frame.sequence,
                payload,
                version=frame.version,
            )
        )
    stream_bytes = b"".join(encoded_frames)
    stream_artifact = _ingest_replay_bytes(
        store,
        project_root,
        selector,
        stream_bytes,
        kind="target-replay-stream",
        media_type="application/octet-stream",
    )
    updated_descriptor = _descriptor_with_stream(fixture.descriptor, stream_artifact)
    descriptor_artifact = _ingest_replay_bytes(
        store,
        project_root,
        f"{selector}-descriptor",
        canonical_replay_json_bytes(updated_descriptor),
        kind="target-replay-descriptor",
        media_type="application/json",
    )
    metadata = dict(descriptor.metadata)
    metadata.update(
        {
            "replay_id": updated_descriptor.replay_id,
            "stream_sha256": updated_descriptor.stream.sha256,
            "stream_size_bytes": updated_descriptor.stream.size_bytes,
        }
    )
    parent = EvidenceEnvelope(
        identity=descriptor.identity,
        operation=descriptor.operation,
        produced_at_utc=descriptor.produced_at_utc,
        parents=descriptor.parents,
        artifacts=(descriptor_artifact, stream_artifact),
        metadata=metadata,
    )
    return store, project_root, results_root, parent, replace(
        manifest, raw_events=stream_artifact
    )


def _assert_replay_publish_failure(
    store: EvidenceStore,
    project_root: Path,
    results_root: Path,
    manifest: RunManifest,
    parent: EvidenceEnvelope,
    expected_message: str,
):
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)
    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(manifest, parent, IMPORT_WORKSPACE_ID)
    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == expected_message
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_replay_publisher_exposes_the_public_publication_entrypoint():
    assert callable(getattr(Publisher, "publish_target_replay", None))


def test_replay_publication_cannot_claim_physical_transport_evidence(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )

    published = Publisher(store, project_root, results_root).publish_target_replay(
        manifest, descriptor, IMPORT_WORKSPACE_ID
    )

    public = published.public_data()
    assert public["execution_source"] == "replay"
    assert public["physical_transport_evidence"] is False
    assert published.root.metadata["execution_source"] == "replay"
    assert published.root.metadata["physical_transport_evidence"] is False


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


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        (
            "stream_size_bytes",
            lambda metadata: int(metadata["stream_size_bytes"]) + 1,
            "Target replay descriptor stream contradicts its parent metadata",
        ),
        (
            "scenario_role",
            lambda metadata: "other-role",
            "Target replay descriptor role contradicts its parent metadata",
        ),
    ],
)
def test_target_replay_publication_rejects_rehashed_descriptor_parent_before_write(
    tmp_path: Path, field: str, value, expected_message: str
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    metadata = dict(descriptor.metadata)
    metadata[field] = value(metadata)
    rehashed_parent = EvidenceEnvelope(
        identity=descriptor.identity,
        operation=descriptor.operation,
        produced_at_utc=descriptor.produced_at_utc,
        parents=descriptor.parents,
        artifacts=descriptor.artifacts,
        metadata=metadata,
    )
    before_store = _tree_bytes(store.root)
    before_results = _tree_bytes(results_root)

    with pytest.raises(EvidenceValidationError) as failure:
        Publisher(store, project_root, results_root).publish_target_replay(
            manifest, rehashed_parent, IMPORT_WORKSPACE_ID
        )

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == expected_message
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


@pytest.mark.parametrize(
    "case",
    [
        "source-labels",
        "origin-workspace",
        "import-workspace",
        "replay-id",
        "stream-digest",
        "artifact-membership",
        "descriptor-identity",
        "metadata-closure",
    ],
)
def test_target_replay_publication_rejects_each_public_parent_binding_contract(
    tmp_path: Path, case: str
):
    """Every malformed parent shape is refused before publication side effects."""
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    metadata = dict(descriptor.metadata)
    identity = descriptor.identity
    artifacts = descriptor.artifacts
    expected_messages = {
        "source-labels": "Target replay descriptor parent physical/source labels are invalid",
        "origin-workspace": "Target replay descriptor parent origin workspace contradicts its identity",
        "import-workspace": "Target replay descriptor parent import workspace contradicts the import",
        "replay-id": "Target replay descriptor ID contradicts its parent metadata",
        "stream-digest": "Target replay descriptor stream contradicts its parent metadata",
        "artifact-membership": "Target replay descriptor parent artifacts are invalid",
        "descriptor-identity": "Target replay descriptor identity contradicts its parent envelope",
        "metadata-closure": "Target replay descriptor parent metadata is not closed",
    }
    if case == "source-labels":
        metadata["execution_source"] = "physical"
    elif case == "origin-workspace":
        metadata["origin_workspace_id"] = sha256(b"other-origin").hexdigest()
    elif case == "import-workspace":
        metadata["import_workspace_id"] = sha256(b"other-import").hexdigest()
    elif case == "replay-id":
        metadata["replay_id"] = "other-replay"
    elif case == "stream-digest":
        metadata["stream_sha256"] = sha256(b"other-stream").hexdigest()
    elif case == "artifact-membership":
        artifacts = (*descriptor.artifacts, descriptor.artifacts[0])
    elif case == "descriptor-identity":
        identity = replace(identity, build_id="1" * 64)
    elif case == "metadata-closure":
        metadata.pop("replay_id")
    else:  # pragma: no cover - the parameter list is the contract
        raise AssertionError(case)

    malformed_parent = EvidenceEnvelope(
        identity=identity,
        operation=descriptor.operation,
        produced_at_utc=descriptor.produced_at_utc,
        parents=descriptor.parents,
        artifacts=artifacts,
        metadata=metadata,
    )
    before_store = _tree_bytes(store.root)
    before_results = _tree_bytes(results_root)

    with pytest.raises(EvidenceValidationError) as failure:
        Publisher(store, project_root, results_root).publish_target_replay(
            manifest, malformed_parent, IMPORT_WORKSPACE_ID
        )

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == expected_messages[case]
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        (
            "execution_source",
            "physical",
            "stored Target replay source labels are invalid",
        ),
        (
            "origin_workspace_id",
            sha256(b"persisted-other-origin").hexdigest(),
            "stored Target replay origin workspace contradicts its identity",
        ),
        (
            "descriptor_evidence_id",
            sha256(b"persisted-other-parent").hexdigest(),
            "stored Target replay parent does not match metadata",
        ),
        (
            "import_workspace_id",
            sha256(b"persisted-other-import").hexdigest(),
            "Target replay descriptor parent import workspace contradicts the import",
        ),
    ],
)
def test_target_replay_repository_rejects_persisted_parent_binding_corruption(
    tmp_path: Path,
    field: str,
    value: str,
    expected_message: str,
):
    """Reload validates persisted envelope identity before exposing a run."""
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    published = Publisher(store, project_root, results_root).publish_target_replay(
        manifest, descriptor, IMPORT_WORKSPACE_ID
    )
    metadata = dict(published.envelope.metadata)
    metadata[field] = value
    corrupted = EvidenceEnvelope(
        identity=published.envelope.identity,
        operation=published.envelope.operation,
        produced_at_utc=published.envelope.produced_at_utc,
        parents=published.envelope.parents,
        artifacts=published.envelope.artifacts,
        metadata=metadata,
    )
    store.put_envelope(corrupted)
    root_path = next((store.root / "roots" / "test-run").glob("*.json"))
    root = published.root.to_dict()
    root["manifest_id"] = str(corrupted.evidence_id)
    root_path.write_bytes(canonical_json_bytes(root))

    with pytest.raises(EvidenceValidationError) as failure:
        Repository(store).load(manifest.run_id)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == expected_message


def test_target_replay_repository_rejects_persisted_root_binding_without_mutating_store(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    published = Publisher(store, project_root, results_root).publish_target_replay(
        manifest, descriptor, IMPORT_WORKSPACE_ID
    )
    root_path = next((store.root / "roots" / "test-run").glob("*.json"))
    root = published.root.to_dict()
    root["metadata"] = {**root["metadata"], "state": "passed"}
    root_path.write_bytes(canonical_json_bytes(root))
    before_store = _tree_bytes(store.root)

    with pytest.raises(EvidenceValidationError) as failure:
        Repository(store).load(manifest.run_id)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == "stored root metadata contradicts the Target replay record"
    assert _tree_bytes(store.root) == before_store


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


def test_target_replay_publication_rejects_valid_identity_contradiction_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A valid manifest identity must still agree with its replay descriptor."""
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store = _tree_bytes(store.root)
    before_results = _tree_bytes(results_root)
    parent_reads = []
    put_calls = []
    collector_directories = []
    collector_publications = []
    original_read = store.read_artifact
    original_put = store.put_envelope
    original_new_directory = publisher._collector.new_directory
    original_write_and_ingest = publisher._collector.write_and_ingest

    def read_artifact(artifact, *, maximum_bytes):
        parent_reads.append(artifact)
        return original_read(artifact, maximum_bytes=maximum_bytes)

    def put_envelope(envelope):
        put_calls.append(envelope)
        return original_put(envelope)

    def new_directory(prefix):
        collector_directories.append(prefix)
        return original_new_directory(prefix)

    def write_and_ingest(*args, **kwargs):
        collector_publications.append((args, kwargs))
        return original_write_and_ingest(*args, **kwargs)

    monkeypatch.setattr(store, "read_artifact", read_artifact)
    monkeypatch.setattr(store, "put_envelope", put_envelope)
    monkeypatch.setattr(publisher._collector, "new_directory", new_directory)
    monkeypatch.setattr(publisher._collector, "write_and_ingest", write_and_ingest)

    mismatched = replace(
        manifest,
        identity=replace(manifest.identity, build_id="1" * 64),
    )
    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(mismatched, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert parent_reads == list(descriptor.artifacts)
    assert put_calls == []
    assert collector_directories == []
    assert collector_publications == []
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_replay_publication_rejects_valid_state_contradiction_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A valid terminal state must still agree with the replay descriptor."""
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store = _tree_bytes(store.root)
    before_results = _tree_bytes(results_root)
    parent_reads = []
    put_calls = []
    collector_directories = []
    collector_publications = []
    original_read = store.read_artifact
    original_put = store.put_envelope
    original_new_directory = publisher._collector.new_directory
    original_write_and_ingest = publisher._collector.write_and_ingest

    def read_artifact(artifact, *, maximum_bytes):
        parent_reads.append(artifact)
        return original_read(artifact, maximum_bytes=maximum_bytes)

    def put_envelope(envelope):
        put_calls.append(envelope)
        return original_put(envelope)

    def new_directory(prefix):
        collector_directories.append(prefix)
        return original_new_directory(prefix)

    def write_and_ingest(*args, **kwargs):
        collector_publications.append((args, kwargs))
        return original_write_and_ingest(*args, **kwargs)

    monkeypatch.setattr(store, "read_artifact", read_artifact)
    monkeypatch.setattr(store, "put_envelope", put_envelope)
    monkeypatch.setattr(publisher._collector, "new_directory", new_directory)
    monkeypatch.setattr(publisher._collector, "write_and_ingest", write_and_ingest)

    mismatched = replace(
        manifest,
        state="passed",
        cases=tuple(replace(case, state="passed", message=None) for case in manifest.cases),
    )
    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(mismatched, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert parent_reads == list(descriptor.artifacts)
    assert put_calls == []
    assert collector_directories == []
    assert collector_publications == []
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_replay_publication_rejects_contradictory_parent_binding_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A descriptor parent cannot bind to a different valid import workspace."""
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store = _tree_bytes(store.root)
    before_results = _tree_bytes(results_root)
    parent_reads = []
    put_calls = []
    collector_directories = []
    collector_publications = []
    original_read = store.read_artifact
    original_put = store.put_envelope
    original_new_directory = publisher._collector.new_directory
    original_write_and_ingest = publisher._collector.write_and_ingest

    def read_artifact(artifact, *, maximum_bytes):
        parent_reads.append(artifact)
        return original_read(artifact, maximum_bytes=maximum_bytes)

    def put_envelope(envelope):
        put_calls.append(envelope)
        return original_put(envelope)

    def new_directory(prefix):
        collector_directories.append(prefix)
        return original_new_directory(prefix)

    def write_and_ingest(*args, **kwargs):
        collector_publications.append((args, kwargs))
        return original_write_and_ingest(*args, **kwargs)

    monkeypatch.setattr(store, "read_artifact", read_artifact)
    monkeypatch.setattr(store, "put_envelope", put_envelope)
    monkeypatch.setattr(publisher._collector, "new_directory", new_directory)
    monkeypatch.setattr(publisher._collector, "write_and_ingest", write_and_ingest)

    contradictory = EvidenceEnvelope(
        identity=descriptor.identity,
        operation=descriptor.operation,
        produced_at_utc=descriptor.produced_at_utc,
        parents=descriptor.parents,
        artifacts=descriptor.artifacts,
        metadata={
            **descriptor.metadata,
            "import_workspace_id": sha256(b"contradictory-import").hexdigest(),
        },
    )
    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(manifest, contradictory, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert parent_reads == []
    assert put_calls == []
    assert collector_directories == []
    assert collector_publications == []
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_artifact_shape_selector_rejects_wrong_public_ref_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)
    candidate = replace(
        manifest,
        raw_events=replace(manifest.raw_events, kind="test-stdout"),
    )

    with pytest.raises(ProtocolError) as failure:
        publisher.publish_target_replay(candidate, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "TEST_PROTOCOL_INVALID"
    assert failure.value.message == "raw_events has an invalid Target replay artifact type"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_manifest_type_selector_rejects_non_manifest_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, _manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)

    with pytest.raises(ProtocolError) as failure:
        publisher.publish_target_replay(None, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "TEST_PROTOCOL_INVALID"
    assert failure.value.message == "manifest must be a TestRunManifest"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_manifest_execution_mode_selector_rejects_host_mode_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)
    candidate = replace(manifest, mode="host")

    with pytest.raises(ProtocolError) as failure:
        publisher.publish_target_replay(candidate, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "TEST_PROTOCOL_INVALID"
    assert failure.value.message == "publication requires a Target replay manifest"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_manifest_nonterminal_selector_rejects_running_state_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)
    candidate = replace(manifest, state="running")

    with pytest.raises(ProtocolError) as failure:
        publisher.publish_target_replay(candidate, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "TEST_PROTOCOL_INVALID"
    assert failure.value.message == "publication requires a completed Target replay manifest"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_manifest_host_output_selector_rejects_stdout_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)
    candidate = replace(manifest, stdout=manifest.raw_events)

    with pytest.raises(ProtocolError) as failure:
        publisher.publish_target_replay(candidate, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "TEST_PROTOCOL_INVALID"
    assert failure.value.message == "Target replay manifests must not contain Host output artifacts"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_parent_type_selector_rejects_non_envelope_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, _descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-failed-before"
    )
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)

    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(manifest, None, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == "Target replay descriptor parent is invalid"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_target_replay_parent_count_selector_rejects_two_parents_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-parent-count"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-parent-count", original
    )
    second_parent = EvidenceEnvelope(
        identity=descriptor.identity,
        operation="target-replay-input-secondary",
        produced_at_utc=descriptor.produced_at_utc,
        parents=(),
        artifacts=descriptor.artifacts,
        metadata=dict(descriptor.metadata),
    )
    store.put_envelope(second_parent)
    _put_replay_graph(
        store,
        descriptor,
        original,
        original,
        manifest_artifact,
        parents=(str(descriptor.evidence_id), str(second_parent.evidence_id)),
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay envelope must have one descriptor parent",
        before_store,
        before_results,
    )


def test_target_replay_envelope_closure_selector_rejects_extra_key_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-envelope-closure"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-envelope-closure", original
    )
    metadata = _replay_metadata(descriptor, original, original, manifest_artifact)
    metadata["unexpected"] = "value"
    _put_replay_graph(
        store, descriptor, original, original, manifest_artifact, metadata=metadata
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay envelope metadata is not closed",
        before_store,
        before_results,
    )


def test_target_replay_operation_id_selector_rejects_metadata_run_id_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-operation-id"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-operation-id", original
    )
    metadata = _replay_metadata(descriptor, original, original, manifest_artifact)
    metadata["test_run_id"] = "vs03-other-run"
    _put_replay_graph(
        store, descriptor, original, original, manifest_artifact, metadata=metadata
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay operation ID contradicts the root",
        before_store,
        before_results,
    )


def test_target_replay_descriptor_id_format_selector_rejects_bad_id_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-descriptor-id-format"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-descriptor-id-format", original
    )
    metadata = _replay_metadata(descriptor, original, original, manifest_artifact)
    metadata["descriptor_evidence_id"] = "bad"
    _put_replay_graph(
        store, descriptor, original, original, manifest_artifact, metadata=metadata
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay descriptor evidence ID is invalid",
        before_store,
        before_results,
    )


def test_target_replay_descriptor_envelope_identity_selector_rejects_build_id_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-descriptor-envelope-identity"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-descriptor-envelope-identity", original
    )
    _put_replay_graph(
        store,
        descriptor,
        original,
        original,
        manifest_artifact,
        identity=replace(descriptor.identity, build_id="1" * 64),
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay descriptor identity contradicts the envelope",
        before_store,
        before_results,
    )


def test_target_replay_manifest_membership_selector_rejects_missing_manifest_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-membership"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-membership", original
    )
    _put_replay_graph(
        store,
        descriptor,
        original,
        original,
        manifest_artifact,
        artifacts=(original.raw_events,),
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay envelope has an invalid test manifest artifact",
        before_store,
        before_results,
    )


def test_target_replay_manifest_digest_selector_rejects_metadata_digest_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-digest"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-digest", original
    )
    metadata = _replay_metadata(descriptor, original, original, manifest_artifact)
    metadata["test_manifest_sha256"] = sha256(b"wrong-manifest").hexdigest()
    _put_replay_graph(
        store, descriptor, original, original, manifest_artifact, metadata=metadata
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest digest contradicts metadata",
        before_store,
        before_results,
    )


def test_target_replay_manifest_run_id_selector_rejects_changed_manifest_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-run-id"
    )
    persisted = replace(original, run_id="vs03-other-run")
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-run-id", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest run ID contradicts the root",
        before_store,
        before_results,
    )


def test_target_replay_manifest_mode_selector_rejects_mailbox_transport_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-mode"
    )
    persisted = replace(original, transport="mailbox")
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-mode", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest has the wrong execution mode",
        before_store,
        before_results,
    )


def test_target_replay_manifest_nonterminal_selector_rejects_running_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-nonterminal"
    )
    persisted = replace(original, state="running")
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-nonterminal", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest is not terminal",
        before_store,
        before_results,
    )


def test_target_replay_manifest_host_output_selector_rejects_stdout_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-host-output"
    )
    persisted = replace(original, stdout=original.raw_events)
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-host-output", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest contains Host output artifacts",
        before_store,
        before_results,
    )


def test_target_replay_manifest_identity_selector_rejects_build_id_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-identity"
    )
    persisted = replace(
        original,
        identity=replace(original.identity, build_id="1" * 64),
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-identity", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest identity contradicts its inputs",
        before_store,
        before_results,
    )


def test_target_replay_manifest_state_selector_rejects_public_passed_projection_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-manifest-state"
    )
    passed_cases = tuple(
        replace(case, state="passed", message=None) for case in original.cases
    )
    persisted = replace(original, state="passed", cases=passed_cases)
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-manifest-state", persisted
    )
    _put_replay_graph(
        store, descriptor, original, persisted, manifest_artifact
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay manifest state contradicts its descriptor",
        before_store,
        before_results,
    )


def test_target_replay_envelope_membership_selector_rejects_reordered_refs_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-envelope-membership"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-envelope-membership", original
    )
    _put_replay_graph(
        store,
        descriptor,
        original,
        original,
        manifest_artifact,
        artifacts=(original.raw_events, manifest_artifact),
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay envelope artifact membership is invalid",
        before_store,
        before_results,
    )


def test_target_replay_envelope_time_selector_rejects_changed_time_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-envelope-time"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-envelope-time", original
    )
    _put_replay_graph(
        store,
        descriptor,
        original,
        original,
        manifest_artifact,
        produced_at_utc=UTC_0,
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay envelope time contradicts the manifest",
        before_store,
        before_results,
    )


def test_target_replay_intent_digest_selector_rejects_wrong_digest_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, original = _fresh_replay_graph(
        tmp_path, "target-replay-intent-digest"
    )
    manifest_artifact = _ingest_replay_manifest(
        store, project_root, "target-replay-intent-digest", original
    )
    metadata = _replay_metadata(descriptor, original, original, manifest_artifact)
    metadata["operation_intent_sha256"] = sha256(b"wrong-intent").hexdigest()
    _put_replay_graph(
        store, descriptor, original, original, manifest_artifact, metadata=metadata
    )
    before_store, before_results = _replay_store_snapshot(store, results_root)

    _assert_replay_load_failure(
        store,
        results_root,
        original.run_id,
        "stored Target replay operation intent digest is invalid",
        before_store,
        before_results,
    )


def test_replay_descriptor_invalid_wire_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-descriptor-invalid-wire"
    )
    invalid_descriptor = _ingest_replay_bytes(
        store,
        project_root,
        "descriptor-invalid-wire",
        b"\xff",
        kind="target-replay-descriptor",
        media_type="application/json",
    )
    parent = replace(
        descriptor,
        artifacts=(invalid_descriptor, descriptor.artifacts[1]),
    )

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "stored Target replay descriptor is invalid",
    )


def test_replay_descriptor_noncanonical_wire_selector_rejects_without_write(
    tmp_path: Path,
):
    fixture, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-descriptor-noncanonical-wire"
    )
    canonical_payload = canonical_replay_json_bytes(
        fixture.descriptor.to_dict()
    )
    noncanonical_descriptor = _ingest_replay_bytes(
        store,
        project_root,
        "descriptor-noncanonical-wire-valid",
        canonical_payload + b" ",
        kind="target-replay-descriptor",
        media_type="application/json",
    )
    parent = replace(
        descriptor,
        artifacts=(noncanonical_descriptor, descriptor.artifacts[1]),
    )

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "stored Target replay descriptor is not canonical JSON",
    )


def test_replay_stream_inventory_identity_selector_rejects_without_write(
    tmp_path: Path,
):
    def mutate(kind: int, payload: dict[str, object]) -> None:
        if kind == 1:
            identity = dict(payload["identity"])
            identity["workspace_id"] = "1" * 64
            payload["identity"] = identity

    store, project_root, results_root, parent, manifest = _replay_stream_variant(
        tmp_path, "stream-inventory-identity", mutate
    )
    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "stored Target replay stream identity contradicts its descriptor",
    )


def test_replay_stream_terminal_state_selector_rejects_without_write(
    tmp_path: Path,
):
    def mutate(kind: int, payload: dict[str, object]) -> None:
        if kind == 5:
            payload["state"] = "passed"

    store, project_root, results_root, parent, manifest = _replay_stream_variant(
        tmp_path, "stream-terminal-state", mutate
    )
    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "stored Target replay stream terminal state contradicts its descriptor",
    )


def test_replay_raw_ref_provider_invalid_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-raw-ref-provider-invalid"
    )
    invalid_raw = replace(manifest.raw_events, relative_path="objects/not-content-addressed")
    candidate = replace(manifest, raw_events=invalid_raw)

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        candidate,
        descriptor,
        "Target replay raw event artifact is invalid",
    )


def test_replay_parent_operation_ancestry_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-parent-operation-ancestry"
    )
    parent = replace(descriptor, operation="other-operation")

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "Target replay descriptor parent operation or ancestry is invalid",
    )


def test_replay_parent_artifact_absent_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-parent-artifact-absent"
    )
    descriptor_path = _artifact_path(store, descriptor.artifacts[0])
    descriptor_path.unlink()
    publisher = Publisher(store, project_root, results_root)
    before_store, before_results = _replay_store_snapshot(store, results_root)

    with pytest.raises(EvidenceValidationError) as failure:
        publisher.publish_target_replay(manifest, descriptor, IMPORT_WORKSPACE_ID)

    assert failure.value.code == "EVIDENCE_CORRUPT"
    assert failure.value.message == "evidence artifact object is absent"
    assert _tree_bytes(store.root) == before_store
    assert _tree_bytes(results_root) == before_results


def test_replay_parent_artifact_path_invalid_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-parent-artifact-path-invalid"
    )
    invalid_descriptor = replace(
        descriptor.artifacts[0], relative_path="objects/not-content-addressed"
    )
    parent = replace(
        descriptor,
        artifacts=(invalid_descriptor, descriptor.artifacts[1]),
    )

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "Target replay descriptor parent artifact is invalid",
    )


def test_replay_parent_stream_size_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-parent-stream-size"
    )
    metadata = dict(descriptor.metadata)
    metadata["stream_size_bytes"] = -1
    parent = replace(descriptor, metadata=metadata)

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "Target replay parent stream size metadata is invalid",
    )


def test_replay_parent_stream_ref_selector_rejects_without_write(
    tmp_path: Path,
):
    _fixture_value, store, project_root, results_root, descriptor, manifest = _bundle(
        tmp_path, name="failed-before", operation_id="vs03-parent-stream-ref"
    )
    alternate_stream = _ingest_replay_bytes(
        store,
        project_root,
        "parent-stream-ref-alternate",
        b"alternate target replay stream",
        kind="target-replay-stream",
        media_type="application/octet-stream",
    )
    parent = replace(
        descriptor,
        artifacts=(descriptor.artifacts[0], alternate_stream),
    )

    _assert_replay_publish_failure(
        store,
        project_root,
        results_root,
        manifest,
        parent,
        "Target replay binary stream artifact contradicts its descriptor",
    )
