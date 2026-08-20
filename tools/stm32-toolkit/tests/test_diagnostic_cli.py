import json
from pathlib import Path

import pytest

from stm32_toolkit import cli
from stm32_toolkit.diagnostic_workflows import DiagnosticWorkflowContext
from stm32_toolkit.result import OperationResult


CONTEXT_ARGS = [
    "--project",
    "project-root",
    "--data-root",
    "data-root",
    "--session-id",
    "toolkit-session",
    "--json",
]
DIAGNOSTIC_SESSION_ID = "0123456789abcdef0123456789abcdef"
HYPOTHESIS_ID = "a" * 32
PLAN_ID = "b" * 64


def parse(argv: list[str]):
    return cli._build_parser().parse_args(argv)


def _start_argv(
    *,
    run_id: str = "run-1",
    operation_id: str = "start-1",
    actor: str | None = None,
    json_output: bool = True,
) -> list[str]:
    argv = [
        "diagnose",
        "start",
        run_id,
        "--operation-id",
        operation_id,
    ]
    if actor is not None:
        argv.extend(["--actor", actor])
    argv.extend(CONTEXT_ARGS if json_output else [value for value in CONTEXT_ARGS if value != "--json"])
    return argv


def _show_argv(
    *,
    session_id: str = DIAGNOSTIC_SESSION_ID,
    json_output: bool = True,
) -> list[str]:
    argv = ["diagnose", "show", session_id]
    argv.extend(CONTEXT_ARGS if json_output else [value for value in CONTEXT_ARGS if value != "--json"])
    return argv


def _begin_argv(
    *,
    session_id: str = DIAGNOSTIC_SESSION_ID,
    operation_id: str = "begin-1",
    expected_revision: str = "0",
    actor: str | None = None,
    json_output: bool = True,
) -> list[str]:
    argv = [
        "diagnose",
        "begin",
        session_id,
        "--operation-id",
        operation_id,
        "--expected-revision",
        expected_revision,
    ]
    if actor is not None:
        argv.extend(["--actor", actor])
    argv.extend(CONTEXT_ARGS if json_output else [value for value in CONTEXT_ARGS if value != "--json"])
    return argv


def _hypothesis_add_argv(
    *,
    session_id: str = DIAGNOSTIC_SESSION_ID,
    operation_id: str = "hypothesis-add-1",
    expected_revision: str = "2",
    statement: str = "clock configuration is inconsistent",
    actor: str | None = None,
    json_output: bool = True,
) -> list[str]:
    argv = [
        "diagnose",
        "hypothesis",
        "add",
        session_id,
        "--operation-id",
        operation_id,
        "--expected-revision",
        expected_revision,
        "--statement",
        statement,
    ]
    if actor is not None:
        argv.extend(["--actor", actor])
    argv.extend(CONTEXT_ARGS if json_output else [value for value in CONTEXT_ARGS if value != "--json"])
    return argv


def _hypothesis_assess_argv(
    *,
    session_id: str = DIAGNOSTIC_SESSION_ID,
    operation_id: str = "hypothesis-assess-1",
    expected_revision: str = "6",
    hypothesis_id: str = HYPOTHESIS_ID,
    plan_id: str = PLAN_ID,
    step_id: str = "failed-case-state",
    polarity: str = "supports",
    rationale: str = "the executed observation matches the hypothesis",
    actor: str | None = None,
    json_output: bool = True,
) -> list[str]:
    argv = [
        "diagnose",
        "hypothesis",
        "assess",
        session_id,
        "--operation-id",
        operation_id,
        "--expected-revision",
        expected_revision,
        "--hypothesis-id",
        hypothesis_id,
        "--plan-id",
        plan_id,
        "--step-id",
        step_id,
        "--polarity",
        polarity,
        "--rationale",
        rationale,
    ]
    if actor is not None:
        argv.extend(["--actor", actor])
    argv.extend(CONTEXT_ARGS if json_output else [value for value in CONTEXT_ARGS if value != "--json"])
    return argv


