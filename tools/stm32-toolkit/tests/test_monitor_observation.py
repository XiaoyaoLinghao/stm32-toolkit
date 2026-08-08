from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import atomic_write_json
from stm32_toolkit.debug import read_variables, sample_registers
from stm32_toolkit.monitor_observation import (
    MonitorObservationError,
    MonitorObservationRequest,
    MonitorObservationSeams,
    open_monitor_observation,
)
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.protocol import PROBE_PROTOCOL_VERSION
from stm32_toolkit.probe.service import ProbeEndpoint
from stm32_toolkit.result import OperationResult
from test_debug_read import Client, DebugEnv, debug_env


def _directory_redirect(link: Path, target: Path) -> None:
    if os.name != "nt":
        os.symlink(target, link, target_is_directory=True)
        return
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip("directory redirection is unavailable on this host")


def _project_snapshot(root: Path) -> dict[str, tuple[str, bytes | None, int]]:
    return {
        path.relative_to(root).as_posix(): (
            "file" if path.is_file() else "directory",
            path.read_bytes() if path.is_file() else None,
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
    }


class StableError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ObservationClient(Client):
    def __init__(self, env: DebugEnv, endpoint: ProbeEndpoint) -> None:
        super().__init__(dict(env.memory))
        self.endpoint = endpoint
        self.closed = False
        self.close_error: BaseException | None = None
        self.close_started: asyncio.Event | None = None
        self.close_release: asyncio.Event | None = None

    async def close(self) -> None:
        if self.close_started is not None:
            self.close_started.set()
        if self.close_release is not None:
            await self.close_release.wait()
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class Supervisor:
    def __init__(self, config: object, registry: dict[str, "Supervisor"]) -> None:
        self.config = config
        self.registry = registry
        self.endpoint: ProbeEndpoint | None = None
        self.stopped = False
        self.stop_error: BaseException | None = None

    async def start(self) -> ProbeEndpoint:
        probe = self.config.probe_id
        if probe in self.registry:
            raise StableError("PROBE_BUSY", "busy raw detail")
        self.registry[probe] = self
        self.endpoint = ProbeEndpoint(
            protocol=PROBE_PROTOCOL_VERSION,
            toolkit_version=__version__,
            host="127.0.0.1",
            port=43123,
            token="11" * 32,
            workspace_id=self.config.workspace_id,
            session_id=self.config.session_id,
            lease_id=f"lease-{probe}",
            probe_id=probe,
            operation_level=OperationLevel.OBSERVE,
        )
        return self.endpoint

    async def stop(self) -> None:
        self.stopped = True
        self.registry.pop(self.config.probe_id, None)
        self.endpoint = None
        if self.stop_error is not None:
            raise self.stop_error


class Harness:
    def __init__(self, env: DebugEnv) -> None:
        self.env = env
        self.registry: dict[str, Supervisor] = {}
        self.supervisors: list[Supervisor] = []
        self.clients: list[ObservationClient] = []
        self.bind_calls: list[object] = []
        self.binding_override = None
        self.bind_result: OperationResult | None = None

    def supervisor(self, config: object, lease: object, backend: object) -> Supervisor:
        assert config.operation_level is OperationLevel.OBSERVE
        instance = Supervisor(config, self.registry)
        self.supervisors.append(instance)
        return instance

    def client(self, endpoint: ProbeEndpoint) -> ObservationClient:
        instance = ObservationClient(self.env, endpoint)
        self.clients.append(instance)
        return instance

    async def bind(self, request: object, client: object) -> OperationResult:
        self.bind_calls.append(request)
        if self.bind_result is not None:
            return self.bind_result
        binding = replace(
            self.env.binding,
            project_root=request.project_root,
            workspace_id=request.workspace_id,
            observation_session_id=request.observation_session_id,
            lease_id=request.lease_id,
            probe_id=request.probe_id,
        )
        flash_path = self.env.root / "artifacts" / "migration" / "flash-result.json"
        flash = json.loads(flash_path.read_text(encoding="utf-8"))
        flash["workspaceId"] = request.workspace_id
        flash["probeId"] = request.probe_id
        atomic_write_json(flash_path, flash)
        if self.binding_override is not None:
            binding = self.binding_override(binding)
        return OperationResult.success("stm32_debug_bind", binding)

    def seams(self) -> MonitorObservationSeams:
        return MonitorObservationSeams(
            backend_factory=lambda: object(),
            lease_manager_factory=lambda root: object(),
            supervisor_factory=self.supervisor,
            client_factory=self.client,
            bind=self.bind,
            catalog_from_binding=lambda binding: self.env.catalog,
            svd_select=lambda *args, **kwargs: self.env.selection,
            read_variables=read_variables,
            sample_registers=sample_registers,
        )


def request(env: DebugEnv, data_root: Path, *, probe: str = "probe-123") -> MonitorObservationRequest:
    return MonitorObservationRequest(
        project_root=env.root,
        data_root=data_root,
        session_id="monitor-session",
        probe_id=probe,
        expected_build_id=env.binding.build_id,
        expected_elf_sha256=env.binding.elf_sha256,
    )


def test_request_has_no_raw_hardware_or_provenance_overrides(debug_env: DebugEnv, tmp_path: Path) -> None:
    names = {item.name for item in fields(MonitorObservationRequest)}
    assert names == {
        "project_root",
        "data_root",
        "session_id",
        "probe_id",
        "expected_build_id",
        "expected_elf_sha256",
    }
    value = request(debug_env, tmp_path / "data")
    for forbidden in ("target", "svd", "elf", "address", "operation_level", "backend", "command"):
        assert not hasattr(value, forbidden)


def test_open_keeps_exact_observe_lease_and_uses_real_typed_provenance(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)
    opened = asyncio.run(
        open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=harness.seams())
    )
    assert opened.ok is True
    session = opened.data
    assert session.binding.project_root == debug_env.root
    assert session.catalog is debug_env.catalog
    assert session.svd is debug_env.selection
    assert session.endpoint.operation_level is OperationLevel.OBSERVE
    config = harness.supervisors[0].config
    assert config.operation_level is OperationLevel.OBSERVE
    assert "probe-123" not in config.session_root.as_posix()
    assert config.project_root == debug_env.root

    variables = asyncio.run(session.read_variables(("signed32",)))
    registers = asyncio.run(session.sample_registers(("GPIOA.IDR",)))
    assert variables.ok is True
    assert registers.ok is True
    assert asyncio.run(session.revalidate()).ok is True
    asyncio.run(session.close())
    assert harness.clients[0].closed is True
    assert harness.supervisors[0].stopped is True


