from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import threading
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
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.protocol import PROBE_PROTOCOL_VERSION
from stm32_toolkit.probe.service import ProbeEndpoint
from stm32_toolkit.probe.supervisor import ProbeServiceSupervisor
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


class RootSwapBackend:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


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

    def changed_parent(
        root: Path,
        destination: Path,
        identities: tuple[tuple[Path, int, int], ...],
    ) -> None:
        external_parent.rmdir()
        _directory_redirect(external_parent, debug_env.root)
        original(root, destination, identities)

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

    def changed_parent(
        root: Path,
        destination: Path,
        identities: tuple[tuple[Path, int, int], ...],
    ) -> None:
        external_parent.rmdir()
        external_parent.mkdir()
        original(root, destination, identities)

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


def test_real_supervisor_root_swap_in_backend_factory_writes_no_replacement_state(
    debug_env: DebugEnv, tmp_path: Path
) -> None:
    harness = Harness(debug_env)
    external_parent = tmp_path / "real-supervisor-parent"
    external_parent.mkdir()
    displaced_parent = tmp_path / "real-supervisor-parent-displaced"
    data_root = external_parent / "data"
    replacement_snapshots: list[dict[str, tuple[str, bytes | None, int]]] = []
    backends: list[RootSwapBackend] = []
    supervisors: list[ProbeServiceSupervisor] = []

    def swapping_backend_factory() -> RootSwapBackend:
        try:
            external_parent.rename(displaced_parent)
            external_parent.mkdir()
        except PermissionError:
            replacement_snapshots.append(_project_snapshot(external_parent))
            raise MonitorObservationError(
                "MONITOR_REQUEST_INVALID", "Monitor data root identity changed"
            ) from None
        replacement_snapshots.append(_project_snapshot(external_parent))
        backend = RootSwapBackend()
        backends.append(backend)
        return backend

    def real_supervisor_factory(
        config: object, lease_manager: object, backend_factory: object
    ) -> ProbeServiceSupervisor:
        assert isinstance(lease_manager, ProbeLeaseManager)
        supervisor = ProbeServiceSupervisor(
            config=config,
            lease_manager=lease_manager,
            backend_factory=backend_factory,
        )
        supervisors.append(supervisor)
        return supervisor

    seams = replace(
        harness.seams(),
        backend_factory=swapping_backend_factory,
        lease_manager_factory=ProbeLeaseManager,
        supervisor_factory=real_supervisor_factory,
    )
    result = asyncio.run(
        open_monitor_observation(request(debug_env, data_root), _seams=seams)
    )
    if result.ok:
        asyncio.run(result.data.close())

    assert result.ok is False
    assert result.code == "MONITOR_REQUEST_INVALID"
    assert replacement_snapshots
    assert _project_snapshot(external_parent) == replacement_snapshots[0]
    assert all(supervisor.endpoint is None for supervisor in supervisors)
    assert all(backend.closed for backend in backends)
    assert not ProbeLeaseManager(data_root).record_path("probe-123").exists()
    assert not list(tmp_path.rglob("probe-endpoint.json"))
    released_parent = tmp_path / "real-supervisor-parent-released"
    external_parent.rename(released_parent)
    released_parent.rename(external_parent)


