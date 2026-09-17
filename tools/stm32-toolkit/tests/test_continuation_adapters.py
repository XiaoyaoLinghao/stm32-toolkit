from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from stm32_toolkit import cli, mcp_server
from stm32_toolkit.result import OperationResult


REQUEST = {
    "schema": "stm32-physical-continuation-request/1",
    "kind": "reuse",
    "continuationEvidenceId": "a" * 64,
}
ATTEMPT_ID = "00000000-0000-4000-8000-000000000011"


def test_begin_cli_and_mcp_preserve_closed_continuation(tmp_path, monkeypatch, capsys):
    calls = []

    def begin(context, **kwargs):
        calls.append((context, kwargs))
        return OperationResult.success("acceptance.attempt.begin", {"attempt": {}})

    monkeypatch.setattr(cli, "begin_acceptance_attempt", begin)
    monkeypatch.setattr(mcp_server, "begin_acceptance_attempt", begin)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(REQUEST), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    assert cli.main([
        "scenario", "attempt", "begin", "--project", str(project),
        "--data-root", str(tmp_path / "data"), "--session-id", "before-session",
        "--attempt-id", ATTEMPT_ID, "--scenario-id", "legacy-keil-physical-repair",
        "--scenario-version", "1", "--continuation-file", str(request_path),
    ]) == 0
    capsys.readouterr()
    server = mcp_server.create_server(project, tmp_path / "data", "before-session")
    _, result = asyncio.run(server.call_tool("stm32_acceptance_attempt_begin", {
        "attemptId": ATTEMPT_ID, "scenarioId": "legacy-keil-physical-repair",
        "scenarioVersion": "1", "continuation": REQUEST,
    }))
    assert result["ok"]
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1] == {
        "attempt_id": ATTEMPT_ID, "scenario_id": "legacy-keil-physical-repair",
        "scenario_version": "1", "continuation": REQUEST,
    }
    assert all(context.session_id == "before-session" for context, _ in calls)


@pytest.mark.parametrize("change", [
    {"authorized": True}, {"kind": "bind"}, {"continuationEvidenceId": "not-a-digest"},
    {"schema": "stm32-physical-continuation-request/2"},
])
def test_mcp_continuation_rejects_unknown_mixed_and_invalid_fields(change):
    with pytest.raises(ValidationError):
        TypeAdapter(mcp_server.ContinuationInput).validate_python({**REQUEST, **change})


def test_mcp_plan_v2_requires_proof_and_v1_rejects_it():
    from stm32_toolkit.diagnostics.model import VerificationPlan

    common = dict(
        verification_plan_id="b" * 64, diagnostic_session_id="c" * 32,
        failed_before_run_id="failed-run", failed_before_evidence_id="d" * 64,
        source_change_declaration_id="e" * 64, fixed_after_run_id="fixed-run",
        fixed_after_evidence_id="f" * 64, required_analysis_ids=("1" * 64,),
        required_analysis_evidence_ids=("2" * 64,), required_monitor_quality="VALID", expected_changed=True,
    )
    old = VerificationPlan.new(**common)
    new = VerificationPlan.new(**common, continuation_evidence_id="3" * 64)
    adapter = TypeAdapter(mcp_server.VerificationPlanRequestInput)
    for value in (old, new):
        parsed = adapter.validate_python(value.to_dict())
        assert parsed.model_dump(by_alias=True) == value.to_dict()
    assert old.plan_digest != new.plan_digest
    with pytest.raises(ValidationError):
        adapter.validate_python({**old.to_dict(), "continuation_evidence_id": "3" * 64})
    missing = new.to_dict()
    del missing["continuation_evidence_id"]
    with pytest.raises(ValidationError):
        adapter.validate_python(missing)
