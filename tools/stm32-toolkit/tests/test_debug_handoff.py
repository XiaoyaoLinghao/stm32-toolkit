from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import atomic_write_json, utc_now_rfc3339
from stm32_toolkit.probe.backend import ProbeAttachmentEvidence
from stm32_toolkit.probe.handoff import (
    CortexDebugAttachContract,
    DebugHandoffRequest,
    HandoffRestore,
    HandoffTicket,
    begin_debug_handoff,
    end_debug_handoff,
)
from stm32_toolkit.probe.model import OperationLevel
from test_build_runner import prepare_project
from test_flash import _elf_with_flash_segment, _publish_current_debug_build


STATE_NAME = "debug-handoff.json"


class FakeLeaseManager:
    def __init__(self, path: Path, data_root: Path) -> None:
        self.path = path
        self.data_root = data_root

    def record_path(self, probe_id: str) -> Path:
        assert probe_id == "probe-123"
        return self.path


class FakeSupervisor:
    def __init__(self, project: Path, session_root: Path) -> None:
        self._config = SimpleNamespace(
            probe_id="probe-123",
            workspace_id="workspace-a",
            session_id="session-a",
            operation_level=OperationLevel.MODIFY,
            session_root=session_root,
            project_root=project,
        )
        self._lease_manager = FakeLeaseManager(
            session_root / "probe.lock", session_root.parents[2]
        )
        self.endpoint = self._new_endpoint()
        self.start_calls = 0
        self.stop_calls = 0
        self.drain_calls = 0
        self.modifications_allowed = True
        self.modify_attempts: list[bool] = []
        self.start_error: BaseException | None = None
        self.stop_error: BaseException | None = None
        self.stop_error_after_cleanup: BaseException | None = None
        self.drain_error: BaseException | None = None
        session_root.mkdir(parents=True, exist_ok=True)
        self._activate()

    def _new_endpoint(self):
        return SimpleNamespace(
            protocol="stm32-toolkit-probe-v1",
            toolkit_version=__version__,
            host="127.0.0.1",
            port=43123,
            token="11" * 32,
            workspace_id="workspace-a",
            session_id="session-a",
            probe_id="probe-123",
            operation_level=OperationLevel.MODIFY,
            lease_id="lease-a",
            record_path=self._config.session_root / "probe-endpoint.json",
        )

    def _activate(self) -> None:
        self.endpoint = self._new_endpoint()
        self.endpoint.record_path.write_text("endpoint", encoding="utf-8")
        atomic_write_json(
            self._lease_manager.path,
            {"schemaVersion": 1, "state": "active", "leaseId": "lease-a"},
        )

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error
        old = self.endpoint
        self.endpoint = None
        if old is not None:
            old.record_path.unlink(missing_ok=True)
        atomic_write_json(
            self._lease_manager.path,
            {"schemaVersion": 1, "state": "released", "leaseId": "lease-a"},
        )
        if self.stop_error_after_cleanup is not None:
            raise self.stop_error_after_cleanup

    async def start(self):
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        if self.endpoint is None:
            self._activate()
        return self.endpoint

    async def drain_modifications(self) -> None:
        self.drain_calls += 1
        if self.drain_error is not None:
            raise self.drain_error
        self.modifications_allowed = False

    def attempt_modify(self) -> None:
        self.modify_attempts.append(self.modifications_allowed)


class FakeClient:
    def __init__(self, endpoint: object, image: bytes) -> None:
        self.endpoint = endpoint
        self.image = image
        self.events: list[tuple[object, ...]] = []
        self.read_error: BaseException | None = None
        self.after_read: object | None = None
        self.resolved_part = "STM32F407VG"

    async def attach(self, probe_id: str, target: str) -> ProbeAttachmentEvidence:
        self.events.append(("attach", probe_id, target))
        return ProbeAttachmentEvidence(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number=self.resolved_part,
            core_count=1,
        )

    async def read_memory(self, address: int, length: int) -> bytes:
        self.events.append(("read", address, length))
        if self.read_error is not None:
            raise self.read_error
        if callable(self.after_read):
            self.after_read()
        offset = address - 0x08000000
        return self.image[offset : offset + length]


