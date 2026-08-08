from __future__ import annotations

import asyncio
import hashlib
import json
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


class FakeObservation:
    def __init__(self, probe_id: str) -> None:
        self.binding = SimpleNamespace(to_dict=lambda: {"probeId": probe_id})
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


class FakeSampler:
    def __init__(self, observation, groups, history) -> None:
        self.inputs = (observation, groups, history)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.close_calls = 0

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

    async def subscribe(self):
        yield {"sequence": 1}
        yield SimpleNamespace(to_dict=lambda: {"sequence": 2})


def _protocol_runtime(tmp_path: Path, *, observation_factory=None):
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.protocol import success
    from stm32_monitor.runtime import MonitorRuntime

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
        return success("monitor.observe.open", observation)

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
        connect_payload = {
            "probeId": "probe-a",
            "expectedBuildId": "a" * 64,
            "expectedElfSha256": "b" * 64,
        }
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
                    "sessionId": "session-a",
                    "startNs": "1",
                    "endNs": "10",
                    "limit": "5",
                },
            )
            created = await runtime.dispatch(
                "monitor.exports.create",
                {
                    "sessionId": "session-a",
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
            assert history.ok and created.ok and fetched.ok
            assert histories[0].calls[-1][1][0].limit == 5
            assert exporters[0].calls[-1][1] == UUID(export_id)
            invalid = await runtime.dispatch(
                "monitor.history.query", {}, query={"startNs": "x"}
            )
            unsupported = await runtime.dispatch("monitor.unknown", {})
            assert not invalid.ok and not unsupported.ok
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_live_subscription_serializes_mapping_and_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(tmp_path)
        await runtime.start(config)
        try:
            await runtime.dispatch(
                "monitor.probe.connect",
                {
                    "probeId": "probe-a",
                    "expectedBuildId": "a" * 64,
                    "expectedElfSha256": "b" * 64,
                },
            )
            received = [item async for item in runtime.live_subscribe()]
            assert received == [{"sequence": 1}, {"sequence": 2}]
        finally:
            await runtime.stop()

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
        payload = {
            "probeId": "probe-a",
            "expectedBuildId": "a" * 64,
            "expectedElfSha256": "b" * 64,
        }
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
