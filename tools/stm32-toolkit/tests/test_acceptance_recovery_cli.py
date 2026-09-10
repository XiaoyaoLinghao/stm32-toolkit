from __future__ import annotations

import json
from pathlib import Path

from stm32_toolkit import cli
from stm32_toolkit.result import OperationResult


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"
TEST_RUN_ID = "00000000-0000-4000-8000-000000000002"
DIAGNOSTIC_ID = "00000000-0000-4000-8000-000000000003"
RECORD_ID = "00000000-0000-4000-8000-000000000004"
DIGEST = "a" * 64


def _common() -> list[str]:
    return ["--project", "C:/work/project", "--data-root", "C:/work/data", "--session-id", "session-a"]


def test_cli_attempt_begin_translates_exact_values_once(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "begin_acceptance_attempt",
        lambda context, **kwargs: calls.append((context, kwargs))
        or OperationResult.success("acceptance.attempt.begin", {"attempt": {}}),
    )
    assert cli.main(["scenario", "attempt", "begin", *_common(), "--attempt-id", ATTEMPT_ID, "--scenario-id", "legacy-keil-migration", "--scenario-version", "1"]) == 0
    assert calls[0][1] == {
        "attempt_id": ATTEMPT_ID,
        "scenario_id": "legacy-keil-migration",
        "scenario_version": "1",
    }
    assert json.loads(capsys.readouterr().out)["operation"] == "acceptance.attempt.begin"


def test_cli_checkpoint_and_authorize_translate_optional_references(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "checkpoint_acceptance_attempt",
        lambda context, **kwargs: calls.append(("checkpoint", kwargs))
        or OperationResult.success("acceptance.attempt.checkpoint", {"attempt": {}}),
    )
    monkeypatch.setattr(
        cli,
        "authorize_acceptance_source_change",
        lambda context, **kwargs: calls.append(("authorize", kwargs))
        or OperationResult.success("acceptance.attempt.authorize-source-change", {"attempt": {}}),
    )
    assert cli.main(["scenario", "attempt", "checkpoint", *_common(), "--attempt-id", ATTEMPT_ID, "--expected-revision", "2", "--stage", "target-failure-replayed", "--test-run-id", TEST_RUN_ID]) == 0
    assert cli.main(["scenario", "attempt", "authorize-source-change", *_common(), "--attempt-id", ATTEMPT_ID, "--expected-revision", "4", "--action-digest", DIGEST, "--authorized"]) == 0
    assert calls[0][1] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 2,
        "stage": "target-failure-replayed",
        "test_run_id": TEST_RUN_ID,
        "diagnostic_session_id": None,
        "acceptance_record_id": None,
    }
    assert calls[1][1] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 4,
        "action_digest": DIGEST,
        "authorized": True,
    }
    capsys.readouterr()


def test_cli_physical_checkpoint_translates_native_refs_and_source_intent(
    monkeypatch, capsys, tmp_path: Path
):
    calls = []
    monkeypatch.setattr(
        cli,
        "checkpoint_acceptance_attempt",
        lambda context, **kwargs: calls.append(kwargs)
        or OperationResult.success("acceptance.attempt.checkpoint", {"attempt": {}}),
    )
    intent = {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "Src/main.c",
                "beforeSha256": "a" * 64,
                "afterSha256": "b" * 64,
                "afterSize": 42,
            }
        ],
    }
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    assert cli.main(
        [
            "scenario",
            "attempt",
            "checkpoint",
            *_common(),
            "--attempt-id",
            ATTEMPT_ID,
            "--expected-revision",
            "3",
            "--stage",
            "diagnosis-completed",
            "--diagnostic-session-id",
            "0123456789abcdef0123456789abcdef",
            "--source-change-intent-file",
            str(intent_path),
        ]
    ) == 0
    assert calls[0] == {
        "attempt_id": ATTEMPT_ID,
        "expected_revision": 3,
        "stage": "diagnosis-completed",
        "test_run_id": None,
        "diagnostic_session_id": "0123456789abcdef0123456789abcdef",
        "acceptance_record_id": None,
        "source_change_intent": intent,
    }
    capsys.readouterr()

def test_cli_attempt_show_and_resume_share_project_bound_context(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "show_acceptance_attempt",
        lambda context, **kwargs: calls.append(("show", context, kwargs))
        or OperationResult.success("acceptance.attempt.show", {"attempt": {}}),
    )
    monkeypatch.setattr(
        cli,
        "resume_acceptance_attempt",
        lambda context, **kwargs: calls.append(("resume", context, kwargs))
        or OperationResult.success("acceptance.attempt.resume", {"attempt": {}}),
    )
    assert cli.main(["scenario", "attempt", "show", *_common(), "--attempt-id", ATTEMPT_ID]) == 0
    assert cli.main(["scenario", "attempt", "resume", *_common(), "--attempt-id", ATTEMPT_ID]) == 0
    assert [kind for kind, _, _ in calls] == ["show", "resume"]
    assert calls[0][2] == {"attempt_id": ATTEMPT_ID}
    assert calls[1][2] == {"attempt_id": ATTEMPT_ID}
    assert calls[0][1].project_root == Path("C:/work/project")
    capsys.readouterr()
