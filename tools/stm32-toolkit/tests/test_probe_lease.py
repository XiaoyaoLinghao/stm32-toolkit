from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stm32_toolkit.probe.lease import (
    ProcessIdentity,
    ProbeBusyError,
    ProbeLeaseError,
    ProbeLeaseManager,
)
from stm32_toolkit.probe.model import OperationLevel


NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)
OWNER = ProcessIdentity(pid=4100, process_start_id="start-4100", boot_id="boot-a")
SUCCESSOR = ProcessIdentity(pid=4200, process_start_id="start-4200", boot_id="boot-a")


def manager(
    data_root: Path,
    identity: ProcessIdentity,
    *,
    inspected: dict[int, ProcessIdentity | None] | None = None,
    health: bool = False,
    now: datetime = NOW,
) -> ProbeLeaseManager:
    process_table = inspected if inspected is not None else {identity.pid: identity}
    return ProbeLeaseManager(
        data_root,
        current_identity=lambda: identity,
        inspect_process=lambda pid: process_table.get(pid),
        health_check=lambda endpoint, lease_id: health,
        utc_now=lambda: now,
    )


def acquire(manager_: ProbeLeaseManager, workspace: str = "workspace-a"):
    return manager_.acquire(
        probe_id="probe-123",
        workspace_id=workspace,
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43123/health",
    )


def stale_record(identity: ProcessIdentity = OWNER) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "protocol": "stm32-toolkit-probe/1",
        "toolkitVersion": "0.3.0",
        "probeId": "probe-123",
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "leaseId": "lease-stale",
        "pid": identity.pid,
        "processStartId": identity.process_start_id,
        "bootId": identity.boot_id,
        "healthUrl": "http://127.0.0.1:43123/health",
        "operationLevel": "observe",
        "createdAtUtc": "2026-08-07T11:00:00.000000Z",
        "heartbeatAtUtc": "2026-08-07T11:00:01.000000Z",
    }


def write_stale_record(manager_: ProbeLeaseManager, record: dict[str, object]) -> Path:
    path = manager_.record_path("probe-123")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return path


def test_two_workspaces_cannot_own_one_probe_and_owner_is_redacted(tmp_path: Path):
    first_manager = manager(tmp_path / "data", OWNER)
    second_manager = manager(tmp_path / "data", SUCCESSOR)
    first = acquire(first_manager)

    try:
        with pytest.raises(ProbeBusyError) as error:
            acquire(second_manager, workspace="workspace-b")

        assert error.value.code == "PROBE_BUSY"
        assert error.value.owner.workspace_id == "workspace-a"
        assert error.value.owner.pid == OWNER.pid
        serialized = json.dumps(error.value.owner.to_dict())
        assert "healthUrl" not in serialized
        assert "processStartId" not in serialized
        assert "token" not in serialized.lower()
    finally:
        first.release()


def test_release_allows_a_successor_and_old_release_is_idempotent(tmp_path: Path):
    first = acquire(manager(tmp_path / "data", OWNER))
    first.release()
    first.release()

    second = acquire(manager(tmp_path / "data", SUCCESSOR), workspace="workspace-b")
    try:
        assert second.owner.workspace_id == "workspace-b"
        assert second.lease_id != first.lease_id
    finally:
        second.release()


def test_dead_process_and_dead_health_are_reclaimed(tmp_path: Path):
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    path = write_stale_record(successor, stale_record())

    lease = acquire(successor, workspace="workspace-b")
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        assert current["leaseId"] == lease.lease_id
        assert current["pid"] == SUCCESSOR.pid
    finally:
        lease.release()


@pytest.mark.parametrize(
    ("inspected", "health"),
    [
        ({OWNER.pid: OWNER, SUCCESSOR.pid: SUCCESSOR}, False),
        ({OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR}, True),
    ],
)
def test_live_process_or_live_authenticated_health_is_never_reclaimed(
    tmp_path: Path, inspected, health
):
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected=inspected,
        health=health,
    )
    write_stale_record(successor, stale_record())

    with pytest.raises(ProbeBusyError) as error:
        acquire(successor, workspace="workspace-b")

    assert error.value.owner.pid == OWNER.pid


def test_reused_pid_with_different_start_identity_can_be_reclaimed(tmp_path: Path):
    reused = replace(OWNER, process_start_id="new-process-same-pid")
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: reused, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    write_stale_record(successor, stale_record())

    lease = acquire(successor, workspace="workspace-b")
    lease.release()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", 2),
        ("protocol", "stm32-toolkit-probe/2"),
        ("toolkitVersion", "0.4.0"),
    ],
)
def test_incompatible_owner_record_is_never_reclaimed(tmp_path: Path, field, value):
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    record = stale_record()
    record[field] = value
    path = write_stale_record(successor, record)

    with pytest.raises(ProbeLeaseError) as error:
        acquire(successor, workspace="workspace-b")

    assert error.value.code == "PROBE_REGISTRY_INCOMPATIBLE"
    assert json.loads(path.read_text(encoding="utf-8"))[field] == value


def test_heartbeat_updates_only_the_current_lease(tmp_path: Path):
    first_manager = manager(tmp_path / "data", OWNER, now=NOW)
    lease = acquire(first_manager)
    later_manager = manager(
        tmp_path / "data", OWNER, now=NOW + timedelta(seconds=5)
    )

    lease.heartbeat(utc_now=later_manager.utc_now)
    record = json.loads(lease.record_path.read_text(encoding="utf-8"))

    assert record["leaseId"] == lease.lease_id
    assert record["heartbeatAtUtc"] == "2026-08-07T12:00:05.000000Z"
    lease.release()


