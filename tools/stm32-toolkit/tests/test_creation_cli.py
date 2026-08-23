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
