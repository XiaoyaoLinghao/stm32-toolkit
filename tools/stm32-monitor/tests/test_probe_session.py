from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from stm32_monitor.models import WatchItem
from stm32_monitor.probe_session import ProbeReadOutcome, ProbeSession
from stm32_toolkit.debug import (
    DebugFirmwareBinding,
    DebugReadItem,
    DebugReadReport,
    MemoryRegionBinding,
    TypedValue,
)
from stm32_toolkit.result import OperationResult


def _binding(project: Path) -> DebugFirmwareBinding:
    return DebugFirmwareBinding(
        logical_project_id="11111111-1111-4111-8111-111111111111",
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
        memory_regions=(MemoryRegionBinding("FLASH", 0x08000000, 1024, "r-x"),),
        project_root=project.resolve(),
    )


def _report(binding: DebugFirmwareBinding, expressions: tuple[str, ...], *, errors: set[str] | None = None) -> DebugReadReport:
    failed = errors or set()
    items = []
    for index, expression in enumerate(expressions):
        if expression in failed:
            items.append(DebugReadItem(expression, "error", code="DEBUG_VALUE_UNAVAILABLE"))
        else:
            items.append(
                DebugReadItem(
                    expression,
                    "ok",
                    value=TypedValue(expression, "uint32_t", index + 1, f"0x{index + 1:08x}", 32),
                )
            )
    return DebugReadReport(binding, tuple(items), "2026-08-08T01:02:04.000000Z")


class FakeObservation:
    def __init__(self, binding: DebugFirmwareBinding) -> None:
        self.binding = binding
        self.catalog = SimpleNamespace(elf_sha256=binding.elf_sha256)
        self.svd = SimpleNamespace(sha256="d" * 64)
        self.variable_calls: list[tuple[str, ...]] = []
        self.register_calls: list[tuple[str, ...]] = []
        self.variable_errors: set[str] = set()
        self.register_errors: set[str] = set()
        self.read_failure: tuple[str, str] | None = None
        self.revalidate_result = OperationResult.success("revalidate", binding)

    async def read_variables(self, expressions: tuple[str, ...]):
        self.variable_calls.append(expressions)
        if self.read_failure is not None:
            return OperationResult.failure("read", self.read_failure[0], self.read_failure[1], {})
        return OperationResult.success("read", _report(self.binding, expressions, errors=self.variable_errors))

    async def sample_registers(self, paths: tuple[str, ...]):
        self.register_calls.append(paths)
        if self.read_failure is not None:
            return OperationResult.failure("registers", self.read_failure[0], self.read_failure[1], {})
        return OperationResult.success("registers", _report(self.binding, paths, errors=self.register_errors))

    async def revalidate(self):
        return self.revalidate_result


def test_probe_session_maps_exact_public_observation_evidence(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observation = FakeObservation(_binding(project))

    session = ProbeSession(observation)

    assert session.binding.to_dict() == {
        "workspaceId": "a" * 24,
        "logicalProjectId": "11111111-1111-4111-8111-111111111111",
        "sessionId": "monitor-1",
        "probeId": "probe-1",
        "targetDevice": "STM32F407VGTx",
        "physicalTarget": "stm32f407vg",
        "buildId": "b" * 64,
        "elfSha256": "e" * 64,
        "inputSnapshotSha256": "f" * 64,
        "gitHead": "c" * 40,
        "gitDirty": False,
        "flashSessionId": "flash-1",
        "leaseId": "lease-1",
        "dwarfSha256": "e" * 64,
        "svdSha256": "d" * 64,
    }


def test_grouped_reads_use_only_named_public_methods_and_preserve_item_order(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        observation.variable_errors.add("broken")
        items = (
            WatchItem.variable("counter"),
            WatchItem.register("GPIOA.IDR"),
            WatchItem.variable("broken"),
            WatchItem.register("USART1.SR"),
        )

        outcome = await ProbeSession(observation).read(items)

        assert isinstance(outcome, ProbeReadOutcome)
        assert outcome.blocked_code is None
        assert observation.variable_calls == [("counter", "broken")]
        assert observation.register_calls == [("GPIOA.IDR", "USART1.SR")]
        assert [value.watch for value in outcome.values] == list(items)
        assert [value.status for value in outcome.values] == ["OK", "OK", "ERROR", "OK"]
        assert outcome.values[2].code == "DEBUG_VALUE_UNAVAILABLE"
        assert outcome.values[0].typed_value["expression"] == "counter"

    asyncio.run(scenario())


def test_register_watches_never_fall_back_to_variable_or_address_reads(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))

        outcome = await ProbeSession(observation).read((WatchItem.register("RCC.CR"),))

        assert outcome.blocked_code is None
        assert observation.variable_calls == []
        assert observation.register_calls == [("RCC.CR",)]

    asyncio.run(scenario())


def test_item_failure_is_isolated_but_provenance_failure_blocks_whole_read(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        session = ProbeSession(observation)
        observation.variable_errors.add("bad")
        item = await session.read((WatchItem.variable("bad"), WatchItem.variable("good")))
        assert item.blocked_code is None
        assert [value.status for value in item.values] == ["ERROR", "OK"]

        observation.read_failure = ("MONITOR_PROVENANCE_CHANGED", "secret absolute path")
        blocked = await session.read((WatchItem.variable("good"),))
        assert blocked.values == ()
        assert blocked.blocked_code == "MONITOR_PROVENANCE_CHANGED"
        assert "secret" not in blocked.message

    asyncio.run(scenario())


def test_revalidation_rejects_firmware_and_dwarf_or_svd_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        session = ProbeSession(observation)
        assert (await session.revalidate()).ok

        observation.revalidate_result = OperationResult.failure(
            "revalidate", "MONITOR_FIRMWARE_CHANGED", "changed", {}
        )
        firmware = await session.revalidate()
        assert not firmware.ok and firmware.code == "MONITOR_FIRMWARE_CHANGED"

        observation.revalidate_result = OperationResult.success("revalidate", observation.binding)
        observation.catalog.elf_sha256 = "9" * 64
        provenance = await session.revalidate()
        assert not provenance.ok and provenance.code == "MONITOR_PROVENANCE_CHANGED"

    asyncio.run(scenario())


def test_malformed_reports_fail_closed_without_raw_exception_text(tmp_path: Path) -> None:
    class MalformedObservation(FakeObservation):
        async def read_variables(self, expressions):
            return OperationResult.success("read", {"unexpected": "C:\\secret"})

    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        outcome = await ProbeSession(MalformedObservation(_binding(project))).read((WatchItem.variable("x"),))
        assert outcome.blocked_code == "MONITOR_PROVENANCE_CHANGED"
        assert "secret" not in outcome.message

    asyncio.run(scenario())
