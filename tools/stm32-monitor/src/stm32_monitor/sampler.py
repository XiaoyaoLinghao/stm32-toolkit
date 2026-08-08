from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from enum import Enum
from uuid import UUID, uuid4

from .models import SampleBatch, WatchGroup, WatchItem
from .probe_session import ProbeSession
from .protocol import ProtocolResult, failure, success


SUBSCRIBER_QUEUE_BATCHES = 8
HISTORY_QUEUE_BATCHES = 128
HISTORY_QUEUE_BYTES = 8 * 1024 * 1024
_STREAM_END = object()
_HISTORY_END = object()


class SamplerState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    PAUSED_BLOCKED = "PAUSED_BLOCKED"
    CLOSED = "CLOSED"


async def _await_owned(task: asyncio.Task[None]) -> asyncio.CancelledError | None:
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
        except BaseException:
            break
    task.result()
    return cancellation


class MonitorSampler:
    def __init__(
        self,
        observation: object,
        groups: object,
        history: object,
        *,
        _history_queue_batches: int = HISTORY_QUEUE_BATCHES,
        _history_queue_bytes: int = HISTORY_QUEUE_BYTES,
    ) -> None:
        if not hasattr(groups, "get_group") or not hasattr(history, "append_batch"):
            raise TypeError("sampler stores are invalid")
        if (
            not isinstance(_history_queue_batches, int)
            or isinstance(_history_queue_batches, bool)
            or not 1 <= _history_queue_batches <= HISTORY_QUEUE_BATCHES
            or not isinstance(_history_queue_bytes, int)
            or isinstance(_history_queue_bytes, bool)
            or not 1 <= _history_queue_bytes <= HISTORY_QUEUE_BYTES
        ):
            raise ValueError("history queue limits are invalid")
        self._probe = ProbeSession(observation)
        self._groups = groups
        self._history = history
        self._history_queue_batches = _history_queue_batches
        self._history_queue_limit = _history_queue_bytes
        self._history_queue: asyncio.Queue[object] | None = None
        self._history_queue_bytes = 0
        self._producer_task: asyncio.Task[None] | None = None
        self._history_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._run_gate: asyncio.Event | None = None
        self._action_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[object]] = set()
        self._group: WatchGroup | None = None
        self._watches: tuple[WatchItem, ...] = ()
        self._run_id: UUID | None = None
        self._sequence = 0
        self._last_capture_monotonic_ns: int | None = None
        self._subscriber_drops_pending = 0
        self._history_drops_pending = 0
        self._deadline_drops_pending = 0
        self._reset_deadline = False
        self.state = SamplerState.IDLE
        self.blocked_code: str | None = None

    @property
    def tasks(self) -> tuple[asyncio.Task[None], ...]:
        return tuple(
            task
            for task in (self._producer_task, self._history_task, self._close_task)
            if task is not None and not task.done()
        )

    async def _get_group(self, group_id: UUID):
        return await asyncio.to_thread(self._groups.get_group, group_id)

    async def start(self, group_id: UUID, *, expected_revision: int) -> ProtocolResult[dict[str, object]]:
        operation = "sampling.start"
        async with self._action_lock:
            if self.state is SamplerState.CLOSED:
                return failure(operation, "MONITOR_REQUEST_INVALID", "sampler is closed")
            if self.state is not SamplerState.IDLE:
                return failure(operation, "MONITOR_GROUP_CONFLICT", "sampling is already active")
            if (
                not isinstance(group_id, UUID)
                or not isinstance(expected_revision, int)
                or isinstance(expected_revision, bool)
                or expected_revision < 1
            ):
                return failure(operation, "MONITOR_REQUEST_INVALID", "sampling request is invalid")
            try:
                result = await self._get_group(group_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                return failure(operation, "MONITOR_STORAGE_INVALID", "watch group cannot be loaded")
            if getattr(result, "ok", None) is not True or not isinstance(getattr(result, "data", None), WatchGroup):
                code = getattr(result, "code", "MONITOR_GROUP_NOT_FOUND")
                message = getattr(result, "message", "watch group was not found")
                return failure(operation, code, message)
            group = result.data
            if group.revision != expected_revision:
                return failure(operation, "MONITOR_GROUP_CONFLICT", "watch group revision changed")
            if not 100 <= group.interval_ms <= 5_000 or not group.items:
                return failure(operation, "MONITOR_REQUEST_INVALID", "watch group cannot be sampled")
            seen: set[tuple[str, str]] = set()
            watches: list[WatchItem] = []
            for watch in group.items:
                key = (watch.kind, watch.selector)
                if key not in seen:
                    seen.add(key)
                    watches.append(watch)
            if len(watches) > 256:
                return failure(operation, "MONITOR_GROUP_LIMIT_EXCEEDED", "active watch limit was exceeded")
            self._group = group
            self._watches = tuple(watches)
            self._run_id = uuid4()
            self._sequence = 0
            self._last_capture_monotonic_ns = None
            self._subscriber_drops_pending = 0
            self._history_drops_pending = 0
            self._deadline_drops_pending = 0
            self._stop_event = asyncio.Event()
            self._run_gate = asyncio.Event()
            self._run_gate.set()
            self._history_queue = asyncio.Queue(maxsize=self._history_queue_batches)
            self._history_queue_bytes = 0
            self.blocked_code = None
            self.state = SamplerState.RUNNING
            self._history_task = asyncio.create_task(self._history_writer(), name="stm32-monitor-history-writer")
            self._producer_task = asyncio.create_task(self._produce(), name="stm32-monitor-sampler")
            return success(
                operation,
                {
                    "groupId": str(group.group_id),
                    "groupRevision": group.revision,
                    "runId": str(self._run_id),
                    "intervalMs": group.interval_ms,
                },
            )

    async def _current_group(self) -> bool:
        group = self._group
        if group is None:
            return False
        try:
            result = await self._get_group(group.group_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._block("MONITOR_STORAGE_INVALID")
            return False
        current = getattr(result, "data", None)
        if getattr(result, "ok", None) is not True or not isinstance(current, WatchGroup):
            self._block(getattr(result, "code", "MONITOR_GROUP_CONFLICT"))
            return False
        if current.revision != group.revision or current.items != group.items or current.interval_ms != group.interval_ms:
            self._block("MONITOR_GROUP_CONFLICT")
            return False
        return True

    def _block(self, code: str) -> None:
        self.blocked_code = code if isinstance(code, str) and code else "MONITOR_PROVENANCE_CHANGED"
        self.state = SamplerState.PAUSED_BLOCKED
        if self._run_gate is not None:
            self._run_gate.clear()

    async def _produce(self) -> None:
        group = self._group
        run_id = self._run_id
        stop_event = self._stop_event
        run_gate = self._run_gate
        if group is None or run_id is None or stop_event is None or run_gate is None:
            return
        interval_ns = group.interval_ms * 1_000_000
        next_deadline = time.monotonic_ns()
        try:
            while not stop_event.is_set():
                await run_gate.wait()
                if stop_event.is_set():
                    return
                if self._reset_deadline:
                    next_deadline = time.monotonic_ns()
                    self._reset_deadline = False
                delay_ns = next_deadline - time.monotonic_ns()
                if delay_ns > 0:
                    await asyncio.sleep(delay_ns / 1_000_000_000)
                if stop_event.is_set() or self.state is not SamplerState.RUNNING:
                    continue
                if not await self._current_group():
                    return
                validation = await self._probe.revalidate()
                if not validation.ok:
                    self._block(validation.code)
                    return
                started = time.monotonic_ns()
                scheduled_unix_ns = max(0, time.time_ns() - max(0, started - next_deadline))
                outcome = await self._probe.read(self._watches)
                if outcome.blocked_code is not None:
                    self._block(outcome.blocked_code)
                    return
                captured_monotonic = time.monotonic_ns()
                captured_unix_ns = time.time_ns()
                subscriber_drops = self._subscriber_drops_pending
                history_drops = self._history_drops_pending
                deadline_drops = self._deadline_drops_pending
                self._subscriber_drops_pending = 0
                self._history_drops_pending = 0
                self._deadline_drops_pending = 0
                if self._last_capture_monotonic_ns is None:
                    actual_rate_hz = 0.0
                else:
                    elapsed = captured_monotonic - self._last_capture_monotonic_ns
                    actual_rate_hz = 0.0 if elapsed <= 0 else 1_000_000_000 / elapsed
                self._last_capture_monotonic_ns = captured_monotonic
                batch = SampleBatch(
                    binding=self._probe.binding,
                    group_id=group.group_id,
                    group_revision=group.revision,
                    run_id=run_id,
                    sequence=self._sequence,
                    scheduled_unix_ns=scheduled_unix_ns,
                    captured_unix_ns=max(captured_unix_ns, scheduled_unix_ns),
                    latency_ns=max(0, captured_monotonic - started),
                    actual_rate_hz=actual_rate_hz,
                    subscriber_drops=subscriber_drops,
                    history_drops=history_drops,
                    deadline_drops=deadline_drops,
                    values=outcome.values,
                )
                self._sequence += 1
                self._enqueue_history(batch)
                self._broadcast(batch)
                next_deadline += interval_ns
                now = time.monotonic_ns()
                if now >= next_deadline:
                    missed = (now - next_deadline) // interval_ns + 1
                    self._deadline_drops_pending += int(missed)
                    next_deadline += int(missed) * interval_ns
        except asyncio.CancelledError:
            raise
        except Exception:
            self._block("MONITOR_PROVENANCE_CHANGED")

    @staticmethod
    def _batch_bytes(batch: SampleBatch) -> int:
        return len(json.dumps(batch.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    def _enqueue_history(self, batch: SampleBatch) -> None:
        queue = self._history_queue
        if queue is None:
            self._history_drops_pending += 1
            return
        size = self._batch_bytes(batch)
        if queue.full() or size > self._history_queue_limit - self._history_queue_bytes:
            self._history_drops_pending += 1
            return
        queue.put_nowait((batch, size))
        self._history_queue_bytes += size

    def _broadcast(self, batch: SampleBatch) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                else:
                    self._subscriber_drops_pending += 1
            queue.put_nowait(batch)

    async def _history_writer(self) -> None:
        queue = self._history_queue
        if queue is None:
            return
        while True:
            item = await queue.get()
            try:
                if item is _HISTORY_END:
                    return
                batch, size = item
                try:
                    result = await asyncio.to_thread(self._history.append_batch, batch)
                    if getattr(result, "ok", None) is not True:
                        self._history_drops_pending += 1
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._history_drops_pending += 1
                finally:
                    self._history_queue_bytes = max(0, self._history_queue_bytes - size)
            finally:
                queue.task_done()

    async def pause(self) -> ProtocolResult[dict[str, object]]:
        operation = "sampling.pause"
        async with self._action_lock:
            if self.state is not SamplerState.RUNNING:
                return failure(operation, self.blocked_code or "MONITOR_REQUEST_INVALID", "sampling cannot be paused")
            self.state = SamplerState.PAUSED
            if self._run_gate is not None:
                self._run_gate.clear()
            return success(operation, {"paused": True})

    async def resume(self) -> ProtocolResult[dict[str, object]]:
        operation = "sampling.resume"
        async with self._action_lock:
            if self.state is SamplerState.PAUSED_BLOCKED:
                return failure(operation, self.blocked_code or "MONITOR_PROVENANCE_CHANGED", "sampling is blocked")
            if self.state is not SamplerState.PAUSED:
                return failure(operation, "MONITOR_REQUEST_INVALID", "sampling is not paused")
            self.state = SamplerState.RUNNING
            self._reset_deadline = True
            if self._run_gate is not None:
                self._run_gate.set()
            return success(operation, {"resumed": True})

    async def _stop_run(self) -> None:
        stop_event = self._stop_event
        run_gate = self._run_gate
        if stop_event is not None:
            stop_event.set()
        if run_gate is not None:
            run_gate.set()
        producer = self._producer_task
        if producer is not None and not producer.done():
            producer.cancel()
        if producer is not None:
            await asyncio.gather(producer, return_exceptions=True)
        queue = self._history_queue
        history_task = self._history_task
        if queue is not None and history_task is not None and not history_task.done():
            await queue.put(_HISTORY_END)
        if history_task is not None:
            await history_task
        self._producer_task = None
        self._history_task = None
        self._history_queue = None
        self._history_queue_bytes = 0
        self._stop_event = None
        self._run_gate = None
        self._group = None
        self._watches = ()
        self._run_id = None
        self._sequence = 0
        self._last_capture_monotonic_ns = None

    async def stop(self) -> ProtocolResult[dict[str, object]]:
        operation = "sampling.stop"
        async with self._action_lock:
            if self.state is SamplerState.CLOSED:
                return failure(operation, "MONITOR_REQUEST_INVALID", "sampler is closed")
            if self.state is SamplerState.IDLE:
                return success(operation, {"stopped": False})
            await self._stop_run()
            self.state = SamplerState.IDLE
            self.blocked_code = None
            return success(operation, {"stopped": True})

    async def subscribe(self) -> AsyncIterator[SampleBatch]:
        queue: asyncio.Queue[object] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_BATCHES)
        self._subscribers.add(queue)
        if self.state is SamplerState.CLOSED:
            queue.put_nowait(_STREAM_END)
        try:
            while True:
                item = await queue.get()
                if item is _STREAM_END:
                    return
                if isinstance(item, SampleBatch):
                    yield item
        finally:
            self._subscribers.discard(queue)

    async def _close_owned(self) -> None:
        async with self._action_lock:
            if self.state is not SamplerState.CLOSED:
                if self.state is not SamplerState.IDLE:
                    await self._stop_run()
                self.state = SamplerState.CLOSED
                self.blocked_code = None
                for queue in tuple(self._subscribers):
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    queue.put_nowait(_STREAM_END)

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_owned(), name="stm32-monitor-sampler-close")
        cancellation = await _await_owned(self._close_task)
        if cancellation is not None:
            raise cancellation


__all__ = ["MonitorSampler", "SamplerState"]
