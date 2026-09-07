import json
from pathlib import Path

import pytest

from stm32_toolkit import cli
from stm32_toolkit.result import OperationResult


CONTEXT_ARGS = [
    "--project",
    "C:/project-root",
    "--data-root",
    "data-root",
    "--session-id",
    "session-a",
    "--json",
]
DIGEST = "a" * 64


def parse(argv: list[str]):
    return cli._build_parser().parse_args(argv)


def _discover_argv() -> list[str]:
    return ["test", "discover", "--mode", "host", *CONTEXT_ARGS]


def _run_argv(*case_ids: str, digest: str = DIGEST) -> list[str]:
    argv = [
        "test",
        "run",
        "--mode",
        "host",
        "--inventory-digest",
        digest,
    ]
    for case_id in case_ids:
        argv.extend(["--case", case_id])
    return [*argv, *CONTEXT_ARGS]


def _show_argv(run_id: str = "run-1") -> list[str]:
    return ["test", "show", run_id, *CONTEXT_ARGS]


def _target_prepare_argv(
    *case_ids: str, recovery_under_reset: bool = False
) -> list[str]:
    argv = ["test", "target", "prepare", "--probe-id", "probe-a"]
    if recovery_under_reset:
        argv.append("--recovery-under-reset")
    for case_id in case_ids:
        argv.extend(["--case-id", case_id])
    return [*argv, *CONTEXT_ARGS]


def _target_execute_argv() -> list[str]:
    return [
        "test", "target", "execute", "--probe-id", "probe-a",
        "--authorized-action-digest", DIGEST, *CONTEXT_ARGS,
    ]


def test_testing_parser_exposes_fixed_operations_and_run_shape() -> None:
    assert parse(_discover_argv()).operation == "test.host.discover"

    run = parse(_run_argv("fails"))
    assert run.operation == "test.host.run"
    assert run.case_ids == ("fails",)

    show = parse(_show_argv())
    assert show.operation == "test.show"
    assert show.run_id == "run-1"
    prepared = parse(_target_prepare_argv("fails"))
    assert prepared.operation == "test.target.prepare" and prepared.case_ids == ("fails",)
    assert prepared.recovery_under_reset is False
    recovery = parse(_target_prepare_argv("fails", recovery_under_reset=True))
    assert recovery.recovery_under_reset is True
    executed = parse(_target_execute_argv())
    assert executed.operation == "test.target.execute" and executed.authorized_action_digest == DIGEST

    with pytest.raises(SystemExit) as duplicate:
        parse([
            "test", "target", "prepare", "--probe-id", "probe-a",
            "--recovery-under-reset", "--recovery-under-reset", "--case-id", "fails",
            *CONTEXT_ARGS,
        ])
    assert duplicate.value.code == 2

    with pytest.raises(SystemExit) as value_form:
        parse([
            "test", "target", "prepare", "--probe-id", "probe-a",
            "--recovery-under-reset=true", "--case-id", "fails", *CONTEXT_ARGS,
        ])
    assert value_form.value.code == 2

    with pytest.raises(SystemExit) as separate_value:
        parse([
            "test", "target", "prepare", "--probe-id", "probe-a",
            "--recovery-under-reset", "true", "--case-id", "fails", *CONTEXT_ARGS,
        ])
    assert separate_value.value.code == 2


@pytest.mark.parametrize(
    ("argv", "workflow", "expected"),
    [
        (_target_prepare_argv("fails"), "target_test_prepare", {"probe_id": "probe-a", "case_ids": ("fails",), "recovery_under_reset": False}),
        (_target_prepare_argv("fails", recovery_under_reset=True), "target_test_prepare", {"probe_id": "probe-a", "case_ids": ("fails",), "recovery_under_reset": True}),
        (_target_execute_argv(), "target_test_execute", {"probe_id": "probe-a", "authorized_action_digest": DIGEST}),
    ],
)
def test_physical_target_cli_is_one_async_workflow_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    argv: list[str], workflow: str, expected: dict[str, object],
) -> None:
    calls: list[dict[str, object]] = []

    async def operation(_context: object, **kwargs: object) -> OperationResult[dict[str, object]]:
        calls.append(kwargs)
        return OperationResult.success("test.target", {"ok": True})

    monkeypatch.setattr(cli, workflow, operation)
    assert cli.main(argv) == 0
    assert calls == [expected]
    assert json.loads(capsys.readouterr().out)["ok"] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["test", "target", "prepare", "--probe", "probe-a", "--case-id", "fails", *CONTEXT_ARGS],
        ["test", "target", "prepare", "--probe-id", "probe-a", "--case", "fails", *CONTEXT_ARGS],
        ["test", "target", "execute", "--probe", "probe-a", "--authorized-action-digest", DIGEST, *CONTEXT_ARGS],
    ],
)
def test_physical_target_cli_rejects_superseded_option_spellings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "target_test_prepare", lambda *args, **kwargs: calls.append("prepare"))
    monkeypatch.setattr(cli, "target_test_execute", lambda *args, **kwargs: calls.append("execute"))

    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("invalid arguments\n")
    assert calls == []


