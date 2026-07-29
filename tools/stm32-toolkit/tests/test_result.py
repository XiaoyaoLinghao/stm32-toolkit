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
