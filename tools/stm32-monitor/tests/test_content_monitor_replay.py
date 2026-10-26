"""Snapshot provenance through Monitor replay import and publication.

Every case uses disposable synthetic recorded or fake-capture data.  No
hardware transport is constructed: the physical journey publishes a fake
TestRun and fake History window through the normal public workflow.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    INCOMPATIBLE_IDENTITY,
    MAX_PHYSICAL_TRANSCRIPT_BYTES,
    MAX_REPLAY_DOCUMENT_BYTES,
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.monitor_replay_contract import (
    ReplayContractError,
    validate_replay_document,
    validate_run_reference,
)
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.model import TestCaseResult as _TestCaseResult
from stm32_toolkit.testing.model import TestRunManifest as _TestRunManifest
from stm32_toolkit.testing.model import (
    calculate_inventory_digest as _calculate_inventory_digest,
)
from stm32_toolkit.testing.publication import TestRunPublisher as _TestRunPublisher


FIXTURES = Path(__file__).parent / "fixtures" / "vs03"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
RUN_IDS = {
    "failed-before": UUID("33333333-3333-4333-8333-333333333333"),
    "fixed-after": UUID("44444444-4444-4444-8444-444444444444"),
}
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
PHYSICAL_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
PHYSICAL_GROUP_ID = UUID("22222222-2222-4222-8222-222222222222")
SOURCE_BASELINE = "input-snapshot-v1"
GIT_EVIDENCE = {"status": "unavailable", "code": "BUILD_GIT_INVALID", "rule": "head"}
STATUS_EVIDENCE = {"status": "unavailable", "code": "BUILD_GIT_INVALID", "rule": "status"}
SNAPSHOT_SHA256 = "9" * 64
CAPTURED_BASE_NS = 1_700_000_000_000_000_000
PROVENANCE_FIELDS = frozenset({"source_baseline", "git_evidence"})
_PROJECT_MANIFEST = {
    "schemaVersion": 3,
    "logicalProjectId": str(PROJECT_ID),
    "generatedBy": {"tool": "stm32-toolkit", "version": "0.6"},
    "project": {"name": "physical-monitor", "origin": "manual"},
    "target": {"device": "stm32:stm32f429zi", "core": "cortex-m4"},
    "framework": {"type": "bare-metal", "version": None},
    "build": {
        "sources": [],
        "includePaths": [],
        "defines": [],
        "compileOptions": [],
        "assemblySources": [],
        "presets": [],
        "elf": None,
    },
    "memory": {"source": "manual", "regions": []},
    "debug": {"backend": "pyocd", "target": "board:fixture-01", "svd": None},
    "generation": {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    },
}


def _paths(tmp_path: Path, session_id: str = "replay-import") -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, PROJECT_ID, session_id)


def _evidence(paths: WorkspacePaths) -> EvidenceStore:
    return EvidenceStore(paths.workspace_root / "evidence")


def _fixture_bytes(role: str) -> bytes:
    raw = (FIXTURES / f"{role}.json").read_bytes()
    assert raw.endswith(b"\n")
    return raw


def _fixture_document(role: str = "failed-before") -> dict[str, object]:
    return json.loads(_fixture_bytes(role)[:-1].decode("utf-8"))


def _redigest_document(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "fixture_sha256"}
    payload["fixture_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()


def _redigest_reference(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "run_ref_sha256"}
    payload["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()


def _snapshot_binding(
    binding: dict[str, object],
    *,
    input_snapshot_sha256: str = SNAPSHOT_SHA256,
    source_baseline: object = SOURCE_BASELINE,
    git_evidence: object = GIT_EVIDENCE,
) -> dict[str, object]:
    return {
        **binding,
        "inputSnapshotSha256": input_snapshot_sha256,
        "gitHead": None,
        "gitDirty": None,
        "sourceBaseline": source_baseline,
        "gitEvidence": dict(git_evidence) if isinstance(git_evidence, dict) else git_evidence,
    }


def _snapshot_document(
    role: str = "failed-before",
    *,
    input_snapshot_sha256: str = SNAPSHOT_SHA256,
    git_evidence: object = GIT_EVIDENCE,
) -> dict[str, object]:
    payload = deepcopy(_fixture_document(role))
    binding = _snapshot_binding(
        payload["binding"],
        input_snapshot_sha256=input_snapshot_sha256,
        git_evidence=git_evidence,
    )
    payload["binding"] = binding
    for batch in payload["batches"]:
        batch["binding"] = deepcopy(binding)
    _redigest_document(payload)
    return payload


def _write_document(tmp_path: Path, payload: dict[str, object], name: str) -> Path:
    target = tmp_path / name
    target.write_bytes(canonical_replay_json_bytes(payload) + b"\n")
    return target


def _read_batches(paths: WorkspacePaths, run_id: UUID) -> tuple[SampleBatch, ...]:
    history = HistoryStore(paths)
    try:
        result = history.query_history(
            HistoryQuery(
                session_id=paths.session_id,
                start_ns=0,
                end_ns=(1 << 63) - 1,
                run_id=run_id,
                limit=10_000,
            )
        )
    finally:
        history.close()
    assert result.ok, result.to_dict()
    assert result.data is not None
    assert result.data.next_cursor is None
    return tuple(
        SampleBatch(
            binding=slice_.binding,
            group_id=slice_.group_id,
            group_revision=slice_.group_revision,
            run_id=slice_.run_id,
            sequence=slice_.sequence,
            scheduled_unix_ns=slice_.scheduled_unix_ns,
            captured_unix_ns=slice_.captured_unix_ns,
            latency_ns=slice_.latency_ns,
            actual_rate_hz=slice_.actual_rate_hz,
            subscriber_drops=slice_.subscriber_drops,
            history_drops=slice_.history_drops,
            deadline_drops=slice_.deadline_drops,
            values=slice_.values,
        )
        for slice_ in result.data.batches
    )


def _root_files(evidence: EvidenceStore, root_type: str) -> tuple[Path, ...]:
    return tuple((evidence.root / "roots" / root_type).glob("*.json"))


def _transcript_artifact_path(evidence: EvidenceStore, operation: str) -> Path:
    root = get_root(evidence, "monitor-run", operation)
    envelope = evidence.get_envelope(root.manifest_id)
    artifact = envelope.artifacts[0]
    return evidence.root.joinpath(*artifact.relative_path.split("/"))


@pytest.fixture(scope="module")
def legacy_reference_payload(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    base = tmp_path_factory.mktemp("legacy-reference")
    paths = _paths(base)
    reference = ingest_monitor_replay(
        paths,
        _evidence(paths),
        str(RUN_IDS["failed-before"]),
        FIXTURES / "failed-before.json",
    )
    return reference.to_dict()


@pytest.fixture(scope="module")
def snapshot_reference_payload(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    base = tmp_path_factory.mktemp("snapshot-reference")
    paths = _paths(base)
    document = _snapshot_document()
    target = _write_document(base, document, "snapshot.json")
    reference = ingest_monitor_replay(
        paths,
        _evidence(paths),
        str(RUN_IDS["failed-before"]),
        target,
    )
    return reference.to_dict()


def test_snapshot_replay_import_carries_the_pair_end_to_end(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = str(RUN_IDS["failed-before"])
    document = _snapshot_document()
    target = _write_document(tmp_path, document, "snapshot.json")

    reference = ingest_monitor_replay(paths, evidence, operation, target)

    assert type(reference) is MonitorRunRef
    assert reference.source_baseline == SOURCE_BASELINE
    assert reference.git_head is None and reference.git_dirty is None
    assert reference.git_evidence == GIT_EVIDENCE
    assert isinstance(reference.git_evidence, MappingProxyType)
    with pytest.raises(TypeError):
        reference.git_evidence["rule"] = "status"  # type: ignore[index]

    payload = reference.to_dict()
    expected = deepcopy(payload)
    assert payload["source_baseline"] == SOURCE_BASELINE
    assert payload["git_evidence"] == GIT_EVIDENCE
    assert payload["git_head"] is None and payload["git_dirty"] is None
    unsigned = {key: value for key, value in payload.items() if key != "run_ref_sha256"}
    assert payload["run_ref_sha256"] == sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    assert validate_run_reference(payload) == payload
    assert validate_replay_document(document) == document
    payload["git_evidence"]["rule"] = "status"  # type: ignore[index]
    assert reference.to_dict()["git_evidence"] == GIT_EVIDENCE

    envelope = evidence.get_envelope(
        get_root(evidence, "monitor-run", operation).manifest_id
    )
    assert envelope.identity.source_baseline == SOURCE_BASELINE
    assert dict(envelope.identity.git_evidence or {}) == GIT_EVIDENCE
    assert envelope.identity.git_commit is None
    assert envelope.identity.git_dirty is None
    stored = evidence.read_artifact(
        envelope.artifacts[0],
        maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
    )
    assert stored == target.read_bytes()

    batches = _read_batches(paths, RUN_IDS["failed-before"])
    assert len(batches) == 2
    for batch in batches:
        assert batch.binding.source_baseline == SOURCE_BASELINE
        assert dict(batch.binding.git_evidence or {}) == GIT_EVIDENCE
        assert batch.binding.git_head is None and batch.binding.git_dirty is None
    assert reference.projected_batch_sha256s == tuple(
        sha256(canonical_replay_json_bytes(batch.to_dict())).hexdigest()
        for batch in batches
    )

    retry = ingest_monitor_replay(paths, evidence, operation, target)
    assert retry.to_dict() == expected
    assert _read_batches(paths, RUN_IDS["failed-before"]) == batches


def test_legacy_replay_import_keeps_exact_bytes_and_reference_keys(
    tmp_path: Path,
    legacy_reference_payload: dict[str, object],
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = str(RUN_IDS["failed-before"])
    target = FIXTURES / "failed-before.json"
    raw = _fixture_bytes("failed-before")

    reference = ingest_monitor_replay(paths, evidence, operation, target)

    assert type(reference) is MonitorRunRef
    assert reference.source_baseline is None and reference.git_evidence is None
    assert set(reference.to_dict()) == set(legacy_reference_payload)
    assert set(reference.to_dict()).isdisjoint(PROVENANCE_FIELDS)
    assert canonical_replay_json_bytes(_fixture_document()) + b"\n" == raw

    envelope = evidence.get_envelope(
        get_root(evidence, "monitor-run", operation).manifest_id
    )
    assert envelope.identity.source_baseline is None
    assert envelope.identity.git_evidence is None
    assert evidence.read_artifact(
        envelope.artifacts[0],
        maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
    ) == raw

    reference_root = get_root(evidence, "monitor-run-ref", operation)
    reference_bytes = evidence.read_artifact(
        evidence.get_envelope(reference_root.manifest_id).artifacts[0],
        maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
    )
    assert reference_bytes == canonical_replay_json_bytes(reference.to_dict())
    assert b"source_baseline" not in reference_bytes
    assert b"git_evidence" not in reference_bytes


_SNAPSHOT_BINDING_MUTATIONS = (
    ("partial-baseline", lambda binding: binding.pop("sourceBaseline")),
    ("partial-evidence", lambda binding: binding.pop("gitEvidence")),
    ("present-null-baseline", lambda binding: binding.update(sourceBaseline=None)),
    ("present-null-evidence", lambda binding: binding.update(gitEvidence=None)),
    ("mixed-git-head", lambda binding: binding.update(gitHead="b" * 40)),
    ("mixed-git-dirty", lambda binding: binding.update(gitDirty=False)),
    ("forged-baseline", lambda binding: binding.update(sourceBaseline="git")),
    (
        "forged-evidence-code",
        lambda binding: binding.update(gitEvidence=dict(GIT_EVIDENCE, code="OTHER")),
    ),
    (
        "forged-evidence-rule",
        lambda binding: binding.update(gitEvidence=dict(GIT_EVIDENCE, rule="branch")),
    ),
    (
        "extra-evidence-key",
        lambda binding: binding.update(gitEvidence=dict(GIT_EVIDENCE, extra="value")),
    ),
    ("unknown-key", lambda binding: binding.update(sourceBaselineExtra="value")),
    (
        "downgraded-legacy",
        lambda binding: (
            binding.pop("sourceBaseline"),
            binding.pop("gitEvidence"),
            binding.update(gitHead=None, gitDirty=None),
        ),
    ),
)


@pytest.mark.parametrize(
    ("case", "mutate"),
    _SNAPSHOT_BINDING_MUTATIONS,
    ids=[case for case, _ in _SNAPSHOT_BINDING_MUTATIONS],
)
def test_snapshot_replay_binding_rejects_partial_mixed_and_forged_forms(
    case: str,
    mutate,
) -> None:
    payload = _snapshot_document()
    binding = payload["binding"]
    assert isinstance(binding, dict)
    mutate(binding)
    for batch in payload["batches"]:
        batch["binding"] = deepcopy(binding)
    _redigest_document(payload)
    before = deepcopy(payload)

    with pytest.raises(ReplayContractError):
        validate_replay_document(payload)
    with pytest.raises(MonitorReplayError) as error:
        MonitorReplayDocument.from_value(payload)

    assert error.value.code == "MONITOR_REPLAY_INVALID"
    assert payload == before, case


_SNAPSHOT_REFERENCE_MUTATIONS = (
    ("partial-baseline", lambda wire: wire.pop("source_baseline")),
    ("partial-evidence", lambda wire: wire.pop("git_evidence")),
    ("present-null-baseline", lambda wire: wire.update(source_baseline=None)),
    ("present-null-evidence", lambda wire: wire.update(git_evidence=None)),
    ("mixed-git-head", lambda wire: wire.update(git_head="b" * 40)),
    ("mixed-git-dirty", lambda wire: wire.update(git_dirty=False)),
    ("forged-baseline", lambda wire: wire.update(source_baseline="git")),
    (
        "namespaced-git-head",
        lambda wire: wire.update(git_head=f"input-snapshot-v1:{SNAPSHOT_SHA256}"),
    ),
    (
        "forged-evidence-status",
        lambda wire: wire.update(git_evidence=dict(GIT_EVIDENCE, status="available")),
    ),
    (
        "extra-evidence-key",
        lambda wire: wire.update(git_evidence=dict(GIT_EVIDENCE, extra="value")),
    ),
    ("unknown-key", lambda wire: wire.update(git_evidence_extra="value")),
    (
        "downgraded-legacy",
        lambda wire: (
            wire.pop("source_baseline"),
            wire.pop("git_evidence"),
            wire.update(git_head=None, git_dirty=None),
        ),
    ),
)


def _v2_physical_snapshot_wire(v1_wire: dict[str, object]) -> dict[str, object]:
    """Project one valid v1 snapshot reference onto the physical v2 form."""
    wire = deepcopy(v1_wire)
    wire.pop("fixture_sha256")
    wire["schema"] = "stm32-monitor-run-ref/2"
    wire["execution_source"] = "physical"
    wire["physical_transport_evidence"] = True
    wire["probe_id"] = sha256(b"probe/serial/01").hexdigest()
    wire["physical_target"] = "stm32f429zi"
    wire["flash_session_id"] = "flash-session-01"
    wire["lease_id"] = "lease-01"
    wire["import_workspace_id"] = wire["origin_workspace_id"]
    wire["projected_session_id"] = wire["origin_session_id"]
    wire["projected_run_id"] = wire["origin_run_id"]
    wire["source_record_sha256"] = "2" * 64
    _redigest_reference(wire)
    return wire


@pytest.mark.parametrize("version", ("v1", "v2"))
@pytest.mark.parametrize(
    ("case", "mutate"),
    _SNAPSHOT_REFERENCE_MUTATIONS,
    ids=[case for case, _ in _SNAPSHOT_REFERENCE_MUTATIONS],
)
def test_snapshot_run_reference_rejects_partial_mixed_and_forged_forms(
    case: str,
    mutate,
    version: str,
    snapshot_reference_payload: dict[str, object],
) -> None:
    if version == "v1":
        wire = deepcopy(snapshot_reference_payload)
    else:
        wire = _v2_physical_snapshot_wire(snapshot_reference_payload)
        assert validate_run_reference(wire) == wire
    mutate(wire)
    _redigest_reference(wire)
    before = deepcopy(wire)

    with pytest.raises(ReplayContractError):
        validate_run_reference(wire)
    with pytest.raises(MonitorReplayError) as error:
        MonitorRunRef.from_value(wire)
    assert error.value.code == "MONITOR_REPLAY_INVALID"
    if version == "v2":
        with pytest.raises(MonitorReplayError) as versioned:
            MonitorRunRefV2.from_value(wire)
        assert versioned.value.code == "MONITOR_REPLAY_INVALID"
    assert wire == before, case


@pytest.mark.parametrize(
    "mutation",
    ("batch-elf", "batch-snapshot", "batch-pair", "document-probe"),
)
def test_snapshot_replay_rejects_identity_mismatch_before_publication(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = str(RUN_IDS["failed-before"])
    payload = _snapshot_document()
    if mutation == "batch-elf":
        payload["batches"][1]["binding"]["elfSha256"] = "0" * 64
    elif mutation == "batch-snapshot":
        payload["batches"][1]["binding"]["inputSnapshotSha256"] = "0" * 64
    elif mutation == "batch-pair":
        payload["batches"][1]["binding"]["gitEvidence"] = dict(STATUS_EVIDENCE)
    else:
        payload["binding"]["probeId"] = "replay:probe-v3"
        for batch in payload["batches"]:
            batch["binding"]["probeId"] = "replay:probe-v3"
    _redigest_document(payload)
    target = _write_document(tmp_path, payload, f"{mutation}.json")

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, target)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _root_files(evidence, "monitor-run") == ()
    assert _root_files(evidence, "monitor-run-ref") == ()
    assert _read_batches(paths, RUN_IDS["failed-before"]) == ()


def test_snapshot_replay_rejects_tampered_published_transcript(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = str(RUN_IDS["failed-before"])
    document = _snapshot_document()
    target = _write_document(tmp_path, document, "snapshot.json")
    ingest_monitor_replay(paths, evidence, operation, target)
    batches = _read_batches(paths, RUN_IDS["failed-before"])

    tampered = deepcopy(document)
    tampered["binding"]["gitEvidence"] = dict(STATUS_EVIDENCE)
    for batch in tampered["batches"]:
        batch["binding"]["gitEvidence"] = dict(STATUS_EVIDENCE)
    _redigest_document(tampered)
    _transcript_artifact_path(evidence, operation).write_bytes(
        canonical_replay_json_bytes(tampered) + b"\n"
    )

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, target)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _read_batches(paths, RUN_IDS["failed-before"]) == batches


def _physical_paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".stm32-project.json").write_text(
        json.dumps(_PROJECT_MANIFEST, sort_keys=True),
        encoding="utf-8",
    )
    return WorkspacePaths.from_roots(
        tmp_path / "state",
        project,
        PROJECT_ID,
        "physical-monitor",
    )


def _publish_snapshot_test_run(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    *,
    test_run_id: str,
    raw_probe: str,
    git_evidence: dict[str, str] = GIT_EVIDENCE,
    build_id: str = "b" * 64,
    elf_sha256: str = "c" * 64,
) -> None:
    identity = EvidenceIdentity(
        workspace_id=paths.workspace_id,
        project_id=str(PROJECT_ID),
        session_id=paths.session_id,
        build_id=build_id,
        elf_sha256=elf_sha256,
        target_device="stm32:stm32f429zi",
        input_snapshot_sha256=SNAPSHOT_SHA256,
        git_commit=None,
        git_dirty=None,
        source_baseline=SOURCE_BASELINE,
        git_evidence=dict(git_evidence),
    )
    case_id = "case.counter"
    stored_inventory_digest = _calculate_inventory_digest("target", identity, (case_id,))
    raw_source = paths.project_root / "events.bin"
    raw_source.write_bytes(b"physical-events")
    raw_events = evidence.ingest_file(
        raw_source,
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    manifest = _TestRunManifest(
        "stm32-test/1",
        test_run_id,
        "target",
        "failed",
        identity,
        "semihosting",
        (
            _TestCaseResult(
                case_id,
                "failed",
                "2026-08-22T00:00:00.000000Z",
                "2026-08-22T00:00:00.001000Z",
                1,
                "expected failure",
                None,
                None,
            ),
        ),
        "2026-08-22T00:00:00.000000Z",
        "2026-08-22T00:00:00.001000Z",
        1,
        None,
        None,
        raw_events,
    )
    manifest_source = paths.project_root / "manifest.json"
    manifest_source.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = evidence.ingest_file(
        manifest_source,
        kind="test-manifest",
        media_type="application/json",
    )
    digest = sha256(b"physical-action").hexdigest()
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-physical",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, raw_events),
        metadata={
            "action_digest": digest,
            "execution_source": "physical",
            "flash_session_id": "flash-session-01",
            "import_session_id": paths.session_id,
            "import_workspace_id": paths.workspace_id,
            "intent_digest": digest,
            "inventory_digest": stored_inventory_digest,
            "lease_id": "lease-01",
            "origin_session_id": paths.session_id,
            "origin_workspace_id": paths.workspace_id,
            "physical_transport_evidence": True,
            "probe_id": sha256(raw_probe.encode("utf-8")).hexdigest(),
            "target_id": identity.target_device,
            "transport_config_digest": "2" * 64,
        },
    )
    evidence.put_envelope(envelope)
    _TestRunPublisher(
        evidence,
        paths.project_root,
        paths.data_root / "results",
    ).publish_target_physical(manifest, envelope)


def _append_snapshot_history(
    paths: WorkspacePaths,
    raw_probe: str,
    *,
    git_evidence: dict[str, str] = GIT_EVIDENCE,
    build_id: str = "b" * 64,
    elf_sha256: str = "c" * 64,
) -> tuple[SampleBatch, ...]:
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id=str(PROJECT_ID),
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id=build_id,
        elf_sha256=elf_sha256,
        input_snapshot_sha256=SNAPSHOT_SHA256,
        git_head=None,
        git_dirty=None,
        flash_session_id="flash-session-01",
        lease_id="lease-01",
        dwarf_sha256="f" * 64,
        svd_sha256=None,
        source_baseline=SOURCE_BASELINE,
        git_evidence=dict(git_evidence),
    )
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=PHYSICAL_GROUP_ID,
            group_revision=1,
            run_id=PHYSICAL_RUN_ID,
            sequence=sequence,
            scheduled_unix_ns=CAPTURED_BASE_NS + sequence * 1_000_000,
            captured_unix_ns=CAPTURED_BASE_NS + sequence * 1_000_000 + 100,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": sequence},
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(paths)
    try:
        appended = history.append_batches(batches)
        assert appended.ok, appended.to_dict()
    finally:
        history.close()
    return batches


def _publish_physical(paths: WorkspacePaths, evidence: EvidenceStore) -> MonitorRunRefV2:
    return publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id="physical-test-run-01",
        run_id=str(PHYSICAL_RUN_ID),
        group_id=str(PHYSICAL_GROUP_ID),
        start_sequence=0,
        end_sequence_exclusive=2,
        start_captured_unix_ns=CAPTURED_BASE_NS + 100,
        end_captured_unix_ns_exclusive=CAPTURED_BASE_NS + 1_000_000 + 101,
        probe_id="probe/serial/01",
    )


def test_snapshot_physical_publication_carries_pair_and_is_idempotent(
    tmp_path: Path,
) -> None:
    paths = _physical_paths(tmp_path)
    evidence = _evidence(paths)
    _publish_snapshot_test_run(
        paths,
        evidence,
        test_run_id="physical-test-run-01",
        raw_probe="probe/serial/01",
    )
    _append_snapshot_history(paths, "probe/serial/01")

    reference = _publish_physical(paths, evidence)

    assert type(reference) is MonitorRunRefV2
    assert reference.source_baseline == SOURCE_BASELINE
    assert reference.git_head is None and reference.git_dirty is None
    assert reference.git_evidence == GIT_EVIDENCE
    payload = reference.to_dict()
    assert payload["source_baseline"] == SOURCE_BASELINE
    assert payload["git_evidence"] == GIT_EVIDENCE
    assert payload["git_head"] is None and payload["git_dirty"] is None
    assert set(payload) - PROVENANCE_FIELDS == (
        set(_v1_legacy_reference_fields()) - {"fixture_sha256"}
    ) | {"source_record_sha256"}
    assert validate_run_reference(payload) == payload
    assert load_monitor_run_reference(
        paths,
        evidence,
        str(PHYSICAL_RUN_ID),
    ).to_dict() == payload

    operation = str(PHYSICAL_RUN_ID)
    envelope = evidence.get_envelope(
        get_root(evidence, "monitor-run", operation).manifest_id
    )
    assert envelope.identity.source_baseline == SOURCE_BASELINE
    assert dict(envelope.identity.git_evidence or {}) == GIT_EVIDENCE
    assert envelope.identity.git_commit is None
    assert envelope.identity.git_dirty is None
    transcript = json.loads(
        evidence.read_artifact(
            envelope.artifacts[0],
            maximum_bytes=MAX_PHYSICAL_TRANSCRIPT_BYTES,
        )
    )
    assert transcript["execution_source"] == "physical"
    assert transcript["binding"]["sourceBaseline"] == SOURCE_BASELINE
    assert transcript["binding"]["gitEvidence"] == GIT_EVIDENCE
    assert transcript["binding"]["gitHead"] is None
    assert transcript["binding"]["gitDirty"] is None

    retry = _publish_physical(paths, evidence)
    assert retry.to_dict() == payload


def _v1_legacy_reference_fields() -> set[str]:
    # The v1 and v2 reference forms differ only in their recorded source digest.
    from stm32_monitor.replay import _REF_FIELDS

    return set(_REF_FIELDS)


@pytest.mark.parametrize("mutation", ("pair", "elf"))
def test_snapshot_physical_publication_rejects_identity_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _physical_paths(tmp_path)
    evidence = _evidence(paths)
    _publish_snapshot_test_run(
        paths,
        evidence,
        test_run_id="physical-test-run-01",
        raw_probe="probe/serial/01",
    )
    if mutation == "pair":
        _append_snapshot_history(
            paths,
            "probe/serial/01",
            git_evidence=STATUS_EVIDENCE,
        )
    else:
        _append_snapshot_history(paths, "probe/serial/01", elf_sha256="e" * 64)

    with pytest.raises(MonitorReplayError) as error:
        _publish_physical(paths, evidence)

    assert error.value.code == INCOMPATIBLE_IDENTITY
    assert _root_files(evidence, "monitor-run") == ()
    assert _root_files(evidence, "monitor-run-ref") == ()
