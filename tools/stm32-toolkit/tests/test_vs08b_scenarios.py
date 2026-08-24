from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
from stm32_toolkit.result import OperationResult


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def _fake_authorities(monkeypatch: pytest.MonkeyPatch, *, origin: str = "keil") -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
        memory=SimpleNamespace(source=origin),
        target_device="STM32F429ZITx",
    )
    monkeypatch.setattr(recovery_workflows, "_load_project_model", lambda _root: model)
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_build_project_context",
        lambda *_args: OperationResult.success(
            "project.context",
            {"build": {"elfFresh": True, "preset": "arm-debug", "buildId": "b" * 64, "elfSha256": "e" * 64}},
        ),
    )


@pytest.mark.parametrize(
    ("origin", "scenario_id"),
    [("keil", "legacy-keil-migration"), ("cubemx", "new-cubemx-project")],
)
def test_each_accepted_origin_begins_and_resumes_software_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    scenario_id: str,
):
    _fake_authorities(monkeypatch, origin=origin)
    project = tmp_path / origin
    project.mkdir()
    context = AcceptanceRecoveryContext(project, tmp_path / "data", "session-a")
    result = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id=scenario_id,
        scenario_version="1",
    )
    assert result.ok is True
    attempt = result.data["attempt"]
    assert attempt["executionSource"] == "replay"
    assert attempt["physicalTransportEvidence"] is False
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["nextStage"] == "project-materialized"
    assert resumed.data["recoveryPolicy"]["physicalTransportEvidence"] is False


def test_timeout_refuses_advancement_without_publishing_a_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _fake_authorities(monkeypatch)
    current = ["2026-08-24T00:00:00.000000Z"]
    context = AcceptanceRecoveryContext(
        tmp_path / "project", tmp_path / "data", "session-a", clock=lambda: current[0]
    )
    context.project_root.mkdir()
    begun = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert begun.ok is True
    current[0] = "2026-08-24T00:01:00.000001Z"
    timed_out = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert timed_out.ok is False
    assert timed_out.code == "ACCEPTANCE_ATTEMPT_TIMED_OUT"
    shown = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert shown.ok is True
    assert shown.data["attempt"]["revision"] == 0
    assert shown.data["timedOut"] is True


def test_same_attempt_id_isolated_by_project_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _fake_authorities(monkeypatch)
    left_project = tmp_path / "left"
    right_project = tmp_path / "right"
    left_project.mkdir()
    right_project.mkdir()
    left = AcceptanceRecoveryContext(left_project, tmp_path / "data", "session-a")
    right = AcceptanceRecoveryContext(right_project, tmp_path / "data", "session-a")
    left_result = begin_acceptance_attempt(left, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1")
    right_result = begin_acceptance_attempt(right, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1")
    assert left_result.ok is True and right_result.ok is True
    assert left_result.data["attempt"]["workspaceId"] != right_result.data["attempt"]["workspaceId"]
