from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.probe.lease import (
    ProcessIdentity,
    ProbeBusyError,
    ProbeLease,
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
        "protocol": "stm32-toolkit-probe/2",
        "toolkitVersion": __version__,
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


def test_runtime_authority_closes_registry_descriptor_when_guard_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager_ = manager(tmp_path / "data", OWNER)
    closed: list[int] = []
    monkeypatch.setattr(manager_, "_ensure_registry", lambda authority: 701)
    monkeypatch.setattr(
        manager_,
        "_open_guard",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("guard denied")),
    )
    monkeypatch.setattr(os, "close", closed.append)

    with pytest.raises(OSError, match="guard denied"):
        manager_.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43123/health",
            _runtime_root_authority=object(),  # type: ignore[arg-type]
        )

    assert closed == [701]


def test_runtime_authority_closes_registry_descriptor_when_guard_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.probe.lease as lease_module

    class Handle:
        closed = False

        def close(self) -> None:
            self.closed = True
            raise OSError("guard close failed")

    handle = Handle()
    closed: list[int] = []
    monkeypatch.setattr(lease_module, "_unlock_handle", lambda value: None)
    monkeypatch.setattr(os, "close", closed.append)
    lease = ProbeLease(
        handle=handle,  # type: ignore[arg-type]
        record_path=tmp_path / "record.lock",
        record=stale_record(),
        owner_identity=OWNER,
        registry_descriptor=702,
    )

    with pytest.raises(OSError, match="guard close failed"):
        lease._close_locked_handle()

    assert handle.closed is True
    assert closed == [702]


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


def test_external_handoff_is_digest_bound_retryable_and_consumed_once(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "ab" * 32
    first_manager = manager(data_root, OWNER)
    first = acquire(first_manager)

    first.reserve_external_handoff(ticket)
    first.release()

    record = json.loads(first.record_path.read_text(encoding="utf-8"))
    serialized = json.dumps(record, sort_keys=True)
    assert record["state"] == "externally-owned"
    assert record["ticketSha256"] == __import__("hashlib").sha256(
        ticket.encode("ascii")
    ).hexdigest()
    assert ticket not in serialized

    successor_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    with pytest.raises(ProbeBusyError):
        acquire(successor_manager, workspace="workspace-b")
    with pytest.raises(ProbeBusyError):
        successor_manager.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43124/health",
            handoff_ticket="cd" * 32,
        )

    claimed = successor_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    claimed.release()
    assert json.loads(first.record_path.read_text(encoding="utf-8"))["state"] == (
        "externally-owned"
    )

    retry = successor_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    retry.consume_external_handoff(ticket)
    retry.release()
    assert json.loads(first.record_path.read_text(encoding="utf-8"))["state"] == (
        "handoff-consumed"
    )
    assert successor_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert successor_manager.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert json.loads(first.record_path.read_text(encoding="utf-8"))["state"] == (
        "released"
    )

    with pytest.raises(ProbeLeaseError) as replay:
        successor_manager.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43124/health",
            handoff_ticket=ticket,
        )
    assert replay.value.code == "PROBE_HANDOFF_INVALID"

    successor = acquire(successor_manager, workspace="workspace-b")
    successor.release()


def test_external_handoff_claim_requires_the_reserved_operation_level(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "ad" * 32
    owner = acquire(manager(data_root, OWNER))
    owner.reserve_external_handoff(ticket)
    owner.release()

    claimant = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
    )
    with pytest.raises(ProbeBusyError) as mismatch:
        claimant.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.MODIFY,
            health_url="http://127.0.0.1:43124/health",
            handoff_ticket=ticket,
        )
    assert mismatch.value.owner.operation_level is OperationLevel.OBSERVE

    exact = claimant.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    exact.release()


def test_consumed_ticket_tombstone_survives_successor_release_and_restart(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "ae" * 32
    owner = acquire(manager(data_root, OWNER))
    owner.reserve_external_handoff(ticket)
    owner.release()

    claimant_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
    )
    claimant = claimant_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    claimant.consume_external_handoff(ticket)
    claimant.release()
    assert claimant_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert claimant_manager.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )

    successor = acquire(claimant_manager, workspace="workspace-b")
    successor.release()

    restarted = manager(
        data_root,
        ProcessIdentity(4300, "start-4300", "boot-a"),
        inspected={SUCCESSOR.pid: None},
    )
    assert restarted.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    with pytest.raises(ProbeLeaseError) as replay:
        restarted.acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43125/health",
            handoff_ticket=ticket,
        )
    assert replay.value.code == "PROBE_HANDOFF_INVALID"


