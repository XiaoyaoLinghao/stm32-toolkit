from __future__ import annotations

import json
from pathlib import Path

from stm32_toolkit.cli import main


def test_cli_create_plan_is_read_only_and_supports_mcu(tmp_path: Path, capsys):
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    assert main(["project", "create-plan", "--project-root", str(tmp_path), "--source-kind", "mcu", "--source", "STM32F429ZITx", "--destination", "generated", "--framework", "hal", "--language", "c", "--json"]) in (0, 2)
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "project-create-plan"
    assert payload["data"]["mutated"] is False
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before
