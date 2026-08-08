from __future__ import annotations

import json
import math
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
    ProtocolResult,
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
        workspace_id="c" * 24,
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


def test_protocol_result_validates_invariants_and_known_models_only() -> None:
    group = WatchGroup.create("G", "", 250, (), group_id=GROUP_ID, now=NOW)
    result = success("groups.list", (group,))
    assert result.data == (group,)
    assert result.to_dict()["data"] == [group.to_dict()]

    invalid_results = (
        (1, "groups.list", "OK", "", None),
        (True, "", "OK", "", None),
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

    class CustomValue:
        calls = 0

        def to_dict(self) -> dict[str, object]:
            self.calls += 1
            return {"unsafe": True}

    custom = CustomValue()
    with pytest.raises((TypeError, ValueError)):
        success("custom", custom)
    assert custom.calls == 0


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
