from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from stm32_monitor.models import SampleValue, WatchItem
from stm32_monitor.probe_session import ProbeReadOutcome, ProbeSession
from stm32_monitor.protocol import MONITOR_PROTOCOL_VERSION, MONITOR_VERSION
from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.monitor_observation import (
    MonitorObservationSeams,
    MonitorObservationSession,
    open_monitor_observation,
)
from stm32_toolkit.result import OperationResult
from test_debug_read import DebugEnv, debug_env  # noqa: F401
from test_monitor_observation import Harness, ObservationClient, request

_WATCHES = (WatchItem.variable("signed32"), WatchItem.register("GPIOA.IDR"))


def _expected_memory_calls(fixture_env: DebugEnv) -> tuple[tuple[int, int], ...]:
    variable = fixture_env.catalog.lookup("signed32")
    register = fixture_env.selection.register("GPIOA.IDR")
    return (
        (variable.address, variable.byte_size),
        (register.address, register.size_bytes),
    )


def _assert_successful_revalidation(result: object, session: ProbeSession) -> None:
    assert result.to_dict() == {  # type: ignore[attr-defined]
        "protocol": MONITOR_PROTOCOL_VERSION,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": MONITOR_VERSION,
        "ok": True,
        "operation": "sampling.revalidate",
        "code": "OK",
        "message": "",
        "data": session.binding.to_dict(),
        "details": {},
    }


def _assert_successful_prepare(result: object) -> None:
    assert result.to_dict() == {  # type: ignore[attr-defined]
        "protocol": MONITOR_PROTOCOL_VERSION,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": MONITOR_VERSION,
        "ok": True,
        "operation": "sampling.prepare",
        "code": "OK",
        "message": "",
        "data": {"prepared": True},
        "details": {},
    }


def _assert_observation_read_success(
    outcome: ProbeReadOutcome, fixture_env: DebugEnv
) -> None:
    variable = fixture_env.catalog.lookup("signed32")
    register = fixture_env.selection.register("GPIOA.IDR")
    assert type(outcome) is ProbeReadOutcome
    assert outcome.blocked_code is None
    assert outcome.message == ""
    assert tuple(value.watch for value in outcome.values) == _WATCHES
    assert tuple(value.status for value in outcome.values) == ("OK", "OK")
    assert tuple(value.to_dict() for value in outcome.values) == (
        SampleValue(
            WatchItem.variable("signed32"),
            "OK",
            typed_value={
                "expression": "signed32",
                "typeName": variable.type.name,
                "value": -1234567,
                "rawHex": "0xffed2979",
                "bitWidth": 32,
            },
            definition={"kind": "variable", "selector": "signed32"},
        ).to_dict(),
        SampleValue(
            WatchItem.register("GPIOA.IDR"),
            "OK",
            typed_value={
                "expression": "GPIOA.IDR",
                "typeName": f"uint{register.size_bytes * 8}_register",
                "value": 0x12345678,
                "rawHex": "0x12345678",
                "bitWidth": 32,
            },
            definition={"kind": "register", "selector": "GPIOA.IDR"},
        ).to_dict(),
    )


def _assert_superseded_read_failure(outcome: ProbeReadOutcome) -> None:
    assert type(outcome) is ProbeReadOutcome
    assert outcome.values == ()
    assert outcome.blocked_code == "MONITOR_PROVENANCE_CHANGED"
    assert outcome.message == "Monitor observation changed"


def _assert_superseded_revalidation_failure(result: object) -> None:
    assert result.to_dict() == {  # type: ignore[attr-defined]
        "protocol": MONITOR_PROTOCOL_VERSION,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": MONITOR_VERSION,
        "ok": False,
        "operation": "sampling.revalidate",
        "code": "MONITOR_PROVENANCE_CHANGED",
        "message": "Monitor observation changed",
        "data": None,
        "details": {},
    }


async def _settle_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await asyncio.wait_for(task, 1)
    except (asyncio.CancelledError, RuntimeError, asyncio.TimeoutError):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _assert_closed_without_backend_read(
    observation: MonitorObservationSession,
    session: ProbeSession,
    client: ObservationClient,
    harness: Harness,
) -> None:
    calls_before_close = tuple(client.calls)
    await observation.close()
    assert client.closed is True
    assert harness.supervisors[0].stopped is True
    assert harness.supervisors[0].endpoint is None
    assert harness.registry == {}

    await observation.close()
    closed_outcome = await session.read(_WATCHES)
    _assert_superseded_read_failure(closed_outcome)
    assert client.calls == list(calls_before_close)


