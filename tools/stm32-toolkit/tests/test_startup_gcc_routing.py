"""Public CLI and MCP routing for the STARTUP-GCC options."""

from __future__ import annotations

import asyncio
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


def _destination(tmp_path):
    destination = tmp_path / "delivered" / "project"
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def test_cli_accepts_startup_options_for_preflight_and_plan(tmp_path, capsys):
    repo = two_assembly_repo(tmp_path)
    destination = _destination(tmp_path)

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
                "--destination",
                str(destination),
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["ok"] is True
    assert plan["data"]["options"]["startupOptions"] == {
        "strategy": "generate-cmsis-gcc",
        "source": STARTUP_SOURCE,
    }
    assert any(
        output["path"] == GENERATED_SOURCE
        for output in plan["data"]["outputs"]
    )
    assert not destination.exists()


def test_cli_apply_requires_the_same_startup_options(tmp_path, capsys):
    repo = startup_repo(tmp_path, name="cli-apply")
    destination = _destination(tmp_path)
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
                "--destination",
                str(destination),
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["planId"]

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
            "--destination",
            str(destination),
            "--apply",
            "--plan-id",
            plan_id,
            "--authorized",
            "--json",
        ]
    ) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    assert applied["data"]["outputRoot"] == str(destination)
    assert (destination / GENERATED_SOURCE).is_file()
    assert not (repo / GENERATED_SOURCE).exists()


def test_cli_rejects_an_unsupported_or_edited_strategy_without_writes(tmp_path, capsys):
    repo = two_assembly_repo(tmp_path)
    destination = _destination(tmp_path)
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
                "--destination",
                str(destination),
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["planId"]

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
            "--destination",
            str(destination),
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
            "--destination",
            str(destination),
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
    assert not destination.exists()


def test_mcp_preflight_and_convert_route_the_camel_case_options(tmp_path):
    repo = startup_repo(tmp_path, name="mcp-apply")
    destination = _destination(tmp_path)
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
        destination=str(destination),
    )
    assert planned["ok"] is True
    assert planned["data"]["options"]["startupOptions"] == {
        "strategy": "generate-cmsis-gcc",
        "source": STARTUP_SOURCE,
    }
    plan_id = planned["data"]["planId"]

    applied = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        plan_id,
        True,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
        destination=str(destination),
    )
    assert applied["ok"] is True
    assert (destination / GENERATED_SOURCE).is_file()
    assert not (repo / GENERATED_SOURCE).exists()


def test_registered_mcp_tools_bind_the_public_camel_case_startup_options(tmp_path):
    """The real registered server, not the snake-case helpers, owns the options."""
    repo = startup_repo(tmp_path, name="mcp-registered-startup")
    destination = _destination(tmp_path)
    server = mcp_mod.create_server(repo, tmp_path / "data", "session-startup-server")

    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for tool_name in ("stm32_keil_preflight", "stm32_keil_convert"):
        properties = tools[tool_name].inputSchema["properties"]
        assert "startupStrategy" in properties
        assert "startupSource" in properties
        assert "startup_strategy" not in properties
        assert "startup_source" not in properties
    assert "destination" in tools["stm32_keil_convert"].inputSchema["properties"]

    def call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        _, structured = asyncio.run(server.call_tool(tool_name, arguments))
        assert structured is not None
        return structured

    selection = {
        "uvprojx": UVPROJX,
        "targetName": TARGET,
        "destination": str(destination),
    }
    startup = {"startupStrategy": "generate-cmsis-gcc", "startupSource": STARTUP_SOURCE}

    preflight = call(
        "stm32_keil_preflight",
        {"uvprojx": UVPROJX, "targetName": TARGET, **startup},
    )
    assert preflight["ok"] is True
    assert preflight["data"]["analysis"]["startup"]["source_path"] == STARTUP_SOURCE

    planned = call("stm32_keil_convert", {**selection, **startup})
    assert planned["ok"] is True
    assert planned["data"]["options"]["startupOptions"] == {
        "strategy": "generate-cmsis-gcc",
        "source": STARTUP_SOURCE,
    }
    plan_id = planned["data"]["planId"]

    # With this single candidate, omitting startupSource still resolves to the
    # same file but is a different reviewed option set (and therefore a
    # different plan identity).  Neither that nor omitting both options may
    # apply the reviewed plan.
    changed = call(
        "stm32_keil_convert",
        {
            **selection,
            "planId": plan_id,
            "authorized": True,
            "startupStrategy": "generate-cmsis-gcc",
        },
    )
    assert changed["ok"] is False
    assert changed["code"] == "PLAN_CHANGED"
    assert not destination.exists()

    omitted = call(
        "stm32_keil_convert",
        {**selection, "planId": plan_id, "authorized": True},
    )
    assert omitted["ok"] is False
    assert omitted["code"] == "PLAN_CHANGED"
    assert not destination.exists()

    applied = call(
        "stm32_keil_convert",
        {**selection, **startup, "planId": plan_id, "authorized": True},
    )
    assert applied["ok"] is True
    assert (destination / GENERATED_SOURCE).is_file()
    assert not (repo / GENERATED_SOURCE).exists()


def test_mcp_apply_refuses_edited_startup_source(tmp_path):
    repo = two_assembly_repo(tmp_path)
    destination = _destination(tmp_path)
    runtime = ServerRuntime.create(repo, tmp_path / "data", "session-startup-2")
    planned = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
        destination=str(destination),
    )
    assert planned["ok"] is True
    plan_id = planned["data"]["planId"]

    edited = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        plan_id,
        True,
        startup_strategy="generate-cmsis-gcc",
        startup_source="DSP/filter.s",
        destination=str(destination),
    )
    assert edited["ok"] is False
    assert edited["code"] == "PLAN_CHANGED"
    assert not destination.exists()


def test_mcp_ambiguous_startup_selection_returns_candidates(tmp_path):
    repo = two_assembly_repo(tmp_path)
    destination = _destination(tmp_path)
    runtime = ServerRuntime.create(repo, tmp_path / "data", "session-startup-3")
    result = mcp_mod.tool_keil_convert(
        runtime,
        UVPROJX,
        TARGET,
        startup_strategy="generate-cmsis-gcc",
        destination=str(destination),
    )
    assert result["ok"] is False
    assert result["code"] == "MIGRATION_STARTUP_SELECTION_REQUIRED"
    assert result["details"]["candidates"] == ["DSP/filter.s", STARTUP_SOURCE]
    assert not destination.exists()
