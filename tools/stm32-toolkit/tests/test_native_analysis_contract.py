from __future__ import annotations

from copy import deepcopy
import hashlib
from types import SimpleNamespace

import pytest

from stm32_toolkit.monitor_analysis_contract import (
    NATIVE_ANALYSIS_REQUEST_SCHEMA,
    NativeAnalysisContractError,
    evaluate_physical_monitor_fact,
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


def _fact_batch(
    timestamp: int,
    value: int,
    *,
    selector_kind: str = "register",
    selector: str = "r0",
    width: int = 8,
) -> dict[str, object]:
    if selector_kind == "variable":
        watch = {"kind": "variable", "expression": selector}
        type_name = "long unsigned int"
        width = 32
    else:
        watch = {"kind": "register", "registerPath": selector}
        type_name = f"uint{width}_register"
    sample = {
        "watch": watch,
        "status": "OK",
        "typedValue": {
            "bitWidth": width,
            "expression": selector,
            "rawHex": f"0x{value:0{width // 4}x}",
            "typeName": type_name,
            "value": value,
        },
        "code": None,
        "definition": {"kind": selector_kind, "selector": selector},
    }
    return {"scheduledUnixNs": timestamp, "values": [sample]}


def _object_batch(timestamp: int, value: int) -> SimpleNamespace:
    payload = _batch(timestamp, value)
    sample = payload["values"][0]
    return SimpleNamespace(
        scheduledUnixNs=payload["scheduledUnixNs"],
        values=[SimpleNamespace(**sample)],
    )


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


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing-field", "native analysis request fields are not closed"),
        ("extra-field", "native analysis request fields are not closed"),
        ("schema", "native analysis request schema is invalid"),
    ),
    ids=("missing-field", "extra-field", "schema"),
)
def test_native_request_rejects_public_wire_shape_and_schema(
    mutation: str, message: str
) -> None:
    malformed = _request()
    if mutation == "missing-field":
        del malformed["max_pairing_skew_ns"]
    elif mutation == "extra-field":
        malformed["unexpected"] = True
    else:
        malformed["schema"] = "stm32-monitor-analysis-request/9"

    with pytest.raises(NativeAnalysisContractError) as error:
        validate_native_request(malformed)

    assert str(error.value) == message


@pytest.mark.parametrize(
    "mutation",
    (
        "mapping-missing-watch",
        "object-missing-watch",
        "watch-extra",
        "typed-extra",
        "typed-raw-mismatch",
    ),
)
def test_native_statistics_excludes_malformed_nested_public_samples(
    mutation: str,
) -> None:
    before: object = _batch(100, 10)
    after: object = _batch(200, 11)
    if mutation == "mapping-missing-watch":
        assert isinstance(after, dict)
        after["values"] = [{"status": "OK"}]
    elif mutation == "object-missing-watch":
        after = SimpleNamespace(
            scheduledUnixNs=200,
            values=[SimpleNamespace(status="OK")],
        )
    else:
        assert isinstance(after, dict)
        sample = after["values"][0]
        assert isinstance(sample, dict)
        if mutation == "watch-extra":
            sample["watch"]["unexpected"] = True
        elif mutation == "typed-extra":
            sample["typedValue"]["unexpected"] = True
        else:
            sample["typedValue"]["rawHex"] = "0x0a"

    before_snapshot = deepcopy(before)
    after_snapshot = deepcopy(after)
    result = native_statistics(
        [before],
        [after],
        selector="r0",
        max_pairing_skew_ns=1,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )

    assert result["quality"] == "INVALID"
    assert result["conclusion"] == "INCONCLUSIVE"
    assert result["aligned_position_count"] == 2
    assert result["aligned_pair_count"] == 0
    assert result["excluded_position_count"] == 2
    assert before == before_snapshot
    assert after == after_snapshot


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


def test_native_statistics_accepts_supported_object_shaped_batches() -> None:
    result = native_statistics(
        [_object_batch(100, 10), _object_batch(110, 20)],
        [_object_batch(500, 11), _object_batch(515, 25)],
        selector="r0",
        max_pairing_skew_ns=5,
        minimum_valid_pairs=2,
        request_digest="a" * 64,
    )
    assert result["quality"] == "VALID"
    assert result["changed"] is True


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