def _flash_result(identity: dict[str, object]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "status": "success",
        "code": "OK",
        "toolkitVersion": __version__,
        "buildId": identity["buildId"],
        "elfSha256": identity["elfSha256"],
        "elfSize": identity["elfSize"],
        "targetDevice": identity["targetDevice"],
        "debugTarget": "stm32f407vg",
        "probeId": "probe-123",
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "verifiedBytes": 320,
        "backendBytesProgrammed": None,
        "backendSectorsProgrammed": None,
        "startedAtUtc": utc_now_rfc3339(),
        "finishedAtUtc": utc_now_rfc3339(),
        "flashResultPath": "artifacts/migration/flash-result.json",
        "elfPath": "build/arm-debug/firmware.elf",
        "gitHead": identity["gitHead"],
        "gitDirty": identity["gitDirty"],
        "inputSnapshotSha256": identity["inputSnapshotSha256"],
        "operationLevel": "modify",
        "authorized": True,
    }


@pytest.fixture
def handoff_env(tmp_path: Path):
    project = prepare_project(tmp_path / "project")
    identity = _publish_current_debug_build(project)
    atomic_write_json(
        project / "artifacts" / "migration" / "flash-result.json",
        _flash_result(identity),
    )
    session_root = tmp_path / "plugin-data" / "projects" / "workspace-a" / "session-a"
    supervisor = FakeSupervisor(project, session_root)
    client = FakeClient(supervisor.endpoint, _elf_with_flash_segment()[84 : 84 + 320])
    request = DebugHandoffRequest(
        project_root=project,
        expected_build_id=str(identity["buildId"]),
        expected_elf_sha256=str(identity["elfSha256"]),
        authorized=True,
        previous_watch_selection=("counter", "device.state"),
    )
    return project, identity, session_root, supervisor, client, request


def _state(session_root: Path) -> dict[str, object]:
    return json.loads((session_root / STATE_NAME).read_text(encoding="utf-8"))


def test_cortex_debug_contract_is_data_only_exact_attach_configuration():
    contract = CortexDebugAttachContract(
        target="stm32f407vg",
        executable="build/arm-debug/firmware.elf",
        serial_number="probe-123",
    )
    assert contract.to_dict() == {
        "servertype": "pyocd",
        "request": "attach",
        "target": "stm32f407vg",
        "serialNumber": "probe-123",
        "executable": "${workspaceFolder}/build/arm-debug/firmware.elf",
    }


def test_cortex_debug_contract_selects_exact_probe_when_two_are_present():
    first = CortexDebugAttachContract(
        "stm32f407vg", "build/arm-debug/firmware.elf", "probe-a"
    )
    second = CortexDebugAttachContract(
        "stm32f407vg", "build/arm-debug/firmware.elf", "probe-b"
    )
    assert first.to_dict()["serialNumber"] == "probe-a"
    assert second.to_dict()["serialNumber"] == "probe-b"
    assert first.to_dict() != second.to_dict()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"servertype": "openocd"},
        {"request": "launch"},
        {"target": "bad target"},
        {"serial_number": "bad probe"},
        {"executable": "../firmware.elf"},
        {"executable": "C:/firmware.elf"},
    ],
)
def test_cortex_debug_contract_rejects_non_attach_or_nonportable_values(kwargs):
    fields = {
        "target": "stm32f407vg",
        "executable": "build/arm-debug/firmware.elf",
        "serial_number": "probe-123",
        **kwargs,
    }
    with pytest.raises(ValueError):
        CortexDebugAttachContract(**fields)


def test_cortex_debug_contract_rejects_backslash_and_control_paths():
    for executable in ("build\\firmware.elf", "build/firmware\n.elf"):
        with pytest.raises(ValueError):
            CortexDebugAttachContract("stm32f407vg", executable, "probe-123")


@pytest.mark.parametrize("authorized", [False, "true", 1, None])
def test_begin_requires_exact_true_without_stopping(handoff_env, authorized):
    *_, supervisor, client, request = handoff_env
    request = DebugHandoffRequest(
        request.project_root,
        request.expected_build_id,
        request.expected_elf_sha256,
        authorized,  # type: ignore[arg-type]
        request.previous_watch_selection,
    )
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.ok is False
    assert result.code == "AUTHORIZATION_REQUIRED"
    assert supervisor.stop_calls == 0


@pytest.mark.parametrize(
    "replacement",
    [
        object(),
        DebugHandoffRequest(Path("missing"), "0" * 64, "1" * 64, True, ()),
        DebugHandoffRequest(Path.cwd(), "bad", "1" * 64, True, ()),
        DebugHandoffRequest(Path.cwd(), "0" * 64, "bad", True, ()),
        DebugHandoffRequest(Path.cwd(), "0" * 64, "1" * 64, True, ("",)),
        DebugHandoffRequest(Path.cwd(), "0" * 64, "1" * 64, True, ["x"]),  # type: ignore[arg-type]
    ],
)
def test_begin_rejects_malformed_request_before_lifecycle(
    handoff_env, replacement
):
    _, _, _, supervisor, client, _ = handoff_env
    result = asyncio.run(begin_debug_handoff(replacement, supervisor, client))
    assert result.code == "HANDOFF_REQUEST_INVALID"
    assert supervisor.stop_calls == 0


