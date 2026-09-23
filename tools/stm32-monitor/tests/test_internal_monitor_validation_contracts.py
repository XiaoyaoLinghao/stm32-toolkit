"""Bounded internal-pure Monitor validation contracts.

These tests measure named in-memory guards only.  Their inputs are either
publicly constructed models or untrusted offline wire values; no Evidence
roots, authority records, or physical publication path is used.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from multidict import MultiDict
import pytest

import stm32_monitor.analysis as analysis_module
import stm32_monitor.analysis_workflows as analysis_workflows_module
from stm32_monitor.models import SampleValue
import stm32_monitor.replay as replay_module
from stm32_monitor.analysis import ANALYSIS_REQUEST_INVALID, AnalysisError
from stm32_monitor.replay import MonitorReplayError
from test_analysis import (
    COUNTER,
    _case,
    _native_physical_source,
)


def test_analysis_workflow_error_constructor_preserves_valid_wire_and_rejects_invalid_fields() -> None:
    valid = analysis_workflows_module.AnalysisWorkflowError(
        analysis_workflows_module.ANALYSIS_WORKFLOW_INVALID,
        "valid analysis workflow error",
    )
    assert valid.code == analysis_workflows_module.ANALYSIS_WORKFLOW_INVALID
    assert valid.message == "valid analysis workflow error"

    with pytest.raises(ValueError, match="unknown analysis workflow error code"):
        analysis_workflows_module.AnalysisWorkflowError("UNKNOWN", "valid")

    with pytest.raises(ValueError, match="analysis workflow error message is invalid"):
        analysis_workflows_module.AnalysisWorkflowError(
            analysis_workflows_module.ANALYSIS_WORKFLOW_INVALID,
            "",
        )

    with pytest.raises(ValueError, match="analysis workflow error message is invalid"):
        analysis_workflows_module.AnalysisWorkflowError(
            analysis_workflows_module.ANALYSIS_WORKFLOW_INVALID,
            "x" * 257,
        )


def test_validate_window_uses_real_canonicalizer_and_rejects_invalid_reference(tmp_path) -> None:
    paths, _, _, before_batches, _, before_reference, _ = _case(tmp_path)
    del paths
    original_batches = tuple(batch.to_dict() for batch in before_batches)

    checked = analysis_module._validate_window(before_reference, before_batches)
    assert checked == before_batches

    with pytest.raises(AnalysisError) as error:
        analysis_module._validate_window(None, before_batches)
    assert error.value.code == ANALYSIS_REQUEST_INVALID
    assert error.value.message == "analysis run reference is invalid"
    assert tuple(batch.to_dict() for batch in before_batches) == original_batches


def test_trusted_sample_rejects_non_nfc_type_directly(tmp_path) -> None:
    paths, _, _, before_batches, _, _, _ = _case(tmp_path)
    del paths
    non_nfc_type = "e\u0301"
    assert unicodedata.normalize("NFC", non_nfc_type) != non_nfc_type

    sample = SampleValue(
        COUNTER,
        "OK",
        typed_value={"type": non_nfc_type, "value": 7},
    )
    checked_batch = replace(before_batches[0], values=(sample,))
    before_wire = checked_batch.to_dict()

    assert analysis_module._trusted_sample(checked_batch, COUNTER) is None
    assert checked_batch.to_dict() == before_wire


@pytest.mark.parametrize(
    ("value", "message"),
    (
        (float("nan"), "not finite"),
        ((), "must not contain tuples"),
    ),
    ids=("nonfinite-float", "tuple-container"),
)
def test_physical_json_copy_rejects_non_json_values_with_default_limits(
    value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replay_module._physical_copy_json(value)


def test_physical_json_copy_rejects_default_bookkeeping_cycles_and_preserves_valid_values() -> None:
    valid = {"items": [None, True, 1, 1.5, "text"]}
    assert replay_module._physical_copy_json(valid) == valid

    cyclic_list: list[Any] = []
    cyclic_list.append(cyclic_list)
    with pytest.raises(ValueError, match="contains a cycle"):
        replay_module._physical_copy_json(cyclic_list)

    cyclic_mapping: dict[str, Any] = {}
    cyclic_mapping["self"] = cyclic_mapping
    with pytest.raises(ValueError, match="contains a cycle"):
        replay_module._physical_copy_json(cyclic_mapping)


def test_physical_json_copy_rejects_duplicate_keys_from_real_multidict_mapping() -> None:
    duplicate_mapping = MultiDict([("a", 1), ("a", 2)])
    assert isinstance(duplicate_mapping, Mapping)
    assert list(duplicate_mapping.items()) == [("a", 1), ("a", 2)]

    with pytest.raises(ValueError, match="physical transcript JSON key is duplicated"):
        replay_module._physical_copy_json(duplicate_mapping)


def _physical_batches() -> tuple[str, tuple[object, ...]]:
    operation_id = "55555555-5555-4555-8555-555555555555"
    group_id = "66666666-6666-4666-8666-666666666666"
    _, batches = _native_physical_source(
        role="failed-before",
        operation_id=operation_id,
        group_id=group_id,
        values=(1, 2),
    )
    return operation_id, batches


def test_physical_transcript_wire_is_untrusted_plain_wire_and_rejects_empty_history() -> None:
    operation_id, batches = _physical_batches()
    wire = replay_module._physical_transcript_wire(
        scenario_role="failed-before",
        test_run_id=operation_id,
        batches=batches,
    )

    assert type(wire) is dict
    assert wire["execution_source"] == "physical"
    assert wire["physical_transport_evidence"] is True
    assert wire["test_run_id"] == operation_id
    assert wire["batches"] == [batch.to_dict() for batch in batches]

    with pytest.raises(MonitorReplayError) as error:
        replay_module._physical_transcript_wire(
            scenario_role="failed-before",
            test_run_id=operation_id,
            batches=(),
        )
    assert error.value.code == replay_module.INCOMPATIBLE_IDENTITY
    assert error.value.message == "physical history window is empty"


def test_physical_json_decoder_returns_untrusted_wire_and_rejects_non_bytes() -> None:
    operation_id, batches = _physical_batches()
    wire = replay_module._physical_transcript_wire(
        scenario_role="failed-before",
        test_run_id=operation_id,
        batches=batches,
    )
    raw = replay_module.canonical_physical_json_bytes(wire)

    decoded = replay_module._decode_physical_json_bytes(raw)
    assert decoded == wire

    with pytest.raises(replay_module.ReplayContractError) as error:
        replay_module._decode_physical_json_bytes(bytearray(raw))
    assert str(error.value) == "physical transcript bytes exceed their size limit"
