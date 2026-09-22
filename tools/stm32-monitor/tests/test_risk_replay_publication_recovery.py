"""Focused public Replay publication refusal and recovery scenarios.

The fixtures in this module exercise only public producer and persistence
boundaries.  They deliberately keep the physical-shaped path offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from stm32_monitor.history import HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.replay import (
    ENVIRONMENT_FAILURE,
    MONITOR_PHYSICAL_INVALID,
    OPERATION_CONFLICT,
    MonitorReplayError,
    ingest_monitor_replay,
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from test_physical_publication import (
    _monitor_root_files,
    _physical_context,
    _publish_physical_test_run,
)
from test_replay import (
    _evidence,
    _fixture,
    _history_batches,
    _operation,
    _paths,
)


def _tree_state(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _replace_root_manifest(
    evidence: EvidenceStore,
    original: RootRecord,
    manifest_id: str,
    root_path: Path,
) -> RootRecord:
    replacement = RootRecord(
        root_type=original.root_type,
        root_id=original.root_id,
        manifest_id=manifest_id,
        metadata=original.metadata,
    )
    root_path.unlink()
    put_root(evidence, replacement)
    return replacement


def _root_path_for_id(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    directory = evidence.root / "roots" / root_type
    candidates = [
        path
        for path in directory.glob("*.json")
        if json.loads(path.read_bytes().decode("utf-8")).get("root_id") == root_id
    ]
    assert len(candidates) == 1
    return candidates[0]


def test_replay_reference_root_rejects_another_valid_envelope_then_restores(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    first = ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))
    original_root_path = _root_path_for_id(evidence, "monitor-run-ref", operation)
    ingest_monitor_replay(
        paths,
        evidence,
        _operation("fixed-after"),
        _fixture("fixed-after"),
    )
    original_root = get_root(evidence, "monitor-run-ref", operation)
    other_root = get_root(evidence, "monitor-run-ref", _operation("fixed-after"))
    history_before = _history_batches(paths, UUID(operation))
    original_state = _tree_state(evidence.root)

    corrupted = _replace_root_manifest(
        evidence,
        original_root,
        other_root.manifest_id,
        original_root_path,
    )
    corrupted_state = _tree_state(evidence.root)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, evidence, operation, _fixture("failed-before"))

    assert error.value.code == OPERATION_CONFLICT
    assert error.value.message == "operation reference root has a different intent"
    assert corrupted.manifest_id == other_root.manifest_id
    assert _tree_state(evidence.root) == corrupted_state

    original_root_path.unlink()
    put_root(evidence, original_root)
    restored = ingest_monitor_replay(
        paths, EvidenceStore(evidence.root), operation, _fixture("failed-before")
    )
    assert restored == first
    assert _history_batches(paths, UUID(operation)) == history_before
    assert _tree_state(evidence.root) == original_state


def _raise_provider_failure(kind: str) -> None:
    if kind == "oserror":
        try:
            raise OSError("provider unavailable")
        except OSError as cause:
            raise RuntimeError("wrapped provider failure") from cause
    raise RuntimeError("provider unavailable")


@pytest.mark.parametrize(
    ("phase", "occurrence", "cause_kind", "expected_message"),
    [
        (
            "transcript",
            1,
            "oserror",
            "replay Evidence provider failed",
        ),
        (
            "reference",
            2,
            "oserror",
            "monitor run reference Evidence provider failed",
        ),
        (
            "reference",
            2,
            "runtime",
            "monitor run reference Evidence publication failed",
        ),
    ],
    ids=(
        "transcript-provider-oserror",
        "reference-provider-oserror",
        "reference-provider-runtime",
    ),
)
def test_replay_provider_failure_preserves_prefix_and_fresh_retry_recovers(
    tmp_path: Path,
    phase: str,
    occurrence: int,
    cause_kind: str,
    expected_message: str,
) -> None:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    operation = _operation("failed-before")
    calls = 0

    def inject(point: str) -> None:
        nonlocal calls
        if point == "artifact.before_publish":
            calls += 1
            if calls == occurrence:
                _raise_provider_failure(cause_kind)

    before_history = _history_batches(paths, UUID(operation))
    faulty = EvidenceStore(evidence.root, fault_injector=inject)
    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(paths, faulty, operation, _fixture("failed-before"))

    assert calls == occurrence
    assert error.value.code == ENVIRONMENT_FAILURE
    assert error.value.message == expected_message
    cause = error.value.__cause__
    assert isinstance(cause, RuntimeError)
    assert str(cause) == (
        "wrapped provider failure"
        if cause_kind == "oserror"
        else "provider unavailable"
    )
    if cause_kind == "oserror":
        assert isinstance(cause.__cause__, OSError)
        assert str(cause.__cause__) == "provider unavailable"
    else:
        assert cause.__cause__ is None
    assert _history_batches(paths, UUID(operation)) == before_history

    transcript_roots = _monitor_root_files(evidence, "monitor-run")
    reference_roots = _monitor_root_files(evidence, "monitor-run-ref")
    if phase == "transcript":
        assert transcript_roots == ()
        assert reference_roots == ()
    else:
        assert len(transcript_roots) == 1
        assert reference_roots == ()
        transcript_root_bytes = transcript_roots[0].read_bytes()
        transcript_manifest_id = get_root(
            evidence, "monitor-run", operation
        ).manifest_id

    recovered = ingest_monitor_replay(
        paths,
        EvidenceStore(evidence.root),
        operation,
        _fixture("failed-before"),
    )
    assert recovered.operation_id == operation
    assert recovered.transcript_evidence_id
    assert len(_monitor_root_files(evidence, "monitor-run")) == 1
    assert len(_monitor_root_files(evidence, "monitor-run-ref")) == 1
    if phase == "reference":
        assert (
            _monitor_root_files(evidence, "monitor-run")[0].read_bytes()
            == transcript_root_bytes
        )
        assert (
            get_root(evidence, "monitor-run", operation).manifest_id
            == transcript_manifest_id
        )
    assert _history_batches(paths, UUID(operation))


def _append_node_heavy_physical_history(
    paths,
    raw_probe: str,
    monitor_run_id: UUID,
    group_id: UUID,
) -> tuple[SampleBatch, ...]:
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id="b" * 64,
        elf_sha256="c" * 64,
        input_snapshot_sha256="d" * 64,
        git_head="e" * 40,
        git_dirty=False,
        flash_session_id="flash-session-01",
        lease_id="lease-01",
        dwarf_sha256="f" * 64,
        svd_sha256=None,
    )
    watches = tuple(WatchItem.variable(f"counter-{index:03d}") for index in range(100))
    definition = {f"field-{index:03d}": index for index in range(128)}
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=tuple(
                SampleValue(
                    watch,
                    "OK",
                    typed_value={
                        "type": "uint32",
                        "value": sequence * len(watches) + index,
                    },
                    definition=definition,
                )
                for index, watch in enumerate(watches)
            ),
        )
        for sequence in range(100)
    )
    history = HistoryStore(paths)
    try:
        result = history.append_batches(batches)
        assert result.ok, result.to_dict()
    finally:
        history.close()
    return batches


def test_physical_transcript_node_limit_refuses_before_publication_and_reuses_input(
    tmp_path: Path,
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
    batches = _append_node_heavy_physical_history(
        paths, raw_probe, monitor_run_id, group_id
    )
    request = {
        "scenario_role": "failed-before",
        "test_run_id": test_run_id,
        "run_id": str(monitor_run_id),
        "group_id": str(group_id),
        "start_sequence": 0,
        "end_sequence_exclusive": len(batches),
        "start_captured_unix_ns": batches[0].captured_unix_ns,
        "end_captured_unix_ns_exclusive": batches[-1].captured_unix_ns + 1,
        "probe_id": raw_probe,
    }
    evidence_before = _tree_state(evidence.root)

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == MONITOR_PHYSICAL_INVALID
    assert error.value.message == "physical Monitor transcript is invalid"
    assert isinstance(error.value.__cause__, ValueError)
    assert (
        str(error.value.__cause__) == "physical transcript JSON exceeds its node limit"
    )
    assert _tree_state(evidence.root) == evidence_before
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()

    recovered = publish_physical_monitor_run(
        paths,
        EvidenceStore(evidence.root),
        **{
            **request,
            "end_sequence_exclusive": 2,
            "end_captured_unix_ns_exclusive": batches[1].captured_unix_ns + 1,
        },
    )
    assert recovered.operation_id == str(monitor_run_id)
    assert recovered.end_sequence_exclusive == 2
    assert (
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )
        == recovered
    )