def test_begin_rejects_non_path_and_regular_file_roots(handoff_env, tmp_path: Path):
    _, _, _, supervisor, client, request = handoff_env
    file_root = tmp_path / "not-a-project"
    file_root.write_text("x", encoding="utf-8")
    for root in ("project", file_root):
        malformed = DebugHandoffRequest(
            root,  # type: ignore[arg-type]
            request.expected_build_id,
            request.expected_elf_sha256,
            True,
            (),
        )
        result = asyncio.run(begin_debug_handoff(malformed, supervisor, client))
        assert result.code == "HANDOFF_REQUEST_INVALID"


def test_begin_persists_paused_stops_releases_then_marks_external(handoff_env):
    _, identity, session_root, supervisor, client, request = handoff_env
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.ok is True
    ticket = result.data
    assert ticket is not None
    assert len(ticket.ticket_id) == 64
    assert supervisor.stop_calls == 1
    assert supervisor.endpoint is None
    assert not (session_root / "probe-endpoint.json").exists()
    document = _state(session_root)
    assert document == {
        "schemaVersion": 1,
        "toolkitVersion": __version__,
        "state": "externally-owned",
        "ticketId": ticket.ticket_id,
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "probeId": "probe-123",
        "leaseId": "lease-a",
        "target": "stm32f407vg",
        "buildId": identity["buildId"],
        "elfSha256": identity["elfSha256"],
        "previousWatchSelection": ["counter", "device.state"],
        "issuedAtUtc": document["issuedAtUtc"],
    }
    if os.name != "nt":
        assert stat.S_IMODE((session_root / STATE_NAME).stat().st_mode) == 0o600
    assert [event[0] for event in client.events] == ["attach", "read"]
    assert ticket.ticket_id not in repr(ticket)


def test_begin_drains_modifications_before_final_target_readback(handoff_env):
    _, _, _, supervisor, client, request = handoff_env
    client.after_read = supervisor.attempt_modify

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert result.ok is True
    assert supervisor.drain_calls == 1
    assert supervisor.modify_attempts == [False]
    assert supervisor.stop_calls == 1


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("protocol", "other-protocol"),
        ("toolkit_version", "99.0.0"),
        ("host", "127.0.0.2"),
        ("port", 43124),
        ("token", "22" * 32),
        ("workspace_id", "workspace-other"),
        ("session_id", "session-other"),
        ("lease_id", "lease-other"),
        ("probe_id", "probe-other"),
        ("operation_level", OperationLevel.OBSERVE),
    ],
)
def test_begin_rejects_client_not_bound_to_supervisor_endpoint(
    handoff_env, field: str, replacement: object
):
    _, _, session_root, supervisor, client, request = handoff_env
    client.endpoint = SimpleNamespace(**vars(supervisor.endpoint))
    setattr(client.endpoint, field, replacement)

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert result.code == "HANDOFF_CLIENT_MISMATCH"
    assert supervisor.stop_calls == 0
    assert client.events == []
    assert not (session_root / STATE_NAME).exists()


