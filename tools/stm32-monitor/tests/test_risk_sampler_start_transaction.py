from __future__ import annotations

import asyncio
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

        def failing_factory(loop: asyncio.AbstractEventLoop, coro, **kwargs):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == failed_task_index:
                coro.close()
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
            finally:
                loop.set_task_factory(previous_factory)
                stopped = await sampler.stop()
                assert stopped.ok
                assert sampler.state is SamplerState.IDLE

            assert observed_error is injected
            assert factory_calls == failed_task_index
            assert observed_state is SamplerState.IDLE
            assert not observed_tasks
            assert observed_plan_invalidations >= 2
            assert observation.plan_invalidations > observed_plan_invalidations

            restarted = await sampler.start(GROUP_ID, expected_revision=1)
            assert restarted.ok
            assert sampler.state is SamplerState.RUNNING
            restarted_stop = await sampler.stop()
            assert restarted_stop.ok
            assert sampler.state is SamplerState.IDLE
        finally:
            loop.set_task_factory(previous_factory)
            await sampler.close()

    asyncio.run(scenario())
