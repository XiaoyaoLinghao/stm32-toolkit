from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from stm32_monitor.models import WatchItem
from stm32_monitor.probe_session import ProbeReadOutcome, ProbeSession
from stm32_monitor.protocol import MONITOR_PROTOCOL_VERSION, MONITOR_VERSION
from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.result import OperationResult
from test_probe_session import FakeObservation, _binding

_WATCHES = (WatchItem.variable("counter"),)
_RESULT_KEYS = {
    "protocol",
    "toolkitVersion",
    "monitorVersion",
    "ok",
    "operation",
    "code",
    "message",
    "data",
    "details",
}


def _assert_result_wire(
    result: object,
    *,
    ok: bool,
    operation: str,
    code: str,
    message: str,
    data: object,
) -> None:
    wire = result.to_dict()  # type: ignore[attr-defined]
    assert set(wire) == _RESULT_KEYS
    assert wire == {
        "protocol": MONITOR_PROTOCOL_VERSION,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": MONITOR_VERSION,
        "ok": ok,
        "operation": operation,
        "code": code,
        "message": message,
        "data": data,
        "details": {},
    }


async def _assert_revalidated(session: ProbeSession) -> None:
    result = await session.revalidate()
    _assert_result_wire(
        result,
        ok=True,
        operation="sampling.revalidate",
        code="OK",
        message="",
        data=session.binding.to_dict(),
    )


async def _assert_prepared(session: ProbeSession) -> None:
    result = await session.prepare_read_plan(_WATCHES)
    _assert_result_wire(
        result,
        ok=True,
        operation="sampling.prepare",
        code="OK",
        message="",
        data={"prepared": True},
    )


def _assert_read_success(outcome: ProbeReadOutcome) -> None:
    assert type(outcome) is ProbeReadOutcome
    assert outcome.blocked_code is None
    assert outcome.message == ""
    assert tuple(value.watch for value in outcome.values) == _WATCHES
    assert tuple(value.status for value in outcome.values) == ("OK",)


async def _assert_public_recovery(
    observation: FakeObservation | object,
    session: ProbeSession,
) -> None:
    await _assert_revalidated(session)
    await _assert_prepared(session)
    _assert_read_success(await session.read(_WATCHES))
    if hasattr(observation, "variable_calls"):
        assert observation.variable_calls[-1] == ("counter",)  # type: ignore[attr-defined]


async def _finish_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
    except RuntimeError:
        return


class _FreshTokenObservation(FakeObservation):
    async def revalidate(self):
        self._admission_token = None
        return await super().revalidate()


class _OptionalObservation:
    def __init__(
        self,
        binding: object,
        *,
        include_invalidation: bool,
        include_token: bool,
    ) -> None:
        self._inner = FakeObservation(binding)
        self.binding = self._inner.binding
        self.catalog = self._inner.catalog
        self.svd = self._inner.svd
        if include_invalidation:
            self._invalidate_read_plan = self._inner._invalidate_read_plan
        if include_token:
            self._read_plan_admission = self._inner._read_plan_admission

    async def _read_batch(self, variables, registers):
        return await self._inner._read_batch(variables, registers)

    async def _prepare_read_plan(self, variables, registers, *, admission_token=None):
        return await self._inner._prepare_read_plan(
            variables,
            registers,
            admission_token=admission_token,
        )

    async def _read_prepared(self, plan):
        return await self._inner._read_prepared(plan)

    async def revalidate(self):
        return await self._inner.revalidate()

    def restore_invalidation(self) -> None:
        self._invalidate_read_plan = self._inner._invalidate_read_plan

    def restore_admission_token(self) -> None:
        self._read_plan_admission = self._inner._read_plan_admission