def test_physical_monitor_facts_recompute_strict_register_and_variable_values() -> None:
    register_batches = [_fact_batch(100 + index, value) for index, value in enumerate((0, 1, 0))]
    assert evaluate_physical_monitor_fact(
        register_batches,
        selector_kind="register",
        selector="r0",
        fact="value-varies",
        minimum_valid_samples=3,
    ) == 1
    assert evaluate_physical_monitor_fact(
        register_batches,
        selector_kind="register",
        selector="r0",
        fact="bit-values-mask",
        minimum_valid_samples=3,
        bit_index=0,
    ) == 3

    variable_batches = [
        _fact_batch(200 + index, value, selector_kind="variable", selector="counter")
        for index, value in enumerate((7, 7))
    ]
    assert evaluate_physical_monitor_fact(
        variable_batches,
        selector_kind="variable",
        selector="counter",
        fact="value-varies",
        minimum_valid_samples=2,
    ) == 0


@pytest.mark.parametrize(
    ("selector_kind", "fact", "minimum", "bit_index", "batches"),
    [
        ("other", "value-varies", 1, None, [_fact_batch(100, 1)]),
        ("register", "other", 1, None, [_fact_batch(100, 1)]),
        ("register", "value-varies", True, None, [_fact_batch(100, 1)]),
        ("register", "value-varies", 0, None, [_fact_batch(100, 1)]),
        ("register", "value-varies", 1, 0, [_fact_batch(100, 1)]),
        ("variable", "bit-values-mask", 1, 0, [_fact_batch(100, 1, selector_kind="variable")]),
        ("register", "bit-values-mask", 1, True, [_fact_batch(100, 1)]),
        ("register", "bit-values-mask", 1, -1, [_fact_batch(100, 1)]),
        ("register", "bit-values-mask", 1, 32, [_fact_batch(100, 1)]),
        ("register", "bit-values-mask", 1, 8, [_fact_batch(100, 1)]),
        ("register", "value-varies", 2, None, [_fact_batch(100, 1)]),
        ("register", "value-varies", 1_025, None, [_fact_batch(100, 1)]),
        ("register", "value-varies", 1, None, "invalid"),
        ("register", "value-varies", 1, None, []),
    ],
)
def test_physical_monitor_fact_policy_and_window_refusals(
    selector_kind: str,
    fact: str,
    minimum: int,
    bit_index: int | None,
    batches: object,
) -> None:
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            batches,
            selector_kind=selector_kind,
            selector="counter" if selector_kind == "variable" else "r0",
            fact=fact,
            minimum_valid_samples=minimum,
            bit_index=bit_index,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "values-shape",
        "non-mapping-sample",
        "missing-selector",
        "duplicate-selector",
        "watch-extra",
        "sample-extra",
        "sample-status",
        "sample-code",
        "typed-missing",
        "typed-extra",
        "typed-expression",
        "typed-width",
        "typed-type",
        "typed-value",
        "typed-raw",
        "definition-extra",
        "definition-selector",
    ),
)
def test_physical_monitor_fact_rejects_malformed_selected_wire_samples(
    mutation: str,
) -> None:
    batch = _fact_batch(100, 1)
    if mutation == "values-shape":
        batch["values"] = "invalid"
    elif mutation == "non-mapping-sample":
        source = batch["values"][0]
        batch["values"] = [SimpleNamespace(**source)]
    else:
        values = batch["values"]
        assert isinstance(values, list)
        sample = values[0]
        assert isinstance(sample, dict)
        if mutation == "missing-selector":
            sample["watch"]["registerPath"] = "r1"
        elif mutation == "duplicate-selector":
            values.append(deepcopy(sample))
        elif mutation == "watch-extra":
            sample["watch"]["unexpected"] = True
        elif mutation == "sample-extra":
            sample["unexpected"] = True
        elif mutation == "sample-status":
            sample["status"] = "ERROR"
        elif mutation == "sample-code":
            sample["code"] = "NATIVE_ERROR"
        elif mutation == "typed-missing":
            sample["typedValue"].pop("rawHex")
        elif mutation == "typed-extra":
            sample["typedValue"]["unexpected"] = True
        elif mutation == "typed-expression":
            sample["typedValue"]["expression"] = "r1"
        elif mutation == "typed-width":
            sample["typedValue"]["bitWidth"] = 64
        elif mutation == "typed-type":
            sample["typedValue"]["typeName"] = "uint16_register"
        elif mutation == "typed-value":
            sample["typedValue"]["value"] = True
        elif mutation == "typed-raw":
            sample["typedValue"]["rawHex"] = "0x02"
        elif mutation == "definition-extra":
            sample["definition"]["unexpected"] = True
        elif mutation == "definition-selector":
            sample["definition"]["selector"] = "r1"

    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            [batch],
            selector_kind="register",
            selector="r0",
            fact="value-varies",
            minimum_valid_samples=1,
        )