def test_crashed_external_claim_restores_reservation_instead_of_erasing_it(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "ef" * 32
    owner_manager = manager(data_root, OWNER)
    lease = acquire(owner_manager)
    lease.reserve_external_handoff(ticket)
    lease.release()

    claimant = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    claimed = claimant.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    claimed._close_locked_handle()

    later = manager(
        data_root,
        ProcessIdentity(4300, "start-4300", "boot-a"),
        inspected={SUCCESSOR.pid: None},
        health=False,
    )
    with pytest.raises(ProbeBusyError):
        acquire(later, workspace="workspace-b")

    retry = later.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43125/health",
        handoff_ticket=ticket,
    )
    retry.release()


def test_external_record_redirect_is_rejected_without_downgrading_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data_root = tmp_path / "data"
    ticket = "12" * 32
    owner_manager = manager(data_root, OWNER)
    lease = acquire(owner_manager)
    lease.reserve_external_handoff(ticket)
    lease.release()
    record_path = owner_manager.record_path("probe-123")
    before = record_path.read_bytes()

    import stm32_toolkit.probe.lease as lease_module

    real_redirect = lease_module._is_redirect

    def redirect(path: Path, metadata: os.stat_result) -> bool:
        return path == record_path or real_redirect(path, metadata)

    monkeypatch.setattr(lease_module, "_is_redirect", redirect)
    with pytest.raises(ProbeLeaseError) as error:
        acquire(manager(data_root, SUCCESSOR), workspace="workspace-b")

    assert error.value.code == "PROBE_REGISTRY_UNSAFE"
    assert record_path.read_bytes() == before


def test_external_record_descriptor_identity_swap_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import stm32_toolkit.probe.lease as lease_module

    data_root = tmp_path / "data"
    owner_manager = manager(data_root, OWNER)
    lease = acquire(owner_manager)
    lease.reserve_external_handoff("34" * 32)
    lease.release()
    record_path = owner_manager.record_path("probe-123")
    before = record_path.read_bytes()
    real_lstat = os.lstat
    record_lstats = 0

    def replaced(path: object, *args, **kwargs):
        nonlocal record_lstats
        metadata = real_lstat(path, *args, **kwargs)
        if Path(path) == record_path:
            record_lstats += 1
            if record_lstats >= 2:
                return type(
                    "Changed",
                    (),
                    {
                        "st_mode": metadata.st_mode,
                        "st_dev": metadata.st_dev,
                        "st_ino": metadata.st_ino + 1,
                        "st_file_attributes": getattr(
                            metadata, "st_file_attributes", 0
                        ),
                    },
                )()
        return metadata

    monkeypatch.setattr(lease_module.os, "lstat", replaced)
    with pytest.raises(ProbeLeaseError) as error:
        acquire(manager(data_root, SUCCESSOR), workspace="workspace-b")
    assert error.value.code == "PROBE_REGISTRY_UNSAFE"
    assert record_path.read_bytes() == before