def test_real_supervisor_pre_start_gate_blocks_post_factory_root_swap(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    external_parent = tmp_path / "real-supervisor-pre-start-parent"
    external_parent.mkdir()
    displaced_parent = tmp_path / "real-supervisor-pre-start-parent-displaced"
    released_parent = tmp_path / "real-supervisor-pre-start-parent-released"
    data_root = external_parent / "data"
    replacement_before: list[dict[str, tuple[str, bytes | None, int]]] = []
    guard_closes: list[object] = []
    original_guard_close = observation._DirectoryGuard.close

    def tracked_guard_close(guard: object) -> None:
        guard_closes.append(guard)
        original_guard_close(guard)

    monkeypatch.setattr(observation._DirectoryGuard, "close", tracked_guard_close)
    if os.name == "nt":
        handles = iter(range(10_000, 20_000))
        monkeypatch.setattr(
            observation, "_windows_directory_handle", lambda path: next(handles)
        )
        monkeypatch.setattr(observation, "_close_windows_handle", lambda handle: None)

    class Backend:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    backend = Backend()

    def swapping_backend_factory() -> Backend:
        def swap_after_factory_returns() -> None:
            external_parent.rename(displaced_parent)
            external_parent.mkdir()
            replacement_before.append(_project_snapshot(external_parent))

        asyncio.get_running_loop().call_soon(swap_after_factory_returns)
        return backend

    def real_supervisor_factory(
        config: object, lease_manager: object, backend_factory: object
    ) -> ProbeServiceSupervisor:
        return ProbeServiceSupervisor(
            config=config,
            lease_manager=lease_manager,
            backend_factory=backend_factory,
        )

    seams = replace(
        harness.seams(),
        backend_factory=swapping_backend_factory,
        lease_manager_factory=ProbeLeaseManager,
        supervisor_factory=real_supervisor_factory,
    )
    result = asyncio.run(
        open_monitor_observation(request(debug_env, data_root), _seams=seams)
    )
    replacement_after = _project_snapshot(external_parent)
    external_parent.rename(released_parent)
    displaced_parent.rename(external_parent)

    assert replacement_before == [{}]
    assert replacement_after == replacement_before[0]
    assert result.code == "MONITOR_REQUEST_INVALID"
    assert backend.close_calls == 1
    assert len(guard_closes) == 1


@pytest.mark.skipif(os.name == "nt", reason="Windows directory handles deny rename")
def test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    external_parent = tmp_path / "real-supervisor-thread-parent"
    external_parent.mkdir()
    displaced_parent = tmp_path / "real-supervisor-thread-parent-displaced"
    released_parent = tmp_path / "real-supervisor-thread-parent-released"
    data_root = external_parent / "data"
    backend_created = threading.Event()
    swap_requested = threading.Event()
    swap_finished = threading.Event()
    swap_errors: list[BaseException] = []
    original_verify = observation._DirectoryGuard.verify
    triggered = False

    def swap_root() -> None:
        try:
            if not swap_requested.wait(5):
                raise TimeoutError("post-factory identity check was not reached")
            external_parent.rename(displaced_parent)
            external_parent.mkdir()
        except BaseException as error:
            swap_errors.append(error)
        finally:
            swap_finished.set()

    thread = threading.Thread(target=swap_root, name="monitor-root-swap")
    thread.start()

    def verified_then_swap(guard: object) -> None:
        nonlocal triggered
        original_verify(guard)
        if backend_created.is_set() and not triggered:
            triggered = True
            swap_requested.set()
            if not swap_finished.wait(5):
                raise TimeoutError("root swap did not finish")

    monkeypatch.setattr(observation._DirectoryGuard, "verify", verified_then_swap)

    class Backend:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    backend = Backend()

    def backend_factory() -> Backend:
        backend_created.set()
        return backend

    def real_supervisor_factory(
        config: object, lease_manager: object, backend_factory: object
    ) -> ProbeServiceSupervisor:
        assert isinstance(lease_manager, ProbeLeaseManager)
        return ProbeServiceSupervisor(
            config=config,
            lease_manager=lease_manager,
            backend_factory=backend_factory,
        )

    seams = replace(
        harness.seams(),
        backend_factory=backend_factory,
        lease_manager_factory=ProbeLeaseManager,
        supervisor_factory=real_supervisor_factory,
    )
    result = asyncio.run(
        open_monitor_observation(request(debug_env, data_root), _seams=seams)
    )
    thread.join(5)
    replacement_after = _project_snapshot(external_parent)
    external_parent.rename(released_parent)
    displaced_parent.rename(external_parent)

    assert not thread.is_alive()
    assert swap_errors == []
    assert triggered is True
    assert replacement_after == {}
    assert result.code == "MONITOR_REQUEST_INVALID"
    assert backend.close_calls == 1


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
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=descriptor
        ),
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
        lambda descriptor: SimpleNamespace(
            st_mode=(stat.S_IFDIR | 0o700) if descriptor == 20 else (stat.S_IFREG | 0o600),
            st_dev=1,
            st_ino=descriptor,
        ),
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
    def fake_fstat(descriptor: int) -> SimpleNamespace:
        if descriptor == 31:
            raise OSError("identity unavailable")
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=30)

    monkeypatch.setattr(observation.os, "fstat", fake_fstat)
    monkeypatch.setattr(observation.os, "close", closed.append)

    with pytest.raises(OSError, match="identity"):
        observation._safe_mkdir_posix(Path("/external"), Path("/external/data"))
    assert sorted(closed) == [30, 31]


