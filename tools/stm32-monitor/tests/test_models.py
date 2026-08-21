from __future__ import annotations

import json
import math
import copy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from stm32_monitor.models import (
    LiveEvent,
    MonitorConfig,
    ObservationBinding,
    ProbeConnectRequest,
    FirmwareStatus,
    SampleBatch,
    SampleValue,
    WatchGroup,
    WatchItem,
)
from stm32_monitor.exports import ExportArtifact
from stm32_monitor.history import HistoryBatchSlice, HistoryPage, flatten_history_page
from stm32_monitor.protocol import (
    MONITOR_PROTOCOL_VERSION,
    ProtocolResult,
    ProtocolViolation,
    failure,
    parse_json_object,
    success,
)
from stm32_toolkit.paths import WorkspacePaths


NOW = datetime(2026, 8, 8, 1, 2, 3, tzinfo=timezone.utc)
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _config(tmp_path: Path) -> MonitorConfig:
    project = tmp_path / "project"
    project.mkdir()
    return MonitorConfig(project, tmp_path / "state", "monitor-1")


def _binding() -> ObservationBinding:
    return ObservationBinding(
        workspace_id="c" * 64,
        logical_project_id="33333333-3333-4333-8333-333333333333",
        session_id="monitor-1",
        probe_id="probe-serial-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256="a" * 64,
    )


def test_live_event_is_an_immutable_bounded_discriminated_union() -> None:
    event = LiveEvent(
        7,
        "heartbeat",
        {
            "stateRevision": 3,
            "capturedAtUtc": "2026-08-08T01:02:03.000000Z",
        },
    )

    assert event.to_dict() == {
        "eventId": 7,
        "type": "heartbeat",
        "data": {
            "stateRevision": 3,
            "capturedAtUtc": "2026-08-08T01:02:03.000000Z",
        },
    }
    with pytest.raises(TypeError):
        event.data["stateRevision"] = 4  # type: ignore[index]
    for values in (
        (0, "state", {}),
        (1, "unknown", {}),
        (1, "state", []),
        (1, "sample", {"value": float("nan")}),
    ):
        with pytest.raises((TypeError, ValueError)):
            LiveEvent(*values)


def _live_status() -> dict[str, object]:
    return {
        "workspaceId": "c" * 64,
        "sessionId": "monitor-1",
        "project": {
            "logicalProjectId": "33333333-3333-4333-8333-333333333333",
            "name": "fixture",
            "targetDevice": "STM32F407VGTx",
        },
        "firmware": None,
        "probe": {"connected": False, "probeId": None},
        "sampling": {
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
        },
        "probeConnected": False,
        "samplingActive": False,
    }


def _live_batch() -> dict[str, object]:
    return SampleBatch(
        binding=_binding(),
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=4,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value=7),),
    ).to_dict()


def test_live_event_exact_payloads_roundtrip_and_snapshot_nested_mutability() -> None:
    payloads = {
        "hello": {
            "protocol": "stm32-toolkit-monitor/1",
            "toolkitVersion": "0.5.0",
            "monitorVersion": "0.5.0",
            "stateRevision": 2,
        },
        "state": {"stateRevision": 2, "gap": False, "status": _live_status()},
        "sample": {"batch": _live_batch(), "serviceSubscriberDrops": 5},
        "heartbeat": {
            "stateRevision": 2,
            "capturedAtUtc": "2026-08-08T01:02:03.123456Z",
        },
    }
    snapshots = {
        kind: LiveEvent(index, kind, payload).to_dict()
        for index, (kind, payload) in enumerate(payloads.items(), 1)
    }
    payloads["state"]["status"]["sampling"]["state"] = "RUNNING"
    payloads["sample"]["batch"]["values"][0]["typedValue"] = 99

    assert snapshots["state"]["data"]["status"]["sampling"]["state"] == "IDLE"
    assert snapshots["sample"]["data"]["batch"]["values"][0]["typedValue"] == 7
    assert [snapshots[kind]["type"] for kind in payloads] == list(payloads)


