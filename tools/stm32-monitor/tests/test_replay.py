from __future__ import annotations

import builtins
import copy
import importlib
import json
import os
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor import replay as replay_module
from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.models import MAX_SIGNED_INT64, ObservationBinding, SampleBatch
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    MONITOR_REPLAY_SCHEMA,
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.evidence.gc import get_root, plan_gc
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.model import EvidenceValidationError
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.replay import load_target_replay_fixture


FIXTURES = Path(__file__).parent / "fixtures" / "vs03"
LOGICAL_PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
RUN_IDS = {
    "failed-before": UUID("33333333-3333-4333-8333-333333333333"),
    "fixed-after": UUID("44444444-4444-4444-8444-444444444444"),
}


def _paths(tmp_path: Path, session_id: str = "replay-import") -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(
        tmp_path / "state", project, LOGICAL_PROJECT_ID, session_id
    )


def _evidence(paths: WorkspacePaths) -> EvidenceStore:
    return EvidenceStore(paths.workspace_root / "evidence")


def _fixture(role: str) -> Path:
    return FIXTURES / f"{role}.json"


def _raw_fixture(role: str) -> bytes:
    return _fixture(role).read_bytes()


def _document(role: str) -> MonitorReplayDocument:
    raw = _raw_fixture(role)
    assert raw.endswith(b"\n")
    return MonitorReplayDocument.from_value(json.loads(raw[:-1].decode("utf-8")))


def _operation(role: str) -> str:
    return str(RUN_IDS[role])


def _history_batches(paths: WorkspacePaths, run_id: UUID):
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
        assert result.ok, result.to_dict()
        assert result.data is not None
        assert result.data.next_cursor is None
        return tuple(
            SampleBatch(
                binding=batch.binding,
                group_id=batch.group_id,
                group_revision=batch.group_revision,
                run_id=batch.run_id,
                sequence=batch.sequence,
                scheduled_unix_ns=batch.scheduled_unix_ns,
                captured_unix_ns=batch.captured_unix_ns,
                latency_ns=batch.latency_ns,
                actual_rate_hz=batch.actual_rate_hz,
                subscriber_drops=batch.subscriber_drops,
                history_drops=batch.history_drops,
                deadline_drops=batch.deadline_drops,
                values=batch.values,
            )
            for batch in result.data.batches
        )
    finally:
        history.close()