def test_external_handoff_transition_guards_are_strict_and_idempotent(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "56" * 32
    lease = acquire(manager(data_root, OWNER))

    with pytest.raises(ProbeLeaseError) as malformed:
        lease.reserve_external_handoff("short")
    assert malformed.value.code == "PROBE_LEASE_INVALID"

    lease.reserve_external_handoff(ticket)
    lease.reserve_external_handoff(ticket)
    with pytest.raises(ProbeLeaseError) as changed:
        lease.reserve_external_handoff("78" * 32)
    assert changed.value.code == "PROBE_LEASE_LOST"
    with pytest.raises(ProbeLeaseError) as wrong_consume:
        lease.consume_external_handoff("78" * 32)
    assert wrong_consume.value.code == "PROBE_LEASE_LOST"
    lease.release()

    with pytest.raises(ProbeLeaseError) as released:
        lease.reserve_external_handoff(ticket)
    assert released.value.code == "PROBE_LEASE_LOST"
    with pytest.raises(ProbeLeaseError) as inactive:
        lease.consume_external_handoff(ticket)
    assert inactive.value.code == "PROBE_LEASE_LOST"

    successor_manager = manager(data_root, SUCCESSOR)
    claimant = successor_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    claimant.consume_external_handoff(ticket)
    claimant.release()
    assert successor_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert successor_manager.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    ordinary = acquire(successor_manager, workspace="workspace-b")
    with pytest.raises(ProbeLeaseError) as not_claimed:
        ordinary.consume_external_handoff(ticket)
    assert not_claimed.value.code == "PROBE_LEASE_LOST"
    ordinary.release()

    with pytest.raises(ProbeLeaseError) as invalid_ticket:
        manager(data_root, OWNER).acquire(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43124/health",
            handoff_ticket="invalid",
        )
    assert invalid_ticket.value.code == "PROBE_LEASE_INVALID"


def test_late_heartbeat_cannot_overwrite_external_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import stm32_toolkit.probe.lease as lease_module

    lease = acquire(manager(tmp_path / "data", OWNER))
    ticket = "9a" * 32
    entered = threading.Event()
    release_write = threading.Event()
    reserve_finished = threading.Event()
    errors: list[BaseException] = []
    real_write = lease_module._write_record_path

    def phased_write(path: Path, record: dict[str, object]) -> None:
        if record.get("heartbeatAtUtc") == "2026-08-07T12:00:01.000000Z":
            entered.set()
            release_write.wait(5)
        real_write(path, record)

    monkeypatch.setattr(lease_module, "_write_record_path", phased_write)

    def heartbeat() -> None:
        try:
            lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))
        except BaseException as error:
            errors.append(error)

    def reserve() -> None:
        try:
            lease.reserve_external_handoff(ticket)
        except BaseException as error:
            errors.append(error)
        finally:
            reserve_finished.set()

    heartbeat_thread = threading.Thread(target=heartbeat)
    reserve_thread = threading.Thread(target=reserve)
    heartbeat_thread.start()
    assert entered.wait(2)
    reserve_thread.start()
    reserve_was_serialized = not reserve_finished.wait(0.2)
    release_write.set()
    heartbeat_thread.join(2)
    reserve_thread.join(2)
    try:
        assert reserve_was_serialized
        assert errors == []
        record = json.loads(lease.record_path.read_text(encoding="utf-8"))
        assert record["state"] == "externally-owned"
        assert record["ticketSha256"] == __import__("hashlib").sha256(
            ticket.encode("ascii")
        ).hexdigest()
    finally:
        release_write.set()
        if not lease._released:
            lease.release()


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
        ("protocol", "stm32-toolkit-probe/1"),
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


def test_truncated_owner_record_is_never_reclaimed_or_overwritten(tmp_path: Path):
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    path = successor.record_path("probe-123")
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"schemaVersion":1')

    with pytest.raises(ProbeLeaseError) as error:
        acquire(successor, workspace="workspace-b")

    assert error.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert path.read_bytes() == b'{"schemaVersion":1'


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("consumedTicketSha256", "not-a-ticket-digest"),
        ("consumedProbeId", "probe/unsafe"),
        ("consumedWorkspaceId", "workspace unsafe"),
        ("consumedSessionId", "session unsafe"),
    ],
)
def test_invalid_persisted_handoff_tombstone_is_refused_without_reclaim(
    tmp_path: Path, field: str, value: str
):
    """A nested recovery record cannot be used to mint a new lease."""
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None},
        health=False,
    )
    record = stale_record()
    record["consumedTicketSha256"] = "ab" * 32
    record[field] = value
    path = write_stale_record(successor, record)
    before = path.read_bytes()

    with pytest.raises(ProbeLeaseError) as failure:
        acquire(successor, workspace="workspace-b")

    assert failure.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert failure.value.message == "Consumed probe handoff recovery evidence is invalid"
    assert path.read_bytes() == before


def test_oversized_persisted_owner_record_is_refused_without_reclaim(tmp_path: Path):
    successor = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None},
        health=False,
    )
    path = successor.record_path("probe-123")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b'{"state":"active","padding":"' + (b"x" * 16_384) + b'"}'
    path.write_bytes(raw)

    with pytest.raises(ProbeLeaseError) as failure:
        acquire(successor, workspace="workspace-b")

    assert failure.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert failure.value.message == "Probe registry record is invalid"
    assert path.read_bytes() == raw


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


