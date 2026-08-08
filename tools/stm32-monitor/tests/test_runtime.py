from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest


MANIFEST = {
    "schemaVersion": 2,
    "logicalProjectId": "12345678-1234-5678-1234-567812345678",
    "generatedBy": {"tool": "stm32-toolkit", "version": "0.4.0"},
    "project": {"name": "monitor-fixture", "origin": "manual"},
    "target": {
        "device": "STM32F407VGTx",
        "core": "cortex-m4",
        "fpu": "fpv4-sp-d16",
        "floatAbi": "hard",
    },
    "framework": {"type": "spl", "version": None},
    "build": {
        "sources": ["Src/main.c"],
        "includePaths": [],
        "defines": [],
        "compileOptions": [],
        "assemblySources": [],
        "presets": ["arm-debug"],
        "elf": "build/arm-debug/firmware.elf",
    },
    "memory": {
        "source": "manual",
        "regions": [
            {
                "name": "FLASH",
                "origin": 134217728,
                "length": 1048576,
                "attributes": "r-x",
            },
            {
                "name": "RAM",
                "origin": 536870912,
                "length": 131072,
                "attributes": "rwx",
            },
        ],
    },
    "debug": {"backend": "pyocd", "target": "stm32f407vg", "svd": None},
    "generation": {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    },
}


def _project(tmp_path: Path, name: str = "project") -> Path:
    project = tmp_path / name
    (project / "Src").mkdir(parents=True)
    (project / "Src" / "main.c").write_bytes(b"int main(void){return 0;}\n")
    (project / ".stm32-project.json").write_bytes(
        json.dumps(MANIFEST, sort_keys=True).encode("utf-8")
    )
    return project.resolve()


@dataclass(frozen=True)
class FakeEndpoint:
    host: str = "127.0.0.1"
    port: int = 39123
    token: str = field(default="c" * 64, repr=False)
    workspace_id: str = ""
    session_id: str = ""
    monitor_version: str = "0.4.0"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class FakeService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.endpoint = FakeEndpoint(
            workspace_id=_kwargs.get("workspace_id", ""),
            session_id=_kwargs.get("session_id", ""),
        )
        self.stop_entered = asyncio.Event()
        self.allow_stop = asyncio.Event()
        self.stop_calls = 0

    async def start(self):
        return self.endpoint

    async def stop(self) -> None:
        self.stop_calls += 1
        self.stop_entered.set()
        await self.allow_stop.wait()


class FakeStore:
    def __init__(self, paths) -> None:
        self.paths = paths


class ProtocolStore(FakeStore):
    def __init__(self, paths) -> None:
        super().__init__(paths)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.closed = 0

    def _result(self, operation, *args, **kwargs):
        from stm32_monitor.protocol import success

        self.calls.append((operation, args, kwargs))
        return success(operation, {"operation": operation})

    def list_groups(self):
        return self._result("groups.list")

    def create_group(self, *args, **kwargs):
        return self._result("groups.create", *args, **kwargs)

    def update_group(self, *args, **kwargs):
        return self._result("groups.update", *args, **kwargs)

    def delete_group(self, *args, **kwargs):
        return self._result("groups.delete", *args, **kwargs)

    def import_groups(self, *args, **kwargs):
        return self._result("groups.import", *args, **kwargs)

    def close(self) -> None:
        self.closed += 1


class FakeHistory(ProtocolStore):
    def query_history(self, query):
        return self._result("history.query", query)


class FakeExporter:
    def __init__(self, paths, history) -> None:
        self.paths = paths
        self.history = history
        self.calls: list[tuple[str, object, object]] = []

    def create_export(self, request, *, authorized):
        from stm32_monitor.protocol import success

        self.calls.append(("create", request, authorized))
        return success("exports.create", {"created": True})

    def get_export(self, export_id):
        from stm32_monitor.protocol import success

        self.calls.append(("get", export_id, None))
        return success("exports.get", {"exportId": str(export_id)})

    def open_download(self, export_id):
        from stm32_monitor.protocol import success

        self.calls.append(("download", export_id, None))
        return success("exports.download", {"exportId": str(export_id)})


class FakeObservation:
    def __init__(self, probe_id: str) -> None:
        self.binding = SimpleNamespace(to_dict=lambda: {"probeId": probe_id})
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1

    async def list_variables(self, query, cursor, limit):
        from stm32_toolkit.debug.types import CatalogPage, VariableDescriptor
        from stm32_toolkit.result import OperationResult

        return OperationResult.success(
            "variables.list",
            CatalogPage(
                (VariableDescriptor("counter", "uint32_t", "integer", 4, signed=False),),
                None,
            ),
        )

    async def list_registers(self, query, cursor, limit):
        from stm32_toolkit.debug.types import CatalogPage, RegisterDescriptor
        from stm32_toolkit.result import OperationResult

        return OperationResult.success(
            "registers.list",
            CatalogPage(
                (
                    RegisterDescriptor(
                        "GPIOA.IDR", 32, "read-only", None, 0, None, (), True, False
                    ),
                ),
                None,
            ),
        )


class FakeSampler:
    def __init__(self, observation, groups, history) -> None:
        self.inputs = (observation, groups, history)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.close_calls = 0
        self.close_error: BaseException | None = None
        self.state = "IDLE"
        self.blocked_code = None
        self._group = None
        self._run_id = None
        self._sequence = 0
        self._subscribers = {}
        self._history_drops_pending = 0
        self._deadline_drops_pending = 0
        self.subscriber_drops_total = 0
        self.history_drops_total = 0
        self.deadline_drops_total = 0

    async def start(self, *args, **kwargs):
        from stm32_monitor.protocol import success

        self.calls.append(("start", args, kwargs))
        return success("sampling.start", {"started": True})

    def pause(self):
        return self._action("pause")

    async def resume(self):
        return self._action("resume")

    def stop(self):
        return self._action("stop")

    def _action(self, action):
        from stm32_monitor.protocol import success

        self.calls.append((action, (), {}))
        return success("sampling." + action, {action: True})

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error

    async def subscribe(self):
        yield {"sequence": 1}
        yield SimpleNamespace(
            subscriber_drops=3, to_dict=lambda: {"sequence": 2}
        )


