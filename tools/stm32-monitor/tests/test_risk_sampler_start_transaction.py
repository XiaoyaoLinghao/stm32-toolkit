from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
from stm32_monitor.sampler import MonitorSampler, SamplerState
from test_sampler import (
    GROUP_ID,
    FakeGroups,
    FakeHistory,
    FakeObservation,
    _binding,
    _group,
)


class OwnedTaskAllocationFailure(RuntimeError):
    """Test-owned host allocation failure for one sampler child task."""


class CleanupTaskAllocationFailure(RuntimeError):
    """Test-owned host allocation failure for rollback cleanup ownership."""


@pytest.mark.parametrize(
    "failed_task_index",
    (1, 2),
    ids=("history-task", "producer-task"),
)
def test_public_start_task_allocation_failure_is_transactional(
    tmp_path: Path,
    failed_task_index: int,
) -> None:
    async def scenario() -> None:
        project = tmp_path / f"project-{failed_task_index}"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(
            observation,
            FakeGroups(_group()),
            FakeHistory(),
        )
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()
        injected = OwnedTaskAllocationFailure(
            f"owned sampler task allocation {failed_task_index}"
        )
        factory_calls = 0
        rejected_coro = None

        def failing_factory(loop: asyncio.AbstractEventLoop, coro, **kwargs):
            nonlocal factory_calls, rejected_coro
            factory_calls += 1
            if factory_calls == failed_task_index:
                rejected_coro = coro
                raise injected
            if previous_factory is not None:
                return previous_factory(loop, coro, **kwargs)
            return asyncio.Task(coro, loop=loop, **kwargs)

        observed_error: OwnedTaskAllocationFailure | None = None
        observed_state: SamplerState | None = None
        observed_tasks: tuple[asyncio.Task[None], ...] = ()
        observed_plan_invalidations = 0
        try:
            loop.set_task_factory(failing_factory)
            try:
                with pytest.raises(OwnedTaskAllocationFailure) as error:
                    await sampler.start(GROUP_ID, expected_revision=1)
                observed_error = error.value
                observed_state = sampler.state
                observed_tasks = sampler.tasks
                observed_plan_invalidations = observation.plan_invalidations
                assert rejected_coro is not None
                assert inspect.getcoroutinestate(rejected_coro) is inspect.CORO_CLOSED
            finally:
                loop.set_task_factory(previous_factory)
                stopped = await sampler.stop()
                assert stopped.ok
                assert sampler.state is SamplerState.IDLE

            assert observed_error is injected
            assert factory_calls == failed_task_index + 1
            assert observed_state is SamplerState.IDLE
            assert not observed_tasks
            assert observed_plan_invalidations >= 2

            restarted = await sampler.start(GROUP_ID, expected_revision=1)
            assert restarted.ok
            assert sampler.state is SamplerState.RUNNING
            restarted_stop = await sampler.stop()
            assert restarted_stop.ok
            assert sampler.state is SamplerState.IDLE
        finally:
            loop.set_task_factory(previous_factory)
            if (
                rejected_coro is not None
                and inspect.getcoroutinestate(rejected_coro) is not inspect.CORO_CLOSED
            ):
                rejected_coro.close()
            await sampler.close()

    asyncio.run(scenario())


def test_public_start_rollback_survives_parent_cancellation(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "cancellation-project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(
            observation,
            FakeGroups(_group()),
            FakeHistory(),
        )
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()
        injected = OwnedTaskAllocationFailure("owned sampler task allocation 2")
        cleanup_gate = asyncio.Event()
        history_started = asyncio.Event()
        cleanup_created = asyncio.Event()
        factory_calls = 0
        rejected_coro = None

        def task_factory(loop: asyncio.AbstractEventLoop, coro, **kwargs):
            nonlocal factory_calls, rejected_coro
            factory_calls += 1
            # Python 3.12 invokes the loop factory without the create_task name;
            # start() allocates history, producer, then rollback in this order.
            if factory_calls == 1:

                async def held_history():
                    history_started.set()
                    await cleanup_gate.wait()
                    return await coro

                held_coro = held_history()
                if previous_factory is not None:
                    return previous_factory(loop, held_coro, **kwargs)
                return asyncio.Task(held_coro, loop=loop, **kwargs)
            if factory_calls == 2:
                rejected_coro = coro
                raise injected
            if factory_calls == 3:
                cleanup_created.set()
            if previous_factory is not None:
                return previous_factory(loop, coro, **kwargs)
            return asyncio.Task(coro, loop=loop, **kwargs)

        start_task = asyncio.create_task(
            sampler.start(GROUP_ID, expected_revision=1),
            name="sampler-start-cancellation-caller",
        )
        try:
            loop.set_task_factory(task_factory)
            await asyncio.wait_for(history_started.wait(), timeout=5)
            await asyncio.wait_for(cleanup_created.wait(), timeout=5)
            assert not start_task.done()
            assert sampler.state is SamplerState.STOPPING
            assert sampler.tasks

            loop.set_task_factory(previous_factory)
            start_task.cancel()
            cleanup_gate.set()
            with pytest.raises(asyncio.CancelledError):
                await start_task

            assert factory_calls == 3
            assert rejected_coro is not None
            assert inspect.getcoroutinestate(rejected_coro) is inspect.CORO_CLOSED
            assert sampler.state is SamplerState.IDLE
            assert not sampler.tasks
            assert observation.plan_invalidations >= 2

            restarted = await sampler.start(GROUP_ID, expected_revision=1)
            assert restarted.ok
            assert sampler.state is SamplerState.RUNNING
            restarted_stop = await sampler.stop()
            assert restarted_stop.ok
            assert sampler.state is SamplerState.IDLE
        finally:
            loop.set_task_factory(previous_factory)
            cleanup_gate.set()
            if not start_task.done():
                start_task.cancel()
            try:
                await start_task
            except (
                asyncio.CancelledError,
                OwnedTaskAllocationFailure,
            ) as cleanup_error:
                del cleanup_error
            if (
                rejected_coro is not None
                and inspect.getcoroutinestate(rejected_coro) is not inspect.CORO_CLOSED
            ):
                rejected_coro.close()
            await sampler.close()

    asyncio.run(scenario())


