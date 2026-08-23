from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from stm32_toolkit.cli import main
from stm32_toolkit.cli import _build_parser


def test_cli_create_plan_is_read_only_and_supports_mcu(tmp_path: Path, capsys):
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    assert main(["project", "create-plan", "--project-root", str(tmp_path), "--source-kind", "mcu", "--source", "STM32F429ZITx", "--destination", "generated", "--framework", "hal", "--language", "c", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "project-create-plan"
    assert payload["data"]["mutated"] is False
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_cli_rejects_duplicate_source_option():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["project", "create-plan", "--project-root", ".", "--source-kind", "mcu", "--source", "A", "--source", "B", "--destination", "x", "--framework", "hal", "--language", "c"])


@pytest.mark.parametrize(
    "option, first, second",
    [
        ("--project-root", ".", "other"),
        ("--source-kind", "mcu", "board"),
        ("--source", "STM32F429ZITx", "STM32F407ZGTX"),
        ("--destination", "generated", "other"),
        ("--framework", "hal", "ll"),
        ("--language", "c", "cpp"),
        ("--support-profile", "profile-a.json", "profile-b.json"),
    ],
)
def test_cli_rejects_every_repeated_scalar_creation_option(option: str, first: str, second: str):
    argv = [
        "project",
        "create-plan",
        "--project-root",
        ".",
        "--source-kind",
        "mcu",
        "--source",
        "STM32F429ZITx",
        "--destination",
        "generated",
        "--framework",
        "hal",
        "--language",
        "c",
    ]
    if option == "--project-root":
        argv[argv.index("--project-root") + 1] = first
    else:
        argv.extend([option, first])
    argv.extend([option, second])
    with pytest.raises(SystemExit):
        _build_parser().parse_args(argv)


def test_cli_invalid_creation_environment_is_closed_json_without_path_leakage(tmp_path: Path, monkeypatch, capsys):
    import stm32_toolkit.cli as cli
    leaked = str(tmp_path / "private-tool.exe")

    def fail(*args, **kwargs):
        raise ValueError(f"candidate path {leaked} is invalid")

    monkeypatch.setattr(cli, "discover_tool_support", fail)
    code = main(
        [
            "project",
            "create-plan",
            "--project-root",
            str(tmp_path),
            "--source-kind",
            "mcu",
            "--source",
            "STM32F429ZITx",
            "--destination",
            "generated",
            "--framework",
            "hal",
            "--language",
            "c",
            "--json",
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["code"] == "CREATION_ENVIRONMENT_INVALID"
    assert leaked not in captured.err


def test_cli_create_prepare_requires_exact_plan_and_action_digest(tmp_path: Path, monkeypatch, capsys):
    import stm32_toolkit.cli as cli
    calls = []

    def fake_prepare(request, **kwargs):
        calls.append((request, kwargs))
        from stm32_toolkit.result import OperationResult
        return OperationResult.success("project-create-prepare", {"mutated": False, "authorizationDigest": "a" * 64})

    monkeypatch.setattr(cli, "prepare_creation_workflow", fake_prepare)
    code = main([
        "project", "create-prepare", "--project-root", str(tmp_path), "--source-kind", "mcu",
        "--source", "STM32F429ZITx", "--destination", "generated", "--framework", "hal", "--language", "c",
        "--plan-id", "b" * 64, "--action-digest", "c" * 64, "--json",
    ])
    assert code == 0
    assert calls and calls[0][1]["plan_id"] == "b" * 64
    assert json.loads(capsys.readouterr().out)["data"]["mutated"] is False


def test_cli_create_apply_forwards_only_authorization_digest_and_true(tmp_path: Path, monkeypatch, capsys):
    import stm32_toolkit.cli as cli
    calls = []

    def fake_apply(request, **kwargs):
        calls.append((request, kwargs))
        from stm32_toolkit.result import OperationResult
        return OperationResult.success("project-create-apply", {"mutated": True})

    monkeypatch.setattr(cli, "apply_creation_workflow", fake_apply)
    code = main([
        "project", "create-apply", "--project-root", str(tmp_path), "--authorization-digest", "a" * 64,
        "--authorized", "--json",
    ])
    assert code == 0
    assert calls and calls[0][1]["authorized"] is True
    assert json.loads(capsys.readouterr().out)["data"]["mutated"] is True


def test_cli_create_apply_without_authorized_is_rejected(tmp_path: Path):
    assert main([
        "project", "create-apply", "--project-root", str(tmp_path), "--authorization-digest", "a" * 64,
        "--json",
    ]) == 2


def test_cli_create_apply_rejects_repeated_authorized_flag(tmp_path: Path):
    with pytest.raises(SystemExit):
        _build_parser().parse_args([
            "project",
            "create-apply",
            "--project-root",
            str(tmp_path),
            "--authorization-digest",
            "a" * 64,
            "--authorized",
            "--authorized",
        ])