def test_posix_guard_revalidates_named_and_descriptor_identity_and_closes_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    paths = (Path("/one"), Path("/one/two"))
    identities = ((paths[0], 7, 11), (paths[1], 7, 12))
    descriptors = iter((41, 42))
    descriptor_identities = {41: 11, 42: 12}
    closed: list[int] = []

    monkeypatch.setattr(observation.os, "name", "posix")
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(
        observation.os,
        "lstat",
        lambda path: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_dev=7,
            st_ino=11 if path == paths[0] else 12,
        ),
    )
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_dev=7,
            st_ino=descriptor_identities[descriptor],
        ),
    )

    def close_descriptor(descriptor: int) -> None:
        closed.append(descriptor)
        if descriptor == 42:
            raise OSError("close failed")

    monkeypatch.setattr(observation.os, "close", close_descriptor)
    guard = observation._DirectoryGuard(identities)
    with pytest.raises(OSError, match="close failed"):
        guard.close()
    assert closed == [42, 41]
    guard.close()
    assert closed == [42, 41]


def test_windows_guard_close_attempts_every_handle_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    guard = observation._DirectoryGuard.__new__(observation._DirectoryGuard)
    guard._identities = ()
    guard._posix_descriptors = []
    guard._windows_handles = [51, 52]
    closed: list[int] = []

    def close_handle(handle: int) -> None:
        closed.append(handle)
        if handle == 52:
            raise OSError("handle close failed")

    monkeypatch.setattr(observation, "_close_windows_handle", close_handle)
    with pytest.raises(OSError, match="handle close failed"):
        guard.close()
    assert closed == [52, 51]
    guard.close()
    assert closed == [52, 51]


def test_windows_close_handle_declares_signature_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes
    import stm32_toolkit.monitor_observation as observation

    class CloseHandle:
        argtypes = None
        restype = None

        def __call__(self, handle: object) -> int:
            return 0

    close_handle = CloseHandle()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(CloseHandle=close_handle),
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 6)

    with pytest.raises(OSError):
        observation._close_windows_handle(73)
    assert close_handle.argtypes is not None
    assert close_handle.restype is not None


def test_posix_guard_constructor_closes_all_after_identity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    paths = (Path("/guard-one"), Path("/guard-one/two"))
    identities = ((paths[0], 3, 21), (paths[1], 3, 22))
    descriptors = iter((61, 62))
    closed: list[int] = []
    monkeypatch.setattr(observation.os, "name", "posix")
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(
        observation.os,
        "lstat",
        lambda path: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_dev=3,
            st_ino=21 if path == paths[0] else 999,
        ),
    )
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_dev=3,
            st_ino=21 if descriptor == 61 else 22,
        ),
    )
    monkeypatch.setattr(observation.os, "close", closed.append)

    with pytest.raises(ValueError):
        observation._DirectoryGuard(identities)
    assert closed == [62, 61]


def test_posix_directory_close_failure_closes_each_descriptor_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    descriptors = iter((81, 82, 83))
    closed: list[int] = []
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(observation.os, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=descriptor
        ),
    )

    def close_descriptor(descriptor: int) -> None:
        closed.append(descriptor)
        if descriptor == 83:
            raise OSError("descriptor close failed")

    monkeypatch.setattr(observation.os, "close", close_descriptor)

    with pytest.raises(OSError, match="descriptor close failed"):
        observation._safe_mkdir_posix(Path("/external"), Path("/external/data"))
    assert closed == [83, 82, 81]


def test_posix_guard_capture_is_cleaned_when_temporary_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    class Guard:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("guard close also failed")

    guard = Guard()
    descriptors = iter((91, 92, 93))
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(descriptors))
    monkeypatch.setattr(observation.os, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=descriptor
        ),
    )
    monkeypatch.setattr(observation, "_DirectoryGuard", lambda identities: guard)
    monkeypatch.setattr(
        observation.os,
        "close",
        lambda descriptor: (_ for _ in ()).throw(OSError("temporary close failed"))
        if descriptor == 93
        else None,
    )

    with pytest.raises(OSError, match="temporary close failed"):
        observation._safe_mkdir_posix(
            Path("/external"),
            Path("/external/data"),
            capture_guard=True,
        )
    assert guard.close_calls == 1