def test_begin_drain_failure_is_stable_and_does_not_touch_target(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.drain_error = RuntimeError("private drain detail")

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert result.code == "HANDOFF_DRAIN_FAILED"
    assert "private drain detail" not in json.dumps(result.to_dict())
    assert supervisor.stop_calls == 0
    assert client.events == []
    assert not (session_root / STATE_NAME).exists()


def test_begin_drain_cancellation_propagates_without_state(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.drain_error = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert supervisor.stop_calls == 0
    assert client.events == []
    assert not (session_root / STATE_NAME).exists()


def test_begin_stop_cancellation_finalizes_external_state_before_propagating(
    handoff_env,
):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.stop_error_after_cleanup = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert supervisor.endpoint is None
    assert _state(session_root)["state"] == "externally-owned"
    assert json.loads(supervisor._lease_manager.path.read_text(encoding="utf-8"))["state"] == "released"


def test_begin_cleanup_failure_after_release_stays_paused(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.stop_error_after_cleanup = RuntimeError("private cleanup detail")

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert result.code == "HANDOFF_STOP_FAILED"
    assert "private cleanup detail" not in json.dumps(result.to_dict())
    assert supervisor.endpoint is None
    assert _state(session_root)["state"] == "paused-for-debug"
    retry = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert retry.code == "HANDOFF_REACQUIRE_REQUIRED"


def test_probe_package_exports_handoff_contracts() -> None:
    import stm32_toolkit.probe as probe

    assert probe.CortexDebugAttachContract is CortexDebugAttachContract
    assert probe.DebugHandoffRequest is DebugHandoffRequest
    assert probe.HandoffRestore is HandoffRestore
    assert probe.HandoffTicket is HandoffTicket
    assert probe.begin_debug_handoff is begin_debug_handoff
    assert probe.end_debug_handoff is end_debug_handoff


def test_idempotent_begin_fails_if_toolkit_or_another_owner_reacquired(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    first = asyncio.run(begin_debug_handoff(request, supervisor, client))
    supervisor._activate()
    second = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert second.code == "HANDOFF_STOP_FAILED"
    assert second.data is None
    assert _state(session_root)["ticketId"] == first.data.ticket_id


def test_begin_rejects_missing_or_wrong_flash_evidence_before_stop(handoff_env):
    project, _, _, supervisor, client, request = handoff_env
    path = project / "artifacts" / "migration" / "flash-result.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["probeId"] = "probe-other"
    atomic_write_json(path, document)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_FLASH_MISMATCH"
    assert supervisor.stop_calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("elfSize", 1),
        ("verifiedBytes", 1),
        ("gitHead", "f" * 40),
        ("gitDirty", "false"),
        ("inputSnapshotSha256", "f" * 64),
        ("startedAtUtc", "yesterday"),
        ("finishedAtUtc", "tomorrow"),
        ("backendBytesProgrammed", True),
        ("backendSectorsProgrammed", -1),
    ],
)
def test_begin_rejects_incomplete_or_mistyped_flash_proof(
    handoff_env, field: str, value: object
):
    project, _, _, supervisor, client, request = handoff_env
    path = project / "artifacts" / "migration" / "flash-result.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    atomic_write_json(path, document)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_FLASH_MISMATCH"
    assert supervisor.stop_calls == 0
    assert client.events == []


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schemaVersion":1,"schemaVersion":1}',
        b'{"schemaVersion":NaN}',
        b'[]',
    ],
)
def test_begin_rejects_duplicate_nonfinite_or_nonobject_flash_result(
    handoff_env, raw: bytes
):
    project, _, _, supervisor, client, request = handoff_env
    (project / "artifacts" / "migration" / "flash-result.json").write_bytes(raw)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_FLASH_REQUIRED"
    assert client.events == []


def test_begin_rejects_missing_flash_result_before_target_access(handoff_env):
    project, _, _, supervisor, client, request = handoff_env
    (project / "artifacts" / "migration" / "flash-result.json").unlink()
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_FLASH_REQUIRED"
    assert client.events == []
    assert supervisor.stop_calls == 0


def test_begin_rejects_wrong_target_readback_without_persisting_state(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    client.resolved_part = "STM32F429ZI"
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_TARGET_MISMATCH"
    assert not (session_root / STATE_NAME).exists()
    assert supervisor.stop_calls == 0


def test_begin_stop_failure_remains_paused_and_retryable(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.stop_error = RuntimeError("private stop detail")
    first = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert first.code == "HANDOFF_STOP_FAILED"
    paused = _state(session_root)
    assert paused["state"] == "paused-for-debug"
    assert "private stop detail" not in json.dumps(first.to_dict())

    supervisor.stop_error = None
    second = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert second.ok is True
    assert second.data.ticket_id == paused["ticketId"]
    assert _state(session_root)["state"] == "externally-owned"


def test_end_reacquires_revalidates_and_consumes_one_time_ticket(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    begun = asyncio.run(begin_debug_handoff(request, supervisor, client))
    ticket = begun.data
    returned_client: list[FakeClient] = []

    def factory(endpoint: object) -> FakeClient:
        value = FakeClient(endpoint, client.image)
        returned_client.append(value)
        return value

    ended = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))
    assert ended.ok is True
    assert ended.data.to_dict() == {
        "previousWatchSelection": ["counter", "device.state"]
    }
    assert supervisor.start_calls == 1
    assert [event[0] for event in returned_client[0].events] == ["attach", "read"]
    consumed = _state(session_root)
    assert consumed["state"] == "observing"
    assert consumed["ticketId"] is None
    assert consumed["previousWatchSelection"] == []

    replay = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))
    assert replay.ok is False
    assert replay.code == "HANDOFF_TICKET_INVALID"
    assert supervisor.start_calls == 1