async def _prepare_public_session(
    fixture_env: DebugEnv,
    data_root: Path,
    harness: Harness,
    *,
    seams: MonitorObservationSeams | None = None,
) -> tuple[MonitorObservationSession, ProbeSession, ObservationClient]:
    opened = await open_monitor_observation(
        request(fixture_env, data_root),
        _seams=harness.seams() if seams is None else seams,
    )
    assert opened.ok is True, opened.to_dict()
    observation = opened.data
    try:
        session = ProbeSession(observation)
        _assert_successful_revalidation(await session.revalidate(), session)
        _assert_successful_prepare(await session.prepare_read_plan(_WATCHES))
    except BaseException:
        await observation.close()
        raise
    return observation, session, harness.clients[0]


@pytest.mark.parametrize("old_read_outcome", ("success", "error", "cancel"))
def test_real_observation_old_read_cannot_supersede_new_public_plan(
    debug_env: DebugEnv,  # noqa: F811
    tmp_path: Path,
    old_read_outcome: str,
) -> None:
    async def scenario() -> None:
        harness = Harness(debug_env)
        observation, session, client = await _prepare_public_session(
            debug_env, tmp_path / "data", harness
        )
        initial_bind_count = len(harness.bind_calls)
        read_entered = asyncio.Event()
        read_release = asyncio.Event()
        read_calls = 0
        phase = "old"
        read_events: list[tuple[str, int, int]] = []
        original_read_memory = client.read_memory

        async def held_read_memory(address: int, length: int) -> bytes:
            nonlocal read_calls
            read_events.append((phase, address, length))
            read_calls += 1
            if read_calls == 1:
                read_entered.set()
                await read_release.wait()
                if old_read_outcome == "error":
                    raise RuntimeError("adapter detail must remain private")
                if old_read_outcome == "cancel":
                    raise asyncio.CancelledError
            return await original_read_memory(address, length)

        client.read_memory = held_read_memory  # type: ignore[method-assign]
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.read(_WATCHES))
            await asyncio.wait_for(read_entered.wait(), 1)

            _assert_successful_prepare(await session.prepare_read_plan(_WATCHES))

            if old_read_outcome == "cancel":
                read_release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(old_task, 1)
            else:
                read_release.set()
                old_outcome = await asyncio.wait_for(old_task, 1)
                _assert_superseded_read_failure(old_outcome)

            phase = "new"
            _assert_observation_read_success(await session.read(_WATCHES), debug_env)
            expected_calls = _expected_memory_calls(debug_env)
            old_call_count = 1 if old_read_outcome == "cancel" else 2
            assert tuple(read_events[:old_call_count]) == tuple(
                ("old", address, length)
                for address, length in expected_calls[:old_call_count]
            )
            assert tuple(read_events[old_call_count:]) == tuple(
                ("new", address, length) for address, length in expected_calls
            )
            assert len(harness.bind_calls) == initial_bind_count
        finally:
            read_release.set()
            await _settle_task(old_task)
            await _assert_closed_without_backend_read(
                observation, session, client, harness
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("old_revalidation_outcome", ("failure", "cancel"))
def test_real_observation_old_revalidation_cannot_clear_new_public_plan(
    debug_env: DebugEnv,  # noqa: F811
    tmp_path: Path,
    old_revalidation_outcome: str,
) -> None:
    async def scenario() -> None:
        harness = Harness(debug_env)
        bind_entered = asyncio.Event()
        bind_release = asyncio.Event()
        bind_calls = 0

        async def held_bind(
            bind_request: object, bind_client: object
        ) -> OperationResult:
            nonlocal bind_calls
            bind_calls += 1
            if bind_calls <= 2:
                return await harness.bind(bind_request, bind_client)
            bind_entered.set()
            await bind_release.wait()
            if old_revalidation_outcome == "cancel":
                raise asyncio.CancelledError
            return OperationResult.failure(
                "stm32_debug_bind",
                "PROBE_LEASE_LOST",
                "Probe lease ownership no longer matches",
                {},
            )

        seams = replace(harness.seams(), bind=held_bind)
        observation, session, client = await _prepare_public_session(
            debug_env, tmp_path / "data", harness, seams=seams
        )
        initial_bind_count = len(harness.bind_calls)
        old_task: asyncio.Task | None = None
        try:
            old_task = asyncio.create_task(session.revalidate())
            await asyncio.wait_for(bind_entered.wait(), 1)

            _assert_successful_prepare(await session.prepare_read_plan(_WATCHES))
            bind_release.set()

            if old_revalidation_outcome == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(old_task, 1)
            else:
                _assert_superseded_revalidation_failure(
                    await asyncio.wait_for(old_task, 1)
                )

            _assert_observation_read_success(await session.read(_WATCHES), debug_env)
            assert tuple(client.calls) == _expected_memory_calls(debug_env)
            assert bind_calls == 3
            assert len(harness.bind_calls) == initial_bind_count
        finally:
            bind_release.set()
            await _settle_task(old_task)
            await _assert_closed_without_backend_read(
                observation, session, client, harness
            )

    asyncio.run(scenario())
