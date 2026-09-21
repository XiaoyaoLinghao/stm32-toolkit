from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import test_debug_handoff as handoff_fixture
from stm32_toolkit.build.identity import atomic_write_json
from stm32_toolkit.probe.handoff import (
    DebugHandoffRequest,
    HandoffRestore,
    HandoffTicket,
    begin_debug_handoff,
    end_debug_handoff,
)

STATE_NAME = handoff_fixture.STATE_NAME
CORTEX_CONFIG_NAME = handoff_fixture.CORTEX_CONFIG_NAME
ORIGINAL_TEXT_SIZE = 256
CHANGED_TEXT_SIZE = 320


class FinalizeFalseOnceSupervisor(handoff_fixture.FakeSupervisor):
    def __init__(self, project: Path, session_root: Path) -> None:
        super().__init__(project, session_root)
        self.post_consume_finalize_calls = 0

    async def finalize_consumed_handoff(self, ticket: str) -> bool:
        if self._handoff_consumed:
            self.post_consume_finalize_calls += 1
            if self.post_consume_finalize_calls == 1:
                return False
        return await super().finalize_consumed_handoff(ticket)


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _state(session_root: Path) -> dict[str, object]:
    return json.loads((session_root / STATE_NAME).read_text(encoding="utf-8"))


def _lease_bytes(supervisor: handoff_fixture.FakeSupervisor) -> bytes:
    return supervisor._lease_manager.path.read_bytes()


def _lease(supervisor: handoff_fixture.FakeSupervisor) -> dict[str, object]:
    return json.loads(supervisor._lease_manager.path.read_text(encoding="utf-8"))


def _make_handoff_env(
    tmp_path: Path,
    supervisor_type: type[handoff_fixture.FakeSupervisor],
) -> tuple[
    Path,
    dict[str, object],
    Path,
    handoff_fixture.FakeSupervisor,
    handoff_fixture.FakeClient,
    DebugHandoffRequest,
]:
    project = handoff_fixture.prepare_project(tmp_path / "project")
    identity = handoff_fixture._publish_current_debug_build(
        project, text_size=ORIGINAL_TEXT_SIZE
    )
    atomic_write_json(
        project / "artifacts" / "migration" / "flash-result.json",
        handoff_fixture._flash_result(identity),
    )
    session_root = tmp_path / "plugin-data" / "projects" / "workspace-a" / "session-a"
    supervisor = supervisor_type(project, session_root)
    client = handoff_fixture.FakeClient(
        supervisor.endpoint,
        handoff_fixture._elf_with_flash_segment(text_size=ORIGINAL_TEXT_SIZE)[
            84 : 84 + 320
        ],
    )
    request = DebugHandoffRequest(
        project_root=project,
        expected_build_id=str(identity["buildId"]),
        expected_elf_sha256=str(identity["elfSha256"]),
        authorized=True,
        previous_watch_selection=("counter", "device.state"),
    )
    return project, identity, session_root, supervisor, client, request


def _assert_ticket(result: object) -> HandoffTicket:
    assert getattr(result, "ok", False) is True
    ticket = getattr(result, "data", None)
    assert type(ticket) is HandoffTicket
    wire = ticket.to_dict()
    assert set(wire) == {"ticket", "cortexDebug", "cortexDebugLaunch"}
    assert wire["ticket"] == ticket.ticket_id
    assert wire["cortexDebug"] == ticket.cortex_debug.to_dict()
    assert isinstance(wire["cortexDebugLaunch"], dict)
    return ticket


def _publish_identity(project: Path, *, text_size: int) -> dict[str, object]:
    return handoff_fixture._publish_current_debug_build(project, text_size=text_size)