def _rewrite_document(
    tmp_path: Path,
    source_role: str,
    mutate,
    name: str,
) -> Path:
    payload = json.loads(_raw_fixture(source_role)[:-1].decode("utf-8"))
    mutate(payload)
    unsigned = dict(payload)
    unsigned.pop("fixture_sha256")
    payload["fixture_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    target = tmp_path / name
    target.write_bytes(canonical_replay_json_bytes(payload) + b"\n")
    return target


def _assert_no_history(paths: WorkspacePaths, run_id: UUID) -> None:
    assert _history_batches(paths, run_id) == ()


def _root_path(evidence: EvidenceStore, root_type: str) -> Path:
    files = tuple((evidence.root / "roots" / root_type).glob("*.json"))
    assert len(files) == 1
    return files[0]


def _manifest_path(evidence: EvidenceStore, evidence_id: str) -> Path:
    return evidence.root / "manifests" / f"{evidence_id}.json"


def _object_path(evidence: EvidenceStore, relative_path: str) -> Path:
    return evidence.root.joinpath(*relative_path.split("/"))


def test_replay_fixtures_are_canonical_closed_documents_and_share_scope() -> None:
    before = _document("failed-before")
    after = _document("fixed-after")

    assert MONITOR_REPLAY_SCHEMA == "stm32-monitor-replay/1"
    assert [field.name for field in fields(MonitorReplayDocument)] == [
        "schema",
        "source",
        "physical_transport_evidence",
        "scenario_role",
        "binding",
        "batches",
        "fixture_sha256",
    ]
    assert before.source == after.source == "toolkit-generated-probe-v2-replay"
    assert before.physical_transport_evidence is False
    assert after.physical_transport_evidence is False
    assert before.scenario_role == "failed-before"
    assert after.scenario_role == "fixed-after"
    assert before.binding.logical_project_id == after.binding.logical_project_id
    assert before.binding.target_device == after.binding.target_device
    assert before.binding.git_dirty is False and after.binding.git_dirty is False
    assert before.binding.probe_id == after.binding.probe_id == "replay:probe-v2"
    assert before.binding.physical_target == after.binding.physical_target == "replay:non-physical"
    assert before.binding.flash_session_id == after.binding.flash_session_id == "replay:no-flash"
    assert before.binding.lease_id == after.binding.lease_id == "replay:no-lease"
    assert len(before.batches) == len(after.batches) == 2
    assert [batch.sequence for batch in before.batches] == [0, 1]
    assert [batch.sequence for batch in after.batches] == [0, 1]
    assert [len(batch.values) for batch in before.batches] == [2, 2]
    assert [len(batch.values) for batch in after.batches] == [2, 2]
    assert [batch.run_id for batch in before.batches] == [RUN_IDS["failed-before"]] * 2
    assert [batch.run_id for batch in after.batches] == [RUN_IDS["fixed-after"]] * 2
    assert [batch.binding.build_id for batch in before.batches] == [before.binding.build_id] * 2
    assert before.binding.workspace_id == after.binding.workspace_id
    assert before.binding.session_id == after.binding.session_id
    assert before.binding.build_id != after.binding.build_id
    assert before.binding.elf_sha256 != after.binding.elf_sha256
    assert before.binding.input_snapshot_sha256 != after.binding.input_snapshot_sha256
    assert before.binding.git_head != after.binding.git_head

    target_fixtures = Path(__file__).parents[2] / "stm32-toolkit" / "tests" / "fixtures" / "vs03" / "target"
    for role, monitor_document in (("failed-before", before), ("fixed-after", after)):
        target_fixture = load_target_replay_fixture(
            target_fixtures / f"{role}.json",
            target_fixtures / f"{role}.hex",
        )
        target_identity = target_fixture.descriptor.identity
        assert monitor_document.binding.logical_project_id == target_identity.project_id
        assert monitor_document.binding.workspace_id == target_identity.workspace_id
        assert monitor_document.binding.target_device == target_identity.target_device
        assert monitor_document.binding.build_id == target_identity.build_id
        assert monitor_document.binding.elf_sha256 == target_identity.elf_sha256
        assert monitor_document.binding.input_snapshot_sha256 == target_identity.input_snapshot_sha256
        assert monitor_document.binding.git_head == target_identity.git_commit
        assert monitor_document.binding.git_dirty == target_identity.git_dirty

    for role, document in (("failed-before", before), ("fixed-after", after)):
        raw = _raw_fixture(role)
        assert raw == canonical_replay_json_bytes(document.to_dict()) + b"\n"
        copied = document.to_dict()
        copied["binding"]["workspaceId"] = "0" * 64
        copied["batches"][0]["values"][0]["typedValue"]["value"] = -1
        assert document.binding.workspace_id != copied["binding"]["workspaceId"]
        assert document.batches[0].values[0].typed_value["value"] != -1


def test_replay_parser_and_shared_contract_use_identical_wire_bytes() -> None:
    try:
        contract = importlib.import_module("stm32_toolkit.monitor_replay_contract")
    except ModuleNotFoundError:
        pytest.fail("shared replay wire contract is not implemented")
    payload = json.loads(_raw_fixture("failed-before")[:-1].decode("utf-8"))
    before = copy.deepcopy(payload)
    assert contract.validate_replay_document(payload) == payload
    assert canonical_replay_json_bytes(payload) == contract.canonical_replay_json_bytes(payload)
    assert payload == before


def test_monitor_run_ref_has_exact_closed_fields_and_round_trips_digest() -> None:
    assert [field.name for field in fields(MonitorRunRef)] == [
        "schema",
        "operation_id",
        "scenario_role",
        "execution_source",
        "physical_transport_evidence",
        "origin_workspace_id",
        "import_workspace_id",
        "logical_project_id",
        "origin_session_id",
        "projected_session_id",
        "origin_run_id",
        "projected_run_id",
        "target_device",
        "probe_id",
        "physical_target",
        "build_id",
        "elf_sha256",
        "input_snapshot_sha256",
        "git_head",
        "git_dirty",
        "flash_session_id",
        "lease_id",
        "dwarf_sha256",
        "svd_sha256",
        "group_id",
        "group_revision",
        "start_sequence",
        "end_sequence_exclusive",
        "start_captured_unix_ns",
        "end_captured_unix_ns_exclusive",
        "fixture_sha256",
        "projected_batch_sha256s",
        "transcript_evidence_id",
        "run_ref_sha256",
    ]

def test_ingest_preserves_origin_transcript_and_projects_only_workspace_session(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    document = _document("failed-before")

    reference = ingest_monitor_replay(
        paths, evidence, _operation("failed-before"), _fixture("failed-before")
    )

    assert reference.schema == "stm32-monitor-run-ref/1"
    assert reference.operation_id == _operation("failed-before")
    assert reference.scenario_role == "failed-before"
    assert reference.execution_source == "replay"
    assert reference.physical_transport_evidence is False
    assert reference.origin_workspace_id == document.binding.workspace_id
    assert reference.import_workspace_id == paths.workspace_id
    assert reference.origin_workspace_id != reference.import_workspace_id
    assert reference.origin_session_id == document.binding.session_id
    assert reference.projected_session_id == paths.session_id
    assert reference.origin_run_id == reference.projected_run_id == str(RUN_IDS["failed-before"])
    assert reference.fixture_sha256 == document.fixture_sha256
    assert reference.transcript_evidence_id
    assert len(reference.projected_batch_sha256s) == len(document.batches)

    root = get_root(evidence, "monitor-run", reference.operation_id)
    assert root.root_type == "monitor-run"
    assert root.root_id == reference.operation_id
    assert root.manifest_id == reference.transcript_evidence_id
    assert set(root.metadata) == {
        "fixture_sha256",
        "run_ref_sha256",
        "origin_workspace_id",
        "import_workspace_id",
        "execution_source",
        "physical_transport_evidence",
    }
    assert root.metadata == {
        "fixture_sha256": reference.fixture_sha256,
        "run_ref_sha256": reference.run_ref_sha256,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    plan = plan_gc(evidence)
    assert f"manifests/{root.manifest_id}.json" in plan.reachable_manifests

    ref_root = get_root(evidence, "monitor-run-ref", reference.operation_id)
    assert ref_root.root_type == "monitor-run-ref"
    assert ref_root.root_id == reference.operation_id
    assert ref_root.manifest_id != root.manifest_id
    assert set(ref_root.metadata) == {
        "operation_id",
        "run_ref_sha256",
        "fixture_sha256",
        "scenario_role",
        "origin_workspace_id",
        "import_workspace_id",
        "execution_source",
        "physical_transport_evidence",
    }
    assert ref_root.metadata == {
        "operation_id": reference.operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "fixture_sha256": reference.fixture_sha256,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    ref_envelope = evidence.get_envelope(ref_root.manifest_id)
    assert ref_envelope.operation == "monitor-run-ref"
    assert ref_envelope.parents == (reference.transcript_evidence_id,)
    assert ref_envelope.identity.workspace_id == document.binding.workspace_id
    assert ref_envelope.identity.project_id == document.binding.logical_project_id
    assert ref_envelope.identity.session_id == document.binding.session_id
    assert ref_envelope.identity.build_id == document.binding.build_id
    assert ref_envelope.identity.elf_sha256 == document.binding.elf_sha256
    assert ref_envelope.identity.input_snapshot_sha256 == document.binding.input_snapshot_sha256
    assert ref_envelope.identity.git_commit == document.binding.git_head
    assert ref_envelope.identity.git_dirty is False
    assert set(ref_envelope.metadata) == set(ref_root.metadata)
    assert ref_envelope.metadata == ref_root.metadata
    assert len(ref_envelope.artifacts) == 1
    assert ref_envelope.artifacts[0].kind == "monitor-run-ref"
    assert ref_envelope.artifacts[0].media_type == "application/json"
    ref_bytes = evidence.read_artifact(ref_envelope.artifacts[0], maximum_bytes=2 * 1024 * 1024)
    assert ref_bytes == canonical_replay_json_bytes(reference.to_dict())
    assert MonitorRunRef.from_value(json.loads(ref_bytes.decode("utf-8"))) == reference
    assert f"manifests/{ref_root.manifest_id}.json" in plan.reachable_manifests

    envelope = evidence.get_envelope(reference.transcript_evidence_id)
    assert envelope.operation == "monitor-replay-import"
    assert set(envelope.metadata) == {
        "operation_id",
        "scenario_role",
        "origin_workspace_id",
        "import_workspace_id",
        "origin_run_id",
        "projected_run_id",
        "fixture_sha256",
        "execution_source",
        "physical_transport_evidence",
    }
    assert envelope.metadata == {
        "operation_id": reference.operation_id,
        "scenario_role": "failed-before",
        "origin_workspace_id": document.binding.workspace_id,
        "import_workspace_id": paths.workspace_id,
        "origin_run_id": reference.origin_run_id,
        "projected_run_id": reference.projected_run_id,
        "fixture_sha256": document.fixture_sha256,
        "execution_source": "replay",
        "physical_transport_evidence": False,
    }
    assert len(envelope.parents) == 0
    assert len(envelope.artifacts) == 1
    assert envelope.artifacts[0].kind == "monitor-replay-transcript"
    assert envelope.artifacts[0].media_type == "application/json"
    assert evidence.read_artifact(envelope.artifacts[0], maximum_bytes=2 * 1024 * 1024) == _raw_fixture(
        "failed-before"
    )
    assert envelope.identity.workspace_id == document.binding.workspace_id
    assert envelope.identity.project_id == document.binding.logical_project_id
    assert envelope.identity.session_id == document.binding.session_id
    assert envelope.identity.build_id == document.binding.build_id
    assert envelope.identity.elf_sha256 == document.binding.elf_sha256
    assert envelope.identity.input_snapshot_sha256 == document.binding.input_snapshot_sha256
    assert envelope.identity.git_commit == document.binding.git_head
    assert envelope.identity.git_dirty is False

    batches = _history_batches(paths, RUN_IDS["failed-before"])
    assert len(batches) == len(document.batches)
    for source, stored, expected_digest in zip(
        document.batches,
        batches,
        reference.projected_batch_sha256s,
        strict=True,
    ):
        assert stored.binding.workspace_id == paths.workspace_id
        assert stored.binding.session_id == paths.session_id
        assert stored.binding.to_dict() == {
            **source.binding.to_dict(),
            "workspaceId": paths.workspace_id,
            "sessionId": paths.session_id,
        }
        assert stored.group_id == source.group_id
        assert stored.group_revision == source.group_revision
        assert stored.run_id == source.run_id
        assert stored.sequence == source.sequence
        assert stored.scheduled_unix_ns == source.scheduled_unix_ns
        assert stored.captured_unix_ns == source.captured_unix_ns
        assert stored.latency_ns == source.latency_ns
        assert stored.actual_rate_hz == source.actual_rate_hz
        assert stored.subscriber_drops == source.subscriber_drops
        assert stored.history_drops == source.history_drops
        assert stored.deadline_drops == source.deadline_drops
        assert stored.values == source.values
        assert sha256(canonical_replay_json_bytes(stored.to_dict())).hexdigest() == expected_digest


def test_fixed_after_survives_fresh_history_and_evidence_reload_and_ref_is_stable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    reference = ingest_monitor_replay(
        paths,
        _evidence(paths),
        _operation("fixed-after"),
        _fixture("fixed-after"),
    )

    round_trip = MonitorRunRef.from_value(reference.to_dict())
    assert round_trip == reference
    copied = reference.to_dict()
    copied["projected_batch_sha256s"][0] = "0" * 64
    assert reference.projected_batch_sha256s[0] != copied["projected_batch_sha256s"][0]
    assert reference.run_ref_sha256 == sha256(
        canonical_replay_json_bytes({key: value for key, value in reference.to_dict().items() if key != "run_ref_sha256"})
    ).hexdigest()

    fresh_paths = WorkspacePaths.from_roots(
        paths.data_root, paths.project_root, LOGICAL_PROJECT_ID, paths.session_id
    )
    fresh_reference = ingest_monitor_replay(
        fresh_paths,
        EvidenceStore(fresh_paths.workspace_root / "evidence"),
        _operation("fixed-after"),
        _fixture("fixed-after"),
    )
    assert fresh_reference == reference
    assert _history_batches(fresh_paths, RUN_IDS["fixed-after"])


def test_exact_retry_is_idempotent_and_different_intent_conflicts_without_append(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root = get_root(evidence, "monitor-run-ref", operation)
    ref_envelope = evidence.get_envelope(ref_root.manifest_id)
    before_ref_root = _root_path(evidence, "monitor-run-ref").read_bytes()
    before_ref_manifest = _manifest_path(evidence, ref_root.manifest_id).read_bytes()
    before_ref_artifact = _object_path(evidence, ref_envelope.artifacts[0].relative_path).read_bytes()

    retried = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert retried == first
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches
    assert _root_path(evidence, "monitor-run-ref").read_bytes() == before_ref_root
    assert _manifest_path(evidence, ref_root.manifest_id).read_bytes() == before_ref_manifest
    assert _object_path(evidence, ref_envelope.artifacts[0].relative_path).read_bytes() == before_ref_artifact

    origin_only_conflict = _rewrite_document(
        tmp_path,
        "failed-before",
        lambda payload: (
            payload["binding"].update({"workspaceId": "d" * 64}),
            [batch["binding"].update({"workspaceId": "d" * 64}) for batch in payload["batches"]],
        ),
        "origin-only-conflicting.json",
    )
    with pytest.raises(MonitorReplayError) as origin_error:
        ingest_monitor_replay(paths, evidence, operation, origin_only_conflict)
    assert origin_error.value.code == "OPERATION_CONFLICT"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches

    conflicting = _rewrite_document(
        tmp_path,
        "failed-before",
        lambda payload: payload["batches"][0]["values"][0]["typedValue"].update({"value": 999}),
        "conflicting.json",
    )
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, conflicting)
    assert error.value.code == "OPERATION_CONFLICT"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches


@pytest.mark.parametrize(
    ("name", "mutate"),
    (
        ("duplicate.json", lambda payload: payload["batches"][1].update({"sequence": 0})),
        (
            "nonmonotonic.json",
            lambda payload: payload["batches"][1].update({"capturedUnixNs": payload["batches"][0]["capturedUnixNs"]}),
        ),
        (
            "identity.json",
            lambda payload: payload["batches"][1]["binding"].update({"targetDevice": "other-target"}),
        ),
    ),
)
def test_chain_and_identity_failures_happen_before_history_append(
    tmp_path: Path, name: str, mutate
) -> None:
    paths = _paths(tmp_path)
    document = _document("failed-before")
    source = _rewrite_document(tmp_path, "failed-before", mutate, name)

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), source)
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    _assert_no_history(paths, RUN_IDS["failed-before"])
    assert not (paths.monitor_root / "monitor.sqlite3").exists()
    assert document.fixture_sha256 != "0" * 64


def test_malformed_fixture_digest_operation_mismatch_and_unknown_fields_fail_stably(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bad_digest_payload = json.loads(_raw_fixture("failed-before")[:-1].decode("utf-8"))
    bad_digest_payload["fixture_sha256"] = "0" * 64
    bad_digest = tmp_path / "bad-digest.json"
    bad_digest.write_bytes(canonical_replay_json_bytes(bad_digest_payload) + b"\n")
    with pytest.raises(MonitorReplayError) as digest_error:
        ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), bad_digest)
    assert digest_error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    with pytest.raises(MonitorReplayError) as operation_error:
        ingest_monitor_replay(
            paths,
            _evidence(paths),
            str(UUID("99999999-9999-4999-8999-999999999999")),
            _fixture("failed-before"),
        )
    assert operation_error.value.code == "MONITOR_REPLAY_INVALID"

    unknown = json.loads(_raw_fixture("failed-before")[:-1].decode("utf-8"))
    unknown["unexpected"] = True
    unknown_path = tmp_path / "unknown.json"
    unknown_path.write_bytes(canonical_replay_json_bytes(unknown) + b"\n")
    with pytest.raises(MonitorReplayError) as unknown_error:
        ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), unknown_path)
    assert unknown_error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    _assert_no_history(paths, RUN_IDS["failed-before"])