def test_live_event_rejects_inexact_payloads_for_every_discriminator() -> None:
    valid = {
        "hello": {
            "protocol": "stm32-toolkit-monitor/1",
            "toolkitVersion": "0.5.0",
            "monitorVersion": "0.5.0",
            "stateRevision": 0,
        },
        "state": {"stateRevision": 0, "gap": False, "status": _live_status()},
        "sample": {"batch": _live_batch(), "serviceSubscriberDrops": 0},
        "heartbeat": {
            "stateRevision": 0,
            "capturedAtUtc": "2026-08-08T01:02:03.000000Z",
        },
    }
    for kind, payload in valid.items():
        missing = dict(payload)
        missing.pop(next(iter(missing)))
        extra = dict(payload, unexpected=True)
        with pytest.raises((TypeError, ValueError)):
            LiveEvent(1, kind, missing)
        with pytest.raises((TypeError, ValueError)):
            LiveEvent(1, kind, extra)

    invalid = (
        ("hello", valid["hello"] | {"stateRevision": True}),
        ("hello", valid["hello"] | {"protocol": ""}),
        ("state", valid["state"] | {"gap": 1}),
        ("state", valid["state"] | {"stateRevision": -1}),
        ("state", valid["state"] | {"status": {"probeConnected": False}}),
        ("sample", valid["sample"] | {"serviceSubscriberDrops": True}),
        ("sample", valid["sample"] | {"serviceSubscriberDrops": -1}),
        ("sample", valid["sample"] | {"batch": {"sequence": 1}}),
        ("heartbeat", valid["heartbeat"] | {"stateRevision": True}),
        ("heartbeat", valid["heartbeat"] | {"capturedAtUtc": "2026-08-08T01:02:03Z"}),
        ("heartbeat", valid["heartbeat"] | {"capturedAtUtc": "2026-08-08T01:02:03.000000+00:00"}),
        ("heartbeat", valid["heartbeat"] | {"capturedAtUtc": "not-a-time"}),
    )
    for kind, payload in invalid:
        with pytest.raises((TypeError, ValueError)):
            LiveEvent(1, kind, payload)

    capability = copy.deepcopy(valid["sample"])
    capability["batch"]["values"][0]["typedValue"] = object()
    with pytest.raises(TypeError):
        LiveEvent(1, "sample", capability)


def _history_slice(
    values: list[SampleValue],
    *,
    start_ordinal: int = 0,
    batch_value_count: int | None = None,
    sequence: int = 4,
) -> HistoryBatchSlice:
    return HistoryBatchSlice(
        binding=_binding(),
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=sequence,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        start_ordinal=start_ordinal,
        batch_value_count=(
            len(values) if batch_value_count is None else batch_value_count
        ),
        values=values,
    )