def test_diagnostic_parser_exposes_fixed_operations_defaults_and_context() -> None:
    start = parse(_start_argv())
    assert start.command == "diagnose"
    assert start.diagnose_command == "start"
    assert start.operation == "diagnostic.start"
    assert start.failed_test_run_id == "run-1"
    assert start.operation_id == "start-1"
    assert start.actor == "user"
    assert start.project_root == Path("project-root")
    assert start.data_root == Path("data-root")
    assert start.session_id == "toolkit-session"
    assert start.json is True

    show = parse(_show_argv())
    assert show.command == "diagnose"
    assert show.diagnose_command == "show"
    assert show.operation == "diagnostic.show"
    assert show.diagnostic_session_id == DIAGNOSTIC_SESSION_ID
    assert show.project_root == Path("project-root")
    assert show.data_root == Path("data-root")
    assert show.session_id == "toolkit-session"
    assert show.json is True

    begin = parse(_begin_argv())
    assert begin.command == "diagnose"
    assert begin.diagnose_command == "begin"
    assert begin.operation == "diagnostic.begin"
    assert begin.diagnostic_session_id == DIAGNOSTIC_SESSION_ID
    assert begin.operation_id == "begin-1"
    assert begin.expected_revision == 0
    assert begin.actor == "user"
    assert begin.project_root == Path("project-root")
    assert begin.data_root == Path("data-root")
    assert begin.session_id == "toolkit-session"
    assert begin.json is True

    add = parse(_hypothesis_add_argv())
    assert add.command == "diagnose"
    assert add.diagnose_command == "hypothesis"
    assert add.hypothesis_command == "add"
    assert add.operation == "diagnostic.hypothesis.add"
    assert add.diagnostic_session_id == DIAGNOSTIC_SESSION_ID
    assert add.operation_id == "hypothesis-add-1"
    assert add.expected_revision == 2
    assert add.statement == "clock configuration is inconsistent"
    assert add.actor == "user"
    assert add.project_root == Path("project-root")
    assert add.data_root == Path("data-root")
    assert add.session_id == "toolkit-session"
    assert add.json is True

    assess = parse(_hypothesis_assess_argv())
    assert assess.command == "diagnose"
    assert assess.diagnose_command == "hypothesis"
    assert assess.hypothesis_command == "assess"
    assert assess.operation == "diagnostic.hypothesis.assess"
    assert assess.diagnostic_session_id == DIAGNOSTIC_SESSION_ID
    assert assess.operation_id == "hypothesis-assess-1"
    assert assess.expected_revision == 6
    assert assess.hypothesis_id == HYPOTHESIS_ID
    assert assess.plan_id == PLAN_ID
    assert assess.step_id == "failed-case-state"
    assert assess.polarity == "supports"
    assert assess.rationale == "the executed observation matches the hypothesis"
    assert assess.actor == "user"
    assert assess.project_root == Path("project-root")
    assert assess.data_root == Path("data-root")
    assert assess.session_id == "toolkit-session"
    assert assess.json is True


def test_start_dispatches_once_with_exact_context_keywords_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    result = OperationResult.success(
        "diagnostic.start",
        {"session": {"diagnostic_session_id": DIAGNOSTIC_SESSION_ID}},
    )

    def start(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "diagnostic_start", start, raising=False)

    assert cli.main(_start_argv(actor="ai-client")) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("project-root"), Path("data-root"), "toolkit-session"
    )
    assert kwargs == {
        "operation_id": "start-1",
        "failed_test_run_id": "run-1",
        "actor": "ai-client",
    }


def test_show_dispatches_once_with_exact_context_keywords_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    result = OperationResult.success("diagnostic.show", {"session": {}})

    def show(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "diagnostic_show", show, raising=False)

    assert cli.main(_show_argv()) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("project-root"), Path("data-root"), "toolkit-session"
    )
    assert kwargs == {"diagnostic_session_id": DIAGNOSTIC_SESSION_ID}


def test_begin_dispatches_once_with_exact_context_keywords_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    result = OperationResult.success("diagnostic.begin", {"session": {}})

    def begin(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "diagnostic_begin", begin, raising=False)

    assert cli.main(_begin_argv(actor="tool", expected_revision="7")) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("project-root"), Path("data-root"), "toolkit-session"
    )
    assert kwargs == {
        "operation_id": "begin-1",
        "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
        "expected_revision": 7,
        "actor": "tool",
    }