def test_handoff_identity_race_refuses_without_overreach_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        project,
        original_identity,
        session_root,
        supervisor,
        client,
        request,
    ) = _make_handoff_env(tmp_path, handoff_fixture.FakeSupervisor)
    session_before = _file_bytes(session_root)
    guard_name = ".debug-handoff.guard"
    assert guard_name not in session_before
    lease_before = _lease_bytes(supervisor)
    flash_path = project / "artifacts" / "migration" / "flash-result.json"
    flash_before = flash_path.read_bytes()
    endpoint = supervisor.endpoint
    changed_identities: list[dict[str, object]] = []
    metadata_calls = 0
    original_metadata = supervisor.debug_handoff_metadata

    async def publish_changed_build(probe_id: str, target: str) -> object:
        nonlocal metadata_calls
        metadata_calls += 1
        if metadata_calls == 1:
            changed_identities.append(
                _publish_identity(project, text_size=CHANGED_TEXT_SIZE)
            )
        return await original_metadata(probe_id, target)

    monkeypatch.setattr(supervisor, "debug_handoff_metadata", publish_changed_build)
    refused = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert refused.ok is False
    assert refused.code == "HANDOFF_IDENTITY_MISMATCH"
    assert refused.message == "Firmware identity changed during debug handoff"
    assert metadata_calls == 1
    assert len(changed_identities) == 1
    assert changed_identities[0]["buildId"] != original_identity["buildId"]
    expected_session_after_refusal = dict(session_before)
    expected_session_after_refusal[guard_name] = b"\0"
    assert _file_bytes(session_root) == expected_session_after_refusal
    assert _lease_bytes(supervisor) == lease_before
    assert supervisor.endpoint is endpoint
    assert (session_root / "probe-endpoint.json").is_file()
    assert not (session_root / STATE_NAME).exists()
    assert not (session_root / CORTEX_CONFIG_NAME).exists()
    assert supervisor.stop_calls == 0
    assert supervisor.lifecycle_events == ["metadata"]
    assert [event[0] for event in client.events] == ["attach", "read"]
    assert request.expected_build_id == str(original_identity["buildId"])
    assert request.expected_elf_sha256 == str(original_identity["elfSha256"])
    assert flash_path.read_bytes() == flash_before

    restored_identity = _publish_identity(project, text_size=ORIGINAL_TEXT_SIZE)
    assert restored_identity["buildId"] == original_identity["buildId"]
    assert restored_identity["elfSha256"] == original_identity["elfSha256"]
    assert flash_path.read_bytes() == flash_before

    begun = asyncio.run(begin_debug_handoff(request, supervisor, client))
    ticket = _assert_ticket(begun)
    external_state = _state(session_root)
    assert external_state["state"] == "externally-owned"
    assert external_state["ticketId"] == ticket.ticket_id
    assert external_state["buildId"] == original_identity["buildId"]
    assert _lease(supervisor)["state"] == "externally-owned"

    returned_clients: list[handoff_fixture.FakeClient] = []
    changed_end_identities: list[dict[str, object]] = []
    end_changed = False

    def factory(endpoint_value: object) -> handoff_fixture.FakeClient:
        nonlocal end_changed
        returned = handoff_fixture.FakeClient(
            endpoint_value,
            handoff_fixture._elf_with_flash_segment(text_size=ORIGINAL_TEXT_SIZE)[
                84 : 84 + 320
            ],
        )
        if not returned_clients:

            def publish_changed_after_read() -> None:
                nonlocal end_changed
                if not end_changed:
                    end_changed = True
                    changed_end_identities.append(
                        _publish_identity(project, text_size=CHANGED_TEXT_SIZE)
                    )

            returned.after_read = publish_changed_after_read
        returned_clients.append(returned)
        return returned

    refused_end = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))
    assert refused_end.ok is False
    assert refused_end.code == "HANDOFF_IDENTITY_MISMATCH"
    assert refused_end.message == "Firmware identity changed during debug handoff"
    assert len(changed_end_identities) == 1
    assert changed_end_identities[0]["buildId"] != original_identity["buildId"]
    expected_reacquiring = dict(external_state)
    expected_reacquiring["state"] = "reacquiring"
    assert _state(session_root) == expected_reacquiring
    expected_external_lease = {
        "schemaVersion": 1,
        "state": "externally-owned",
        "leaseId": "lease-a",
        "ticketSha256": hashlib.sha256(ticket.ticket_id.encode("ascii")).hexdigest(),
    }
    assert _lease(supervisor) == expected_external_lease
    assert supervisor.endpoint is None
    assert not (session_root / "probe-endpoint.json").exists()
    assert supervisor.start_calls == 1
    assert supervisor.stop_calls == 2
    assert supervisor.lifecycle_events == [
        "metadata",
        "metadata",
        "reserve",
        "stop",
        "start",
        "stop",
    ]
    assert "consume" not in supervisor.lifecycle_events
    assert "finalize" not in supervisor.lifecycle_events
    assert "acknowledge" not in supervisor.lifecycle_events
    assert [event[0] for event in returned_clients[0].events] == [
        "attach",
        "read",
        "close",
    ]
    assert request.expected_build_id == str(original_identity["buildId"])
    assert request.expected_elf_sha256 == str(original_identity["elfSha256"])
    assert flash_path.read_bytes() == flash_before

    restored_identity = _publish_identity(project, text_size=ORIGINAL_TEXT_SIZE)
    assert restored_identity["buildId"] == original_identity["buildId"]
    assert restored_identity["elfSha256"] == original_identity["elfSha256"]

    ended = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))
    assert ended.ok is True
    assert type(ended.data) is HandoffRestore
    assert ended.data.previous_watch_selection == request.previous_watch_selection
    assert _state(session_root)["state"] == "observing"
    assert _state(session_root)["ticketId"] is None
    assert _state(session_root)["previousWatchSelection"] == []
    assert _lease(supervisor)["state"] == "released"
    assert supervisor.endpoint is None
    assert not (session_root / "probe-endpoint.json").exists()
    assert supervisor.start_calls == 2
    assert supervisor.stop_calls == 3
    assert supervisor.lifecycle_events == [
        "metadata",
        "metadata",
        "reserve",
        "stop",
        "start",
        "stop",
        "start",
        "consume",
        "stop",
        "finalize",
        "acknowledge",
    ]
    assert len(returned_clients) == 2
    assert [event[0] for event in returned_clients[0].events] == [
        "attach",
        "read",
        "close",
    ]
    assert [event[0] for event in returned_clients[1].events] == [
        "attach",
        "read",
        "close",
    ]
    assert flash_path.read_bytes() == flash_before


