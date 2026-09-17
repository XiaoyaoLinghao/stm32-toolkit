from __future__ import annotations

import hashlib

import pytest

from stm32_toolkit.monitor_analysis_contract import (
    NATIVE_ANALYSIS_REQUEST_SCHEMA,
    NativeAnalysisContractError,
    native_statistics,
    validate_native_request,
)
from stm32_toolkit.monitor_replay_contract import canonical_replay_json_bytes


def _reference(role: str, run_id: str) -> dict[str, object]:
    reference = {
        "schema": "stm32-monitor-run-ref/2",
        "operation_id": run_id,
        "scenario_role": role,
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "origin_workspace_id": "a" * 64,
        "import_workspace_id": "a" * 64,
        "logical_project_id": "123e4567-e89b-42d3-a456-426614174000",
        "origin_session_id": "session",
        "projected_session_id": "session",
        "origin_run_id": run_id,
        "projected_run_id": run_id,
        "target_device": "stm32f429zi",
        "probe_id": "b" * 64,
        "physical_target": "stm32f429zi",
        "build_id": "c" * 64,
        "elf_sha256": "d" * 64,
        "input_snapshot_sha256": "e" * 64,
        "git_head": "f" * 40,
        "git_dirty": False,
        "flash_session_id": "flash",
        "lease_id": "lease",
        "dwarf_sha256": "1" * 64,
        "svd_sha256": None,
        "group_id": "123e4567-e89b-42d3-a456-426614174001",
        "group_revision": 1,
        "start_sequence": 0,
        "end_sequence_exclusive": 2,
        "start_captured_unix_ns": 1,
        "end_captured_unix_ns_exclusive": 3,
        "source_record_sha256": "2" * 64,
        "projected_batch_sha256s": ["3" * 64, "4" * 64],
        "transcript_evidence_id": "5" * 64,
        "run_ref_sha256": "6" * 64,
    }
    reference["run_ref_sha256"] = hashlib.sha256(
        canonical_replay_json_bytes(
            {key: value for key, value in reference.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()
    return reference


def _request() -> dict[str, object]:
    return {
        "schema": NATIVE_ANALYSIS_REQUEST_SCHEMA,
        "before_run": _reference("failed-before", "123e4567-e89b-42d3-a456-426614174010"),
        "after_run": _reference("fixed-after", "123e4567-e89b-42d3-a456-426614174011"),
        "selector_kind": "register",
        "selector": "r0",
        "alignment": "bounded-run-relative",
        "minimum_valid_pairs": 2,
        "scalar_policy": "native-uint-register/1",
        "max_pairing_skew_ns": 5,
    }


def _batch(timestamp: int, value: object, *, width: int = 8, status: str = "OK") -> dict[str, object]:
    typed = {
        "bitWidth": width,
        "expression": "r0",
        "rawHex": f"0x{int(value):0{width // 4}x}",
        "typeName": f"uint{width}_register",
        "value": value,
    }
    return {
        "scheduledUnixNs": timestamp,
        "values": [{
            "watch": {"kind": "register", "registerPath": "r0"},
            "status": status,
            "typedValue": typed if status == "OK" else None,
        }],
    }


def test_native_request_is_closed_and_requires_physical_v2_refs() -> None:
    request = _request()
    assert validate_native_request(request) is request

    malformed = dict(request)
    malformed["max_pairing_skew_ns"] = True
    with pytest.raises(NativeAnalysisContractError):
        validate_native_request(malformed)

    replay = dict(request)
    replay["before_run"] = dict(request["before_run"])
    replay["before_run"]["execution_source"] = "replay"
    with pytest.raises(NativeAnalysisContractError):
        validate_native_request(replay)


def test_native_alignment_is_inclusive_and_preserves_before_time_order() -> None:
    result = native_statistics(
        [_batch(100, 10), _batch(110, 20)],
        # The absolute starts differ by 400 ns.  Pairing is relative to each
        # run's first scheduled timestamp, so the second pair is exactly on
        # the inclusive five-nanosecond boundary (10 versus 15 ns).
        [_batch(500, 11), _batch(515, 25)],
        selector="r0",
        max_pairing_skew_ns=5,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )

    assert result["aligned_position_count"] == 2
    assert result["aligned_pair_count"] == 2
    assert result["excluded_position_count"] == 0
    assert result["before_first"] == 10
    assert result["before_last"] == 20
    assert result["after_first"] == 11
    assert result["after_last"] == 25
    assert result["quality"] == "VALID"


def test_native_alignment_excludes_relative_skew_above_inclusive_boundary() -> None:
    result = native_statistics(
        [_batch(100, 10), _batch(110, 20)],
        [_batch(500, 11), _batch(516, 25)],
        selector="r0",
        max_pairing_skew_ns=5,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )

    assert result["aligned_position_count"] == 3
    assert result["aligned_pair_count"] == 1
    assert result["excluded_position_count"] == 2
    assert result["quality"] == "INVALID"


def test_native_ambiguous_edges_are_rejected_before_value_filtering() -> None:
    result = native_statistics(
        [_batch(100, 10), _batch(102, 20)],
        [_batch(102, 30)],
        selector="r0",
        max_pairing_skew_ns=3,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )
    assert result["aligned_position_count"] == 3
    assert result["aligned_pair_count"] == 0
    assert result["excluded_position_count"] == 3
    assert result["quality"] == "INVALID"


def test_native_ambiguous_edges_are_not_resolved_by_an_invalid_native_value() -> None:
    result = native_statistics(
        # The invalid before endpoint is still a time-pair candidate. If an
        # implementation filters values before resolving edges, the after
        # endpoint would appear to have one unique partner incorrectly.
        [_batch(100, 10, status="ERROR"), _batch(102, 20)],
        [_batch(102, 30)],
        selector="r0",
        max_pairing_skew_ns=3,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )

    assert result["aligned_position_count"] == 3
    assert result["aligned_pair_count"] == 0
    assert result["excluded_position_count"] == 3
    assert result["quality"] == "INVALID"


def test_native_invalid_value_and_width_are_excluded_after_time_pairing() -> None:
    result = native_statistics(
        [_batch(100, 10), _batch(110, 20)],
        [_batch(100, 10, width=16), _batch(110, 25, status="ERROR")],
        selector="r0",
        max_pairing_skew_ns=1,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )
    assert result["aligned_position_count"] == 2
    assert result["aligned_pair_count"] == 0
    assert result["excluded_position_count"] == 2
    assert result["quality"] == "INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("value", True),
        ("value", -1),
        ("value", 256),
        ("rawHex", "0X0a"),
        ("rawHex", "0x0A"),
        ("rawHex", "0x0a0"),
        ("typeName", "uint16_register"),
        ("expression", "r1"),
        ("bitWidth", 64),
    ),
)
def test_native_typed_register_shape_and_range_are_strict(
    field: str, value: object
) -> None:
    before = [_batch(100, 10), _batch(110, 20)]
    after = [_batch(100, 11), _batch(110, 21)]
    typed = after[0]["values"][0]["typedValue"]
    assert isinstance(typed, dict)
    typed[field] = value

    result = native_statistics(
        before,
        after,
        selector="r0",
        max_pairing_skew_ns=1,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )
    assert result["aligned_position_count"] == 2
    assert result["aligned_pair_count"] == 1
    assert result["excluded_position_count"] == 1
    assert result["quality"] == "INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("selector_kind", "variable"),
        ("selector", ""),
        ("alignment", "run-relative"),
        ("scalar_policy", "native-uint-register/0"),
        ("minimum_valid_pairs", True),
        ("minimum_valid_pairs", 1),
        ("minimum_valid_pairs", 10_001),
        ("max_pairing_skew_ns", True),
        ("max_pairing_skew_ns", 0),
        ("max_pairing_skew_ns", 5_000_001),
        ("max_pairing_skew_ns", 1.0),
    ),
)
def test_native_request_policy_boundaries_are_closed(field: str, value: object) -> None:
    malformed = _request()
    malformed[field] = value
    with pytest.raises(NativeAnalysisContractError):
        validate_native_request(malformed)


def test_native_timestamps_must_increase_strictly() -> None:
    with pytest.raises(NativeAnalysisContractError):
        native_statistics(
            [_batch(100, 1), _batch(100, 2)],
            [_batch(100, 1), _batch(101, 2)],
            selector="r0",
            max_pairing_skew_ns=1,
            minimum_valid_pairs=2,
            request_digest="a" * 64,
        )