def test_public_acquire_naive_utc_clock_fails_before_record_write(tmp_path: Path):
    data_root = tmp_path / "data"
    naive_manager = manager(
        data_root,
        OWNER,
        now=datetime(2026, 8, 7, 12, 0, 0),
    )
    record_path = naive_manager.record_path("probe-123")

    with pytest.raises(
        ValueError,
        match="^UTC clock must return a timezone-aware datetime$",
    ):
        acquire(naive_manager)

    assert not record_path.exists()
    assert not list(record_path.parent.glob(f".{record_path.name}.*.tmp"))

    lease = acquire(manager(data_root, OWNER, now=NOW))
    try:
        lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))
    finally:
        lease.release()
    assert json.loads(record_path.read_text(encoding="utf-8"))["state"] == (
        "released"
    )
    assert not list(record_path.parent.glob(f".{record_path.name}.*.tmp"))


def test_public_heartbeat_naive_utc_clock_preserves_active_record(tmp_path: Path):
    lease = acquire(manager(tmp_path / "data", OWNER, now=NOW))
    try:
        record_path = lease.record_path
        before = record_path.read_bytes()
        temporary_before = sorted(
            path.name
            for path in record_path.parent.glob(f".{record_path.name}.*.tmp")
        )

        with pytest.raises(
            ValueError,
            match="^UTC clock must return a timezone-aware datetime$",
        ):
            lease.heartbeat(utc_now=lambda: datetime(2026, 8, 7, 12, 0, 0))

        assert record_path.read_bytes() == before
        assert json.loads(before.decode("utf-8"))["state"] == "active"
        assert sorted(
            path.name
            for path in record_path.parent.glob(f".{record_path.name}.*.tmp")
        ) == temporary_before

        lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))
        updated = json.loads(record_path.read_text(encoding="utf-8"))
        assert updated["state"] == "active"
        assert updated["leaseId"] == lease.lease_id
        assert updated["heartbeatAtUtc"] == "2026-08-07T12:00:01.000000Z"
    finally:
        lease.release()
    assert json.loads(record_path.read_text(encoding="utf-8"))["state"] == (
        "released"
    )
    assert not list(record_path.parent.glob(f".{record_path.name}.*.tmp"))


def test_released_handoff_owner_cannot_heartbeat_after_settlement(tmp_path: Path):
    data_root = tmp_path / "data"
    ticket = "bc" * 32
    owner = acquire(manager(data_root, OWNER))
    owner.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))
    owner.reserve_external_handoff(ticket)
    owner.release()
    reservation = owner.record_path.read_bytes()
    assert json.loads(reservation.decode("utf-8"))["state"] == "externally-owned"

    with pytest.raises(ProbeLeaseError) as stale_heartbeat:
        owner.heartbeat(utc_now=lambda: NOW + timedelta(seconds=2))
    assert stale_heartbeat.value.code == "PROBE_LEASE_LOST"
    assert owner.record_path.read_bytes() == reservation

    successor_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
    )
    successor = successor_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    successor.consume_external_handoff(ticket)
    successor.release()
    assert successor_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert successor_manager.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert json.loads(owner.record_path.read_text(encoding="utf-8"))["state"] == (
        "released"
    )


def test_heartbeat_replace_failure_preserves_record_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import stm32_toolkit.probe.lease as lease_module

    lease = acquire(manager(tmp_path / "data", OWNER, now=NOW))
    record_path = lease.record_path
    before = record_path.read_bytes()

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("registry replace failed")

    monkeypatch.setattr(lease_module.os, "replace", fail_replace)
    with pytest.raises(ProbeLeaseError) as failure:
        lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))

    assert failure.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert record_path.read_bytes() == before
    assert not list(record_path.parent.glob(f".{record_path.name}.*.tmp"))

    monkeypatch.undo()
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


def test_real_crashed_owner_releases_guard_and_allows_safe_reclaim(tmp_path: Path):
    data_root = tmp_path / "data"
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import os
import sys
from pathlib import Path
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel

