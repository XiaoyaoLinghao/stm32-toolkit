from __future__ import annotations

import json
from pathlib import Path

import pytest

from stm32_toolkit import cli
from stm32_toolkit.diagnostic_workflows import DiagnosticWorkflowContext
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing_workflows import TestingWorkflowContext as _TestingWorkflowContext


SESSION = "0123456789abcdef0123456789abcdef"
OPERATION = "operation-1"
DIGEST = "a" * 64


def _context_args() -> list[str]:
    return [
        "--project-root",
        "C:/project-root",
        "--data-root",
        "data-root",
        "--session-id",
        "tool-session",
        "--json",
    ]


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_target_replay_parser_and_dispatch_are_one_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    descriptor = _write_json(tmp_path / "descriptor.json", {"descriptor": True})
    stream = tmp_path / "stream.bin"
    stream.write_bytes(b"stream")
    result = OperationResult.success("test.target.replay", {"published": True})
    calls: list[tuple[object, dict[str, object]]] = []

    def replay(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "target_replay_run", replay, raising=False)
    argv = [
        "test",
        "replay",
        "--project-root",
        "C:/project-root",
        "--data-root",
        "data-root",
        "--session-id",
        "tool-session",
        "--operation-id",
        OPERATION,
        "--descriptor-file",
        str(descriptor),
        "--stream-file",
        str(stream),
        "--json",
    ]

    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == result.to_dict()
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == _TestingWorkflowContext(
        Path("C:/project-root"), Path("data-root"), "tool-session"
    )
    assert kwargs == {
        "operation_id": OPERATION,
        "descriptor_file": descriptor,
        "stream_file": stream,
    }


@pytest.mark.parametrize(
    "command",
    [
        "source-change",
        "verification-plan",
        "verification",
        "marker",
    ],
)
def test_diagnostic_adapter_object_files_are_decoded_before_one_workflow_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    object_file = _write_json(tmp_path / f"{command}.json", {"value": command})
    result = OperationResult.success(f"diagnostic.{command}", {"ok": True})
    calls: list[tuple[object, dict[str, object]]] = []

    workflow_name = {
        "source-change": "diagnostic_declare_source_change",
        "verification-plan": "diagnostic_add_verification_plan",
        "verification": "diagnostic_start_verification",
        "marker": "diagnostic_attach_marker",
    }[command]

    def workflow(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, workflow_name, workflow, raising=False)
    if command == "source-change":
        argv = [
            "diagnose",
            "source-change",
            "declare",
            SESSION,
            "--operation-id",
            OPERATION,
            "--expected-revision",
            "3",
            "--declaration-file",
            str(object_file),
            *_context_args(),
        ]
    elif command == "verification-plan":
        argv = [
            "diagnose",
            "verification-plan",
            "add",
            SESSION,
            "--operation-id",
            OPERATION,
            "--expected-revision",
            "3",
            "--plan-file",
            str(object_file),
            *_context_args(),
        ]
    elif command == "verification":
        argv = [
            "diagnose",
            "verification",
            "start",
            SESSION,
            "--operation-id",
            OPERATION,
            "--expected-revision",
            "3",
            "--verification-plan-id",
            DIGEST,
            *_context_args(),
        ]
    else:
        argv = [
            "diagnose",
            "marker",
            "attach",
            SESSION,
            "--operation-id",
            OPERATION,
            "--expected-revision",
            "3",
            "--marker-file",
            str(object_file),
            *_context_args(),
        ]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == result.to_dict()
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("C:/project-root"), Path("data-root"), "tool-session"
    )
    if command in {"source-change", "verification-plan", "marker"}:
        object_key = {
            "source-change": "source_change_declaration",
            "verification-plan": "verification_plan",
            "marker": "diagnostic_marker_ref",
        }[command]
        assert kwargs[object_key] == {"value": command}


def test_verification_complete_collects_operation_ids_and_show_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    complete = OperationResult.success("diagnostic.verification.complete", {})
    show = OperationResult.success("diagnostic.verification.show", {})
    complete_calls: list[dict[str, object]] = []
    show_calls: list[dict[str, object]] = []

    def complete_workflow(context: object, **kwargs: object) -> OperationResult[object]:
        complete_calls.append(kwargs)
        return complete

    def show_workflow(context: object, **kwargs: object) -> OperationResult[object]:
        show_calls.append(kwargs)
        return show

    monkeypatch.setattr(cli, "diagnostic_complete_verification", complete_workflow)
    monkeypatch.setattr(cli, "diagnostic_show_verification", show_workflow)
    common = [
        "--project-root",
        "C:/project-root",
        "--data-root",
        "data-root",
        "--session-id",
        "tool-session",
        "--json",
    ]
    assert (
        cli.main(
            [
                "diagnose",
                "verification",
                "complete",
                SESSION,
                "--operation-id",
                OPERATION,
                "--expected-revision",
                "4",
                "--executed-operation-id",
                "run-one",
                "--executed-operation-id",
                "run-two",
                "--cancelled",
                *common,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == complete.to_dict()
    assert complete_calls == [
        {
            "operation_id": OPERATION,
            "diagnostic_session_id": SESSION,
            "expected_revision": 4,
            "executed_operation_ids": ["run-one", "run-two"],
            "cancelled": True,
            "actor": "tool",
        }
    ]
    assert cli.main(["diagnose", "verification", "show", SESSION, *common]) == 0
    assert json.loads(capsys.readouterr().out) == show.to_dict()
    assert show_calls == [{"diagnostic_session_id": SESSION}]


def test_new_cli_grammar_and_safe_object_file_errors_precede_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        cli,
        "diagnostic_declare_source_change",
        lambda *args, **kwargs: calls.append(True),
    )
    missing = tmp_path / "missing.json"
    argv = [
        "diagnose",
        "source-change",
        "declare",
        SESSION,
        "--operation-id",
        OPERATION,
        "--expected-revision",
        "0",
        "--declaration-file",
        str(missing),
        *_context_args(),
    ]
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("invalid arguments\n")
    assert calls == []