def test_same_probe_is_busy_while_different_probe_is_isolated(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)

    async def exercise() -> None:
        first = await open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=harness.seams())
        same = await open_monitor_observation(request(debug_env, tmp_path / "data", probe="probe-123"), _seams=harness.seams())
        other = await open_monitor_observation(request(debug_env, tmp_path / "data", probe="probe-456"), _seams=harness.seams())
        assert first.ok is True
        assert same.code == "MONITOR_PROBE_BUSY"
        assert other.ok is True
        await first.data.close()
        await other.data.close()

    asyncio.run(exercise())


def test_invalid_roots_and_identity_fail_before_runtime_creation(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)
    cases = (
        object(),
        replace(request(debug_env, tmp_path / "data"), project_root="bad"),
        replace(request(debug_env, tmp_path / "data"), project_root=tmp_path / "missing"),
        replace(request(debug_env, debug_env.root / "inside")),
        replace(request(debug_env, debug_env.root.parent)),
        replace(request(debug_env, tmp_path / "data"), expected_build_id="bad"),
        replace(request(debug_env, tmp_path / "data"), session_id="../bad"),
    )
    for invalid in cases:
        result = asyncio.run(open_monitor_observation(invalid, _seams=harness.seams()))
        assert result.code == "MONITOR_REQUEST_INVALID"
    assert harness.supervisors == []