lease = ProbeLeaseManager(Path(sys.argv[1])).acquire(
    probe_id="probe-crash",
    workspace_id="workspace-crashed",
    session_id="session-crashed",
    operation_level=OperationLevel.OBSERVE,
    health_url="http://127.0.0.1:43125/health",
)
print(lease.lease_id, flush=True)
os._exit(0)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(data_root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    crashed_lease_id = stdout.strip()
    assert crashed_lease_id.startswith("lease-")

    successor_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={process.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    successor = successor_manager.acquire(
        probe_id="probe-crash",
        workspace_id="workspace-successor",
        session_id="session-successor",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43126/health",
    )
    try:
        assert successor.lease_id != crashed_lease_id
        assert successor.owner.workspace_id == "workspace-successor"
    finally:
        successor.release()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("probe_id", "probe/unsafe", id="probe-id"),
        pytest.param("workspace_id", "workspace unsafe", id="workspace-id"),
        pytest.param("session_id", "session unsafe", id="session-id"),
    ],
)
def test_public_acquire_rejects_invalid_identifiers_before_registry(
    tmp_path: Path, field: str, value: str
) -> None:
    data_root = tmp_path / "data"
    manager_ = manager(data_root, OWNER)
    arguments: dict[str, object] = {
        "probe_id": "probe-123",
        "workspace_id": "workspace-a",
        "session_id": "session-a",
        "operation_level": OperationLevel.OBSERVE,
        "health_url": "http://127.0.0.1:43123/health",
    }
    arguments[field] = value

    with pytest.raises(ProbeLeaseError) as error:
        manager_.acquire(**arguments)

    assert error.value.code == "PROBE_LEASE_INVALID"
    assert error.value.message == f"{field} is not a portable identifier"
    assert not data_root.exists()


def test_public_acquire_treats_empty_persisted_record_as_missing(tmp_path: Path):
    data_root = tmp_path / "data"
    successor_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    path = successor_manager.record_path("probe-123")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    unrelated = path.parent / "unrelated.bin"
    unrelated.write_bytes(b"preserve")
    unrelated_before = unrelated.read_bytes()

    lease = acquire(successor_manager, workspace="workspace-b")
    try:
        assert isinstance(lease, ProbeLease)
        active = json.loads(path.read_text(encoding="utf-8"))
        assert active["state"] == "active"
        assert active["pid"] == SUCCESSOR.pid
        assert active["workspaceId"] == "workspace-b"
    finally:
        lease.release()

    released = json.loads(path.read_text(encoding="utf-8"))
    assert released["state"] == "released"
    assert released["leaseId"] == lease.lease_id
    assert unrelated.read_bytes() == unrelated_before


def test_public_acquire_rejects_non_dict_persisted_record_without_rewrite(
    tmp_path: Path,
):
    successor_manager = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    path = successor_manager.record_path("probe-123")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"[]"
    path.write_bytes(raw)

    with pytest.raises(ProbeLeaseError) as error:
        acquire(successor_manager, workspace="workspace-b")

    assert error.value.code == "PROBE_REGISTRY_UNAVAILABLE"
    assert error.value.message == "Probe registry record is invalid"
    assert path.read_bytes() == raw


