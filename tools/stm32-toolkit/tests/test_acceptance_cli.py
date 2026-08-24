from __future__ import annotations

import json
from pathlib import Path

import pytest

from stm32_toolkit import cli
from stm32_toolkit.result import OperationResult


def test_cli_record_dispatches_exact_values_once(monkeypatch, capsys):
    seen = []
    record_id = "00000000-0000-4000-8000-000000000001"
    failed_id = "00000000-0000-4000-8000-000000000002"
    fixed_id = "00000000-0000-4000-8000-000000000003"
    session_id = "00000000-0000-4000-8000-000000000004"
    ok = OperationResult.success(
        "acceptance.scenario.record", {"record": {"recordId": record_id}}
    )
    monkeypatch.setattr(
        cli,
        "record_acceptance_scenario",
        lambda context, **kwargs: seen.append((context, kwargs)) or ok,
    )
    assert cli.main([
        "scenario", "record", "--project", "C:/work/project",
        "--data-root", "C:/work/data", "--session-id", "session-a",
        "--record-id", record_id,
        "--scenario-id", "legacy-keil-migration",
        "--scenario-version", "1",
        "--failed-before-test-run-id", failed_id,
        "--fixed-after-test-run-id", fixed_id,
        "--diagnostic-session-id", session_id,
    ]) == 0
    assert seen[0][1] == {
        "record_id": record_id,
        "scenario_id": "legacy-keil-migration",
        "scenario_version": "1",
        "failed_before_test_run_id": failed_id,
        "fixed_after_test_run_id": fixed_id,
        "diagnostic_session_id": session_id,
    }
    assert json.loads(capsys.readouterr().out)["operation"] == "acceptance.scenario.record"


def test_cli_describe_and_show_dispatch_through_shared_helpers(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "describe_acceptance_scenario",
        lambda context, **kwargs: calls.append(("describe", context, kwargs))
        or OperationResult.success("acceptance.scenario.describe", {"scenario": {}}),
    )
    monkeypatch.setattr(
        cli,
        "show_acceptance_scenario",
        lambda context, **kwargs: calls.append(("show", context, kwargs))
        or OperationResult.success("acceptance.scenario.show", {"record": {}}),
    )
    record_id = "00000000-0000-4000-8000-000000000001"
    assert cli.main([
        "scenario", "describe", "--project", "C:/work/project",
        "--data-root", "C:/work/data", "--session-id", "session-a",
        "--scenario-id", "new-cubemx-project", "--scenario-version", "1",
    ]) == 0
    assert cli.main([
        "scenario", "show", "--project", "C:/work/project",
        "--data-root", "C:/work/data", "--session-id", "session-a",
        "--record-id", record_id,
    ]) == 0
    assert [item[0] for item in calls] == ["describe", "show"]
    assert calls[0][2] == {"scenario_id": "new-cubemx-project", "scenario_version": "1"}
    assert calls[1][2] == {"record_id": record_id}
    output = capsys.readouterr().out
    assert '"operation": "acceptance.scenario.show"' in output


@pytest.mark.parametrize("bad", ["not-a-uuid", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"])
def test_cli_rejects_noncanonical_acceptance_uuid(bad, capsys):
    assert cli.main([
        "scenario", "show", "--project", "C:/work/project",
        "--data-root", "C:/work/data", "--session-id", "session-a",
        "--record-id", bad,
    ]) == 2
    assert capsys.readouterr().out == ""