def test_end_rejects_factory_client_bound_to_another_endpoint(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data

    def wrong_factory(endpoint: object) -> FakeClient:
        wrong_endpoint = SimpleNamespace(**vars(endpoint))
        wrong_endpoint.token = "22" * 32
        return FakeClient(wrong_endpoint, client.image)

    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, wrong_factory)
    )

    assert result.code == "HANDOFF_CLIENT_MISMATCH"
    assert _state(session_root)["state"] == "reacquiring"
    assert _state(session_root)["ticketId"] == ticket.ticket_id


def test_end_wrong_ticket_or_binding_does_not_start(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    wrong = asyncio.run(end_debug_handoff("0" * 64, supervisor, lambda _: client))
    assert wrong.code == "HANDOFF_TICKET_INVALID"
    assert supervisor.start_calls == 0

    document = _state(session_root)
    document["workspaceId"] = "workspace-other"
    atomic_write_json(session_root / STATE_NAME, document)
    forged = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, lambda _: client))
    assert forged.code == "HANDOFF_TICKET_INVALID"
    assert supervisor.start_calls == 0


@pytest.mark.parametrize("ticket", [None, "short", "G" * 64, 1])
def test_end_rejects_malformed_opaque_ticket_before_start(handoff_env, ticket):
    *_, supervisor, client, _ = handoff_env
    result = asyncio.run(end_debug_handoff(ticket, supervisor, lambda _: client))
    assert result.code == "HANDOFF_TICKET_INVALID"
    assert supervisor.start_calls == 0


def test_end_start_or_readback_failure_stays_reacquiring_for_retry(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    supervisor.start_error = RuntimeError("private startup detail")
    first = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, lambda _: client))
    assert first.code == "HANDOFF_REACQUIRE_FAILED"
    assert _state(session_root)["state"] == "reacquiring"
    assert "private startup detail" not in json.dumps(first.to_dict())

    supervisor.start_error = None
    bad = FakeClient(supervisor._new_endpoint(), b"\x00" * len(client.image))
    second = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, lambda _: bad))
    assert second.code == "FLASH_VERIFY_FAILED"
    assert _state(session_root)["state"] == "reacquiring"

    third = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: FakeClient(endpoint, client.image)))
    assert third.ok is True
    assert _state(session_root)["state"] == "observing"


def test_process_restart_uses_persisted_state_not_python_object_identity(handoff_env):
    project, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    restarted = FakeSupervisor(project, session_root)
    restarted.endpoint = None
    (session_root / "probe-endpoint.json").unlink(missing_ok=True)
    atomic_write_json(
        restarted._lease_manager.path,
        {"schemaVersion": 1, "state": "released", "leaseId": "lease-a"},
    )
    result = asyncio.run(
        end_debug_handoff(
            ticket.ticket_id,
            restarted,
            lambda endpoint: FakeClient(endpoint, client.image),
        )
    )
    assert result.ok is True
    assert result.data.previous_watch_selection == ("counter", "device.state")


def test_corrupt_or_oversized_state_fails_closed_without_lifecycle_call(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    path = session_root / STATE_NAME
    path.write_bytes(b"{" + b"x" * 70_000)
    begin = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert begin.code == "HANDOFF_STATE_INVALID"
    assert supervisor.stop_calls == 0
    end = asyncio.run(end_debug_handoff("a" * 64, supervisor, lambda _: client))
    assert end.code == "HANDOFF_STATE_INVALID"
    assert supervisor.start_calls == 0


@pytest.mark.parametrize(
    "raw",
    [
        b'{"state":"externally-owned","state":"observing"}',
        b'{"schemaVersion":NaN}',
        b'[]',
        b'\xff',
    ],
)
def test_duplicate_nonfinite_or_nonobject_state_fails_closed(handoff_env, raw: bytes):
    _, _, session_root, supervisor, client, request = handoff_env
    (session_root / STATE_NAME).write_bytes(raw)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_INVALID"
    assert supervisor.stop_calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unexpected", 1),
        ("state", "paused-for-flash"),
        ("ticketId", "short"),
        ("workspaceId", "bad workspace"),
        ("buildId", "short"),
        ("issuedAtUtc", "invalid"),
        ("previousWatchSelection", [1]),
    ],
)
def test_every_corrupt_state_class_fails_closed(
    handoff_env, field: str, value: object
):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    document = _state(session_root)
    document[field] = value
    atomic_write_json(session_root / STATE_NAME, document)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_STATE_INVALID"
    assert supervisor.start_calls == 0