def _protocol_runtime(
    tmp_path: Path,
    *,
    observation_factory=None,
    firmware_status_factory=None,
    probe_list_factory=None,
):
    from stm32_monitor.models import FirmwareStatus, MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime
    from stm32_toolkit.result import OperationResult

    project = _project(tmp_path)
    groups: list[ProtocolStore] = []
    histories: list[FakeHistory] = []
    exporters: list[FakeExporter] = []
    samplers: list[FakeSampler] = []
    observations: list[FakeObservation] = []
    requests: list[object] = []

    def group_factory(paths):
        store = ProtocolStore(paths)
        groups.append(store)
        return store

    def history_factory(paths):
        store = FakeHistory(paths)
        histories.append(store)
        return store

    def export_factory(paths, history):
        exporter = FakeExporter(paths, history)
        exporters.append(exporter)
        return exporter

    async def default_observation(request):
        requests.append(request)
        observation = FakeObservation(request.probe_id)
        observations.append(observation)
        return OperationResult.success("monitor.observe.open", observation)

    def default_firmware(_project):
        return FirmwareStatus("a" * 64, "b" * 64, "d" * 64, "c" * 40, False, "STM32F407VGTx")

    async def default_probe_list(_request):
        return OperationResult.success(
            "stm32_probe_list",
            {
                "workspaceId": "ignored",
                "sessionId": "ignored",
                "probes": [
                    {"probeId": "probe-a", "vendor": "ST", "product": "ST-LINK", "boardName": None}
                ],
            },
        )

    def sampler_factory(*args):
        sampler = FakeSampler(*args)
        samplers.append(sampler)
        return sampler

    runtime = MonitorRuntime(
        group_store_factory=group_factory,
        history_store_factory=history_factory,
        exporter_factory=export_factory,
        sampler_factory=sampler_factory,
        observation_factory=observation_factory or default_observation,
        firmware_status_factory=firmware_status_factory or default_firmware,
        probe_list_factory=probe_list_factory or default_probe_list,
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
    return runtime, config, groups, histories, exporters, samplers, observations, requests


def test_start_is_project_read_only_and_runtime_record_contains_digest_not_token(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime

    project = _project(tmp_path)
    before = {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    service_holder: list[FakeService] = []

    def service_factory(*args, **kwargs):
        service = FakeService(*args, **kwargs)
        service.allow_stop.set()
        service_holder.append(service)
        return service

    async def scenario() -> None:
        runtime = MonitorRuntime(
            group_store_factory=FakeStore,
            history_store_factory=FakeStore,
            exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=service_factory,
        )
        endpoint = await runtime.start(
            MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
        )
        record = json.loads(runtime.runtime_record.read_text(encoding="utf-8"))
        assert record["tokenSha256"] == hashlib.sha256(
            endpoint.token.encode("ascii")
        ).hexdigest()
        assert record["monitorVersion"] == "0.4.0"
        assert endpoint.token not in runtime.runtime_record.read_text(encoding="utf-8")
        assert endpoint.token not in repr(runtime)
        await runtime.stop()

    asyncio.run(scenario())
    after = {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert after == before
    assert service_holder[0].stop_calls == 1


def test_same_workspace_runtime_lock_is_busy_until_owner_stops(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError

    project = _project(tmp_path)
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")

    def make_runtime() -> MonitorRuntime:
        return MonitorRuntime(
                group_store_factory=FakeStore,
                history_store_factory=FakeStore,
                exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )

    async def scenario() -> None:
        first, second = make_runtime(), make_runtime()
        await first.start(config)
        try:
            try:
                await second.start(config)
            except MonitorRuntimeError as error:
                assert error.code == "MONITOR_RUNTIME_BUSY"
            else:
                raise AssertionError("second runtime acquired the same workspace")
        finally:
            await first.stop()
        await second.start(config)
        await second.stop()

    asyncio.run(scenario())


def _ready_service(*args, **kwargs) -> FakeService:
    service = FakeService(*args, **kwargs)
    service.allow_stop.set()
    return service


def test_repeated_cancellation_cannot_interrupt_owned_shutdown(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime

    project = _project(tmp_path)
    holder: list[FakeService] = []

    def service_factory(*args, **kwargs):
        service = FakeService(*args, **kwargs)
        holder.append(service)
        return service

    async def scenario() -> None:
        runtime = MonitorRuntime(
            group_store_factory=FakeStore,
            history_store_factory=FakeStore,
            exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=service_factory,
        )
        await runtime.start(
            MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
        )
        stopping = asyncio.create_task(runtime.stop())
        await holder[0].stop_entered.wait()
        stopping.cancel("first")
        await asyncio.sleep(0)
        stopping.cancel("second")
        holder[0].allow_stop.set()
        try:
            await stopping
        except asyncio.CancelledError:
            pass
        assert holder[0].stop_calls == 1
        assert not runtime.runtime_record.exists()
        replacement = MonitorRuntime(
                group_store_factory=FakeStore,
                history_store_factory=FakeStore,
                exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )
        await replacement.start(
            MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
        )
        await replacement.stop()

    asyncio.run(scenario())


def test_group_dispatch_is_exact_and_never_accepts_caller_workspace_fields(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, groups, *_ = _protocol_runtime(tmp_path)
        await runtime.start(config)
        group_id = "12345678-1234-5678-1234-567812345678"
        try:
            assert (await runtime.dispatch("monitor.groups.list", {})).ok
            created = await runtime.dispatch(
                "monitor.groups.create",
                {
                    "name": "Core",
                    "description": "core state",
                    "intervalMs": 250,
                    "items": [
                        {"kind": "variable", "expression": "counter"},
                        {"kind": "register", "registerPath": "SCB.CFSR"},
                    ],
                    "authorized": True,
                },
            )
            assert created.ok
            assert groups[0].calls[-1][2]["authorized"] is True
            assert [item.kind for item in groups[0].calls[-1][1][3]] == [
                "variable",
                "register",
            ]
            updated = await runtime.dispatch(
                "monitor.groups.update",
                {
                    "expectedRevision": 1,
                    "intervalMs": 500,
                    "authorized": True,
                },
                resource_id=group_id,
            )
            deleted = await runtime.dispatch(
                "monitor.groups.delete",
                {"expectedRevision": 2, "authorized": True},
                resource_id=group_id,
            )
            imported = await runtime.dispatch(
                "monitor.groups.import",
                {"authorized": True, "document": {"groups": []}},
            )
            assert updated.ok and deleted.ok and imported.ok
            assert groups[0].calls[-1][1][0] == b'{"groups":[]}'
            rejected = await runtime.dispatch(
                "monitor.groups.create",
                {
                    "name": "bad",
                    "description": "",
                    "intervalMs": 100,
                    "items": [],
                    "authorized": True,
                    "workspaceId": "attacker",
                },
            )
            assert not rejected.ok and rejected.code == "MONITOR_REQUEST_INVALID"
        finally:
            await runtime.stop()
        assert groups[0].closed == 1

    asyncio.run(scenario())


def test_probe_and_sampling_lifecycle_uses_only_typed_fixed_inputs(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, _groups, _history, _exports, samplers, observations, requests = (
            _protocol_runtime(tmp_path)
        )
        await runtime.start(config)
        connect_payload = {"probeId": "probe-a"}
        try:
            connected = await runtime.dispatch("monitor.probe.connect", connect_payload)
            assert connected.ok and connected.data == {"probeId": "probe-a"}
            request = requests[0]
            assert request.project_root == config.project_root
            assert request.data_root == config.data_root
            assert request.session_id == config.session_id
            assert request.probe_id == "probe-a"
            busy = await runtime.dispatch(
                "monitor.probe.connect", {**connect_payload, "probeId": "probe-b"}
            )
            assert not busy.ok and busy.code == "MONITOR_PROBE_BUSY"
            group_id = "12345678-1234-5678-1234-567812345678"
            started = await runtime.dispatch(
                "monitor.sampling.start",
                {"groupId": group_id, "expectedRevision": 3},
            )
            paused = await runtime.dispatch("monitor.sampling.pause", {})
            resumed = await runtime.dispatch("monitor.sampling.resume", {})
            stopped = await runtime.dispatch("monitor.sampling.stop", {})
            assert all(result.ok for result in (started, paused, resumed, stopped))
            assert samplers[0].calls[0] == (
                "start",
                (UUID(group_id),),
                {"expected_revision": 3},
            )
            reconnected = await runtime.dispatch("monitor.probe.reconnect", {})
            assert reconnected.ok
            assert reconnected.data == {"probeId": "probe-a"}
            assert observations[0].close_calls == 1
            assert samplers[0].close_calls == 1
            released = await runtime.dispatch("monitor.probe.release", {})
            assert released.ok and observations[1].close_calls == 1
            unavailable = await runtime.dispatch("monitor.sampling.pause", {})
            assert not unavailable.ok
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_probe_discovery_status_catalogs_and_connect_are_server_owned(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        runtime, config, _groups, _history, _exports, samplers, _observations, requests = (
            _protocol_runtime(tmp_path)
        )
        project_before = {
            path.relative_to(config.project_root).as_posix(): path.read_bytes()
            for path in config.project_root.rglob("*")
            if path.is_file()
        }
        await runtime.start(config)
        try:
            probes = await runtime.dispatch("monitor.probes.list", {})
            assert probes.ok and probes.to_dict()["data"] == {
                "probes": [
                    {"probeId": "probe-a", "vendor": "ST", "product": "ST-LINK", "boardName": None}
                ]
            }
            status = await runtime.dispatch("monitor.status", {})
            assert status.ok
            assert status.data["project"] == {
                "logicalProjectId": MANIFEST["logicalProjectId"],
                "name": "monitor-fixture",
                "targetDevice": "STM32F407VGTx",
            }
            assert status.data["firmware"]["buildId"] == "a" * 64
            assert status.data["probe"] == {"connected": False, "probeId": None}
            assert status.data["sampling"] == {
                "state": "IDLE",
                "active": False,
                "blockedCode": None,
                "groupId": None,
                "groupRevision": None,
                "runId": None,
                "lastSequence": None,
                "bindingEpoch": 0,
                "subscriberDrops": 0,
                "historyDrops": 0,
                "deadlineDrops": 0,
                "serviceDrops": 0,
            }
            assert project_before == {
                path.relative_to(config.project_root).as_posix(): path.read_bytes()
                for path in config.project_root.rglob("*")
                if path.is_file()
            }

            connected = await runtime.dispatch("monitor.probe.connect", {"probeId": "probe-a"})
            assert connected.ok
            request = requests[-1]
            assert request.expected_build_id == "a" * 64
            assert request.expected_elf_sha256 == "b" * 64
            assert not any(
                hasattr(request, name)
                for name in ("target", "elf", "svd", "address", "backend", "operation", "workspace")
            )
            variables = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={"query": "counter", "limit": "25"}
            )
            registers = await runtime.dispatch(
                "monitor.catalog.registers", {}, query={"cursor": "opaque"}
            )
            assert variables.ok and variables.data["items"][0]["selector"] == "counter"
            assert registers.ok and registers.data["items"][0]["selector"] == "GPIOA.IDR"
            assert (await runtime.dispatch("monitor.probe.connect", {
                "probeId": "probe-b", "target": "attacker", "expectedBuildId": "f" * 64
            })).code == "MONITOR_REQUEST_INVALID"
            assert samplers
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_connect_rederives_firmware_and_fails_closed_on_open_race(tmp_path: Path) -> None:
    from stm32_monitor.models import FirmwareStatus
    from stm32_monitor.protocol import failure

    statuses = [
        FirmwareStatus("a" * 64, "b" * 64, "d" * 64, "c" * 40, False, "STM32F407VGTx"),
        FirmwareStatus("e" * 64, "f" * 64, "1" * 64, "2" * 40, True, "STM32F407VGTx"),
    ]
    opened: list[object] = []

    def firmware(_project):
        return statuses.pop(0)

    async def changed_during_open(request):
        opened.append(request)
        return failure("observe", "MONITOR_FIRMWARE_CHANGED", "changed")

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(
            tmp_path,
            observation_factory=changed_during_open,
            firmware_status_factory=firmware,
        )
        await runtime.start(config)
        try:
            status = await runtime.dispatch("monitor.status", {})
            assert status.data["firmware"]["buildId"] == "a" * 64
            connected = await runtime.dispatch("monitor.probe.connect", {"probeId": "probe-a"})
            assert connected.code == "MONITOR_FIRMWARE_CHANGED"
            assert opened[0].expected_build_id == "e" * 64
            assert opened[0].expected_elf_sha256 == "f" * 64
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_probe_catalog_and_status_failure_boundaries_are_closed_and_bounded(
    tmp_path: Path,
) -> None:
    from stm32_monitor.models import FirmwareStatus
    from stm32_toolkit.debug.types import CatalogPage, VariableDescriptor
    from stm32_toolkit.result import OperationResult

    mode = {"probe": "raise", "firmware": False}

    async def probe_list(_request):
        current = mode["probe"]
        if current == "raise":
            raise RuntimeError("USB secret")
        if current == "failure":
            return OperationResult.failure(
                "stm32_probe_list", "PROBE_ENUMERATION_FAILED", "secret", {}
            )
        if current == "malformed":
            return OperationResult.success("stm32_probe_list", {"probes": [{}]})
        if current == "duplicate":
            item = {"probeId": "probe-a", "vendor": "ST", "product": "LINK", "boardName": None}
            return OperationResult.success("stm32_probe_list", {"probes": [item, item]})
        return OperationResult.success(
            "stm32_probe_list",
            {"probes": [{"probeId": "probe-a", "vendor": "ST", "product": "LINK", "boardName": None}]},
        )

    def firmware(_project):
        if not mode["firmware"]:
            raise RuntimeError("missing build")
        return FirmwareStatus("a" * 64, "b" * 64, "d" * 64, "c" * 40, False, "STM32F407VGTx")

    async def scenario() -> None:
        runtime, config, _groups, _history, _exports, samplers, observations, _requests = (
            _protocol_runtime(
                tmp_path,
                firmware_status_factory=firmware,
                probe_list_factory=probe_list,
            )
        )
        assert runtime._current_firmware() is None
        await runtime.start(config)
        try:
            disconnected = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={}
            )
            bad_query = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={"unknown": "x"}
            )
            assert disconnected.code == bad_query.code == "MONITOR_REQUEST_INVALID"
            for probe_mode in ("raise", "failure", "malformed", "duplicate"):
                mode["probe"] = probe_mode
                listed = await runtime.dispatch("monitor.probes.list", {})
                assert listed.code == "MONITOR_PROBE_ENUMERATION_FAILED"

            mode["probe"] = "good"
            unknown = await runtime.dispatch(
                "monitor.probe.connect", {"probeId": "probe-missing"}
            )
            assert unknown.code == "MONITOR_REQUEST_INVALID"
            unavailable = await runtime.dispatch(
                "monitor.probe.connect", {"probeId": "probe-a"}
            )
            assert unavailable.code == "MONITOR_FIRMWARE_CHANGED"

            mode["firmware"] = True
            connected = await runtime.dispatch(
                "monitor.probe.connect", {"probeId": "probe-a"}
            )
            assert connected.ok
            observation = observations[0]

            async def invalid_page(*_args):
                return OperationResult.failure(
                    "variables.list", "DWARF_LIMIT_INVALID", "invalid", {}
                )

            observation.list_variables = invalid_page
            invalid = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={"limit": "257"}
            )
            assert invalid.code == "MONITOR_REQUEST_INVALID"

            async def changed_page(*_args):
                return OperationResult.failure(
                    "registers.list", "SVD_INPUT_CHANGED", "changed", {}
                )

            observation.list_registers = changed_page
            changed = await runtime.dispatch(
                "monitor.catalog.registers", {}, query={}
            )
            assert changed.code == "MONITOR_PROVENANCE_CHANGED"

            async def typed_page(*_args):
                descriptor = VariableDescriptor(
                    "counter", "uint32_t", "integer", 4, signed=False
                )
                return OperationResult.success(
                    "variables.list", CatalogPage((descriptor,), None)
                )

            observation.list_variables = typed_page
            page = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={}
            )
            assert page.to_dict()["data"]["items"][0]["selector"] == "counter"

            sampler = samplers[0]
            sampler.state = "RUNNING"
            sampler._group = SimpleNamespace(
                group_id=UUID("12345678-1234-5678-9234-567812345678"), revision=4
            )
            sampler._run_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            sampler._sequence = 5
            sampler._subscribers = {object(): 2}
            sampler._history_drops_pending = 3
            sampler._deadline_drops_pending = 4
            sampler.subscriber_drops_total = 7
            sampler.history_drops_total = 8
            sampler.deadline_drops_total = 9
            runtime._service_drops_total = 10
            for state, active in (
                ("RUNNING", True),
                ("PAUSED", True),
                ("PAUSED_BLOCKED", False),
            ):
                sampler.state = state
                status = await runtime.dispatch("monitor.status", {})
                sampling = status.data["sampling"]
                assert sampling["active"] is active
                assert sampling["lastSequence"] == 4
                assert sampling["subscriberDrops"] == 7
                assert sampling["historyDrops"] == 8
                assert sampling["deadlineDrops"] == 9
                assert sampling["serviceDrops"] == 10
                assert status.data["probe"]["probeId"] == "probe-a"

            sampler._history_drops_pending = 0
            sampler._deadline_drops_pending = 0
            later = await runtime.dispatch("monitor.status", {})
            assert later.data["sampling"]["historyDrops"] == 8
            assert later.data["sampling"]["deadlineDrops"] == 9
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_probe_discovery_validates_exact_public_values_and_the_sixty_four_probe_cap(
    tmp_path: Path,
) -> None:
    from stm32_toolkit.result import OperationResult

    listed = {"probes": ()}

    async def probe_list(_request):
        return OperationResult.success("stm32_probe_list", listed)

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(
            tmp_path, probe_list_factory=probe_list
        )
        await runtime.start(config)
        try:
            valid = tuple(
                {
                    "probeId": f"probe-{index:02d}",
                    "vendor": "V" * 128,
                    "product": "ST-LINK/V3",
                    "boardName": None if index else "B" * 128,
                }
                for index in range(64)
            )
            listed["probes"] = valid
            accepted = await runtime.dispatch("monitor.probes.list", {})
            assert accepted.ok and len(accepted.data["probes"]) == 64

            listed["probes"] = valid + ({
                "probeId": "probe-64",
                "vendor": "ST",
                "product": "LINK",
                "boardName": None,
            },)
            assert (await runtime.dispatch("monitor.probes.list", {})).code == (
                "MONITOR_PROBE_ENUMERATION_FAILED"
            )

            malformed = (
                {"probeId": "../probe", "vendor": "ST", "product": "LINK", "boardName": None},
                {"probeId": "probe-a", "vendor": "", "product": "LINK", "boardName": None},
                {"probeId": "probe-a", "vendor": "ST\n", "product": "LINK", "boardName": None},
                {"probeId": "probe-a", "vendor": "C:\\secret", "product": "LINK", "boardName": None},
                {"probeId": "probe-a", "vendor": "ST", "product": "/secret", "boardName": None},
                {"probeId": "probe-a", "vendor": "ST", "product": "LINK", "boardName": "../secret"},
                {"probeId": "probe-a", "vendor": "V" * 129, "product": "LINK", "boardName": None},
                {"probeId": "probe-a", "vendor": "ST", "product": "P" * 129, "boardName": None},
                {"probeId": "probe-a", "vendor": "ST", "product": "LINK", "boardName": "B" * 129},
            )
            for item in malformed:
                listed["probes"] = (item,)
                result = await runtime.dispatch("monitor.probes.list", {})
                assert result.code == "MONITOR_PROBE_ENUMERATION_FAILED"
                assert result.message == "Debug probe enumeration failed"
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_runtime_catalog_accepts_only_exact_typed_pages_and_matching_descriptors(
    tmp_path: Path,
) -> None:
    from stm32_toolkit.debug.types import (
        CatalogPage,
        RegisterDescriptor,
    )
    from stm32_toolkit.result import OperationResult

    class ForgedPage:
        calls = 0

        def to_dict(self):
            self.calls += 1
            return {"items": [{"address": "C:\\private\\secret"}]}

    async def scenario() -> None:
        runtime, config, *_tail, observations, _requests = _protocol_runtime(tmp_path)
        await runtime.start(config)
        try:
            assert (await runtime.dispatch(
                "monitor.probe.connect", {"probeId": "probe-a"}
            )).ok
            observation = observations[0]
            forged = ForgedPage()
            forged_result = OperationResult.success("variables.list", forged)
            construction_calls = forged.calls

            async def custom_page(*_args):
                return forged_result

            observation.list_variables = custom_page
            rejected = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={}
            )
            assert rejected.code == "MONITOR_PROVENANCE_CHANGED"
            assert rejected.message == "Monitor catalog response is invalid"
            assert forged.calls == construction_calls

            async def mapping_page(*_args):
                return OperationResult.success(
                    "variables.list",
                    {"items": [{"address": 0x20000000}], "nextCursor": None},
                )

            observation.list_variables = mapping_page
            rejected = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={}
            )
            assert rejected.code == "MONITOR_PROVENANCE_CHANGED"

            wrong = RegisterDescriptor(
                "GPIOA.IDR", 32, "read-only", None, 0, None, (), True, False
            )

            async def wrong_descriptor(*_args):
                return OperationResult.success(
                    "variables.list", CatalogPage((wrong,), None)
                )

            observation.list_variables = wrong_descriptor
            rejected = await runtime.dispatch(
                "monitor.catalog.variables", {}, query={}
            )
            assert rejected.code == "MONITOR_PROVENANCE_CHANGED"
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_history_export_status_and_live_dispatch_are_protocol_bounded(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, _groups, histories, exporters, *_ = _protocol_runtime(tmp_path)
        before = await runtime.dispatch("monitor.status", {})
        assert not before.ok and before.code == "MONITOR_SERVICE_UNAVAILABLE"
        await runtime.start(config)
        try:
            status = await runtime.dispatch("monitor.status", {})
            assert status.ok and status.data["probeConnected"] is False
            history = await runtime.dispatch(
                "monitor.history.query",
                {},
                query={
                    "startNs": "1",
                    "endNs": "10",
                    "limit": "5",
                    "runId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "groupId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "selectorKind": "variable",
                    "selector": "counter",
                },
            )
            created = await runtime.dispatch(
                "monitor.exports.create",
                {
                    "startNs": 1,
                    "endNs": 10,
                    "format": "jsonl",
                    "authorized": True,
                },
            )
            export_id = "12345678-1234-5678-1234-567812345678"
            fetched = await runtime.dispatch(
                "monitor.exports.get", {}, resource_id=export_id
            )
            downloaded = await runtime.dispatch(
                "monitor.exports.download", {}, resource_id=export_id
            )
            assert history.ok and created.ok and fetched.ok and downloaded.ok
            query = histories[0].calls[-1][1][0]
            assert query.session_id == "session-a"
            assert query.limit == 5
            assert query.run_id == UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            assert query.group_id == UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
            assert (query.selector_kind, query.selector) == ("variable", "counter")
            assert exporters[0].calls[0][1].session_id == "session-a"
            assert exporters[0].calls[-2][1] == UUID(export_id)
            assert exporters[0].calls[-1] == ("download", UUID(export_id), None)
            invalid = await runtime.dispatch(
                "monitor.history.query", {}, query={"startNs": "x"}
            )
            incomplete_selector = await runtime.dispatch(
                "monitor.history.query",
                {},
                query={"startNs": "1", "endNs": "10", "selector": "counter"},
            )
            identity_override = await runtime.dispatch(
                "monitor.history.query",
                {},
                query={"sessionId": "other", "startNs": "1", "endNs": "10"},
            )
            unsupported = await runtime.dispatch("monitor.unknown", {})
            assert not invalid.ok and not incomplete_selector.ok
            assert not identity_override.ok and not unsupported.ok
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_live_subscription_serializes_mapping_and_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, *_tail, samplers, _observations, _requests = _protocol_runtime(tmp_path)
        await runtime.start(config)
        try:
            await runtime.dispatch(
                "monitor.probe.connect",
                {
                    "probeId": "probe-a",
                },
            )
            stream = runtime.live_subscribe()
            hello = await asyncio.wait_for(anext(stream), 1)
            connected = await asyncio.wait_for(anext(stream), 1)
            started = await runtime.dispatch(
                "monitor.sampling.start",
                {
                    "groupId": "12345678-1234-5678-9234-567812345678",
                    "expectedRevision": 1,
                },
            )
            assert started.ok
            state = await asyncio.wait_for(anext(stream), 1)
            samples = [
                await asyncio.wait_for(anext(stream), 1),
                await asyncio.wait_for(anext(stream), 1),
            ]
            assert [hello["type"], connected["type"], state["type"]] == [
                "hello",
                "state",
                "state",
            ]
            assert [item["data"]["batch"]["sequence"] for item in samples] == [1, 2]
            assert [item["data"]["serviceSubscriberDrops"] for item in samples] == [0, 3]
            status = await runtime.dispatch("monitor.status", {})
            assert status.data["sampling"]["serviceDrops"] == 3
            await stream.aclose()
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_live_broker_emits_initial_events_replays_and_reports_gap(tmp_path: Path) -> None:
    async def take(stream, count):
        return [await asyncio.wait_for(anext(stream), 1) for _ in range(count)]

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(tmp_path)
        await runtime.start(config)
        try:
            initial = runtime.live_subscribe()
            hello, state = await take(initial, 2)
            assert [hello["type"], state["type"]] == ["hello", "state"]
            assert hello["data"]["stateRevision"] == state["data"]["stateRevision"]
            assert state["data"]["status"]["sampling"]["state"] == "IDLE"
            assert hello["eventId"] < state["eventId"]
            await initial.aclose()

            replay = runtime.live_subscribe(after_event_id=hello["eventId"])
            assert await take(replay, 1) == [state]
            await replay.aclose()

            for _ in range(260):
                runtime._publish_heartbeat()
            gap_stream = runtime.live_subscribe(after_event_id=1)
            gap_hello, gap_state = await take(gap_stream, 2)
            assert gap_hello["type"] == "hello"
            assert gap_state["type"] == "state"
            assert gap_state["data"]["gap"] is True
            assert gap_state["eventId"] > gap_hello["eventId"]
            await gap_stream.aclose()
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_live_broker_publishes_state_after_dispatch_transitions_and_sample_events(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        runtime, config, *_tail, samplers, _observations, _requests = _protocol_runtime(tmp_path)
        await runtime.start(config)
        try:
            stream = runtime.live_subscribe()
            await asyncio.wait_for(anext(stream), 1)
            await asyncio.wait_for(anext(stream), 1)
            connected = await runtime.dispatch("monitor.probe.connect", {"probeId": "probe-a"})
            assert connected.ok
            event = await asyncio.wait_for(anext(stream), 1)
            assert event["type"] == "state"
            assert event["data"]["status"]["probe"]["connected"] is True

            sampler = samplers[0]
            sampler.state = "RUNNING"
            sampler._group = SimpleNamespace(
                group_id=UUID("12345678-1234-5678-9234-567812345678"), revision=4
            )
            sampler._run_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            sampler._sequence = 2
            started = await runtime.dispatch(
                "monitor.sampling.start",
                {"groupId": str(sampler._group.group_id), "expectedRevision": 4},
            )
            assert started.ok
            state = await asyncio.wait_for(anext(stream), 1)
            assert state["data"]["status"]["sampling"]["state"] == "RUNNING"

            runtime._publish_sample({"sequence": 2}, service_subscriber_drops=3)
            sample = await asyncio.wait_for(anext(stream), 1)
            while sample["data"].get("serviceSubscriberDrops") != 3:
                sample = await asyncio.wait_for(anext(stream), 1)
            assert sample["type"] == "sample"
            assert sample["data"] == {
                "batch": {"sequence": 2},
                "serviceSubscriberDrops": 3,
            }
            assert [state["eventId"], sample["eventId"]] == sorted(
                [state["eventId"], sample["eventId"]]
            )
            await stream.aclose()
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_heartbeat_uses_runtime_clock_and_live_queue_eviction_is_accounted(
    tmp_path: Path,
) -> None:
    from stm32_monitor.runtime import MonitorRuntime

    for interval in (True, 0, 301):
        with pytest.raises(ValueError, match="heartbeat"):
            MonitorRuntime(heartbeat_interval_seconds=interval)

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(tmp_path)
        runtime._heartbeat_interval_seconds = 0.01
        assert [item async for item in runtime.live_subscribe()] == []
        assert runtime._publish_state() == {}
        for invalid in (0, -1, True):
            with pytest.raises(ValueError):
                await anext(runtime.live_subscribe(after_event_id=invalid))

        await runtime.start(config)
        stream = runtime.live_subscribe()
        hello = await asyncio.wait_for(anext(stream), 1)
        state = await asyncio.wait_for(anext(stream), 1)
        heartbeat = await asyncio.wait_for(anext(stream), 1)
        try:
            assert heartbeat["type"] == "heartbeat"
            assert heartbeat["data"]["stateRevision"] == state["data"]["stateRevision"]
            assert heartbeat["data"]["capturedAtUtc"].endswith("Z")
            assert hello["eventId"] < state["eventId"] < heartbeat["eventId"]

            assert runtime._heartbeat_task is not None
            runtime._heartbeat_task.cancel()
            await asyncio.gather(runtime._heartbeat_task, return_exceptions=True)
            runtime._heartbeat_task = None
            queue = next(iter(runtime._live_subscribers))
            while not queue.empty():
                queue.get_nowait()
            drops_before = runtime._service_drops_total
            for _ in range(257):
                runtime._publish_heartbeat()
            assert runtime._service_drops_total == drops_before + 1
            runtime.record_service_drops(2)
            runtime.record_service_drops(0)
            runtime.record_service_drops(True)
            assert runtime._service_drops_total == drops_before + 3
        finally:
            await runtime.stop()
            await stream.aclose()

    asyncio.run(scenario())


def test_path_guards_reject_missing_redirected_nested_and_non_directory_paths(
    tmp_path: Path,
) -> None:
    from stm32_monitor.runtime import (
        MonitorRuntimeError,
        _ensure_owned_directory,
        _existing_prefixes,
        _safe_data,
        _safe_project,
    )

    project = _project(tmp_path)
    assert _safe_project(project) == project
    assert _existing_prefixes(Path()) == ()
    for value in ("not-a-path", Path("relative"), tmp_path / "missing"):
        with pytest.raises(MonitorRuntimeError) as caught:
            _safe_project(value)
        assert caught.value.code == "MONITOR_INPUT_INVALID"
    with pytest.raises(MonitorRuntimeError):
        _safe_data("not-a-path", project)
    with pytest.raises(MonitorRuntimeError):
        _safe_data(project / "data", project)
    unsafe_data = tmp_path / "unsafe-data"
    unsafe_data.write_bytes(b"not a directory")
    with pytest.raises(MonitorRuntimeError):
        _safe_data(unsafe_data / "child", project)
    data = (tmp_path / "owned-data").resolve()
    with pytest.raises(MonitorRuntimeError):
        _ensure_owned_directory(data, project)
    bad_component = data / "projects"
    bad_component.parent.mkdir(parents=True)
    bad_component.write_bytes(b"not a directory")
    with pytest.raises(MonitorRuntimeError):
        _ensure_owned_directory(data, bad_component / "workspace")


def test_start_rejects_invalid_config_and_cleans_partial_dependencies(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError

    project = _project(tmp_path)
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
    closed: list[str] = []

    class ClosingStore(FakeStore):
        def close(self):
            closed.append(type(self).__name__)

    class InvalidEndpointService:
        async def start(self):
            return SimpleNamespace(token="short", port=1)

        async def stop(self):
            closed.append("service")

    runtime = MonitorRuntime(
        group_store_factory=ClosingStore,
        history_store_factory=ClosingStore,
        exporter_factory=lambda *_args: object(),
        sampler_factory=lambda *_args: object(),
        observation_factory=lambda *_args: object(),
        service_factory=lambda *_args, **_kwargs: InvalidEndpointService(),
    )

    async def scenario() -> None:
        with pytest.raises(MonitorRuntimeError):
            _ = runtime.runtime_record
        with pytest.raises(MonitorRuntimeError) as invalid:
            await runtime.start(object())
        assert invalid.value.code == "MONITOR_INPUT_INVALID"
        with pytest.raises(ValueError):
            await runtime.start(config)
        assert sorted(closed) == ["ClosingStore", "ClosingStore", "service"]

    asyncio.run(scenario())


def test_atomic_runtime_record_failure_is_sanitized_and_removes_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_monitor.runtime as runtime_module

    target = tmp_path / "runtime.json"

    def fail_replace(_source, _target):
        raise OSError("SECRET C:\\private\\runtime.json")

    monkeypatch.setattr(runtime_module.os, "replace", fail_replace)
    with pytest.raises(runtime_module.MonitorRuntimeError) as caught:
        runtime_module._atomic_json(target, {"tokenSha256": "a" * 64})
    assert caught.value.code == "MONITOR_RUNTIME_PATH_UNSAFE"
    assert "SECRET" not in caught.value.message
    assert list(tmp_path.iterdir()) == []


def test_probe_failures_are_stable_and_do_not_leave_partial_sessions(tmp_path: Path) -> None:
    from stm32_monitor.protocol import failure, success

    outcomes: list[object] = [
        object(),
        failure("observe", "MONITOR_PROBE_BUSY", "Probe busy"),
        success("observe", None),
    ]

    async def observation_factory(_request):
        return outcomes.pop(0)

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(
            tmp_path, observation_factory=observation_factory
        )
        await runtime.start(config)
        payload = {"probeId": "probe-a"}
        try:
            no_prior = await runtime.dispatch("monitor.probe.reconnect", {})
            malformed = await runtime.dispatch("monitor.probe.connect", payload)
            busy = await runtime.dispatch("monitor.probe.connect", payload)
            empty = await runtime.dispatch("monitor.probe.connect", payload)
            assert [malformed.code, busy.code, empty.code, no_prior.code] == [
                "MONITOR_INTERNAL_ERROR",
                "MONITOR_PROBE_BUSY",
                "MONITOR_INTERNAL_ERROR",
                "MONITOR_REQUEST_INVALID",
            ]
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_invalid_dispatch_shapes_and_optional_update_fields_fail_closed(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, groups, *_ = _protocol_runtime(tmp_path)
        await runtime.start(config)
        group_id = "12345678-1234-5678-1234-567812345678"
        try:
            updated = await runtime.dispatch(
                "monitor.groups.update",
                {
                    "expectedRevision": 1,
                    "authorized": True,
                    "name": "Updated",
                    "description": "new",
                    "items": [{"kind": "variable", "expression": "counter"}],
                },
                resource_id=group_id,
            )
            assert updated.ok
            assert groups[0].calls[-1][2]["name"] == "Updated"
            invalid_requests = (
                ("monitor.groups.create", {"name": "missing fields"}, None),
                (
                    "monitor.groups.create",
                    {"name": "x", "description": "", "intervalMs": True, "items": {}, "authorized": True},
                    None,
                ),
                ("monitor.groups.delete", {"expectedRevision": True, "authorized": True}, group_id),
                ("monitor.groups.delete", {"expectedRevision": 1, "authorized": True}, None),
                ("monitor.exports.get", {}, "not-a-uuid"),
            )
            for operation, body, resource in invalid_requests:
                result = await runtime.dispatch(operation, body, resource_id=resource)
                assert not result.ok and result.code == "MONITOR_REQUEST_INVALID"
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_wait_closed_and_cleanup_failure_are_owned_and_stable(tmp_path: Path) -> None:
    class BrokenStore(FakeStore):
        def close(self):
            raise RuntimeError("SECRET cleanup")

    async def scenario() -> None:
        from stm32_monitor.models import MonitorConfig
        from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError

        project = _project(tmp_path)
        runtime = MonitorRuntime(
            group_store_factory=BrokenStore,
            history_store_factory=FakeStore,
            exporter_factory=FakeExporter,
            sampler_factory=lambda *_args: object(),
            observation_factory=lambda *_args: object(),
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )
        await runtime.start(
            MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
        )
        waiter = asyncio.create_task(runtime.wait_closed())
        with pytest.raises(MonitorRuntimeError) as caught:
            await runtime.stop()
        await waiter
        assert caught.value.code == "MONITOR_CLEANUP_FAILED"
        assert "SECRET" not in caught.value.message
        assert [item async for item in runtime.live_subscribe()] == []

    asyncio.run(scenario())


def test_double_cancel_during_partial_start_finishes_all_owned_cleanup_and_unlocks(
    tmp_path: Path,
) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime

    project = _project(tmp_path)
    config = MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
    start_entered = asyncio.Event()
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    closed: list[str] = []

    class ClosingStore(FakeStore):
        def __init__(self, paths, name):
            super().__init__(paths)
            self.name = name

        async def close(self):
            closed.append(self.name)

    class ClosingExporter:
        def __init__(self, _paths, _history):
            pass

        async def close(self):
            closed.append("exporter")

    class PartialService:
        async def start(self):
            start_entered.set()
            await asyncio.Future()

        async def close(self):
            cleanup_entered.set()
            await allow_cleanup.wait()
            closed.append("service")

    runtime = MonitorRuntime(
        group_store_factory=lambda paths: ClosingStore(paths, "groups"),
        history_store_factory=lambda paths: ClosingStore(paths, "history"),
        exporter_factory=ClosingExporter,
        sampler_factory=lambda *_args: object(),
        observation_factory=lambda *_args: object(),
        service_factory=lambda *_args, **_kwargs: PartialService(),
    )

    async def scenario() -> None:
        starting = asyncio.create_task(runtime.start(config))
        await start_entered.wait()
        starting.cancel("first")
        await cleanup_entered.wait()
        starting.cancel("second")
        await asyncio.sleep(0)
        allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await starting
        assert sorted(closed) == ["exporter", "groups", "history", "service"]

        replacement, replacement_config, *_ = _protocol_runtime(tmp_path / "replacement")
        # Use the exact same workspace to prove the partial-start lock was released.
        replacement_config = MonitorConfig(
            project, config.data_root, config.session_id
        )
        await replacement.start(replacement_config)
        await replacement.stop()

    asyncio.run(scenario())


def test_sampler_close_failure_still_closes_observation_once_and_allows_reconnect(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        runtime, config, _groups, _history, _exports, samplers, observations, _requests = (
            _protocol_runtime(tmp_path)
        )
        await runtime.start(config)
        payload = {"probeId": "probe-a"}
        try:
            assert (await runtime.dispatch("monitor.probe.connect", payload)).ok
            samplers[0].close_error = RuntimeError("SECRET sampler cleanup")
            released = await runtime.dispatch("monitor.probe.release", {})
            assert released.ok is False
            assert released.code == "MONITOR_CLEANUP_FAILED"
            assert observations[0].close_calls == 1
            assert samplers[0].close_calls == 1
            reconnected = await runtime.dispatch("monitor.probe.reconnect", {})
            assert reconnected.ok is True
            assert len(observations) == 2
            assert (await runtime.dispatch("monitor.probe.release", {})).ok
            assert observations[1].close_calls == 1
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_runtime_lock_rejects_hardlink_redirect_and_descriptor_replacement_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_monitor.runtime as runtime_module
    from stm32_monitor.models import MonitorConfig
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    project = _project(tmp_path)
    data = (tmp_path / "data").resolve()
    config = MonitorConfig(project, data, "session-a")
    model = load_project_model(project)
    paths = WorkspacePaths.from_roots(
        data, project, model.logical_project_id, config.session_id
    )
    paths.workspace_root.mkdir(parents=True)
    lock_path = paths.workspace_root / ".monitor-runtime.lock"
    sentinel = tmp_path / "outside-sentinel.bin"
    sentinel.write_bytes(b"")
    os.link(sentinel, lock_path)
    runtime = runtime_module.MonitorRuntime(
        group_store_factory=FakeStore,
        history_store_factory=FakeStore,
        exporter_factory=FakeExporter,
        sampler_factory=lambda *_args: object(),
        observation_factory=lambda *_args: object(),
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    with pytest.raises(runtime_module.MonitorRuntimeError) as hardlink:
        asyncio.run(runtime.start(config))
    assert hardlink.value.code == "MONITOR_RUNTIME_PATH_UNSAFE"
    assert sentinel.read_bytes() == b""
    lock_path.unlink()

    lock_path.write_bytes(b"x")
    original_lstat = runtime_module.os.lstat

    def redirected(path):
        metadata = original_lstat(path)
        if Path(path) == lock_path:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino,
                st_nlink=1,
                st_file_attributes=0x400,
            )
        return metadata

    monkeypatch.setattr(runtime_module.os, "lstat", redirected)
    redirect_lock = runtime_module._WorkspaceLock(lock_path)
    with pytest.raises(runtime_module.MonitorRuntimeError):
        redirect_lock.acquire()
    monkeypatch.setattr(runtime_module.os, "lstat", original_lstat)

    calls = 0

    def replaced(path):
        nonlocal calls
        metadata = original_lstat(path)
        if Path(path) == lock_path:
            calls += 1
            if calls >= 2:
                return SimpleNamespace(
                    st_mode=metadata.st_mode,
                    st_dev=metadata.st_dev,
                    st_ino=metadata.st_ino + 1,
                    st_nlink=1,
                    st_file_attributes=0,
                )
        return metadata

    monkeypatch.setattr(runtime_module.os, "lstat", replaced)
    replaced_lock = runtime_module._WorkspaceLock(lock_path)
    with pytest.raises(runtime_module.MonitorRuntimeError):
        replaced_lock.acquire()


def test_default_runtime_factories_load_and_existing_lock_content_is_exact(
    tmp_path: Path,
) -> None:
    import stm32_monitor.runtime as runtime_module

    # The production dependency graph must remain importable without test doubles.
    runtime = runtime_module.MonitorRuntime()
    assert type(runtime).__name__ == "MonitorRuntime"

    lock_path = tmp_path / "runtime.lock"
    lock_path.write_bytes(b"\0")
    lock = runtime_module._WorkspaceLock(lock_path)
    lock.acquire()
    lock.release()
    lock.release()

    for invalid in (b"x", b"\0\0"):
        lock_path.write_bytes(invalid)
        with pytest.raises(runtime_module.MonitorRuntimeError) as caught:
            runtime_module._WorkspaceLock(lock_path).acquire()
        assert caught.value.code == "MONITOR_RUNTIME_PATH_UNSAFE"