def test_hypothesis_add_dispatches_once_with_exact_context_keywords_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    result = OperationResult.success(
        "diagnostic.hypothesis.add",
        {"hypothesis": {"hypothesis_id": HYPOTHESIS_ID}},
    )

    def add(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "diagnostic_add_hypothesis", add, raising=False)

    assert cli.main(_hypothesis_add_argv(actor="tool")) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("project-root"), Path("data-root"), "toolkit-session"
    )
    assert kwargs == {
        "operation_id": "hypothesis-add-1",
        "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
        "expected_revision": 2,
        "statement": "clock configuration is inconsistent",
        "actor": "tool",
    }


def test_hypothesis_assess_dispatches_once_with_exact_context_keywords_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    result = OperationResult.success(
        "diagnostic.hypothesis.assess",
        {"assessment": {"assessment_id": "c" * 64}},
    )

    def assess(context: object, **kwargs: object) -> OperationResult[object]:
        calls.append((context, kwargs))
        return result

    monkeypatch.setattr(cli, "diagnostic_assess_hypothesis", assess, raising=False)

    assert cli.main(_hypothesis_assess_argv(actor="ai-client")) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""
    assert len(calls) == 1
    context, kwargs = calls[0]
    assert context == DiagnosticWorkflowContext(
        Path("project-root"), Path("data-root"), "toolkit-session"
    )
    assert kwargs == {
        "operation_id": "hypothesis-assess-1",
        "diagnostic_session_id": DIAGNOSTIC_SESSION_ID,
        "expected_revision": 6,
        "hypothesis_id": HYPOTHESIS_ID,
        "plan_id": PLAN_ID,
        "step_id": "failed-case-state",
        "polarity": "supports",
        "rationale": "the executed observation matches the hypothesis",
        "actor": "ai-client",
    }