def test_unprepared_failure_with_empty_code_is_isolated_and_recovers(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        original_read_batch = observation._read_batch

        async def empty_code_failure(*_args, **_kwargs):
            return OperationResult.failure("read", "", "adapter failed", {})

        observation._read_batch = empty_code_failure
        session = ProbeSession(observation)
        try:
            outcome = await session.read(_WATCHES)
            assert outcome.blocked_code is None
            assert outcome.message == ""
            assert tuple(value.to_dict() for value in outcome.values) == (
                {
                    "watch": {"kind": "variable", "selector": "counter"},
                    "status": "ERROR",
                    "typedValue": None,
                    "code": "MONITOR_PROVENANCE_CHANGED",
                    "definition": {"kind": "variable", "selector": "counter"},
                },
            )
        finally:
            observation._read_batch = original_read_batch

        _assert_read_success(await session.read(_WATCHES))
        assert observation.variable_calls == [("counter",)]

    asyncio.run(scenario())


def test_unprepared_success_without_data_blocks_and_recovers(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        original_read_batch = observation._read_batch

        async def missing_report(*_args, **_kwargs):
            return OperationResult.success("read", None)

        observation._read_batch = missing_report
        session = ProbeSession(observation)
        try:
            outcome = await session.read(_WATCHES)
            assert outcome.values == ()
            assert outcome.blocked_code == "MONITOR_PROVENANCE_CHANGED"
            assert outcome.message == "Monitor observation report is invalid"
        finally:
            observation._read_batch = original_read_batch

        _assert_read_success(await session.read(_WATCHES))
        assert observation.variable_calls == [("counter",)]

    asyncio.run(scenario())


def test_prepare_unknown_failure_invalidates_and_recovers(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        original_prepare = observation._prepare_read_plan
        awaitable_session = ProbeSession(observation)
        await _assert_revalidated(awaitable_session)

        async def unknown_failure(*_args, **_kwargs):
            return OperationResult.failure("prepare", "UNEXPECTED_PROVIDER", "secret", {})

        observation._prepare_read_plan = unknown_failure
        try:
            result = await awaitable_session.prepare_read_plan(_WATCHES)
            _assert_result_wire(
                result,
                ok=False,
                operation="sampling.prepare",
                code="MONITOR_PROVENANCE_CHANGED",
                message="Monitor read plan could not be prepared",
                data=None,
            )
            assert observation.plan_invalidations == 1
        finally:
            observation._prepare_read_plan = original_prepare

        await _assert_public_recovery(observation, awaitable_session)

    asyncio.run(scenario())


def test_prepare_success_without_plan_invalidates_and_recovers(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        original_prepare = observation._prepare_read_plan
        session = ProbeSession(observation)
        await _assert_revalidated(session)

        async def missing_plan(*_args, **_kwargs):
            return OperationResult.success("prepare", None)

        observation._prepare_read_plan = missing_plan
        try:
            result = await session.prepare_read_plan(_WATCHES)
            _assert_result_wire(
                result,
                ok=False,
                operation="sampling.prepare",
                code="MONITOR_PROVENANCE_CHANGED",
                message="Monitor read plan is invalid",
                data=None,
            )
            assert observation.plan_invalidations == 1
        finally:
            observation._prepare_read_plan = original_prepare

        await _assert_public_recovery(observation, session)

    asyncio.run(scenario())


def test_prepare_plan_after_admission_change_invalidates_and_recovers(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        original_prepare = observation._prepare_read_plan
        session = ProbeSession(observation)
        await _assert_revalidated(session)

        async def changed_admission(variables, registers, *, admission_token=None):
            result = await original_prepare(
                variables,
                registers,
                admission_token=admission_token,
            )
            observation._admission_token = object()
            return result

        observation._prepare_read_plan = changed_admission
        try:
            result = await session.prepare_read_plan(_WATCHES)
            _assert_result_wire(
                result,
                ok=False,
                operation="sampling.prepare",
                code="MONITOR_PROVENANCE_CHANGED",
                message="Monitor read admission changed",
                data=None,
            )
            assert observation.plan_invalidations == 1
        finally:
            observation._prepare_read_plan = original_prepare

        await _assert_public_recovery(observation, session)

    asyncio.run(scenario())


def test_superseded_prepare_failure_does_not_invalidate_new_plan(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _FreshTokenObservation(_binding(project))
        session = ProbeSession(observation)
        await _assert_revalidated(session)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        original_prepare = observation._prepare_read_plan

        async def held_prepare(variables, registers, *, admission_token=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
                return OperationResult.failure(
                    "prepare", "MONITOR_FIRMWARE_CHANGED", "old", {}
                )
            return await original_prepare(
                variables,
                registers,
                admission_token=admission_token,
            )

        observation._prepare_read_plan = held_prepare
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.prepare_read_plan(_WATCHES))
            await asyncio.wait_for(entered.wait(), 1)
            await _assert_revalidated(session)
            await _assert_prepared(session)
            release.set()
            old_result = await old_task
            _assert_result_wire(
                old_result,
                ok=False,
                operation="sampling.prepare",
                code="MONITOR_FIRMWARE_CHANGED",
                message="Monitor read plan could not be prepared",
                data=None,
            )
            _assert_read_success(await session.read(_WATCHES))
            assert calls == 2
            assert observation.plan_invalidations == 0
        finally:
            release.set()
            await _finish_task(old_task)
            observation._prepare_read_plan = original_prepare

    asyncio.run(scenario())


def test_superseded_prepared_read_cancellation_does_not_invalidate_new_plan(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _FreshTokenObservation(_binding(project))
        session = ProbeSession(observation)
        await _assert_revalidated(session)
        await _assert_prepared(session)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        original_read = observation._read_prepared

        async def held_read(plan):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
            return await original_read(plan)

        observation._read_prepared = held_read
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.read(_WATCHES))
            await asyncio.wait_for(entered.wait(), 1)
            await _assert_revalidated(session)
            await _assert_prepared(session)
            old_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await old_task
            _assert_read_success(await session.read(_WATCHES))
            assert calls == 2
            assert observation.plan_invalidations == 0
        finally:
            release.set()
            await _finish_task(old_task)
            observation._read_prepared = original_read

    asyncio.run(scenario())


def test_superseded_prepared_read_exception_does_not_invalidate_new_plan(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _FreshTokenObservation(_binding(project))
        session = ProbeSession(observation)
        await _assert_revalidated(session)
        await _assert_prepared(session)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        original_read = observation._read_prepared

        async def held_read(plan):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
                raise RuntimeError(r"C:\secret\read.log")
            return await original_read(plan)

        observation._read_prepared = held_read
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.read(_WATCHES))
            await asyncio.wait_for(entered.wait(), 1)
            await _assert_revalidated(session)
            await _assert_prepared(session)
            release.set()
            old_outcome = await old_task
            assert old_outcome.values == ()
            assert old_outcome.blocked_code == "MONITOR_PROVENANCE_CHANGED"
            assert old_outcome.message == "Monitor observation read failed"
            assert "secret" not in old_outcome.message
            _assert_read_success(await session.read(_WATCHES))
            assert calls == 2
            assert observation.plan_invalidations == 0
        finally:
            release.set()
            await _finish_task(old_task)
            observation._read_prepared = original_read

    asyncio.run(scenario())


def test_superseded_revalidation_failure_does_not_invalidate_new_plan(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _FreshTokenObservation(_binding(project))
        session = ProbeSession(observation)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        original_revalidate = observation.revalidate

        async def held_revalidate():
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
                return OperationResult.failure(
                    "revalidate", "MONITOR_PROVENANCE_CHANGED", "old", {}
                )
            return await original_revalidate()

        observation.revalidate = held_revalidate
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.revalidate())
            await asyncio.wait_for(entered.wait(), 1)
            await _assert_revalidated(session)
            await _assert_prepared(session)
            release.set()
            old_result = await old_task
            _assert_result_wire(
                old_result,
                ok=False,
                operation="sampling.revalidate",
                code="MONITOR_PROVENANCE_CHANGED",
                message="Monitor observation changed",
                data=None,
            )
            _assert_read_success(await session.read(_WATCHES))
            assert calls == 2
            assert observation.plan_invalidations == 0
        finally:
            release.set()
            await _finish_task(old_task)
            observation.revalidate = original_revalidate

    asyncio.run(scenario())


def test_prepare_without_invalidation_hook_recovers_after_hook_restore(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _OptionalObservation(
            _binding(project),
            include_invalidation=False,
            include_token=True,
        )
        session = ProbeSession(observation)

        result = await session.prepare_read_plan(_WATCHES)
        _assert_result_wire(
            result,
            ok=False,
            operation="sampling.prepare",
            code="MONITOR_PROVENANCE_CHANGED",
            message="Monitor read plan could not be prepared",
            data=None,
        )
        assert observation._inner.prepare_calls == 0

        observation.restore_invalidation()
        await _assert_public_recovery(observation, session)

    asyncio.run(scenario())


def test_revalidate_without_admission_token_recovers_after_capability_restore(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = _OptionalObservation(
            _binding(project),
            include_invalidation=True,
            include_token=False,
        )
        session = ProbeSession(observation)

        result = await session.revalidate()
        _assert_result_wire(
            result,
            ok=False,
            operation="sampling.revalidate",
            code="MONITOR_PROVENANCE_CHANGED",
            message="Monitor observation changed",
            data=None,
        )
        assert observation._inner.plan_invalidations == 1
        assert observation._inner.prepare_calls == 0

        observation.restore_admission_token()
        await _assert_public_recovery(observation, session)

    asyncio.run(scenario())