def test_canonical_replay_document_without_final_lf_is_accepted(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    no_lf = tmp_path / "no-final-lf.json"
    no_lf.write_bytes(_raw_fixture("failed-before")[:-1])

    reference = ingest_monitor_replay(
        paths, _evidence(paths), _operation("failed-before"), no_lf
    )

    assert reference.operation_id == _operation("failed-before")
    envelope = _evidence(paths).get_envelope(reference.transcript_evidence_id)
    assert _evidence(paths).read_artifact(envelope.artifacts[0], maximum_bytes=2 * 1024 * 1024) == no_lf.read_bytes()


def test_integer_actual_rate_is_not_a_canonical_float(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    source = _rewrite_document(
        tmp_path,
        "failed-before",
        lambda payload: [batch.update({"actualRateHz": 1000}) for batch in payload["batches"]],
        "integer-rate.json",
    )

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), source)
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    _assert_no_history(paths, RUN_IDS["failed-before"])
    assert not _evidence(paths).root.exists()


def test_max_int64_reference_window_fails_before_any_mutation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    source = _rewrite_document(
        tmp_path,
        "failed-before",
        lambda payload: (
            payload["batches"][0].update({"sequence": MAX_SIGNED_INT64 - 1}),
            payload["batches"][1].update({"sequence": MAX_SIGNED_INT64}),
        ),
        "max-int64-window.json",
    )

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), source)
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    _assert_no_history(paths, RUN_IDS["failed-before"])
    assert not _evidence(paths).root.exists()


