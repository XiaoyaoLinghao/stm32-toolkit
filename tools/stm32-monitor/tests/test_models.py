from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.models import (
    MonitorConfig,
    ObservationBinding,
    ProbeConnectRequest,
    SampleBatch,
    SampleValue,
    WatchGroup,
    WatchItem,
)
from stm32_monitor.protocol import (
    MONITOR_PROTOCOL_VERSION,
    ProtocolViolation,
    failure,
    parse_json_object,
    success,
)


NOW = datetime(2026, 8, 8, 1, 2, 3, tzinfo=timezone.utc)
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _config(tmp_path: Path) -> MonitorConfig:
    project = tmp_path / "project"
    project.mkdir()
    return MonitorConfig(project, tmp_path / "state", "monitor-1")


def _binding() -> ObservationBinding:
    return ObservationBinding(
        workspace_id="w" * 64,
        logical_project_id="33333333-3333-4333-8333-333333333333",
        session_id="monitor-1",
        probe_id="probe-serial-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="i" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256="s" * 64,
    )


def test_monitor_config_canonicalizes_external_roots_without_creating_state(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.project_root == (tmp_path / "project").resolve()
    assert config.data_root == (tmp_path / "state").resolve()
    assert config.session_id == "monitor-1"
    assert not config.data_root.exists()


def test_monitor_config_rejects_state_inside_project_and_unsafe_session(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(ValueError, match="outside"):
        MonitorConfig(project, project / ".state", "monitor-1")
    with pytest.raises(ValueError, match="session"):
        MonitorConfig(project, tmp_path / "state", "../escape")


def test_probe_request_requires_exact_nonempty_pins() -> None:
    request = ProbeConnectRequest("probe-serial-1", "b" * 64, "e" * 64)
    assert request.to_dict() == {
        "probeId": "probe-serial-1",
        "expectedBuildId": "b" * 64,
        "expectedElfSha256": "e" * 64,
    }

    for values in (("", "b" * 64, "e" * 64), ("p", "bad", "e" * 64), ("p", "b" * 64, "bad")):
        with pytest.raises(ValueError):
            ProbeConnectRequest(*values)


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
    bad = failure("groups.create", "MONITOR_REQUEST_INVALID", "invalid request", details)
    details["field"].append("changed")
    good = success("groups.list", {"groups": []})

    assert bad.protocol == MONITOR_PROTOCOL_VERSION == "stm32-toolkit-monitor/1"
    assert bad.to_dict()["details"] == {"field": ["name"]}
    assert good.ok is True and good.code == "OK"
    json.dumps(bad.to_dict())


def test_protocol_json_parser_is_bounded_and_requires_an_object() -> None:
    assert parse_json_object(b'{"name":"g"}', limit=64) == {"name": "g"}

    for payload in (b"[]", b"not-json", b'{"name":"' + b"x" * 64 + b'"}'):
        with pytest.raises(ProtocolViolation) as raised:
            parse_json_object(payload, limit=64)
        assert raised.value.code in {"MONITOR_REQUEST_INVALID", "MONITOR_IMPORT_INVALID"}

