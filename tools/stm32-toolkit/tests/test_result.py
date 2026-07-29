from types import MappingProxyType

import pytest

from stm32_toolkit.result import OperationResult


def test_success_result_has_stable_envelope():
    result = OperationResult.success("project.detect", {"kind": "keil"})
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "operation": "project.detect",
        "code": "OK",
        "message": "",
        "data": {"kind": "keil"},
        "details": {},
    }


def test_failure_result_has_machine_readable_code():
    result = OperationResult.failure(
        "project.load", "PROJECT_SCHEMA_INVALID", "Project manifest is invalid",
        {"field": "logicalProjectId"},
    )
    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["code"] == "PROJECT_SCHEMA_INVALID"
    assert payload["details"] == {"field": "logicalProjectId"}


def test_success_result_snapshots_json_style_data():
    data = {"items": [{"name": "initial"}], "kind": "keil"}
    result = OperationResult.success("project.detect", data)

    data["items"][0]["name"] = "mutated"
    data["items"].append({"name": "later"})

    assert result.to_dict()["data"] == {
        "items": [{"name": "initial"}],
        "kind": "keil",
    }
    with pytest.raises(TypeError):
        result.data["items"] = []


def test_failure_result_snapshots_and_does_not_expose_mutable_details():
    details = {"field": {"name": "initial"}}
    result = OperationResult.failure("project.load", "INVALID", "Invalid project", details)

    details["field"]["name"] = "mutated"

    assert result.to_dict()["details"] == {"field": {"name": "initial"}}
    with pytest.raises(TypeError):
        result.details["field"] = {}


def test_failure_result_serializes_mapping_proxy_details():
    details = MappingProxyType({"field": "logicalProjectId"})

    result = OperationResult.failure("project.load", "INVALID", "Invalid project", details)

    assert result.to_dict()["details"] == {"field": "logicalProjectId"}


def test_success_result_rejects_nested_set_data():
    with pytest.raises(TypeError, match="set and frozenset values are not supported"):
        OperationResult.success("project.detect", {"targets": {"keil"}})


def test_success_result_rejects_nested_frozenset_data():
    with pytest.raises(TypeError, match="set and frozenset values are not supported"):
        OperationResult.success("project.detect", {"targets": frozenset({"keil"})})


def test_failure_result_rejects_nested_set_details():
    with pytest.raises(TypeError, match="set and frozenset values are not supported"):
        OperationResult.failure("project.load", "INVALID", "Invalid project", {"targets": {"keil"}})


def test_failure_result_rejects_nested_frozenset_details():
    with pytest.raises(TypeError, match="set and frozenset values are not supported"):
        OperationResult.failure(
            "project.load",
            "INVALID",
            "Invalid project",
            {"targets": frozenset({"keil"})},
        )
