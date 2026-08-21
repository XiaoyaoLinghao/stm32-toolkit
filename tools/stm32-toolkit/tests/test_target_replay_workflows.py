"""Contract tests for the public Target replay workflow."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.testing_workflows as workflows


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")


def _context(tmp_path: Path) -> workflows.TestingWorkflowContext:
    project_root = tmp_path / "project"
    project_root.mkdir()
    return workflows.TestingWorkflowContext(
        project_root=project_root,
        data_root=tmp_path / "data",
        session_id="replay-session",
    )


def _install_model(monkeypatch: pytest.MonkeyPatch, context: workflows.TestingWorkflowContext) -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=PROJECT_ID,
        testing=SimpleNamespace(host=None, target=object()),
    )
    monkeypatch.setattr(workflows, "_load_project_model", lambda _root: model)


def test_target_replay_workflow_exposes_the_public_entrypoint():
    assert callable(getattr(workflows, "target_replay_run", None))


def test_target_replay_run_preserves_origin_and_import_identity_and_reloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)

    def fail_if_physical_runner_is_constructed(**_kwargs: object):
        pytest.fail("Target replay must not construct a physical runner")

    monkeypatch.setattr(workflows, "_host_runner_factory", fail_if_physical_runner_is_constructed)
    result = workflows.target_replay_run(
        context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )

    assert result.ok is True
    data = result.to_dict()["data"]
    assert data["run"]["run_id"] == "vs03-failed-before"
    assert data["run"]["identity"]["workspace_id"] != data["import_workspace_id"]
    assert data["execution_source"] == "replay"
    assert data["physical_transport_evidence"] is False
    shown = workflows.test_show(context, run_id="vs03-failed-before")
    assert shown.ok is True
    assert shown.to_dict()["data"] == {**data, "authoritative": True}

    retry = workflows.target_replay_run(
        workflows.TestingWorkflowContext(
            context.project_root, context.data_root, context.session_id
        ),
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert retry.ok is True
    assert retry.to_dict()["data"] == data


def test_target_replay_run_binds_operation_id_to_frozen_run_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)
    result = workflows.target_replay_run(
        context,
        "wrong-operation-id",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )

    assert result.ok is False
    assert result.code == "TEST_PROTOCOL_INVALID"
    workspace = workflows.WorkspacePaths.from_roots(
        context.data_root, context.project_root, PROJECT_ID, context.session_id
    )
    assert not any((workspace.workspace_root / "evidence").rglob("*.json"))


@pytest.mark.parametrize(
    ("operation_id", "name", "state"),
    (("vs03-failed-before", "failed-before", "failed"), ("vs03-fixed-after", "fixed-after", "passed")),
)
def test_target_replay_run_executes_both_frozen_terminal_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation_id: str,
    name: str,
    state: str,
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)
    result = workflows.target_replay_run(
        context,
        operation_id,
        FIXTURES / f"{name}.json",
        FIXTURES / f"{name}.hex",
    )
    assert result.ok is True
    assert result.to_dict()["data"]["run"]["state"] == state
