from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_monitor.models import WatchGroup, WatchItem
from stm32_monitor.protocol import failure, success
from stm32_monitor.sampler import MonitorSampler, SamplerState
from stm32_toolkit.debug import (
    DebugFirmwareBinding,
    DebugReadItem,
    DebugReadReport,
    MemoryRegionBinding,
    TypedValue,
)
from stm32_toolkit.result import OperationResult


GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")


def _binding(project: Path) -> DebugFirmwareBinding:
    return DebugFirmwareBinding(
        logical_project_id="22222222-2222-4222-8222-222222222222",
        workspace_id="a" * 24,
        observation_session_id="monitor-1",
        flash_session_id="flash-1",
        lease_id="lease-1",
        probe_id="probe-1",
        target_device="STM32F407VGTx",
        debug_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        elf_size=4096,
        elf_path="build/firmware.elf",
        input_snapshot_sha256="f" * 64,
        git_head="c" * 40,
        git_dirty=False,
        confirmed_at_utc="2026-08-08T01:02:03.000000Z",
        memory_regions=(MemoryRegionBinding("RAM", 0x20000000, 1024, "rw-"),),
        project_root=project.resolve(),
    )


class FakeObservation:
    def __init__(self, binding: DebugFirmwareBinding, *, delay: float = 0.0) -> None:
        self.binding = binding
        self.catalog = SimpleNamespace(elf_sha256=binding.elf_sha256)
        self.svd = SimpleNamespace(sha256="d" * 64)
        self.delay = delay
        self.calls = 0
        self.call_times: list[float] = []
        self.revalidate_calls = 0
        self.block_after: int | None = None
        self.item_error = False

    async def revalidate(self):
        self.revalidate_calls += 1
        if self.block_after is not None and self.revalidate_calls > self.block_after:
            return OperationResult.failure("revalidate", "MONITOR_FIRMWARE_CHANGED", "changed", {})
        return OperationResult.success("revalidate", self.binding)

    async def read_variables(self, expressions: tuple[str, ...]):
        self.calls += 1
        self.call_times.append(time.monotonic())
        if self.delay:
            await asyncio.sleep(self.delay)
        items = []
        for expression in expressions:
            if self.item_error and expression == "bad":
                items.append(DebugReadItem(expression, "error", code="DEBUG_VALUE_UNAVAILABLE"))
            else:
                items.append(DebugReadItem(expression, "ok", TypedValue(expression, "uint32_t", self.calls, f"0x{self.calls:08x}", 32)))
        return OperationResult.success(
            "read",
            DebugReadReport(self.binding, tuple(items), "2026-08-08T01:02:04.000000Z"),
        )

    async def sample_registers(self, paths: tuple[str, ...]):
        return await self.read_variables(paths)


class FakeGroups:
    def __init__(self, group: WatchGroup) -> None:
        self.group = group
        self.raise_load = False
        self.missing = False

    def get_group(self, group_id: UUID):
        if self.raise_load:
            raise RuntimeError("C:\\secret")
        if self.missing:
            return failure("groups.get", "MONITOR_GROUP_NOT_FOUND", "not found")
        if group_id != self.group.group_id:
            return failure("groups.get", "MONITOR_GROUP_NOT_FOUND", "not found")
        return success("groups.get", self.group)


class FakeHistory:
    def __init__(self, *, release: threading.Event | None = None, fail: bool = False, raise_append: bool = False) -> None:
        self.batches = []
        self.release = release
        self.entered = threading.Event()
        self.fail = fail
        self.raise_append = raise_append

    def append_batch(self, batch):
        self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=5)
        if self.raise_append:
            raise RuntimeError("C:\\secret")
        self.batches.append(batch)
        if self.fail:
            return failure("history.append", "MONITOR_STORAGE_INVALID", "failed")
        return success("history.append", {"stored": True})


def _group(*, revision: int = 1, interval_ms: int = 100, items=None) -> WatchGroup:
    now = __import__("datetime").datetime(2026, 8, 8, tzinfo=__import__("datetime").timezone.utc)
    return WatchGroup(
        GROUP_ID,
        "Core",
        "",
        interval_ms,
        tuple(items if items is not None else (WatchItem.variable("counter"),)),
        revision,
        now,
        now,
    )


async def _next(stream, timeout: float = 2.0):
    return await asyncio.wait_for(anext(stream), timeout)