@pytest.mark.parametrize(
    ("argv_factory", "workflow_name", "operation"),
    [
        (_start_argv, "diagnostic_start", "diagnostic.start"),
        (_show_argv, "diagnostic_show", "diagnostic.show"),
        (_begin_argv, "diagnostic_begin", "diagnostic.begin"),
        (_hypothesis_add_argv, "diagnostic_add_hypothesis", "diagnostic.hypothesis.add"),
        (_hypothesis_assess_argv, "diagnostic_assess_hypothesis", "diagnostic.hypothesis.assess"),
    ],
)
def test_json_flag_is_optional_without_changing_result_bytes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv_factory,
    workflow_name: str,
    operation: str,
) -> None:
    result = OperationResult.success(operation, {"value": "ok"})
    calls: list[object] = []

    def workflow(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(cli, workflow_name, workflow, raising=False)

    assert cli.main(argv_factory()) == 0
    with_json = capsys.readouterr()
    assert cli.main(argv_factory(json_output=False)) == 0
    without_json = capsys.readouterr()

    expected = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert with_json.out == expected
    assert without_json.out == expected
    assert with_json.err == without_json.err == ""
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("argv_factory", "workflow_name", "operation"),
    [
        (_start_argv, "diagnostic_start", "diagnostic.start"),
        (_show_argv, "diagnostic_show", "diagnostic.show"),
        (_begin_argv, "diagnostic_begin", "diagnostic.begin"),
        (_hypothesis_add_argv, "diagnostic_add_hypothesis", "diagnostic.hypothesis.add"),
        (_hypothesis_assess_argv, "diagnostic_assess_hypothesis", "diagnostic.hypothesis.assess"),
    ],
)
def test_domain_failure_keeps_operation_result_json_and_returns_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv_factory,
    workflow_name: str,
    operation: str,
) -> None:
    result = OperationResult.failure(
        operation,
        "DIAGNOSTIC_SESSION_NOT_FOUND",
        "Diagnostic session was not found.",
        {},
    )
    monkeypatch.setattr(cli, workflow_name, lambda *args, **kwargs: result, raising=False)

    assert cli.main(argv_factory()) == 2

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["diagnose", "start", "run-1", "--operation-id", "op"],
        ["diagnose", "start", "run-1", "--operation-id", "op", "--actor", "robot", *CONTEXT_ARGS],
        ["diagnose", "start", "Run-1", "--operation-id", "op", *CONTEXT_ARGS],
        ["diagnose", "start", "-run-1", "--operation-id", "op", *CONTEXT_ARGS],
        ["diagnose", "start", "run-1", "--operation-id", "Bad", *CONTEXT_ARGS],
        ["diagnose", "start", "run-1", "--operation-id", "a" * 129, *CONTEXT_ARGS],
        ["diagnose", "start", "run-1", "--operation-id", "op", "--unknown", "x", *CONTEXT_ARGS],
        ["diagnose", "show", "short", *CONTEXT_ARGS],
        ["diagnose", "show", "ABC" * 11, *CONTEXT_ARGS],
        ["diagnose", "begin", DIAGNOSTIC_SESSION_ID, "--operation-id", "op", *CONTEXT_ARGS],
        [
            "diagnose",
            "begin",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "-1",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "begin",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "10001",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "begin",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "not-an-int",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "-1",
            "--statement",
            "statement",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "not-an-int",
            "--statement",
            "statement",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            "short",
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            "--statement",
            "statement",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "Bad",
            "--expected-revision",
            "0",
            "--statement",
            "statement",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            "--statement",
            "",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            "--statement",
            "e\u0301",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            "--statement",
            "a" * (64 * 1024 + 1),
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "add",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "0",
            "--statement",
            "statement",
            "--actor",
            "robot",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            "A" * 32,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "rationale",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "10001",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "rationale",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            "b" * 63,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "rationale",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "Bad",
            "--polarity",
            "supports",
            "--rationale",
            "rationale",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "neutral",
            "--rationale",
            "rationale",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "e\u0301",
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "a" * (64 * 1024 + 1),
            *CONTEXT_ARGS,
        ],
        [
            "diagnose",
            "hypothesis",
            "assess",
            DIAGNOSTIC_SESSION_ID,
            "--operation-id",
            "op",
            "--expected-revision",
            "6",
            "--hypothesis-id",
            HYPOTHESIS_ID,
            "--plan-id",
            PLAN_ID,
            "--step-id",
            "step",
            "--polarity",
            "supports",
            "--rationale",
            "rationale",
            "--unknown",
            "value",
            *CONTEXT_ARGS,
        ],
    ],
)
def test_invalid_diagnostic_grammar_rejects_before_workflow_calls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    calls: list[str] = []
    for name in (
        "diagnostic_start",
        "diagnostic_show",
        "diagnostic_begin",
        "diagnostic_add_hypothesis",
        "diagnostic_assess_hypothesis",
    ):
        monkeypatch.setattr(
            cli,
            name,
            lambda *args, _name=name, **kwargs: calls.append(_name),
            raising=False,
        )

    assert cli.main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("invalid arguments\n")
    assert calls == []


def test_failed_run_id_over_utf8_limit_rejects_without_leaking_value_or_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(cli, "diagnostic_start", lambda *args, **kwargs: calls.append(1), raising=False)
    oversized = "a" * (64 * 1024 + 1)

    assert cli.main(_start_argv(run_id=oversized)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("invalid arguments\n")
    assert oversized not in captured.err
    assert calls == []


def test_unexpected_diagnostic_workflow_error_uses_existing_non_hardware_policy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("diagnostic adapter exploded")

    monkeypatch.setattr(cli, "diagnostic_begin", explode, raising=False)

    assert cli.main(_begin_argv()) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "stm32-toolkit: internal error: diagnostic adapter exploded\n"
    assert "Traceback" not in captured.err


def test_unexpected_hypothesis_workflow_error_uses_existing_non_hardware_policy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("hypothesis adapter exploded")

    monkeypatch.setattr(cli, "diagnostic_assess_hypothesis", explode, raising=False)

    assert cli.main(_hypothesis_assess_argv()) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "stm32-toolkit: internal error: hypothesis adapter exploded\n"
    assert "Traceback" not in captured.err