def test_external_root_parent_change_never_writes_into_project(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    external_parent = tmp_path / "external-parent"
    external_parent.mkdir()
    data_root = external_parent / "data"
    before = _project_snapshot(debug_env.root)
    original = observation._safe_mkdir_chain

    def changed_parent(root: Path, destination: Path) -> None:
        external_parent.rmdir()
        _directory_redirect(external_parent, debug_env.root)
        original(root, destination)

    monkeypatch.setattr(observation, "_safe_mkdir_chain", changed_parent)
    result = asyncio.run(
        open_monitor_observation(
            request(debug_env, data_root),
            _seams=harness.seams(),
        )
    )

    assert result.ok is False
    assert result.code == "MONITOR_REQUEST_INVALID"
    assert harness.supervisors == []
    assert _project_snapshot(debug_env.root) == before


def test_external_root_identity_change_fails_before_backend_start(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    external_parent = tmp_path / "external-parent-identity"
    external_parent.mkdir()
    data_root = external_parent / "data"
    original = observation._safe_mkdir_chain

    def changed_parent(root: Path, destination: Path) -> None:
        external_parent.rmdir()
        external_parent.mkdir()
        original(root, destination)

    monkeypatch.setattr(observation, "_safe_mkdir_chain", changed_parent)
    result = asyncio.run(
        open_monitor_observation(
            request(debug_env, data_root),
            _seams=harness.seams(),
        )
    )

    assert result.ok is False
    assert result.code == "MONITOR_REQUEST_INVALID"
    assert harness.supervisors == []


def test_posix_directory_creation_uses_directory_descriptors(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    opened: list[tuple[object, tuple[object, ...], dict[str, object]]] = []
    created: list[tuple[object, int]] = []
    closed: list[int] = []
    next_descriptor = iter(range(10, 20))

    def fake_open(path: object, *args: object, **kwargs: object) -> int:
        descriptor = next(next_descriptor)
        opened.append((path, args, kwargs))
        return descriptor

    def fake_mkdir(path: object, *, dir_fd: int) -> None:
        created.append((path, dir_fd))
        if len(created) == 1:
            raise FileExistsError

    monkeypatch.setattr(observation.os, "open", fake_open)
    monkeypatch.setattr(observation.os, "mkdir", fake_mkdir)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(st_mode=stat.S_IFDIR | 0o700),
    )
    monkeypatch.setattr(observation.os, "close", closed.append)

    root = Path("/external/data")
    observation._safe_mkdir_posix(root, root / "sessions" / "monitor")

    assert created
    assert all("dir_fd" in kwargs for _, _, kwargs in opened[1:])
    assert len(closed) == len(opened)


def test_posix_directory_creation_rejects_non_directory_component(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    descriptors = iter((20, 21))
    closed: list[int] = []
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(observation.os, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(st_mode=stat.S_IFREG | 0o600),
    )
    monkeypatch.setattr(observation.os, "close", closed.append)

    with pytest.raises(ValueError):
        observation._safe_mkdir_posix(Path("/external"), Path("/external/data"))
    assert closed == [21, 20]


def test_posix_directory_identity_failure_closes_new_descriptor(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    descriptors = iter((30, 31))
    closed: list[int] = []
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(observation.os, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: (_ for _ in ()).throw(OSError("identity unavailable")),
    )
    monkeypatch.setattr(observation.os, "close", closed.append)

    with pytest.raises(OSError, match="identity"):
        observation._safe_mkdir_posix(Path("/external"), Path("/external/data"))
    assert sorted(closed) == [30, 31]


def test_revalidate_rejects_firmware_epoch_change(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)

    async def exercise() -> None:
        opened = await open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=harness.seams())
        assert opened.ok
        harness.binding_override = lambda binding: replace(binding, build_id="0" * 64)
        changed = await opened.data.revalidate()
        assert changed.code == "MONITOR_FIRMWARE_CHANGED"
        await opened.data.close()

    asyncio.run(exercise())


def test_open_rejects_forged_binding_identity_before_exposing_session(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)
    harness.binding_override = lambda binding: replace(
        binding, workspace_id="forged-workspace"
    )
    result = asyncio.run(
        open_monitor_observation(
            request(debug_env, tmp_path / "data"), _seams=harness.seams()
        )
    )
    assert result.code == "MONITOR_FIRMWARE_CHANGED"
    assert harness.clients[0].closed is True
    assert harness.supervisors[0].stopped is True


def test_optional_svd_and_invalid_provenance_factories(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    manifest_path = debug_env.root / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["debug"].pop("svd", None)
    manifest_path.write_bytes(
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    )
    harness = Harness(debug_env)
    opened = asyncio.run(
        open_monitor_observation(
            request(debug_env, tmp_path / "data"), _seams=harness.seams()
        )
    )
    assert opened.ok is True
    assert opened.data.svd is None
    assert asyncio.run(opened.data.sample_registers(("GPIOA.IDR",))).code == "SVD_SELECTION_REQUIRED"
    asyncio.run(opened.data.close())

    for field in ("catalog_from_binding", "svd_select"):
        # Restore exact SVD only for the SVD-factory branch.
        if field == "svd_select":
            manifest["debug"]["svd"] = "svd/device.svd"
            manifest_path.write_bytes(
                (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            )
        other = Harness(debug_env)
        seams = replace(other.seams(), **{field: lambda *args, **kwargs: object()})
        rejected = asyncio.run(
            open_monitor_observation(
                request(debug_env, tmp_path / f"data-{field}"), _seams=seams
            )
        )
        assert rejected.code == "MONITOR_PROVENANCE_CHANGED"
        assert other.supervisors[0].stopped is True


def test_revalidate_maps_binding_and_svd_failures(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)

    async def exercise() -> None:
        opened = await open_monitor_observation(
            request(debug_env, tmp_path / "data"), _seams=harness.seams()
        )
        session = opened.data
        harness.bind_result = OperationResult.failure(
            "stm32_debug_bind", "DEBUG_FIRMWARE_CHANGED", "changed", {}
        )
        assert (await session.revalidate()).code == "MONITOR_FIRMWARE_CHANGED"
        harness.bind_result = OperationResult.success(
            "stm32_debug_bind",
            replace(session.binding, input_snapshot_sha256="e" * 64),
        )
        assert (await session.revalidate()).code == "MONITOR_FIRMWARE_CHANGED"
        harness.bind_result = None
        svd_path = debug_env.root / debug_env.selection.path
        svd_path.write_bytes(svd_path.read_bytes() + b"changed")
        assert (await session.revalidate()).code == "MONITOR_PROVENANCE_CHANGED"
        await session.close()

    asyncio.run(exercise())


def test_open_cancellation_awaits_cleanup(debug_env: DebugEnv, tmp_path: Path) -> None:
    harness = Harness(debug_env)
    seams = harness.seams()

    async def cancel_bind(request: object, client: object) -> OperationResult:
        raise asyncio.CancelledError

    seams = replace(seams, bind=cancel_bind)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            open_monitor_observation(
                request(debug_env, tmp_path / "data"), _seams=seams
            )
        )
    assert harness.clients[0].closed is True
    assert harness.supervisors[0].stopped is True


def test_cleanup_failure_has_priority_when_open_fails(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)
    harness.bind_result = OperationResult.failure("stm32_debug_bind", "DEBUG_FIRMWARE_CHANGED", "changed", {})
    seams = harness.seams()
    original = seams.client_factory

    def broken_client(endpoint: object) -> ObservationClient:
        client = original(endpoint)
        client.close_error = RuntimeError("raw cleanup secret")
        return client

    seams = replace(seams, client_factory=broken_client)
    result = asyncio.run(open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=seams))
    assert result.code == "MONITOR_CLEANUP_FAILED"
    assert "secret" not in str(result.to_dict())
    assert harness.supervisors[0].stopped is True


def test_close_finishes_owned_cleanup_despite_repeated_cancellation(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)

    async def exercise() -> None:
        opened = await open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=harness.seams())
        session = opened.data
        client = harness.clients[0]
        client.close_started = asyncio.Event()
        client.close_release = asyncio.Event()
        closing = asyncio.create_task(session.close())
        await client.close_started.wait()
        closing.cancel()
        await asyncio.sleep(0)
        closing.cancel()
        client.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert client.closed is True
        assert harness.supervisors[0].stopped is True
        await session.close()

    asyncio.run(exercise())


def test_close_cleanup_error_is_stable(debug_env: DebugEnv, tmp_path: Path) -> None:
    harness = Harness(debug_env)

    async def exercise() -> None:
        opened = await open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=harness.seams())
        harness.clients[0].close_error = RuntimeError("raw close secret")
        with pytest.raises(MonitorObservationError) as raised:
            await opened.data.close()
        assert raised.value.code == "MONITOR_CLEANUP_FAILED"
        assert "secret" not in str(raised.value)
        assert harness.supervisors[0].stopped is True

    asyncio.run(exercise())


def test_supervisor_cleanup_error_and_cancelled_client_are_stable(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    async def exercise(error: BaseException, suffix: str) -> None:
        harness = Harness(debug_env)
        opened = await open_monitor_observation(
            request(debug_env, tmp_path / suffix), _seams=harness.seams()
        )
        harness.supervisors[0].stop_error = error
        with pytest.raises(MonitorObservationError) as raised:
            await opened.data.close()
        assert raised.value.code == "MONITOR_CLEANUP_FAILED"

    asyncio.run(exercise(RuntimeError("stop secret"), "stop-error"))
    harness = Harness(debug_env)

    async def cancelled_client() -> None:
        opened = await open_monitor_observation(
            request(debug_env, tmp_path / "cancelled-client"), _seams=harness.seams()
        )
        harness.clients[0].close_error = asyncio.CancelledError()
        with pytest.raises(MonitorObservationError):
            await opened.data.close()
        assert harness.supervisors[0].stopped is True

    asyncio.run(cancelled_client())
