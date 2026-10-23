"""Public CLI and MCP routing for the STARTUP-GCC options."""

from __future__ import annotations

import json

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.mcp_server import ServerRuntime

from startup_gcc_fixture import (
    GENERATED_SOURCE,
    STARTUP_SOURCE,
    TARGET,
    UVPROJX,
    startup_repo,
    two_assembly_repo,
)


def test_cli_accepts_startup_options_for_preflight_and_plan(tmp_path, capsys):
    repo = two_assembly_repo(tmp_path)

    assert (
        cli_main(
            [
                "keil",
                "preflight",
                "--project",
                str(repo),
                "--uvprojx",
                UVPROJX,
                "--target-name",
                TARGET,
                "--startup-strategy",
                "generate-cmsis-gcc",
                "--startup-source",
                STARTUP_SOURCE,
                "--json",
            ]
        )
        == 0
    )
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["ok"] is True
    assert preflight["data"]["analysis"]["startup"]["source_path"] == STARTUP_SOURCE

    assert (
        cli_main(
            [
                "keil",
                "convert",
                "--project",
                str(repo),
                "--uvprojx",
                UVPROJX,
                "--target-name",
                TARGET,
                "--startup-strategy",
                "generate-cmsis-gcc",
                "--startup-source",
                STARTUP_SOURCE,
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["ok"] is True
    assert plan["data"]["startup"]["status"] == "ready"
    assert any(
        patch["path"] == GENERATED_SOURCE for patch in plan["data"]["patches"]
    )


def test_cli_apply_requires_the_same_startup_options(tmp_path, capsys):
    repo = startup_repo(tmp_path, name="cli-apply")
    assert (
        cli_main(
            [
                "keil",
                "convert",
                "--project",
                str(repo),
                "--uvprojx",
                UVPROJX,
                "--target-name",
                TARGET,
                "--startup-strategy",
                "generate-cmsis-gcc",
                "--startup-source",
                STARTUP_SOURCE,
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["plan_id"]

    assert cli_main(
        [
            "keil",
            "convert",
            "--project",
            str(repo),
            "--uvprojx",
            UVPROJX,
            "--target-name",
            TARGET,
            "--startup-strategy",
            "generate-cmsis-gcc",
            "--startup-source",
            STARTUP_SOURCE,
            "--apply",
            "--plan-id",
            plan_id,
            "--authorized",
            "--json",
        ]
    ) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    assert (repo / GENERATED_SOURCE).is_file()


def test_cli_rejects_an_unsupported_or_edited_strategy_without_writes(tmp_path, capsys):
    repo = two_assembly_repo(tmp_path)
    assert (
        cli_main(
            [
                "keil",
                "convert",
                "--project",
                str(repo),
                "--uvprojx",
                UVPROJX,
                "--target-name",
                TARGET,
                "--startup-strategy",
                "generate-cmsis-gcc",
                "--startup-source",
                STARTUP_SOURCE,
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["plan_id"]

    assert cli_main(
        [
            "keil",
            "convert",
            "--project",
            str(repo),
            "--uvprojx",
            UVPROJX,
            "--target-name",
            TARGET,
            "--startup-strategy",
            "not-supported",
            "--dry-run",
            "--json",
        ]
    ) != 0
    failure = json.loads(capsys.readouterr().out)
    assert failure["code"] == "MIGRATION_STARTUP_STRATEGY_UNSUPPORTED"

    assert cli_main(
        [
            "keil",
            "convert",
            "--project",
            str(repo),
            "--uvprojx",
            UVPROJX,
            "--target-name",
            TARGET,
            "--startup-strategy",
            "generate-cmsis-gcc",
            "--startup-source",
            "DSP/filter.s",
            "--apply",
            "--plan-id",
            plan_id,
            "--authorized",
            "--json",
        ]
    ) != 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["code"] == "PLAN_CHANGED"
    assert not (repo / GENERATED_SOURCE).exists()


def test_mcp_preflight_and_convert_route_the_camel_case_options(tmp_path):
    repo = startup_repo(tmp_path, name="mcp-apply")
    runtime = ServerRuntime.create(repo, tmp_path / "data", "session-startup")

    preflight = mcp_mod.tool_keil_preflight(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert preflight["ok"] is True
    assert preflight["data"]["analysis"]["startup"]["source_path"] == STARTUP_SOURCE

    planned = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert planned["ok"] is True
    assert planned["data"]["startup"]["status"] == "ready"
    plan_id = planned["data"]["plan_id"]

    applied = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        plan_id,
        True,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert applied["ok"] is True
    assert (repo / GENERATED_SOURCE).is_file()


def test_mcp_apply_refuses_edited_startup_source(tmp_path):
    repo = two_assembly_repo(tmp_path)
    runtime = ServerRuntime.create(repo, tmp_path / "data", "session-startup-2")
    planned = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert planned["ok"] is True
    plan_id = planned["data"]["plan_id"]

    edited = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        plan_id,
        True,
        startup_strategy="generate-cmsis-gcc",
        startup_source="DSP/filter.s",
    )
    assert edited["ok"] is False
    assert edited["code"] == "PLAN_CHANGED"
    assert not (repo / GENERATED_SOURCE).exists()


def test_mcp_ambiguous_startup_selection_returns_candidates(tmp_path):
    repo = two_assembly_repo(tmp_path)
    runtime = ServerRuntime.create(repo, tmp_path / "data", "session-startup-3")
    result = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
    )
    assert result["ok"] is False
    assert result["code"] == "MIGRATION_STARTUP_SELECTION_REQUIRED"
    assert result["details"]["candidates"] == ["DSP/filter.s", STARTUP_SOURCE]