def test_posix_directory_guard_rejects_swap_between_walk_and_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    root = Path("/external")
    destination = root / "data"
    opened = iter((101, 102, 103))
    temporary = {101: 1, 102: 2, 103: 3}
    closed: list[int] = []

    class Guard:
        def __init__(
            self, identities: tuple[tuple[Path, int, int], ...]
        ) -> None:
            assert identities[1] == (root, 5, 2)
            raise ValueError

        @classmethod
        def capture(cls, destination: Path) -> object:
            return object()

    monkeypatch.setattr(observation, "_DirectoryGuard", Guard)
    monkeypatch.setattr(observation.os, "open", lambda *args, **kwargs: next(opened))
    monkeypatch.setattr(observation.os, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        observation.os,
        "fstat",
        lambda descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_dev=5,
            st_ino=temporary[descriptor],
        ),
    )
    monkeypatch.setattr(observation.os, "close", closed.append)

    with pytest.raises(ValueError):
        observation._safe_mkdir_posix(
            root,
            destination,
            capture_guard=True,
        )
    assert sorted(closed) == [101, 102, 103]


def test_windows_directory_creation_closes_guard_if_temporary_handle_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    opened: list[int] = []
    closed: list[int] = []

    def open_handle(path: Path) -> int:
        handle = len(opened) + 101
        opened.append(handle)
        return handle

    def close_handle(handle: int) -> None:
        closed.append(handle)
        if handle == 101:
            raise OSError("temporary handle close failed")

    monkeypatch.setattr(observation, "_windows_directory_handle", open_handle)
    monkeypatch.setattr(observation, "_close_windows_handle", close_handle)

    root = tmp_path / "windows-create-root"
    destination = root / "sessions" / "one"
    with pytest.raises(OSError, match="temporary handle close failed"):
        observation._safe_mkdir_windows(root, destination, ())
    assert set(opened).issubset(closed)


def test_windows_directory_creation_rejects_changed_anchor_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    anchor = Path(tmp_path.anchor)
    metadata = os.lstat(anchor)
    closed: list[int] = []
    monkeypatch.setattr(observation, "_windows_directory_handle", lambda path: 201)
    monkeypatch.setattr(observation, "_close_windows_handle", closed.append)

    with pytest.raises(ValueError):
        observation._safe_mkdir_windows(
            tmp_path / "root",
            tmp_path / "root" / "session",
            ((anchor, int(metadata.st_dev), int(metadata.st_ino) + 1),),
        )
    assert closed == [201]


def test_safe_mkdir_chain_uses_posix_guard_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    guard = object()
    calls: list[tuple[Path, Path, tuple[tuple[Path, int, int], ...], bool]] = []
    root = Path("/data")
    destination = root / "session"
    monkeypatch.setattr(observation.os, "name", "posix")
    monkeypatch.setattr(observation, "_verify_ancestor_identities", lambda value: None)

    def create(
        root: Path,
        destination: Path,
        identities: tuple[tuple[Path, int, int], ...],
        *,
        capture_guard: bool,
    ) -> object:
        calls.append((root, destination, identities, capture_guard))
        return guard

    monkeypatch.setattr(observation, "_safe_mkdir_posix", create)

    assert observation._safe_mkdir_chain(root, destination) is guard
    assert calls == [(root, destination, (), True)]


def test_directory_guard_capture_requires_existing_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    monkeypatch.setattr(observation, "_ancestor_identities", lambda destination: ())
    with pytest.raises(ValueError):
        observation._DirectoryGuard.capture(Path("/missing"))


def test_guarded_backend_factory_closes_backend_when_root_identity_changes() -> None:
    import stm32_toolkit.monitor_observation as observation

    class Guard:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self) -> None:
            self.calls += 1
            if self.calls == 2:
                raise ValueError

    backend = RootSwapBackend()
    guarded = observation._guard_backend_factory(Guard(), lambda: backend)

    with pytest.raises(MonitorObservationError) as raised:
        guarded()
    assert raised.value.code == "MONITOR_REQUEST_INVALID"
    assert backend.closed is True