def test_public_start_cleanup_allocation_refusal_preserves_recovery(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "cleanup-refusal-project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        sampler = MonitorSampler(
            observation,
            FakeGroups(_group()),
            FakeHistory(),
        )
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()
        producer_error = OwnedTaskAllocationFailure(
            "owned sampler producer allocation refused"
        )
        cleanup_error = CleanupTaskAllocationFailure(
            "owned sampler rollback allocation refused"
        )
        factory_calls = 0
        rejected_producer_coro = None
        rejected_cleanup_coro = None
        start_task = asyncio.create_task(
            sampler.start(GROUP_ID, expected_revision=1),
            name="sampler-start-cleanup-refusal-caller",
        )

        def task_factory(loop: asyncio.AbstractEventLoop, coro, **kwargs):
            nonlocal factory_calls, rejected_cleanup_coro, rejected_producer_coro
            factory_calls += 1
            # Python 3.12 invokes the loop factory without the create_task name;
            # start() allocates history, producer, then rollback in this order.
            if factory_calls == 2:
                rejected_producer_coro = coro
                raise producer_error
            if factory_calls == 3:
                rejected_cleanup_coro = coro
                raise cleanup_error
            if previous_factory is not None:
                return previous_factory(loop, coro, **kwargs)
            return asyncio.Task(coro, loop=loop, **kwargs)

        try:
            loop.set_task_factory(task_factory)
            with pytest.raises(OwnedTaskAllocationFailure) as error:
                await asyncio.wait_for(start_task, timeout=5)

            assert error.value is producer_error
            assert error.value.__cause__ is cleanup_error
            assert factory_calls == 3
            assert rejected_producer_coro is not None
            assert rejected_cleanup_coro is not None
            assert (
                inspect.getcoroutinestate(rejected_producer_coro) is inspect.CORO_CLOSED
            )
            assert (
                inspect.getcoroutinestate(rejected_cleanup_coro) is inspect.CORO_CLOSED
            )
            assert sampler.state is SamplerState.STOPPING
            observed_tasks = sampler.tasks
            assert len(observed_tasks) == 1
            history_task = observed_tasks[0]
            assert history_task.get_name() == "stm32-monitor-history-writer"
            assert not history_task.done()

            loop.set_task_factory(previous_factory)
            stopped = await asyncio.wait_for(sampler.stop(), timeout=5)
            assert stopped.ok
            assert sampler.state is SamplerState.IDLE
            assert not sampler.tasks
            assert history_task.done()

            restarted = await asyncio.wait_for(
                sampler.start(GROUP_ID, expected_revision=1),
                timeout=5,
            )
            assert restarted.ok
            assert sampler.state is SamplerState.RUNNING
            restarted_stop = await asyncio.wait_for(sampler.stop(), timeout=5)
            assert restarted_stop.ok
            assert sampler.state is SamplerState.IDLE
        finally:
            loop.set_task_factory(previous_factory)
            if (
                rejected_producer_coro is not None
                and inspect.getcoroutinestate(rejected_producer_coro)
                is not inspect.CORO_CLOSED
            ):
                rejected_producer_coro.close()
            if (
                rejected_cleanup_coro is not None
                and inspect.getcoroutinestate(rejected_cleanup_coro)
                is not inspect.CORO_CLOSED
            ):
                rejected_cleanup_coro.close()
            if not start_task.done():
                start_task.cancel()
            try:
                await start_task
            except (
                asyncio.CancelledError,
                CleanupTaskAllocationFailure,
                OwnedTaskAllocationFailure,
            ) as cleanup_error_value:
                del cleanup_error_value
            await sampler.close()

    asyncio.run(scenario())
