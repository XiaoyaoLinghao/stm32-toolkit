from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


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

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class FakeService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.endpoint = FakeEndpoint()
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
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )
        await replacement.start(
            MonitorConfig(project, (tmp_path / "data").resolve(), "session-a")
        )
        await replacement.stop()

    asyncio.run(scenario())

