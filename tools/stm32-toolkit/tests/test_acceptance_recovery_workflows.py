from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    begin_acceptance_attempt,
    resume_acceptance_attempt,
)


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def test_begin_publishes_revision_zero_and_retry_returns_the_same_snapshot(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    monkeypatch.setattr(
        "stm32_toolkit.acceptance.recovery_workflows._load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    context = AcceptanceRecoveryContext(project, data, "session-a")
    first = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert first.ok is True
    assert first.data["attempt"]["revision"] == 0
    second = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert second.ok is True
    assert second.data["attempt"] == first.data["attempt"]
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == first.data["attempt"]
    assert resumed.data["nextStage"] == "project-materialized"
    assert resumed.data["authorizationRequired"] is False
