from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from stm32_monitor.history import HistoryPage, HistoryQuery, HistoryStore
from stm32_monitor.models import HistoryBatchSlice, SampleValue, WatchItem
from stm32_monitor.replay import (
    INCOMPATIBLE_IDENTITY,
    MonitorReplayError,
    load_monitor_run_reference,
    publish_physical_monitor_run,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository
from test_physical_publication import (
    _append_large_physical_history,
    _monitor_root_files,
    _physical_context,
    _physical_evidence_state,
    _publish_physical_test_run,
)


def _public_history_pages(
    paths: WorkspacePaths,
    run_id: UUID,
    group_id: UUID,
    *,
    start_ns: int,
    end_ns: int,
) -> tuple[HistoryPage, ...]:
    pages: list[HistoryPage] = []
    seen_cursors: set[str] = set()
    history = HistoryStore(paths)
    try:
        cursor: str | None = None
        for _ in range(64):
            result = history.query_history(
                HistoryQuery(
                    session_id=paths.session_id,
                    start_ns=start_ns,
                    end_ns=end_ns,
                    limit=10_000,
                    cursor=cursor,
                    run_id=run_id,
                    group_id=group_id,
                )
            )
            assert result.ok and result.data is not None, result.to_dict()
            page = result.data
            assert type(page) is HistoryPage
            assert set(page.to_dict()) == {
                "batches",
                "valueCount",
                "nextCursor",
                "serializedBytes",
            }
            assert type(page.batches) is tuple
            assert all(type(batch) is HistoryBatchSlice for batch in page.batches)
            pages.append(page)
            cursor = page.next_cursor
            if cursor is None:
                break
            assert cursor not in seen_cursors
            seen_cursors.add(cursor)
        else:
            raise AssertionError("public History cursor did not terminate")
    finally:
        history.close()
    assert pages
    return tuple(pages)


def _page_wire(pages: tuple[HistoryPage, ...]) -> tuple[dict[str, object], ...]:
    return tuple(page.to_dict() for page in pages)


def test_physical_history_window_rejects_10001_values_then_recovers_40_batches(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_large_physical_history(paths, raw_probe, monitor_run_id, group_id)
    extra = replace(
        batches[-1],
        sequence=40,
        scheduled_unix_ns=batches[-1].scheduled_unix_ns + 1_000_000,
        captured_unix_ns=batches[-1].captured_unix_ns + 1_000_000,
        values=(
            SampleValue(
                WatchItem.variable("counter-000"),
                "OK",
                typed_value={"type": "uint32", "value": 10_000},
                definition={"description": "x" * 256},
            ),
        ),
    )
    history = HistoryStore(paths)
    try:
        appended = history.append_batches((extra,))
        assert appended.ok, appended.to_dict()
    finally:
        history.close()

    full_request = {
        "scenario_role": "failed-before",
        "test_run_id": test_run_id,
        "run_id": str(monitor_run_id),
        "group_id": str(group_id),
        "start_sequence": 0,
        "end_sequence_exclusive": 41,
        "start_captured_unix_ns": batches[0].captured_unix_ns,
        "end_captured_unix_ns_exclusive": extra.captured_unix_ns + 1,
        "probe_id": raw_probe,
    }
    pages_before = _public_history_pages(
        paths,
        monitor_run_id,
        group_id,
        start_ns=batches[0].captured_unix_ns,
        end_ns=extra.captured_unix_ns + 1,
    )
    assert sum(page.value_count for page in pages_before) == 10_001
    fragments = tuple(fragment for page in pages_before for fragment in page.batches)
    assert {fragment.sequence for fragment in fragments} == set(range(41))
    assert sum(
        len(fragment.values) for fragment in fragments if fragment.sequence == 40
    ) == 1
    pages_before_wire = _page_wire(pages_before)
    test_run_before = TestRunRepository(evidence).load(test_run_id)
    evidence_before = _physical_evidence_state(evidence)

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **full_request)
    assert error.value.code == INCOMPATIBLE_IDENTITY
    assert error.value.message == "physical Monitor history window is too large"
    assert _physical_evidence_state(evidence) == evidence_before
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()
    assert _page_wire(
        _public_history_pages(
            paths,
            monitor_run_id,
            group_id,
            start_ns=batches[0].captured_unix_ns,
            end_ns=extra.captured_unix_ns + 1,
        )
    ) == pages_before_wire
    assert TestRunRepository(evidence).load(test_run_id) == test_run_before

    legal_request = {
        **full_request,
        "end_sequence_exclusive": 40,
        "end_captured_unix_ns_exclusive": batches[-1].captured_unix_ns + 1,
    }
    reference = publish_physical_monitor_run(paths, evidence, **legal_request)
    assert reference.start_sequence == 0
    assert reference.end_sequence_exclusive == 40
    fresh = load_monitor_run_reference(
        WorkspacePaths.from_roots(
            paths.data_root,
            paths.project_root,
            UUID("123e4567-e89b-42d3-a456-426614174000"),
            paths.session_id,
        ),
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    )
    assert fresh == reference
    assert _page_wire(
        _public_history_pages(
            paths,
            monitor_run_id,
            group_id,
            start_ns=batches[0].captured_unix_ns,
            end_ns=extra.captured_unix_ns + 1,
        )
    ) == pages_before_wire
    assert TestRunRepository(evidence).load(test_run_id) == test_run_before
