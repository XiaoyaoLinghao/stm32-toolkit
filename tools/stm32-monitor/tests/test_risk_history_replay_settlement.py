from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import (
    INCOMPATIBLE_IDENTITY,
    AnalysisWorkflowError,
    compare_monitor_runs,
)
from stm32_monitor.history import (
    MAX_HISTORY_BATCH_BYTES,
    HistoryPage,
    HistoryQuery,
    HistoryStore,
)
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    MonitorReplayError,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths

TOOLKIT_TESTS = Path(__file__).parents[2] / "stm32-toolkit" / "tests"
if str(TOOLKIT_TESTS) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_TESTS))

from test_acceptance_continuation import prepare_pair
from test_continuation_monitor import _monitor_baseline
from test_physical_publication import (
    _monitor_manifest_operations,
    _monitor_root_files,
    _physical_context,
    _physical_request,
    _publish_physical_test_run,
)

LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, LOGICAL_ID, "monitor-1")


def _binding(paths: WorkspacePaths) -> ObservationBinding:
    return ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id=str(LOGICAL_ID),
        session_id=paths.session_id,
        probe_id="probe-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256="a" * 64,
    )


def _batch(
    paths: WorkspacePaths,
    sequence: int,
    *,
    captured_ns: int | None = None,
    value: object = 7,
) -> SampleBatch:
    captured = captured_ns if captured_ns is not None else 1_000_000_000 + sequence
    return SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=sequence,
        scheduled_unix_ns=captured - 100,
        captured_unix_ns=captured,
        latency_ns=100,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(
            SampleValue(
                WatchItem.variable("counter"),
                "OK",
                typed_value={"type": "uint32", "value": value},
            ),
        ),
    )


def _tree_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _database_snapshot(database: Path, *, immutable: bool = False) -> tuple[object, ...]:
    query = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    with sqlite3.connect(database.as_uri() + query, uri=True) as connection:
        return (
            tuple(
                connection.execute(
                    "SELECT singleton,logical_bytes FROM monitor_history_accounting"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT batch_id,session_id,run_id,sequence,captured_ns,"
                    "payload_json,payload_bytes,payload_sha256,value_count "
                    "FROM history_batches ORDER BY batch_id"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "SELECT batch_id,ordinal,selector_kind,selector,value_json,"
                    "value_bytes,value_sha256 FROM history_values ORDER BY batch_id,ordinal"
                ).fetchall()
            ),
        )


def _query(paths: WorkspacePaths) -> HistoryQuery:
    return HistoryQuery(
        session_id=paths.session_id,
        start_ns=0,
        end_ns=2_000_000_000,
        limit=10_000,
    )


def _oversized_replay_file(tmp_path: Path) -> tuple[Path, bytes, int]:
    source = Path(__file__).parent / "fixtures" / "vs03" / "failed-before.json"
    payload = json.loads(source.read_bytes()[:-1].decode("utf-8"))
    template = copy.deepcopy(payload["batches"][0])
    template_value = copy.deepcopy(template["values"][0])
    total_values = 10_001
    values = [copy.deepcopy(template_value) for _ in range(total_values)]
    batches = []
    for sequence, offset in enumerate(range(0, total_values, 250)):
        batch = copy.deepcopy(template)
        batch["sequence"] = sequence
        batch["scheduledUnixNs"] = template["scheduledUnixNs"] + sequence * 1_000_000
        batch["capturedUnixNs"] = template["capturedUnixNs"] + sequence * 1_000_000
        batch["scheduledAtUtc"] = template["scheduledAtUtc"]
        batch["capturedAtUtc"] = template["capturedAtUtc"]
        batch["values"] = values[offset : offset + 250]
        batches.append(batch)
    payload["batches"] = batches
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )
    path = tmp_path / "oversized-replay.json"
    path.write_bytes(raw)
    return path, raw, total_values