def test_constructor_rejects_invalid_stores_and_private_queue_limits(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observation = FakeObservation(_binding(project))
    with pytest.raises(TypeError, match="stores"):
        MonitorSampler(observation, object(), object())
    for value in (True, 0, 129):
        with pytest.raises(ValueError, match="limits"):
            MonitorSampler(observation, FakeGroups(_group()), FakeHistory(), _history_queue_batches=value)
    with pytest.raises(ValueError, match="limits"):
        MonitorSampler(observation, FakeGroups(_group()), FakeHistory(), _history_queue_bytes=8 * 1024 * 1024 + 1)


def test_start_binds_exact_group_revision_and_emits_immutable_batch(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        history = FakeHistory()
        sampler = MonitorSampler(observation, FakeGroups(_group(revision=3)), history)
        stream = sampler.subscribe()
        pending = asyncio.create_task(_next(stream))
        started = await sampler.start(GROUP_ID, expected_revision=3)
        batch = await pending
        try:
            assert started.ok and sampler.state is SamplerState.RUNNING
            assert batch.group_id == GROUP_ID and batch.group_revision == 3
            assert batch.sequence == 0
            assert batch.binding.build_id == "b" * 64
            assert batch.values[0].watch == WatchItem.variable("counter")
            assert batch.values[0].status == "OK"
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_start_rejects_stale_revision_missing_group_and_non_integer_revision(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group(revision=2)), FakeHistory())
        try:
            stale = await sampler.start(GROUP_ID, expected_revision=1)
            invalid = await sampler.start(GROUP_ID, expected_revision=True)
            missing = await sampler.start(UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"), expected_revision=2)
            assert stale.code == "MONITOR_GROUP_CONFLICT"
            assert invalid.code == "MONITOR_REQUEST_INVALID"
            assert missing.code == "MONITOR_GROUP_NOT_FOUND"
            assert sampler.state is SamplerState.IDLE
        finally:
            await sampler.close()

    asyncio.run(scenario())


def test_start_rejects_load_failure_empty_group_active_run_and_closed_sampler(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        groups = FakeGroups(_group())
        sampler = MonitorSampler(FakeObservation(_binding(project)), groups, FakeHistory())
        groups.raise_load = True
        failed = await sampler.start(GROUP_ID, expected_revision=1)
        assert failed.code == "MONITOR_STORAGE_INVALID"

        groups.raise_load = False
        groups.group = _group(items=())
        empty = await sampler.start(GROUP_ID, expected_revision=1)
        assert empty.code == "MONITOR_REQUEST_INVALID"

        groups.group = _group()
        started = await sampler.start(GROUP_ID, expected_revision=1)
        active = await sampler.start(GROUP_ID, expected_revision=1)
        assert started.ok and active.code == "MONITOR_GROUP_CONFLICT"
        await sampler.close()
        closed = await sampler.start(GROUP_ID, expected_revision=1)
        assert closed.code == "MONITOR_REQUEST_INVALID"

    asyncio.run(scenario())


def test_duplicate_watch_inputs_are_deduplicated_defensively(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        group = _group(items=(WatchItem.variable("counter"),))
        object.__setattr__(group, "items", (WatchItem.variable("counter"), WatchItem.variable("counter")))
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(observation, FakeGroups(group), FakeHistory())
        stream = sampler.subscribe()
        pending = asyncio.create_task(_next(stream))
        result = await sampler.start(GROUP_ID, expected_revision=1)
        batch = await pending
        try:
            assert result.ok
            assert len(batch.values) == 1
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_item_errors_do_not_pause_run_and_variable_register_order_is_preserved(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        observation.item_error = True
        group = _group(items=(WatchItem.variable("bad"), WatchItem.register("GPIOA.IDR"), WatchItem.variable("good")))
        sampler = MonitorSampler(observation, FakeGroups(group), FakeHistory())
        stream = sampler.subscribe()
        pending = asyncio.create_task(_next(stream))
        await sampler.start(GROUP_ID, expected_revision=1)
        batch = await pending
        try:
            assert [value.watch for value in batch.values] == list(group.items)
            assert [value.status for value in batch.values] == ["ERROR", "OK", "OK"]
            assert sampler.state is SamplerState.RUNNING
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_slow_tick_skips_deadlines_without_bursting(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project), delay=0.25)
        sampler = MonitorSampler(observation, FakeGroups(_group()), FakeHistory())
        stream = sampler.subscribe()
        await sampler.start(GROUP_ID, expected_revision=1)
        batches = [await _next(stream, 3) for _ in range(3)]
        try:
            gaps = [right - left for left, right in zip(observation.call_times, observation.call_times[1:])]
            assert all(gap >= 0.24 for gap in gaps)
            assert any(batch.deadline_drops > 0 for batch in batches[1:])
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_subscriber_queue_holds_eight_and_drops_oldest(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(observation, FakeGroups(_group()), FakeHistory())
        stream = sampler.subscribe()
        first_pending = asyncio.create_task(_next(stream))
        await sampler.start(GROUP_ID, expected_revision=1)
        first = await first_pending
        while observation.calls < 12:
            await asyncio.sleep(0.02)
        queued = [await _next(stream) for _ in range(8)]
        try:
            assert first.sequence == 0
            assert queued[0].sequence >= 4
            assert any(batch.subscriber_drops > 0 for batch in queued)
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_history_queue_is_nonblocking_bounded_and_reports_drops(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        release = threading.Event()
        history = FakeHistory(release=release)
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(
            observation,
            FakeGroups(_group()),
            history,
            _history_queue_batches=1,
            _history_queue_bytes=8 * 1024 * 1024,
        )
        stream = sampler.subscribe()
        pending = asyncio.create_task(_next(stream))
        await sampler.start(GROUP_ID, expected_revision=1)
        await pending
        assert await asyncio.to_thread(history.entered.wait, 2)
        batches = [await _next(stream) for _ in range(4)]
        try:
            assert observation.calls >= 5
            assert any(batch.history_drops > 0 for batch in batches)
        finally:
            release.set()
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_provenance_loss_pauses_without_spin_resume_or_auto_reacquire(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        observation.block_after = 1
        sampler = MonitorSampler(observation, FakeGroups(_group()), FakeHistory())
        await sampler.start(GROUP_ID, expected_revision=1)
        deadline = time.monotonic() + 2
        while sampler.state is not SamplerState.PAUSED_BLOCKED and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        calls = observation.revalidate_calls
        await asyncio.sleep(0.25)
        try:
            assert sampler.state is SamplerState.PAUSED_BLOCKED
            assert observation.revalidate_calls == calls
            resumed = await sampler.resume()
            assert not resumed.ok and resumed.code == "MONITOR_FIRMWARE_CHANGED"
            assert observation.revalidate_calls == calls
        finally:
            await sampler.close()

    asyncio.run(scenario())


def test_group_revision_change_blocks_active_run(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        groups = FakeGroups(_group(revision=1))
        sampler = MonitorSampler(FakeObservation(_binding(project)), groups, FakeHistory())
        await sampler.start(GROUP_ID, expected_revision=1)
        groups.group = _group(revision=2)
        deadline = time.monotonic() + 2
        while sampler.state is not SamplerState.PAUSED_BLOCKED and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        try:
            assert sampler.state is SamplerState.PAUSED_BLOCKED
            assert sampler.blocked_code == "MONITOR_GROUP_CONFLICT"
        finally:
            await sampler.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["missing", "raise"])
def test_group_store_loss_blocks_active_run_without_leaking_details(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        groups = FakeGroups(_group())
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(observation, groups, FakeHistory())
        await sampler.start(GROUP_ID, expected_revision=1)
        if mode == "missing":
            groups.missing = True
        else:
            groups.raise_load = True
        deadline = time.monotonic() + 2
        while sampler.state is not SamplerState.PAUSED_BLOCKED and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        try:
            assert sampler.state is SamplerState.PAUSED_BLOCKED
            assert sampler.blocked_code in {"MONITOR_GROUP_NOT_FOUND", "MONITOR_STORAGE_INVALID"}
        finally:
            await sampler.close()

    asyncio.run(scenario())


def test_probe_read_block_and_unexpected_adapter_failure_pause_whole_run(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(observation, FakeGroups(_group()), FakeHistory())
        sampler._probe.read = lambda watches: asyncio.sleep(0, result=SimpleNamespace(  # type: ignore[method-assign]
            blocked_code="PROBE_LEASE_LOST", values=()
        ))
        await sampler.start(GROUP_ID, expected_revision=1)
        deadline = time.monotonic() + 2
        while sampler.state is not SamplerState.PAUSED_BLOCKED and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert sampler.blocked_code == "PROBE_LEASE_LOST"
        await sampler.stop()

        sampler._probe.read = lambda watches: (_ for _ in ()).throw(RuntimeError("secret"))  # type: ignore[method-assign]
        await sampler.start(GROUP_ID, expected_revision=1)
        deadline = time.monotonic() + 2
        while sampler.state is not SamplerState.PAUSED_BLOCKED and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        try:
            assert sampler.blocked_code == "MONITOR_PROVENANCE_CHANGED"
        finally:
            await sampler.close()

    asyncio.run(scenario())


def test_pause_resume_stop_and_new_start_create_distinct_runs(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group()), FakeHistory())
        stream = sampler.subscribe()
        first_pending = asyncio.create_task(_next(stream))
        await sampler.start(GROUP_ID, expected_revision=1)
        first = await first_pending
        paused = await sampler.pause()
        await asyncio.sleep(0.15)
        resumed = await sampler.resume()
        second = await _next(stream)
        stopped = await sampler.stop()
        restarted_pending = asyncio.create_task(_next(stream))
        restarted = await sampler.start(GROUP_ID, expected_revision=1)
        third = await restarted_pending
        try:
            assert all(result.ok for result in (paused, resumed, stopped, restarted))
            assert second.run_id == first.run_id
            assert third.run_id != first.run_id and third.sequence == 0
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("raise_append", [False, True])
def test_history_storage_failures_are_counted_without_blocking_sampling(tmp_path: Path, raise_append: bool) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        history = FakeHistory(fail=not raise_append, raise_append=raise_append)
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group()), history)
        stream = sampler.subscribe()
        await sampler.start(GROUP_ID, expected_revision=1)
        first = await _next(stream)
        second = await _next(stream)
        try:
            assert first.history_drops == 0
            assert second.history_drops >= 1
            assert sampler.state is SamplerState.RUNNING
        finally:
            await stream.aclose()
            await sampler.close()

    asyncio.run(scenario())


def test_invalid_lifecycle_calls_and_close_terminate_full_subscriber(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group()), FakeHistory())
        assert not (await sampler.pause()).ok
        assert not (await sampler.resume()).ok
        assert (await sampler.stop()).data == {"stopped": False}

        stream = sampler.subscribe()
        await sampler.start(GROUP_ID, expected_revision=1)
        while sampler._subscribers and next(iter(sampler._subscribers)).qsize() < 8:
            await asyncio.sleep(0.02)
        await sampler.close()
        with pytest.raises(StopAsyncIteration):
            while True:
                await _next(stream)
        assert not (await sampler.stop()).ok
        await sampler.close()

    asyncio.run(scenario())


def test_repeated_cancellation_cannot_release_close_ownership_early(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        release = threading.Event()
        history = FakeHistory(release=release)
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group()), history)
        await sampler.start(GROUP_ID, expected_revision=1)
        assert await asyncio.to_thread(history.entered.wait, 2)

        closing = asyncio.create_task(sampler.close())
        await asyncio.sleep(0)
        closing.cancel()
        await asyncio.sleep(0.05)
        assert not closing.done()
        assert sampler.state is not SamplerState.CLOSED
        release.set()
        try:
            await closing
        except asyncio.CancelledError:
            pass
        await sampler.close()
        assert sampler.state is SamplerState.CLOSED
        assert not sampler.tasks

    asyncio.run(scenario())


def test_stop_cancellation_waits_for_owned_cleanup_before_propagating(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        release = threading.Event()
        history = FakeHistory(release=release)
        sampler = MonitorSampler(FakeObservation(_binding(project)), FakeGroups(_group()), history)
        await sampler.start(GROUP_ID, expected_revision=1)
        assert await asyncio.to_thread(history.entered.wait, 2)

        first_stop = asyncio.create_task(sampler.stop())
        await asyncio.sleep(0)
        first_stop.cancel()
        await asyncio.sleep(0.05)
        second_stop = asyncio.create_task(sampler.stop())
        await asyncio.sleep(0.05)
        try:
            assert not first_stop.done()
            assert not second_stop.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await first_stop
            stopped = await second_stop
            assert stopped.ok and stopped.data == {"stopped": True}
            assert sampler.state is SamplerState.IDLE
            assert sampler._history_queue is None and sampler._history_queue_bytes == 0
            assert not sampler.tasks

            restarted = await sampler.start(GROUP_ID, expected_revision=1)
            stopped_again = await sampler.stop()
            assert restarted.ok
            assert stopped_again.ok and stopped_again.data == {"stopped": True}
            assert sampler.state is SamplerState.IDLE and not sampler.tasks
        finally:
            release.set()
            try:
                await sampler.close()
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_subscriber_drop_evidence_survives_eviction_without_affecting_fast_subscriber(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(observation, FakeGroups(_group()), FakeHistory())
        slow = sampler.subscribe()
        fast = sampler.subscribe()
        slow_first = asyncio.create_task(_next(slow))
        fast_first = asyncio.create_task(_next(fast))
        await sampler.start(GROUP_ID, expected_revision=1)
        delivered_to_slow = [await slow_first]
        delivered_to_fast = [await fast_first]
        try:
            while delivered_to_fast[-1].sequence < 19:
                delivered_to_fast.append(await _next(fast, 3))
            delivered_to_slow.extend([await _next(slow) for _ in range(8)])

            produced = delivered_to_fast[-1].sequence + 1
            assert produced == len(delivered_to_slow) + sum(batch.subscriber_drops for batch in delivered_to_slow)
            assert all(batch.subscriber_drops == 0 for batch in delivered_to_fast)
        finally:
            await slow.aclose()
            await fast.aclose()
            await sampler.close()

    asyncio.run(scenario())
