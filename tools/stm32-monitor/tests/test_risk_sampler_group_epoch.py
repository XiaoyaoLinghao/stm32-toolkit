from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from stm32_monitor.models import WatchGroup
from stm32_monitor.protocol import failure, success
from stm32_monitor.sampler import MonitorSampler, SamplerState
from test_sampler import (
    GROUP_ID,
    FakeGroups,
    FakeHistory,
    FakeObservation,
    _binding,
    _group,
    _next,
)


class HeldGroupProvider(FakeGroups):
    def __init__(
        self,
        group: WatchGroup,
        old_outcome: object,
        record: Callable[[str], None],
    ) -> None:
        super().__init__(group)
        self.old_outcome = old_outcome
        self.record = record
        self.calls = 0
        self.old_lookup_started = threading.Event()
        self.release_old_lookup = threading.Event()
        self.fresh_lookup_started = threading.Event()
        self._lock = threading.Lock()

    def get_group(self, group_id):
        with self._lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.record("group-initial")
            return success("groups.get", self.group)
        if call == 2:
            self.record("group-old-start")
            self.old_lookup_started.set()
            if not self.release_old_lookup.wait(timeout=5):
                raise RuntimeError("held provider was not released")
            self.record("group-old-return")
            if isinstance(self.old_outcome, BaseException):
                raise self.old_outcome
            return self.old_outcome
        self.record("group-fresh")
        self.fresh_lookup_started.set()
        return success("groups.get", self.group)


class RecordingObservation(FakeObservation):
    def __init__(self, binding, record: Callable[[str], None]) -> None:
        super().__init__(binding)
        self.record = record
        self.first_read_started = threading.Event()
        self.read_count = 0

    async def _read_batch(self, variables, registers):
        self.read_count += 1
        self.record("read")
        self.first_read_started.set()
        return await super()._read_batch(variables, registers)


class RecordingHistory(FakeHistory):
    def __init__(self, record: Callable[[str], None]) -> None:
        super().__init__()
        self.record = record
        self.first_append_finished = threading.Event()

    def append_batch(self, batch):
        result = super().append_batch(batch)
        self.record("history")
        self.first_append_finished.set()
        return result


def _response(operation: str, data: dict[str, object]) -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-monitor/1",
        "ok": True,
        "operation": operation,
        "code": "OK",
        "message": "",
        "data": data,
        "details": {},
    }


@pytest.mark.parametrize(
    "outcome_kind",
    ["provider-error", "failed-result", "revision-change", "unchanged"],
    ids=["runtime-error", "failed-protocol-result", "changed-revision", "unchanged-group"],
)
def test_pause_resume_discards_held_group_lookup_by_epoch(
    tmp_path: Path, outcome_kind: str
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        events: list[str] = []
        events_lock = threading.Lock()

        def record(event: str) -> None:
            with events_lock:
                events.append(event)

        group = _group(revision=1, interval_ms=5_000)
        if outcome_kind == "provider-error":
            old_outcome: object = RuntimeError("C:\\secret")
        elif outcome_kind == "failed-result":
            old_outcome = failure(
                "groups.get", "MONITOR_GROUP_NOT_FOUND", "watch group was not found"
            )
        elif outcome_kind == "revision-change":
            old_outcome = success("groups.get", _group(revision=2, interval_ms=5_000))
        else:
            old_outcome = success("groups.get", group)

        observation = RecordingObservation(_binding(project), record)
        groups = HeldGroupProvider(group, old_outcome, record)
        history = RecordingHistory(record)
        sampler = MonitorSampler(observation, groups, history)
        stream = sampler.subscribe()
        try:
            started = await sampler.start(GROUP_ID, expected_revision=1)
            assert started.to_dict()["ok"] is True
            started_data = started.to_dict()["data"]
            assert isinstance(started_data, dict)
            run_id = started_data["runId"]
            assert started.to_dict() == _response(
                "sampling.start",
                {
                    "groupId": str(GROUP_ID),
                    "groupRevision": 1,
                    "runId": run_id,
                    "intervalMs": 5_000,
                },
            )
            assert await asyncio.to_thread(groups.old_lookup_started.wait, 2)

            paused = await sampler.pause()
            assert paused.to_dict() == _response("sampling.pause", {"paused": True})
            assert sampler.state is SamplerState.PAUSED

            resumed = await sampler.resume()
            assert resumed.to_dict() == _response("sampling.resume", {"resumed": True})
            assert sampler.state is SamplerState.RUNNING
            assert sampler.blocked_code is None

            groups.release_old_lookup.set()
            assert await asyncio.to_thread(groups.fresh_lookup_started.wait, 2)
            assert await asyncio.to_thread(observation.first_read_started.wait, 2)

            first_read_index = events.index("read")
            assert events.index("group-old-return") < events.index("group-fresh")
            assert events.index("group-fresh") < first_read_index
            assert events[:4] == [
                "group-initial",
                "group-old-start",
                "group-old-return",
                "group-fresh",
            ]
            assert observation.read_count == 1
            assert groups.calls == 3

            batch = await _next(stream)
            assert batch.sequence == 0
            assert batch.group_id == GROUP_ID
            assert batch.group_revision == 1
            assert str(batch.run_id) == run_id
            assert batch.binding.session_id == "monitor-1"
            assert sampler.state is SamplerState.RUNNING
            assert sampler.blocked_code is None

            stopped = await sampler.stop()
            assert stopped.to_dict() == _response("sampling.stop", {"stopped": True})
            assert await asyncio.to_thread(history.first_append_finished.wait, 2)
            assert len(history.batches) == 1
            assert history.batches[0].to_dict() == batch.to_dict()
            assert history.batches[0].sequence == 0
            assert history.batches[0].group_id == GROUP_ID
            assert str(history.batches[0].run_id) == run_id

            await stream.aclose()
            await sampler.close()
            assert sampler.state is SamplerState.CLOSED
            assert sampler.tasks == ()
        finally:
            groups.release_old_lookup.set()
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())
