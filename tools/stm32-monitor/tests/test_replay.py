from __future__ import annotations

import builtins
import copy
import json
import os
from dataclasses import fields
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.history import HistoryQuery, HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch
from stm32_monitor.replay import (
    MONITOR_REPLAY_SCHEMA,
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths


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
    result = HistoryStore(paths).query_history(
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

    for role, document in (("failed-before", before), ("fixed-after", after)):
        raw = _raw_fixture(role)
        assert raw == canonical_replay_json_bytes(document.to_dict()) + b"\n"
        copied = document.to_dict()
        copied["binding"]["workspaceId"] = "0" * 64
        copied["batches"][0]["values"][0]["typedValue"]["value"] = -1
        assert document.binding.workspace_id != copied["binding"]["workspaceId"]
        assert document.batches[0].values[0].typed_value["value"] != -1


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

    retried = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    assert retried == first
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


def test_document_parser_rejects_tuples_subclasses_and_noncanonical_json() -> None:
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

    path = Path("noncanonical.json")
    assert path.name == "noncanonical.json"


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