def test_corrupt_consumed_observing_state_fails_closed(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    document = _state(session_root)
    document["state"] = "observing"
    atomic_write_json(session_root / STATE_NAME, document)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_STATE_INVALID"


@pytest.mark.parametrize(
    "selection",
    [
        ["x"] * 129,
        ["x" * 513],
        ["x" * 512] * 33,
        ["watch\x00name"],
        ["watch\nname"],
    ],
)
def test_persisted_selection_reuses_request_bounds_and_character_policy(
    handoff_env, selection: list[str]
):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    document = _state(session_root)
    document["previousWatchSelection"] = selection
    atomic_write_json(session_root / STATE_NAME, document)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_STATE_INVALID"
    assert supervisor.start_calls == 0


def test_state_inspection_permission_failure_is_structured(handoff_env, monkeypatch):
    _, _, session_root, supervisor, client, request = handoff_env
    real_lstat = os.lstat

    def denied(path: object, *args, **kwargs):
        if Path(path).name == STATE_NAME:
            raise PermissionError("private state path")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", denied)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_UNAVAILABLE"
    assert "private state path" not in json.dumps(result.to_dict())


def test_guard_identity_swap_is_rejected_before_hardware_access(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    real_lstat = os.lstat

    def swapped(path: object, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if Path(path).name == ".debug-handoff.guard":
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=0,
                st_dev=result.st_dev,
                st_ino=result.st_ino + 1,
            )
        return result

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", swapped)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_INVALID"
    assert client.events == []


def test_guard_fstat_failure_closes_descriptor_and_is_structured(
    handoff_env, monkeypatch
):
    _, _, _, supervisor, client, request = handoff_env
    real_fstat = os.fstat
    real_close = os.close
    closes: list[int] = []

    def failed_fstat(descriptor: int):
        raise OSError("private fstat detail")

    def recorded_close(descriptor: int):
        closes.append(descriptor)
        return real_close(descriptor)

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.fstat", failed_fstat)
    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.close", recorded_close)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_UNAVAILABLE"
    assert closes


def test_guard_open_permission_failure_is_structured(handoff_env, monkeypatch):
    _, _, _, supervisor, client, request = handoff_env
    real_open = os.open

    def denied(path: object, flags: int, mode: int = 0o777):
        if Path(path).name == ".debug-handoff.guard":
            raise PermissionError("private guard path")
        return real_open(path, flags, mode)

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.open", denied)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_UNAVAILABLE"
    assert "private guard path" not in json.dumps(result.to_dict())


def test_state_swap_to_redirect_after_open_fails_closed(handoff_env, monkeypatch):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    state_path = session_root / STATE_NAME
    real_lstat = os.lstat
    state_lstats = 0

    def swapped(path: object, *args, **kwargs):
        nonlocal state_lstats
        result = real_lstat(path, *args, **kwargs)
        if Path(path) == state_path:
            state_lstats += 1
            if state_lstats >= 3:
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=0x400,
                    st_dev=result.st_dev,
                    st_ino=result.st_ino,
                )
        return result

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", swapped)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_STATE_INVALID"
    assert supervisor.start_calls == 0


def test_state_opened_and_named_identity_mismatch_fails_closed(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    state_path = session_root / STATE_NAME
    real_lstat = os.lstat
    state_lstats = 0

    def replaced(path: object, *args, **kwargs):
        nonlocal state_lstats
        result = real_lstat(path, *args, **kwargs)
        if Path(path) == state_path:
            state_lstats += 1
            if state_lstats >= 3:
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=0,
                    st_dev=result.st_dev,
                    st_ino=result.st_ino + 1,
                )
        return result

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", replaced)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_STATE_INVALID"


def test_state_parent_identity_change_after_open_fails_closed(
    handoff_env, monkeypatch: pytest.MonkeyPatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    first = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert first.ok is True
    state_path = session_root / STATE_NAME
    real_fstat = os.fstat
    real_lstat = os.lstat
    state_metadata = real_lstat(state_path)
    state_identity = (state_metadata.st_dev, state_metadata.st_ino)
    state_opened = False
    changed_paths: list[Path] = []

    def tracking_fstat(descriptor: int):
        nonlocal state_opened
        metadata = real_fstat(descriptor)
        state_opened = (metadata.st_dev, metadata.st_ino) == state_identity
        return metadata

    def changed_parent(path: object, *args, **kwargs):
        metadata = real_lstat(path, *args, **kwargs)
        if state_opened and Path(path) == session_root:
            changed_paths.append(Path(path))
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino + 1,
                st_file_attributes=getattr(metadata, "st_file_attributes", 0),
            )
        return metadata

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.fstat", tracking_fstat)
    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", changed_parent)

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_INVALID", (result.code, changed_paths)
    assert supervisor.start_calls == 0


def test_oversized_lease_release_record_cannot_publish_external_ownership(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    original_stop = supervisor.stop

    async def oversized_release() -> None:
        await original_stop()
        supervisor._lease_manager.path.write_bytes(b"{" + b"x" * 70_000)

    supervisor.stop = oversized_release
    real_read_text = Path.read_text
    read_text_paths: list[Path] = []

    def recorded_read_text(path: Path, *args, **kwargs):
        read_text_paths.append(path)
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", recorded_read_text)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STOP_FAILED"
    assert _state(session_root)["state"] == "paused-for-debug"
    assert supervisor._lease_manager.path not in read_text_paths


def test_lease_opened_and_named_identity_mismatch_blocks_external_state(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    lease_path = supervisor._lease_manager.path
    real_lstat = os.lstat
    lease_lstats = 0

    def replaced(path: object, *args, **kwargs):
        nonlocal lease_lstats
        result = real_lstat(path, *args, **kwargs)
        if Path(path) == lease_path:
            lease_lstats += 1
            if lease_lstats >= 2:
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=0,
                    st_dev=result.st_dev,
                    st_ino=result.st_ino + 1,
                )
        return result

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", replaced)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STOP_FAILED"
    assert _state(session_root)["state"] == "paused-for-debug"


def test_end_missing_configured_project_root_is_stable_supervisor_error(handoff_env):
    _, _, _, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    supervisor._config.project_root = request.project_root / "missing"
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_SUPERVISOR_INVALID"
    assert supervisor.start_calls == 0


def test_system_exit_is_never_converted_to_protocol_failure(handoff_env):
    _, _, _, supervisor, client, request = handoff_env

    async def exit_attach(probe: str, target: str):
        raise SystemExit(7)

    client.attach = exit_attach
    with pytest.raises(SystemExit, match="7"):
        asyncio.run(begin_debug_handoff(request, supervisor, client))


def test_concurrent_begin_is_serialized_and_returns_one_active_ticket(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env

    async def run_both():
        return await asyncio.gather(
            begin_debug_handoff(request, supervisor, client),
            begin_debug_handoff(request, supervisor, client),
        )

    first, second = asyncio.run(run_both())
    assert first.ok is True and second.ok is True
    assert first.data.ticket_id == second.data.ticket_id == _state(session_root)["ticketId"]
    assert supervisor.stop_calls == 1


def test_begin_cancellation_preserves_paused_state_for_retry(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    supervisor.stop_error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert _state(session_root)["state"] == "paused-for-debug"


def test_end_cancellation_preserves_reacquiring_state_for_retry(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    supervisor.start_error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
        )
    assert _state(session_root)["state"] == "reacquiring"


def test_concurrent_end_consumes_ticket_exactly_once(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data

    async def run_both():
        return await asyncio.gather(
            end_debug_handoff(
                ticket.ticket_id,
                supervisor,
                lambda endpoint: FakeClient(endpoint, client.image),
            ),
            end_debug_handoff(
                ticket.ticket_id,
                supervisor,
                lambda endpoint: FakeClient(endpoint, client.image),
            ),
        )

    first, second = asyncio.run(run_both())
    assert sorted((first.ok, second.ok)) == [False, True]
    assert {first.code, second.code} == {"OK", "HANDOFF_TICKET_INVALID"}
    assert supervisor.start_calls == 1
    assert _state(session_root)["state"] == "observing"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sessionId", "session-other"),
        ("probeId", "probe-other"),
        ("buildId", "1" * 64),
        ("elfSha256", "2" * 64),
        ("target", "stm32f429zi"),
    ],
)
def test_end_rejects_every_forged_ticket_binding_without_start(
    handoff_env, field: str, value: str
):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    document = _state(session_root)
    document[field] = value
    atomic_write_json(session_root / STATE_NAME, document)
    result = asyncio.run(
        end_debug_handoff(ticket.ticket_id, supervisor, lambda endpoint: client)
    )
    assert result.code == "HANDOFF_TICKET_INVALID"
    assert supervisor.start_calls == 0


def test_session_chain_redirect_is_rejected_before_read_or_lifecycle(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    real_lstat = os.lstat

    def redirected(path: object, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if Path(path) == session_root.parent:
            values = list(result)
            fake = SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=0x400,
            )
            return fake
        return result

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.lstat", redirected)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_INVALID"
    assert supervisor.stop_calls == 0
    assert client.events == []


def test_atomic_transition_failure_does_not_stop_service_or_publish_partial_state(
    handoff_env, monkeypatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    real_replace = os.replace

    def fail_state_replace(source: object, destination: object):
        if Path(destination).name == STATE_NAME:
            raise PermissionError("private path")
        return real_replace(source, destination)

    monkeypatch.setattr("stm32_toolkit.probe.handoff.os.replace", fail_state_replace)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_UNAVAILABLE"
    assert supervisor.stop_calls == 0
    assert not (session_root / STATE_NAME).exists()
    assert list(session_root.glob(".debug-handoff-*.tmp")) == []


def test_external_transition_write_failure_requires_reacquire_and_readback(
    handoff_env, monkeypatch: pytest.MonkeyPatch
):
    _, _, session_root, supervisor, client, request = handoff_env
    real_replace = os.replace
    state_replacements = 0

    def fail_second_state_replace(source: object, destination: object):
        nonlocal state_replacements
        if Path(destination).name == STATE_NAME:
            state_replacements += 1
            if state_replacements == 2:
                raise PermissionError("private path")
        return real_replace(source, destination)

    monkeypatch.setattr(
        "stm32_toolkit.probe.handoff.os.replace", fail_second_state_replace
    )
    failed = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert failed.code == "HANDOFF_STATE_UNAVAILABLE"
    assert supervisor.endpoint is None
    assert _state(session_root)["state"] == "paused-for-debug"

    blocked = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert blocked.code == "HANDOFF_REACQUIRE_REQUIRED"
    assert _state(session_root)["state"] == "paused-for-debug"

    asyncio.run(supervisor.start())
    client.image = b"\x00" * len(client.image)
    changed = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert changed.code == "FLASH_VERIFY_FAILED"
    assert supervisor.endpoint is not None
    assert _state(session_root)["state"] == "paused-for-debug"


def test_begin_conflicting_selection_does_not_replace_active_ticket(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    first = asyncio.run(begin_debug_handoff(request, supervisor, client))
    conflicting = DebugHandoffRequest(
        request.project_root,
        request.expected_build_id,
        request.expected_elf_sha256,
        True,
        ("other",),
    )
    second = asyncio.run(begin_debug_handoff(conflicting, supervisor, client))
    assert second.code == "HANDOFF_STATE_CONFLICT"
    assert _state(session_root)["ticketId"] == first.data.ticket_id


def test_begin_rejects_identity_change_or_inactive_supervisor(handoff_env):
    _, _, _, supervisor, client, request = handoff_env
    wrong = DebugHandoffRequest(
        request.project_root,
        "f" * 64,
        request.expected_elf_sha256,
        True,
        (),
    )
    identity = asyncio.run(begin_debug_handoff(wrong, supervisor, client))
    assert identity.code == "HANDOFF_IDENTITY_MISMATCH"
    supervisor.endpoint = None
    inactive = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert inactive.code == "HANDOFF_SUPERVISOR_INVALID"


def test_begin_rejects_invalid_endpoint_or_config_without_hardware(handoff_env):
    _, _, _, supervisor, client, request = handoff_env
    supervisor.endpoint.probe_id = "probe-other"
    endpoint = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert endpoint.code == "HANDOFF_SUPERVISOR_INVALID"
    supervisor.endpoint.probe_id = "probe-123"
    supervisor._config.operation_level = OperationLevel.OBSERVE
    config = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert config.code == "HANDOFF_SUPERVISOR_INVALID"
    assert client.events == []


def test_begin_while_reacquiring_fails_without_stopping_again(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data
    document = _state(session_root)
    document["state"] = "reacquiring"
    atomic_write_json(session_root / STATE_NAME, document)
    result = asyncio.run(begin_debug_handoff(request, supervisor, client))
    assert result.code == "HANDOFF_STATE_CONFLICT"
    assert supervisor.stop_calls == 1
    assert ticket.ticket_id == document["ticketId"]


def test_end_client_factory_failure_is_retryable(handoff_env):
    _, _, session_root, supervisor, client, request = handoff_env
    ticket = asyncio.run(begin_debug_handoff(request, supervisor, client)).data

    def fail_factory(endpoint: object):
        raise RuntimeError("private factory detail")

    result = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, fail_factory))
    assert result.code == "HANDOFF_REACQUIRE_FAILED"
    assert _state(session_root)["state"] == "reacquiring"
    assert "private factory detail" not in json.dumps(result.to_dict())