def test_root_missing_with_preexisting_projected_history_is_a_conflict(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    document = _document("failed-before")
    projected = tuple(
        replace(
            batch,
            binding=replace(
                batch.binding,
                workspace_id=paths.workspace_id,
                session_id=paths.session_id,
            ),
        )
        for batch in document.batches
    )
    history = HistoryStore(paths)
    try:
        for batch in projected:
            assert history.append_batch(batch).ok
    finally:
        history.close()

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, _operation("failed-before"), _fixture("failed-before"))
    assert error.value.code == "OPERATION_CONFLICT"
    assert not evidence.root.exists()


def test_exact_root_without_history_recovers_with_one_atomic_append(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    failure = ProtocolResult(
        ok=False,
        operation="history.appendbatches",
        code="MONITOR_STORAGE_BUSY",
        message="monitor storage is busy",
        data=None,
    )

    def fail_append(self, batches):
        return failure

    monkeypatch.setattr(HistoryStore, "append_batches", fail_append, raising=False)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, _operation("failed-before"), _fixture("failed-before"))
    assert error.value.code == "ENVIRONMENT_FAILURE"
    root = get_root(evidence, "monitor-run", _operation("failed-before"))
    assert root.root_id == _operation("failed-before")
    ref_root = get_root(evidence, "monitor-run-ref", _operation("failed-before"))
    assert ref_root.root_id == _operation("failed-before")
    assert _history_batches(paths, RUN_IDS["failed-before"]) == ()

    monkeypatch.undo()
    recovered = ingest_monitor_replay(
        paths, evidence, _operation("failed-before"), _fixture("failed-before")
    )
    assert recovered.transcript_evidence_id == root.manifest_id
    assert get_root(evidence, "monitor-run-ref", _operation("failed-before")).manifest_id == ref_root.manifest_id
    assert _history_batches(paths, RUN_IDS["failed-before"])


