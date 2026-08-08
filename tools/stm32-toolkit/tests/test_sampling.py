from __future__ import annotations

import asyncio

import pytest

from stm32_toolkit.debug import sampling as sampling_mod
from stm32_toolkit.debug.sampling import (
    RegisterSampleRequest,
    SampleVariablesRequest,
    sample_registers,
    sample_variables,
)

from test_debug_read import Client, DebugEnv, debug_env


class Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        assert delay >= 0
        self.now += delay


class TimedClient(Client):
    def __init__(
        self, env: DebugEnv, clock: Clock, *, read_seconds: float = 0.0
    ) -> None:
        super().__init__(dict(env.memory))
        self.clock = clock
        self.read_seconds = read_seconds
        self.read_count = 0

    async def read_memory(self, address: int, length: int) -> bytes:
        self.read_count += 1
        self.clock.now += self.read_seconds
        return await super().read_memory(address, length)


def request(env: DebugEnv, **changes: object) -> SampleVariablesRequest:
    values = {
        "binding": env.binding,
        "catalog": env.catalog,
        "expressions": ("signed32",),
        "interval_ms": 50,
        "count": 3,
        "duration_ms": None,
    }
    values.update(changes)
    return SampleVariablesRequest(**values)


def test_sampling_real_provenance_clamps_interval_and_reports_timing(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()
    client = TimedClient(debug_env, clock, read_seconds=0.01)
    result = asyncio.run(
        sample_variables(
            request(debug_env),
            client,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert result.ok is True
    report = result.data
    assert report.requested_interval_ms == 50
    assert report.applied_interval_ms == 100
    assert len(report.samples) == 3
    assert report.deadline_misses == 0
    assert report.dropped_samples == 0
    assert report.actual_rate_hz == pytest.approx(10.0)
    sample = report.to_dict()["samples"][0]
    assert set(sample) == {
        "index",
        "scheduledOffsetMs",
        "actualOffsetMs",
        "latencyMs",
        "actualAtUtc",
        "items",
    }
    assert sample["items"][0]["status"] == "ok"
    assert client.attach_count == 6


def test_sampling_drops_missed_slots_without_catch_up_storm(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()
    client = TimedClient(debug_env, clock, read_seconds=0.25)
    result = asyncio.run(
        sample_variables(
            request(debug_env, interval_ms=100, count=6),
            client,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert result.ok is True
    assert [sample["index"] for sample in result.data.samples] == [0, 2, 5]
    assert result.data.deadline_misses >= 2
    assert result.data.dropped_samples == 3
    assert client.read_count == 3


def test_sampling_duration_is_finite_and_interval_has_upper_clamp(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()
    result = asyncio.run(
        sample_variables(
            request(debug_env, interval_ms=9000, count=None, duration_ms=10_000),
            TimedClient(debug_env, clock),
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert result.ok is True
    assert result.data.applied_interval_ms == 5000
    assert len(result.data.samples) == 2


def test_sampling_rejects_unbounded_forged_or_oversized_requests(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()
    client = TimedClient(debug_env, clock)
    cases = (
        object(),
        request(debug_env, binding=object()),
        request(debug_env, count=None, duration_ms=None),
        request(debug_env, interval_ms=True),
        request(debug_env, interval_ms=3_600_001),
        request(debug_env, count=True),
        request(debug_env, count=10_001),
        request(debug_env, count=None, duration_ms=3_600_001),
        request(debug_env, expressions=tuple(f"v{i}" for i in range(257))),
        request(debug_env, expressions=("signed32", "signed32")),
        request(debug_env, catalog=object()),
        request(debug_env, expressions=tuple(f"v{i}" for i in range(256)), count=100),
    )
    for invalid in cases:
        result = asyncio.run(
            sample_variables(
                invalid,
                client,
                _monotonic=clock.monotonic,
                _sleep=clock.sleep,
            )
        )
        assert result.code == "DEBUG_SAMPLE_REQUEST_INVALID"
    assert client.calls == []


def test_sampling_rejects_worst_case_report_budget_before_hardware(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()

    class ForbiddenHardware(TimedClient):
        async def attach(self, probe_id: str, target: str) -> object:
            self.attach_count += 1
            raise AssertionError("oversized sample request reached hardware")

    client = ForbiddenHardware(debug_env, clock)
    result = asyncio.run(
        sample_variables(
            request(
                debug_env,
                expressions=("signed32", "unsigned32"),
                count=10_000,
            ),
            client,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert result.code == "DEBUG_SAMPLE_REQUEST_INVALID"
    assert client.attach_count == 0
    assert client.calls == []


def test_sampling_propagates_cancellation_without_background_tasks(
    debug_env: DebugEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()

    class CancelClient(TimedClient):
        async def read_memory(self, address: int, length: int) -> bytes:
            raise asyncio.CancelledError

    def forbidden_task(*args: object, **kwargs: object) -> object:
        raise AssertionError("sampling must not create background tasks")

    monkeypatch.setattr(asyncio, "create_task", forbidden_task)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            sample_variables(
                request(debug_env),
                CancelClient(debug_env, clock),
                _monotonic=clock.monotonic,
                _sleep=clock.sleep,
            )
        )


def test_sampling_stops_on_lost_lease_or_changed_firmware(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()

    class LostLeaseClient(TimedClient):
        async def read_memory(self, address: int, length: int) -> bytes:
            data = await super().read_memory(address, length)
            self.endpoint.lease_id = "replacement-lease"
            return data

    lost = asyncio.run(
        sample_variables(
            request(debug_env),
            LostLeaseClient(debug_env, clock),
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert lost.code == "DEBUG_BINDING_LOST"
    assert lost.details["cause"] == "DEBUG_ENDPOINT_MISMATCH"

    clock = Clock()
    changed_client = TimedClient(debug_env, clock)
    elf_path = debug_env.root / debug_env.binding.elf_path
    changed_client.after_read = lambda: elf_path.write_bytes(
        elf_path.read_bytes() + b"changed"
    )
    changed = asyncio.run(
        sample_variables(
            request(debug_env),
            changed_client,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert changed.code == "DEBUG_BINDING_LOST"
    assert changed.details["cause"] == "DEBUG_FIRMWARE_CHANGED"


def test_sampling_clock_runtime_single_and_all_dropped_branches(
    debug_env: DebugEnv,
) -> None:
    clock = Clock()
    invalid_clock = asyncio.run(
        sample_variables(
            request(debug_env),
            TimedClient(debug_env, clock),
            _monotonic=lambda: float("nan"),
        )
    )
    assert invalid_clock.code == "DEBUG_SAMPLE_CLOCK_INVALID"

    async def broken_sleep(delay: float) -> None:
        raise RuntimeError("secret")

    failed = asyncio.run(
        sample_variables(
            request(debug_env, count=2),
            TimedClient(debug_env, clock),
            _monotonic=clock.monotonic,
            _sleep=broken_sleep,
        )
    )
    assert failed.code == "DEBUG_SAMPLE_FAILED"
    assert "secret" not in str(failed.to_dict())

    single = asyncio.run(
        sample_variables(
            request(debug_env, count=1),
            TimedClient(debug_env, clock),
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert single.data.actual_rate_hz == 0.0

    starts = iter((10.0, 11.0))
    dropped = asyncio.run(
        sample_variables(
            request(debug_env, count=3),
            TimedClient(debug_env, clock),
            _monotonic=lambda: next(starts),
            _sleep=clock.sleep,
        )
    )
    assert dropped.data.samples == ()
    assert dropped.data.dropped_samples == 3


def test_sampling_request_is_frozen_and_has_no_raw_address(debug_env: DebugEnv) -> None:
    sample = request(debug_env)
    assert sample.expressions == ("signed32",)
    assert not hasattr(sample, "address")
    with pytest.raises(Exception):
        sample.interval_ms = 10


def test_sample_report_constructor_failures_are_stable(
    debug_env: DebugEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()

    def invalid_report(*args: object, **kwargs: object) -> object:
        raise ValueError("raw constructor detail")

    monkeypatch.setattr(sampling_mod, "SampleReport", invalid_report)
    result = asyncio.run(
        sample_variables(
            request(debug_env, count=1),
            TimedClient(debug_env, clock),
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )
    )
    assert result.code == "DEBUG_SAMPLE_FAILED"
    assert "raw constructor detail" not in str(result.to_dict())


def test_register_sampling_uses_exact_svd_and_sampling_risk_gate(
    debug_env: DebugEnv,
) -> None:
    client = debug_env.client()
    safe = asyncio.run(
        sample_registers(
            RegisterSampleRequest(
                debug_env.binding, debug_env.selection, ("GPIOA.IDR",)
            ),
            client,
        )
    )
    assert safe.ok is True
    assert safe.data.items[0].to_dict()["value"]["value"] == 0x12345678

    for path, code in (
        ("GPIOA.EVENT", "SVD_REGISTER_NOT_SAMPLEABLE"),
        ("GPIOA.COMMAND", "SVD_REGISTER_WRITE_ONLY"),
    ):
        rejected = asyncio.run(
            sample_registers(
                RegisterSampleRequest(debug_env.binding, debug_env.selection, (path,)),
                client,
            )
        )
        assert rejected.ok is False
        assert rejected.code == code


def test_register_sample_request_is_bounded_and_has_no_raw_override(
    debug_env: DebugEnv,
) -> None:
    request = RegisterSampleRequest(
        debug_env.binding, debug_env.selection, ("GPIOA.IDR",)
    )
    assert not hasattr(request, "address")
    assert not hasattr(request, "acknowledge_access_risk")
    client = debug_env.client()
    for invalid in (
        object(),
        RegisterSampleRequest(object(), debug_env.selection, ("GPIOA.IDR",)),
        RegisterSampleRequest(debug_env.binding, object(), ("GPIOA.IDR",)),
        RegisterSampleRequest(debug_env.binding, debug_env.selection, []),
        RegisterSampleRequest(debug_env.binding, debug_env.selection, ("GPIOA.IDR",) * 2),
        RegisterSampleRequest(
            debug_env.binding,
            debug_env.selection,
            tuple(f"GPIOA.R{i}" for i in range(257)),
        ),
    ):
        result = asyncio.run(sample_registers(invalid, client))
        assert result.code == "DEBUG_SAMPLE_REQUEST_INVALID"


def test_register_sampling_revalidates_svd_and_propagates_cancellation(
    debug_env: DebugEnv,
) -> None:
    svd_path = debug_env.root / debug_env.selection.path
    original = svd_path.read_bytes()
    svd_path.write_bytes(original + b"changed")
    changed = asyncio.run(
        sample_registers(
            RegisterSampleRequest(
                debug_env.binding, debug_env.selection, ("GPIOA.IDR",)
            ),
            debug_env.client(),
        )
    )
    assert changed.code == "SVD_PROVENANCE_MISMATCH"
    svd_path.write_bytes(original)

    class CancelClient(Client):
        async def attach(self, probe_id: str, target: str) -> object:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            sample_registers(
                RegisterSampleRequest(
                    debug_env.binding, debug_env.selection, ("GPIOA.IDR",)
                ),
                CancelClient(dict(debug_env.memory)),
            )
        )