def test_public_acquire_rejects_handoff_ticket_on_stale_active_record(
    tmp_path: Path,
):
    successor_manager = manager(
        tmp_path / "data",
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    path = write_stale_record(successor_manager, stale_record())
    before = path.read_bytes()

    with pytest.raises(ProbeBusyError) as error:
        successor_manager.acquire(
            probe_id="probe-123",
            workspace_id="workspace-b",
            session_id="session-a",
            operation_level=OperationLevel.OBSERVE,
            health_url="http://127.0.0.1:43123/health",
            handoff_ticket="ab" * 32,
        )

    assert error.value.code == "PROBE_BUSY"
    assert error.value.message == "The selected probe is owned by another session"
    assert error.value.owner.workspace_id == "workspace-a"
    assert path.read_bytes() == before


def test_public_acquire_lock_held_invalid_state_preserves_bytes_before_release(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    owner = acquire(manager(data_root, OWNER))
    path = owner.record_path
    active_before = path.read_bytes()
    invalid_record = json.loads(active_before.decode("utf-8"))
    invalid_record["state"] = "invalid-state"
    invalid_bytes = json.dumps(
        invalid_record, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    contender = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )

    try:
        path.write_bytes(invalid_bytes)
        before = path.read_bytes()
        with pytest.raises(ProbeLeaseError) as error:
            acquire(contender, workspace="workspace-b")

        assert error.value.code == "PROBE_REGISTRY_UNAVAILABLE"
        assert error.value.message == "Probe owner record is unavailable"
        assert path.read_bytes() == before
    finally:
        path.write_bytes(active_before)
        owner.release()

    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "released"


def test_public_heartbeat_rejects_identity_tamper_without_rewrite(tmp_path: Path):
    lease = acquire(manager(tmp_path / "data", OWNER))
    path = lease.record_path

    try:
        tampered_record = json.loads(path.read_text(encoding="utf-8"))
        tampered_record["pid"] = SUCCESSOR.pid
        tampered_record["processStartId"] = SUCCESSOR.process_start_id
        tampered_record["bootId"] = SUCCESSOR.boot_id
        tampered_bytes = json.dumps(
            tampered_record, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        path.write_bytes(tampered_bytes)
        before = path.read_bytes()

        with pytest.raises(ProbeLeaseError) as error:
            lease.heartbeat(utc_now=lambda: NOW + timedelta(seconds=1))

        assert error.value.code == "PROBE_LEASE_LOST"
        assert error.value.message == "Probe lease ownership no longer matches"
        assert path.read_bytes() == before
    finally:
        lease.release()


@pytest.mark.parametrize(
    ("action", "workspace_id", "ticket"),
    [
        pytest.param(
            "consume",
            "workspace-a",
            "short",
            id="consume-short-ticket",
        ),
        pytest.param(
            "finalize",
            "workspace unsafe",
            "cd" * 32,
            id="finalize-unsafe-workspace",
        ),
        pytest.param(
            "finalize",
            "workspace-a",
            "short",
            id="finalize-short-ticket",
        ),
    ],
)
def test_public_handoff_rejects_invalid_transition_inputs_without_write(
    tmp_path: Path, action: str, workspace_id: str, ticket: str
) -> None:
    data_root = tmp_path / "data"
    owner_manager = manager(data_root, OWNER)
    lease = acquire(owner_manager)
    before = lease.record_path.read_bytes()

    try:
        with pytest.raises(ProbeLeaseError) as error:
            if action == "consume":
                lease.consume_external_handoff(ticket)
            else:
                owner_manager.finalize_consumed_handoff(
                    probe_id="probe-123",
                    workspace_id=workspace_id,
                    session_id="session-a",
                    ticket=ticket,
                )

        assert error.value.code == "PROBE_LEASE_INVALID"
        if action == "consume":
            assert error.value.message == "External handoff ticket is invalid"
        else:
            assert error.value.message == "External handoff identity is invalid"
        assert lease.record_path.read_bytes() == before
    finally:
        lease.release()


def test_public_handoff_settlement_rejects_wrong_order_and_finishes_once(
    tmp_path: Path,
):
    data_root = tmp_path / "data"
    ticket = "ef" * 32
    owner = acquire(manager(data_root, OWNER))
    try:
        owner.reserve_external_handoff(ticket)
    finally:
        owner.release()

    claimant_manager = manager(
        data_root,
        SUCCESSOR,
        inspected={OWNER.pid: None, SUCCESSOR.pid: SUCCESSOR},
        health=False,
    )
    claimant = claimant_manager.acquire(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:43124/health",
        handoff_ticket=ticket,
    )
    try:
        claimant.consume_external_handoff(ticket)
    finally:
        claimant.release()

    path = claimant.record_path
    consumed_before = path.read_bytes()
    third_identity = ProcessIdentity(4300, "start-4300", "boot-a")
    third_manager = manager(
        data_root,
        third_identity,
        inspected={SUCCESSOR.pid: None, third_identity.pid: third_identity},
        health=False,
    )
    with pytest.raises(ProbeBusyError) as busy:
        acquire(third_manager, workspace="workspace-b")
    assert busy.value.code == "PROBE_BUSY"
    assert busy.value.message == "The selected probe is owned by another session"
    assert path.read_bytes() == consumed_before

    assert (
        claimant_manager.acknowledge_consumed_handoff(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            ticket=ticket,
        )
        is False
    )
    assert path.read_bytes() == consumed_before

    assert (
        claimant_manager.finalize_consumed_handoff(
            probe_id="probe-123",
            workspace_id="workspace-b",
            session_id="session-a",
            ticket=ticket,
        )
        is False
    )
    assert path.read_bytes() == consumed_before

    assert claimant_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    finalized = path.read_bytes()
    assert json.loads(finalized.decode("utf-8"))["state"] == "handoff-finalized"
    assert claimant_manager.finalize_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    assert path.read_bytes() == finalized

    assert claimant_manager.acknowledge_consumed_handoff(
        probe_id="probe-123",
        workspace_id="workspace-a",
        session_id="session-a",
        ticket=ticket,
    )
    released = json.loads(path.read_text(encoding="utf-8"))
    assert released["state"] == "released"
    assert released["consumedTicketSha256"]

    successor = acquire(claimant_manager, workspace="workspace-b")
    try:
        assert successor.owner.workspace_id == "workspace-b"
    finally:
        successor.release()

    path.unlink()
    assert not path.exists()
    assert (
        claimant_manager.finalize_consumed_handoff(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            ticket=ticket,
        )
        is False
    )
    assert not path.exists()