def test_replay_oversized_document_records_the_first_public_guard(
    tmp_path: Path,
) -> None:
    """An oversized document is rejected by the reader; the value-count guard is unproven."""

    paths = _paths(tmp_path)
    evidence = EvidenceStore(paths.workspace_root / "evidence")
    document, raw, total_values = _oversized_replay_file(tmp_path)
    assert total_values > 10_000
    assert len(raw) > 1_048_576
    before = _tree_snapshot(evidence.root)

    with pytest.raises(MonitorReplayError) as error:
        ingest_monitor_replay(
            paths,
            evidence,
            str(UUID("33333333-3333-4333-8333-333333333333")),
            document,
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "replay document could not be read safely"
    assert _tree_snapshot(evidence.root) == before


def test_physical_monitor_history_partial_final_fragment_rejects_before_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
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
    before = _tree_snapshot(evidence.root)
    original_query = replay_module.HistoryStore.query_history
    calls: list[HistoryQuery] = []

    def partial_page(history: HistoryStore, query: HistoryQuery):
        calls.append(query)
        result = original_query(history, query)
        assert result.ok and result.data is not None
        assert result.data.batches
        final = result.data.batches[-1]
        changed_final = replace(final, batch_value_count=final.batch_value_count + 1)
        changed_page = HistoryPage.create(
            (*result.data.batches[:-1], changed_final),
            next_cursor=result.data.next_cursor,
        )
        return ProtocolResult(
            ok=True,
            operation=result.operation,
            code=result.code,
            message=result.message,
            data=changed_page,
            details=result.details,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", partial_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == INCOMPATIBLE_IDENTITY
    assert error.value.message == "physical Monitor history ended with a partial batch"
    assert calls
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()
    assert _monitor_manifest_operations(evidence) == ()
    assert _tree_snapshot(evidence.root) == before
    reopened = HistoryStore(paths)
    reopened.close()


def test_history_append_batches_rejects_one_oversized_batch_atomically(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    database = paths.monitor_root / "monitor.sqlite3"
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        before = _database_snapshot(database)
        oversized = replace(
            _batch(paths, 2),
            values=tuple(
                SampleValue(
                    WatchItem.variable(f"oversized_{index}"),
                    "OK",
                    typed_value={"type": "uint32", "value": index},
                    definition={"description": "x" * 18_000},
                )
                for index in range(256)
            ),
        )
        encoded_size = len(
            json.dumps(
                oversized.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        assert encoded_size > MAX_HISTORY_BATCH_BYTES

        rejected = store.append_batches((oversized,))
        assert not rejected.ok
        assert rejected.operation == "history.appendbatches"
        assert rejected.code == "MONITOR_REQUEST_INVALID"
        assert rejected.message == "sample batch collection is invalid"
        assert _database_snapshot(database) == before

        assert store.append_batches((_batch(paths, 2),)).ok
        queried = store.query_history(_query(paths))
        assert queried.ok and queried.data is not None
        assert tuple(item.sequence for item in queried.data.batches) == (1, 2)
    finally:
        store.close()


def test_history_query_rejects_persisted_zero_batch_id_without_mutation(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    database = paths.monitor_root / "monitor.sqlite3"
    store = HistoryStore(paths)
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("UPDATE history_values SET batch_id = 0 WHERE batch_id = 1")
            connection.commit()

        before = _database_snapshot(database)
        rejected = store.query_history(_query(paths))
        assert not rejected.ok
        assert rejected.operation == "history.query"
        assert rejected.code == "MONITOR_STORAGE_CORRUPT"
        assert rejected.message == "monitor history is corrupt"
        assert _database_snapshot(database) == before
    finally:
        store.close()

    reopened = HistoryStore(paths)
    try:
        rejected_again = reopened.query_history(_query(paths))
        assert not rejected_again.ok
        assert rejected_again.code == "MONITOR_STORAGE_CORRUPT"
        assert rejected_again.message == "monitor history is corrupt"
        assert _database_snapshot(database) == before
    finally:
        reopened.close()


def test_history_trusted_write_rejects_injected_wal_hardlink_and_recovers(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    database = paths.monitor_root / "monitor.sqlite3"
    store = HistoryStore(paths)
    sentinel = tmp_path / "external-wal-sentinel"
    sidecar = database.with_name(database.name + "-wal")
    injection_completed = False
    sentinel_after_injection: tuple[bytes, int] | None = None
    try:
        assert store.append_batch(_batch(paths, 1)).ok
        before = _database_snapshot(database, immutable=True)
        sentinel.write_bytes(b"external-wal-sentinel")
        assert not sidecar.exists(), "initial append left a sidecar that blocks the injection"
        os.link(sentinel, sidecar)
        injection_completed = True
        sentinel_after_injection = (sentinel.read_bytes(), os.lstat(sentinel).st_nlink)

        rejected = store.append_batch(_batch(paths, 2))
        assert not rejected.ok
        assert rejected.operation == "history.append"
        assert rejected.code == "MONITOR_STORAGE_INVALID"
        assert rejected.message == "monitor storage is not a private regular file"
        assert _database_snapshot(database, immutable=True) == before
        assert sentinel_after_injection is not None
        assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == sentinel_after_injection
        assert os.path.samefile(sentinel, sidecar)
    finally:
        store.close()
        if injection_completed:
            assert sentinel_after_injection is not None
            assert os.path.samefile(sentinel, sidecar)
            assert (sentinel.read_bytes(), os.lstat(sentinel).st_nlink) == sentinel_after_injection
            sidecar.unlink()

    recovered = HistoryStore(paths)
    try:
        assert recovered.append_batch(_batch(paths, 2)).ok
        queried = recovered.query_history(_query(paths))
        assert queried.ok and queried.data is not None
        assert tuple(item.sequence for item in queried.data.batches) == (1, 2)
    finally:
        recovered.close()


def _with_probe(reference: MonitorRunRefV2, probe: str) -> MonitorRunRefV2:
    payload = reference.to_dict()
    payload["probe_id"] = sha256(probe.encode("utf-8")).hexdigest()
    payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()
    return MonitorRunRefV2.from_value(payload)


def test_continuation_rejects_same_changed_probe_on_both_run_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch)
    baseline = _monitor_baseline(pair, tmp_path)
    changed_probe = "probe/serial/changed"
    changed_refs = tuple(_with_probe(reference, changed_probe) for reference in baseline.refs)
    request = AnalysisRequest(
        schema=baseline.request.schema,
        before_run=changed_refs[0],
        after_run=changed_refs[1],
        selector_kind=baseline.request.selector_kind,
        selector=baseline.request.selector,
        alignment=baseline.request.alignment,
        minimum_valid_pairs=baseline.request.minimum_valid_pairs,
    )
    compare_args = (*baseline.compare_args[:2], request, *baseline.compare_args[3:])
    before = _tree_snapshot(tmp_path)

    with pytest.raises(AnalysisWorkflowError) as error:
        compare_monitor_runs(
            *compare_args,
            continuation_evidence_id=baseline.continuation_id,
        )

    assert error.value.code == INCOMPATIBLE_IDENTITY
    assert error.value.message == "continuation does not match runs"
    assert _tree_snapshot(tmp_path) == before