def test_physical_monitor_fact_rejects_conflicting_widths_and_preserves_input() -> None:
    batches = [_fact_batch(100, 1, width=8), _fact_batch(101, 2, width=16)]
    before = deepcopy(batches)
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            batches,
            selector_kind="register",
            selector="r0",
            fact="value-varies",
            minimum_valid_samples=2,
        )
    assert batches == before


@pytest.mark.parametrize("selector", ["", "e\u0301", "line\nfeed"])
def test_physical_monitor_fact_rejects_noncanonical_selectors(selector: str) -> None:
    with pytest.raises(NativeAnalysisContractError):
        evaluate_physical_monitor_fact(
            [_fact_batch(100, 1)],
            selector_kind="register",
            selector=selector,
            fact="value-varies",
            minimum_valid_samples=1,
        )


@pytest.mark.parametrize(
    ("before", "after", "request_digest"),
    [
        ([], [_batch(100, 1)], "a" * 64),
        ([{"scheduledUnixNs": 100, "values": "invalid"}], [_batch(100, 1)], "a" * 64),
        ([{"scheduledUnixNs": True, "values": []}], [_batch(100, 1)], "a" * 64),
        ([{"scheduledUnixNs": -1, "values": []}], [_batch(100, 1)], "a" * 64),
        ([_batch(100, 1)], [_batch(100, 1)], "a" * 63),
    ],
)
def test_native_statistics_rejects_malformed_timestamp_windows_and_digest(
    before: object,
    after: object,
    request_digest: str,
) -> None:
    with pytest.raises(NativeAnalysisContractError):
        native_statistics(
            before,
            after,
            selector="r0",
            max_pairing_skew_ns=1,
            minimum_valid_pairs=2,
            request_digest=request_digest,
        )


@pytest.mark.parametrize(
    ("before", "after", "max_pairing_skew_ns", "minimum_valid_pairs", "request_digest", "message"),
    (
        (
            object(),
            [_batch(100, 1)],
            1,
            2,
            "a" * 64,
            "before batches are invalid",
        ),
        (
            [_batch(100, 1)],
            [_batch(100, 1)],
            True,
            2,
            "a" * 64,
            "native analysis pairing skew is invalid",
        ),
        (
            [_batch(100, 1)],
            [_batch(100, 1)],
            1,
            True,
            "a" * 64,
            "native analysis minimum pair count is invalid",
        ),
        (
            [_batch(100, 1)],
            [_batch(100, 1)],
            1,
            2,
            True,
            "native analysis request digest is invalid",
        ),
    ),
    ids=("batches", "pairing-skew", "minimum-pairs", "request-digest"),
)
def test_native_statistics_rejects_public_argument_domain_errors(
    before: object,
    after: object,
    max_pairing_skew_ns: object,
    minimum_valid_pairs: object,
    request_digest: object,
    message: str,
) -> None:
    with pytest.raises(NativeAnalysisContractError) as error:
        native_statistics(
            before,
            after,
            selector="r0",
            max_pairing_skew_ns=max_pairing_skew_ns,  # type: ignore[arg-type]
            minimum_valid_pairs=minimum_valid_pairs,  # type: ignore[arg-type]
            request_digest=request_digest,  # type: ignore[arg-type]
        )
    assert str(error.value) == message


def test_native_request_expected_reference_guards_reject_drift() -> None:
    request = _request()
    expected_before = dict(request["before_run"])
    expected_before["group_revision"] = 2
    expected_after = dict(request["after_run"])
    expected_after["target_device"] = "other-target"

    with pytest.raises(NativeAnalysisContractError):
        validate_native_request(request, expected_before=expected_before)
    with pytest.raises(NativeAnalysisContractError):
        validate_native_request(request, expected_after=expected_after)
    assert request["before_run"]["group_revision"] == 1
    assert request["after_run"]["target_device"] == "stm32f429zi"


def test_native_statistics_rejects_value_and_position_budget_overflows() -> None:
    oversized_values = _batch(100, 1)
    sample = oversized_values["values"][0]
    oversized_values["values"] = [sample] * 10_001
    with pytest.raises(NativeAnalysisContractError) as error:
        native_statistics(
            [oversized_values],
            [_batch(200, 1)],
            selector="r0",
            max_pairing_skew_ns=1,
            minimum_valid_pairs=2,
            request_digest="a" * 64,
        )
    assert str(error.value) == "before values exceed their limit"
    # Each side is bounded to 1,024 positions by _timestamps, so the
    # combined 2,048-position guard is unreachable through the public caller.