def test_legacy_transcript_root_and_complete_history_repair_missing_reference_authority(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    old_root_path = _root_path(evidence, "monitor-run")
    old_root_bytes = old_root_path.read_bytes()
    transcript_envelope_path = _manifest_path(evidence, first.transcript_evidence_id)
    transcript_envelope_bytes = transcript_envelope_path.read_bytes()
    history_before = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root = get_root(evidence, "monitor-run-ref", operation)
    ref_envelope = evidence.get_envelope(ref_root.manifest_id)
    ref_root_path = _root_path(evidence, "monitor-run-ref")
    ref_artifact_path = _object_path(evidence, ref_envelope.artifacts[0].relative_path)

    ref_root_path.unlink()
    _manifest_path(evidence, ref_root.manifest_id).unlink()
    ref_artifact_path.unlink()

    repaired = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert repaired == first
    assert _root_path(evidence, "monitor-run").read_bytes() == old_root_bytes
    assert transcript_envelope_path.read_bytes() == transcript_envelope_bytes
    assert _history_batches(paths, RUN_IDS["failed-before"]) == history_before
    repaired_root = get_root(evidence, "monitor-run-ref", operation)
    assert repaired_root.to_dict() == ref_root.to_dict()
    repaired_envelope = evidence.get_envelope(repaired_root.manifest_id)
    assert evidence.read_artifact(
        repaired_envelope.artifacts[0], maximum_bytes=2 * 1024 * 1024
    ) == canonical_replay_json_bytes(repaired.to_dict())


def test_conflicting_reference_root_fails_before_history_mutation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root_path = _root_path(evidence, "monitor-run-ref")
    conflicting = json.loads(ref_root_path.read_bytes().decode("utf-8"))
    conflicting["metadata"]["run_ref_sha256"] = "0" * 64
    ref_root_path.write_bytes(canonical_json_bytes(conflicting))

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "OPERATION_CONFLICT"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches
    assert first.run_ref_sha256 != "0" * 64


def test_corrupt_reference_artifact_fails_before_history_mutation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root = get_root(evidence, "monitor-run-ref", operation)
    ref_envelope = evidence.get_envelope(ref_root.manifest_id)
    _object_path(evidence, ref_envelope.artifacts[0].relative_path).write_bytes(b"not-canonical-ref")

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches
    assert first.transcript_evidence_id == get_root(evidence, "monitor-run", operation).manifest_id


def test_reference_provider_failure_is_environment_error_without_history_mutation(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root = get_root(evidence, "monitor-run-ref", operation)
    original_get_envelope = evidence.get_envelope

    def fail_reference_provider(evidence_id: str):
        if evidence_id == ref_root.manifest_id:
            raise OSError("reference provider unavailable")
        return original_get_envelope(evidence_id)

    monkeypatch.setattr(evidence, "get_envelope", fail_reference_provider)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "ENVIRONMENT_FAILURE"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches
    assert first.run_ref_sha256 == get_root(evidence, "monitor-run-ref", operation).metadata["run_ref_sha256"]


def test_missing_reference_manifest_is_integrity_failure_without_history_mutation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    ref_root = get_root(evidence, "monitor-run-ref", operation)
    _manifest_path(evidence, ref_root.manifest_id).unlink()

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches
    assert first.run_ref_sha256 == ref_root.metadata["run_ref_sha256"]


@pytest.mark.parametrize("failure_point", ("envelope", "artifact"))
def test_transcript_provider_io_is_environment_failure(
    tmp_path: Path, monkeypatch, failure_point: str
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    before_batches = _history_batches(paths, RUN_IDS["failed-before"])
    if failure_point == "envelope":
        original_get_envelope = evidence.get_envelope

        def fail_transcript_envelope(evidence_id: str):
            if evidence_id == first.transcript_evidence_id:
                raise OSError("transcript provider unavailable")
            return original_get_envelope(evidence_id)

        monkeypatch.setattr(evidence, "get_envelope", fail_transcript_envelope)
    else:
        transcript_envelope = evidence.get_envelope(first.transcript_evidence_id)
        original_read_artifact = evidence.read_artifact

        def fail_transcript_artifact(artifact, *, maximum_bytes: int):
            if artifact == transcript_envelope.artifacts[0]:
                raise OSError("transcript artifact provider unavailable")
            return original_read_artifact(artifact, maximum_bytes=maximum_bytes)

        monkeypatch.setattr(evidence, "read_artifact", fail_transcript_artifact)

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "ENVIRONMENT_FAILURE"
    assert _history_batches(paths, RUN_IDS["failed-before"]) == before_batches


@pytest.mark.parametrize("with_history", (False, True))
def test_reference_without_transcript_root_is_partial_state(
    tmp_path: Path, monkeypatch, with_history: bool
) -> None:
    case_root = tmp_path / ("with-history" if with_history else "without-history")
    case_root.mkdir()
    paths = _paths(case_root)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    if with_history:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
        history_before = _history_batches(paths, RUN_IDS["failed-before"])
    else:
        failure = ProtocolResult(
            ok=False,
            operation="history.appendbatches",
            code="MONITOR_STORAGE_BUSY",
            message="monitor storage is busy",
            data=None,
        )
        monkeypatch.setattr(HistoryStore, "append_batches", lambda self, batches: failure, raising=False)
        with pytest.raises(MonitorReplayError) as error:
            ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
        assert error.value.code == "ENVIRONMENT_FAILURE"
        monkeypatch.undo()
        history_before = ()

    transcript_root_path = _root_path(evidence, "monitor-run")
    transcript_root_path.unlink()
    reference_root_path = _root_path(evidence, "monitor-run-ref")

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert not transcript_root_path.exists()
    assert reference_root_path.exists()
    assert _history_batches(paths, RUN_IDS["failed-before"]) == history_before


@pytest.mark.parametrize("winner", ("valid", "corrupt"))
def test_reference_root_publish_race_reloads_winner_before_classification(
    tmp_path: Path, monkeypatch, winner: str
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    _root_path(evidence, "monitor-run-ref").unlink()
    original_put_root = replay_module.put_root

    def race_put_root(store, candidate):
        if winner == "valid":
            conflicting = replace(
                candidate,
                metadata={**candidate.metadata, "run_ref_sha256": "0" * 64},
            )
            original_put_root(store, conflicting)
        else:
            root_directory = store.root / "roots" / "monitor-run-ref"
            root_name = sha256(
                canonical_json_bytes(
                    {"root_type": "monitor-run-ref", "root_id": operation}
                )
            ).hexdigest()
            (root_directory / f"{root_name}.json").write_bytes(b"not-canonical-root")
        raise EvidenceValidationError(
            "EVIDENCE_CORRUPT",
            "root identity already has different canonical bytes",
        )

    monkeypatch.setattr(replay_module, "put_root", race_put_root)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert error.value.code == (
        "OPERATION_CONFLICT" if winner == "valid" else "EVIDENCE_INTEGRITY_FAILURE"
    )


def test_document_parser_rejects_tuples_subclasses_and_noncanonical_json(tmp_path: Path) -> None:
    payload = json.loads(_raw_fixture("failed-before")[:-1].decode("utf-8"))
    with pytest.raises(MonitorReplayError) as tuple_error:
        MonitorReplayDocument.from_value({**payload, "batches": tuple(payload["batches"])})
    assert tuple_error.value.code == "MONITOR_REPLAY_INVALID"

    class DocumentSubclass(MonitorReplayDocument):
        pass

    document = _document("failed-before")
    subclass = DocumentSubclass(
        document.schema,
        document.source,
        document.physical_transport_evidence,
        document.scenario_role,
        document.binding,
        document.batches,
        document.fixture_sha256,
    )
    with pytest.raises(MonitorReplayError) as subclass_error:
        MonitorReplayDocument.from_value(subclass)
    assert subclass_error.value.code == "MONITOR_REPLAY_INVALID"

    paths = _paths(tmp_path)
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(_raw_fixture("failed-before") + b"\n")
    with pytest.raises(MonitorReplayError) as noncanonical_error:
        ingest_monitor_replay(
            paths,
            _evidence(paths),
            _operation("failed-before"),
            noncanonical,
        )
    assert noncanonical_error.value.code == "EVIDENCE_INTEGRITY_FAILURE"


def test_unsafe_symlink_and_hardlink_sources_are_rejected_before_append(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    symlink = tmp_path / "fixture-link.json"
    try:
        symlink.symlink_to(_fixture("failed-before"))
    except (OSError, NotImplementedError):
        symlink = None
    if symlink is not None:
        try:
            with pytest.raises(MonitorReplayError) as error:
                ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), symlink)
            assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
            _assert_no_history(paths, RUN_IDS["failed-before"])
        finally:
            symlink.unlink(missing_ok=True)

    hardlink = tmp_path / "fixture-hardlink.json"
    try:
        os.link(_fixture("failed-before"), hardlink)
    except (OSError, NotImplementedError):
        hardlink = None
    if hardlink is not None:
        try:
            with pytest.raises(MonitorReplayError) as error:
                ingest_monitor_replay(paths, _evidence(paths), _operation("failed-before"), hardlink)
            assert error.value.code == "EVIDENCE_INTEGRITY_FAILURE"
            _assert_no_history(paths, RUN_IDS["failed-before"])
        finally:
            hardlink.unlink(missing_ok=True)


def test_ingest_does_not_import_or_construct_physical_monitor_services(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported.append(name)
        if name.startswith("stm32_monitor.service") or name.startswith("stm32_monitor.probe_session"):
            raise AssertionError("physical monitor service was imported")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    reference = ingest_monitor_replay(
        paths, _evidence(paths), _operation("failed-before"), _fixture("failed-before")
    )
    assert reference.execution_source == "replay"
    assert not any(
        name.startswith("stm32_monitor.service") or name.startswith("stm32_monitor.probe_session")
        for name in imported
    )


def test_provider_failures_are_bounded_environment_errors(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)

    def fail_provider(*args, **kwargs):
        raise RuntimeError("provider leaked absolute path")

    monkeypatch.setattr(evidence, "ingest_file", fail_provider)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(
            paths, evidence, _operation("failed-before"), _fixture("failed-before")
        )
    assert error.value.code == "ENVIRONMENT_FAILURE"
    assert "provider leaked" not in str(error.value)
    _assert_no_history(paths, RUN_IDS["failed-before"])