@pytest.mark.parametrize(
    ("argv", "workflow", "operation"),
    [
        (_target_prepare_argv("fails"), "target_test_prepare", "test.target.prepare"),
        (_target_execute_argv(), "target_test_execute", "test.target.execute"),
    ],
)
def test_physical_target_cli_sanitizes_escaping_exceptions_with_exact_operation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    workflow: str,
    operation: str,
) -> None:
    async def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("SECRET physical adapter failure")

    monkeypatch.setattr(cli, workflow, explode)
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == OperationResult.failure(
        operation, "HARDWARE_INTERNAL_ERROR", "Hardware command failed", {}
    ).to_dict()
    assert "SECRET" not in captured.out
    assert captured.err == ""


def test_discover_dispatches_exactly_once_and_writes_one_json_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    result = OperationResult.success("test.host.discover", {"inventory": {"caseIds": []}})

    def discover(context: object) -> OperationResult[dict[str, object]]:
        calls.append(context)
        return result

    monkeypatch.setattr(cli, "host_test_discover", discover, raising=False)

    assert cli.main(_discover_argv()) == 0

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert json.loads(captured.out) == result.to_dict()
    assert captured.err == ""
    assert len(calls) == 1
    context = calls[0]
    assert context.project_root == Path("C:/project-root")
    assert context.data_root == Path("data-root")
    assert context.session_id == "session-a"


def test_run_dispatches_exactly_once_with_digest_and_tuple_cases(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, str, tuple[str, ...]]] = []
    result = OperationResult.success("test.host.run", {"run": {"state": "failed"}})

    def run(
        context: object, *, inventory_digest: str, case_ids: tuple[str, ...]
    ) -> OperationResult[dict[str, object]]:
        calls.append((context, inventory_digest, case_ids))
        return result

    monkeypatch.setattr(cli, "host_test_run", run, raising=False)

    assert cli.main(_run_argv("fails", "other")) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == result.to_dict()
    assert captured.err == ""
    assert len(calls) == 1
    context, digest, case_ids = calls[0]
    assert context.project_root == Path("C:/project-root")
    assert context.data_root == Path("data-root")
    assert context.session_id == "session-a"
    assert digest == DIGEST
    assert case_ids == ("fails", "other")


def test_run_without_cases_dispatches_an_empty_tuple(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, ...]] = []
    result = OperationResult.success("test.host.run", {"run": {"state": "failed"}})

    def run(
        context: object, *, inventory_digest: str, case_ids: tuple[str, ...]
    ) -> OperationResult[dict[str, object]]:
        calls.append(case_ids)
        return result

    monkeypatch.setattr(cli, "host_test_run", run, raising=False)

    assert cli.main(_run_argv()) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == result.to_dict()
    assert captured.err == ""
    assert calls == [()]


def test_show_dispatches_exactly_once_with_run_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[object, str]] = []
    result = OperationResult.success("test.show", {"run": {"run_id": "run-1"}})

    def show(context: object, *, run_id: str) -> OperationResult[dict[str, object]]:
        calls.append((context, run_id))
        return result

    monkeypatch.setattr(cli, "test_show", show, raising=False)

    assert cli.main(_show_argv()) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == result.to_dict()
    assert captured.err == ""
    assert len(calls) == 1
    context, run_id = calls[0]
    assert context.project_root == Path("C:/project-root")
    assert context.data_root == Path("data-root")
    assert context.session_id == "session-a"
    assert run_id == "run-1"


@pytest.mark.parametrize(
    ("argv", "workflow_name", "operation"),
    [
        (_discover_argv(), "host_test_discover", "test.host.discover"),
        (_run_argv("fails"), "host_test_run", "test.host.run"),
        (_show_argv(), "test_show", "test.show"),
    ],
)
def test_json_flag_is_optional_for_each_testing_leaf(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    workflow_name: str,
    operation: str,
) -> None:
    result = OperationResult.success(operation, {"value": "ok"})
    calls: list[object] = []

    def workflow(*args: object, **kwargs: object) -> OperationResult[dict[str, object]]:
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(cli, workflow_name, workflow, raising=False)

    without_json = [value for value in argv if value != "--json"]
    assert cli.main(without_json) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == result.to_dict()
    assert captured.err == ""
    assert len(calls) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["test", "discover", *CONTEXT_ARGS],
        ["test", "discover", "--mode", "target", *CONTEXT_ARGS],
        ["test", "discover", "--mode", "host", "--unknown", "value", *CONTEXT_ARGS],
        _run_argv("fails", "fails"),
        _run_argv("fails", digest="not-a-digest"),
    ],
)
def test_invalid_testing_grammar_rejects_before_workflow_calls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    calls: list[str] = []
    for name in ("host_test_discover", "host_test_run", "test_show"):
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


def test_testing_failure_result_keeps_operation_result_json_projection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = OperationResult.failure(
        "test.show",
        "EVIDENCE_CORRUPT",
        "Evidence is corrupt.",
        {},
    )
    monkeypatch.setattr(cli, "test_show", lambda *args, **kwargs: result, raising=False)

    assert cli.main(_show_argv()) == 2

    captured = capsys.readouterr()
    assert captured.out == json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert captured.err == ""


def test_unexpected_testing_error_uses_existing_non_hardware_stderr_policy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("testing adapter exploded")

    monkeypatch.setattr(cli, "host_test_run", explode, raising=False)

    assert cli.main(_run_argv("fails")) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "stm32-toolkit: internal error: testing adapter exploded\n"