@pytest.fixture
def settlement_env(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, object],
    Path,
    FinalizeFalseOnceSupervisor,
    handoff_fixture.FakeClient,
    DebugHandoffRequest,
]:
    return _make_handoff_env(tmp_path, FinalizeFalseOnceSupervisor)  # type: ignore[return-value]


def test_handoff_finalize_false_preserves_settlement_for_public_retry(
    settlement_env: tuple[
        Path,
        dict[str, object],
        Path,
        FinalizeFalseOnceSupervisor,
        handoff_fixture.FakeClient,
        DebugHandoffRequest,
    ],
) -> None:
    (
        project,
        original_identity,
        session_root,
        supervisor,
        client,
        request,
    ) = settlement_env
    begun = asyncio.run(begin_debug_handoff(request, supervisor, client))
    ticket = _assert_ticket(begun)
    external_state = _state(session_root)
    lease_before_end = _lease_bytes(supervisor)
    flash_path = project / "artifacts" / "migration" / "flash-result.json"
    flash_before = flash_path.read_bytes()
    returned_clients: list[handoff_fixture.FakeClient] = []

    def factory(endpoint_value: object) -> handoff_fixture.FakeClient:
        returned = handoff_fixture.FakeClient(
            endpoint_value,
            handoff_fixture._elf_with_flash_segment(text_size=ORIGINAL_TEXT_SIZE)[
                84 : 84 + 320
            ],
        )
        returned_clients.append(returned)
        return returned

    events_before_end = list(supervisor.lifecycle_events)
    first = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))

    assert first.ok is False
    assert first.code == "HANDOFF_REACQUIRE_FAILED"
    assert first.message == "Consumed handoff ownership could not be finalized"
    expected_reacquiring = dict(external_state)
    expected_reacquiring["state"] = "reacquiring"
    assert _state(session_root) == expected_reacquiring
    expected_consumed_lease = {
        "schemaVersion": 1,
        "state": "handoff-consumed",
        "leaseId": "lease-a",
        "ticketSha256": hashlib.sha256(ticket.ticket_id.encode("ascii")).hexdigest(),
    }
    assert _lease(supervisor) == expected_consumed_lease
    assert _lease_bytes(supervisor) != lease_before_end
    assert supervisor.endpoint is None
    assert not (session_root / "probe-endpoint.json").exists()
    assert supervisor.start_calls == 1
    assert supervisor.stop_calls == 2
    assert supervisor.post_consume_finalize_calls == 1
    assert supervisor.lifecycle_events == events_before_end + [
        "start",
        "consume",
        "stop",
    ]
    assert "acknowledge" not in supervisor.lifecycle_events
    assert [event[0] for event in returned_clients[0].events] == [
        "attach",
        "read",
        "close",
    ]
    assert request.expected_build_id == str(original_identity["buildId"])
    assert request.expected_elf_sha256 == str(original_identity["elfSha256"])
    assert flash_path.read_bytes() == flash_before

    state_before_retry = _file_bytes(session_root)
    lease_before_retry = _lease_bytes(supervisor)
    events_before_retry = list(supervisor.lifecycle_events)
    second = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))

    assert second.ok is True
    assert type(second.data) is HandoffRestore
    assert second.data.previous_watch_selection == request.previous_watch_selection
    assert supervisor.post_consume_finalize_calls == 2
    assert supervisor.start_calls == 1
    assert supervisor.stop_calls == 2
    assert len(returned_clients) == 1
    assert supervisor.lifecycle_events == events_before_retry + [
        "finalize",
        "acknowledge",
    ]
    assert supervisor.lifecycle_events.count("start") == 1
    assert supervisor.lifecycle_events.count("consume") == 1
    assert supervisor.lifecycle_events.count("finalize") == 1
    assert supervisor.lifecycle_events.count("acknowledge") == 1
    assert _state(session_root)["state"] == "observing"
    assert _state(session_root)["ticketId"] is None
    assert _state(session_root)["previousWatchSelection"] == []
    assert _lease(supervisor)["state"] == "released"
    assert supervisor.endpoint is None
    assert not (session_root / "probe-endpoint.json").exists()
    assert [event[0] for event in returned_clients[0].events] == [
        "attach",
        "read",
        "close",
    ]
    assert flash_path.read_bytes() == flash_before

    replay_state = _file_bytes(session_root)
    replay_lease = _lease_bytes(supervisor)
    replay_events = list(supervisor.lifecycle_events)
    replay = asyncio.run(end_debug_handoff(ticket.ticket_id, supervisor, factory))
    assert replay.ok is False
    assert replay.code == "HANDOFF_TICKET_INVALID"
    assert replay.message == "Debug handoff ticket is invalid"
    assert _file_bytes(session_root) == replay_state
    assert _lease_bytes(supervisor) == replay_lease
    assert supervisor.lifecycle_events == replay_events
    assert supervisor.start_calls == 1
    assert supervisor.stop_calls == 2
    assert len(returned_clients) == 1
    assert _file_bytes(session_root) != state_before_retry
    assert _lease_bytes(supervisor) != lease_before_retry