def test_monitor_config_canonicalizes_external_roots_without_creating_state(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.project_root == (tmp_path / "project").resolve()
    assert config.data_root == (tmp_path / "state").resolve()
    assert config.session_id == "monitor-1"
    assert not config.data_root.exists()


def test_group_page_is_deeply_immutable_bounded_and_address_free() -> None:
    from stm32_monitor.models import GroupPage

    groups = [
        WatchGroup.create(
            "Core",
            "",
            250,
            (WatchItem.variable("counter"),),
            group_id=GROUP_ID,
            now=NOW,
        )
    ]
    page = GroupPage(groups, "opaque", "a" * 64)
    groups.clear()

    assert page.to_dict() == {
        "groups": [
            {
                "groupId": str(GROUP_ID),
                "name": "Core",
                "description": "",
                "intervalMs": 250,
                "items": [{"kind": "variable", "expression": "counter"}],
                "revision": 1,
                "createdAtUtc": "2026-08-08T01:02:03.000000Z",
                "updatedAtUtc": "2026-08-08T01:02:03.000000Z",
            }
        ],
        "nextCursor": "opaque",
        "revision": "a" * 64,
    }
    assert "address" not in json.dumps(page.to_dict()).casefold()
    with pytest.raises((TypeError, ValueError)):
        GroupPage(tuple(page.groups) * 17, None, "a" * 64)
    with pytest.raises((TypeError, ValueError)):
        GroupPage(page.groups, "", "a" * 64)
    with pytest.raises((TypeError, ValueError)):
        GroupPage(page.groups, None, "not-a-digest")


def test_group_page_and_protocol_result_detach_the_complete_group_graph() -> None:
    from stm32_monitor.models import GroupPage

    item = WatchItem.variable("counter")
    group = WatchGroup.create(
        "Core", "", 250, (item,), group_id=GROUP_ID, now=NOW
    )
    page = GroupPage((group,), "opaque", "a" * 64)
    page_payload = page.to_dict()
    page_repr = repr(page)
    result = success("groups.list", page)
    result_payload = result.to_dict()
    result_repr = repr(result.data)

    assert page.groups[0] is not group
    assert page.groups[0].items[0] is not item
    assert result.data is not page
    assert result.data.groups[0] is not page.groups[0]
    assert result.data.groups[0].items[0] is not page.groups[0].items[0]

    object.__setattr__(item, "selector", "tampered-item")
    object.__setattr__(group, "name", "Tampered group")
    object.__setattr__(group, "items", ())
    assert page.to_dict() == page_payload
    assert repr(page) == page_repr

    object.__setattr__(page.groups[0].items[0], "selector", "tampered-page-item")
    object.__setattr__(page.groups[0], "name", "Tampered page group")
    object.__setattr__(page, "next_cursor", "tampered-page-cursor")
    assert result.to_dict() == result_payload
    assert repr(result.data) == result_repr


def test_group_page_rejects_model_subclasses_and_forged_nested_items() -> None:
    from stm32_monitor.models import GroupPage

    class DerivedItem(WatchItem):
        pass

    derived = DerivedItem.variable("counter")
    group_with_subclass = WatchGroup.create(
        "Core", "", 250, (derived,), group_id=GROUP_ID, now=NOW
    )
    with pytest.raises(ValueError, match="group page"):
        GroupPage((group_with_subclass,), None, "a" * 64)

    forged = WatchItem.variable("counter")
    group_with_forgery = WatchGroup.create(
        "Core", "", 250, (forged,), group_id=GROUP_ID, now=NOW
    )
    object.__setattr__(forged, "kind", "address")
    with pytest.raises(ValueError, match="group page"):
        GroupPage((group_with_forgery,), None, "a" * 64)


def test_monitor_config_rejects_state_inside_project_and_unsafe_session(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(ValueError, match="outside"):
        MonitorConfig(project, project / ".state", "monitor-1")
    with pytest.raises(ValueError, match="session"):
        MonitorConfig(project, tmp_path / "state", "../escape")


def test_probe_request_accepts_only_the_discovered_probe_identity() -> None:
    request = ProbeConnectRequest("probe-serial-1")
    assert request.to_dict() == {"probeId": "probe-serial-1"}
    assert {item.name for item in __import__("dataclasses").fields(request)} == {"probe_id"}

    for values in (("",), ("../probe",), ("p" * 257,)):
        with pytest.raises(ValueError):
            ProbeConnectRequest(*values)


def test_firmware_status_is_immutable_validated_and_path_free() -> None:
    status = FirmwareStatus(
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        target_device="STM32F407VGTx",
    )
    assert status.to_dict() == {
        "buildId": "b" * 64,
        "elfSha256": "e" * 64,
        "inputSnapshotSha256": "f" * 64,
        "gitHead": "a" * 40,
        "gitDirty": False,
        "targetDevice": "STM32F407VGTx",
    }
    rendered = json.dumps(status.to_dict()) + repr(status)
    assert "path" not in rendered.casefold()
    with pytest.raises(ValueError):
        replace(status, build_id="bad")


def test_observation_binding_round_trips_complete_workspace_id_without_using_storage_key(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    logical_project_id = UUID("33333333-3333-4333-8333-333333333333")
    paths = WorkspacePaths.from_roots(
        tmp_path / "state",
        project,
        logical_project_id,
        "monitor-1",
    )
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id=str(logical_project_id),
        session_id=paths.session_id,
        probe_id="probe-serial-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256="a" * 64,
    )

    assert len(paths.workspace_id) == 64
    assert paths.workspace_storage_key == paths.workspace_id[:24]
    assert paths.workspace_storage_key != paths.workspace_id
    assert paths.workspace_root == paths.data_root / "projects" / paths.workspace_storage_key
    assert ObservationBinding.from_dict(binding.to_dict()) == binding
    assert binding.to_dict()["workspaceId"] == paths.workspace_id

    with pytest.raises(ValueError, match="workspace ID is invalid"):
        ObservationBinding.from_dict(
            binding.to_dict() | {"workspaceId": paths.workspace_storage_key}
        )
    with pytest.raises(ValueError, match="workspace ID is invalid"):
        ObservationBinding.from_dict(
            binding.to_dict() | {"workspaceId": paths.workspace_id.upper()}
        )


def test_watch_item_is_a_bounded_discriminated_union_without_address_field() -> None:
    variable = WatchItem.variable("state.counter")
    register = WatchItem.register("USART1.SR")

    assert variable.to_dict() == {"kind": "variable", "expression": "state.counter"}
    assert register.to_dict() == {"kind": "register", "registerPath": "USART1.SR"}
    assert "address" not in variable.to_dict()
    assert "address" not in register.to_dict()

    with pytest.raises(ValueError):
        WatchItem("address", "0x20000000")
    with pytest.raises(ValueError):
        WatchItem.variable("x" * 513)
    with pytest.raises(ValueError):
        WatchItem.register("USART1\x00SR")


def test_watch_group_normalizes_name_and_snapshots_immutable_items() -> None:
    items = [WatchItem.variable("counter")]
    group = WatchGroup.create(
        name="  Cafe\u0301  ",
        description="counts",
        interval_ms=250,
        items=items,
        group_id=GROUP_ID,
        now=NOW,
    )
    items.append(WatchItem.register("GPIOA.IDR"))

    assert group.name == "Caf\u00e9"
    assert group.items == (WatchItem.variable("counter"),)
    assert group.revision == 1
    assert group.to_dict()["createdAtUtc"] == "2026-08-08T01:02:03.000000Z"
    json.dumps(group.to_dict())


@pytest.mark.parametrize("interval", [99, 5001])
def test_watch_group_rejects_out_of_range_interval(interval: int) -> None:
    with pytest.raises(ValueError, match="interval"):
        WatchGroup.create("group", "", interval, (), group_id=GROUP_ID, now=NOW)


def test_watch_group_enforces_name_and_description_character_limits() -> None:
    accepted = WatchGroup.create("n" * 128, "d" * 1024, 250, (), group_id=GROUP_ID, now=NOW)
    assert len(accepted.name) == 128 and len(accepted.description) == 1024
    with pytest.raises(ValueError, match="name"):
        WatchGroup.create("n" * 129, "", 250, (), group_id=GROUP_ID, now=NOW)
    with pytest.raises(ValueError, match="description"):
        WatchGroup.create("g", "d" * 1025, 250, (), group_id=GROUP_ID, now=NOW)


def test_observation_and_sample_models_are_deeply_immutable_and_json_safe() -> None:
    typed = {"type": "uint32", "value": 7, "nested": [1, {"ok": True}]}
    sample = SampleValue(WatchItem.variable("counter"), "OK", typed_value=typed)
    batch = SampleBatch(
        binding=_binding(),
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=4,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(sample,),
    )
    typed["value"] = 99
    typed["nested"][1]["ok"] = False

    payload = batch.to_dict()
    assert payload["values"][0]["typedValue"] == {
        "type": "uint32",
        "value": 7,
        "nested": [1, {"ok": True}],
    }
    assert payload["capturedAtUtc"] == "1970-01-01T00:00:00.000001Z"
    json.dumps(payload)


def test_protocol_results_are_monitor_versioned_and_details_are_snapshotted() -> None:
    details = {"field": ["name"]}
    data = {"groups": [{"name": "original"}]}
    bad = failure("groups.create", "MONITOR_REQUEST_INVALID", "invalid request", details)
    details["field"].append("changed")
    good = success("groups.list", data)
    data["groups"][0]["name"] = "changed"

    assert bad.protocol == MONITOR_PROTOCOL_VERSION == "stm32-toolkit-monitor/1"
    assert bad.to_dict() == {
        "protocol": "stm32-toolkit-monitor/1",
        "toolkitVersion": "0.5.0",
        "monitorVersion": "0.5.0",
        "ok": False,
        "operation": "groups.create",
        "code": "MONITOR_REQUEST_INVALID",
        "message": "invalid request",
        "data": None,
        "details": {"field": ["name"]},
    }
    assert good.ok is True and good.code == "OK"
    assert good.to_dict()["data"] == {"groups": [{"name": "original"}]}
    json.dumps(bad.to_dict())


def test_protocol_json_parser_is_bounded_and_requires_an_object() -> None:
    assert parse_json_object(b'{"name":"g"}', limit=64) == {"name": "g"}

    for payload in (b"[]", b"not-json", b'{"name":"' + b"x" * 64 + b'"}'):
        with pytest.raises(ProtocolViolation) as raised:
            parse_json_object(payload, limit=64)
        assert raised.value.code in {"MONITOR_REQUEST_INVALID", "MONITOR_IMPORT_INVALID"}


def test_models_reject_mutable_or_malformed_evidence_boundaries(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.project_root.is_dir()
    with pytest.raises(ValueError, match="directory"):
        MonitorConfig(config.project_root / "missing", tmp_path / "other", "monitor-1")

    with pytest.raises(TypeError, match="sets"):
        SampleValue(WatchItem.variable("counter"), "OK", typed_value={"values": {1, 2}})
    for item in (
        {"kind": "register", "registerPath": "GPIOA.IDR"},
        {"kind": "address", "address": "0x20000000"},
    ):
        if item["kind"] == "register":
            assert WatchItem.from_dict(item) == WatchItem.register("GPIOA.IDR")
        else:
            with pytest.raises(ValueError):
                WatchItem.from_dict(item)


def test_group_sample_and_batch_reject_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="unique"):
        WatchGroup.create("G", "", 250, (WatchItem.variable("x"), WatchItem.variable("x")), group_id=GROUP_ID, now=NOW)
    with pytest.raises(ValueError, match="revision"):
        WatchGroup(GROUP_ID, "G", "", 250, (), 0, NOW, NOW)
    with pytest.raises(ValueError, match="status"):
        SampleValue(WatchItem.variable("x"), "UNKNOWN", typed_value=1)
    with pytest.raises(ValueError, match="typed value"):
        SampleValue(WatchItem.variable("x"), "OK")
    with pytest.raises(ValueError, match="code"):
        SampleValue(WatchItem.variable("x"), "ERROR")

    base = dict(
        binding=_binding(), group_id=GROUP_ID, group_revision=1, run_id=RUN_ID,
        sequence=1, scheduled_unix_ns=100, captured_unix_ns=200, latency_ns=100,
        actual_rate_hz=4.0, subscriber_drops=0, history_drops=0, deadline_drops=0,
        values=(SampleValue(WatchItem.variable("x"), "OK", typed_value=1),),
    )
    for update in (
        {"group_revision": 0},
        {"captured_unix_ns": 99},
        {"actual_rate_hz": -1.0},
        {"values": ("bad",)},
    ):
        with pytest.raises(ValueError):
            SampleBatch(**(base | update))


def test_binding_rejects_bad_git_and_non_boolean_dirty_state() -> None:
    payload = _binding().to_dict()
    payload["gitHead"] = "not-a-sha"
    with pytest.raises(ValueError, match="Git HEAD"):
        ObservationBinding.from_dict(payload)
    payload = _binding().to_dict()
    payload["gitDirty"] = 1
    with pytest.raises(ValueError, match="dirty"):
        ObservationBinding.from_dict(payload)
    payload = _binding().to_dict()
    payload.pop("leaseId")
    with pytest.raises(ValueError, match="binding"):
        ObservationBinding.from_dict(payload)


def test_json_values_are_exact_bounded_immutable_snapshots() -> None:
    class CustomValue:
        def __init__(self) -> None:
            self.calls = 0

        def to_dict(self) -> dict[str, object]:
            self.calls += 1
            return {"secret": "executed"}

    source = {"nested": [{"value": 1}], "text": "ok"}
    sample = SampleValue(WatchItem.variable("counter"), "OK", typed_value=source)
    source["nested"][0]["value"] = 99
    assert sample.to_dict()["typedValue"] == {
        "nested": [{"value": 1}],
        "text": "ok",
    }

    custom = CustomValue()
    cyclic: list[object] = []
    cyclic.append(cyclic)
    deep: object = None
    for _ in range(40):
        deep = [deep]
    rejected = (
        b"bytes",
        {1: "non-string key"},
        {"Caf\u00e9": 1, "Cafe\u0301": 2},
        math.nan,
        math.inf,
        cyclic,
        deep,
        [None] * 10_001,
        "x" * (1024 * 1024 + 1),
        custom,
    )
    for value in rejected:
        with pytest.raises((TypeError, ValueError)):
            SampleValue(WatchItem.variable("counter"), "OK", typed_value=value)
    assert custom.calls == 0


def test_json_integer_timestamp_and_binding_boundaries_are_explicitly_bounded() -> None:
    watch = WatchItem.variable("counter")
    with pytest.raises(ValueError):
        SampleValue(watch, "OK", typed_value=10**5000)
    with pytest.raises(ProtocolViolation):
        parse_json_object(b'{"value":' + b"9" * 100 + b"}")

    value = SampleValue(watch, "OK", typed_value=1)
    base = dict(
        binding=_binding(), group_id=GROUP_ID, group_revision=1, run_id=RUN_ID,
        sequence=1, scheduled_unix_ns=100, captured_unix_ns=200, latency_ns=100,
        actual_rate_hz=4.0, subscriber_drops=0, history_drops=0, deadline_drops=0,
        values=(value,),
    )
    with pytest.raises(ValueError, match="binding"):
        SampleBatch(**(base | {"binding": object()}))
    with pytest.raises(ValueError):
        SampleBatch(**(base | {"scheduled_unix_ns": 2**63, "captured_unix_ns": 2**63}))


def test_protocol_result_validates_invariants_and_known_models_only() -> None:
    group = WatchGroup.create("G", "", 250, (), group_id=GROUP_ID, now=NOW)
    result = success("groups.list", (group,))
    assert result.data == (group,)
    assert result.to_dict()["data"] == [group.to_dict()]

    invalid_results = (
        (1, "groups.list", "OK", "", None),
        (True, "", "OK", "", None),
        (True, " groups.list ", "OK", "", None),
        (True, "groups.list", "lowercase", "", None),
        (True, "groups.list", "BAD", "", None),
        (True, "groups.list", "OK", "not empty", None),
        (False, "groups.list", "OK", "failed", None),
        (False, "groups.list", "MONITOR_FAILED", "", None),
        (False, "groups.list", "MONITOR_FAILED", "failed", {"unexpected": True}),
    )
    for ok, operation, code, message, data in invalid_results:
        with pytest.raises((TypeError, ValueError)):
            ProtocolResult(ok, operation, code, message, data)
    with pytest.raises(ValueError):
        ProtocolResult(
            True,
            "groups.list",
            "OK",
            "",
            None,
            protocol="another-protocol",
        )
    with pytest.raises(ValueError):
        ProtocolResult(True, "groups.list", "OK", "", None, {"warning": "no"})

    class CustomValue:
        calls = 0

        def to_dict(self) -> dict[str, object]:
            self.calls += 1
            return {"unsafe": True}

    custom = CustomValue()
    with pytest.raises((TypeError, ValueError)):
        success("custom", custom)
    assert custom.calls == 0


def test_protocol_result_snapshots_and_serializes_known_history_and_export_models(
    tmp_path: Path,
) -> None:
    typed = {"nested": [{"value": 1}]}
    values = [SampleValue(WatchItem.variable("counter"), "OK", typed_value=typed)]
    batches = [_history_slice(values)]
    page = HistoryPage.create(batches, next_cursor=None)
    page_result = success("history.query", page)
    snapshot = page_result.to_dict()
    typed["nested"][0]["value"] = 2
    values.clear()
    batches.clear()
    object.__setattr__(page, "next_cursor", "9:9")
    object.__setattr__(page.batches[0], "sequence", 99)

    payload = page_result.to_dict()["data"]
    assert page_result.to_dict() == snapshot
    assert page_result.data is not page
    assert page_result.data.batches[0] is not page.batches[0]
    assert payload["valueCount"] == 1
    assert payload["batches"][0]["values"][0]["typedValue"] == {
        "nested": [{"value": 1}]
    }
    assert set(payload) == {"batches", "valueCount", "nextCursor", "serializedBytes"}
    assert payload["serializedBytes"] == len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    flattened = tuple(flatten_history_page(page_result.data))
    assert flattened[0]["valueOrdinal"] == 0
    assert flattened[0]["batchValueCount"] == 1
    assert flattened[0]["binding"]["elfSha256"] == "e" * 64

    artifact = ExportArtifact(
        GROUP_ID,
        tmp_path,
        tmp_path / "history.jsonl",
        tmp_path / "manifest.json",
        "a" * 64,
        12,
        1,
    )
    assert success("exports.get", artifact).to_dict()["data"] == artifact.to_dict()

    with pytest.raises(ValueError):
        ProtocolResult(True, "groups.\x00list", "OK", "", None)
    with pytest.raises(TypeError):
        ProtocolResult(True, "groups.list", "OK", "", None, ())


@pytest.mark.parametrize(
    "forgery",
    [
        "page-subclass",
        "batch-subclass",
        "binding-subclass",
        "sample-subclass",
        "sample-status",
        "watch-subclass",
        "nested-json-subclass",
        "batch-sequence",
        "binding-dirty-type",
        "page-count",
    ],
)
def test_history_protocol_snapshot_rejects_forged_current_object_graph(
    forgery: str,
) -> None:
    sample = SampleValue(
        WatchItem.variable("counter"),
        "OK",
        typed_value={"nested": [1]},
    )
    batch = _history_slice([sample])
    page = HistoryPage.create((batch,), next_cursor=None)
    batch = page.batches[0]
    sample = batch.values[0]
    candidate = page

    if forgery == "page-subclass":
        class DerivedPage(HistoryPage):
            pass

        candidate = DerivedPage(
            page.batches,
            page.value_count,
            page.next_cursor,
            page.serialized_bytes,
        )
    elif forgery == "batch-subclass":
        class DerivedBatch(HistoryBatchSlice):
            pass

        derived = DerivedBatch(**{
            name: getattr(batch, name)
            for name, definition in batch.__dataclass_fields__.items()
            if definition.init
        })
        object.__setattr__(page, "batches", (derived,))
    elif forgery == "binding-subclass":
        class DerivedBinding(ObservationBinding):
            pass

        binding = batch.binding
        derived = DerivedBinding(**{
            field: getattr(binding, field)
            for field in binding.__dataclass_fields__
        })
        object.__setattr__(batch, "binding", derived)
    elif forgery == "sample-subclass":
        class DerivedSample(SampleValue):
            pass

        derived = DerivedSample(
            sample.watch,
            sample.status,
            typed_value=sample.typed_value,
            code=sample.code,
            definition=sample.definition,
        )
        object.__setattr__(batch, "values", (derived,))
    elif forgery == "sample-status":
        object.__setattr__(sample, "status", "NO")
    elif forgery == "watch-subclass":
        class DerivedWatch(WatchItem):
            pass

        object.__setattr__(sample, "watch", DerivedWatch.variable("counter"))
    elif forgery == "nested-json-subclass":
        class DerivedList(list):
            pass

        object.__setattr__(
            sample,
            "typed_value",
            MappingProxyType({"nested": DerivedList([1])}),
        )
    elif forgery == "batch-sequence":
        object.__setattr__(batch, "sequence", -1)
    elif forgery == "binding-dirty-type":
        object.__setattr__(batch.binding, "git_dirty", 1)
    else:
        object.__setattr__(page, "value_count", 2)

    with pytest.raises((TypeError, ValueError)):
        success("history.query", candidate)


def test_history_page_rejects_subclasses_ordinal_gaps_count_mismatch_and_bad_cursor() -> None:
    value = SampleValue(WatchItem.variable("counter"), "OK", typed_value=1)

    class DerivedValue(SampleValue):
        pass

    with pytest.raises((TypeError, ValueError), match="value"):
        _history_slice(
            [DerivedValue(WatchItem.variable("counter"), "OK", typed_value=1)]
        )
    with pytest.raises(ValueError, match="ordinal"):
        _history_slice([value, value], start_ordinal=255, batch_value_count=256)

    first = _history_slice([value], start_ordinal=0, batch_value_count=2)
    second = _history_slice([value], start_ordinal=1, batch_value_count=2)
    with pytest.raises(ValueError, match="value count"):
        HistoryPage((first, second), 1, None, 0)
    with pytest.raises(ValueError, match="cursor"):
        HistoryPage.create((first, second), next_cursor="01:0")
    for cursor in ("1:00", "１:０", "1" * 20 + ":0", f"{2**63}:0"):
        with pytest.raises(ValueError, match="cursor"):
            HistoryPage.create((first, second), next_cursor=cursor)

    class DerivedSlice(HistoryBatchSlice):
        pass

    derived = DerivedSlice(**{
        name: getattr(first, name)
        for name, definition in first.__dataclass_fields__.items()
        if definition.init
    })
    with pytest.raises((TypeError, ValueError), match="batch"):
        HistoryPage.create((derived,), next_cursor=None)


def test_history_page_constructor_enforces_exact_layout_and_slice_order() -> None:
    value = SampleValue(WatchItem.variable("counter"), "OK", typed_value=1)
    first = _history_slice([value], start_ordinal=0, batch_value_count=3)
    contiguous = _history_slice([value], start_ordinal=1, batch_value_count=3)
    valid = HistoryPage.create((first, contiguous), next_cursor="1:1")

    with pytest.raises(ValueError, match="batches"):
        HistoryPage((object(),), 0, None, 0)
    with pytest.raises(ValueError, match="value count"):
        HistoryPage((), False, None, 0)
    with pytest.raises(ValueError, match="serialized byte count"):
        HistoryPage(valid.batches, valid.value_count, valid.next_cursor, False)
    with pytest.raises(ValueError, match="inconsistent"):
        HistoryPage(
            valid.batches,
            valid.value_count,
            valid.next_cursor,
            valid.serialized_bytes + 1,
        )

    gap = _history_slice([value], start_ordinal=2, batch_value_count=3)
    with pytest.raises(ValueError, match="contiguous"):
        HistoryPage.create((first, gap), next_cursor=None)
    changed_evidence = replace(contiguous, actual_rate_hz=5.0)
    with pytest.raises(ValueError, match="contiguous"):
        HistoryPage.create((first, changed_evidence), next_cursor=None)
    middle = _history_slice(
        [value], start_ordinal=0, batch_value_count=1, sequence=5
    )
    with pytest.raises(ValueError, match="contiguous"):
        HistoryPage.create((first, middle, contiguous), next_cursor=None)

    too_many = tuple(
        _history_slice(
            [value] * 256,
            batch_value_count=256,
            sequence=sequence,
        )
        for sequence in range(40)
    )
    with pytest.raises(ValueError, match="10,000"):
        HistoryPage(too_many, 10_240, None, 0)
    with pytest.raises(TypeError, match="history page"):
        tuple(flatten_history_page(object()))


def test_history_page_deep_snapshots_two_slices_from_one_batch() -> None:
    typed_value = {"nested": [{"value": 7}]}
    definition = {"type": {"name": "uint32"}}
    watch = WatchItem.variable("telemetry.counter")
    sample = SampleValue(
        watch, "OK", typed_value=typed_value, definition=definition
    )
    binding = _binding()
    batch = SampleBatch(
        binding=binding,
        group_id=GROUP_ID,
        group_revision=3,
        run_id=RUN_ID,
        sequence=4,
        scheduled_unix_ns=1_000,
        captured_unix_ns=1_250,
        latency_ns=250,
        actual_rate_hz=4.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(sample, sample),
    )
    slice_fields = {
        field: getattr(batch, field)
        for field in batch.__dataclass_fields__
        if field != "values"
    }
    first = HistoryBatchSlice(
        **slice_fields,
        start_ordinal=0,
        batch_value_count=2,
        values=batch.values[:1],
    )
    second = HistoryBatchSlice(
        **slice_fields,
        start_ordinal=1,
        batch_value_count=2,
        values=(sample,),
    )
    page = HistoryPage.create((first, second), next_cursor=None)
    before = page.to_dict()

    typed_value["nested"][0]["value"] = 99
    definition["type"]["name"] = "tampered"
    object.__setattr__(watch, "selector", "tampered.watch")
    object.__setattr__(sample, "typed_value", {"tampered": True})
    object.__setattr__(binding, "probe_id", "tampered-probe")
    object.__setattr__(batch, "sequence", 99)
    object.__setattr__(first, "sequence", 99)
    object.__setattr__(second, "values", ())

    assert page.to_dict() == before
    assert page.to_dict()["batches"][0]["binding"]["probeId"] == "probe-serial-1"
    assert page.to_dict()["batches"][0]["values"][0]["watch"] == {
        "kind": "variable", "expression": "telemetry.counter"
    }
    assert page.to_dict()["batches"][0]["values"][0]["typedValue"] == {
        "nested": [{"value": 7}]
    }
    assert page.to_dict()["batches"][0]["values"][0]["definition"] == {
        "type": {"name": "uint32"}
    }


def test_history_page_continuation_cursor_identifies_last_returned_ordinal() -> None:
    value = SampleValue(WatchItem.variable("counter"), "OK", typed_value=1)
    slice_ = _history_slice([value], start_ordinal=7, batch_value_count=16)

    with pytest.raises(ValueError, match="cursor"):
        HistoryPage.create((), next_cursor="1:7")
    with pytest.raises(ValueError, match="cursor"):
        HistoryPage.create((slice_,), next_cursor="1:8")

    assert HistoryPage.create((slice_,), next_cursor="1:7").next_cursor == "1:7"


def test_history_page_enforces_ten_thousand_value_and_four_mib_exact_budgets() -> None:
    ordinary = SampleValue(
        WatchItem.variable("counter"),
        "OK",
        typed_value={"type": "uint32", "value": 7},
    )
    too_many = tuple(
        _history_slice(
            [ordinary] * 256,
            batch_value_count=256,
            sequence=sequence,
        )
        for sequence in range(40)
    )
    with pytest.raises(ValueError, match="10,000"):
        HistoryPage.create(too_many, next_cursor=None)

    huge = SampleValue(
        WatchItem.variable("counter"),
        "OK",
        typed_value="x" * (1024 * 1024),
    )
    oversized = _history_slice([huge] * 4, batch_value_count=4)
    with pytest.raises(ValueError, match="4 MiB"):
        HistoryPage.create((oversized,), next_cursor=None)


def test_flatten_history_page_preserves_batch_value_count_and_value_ordinal() -> None:
    value = SampleValue(WatchItem.variable("counter"), "OK", typed_value=7)
    page = HistoryPage.create(
        (_history_slice([value], start_ordinal=7, batch_value_count=16),),
        next_cursor="1:7",
    )

    assert tuple(flatten_history_page(page))[0]["batchValueCount"] == 16
    assert tuple(flatten_history_page(page))[0]["valueOrdinal"] == 7


def test_history_protocol_serializes_ten_thousand_values_without_relaxing_generic_budget() -> None:
    slices: list[HistoryBatchSlice] = []
    remaining = 10_000
    sequence = 0
    while remaining:
        count = min(256, remaining)
        values = [
            SampleValue(
                WatchItem.variable(f"telemetry.channel_{sequence}_{ordinal}"),
                "OK",
                typed_value={"type": "uint32", "value": ordinal},
            )
            for ordinal in range(count)
        ]
        slices.append(
            _history_slice(
                values,
                batch_value_count=256,
                sequence=sequence,
            )
        )
        remaining -= count
        sequence += 1

    page = HistoryPage.create(slices, next_cursor="40:15")
    payload = success("history.query", page).to_dict()["data"]
    assert payload["valueCount"] == 10_000
    assert len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ) <= 4 * 1024 * 1024
    assert sum(len(item["values"]) for item in payload["batches"]) == 10_000

    with pytest.raises(ValueError, match="node limit"):
        success("generic.result", tuple(range(10_001)))


def test_protocol_and_sample_models_reject_nonfinite_oversized_and_xor_states() -> None:
    watch = WatchItem.variable("counter")
    for kwargs in (
        {"status": "OK", "typed_value": 1, "code": "MONITOR_FAILED"},
        {"status": "ERROR", "typed_value": 1, "code": "MONITOR_FAILED"},
        {"status": "ERROR", "typed_value": None, "code": None},
    ):
        with pytest.raises(ValueError):
            SampleValue(watch, **kwargs)

    value = SampleValue(watch, "OK", typed_value=1)
    base = dict(
        binding=_binding(), group_id=GROUP_ID, group_revision=1, run_id=RUN_ID,
        sequence=1, scheduled_unix_ns=100, captured_unix_ns=200, latency_ns=100,
        actual_rate_hz=4.0, subscriber_drops=0, history_drops=0, deadline_drops=0,
        values=(value,),
    )
    for update in (
        {"actual_rate_hz": math.nan},
        {"actual_rate_hz": math.inf},
        {"values": (value,) * 257},
        {"scheduled_unix_ns": 10**30, "captured_unix_ns": 10**30},
    ):
        with pytest.raises(ValueError):
            SampleBatch(**(base | update))


def test_json_parser_rejects_duplicate_normalized_keys_and_nonfinite_numbers() -> None:
    for document in (
        b'{"a":1,"a":2}',
        '{"Caf\u00e9":1,"Cafe\u0301":2}'.encode("utf-8"),
        b'{"value":NaN}',
        b'{"value":Infinity}',
    ):
        with pytest.raises(ProtocolViolation, match="invalid"):
            parse_json_object(document)