def test_guarded_backend_factory_cleanup_failure_has_priority() -> None:
    import stm32_toolkit.monitor_observation as observation

    class Guard:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self) -> None:
            self.calls += 1
            if self.calls == 2:
                raise ValueError

    class Backend:
        def close(self) -> None:
            raise RuntimeError("raw backend cleanup detail")

    guarded = observation._guard_backend_factory(Guard(), Backend)

    with pytest.raises(MonitorObservationError) as raised:
        guarded()
    assert raised.value.code == "MONITOR_CLEANUP_FAILED"
    assert "detail" not in str(raised.value)


def test_guarded_backend_factory_returns_only_after_two_identity_checks() -> None:
    import stm32_toolkit.monitor_observation as observation

    class Guard:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self) -> None:
            self.calls += 1

    guard = Guard()
    backend = RootSwapBackend()
    guarded = observation._guard_backend_factory(guard, lambda: backend)

    assert guarded() is backend
    assert guard.calls == 2


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


def test_open_cancellation_awaits_cleanup(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    seams = harness.seams()
    guard_closes: list[object] = []
    original_guard_close = observation._DirectoryGuard.close

    def tracked_guard_close(guard: object) -> None:
        guard_closes.append(guard)
        original_guard_close(guard)

    monkeypatch.setattr(observation._DirectoryGuard, "close", tracked_guard_close)

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
    assert len(guard_closes) == 1


def test_cleanup_failure_has_priority_when_open_fails(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    harness.bind_result = OperationResult.failure("stm32_debug_bind", "DEBUG_FIRMWARE_CHANGED", "changed", {})
    seams = harness.seams()
    original = seams.client_factory
    guard_closes: list[object] = []
    original_guard_close = observation._DirectoryGuard.close

    def tracked_guard_close(guard: object) -> None:
        guard_closes.append(guard)
        original_guard_close(guard)

    monkeypatch.setattr(observation._DirectoryGuard, "close", tracked_guard_close)

    def broken_client(endpoint: object) -> ObservationClient:
        client = original(endpoint)
        client.close_error = RuntimeError("raw cleanup secret")
        return client

    seams = replace(seams, client_factory=broken_client)
    result = asyncio.run(open_monitor_observation(request(debug_env, tmp_path / "data"), _seams=seams))
    assert result.code == "MONITOR_CLEANUP_FAILED"
    assert "secret" not in str(result.to_dict())
    assert harness.supervisors[0].stopped is True
    assert len(guard_closes) == 1


def test_close_finishes_owned_cleanup_despite_repeated_cancellation(
    debug_env: DebugEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.monitor_observation as observation

    harness = Harness(debug_env)
    guard_closes: list[object] = []
    original_guard_close = observation._DirectoryGuard.close

    def tracked_guard_close(guard: object) -> None:
        guard_closes.append(guard)
        original_guard_close(guard)

    monkeypatch.setattr(observation._DirectoryGuard, "close", tracked_guard_close)

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
        assert len(guard_closes) == 1
        await session.close()
        assert len(guard_closes) == 1

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


def test_cleanup_attempts_every_resource_and_preserves_first_fatal() -> None:
    import stm32_toolkit.monitor_observation as observation

    class Fatal(BaseException):
        pass

    events: list[str] = []

    class Client:
        async def close(self) -> None:
            events.append("client")
            raise Fatal("client fatal")

    class Supervisor:
        async def stop(self) -> None:
            events.append("supervisor")
            raise Fatal("supervisor fatal")

    class Guard:
        def close(self) -> None:
            events.append("guard")
            raise Fatal("guard fatal")

    with pytest.raises(Fatal, match="client fatal"):
        asyncio.run(observation._cleanup_resources(Client(), Supervisor(), Guard()))
    assert events == ["client", "supervisor", "guard"]


@pytest.mark.parametrize("cancelled_resource", ("supervisor", "guard"))
def test_cleanup_maps_resource_cancellation_to_stable_failure(
    cancelled_resource: str,
) -> None:
    import stm32_toolkit.monitor_observation as observation

    class Client:
        async def close(self) -> None:
            return None

    class Supervisor:
        async def stop(self) -> None:
            if cancelled_resource == "supervisor":
                raise asyncio.CancelledError

    class Guard:
        def close(self) -> None:
            if cancelled_resource == "guard":
                raise asyncio.CancelledError

    with pytest.raises(MonitorObservationError) as raised:
        asyncio.run(observation._cleanup_resources(Client(), Supervisor(), Guard()))
    assert raised.value.code == "MONITOR_CLEANUP_FAILED"
