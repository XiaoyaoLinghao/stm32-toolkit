from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest
from fakes.fake_probe import FakeProbeBackend
from stm32_toolkit.monitor_observation import (
    MonitorObservationRequest,
    MonitorObservationSeams,
    open_monitor_observation,
)
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.probe.backend import ProbeDescriptor
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.supervisor import ProbeServiceSupervisor
from stm32_toolkit.project_model import load_project_model
from test_debug_read import DebugEnv, debug_env  # noqa: F401

PROBE_ID = "probe-123"
SESSION_ID = "monitor-session"


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


def _project_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _session_root(env: DebugEnv, data_root: Path) -> tuple[Path, str]:
    model = load_project_model(env.root)
    paths = WorkspacePaths.from_roots(
        data_root, env.root, model.logical_project_id, SESSION_ID
    )
    component = "probe-" + hashlib.sha256(PROBE_ID.encode("utf-8")).hexdigest()[:24]
    return paths.session_root / "probes" / component, paths.workspace_id


def _request(env: DebugEnv, data_root: Path) -> MonitorObservationRequest:
    return MonitorObservationRequest(
        project_root=env.root,
        data_root=data_root,
        session_id=SESSION_ID,
        probe_id=PROBE_ID,
        expected_build_id=env.binding.build_id,
        expected_elf_sha256=env.binding.elf_sha256,
    )


class _NoHardwareBackend(FakeProbeBackend):
    def __init__(self) -> None:
        super().__init__(
            probes=(
                ProbeDescriptor(
                    PROBE_ID, "STMicroelectronics", "ST-LINK/V3", None
                ),
            ),
            memory={},
            registers={},
        )


@pytest.mark.parametrize("obstruction", ("registry-file", "guard-directory"))
def test_windows_public_observation_refusal_releases_lease_for_reuse(
    debug_env: DebugEnv,  # noqa: F811
    tmp_path: Path,
    obstruction: str,
) -> None:
    if os.name != "nt":
        pytest.skip("the qualified directory-guard contract is Windows-only")

    project_before = _project_snapshot(debug_env.root)
    data_root = (tmp_path / "monitor-data").absolute()
    data_root.mkdir()
    session_root, workspace_id = _session_root(debug_env, data_root)
    session_root.mkdir(parents=True)

    manager = ProbeLeaseManager(data_root)
    registry_root = manager.registry_root
    record_path = manager.record_path(PROBE_ID)
    guard_path = record_path.with_suffix(".guard")
    if obstruction == "registry-file":
        data_before = _tree_snapshot(data_root)
        registry_root.write_bytes(b"owned registry obstruction\n")
        obstruction_path = registry_root
    else:
        registry_root.mkdir()
        data_before = _tree_snapshot(data_root)
        guard_path.mkdir()
        obstruction_path = guard_path
    data_during_refusal = _tree_snapshot(data_root)

    backends: list[_NoHardwareBackend] = []
    supervisors: list[ProbeServiceSupervisor] = []
    bind_calls: list[object] = []

    def backend_factory() -> _NoHardwareBackend:
        backend = _NoHardwareBackend()
        backends.append(backend)
        return backend

    def supervisor_factory(
        config: object, lease_manager: object, backend_contract: object
    ) -> ProbeServiceSupervisor:
        supervisor = ProbeServiceSupervisor(
            config=config,  # type: ignore[arg-type]
            lease_manager=lease_manager,  # type: ignore[arg-type]
            backend_factory=backend_contract,  # type: ignore[arg-type]
        )
        supervisors.append(supervisor)
        return supervisor

    async def bind_without_reaching(request: object, client: object) -> object:
        bind_calls.append((request, client))
        raise AssertionError("obstruction refusal must precede firmware binding")

    seams = MonitorObservationSeams(
        _test_backend_factory=backend_factory,
        supervisor_factory=supervisor_factory,
        bind=bind_without_reaching,
    )
    opened = asyncio.run(
        open_monitor_observation(_request(debug_env, data_root), _seams=seams)
    )

    assert opened.ok is False
    assert opened.operation == "stm32_monitor_observation_open"
    assert opened.code == "MONITOR_PROVENANCE_CHANGED"
    assert opened.message == "Monitor observation could not be established"
    assert dict(opened.details) == {}
    assert bind_calls == []
    assert len(backends) == 1
    assert backends[0].events == [("close",)]
    assert backends[0].closed is True
    assert len(supervisors) == 1
    assert supervisors[0].endpoint is None
    assert not record_path.exists()
    assert not (session_root / "probe-endpoint.json").exists()
    assert _tree_snapshot(data_root) == data_during_refusal
    assert _project_snapshot(debug_env.root) == project_before

    obstruction_path.unlink() if obstruction_path.is_file() else obstruction_path.rmdir()
    data_root.rename(tmp_path / "monitor-data-moved")
    (tmp_path / "monitor-data-moved").rename(data_root)
    assert _tree_snapshot(data_root) == data_before

    first = manager.acquire(
        probe_id=PROBE_ID,
        workspace_id=workspace_id,
        session_id=SESSION_ID,
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43123/health",
    )
    first_lease_id = first.lease_id
    try:
        assert first.record_path == record_path
        assert json.loads(record_path.read_text(encoding="utf-8"))["state"] == "active"
    finally:
        first.release()

    second = manager.acquire(
        probe_id=PROBE_ID,
        workspace_id=workspace_id,
        session_id=SESSION_ID,
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43123/health",
    )
    try:
        assert second.lease_id != first_lease_id
    finally:
        second.release()
    assert json.loads(record_path.read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "state": "released",
        "leaseId": second.lease_id,
    }