def test_tampered_record_is_not_released_or_overwritten_by_old_owner(tmp_path: Path):
    lease = acquire(manager(tmp_path / "data", OWNER))
    record = json.loads(lease.record_path.read_text(encoding="utf-8"))
    record["leaseId"] = "lease-successor"
    lease.record_path.write_bytes(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )

    with pytest.raises(ProbeLeaseError) as error:
        lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))

    assert error.value.code == "PROBE_LEASE_LOST"
    assert json.loads(lease.record_path.read_text(encoding="utf-8"))["leaseId"] == (
        "lease-successor"
    )


def test_record_path_is_portable_and_does_not_expose_probe_id(tmp_path: Path):
    manager_ = manager(tmp_path / "data", OWNER)

    path = manager_.record_path("probe:serial/with-invalid-path-chars")

    assert path.parent.name == "probe-registry"
    assert path.suffix == ".lock"
    assert path.stem.isalnum()
    assert "probe:serial" not in str(path)


@pytest.mark.parametrize(
    "health_url",
    [
        "http://localhost:43123/health",
        "https://127.0.0.1:43123/health",
        "http://user@127.0.0.1:43123/health",
        "http://127.0.0.1:bad/health",
        "http://127.0.0.1:99999/health",
        "http://127.0.0.1:43123/other",
    ],
)
def test_health_endpoint_requires_exact_bounded_loopback_url(
    health_url: str, tmp_path: Path
):
    manager_ = manager(tmp_path / "data", OWNER)

    with pytest.raises(ProbeLeaseError) as error:
        manager_.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url=health_url,
        )

    assert error.value.code == "PROBE_LEASE_INVALID"


def test_registry_redirect_is_rejected_before_lock_write(tmp_path: Path, monkeypatch):
    data_root = tmp_path / "data"
    outside = tmp_path / "outside"
    data_root.mkdir()
    outside.mkdir()
    registry = data_root / "probe-registry"
    try:
        registry.symlink_to(outside, target_is_directory=True)
    except OSError:
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(registry), str(outside)],
            capture_output=True,
            check=False,
        ) if os.name == "nt" else None
        if result is None or result.returncode != 0:
            registry.mkdir()
            import stm32_toolkit.probe.lease as lease_module

            real_is_redirect = lease_module._is_redirect

            def injected_redirect(path, metadata):
                return path == registry or real_is_redirect(path, metadata)

            monkeypatch.setattr(lease_module, "_is_redirect", injected_redirect)

    with pytest.raises(ProbeLeaseError) as error:
        acquire(manager(data_root, OWNER))

    assert error.value.code == "PROBE_REGISTRY_UNSAFE"
    assert list(outside.iterdir()) == []


def test_data_root_parent_redirect_is_rejected_before_directory_creation(
    tmp_path: Path, monkeypatch
):
    container = tmp_path / "container"
    outside = tmp_path / "outside"
    redirect_parent = container / "redirect-parent"
    container.mkdir()
    outside.mkdir()
    try:
        redirect_parent.symlink_to(outside, target_is_directory=True)
    except OSError:
        result = (
            subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(redirect_parent), str(outside)],
                capture_output=True,
                check=False,
            )
            if os.name == "nt"
            else None
        )
        if result is None or result.returncode != 0:
            redirect_parent.mkdir()
            import stm32_toolkit.probe.lease as lease_module

            real_is_redirect = lease_module._is_redirect

            def injected_redirect(path, metadata):
                return path == redirect_parent or real_is_redirect(path, metadata)

            monkeypatch.setattr(lease_module, "_is_redirect", injected_redirect)

    data_root = redirect_parent / "plugin-data"
    with pytest.raises(ProbeLeaseError) as error:
        acquire(manager(data_root, OWNER))

    assert error.value.code == "PROBE_REGISTRY_UNSAFE"
    assert not (outside / "plugin-data").exists()


def test_registry_permission_failure_is_stable_and_does_not_leak_path(
    tmp_path: Path, monkeypatch
):
    manager_ = manager(tmp_path / "data", OWNER)
    real_replace = os.replace

    def denied(source, destination):
        if str(destination).endswith(".lock"):
            raise PermissionError("C:\\private\\probe-registry")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", denied)

    with pytest.raises(ProbeLeaseError) as error:
        acquire(manager_)

    assert error.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert "private" not in error.value.message.lower()


def test_real_cross_process_lock_blocks_then_allows_successor(tmp_path: Path):
    data_root = tmp_path / "data"
    parent = ProbeLeaseManager(data_root).acquire(
        probe_id="probe-123",
        workspace_id="workspace-parent",
        session_id="session-parent",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43123/health",
    )
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import sys
from pathlib import Path
from stm32_toolkit.probe.lease import ProbeBusyError, ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel

try:
    lease = ProbeLeaseManager(Path(sys.argv[1])).acquire(
        probe_id="probe-123",
        workspace_id="workspace-child",
        session_id="session-child",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
    )
except ProbeBusyError as error:
    print("BUSY:" + error.owner.workspace_id)
else:
    print("ACQUIRED:" + lease.owner.workspace_id)
    lease.release()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)

    try:
        blocked = subprocess.run(
            [sys.executable, "-c", script, str(data_root)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )
        assert blocked.returncode == 0, blocked.stderr
        assert blocked.stdout.strip() == "BUSY:workspace-parent"
    finally:
        parent.release()

    successor = subprocess.run(
        [sys.executable, "-c", script, str(data_root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=environment,
    )
    assert successor.returncode == 0, successor.stderr
    assert successor.stdout.strip() == "ACQUIRED:workspace-child"
