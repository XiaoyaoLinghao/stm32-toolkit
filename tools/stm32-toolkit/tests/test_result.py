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


def make_build_report():
    from stm32_toolkit.build import BuildReport, FirmwareIdentity, MemoryUsage

    return BuildReport(
        identity=FirmwareIdentity(
            schema_version=1,
            build_id="a" * 64,
            logical_project_id="12345678-1234-5678-1234-567812345678",
            toolkit_version="0.2.0",
            git_head="b" * 40,
            git_dirty=False,
            input_snapshot_sha256="c" * 64,
            newest_input_mtime_ns=123456789,
            target_device="STM32F407VGTx",
            preset="arm-debug",
            elf_path="build/arm-debug/firmware.elf",
            elf_sha256="d" * 64,
            elf_size=512,
            map_path="build/arm-debug/firmware.map",
            map_sha256="e" * 64,
            entry_point=0x08000011,
            vector_address=0x08000000,
            reset_handler_address=0x08000011,
            built_at_utc="2026-08-06T08:00:00.000000Z",
        ),
        memory=(
            MemoryUsage(
                name="FLASH", origin=0x08000000, length=0x100000, used=576, free=1048000
            ),
        ),
        warnings=(),
        build_log_path="artifacts/migration/build.log",
        build_result_path="artifacts/migration/build-result.json",
        identity_path="build/arm-debug/firmware-identity.json",
        configure_duration_ms=10,
        build_duration_ms=20,
    )


def test_typed_build_report_data_is_json_serializable_and_snapshotted():
    import json

    report = make_build_report()
    result = OperationResult.success("build", report)

    assert result.data is report
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["data"]["identity"]["buildId"] == report.identity.build_id
    assert payload["data"]["identity"]["elfPath"] == "build/arm-debug/firmware.elf"
    assert payload["data"]["memory"] == [
        {
            "name": "FLASH",
            "origin": 0x08000000,
            "length": 0x100000,
            "used": 576,
            "free": 1048000,
        }
    ]


def test_captured_payload_snapshot_survives_later_mutation_of_returned_mapping():
    import json

    report = make_build_report()
    result = OperationResult.success("build", report)
    returned = report.to_dict()
    returned["identity"]["gitHead"] = "f" * 40
    returned["warnings"].append("later")

    snapshot = result.to_dict()["data"]
    assert snapshot["identity"]["gitHead"] == "b" * 40
    assert snapshot["warnings"] == []
    assert json.dumps(result.to_dict())

    # to_dict() returns a fresh ordinary mapping on every call
    first = result.to_dict()["data"]
    first["identity"]["gitHead"] = "g" * 40
    assert result.to_dict()["data"]["identity"]["gitHead"] == "b" * 40
