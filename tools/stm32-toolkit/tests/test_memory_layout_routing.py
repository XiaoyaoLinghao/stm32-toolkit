"""Public CLI and MCP routing for the explicit memory-layout options."""

from __future__ import annotations

import asyncio
import json

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main

from startup_gcc_fixture import STARTUP_SOURCE, TARGET, UVPROJX
from test_memory_layout_migration import ALL_MAIN, SPLIT, multi_ram_repo

STARTUP_ARGS = [
    "--startup-strategy",
    "generate-cmsis-gcc",
    "--startup-source",
    STARTUP_SOURCE,
]


def _preflight(repo, layout_text: str | None):
    arguments = [
        "keil",
        "preflight",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        *STARTUP_ARGS,
        "--json",
    ]
    if layout_text is not None:
        arguments[arguments.index("--json"):arguments.index("--json")] = [
            "--memory-layout",
            layout_text,
        ]
    return cli_main(arguments)


def _convert(repo, layout_text: str | None, *extra: str):
    arguments = [
        "keil",
        "convert",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        *STARTUP_ARGS,
        *extra,
        "--json",
    ]
    if layout_text is not None:
        arguments[arguments.index("--json"):arguments.index("--json")] = [
            "--memory-layout",
            layout_text,
        ]
    return cli_main(arguments)


def test_cli_preflight_and_plan_route_the_exact_json_layout(tmp_path, capsys):
    repo = multi_ram_repo(tmp_path / "cli")
    layout_text = json.dumps(ALL_MAIN.to_dict())

    assert _preflight(repo, layout_text) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["ok"] is True
    assert preflight["data"]["analysis"]["memoryLayout"]["status"] == "explicit"
    assert (
        preflight["data"]["analysis"]["memoryLayout"]["layout"]
        == ALL_MAIN.to_dict()
    )

    assert _convert(repo, layout_text, "--dry-run") == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["ok"] is True
    assert plan["data"]["memory_layout"]["status"] == "explicit"
    assert plan["data"]["memory_layout"]["layout"] == ALL_MAIN.to_dict()
    manifest = next(
        patch for patch in plan["data"]["patches"]
        if patch["path"] == ".stm32-project.json"
    )
    added = "".join(
        line[1:] + "\n"
        for line in manifest["unified_diff"].splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    payload = json.loads(added)
    assert payload["memory"]["layout"] == ALL_MAIN.to_dict()


def test_cli_no_layout_returns_candidates_and_a_blocker(tmp_path, capsys):
    repo = multi_ram_repo(tmp_path / "cli-required")
    assert _preflight(repo, None) == 0
    preflight = json.loads(capsys.readouterr().out)
    layout = preflight["data"]["analysis"]["memoryLayout"]
    assert layout["status"] == "requires-selection"
    assert layout["layout"] is None
    assert [entry["name"] for entry in layout["candidates"]["ram"]] == [
        "IRAM1",
        "IRAM2",
    ]
    codes = {
        blocker["code"] for blocker in preflight["data"]["analysis"]["blockers"]
    }
    assert "MEMORY_LAYOUT_REQUIRED" in codes


def test_cli_rejects_duplicate_keys_before_inspection(tmp_path, capsys):
    repo = multi_ram_repo(tmp_path / "cli-duplicate")
    duplicate = (
        '{"flash":"IROM1","flash":"IROM1","data":"IRAM1",'
        '"bss":"IRAM1","heap":"IRAM1","stack":"IRAM1"}'
    )
    # A missing uvprojx proves the JSON failure happens before inspection.
    arguments = [
        "keil",
        "preflight",
        "--project",
        str(repo),
        "--uvprojx",
        "missing.uvprojx",
        "--target-name",
        TARGET,
        "--memory-layout",
        duplicate,
        "--json",
    ]
    assert cli_main(arguments) != 0
    failure = json.loads(capsys.readouterr().out)
    assert failure["code"] == "MEMORY_LAYOUT_INVALID"
    assert failure["details"] == {
        "field": "memoryLayout",
        "rule": "duplicateKey",
        "remediation": failure["details"].get("remediation"),
    }


def test_cli_rejects_oversized_json_integers_before_inspection(tmp_path, capsys):
    """Regression: json's integer-string ValueError must be a layout failure."""
    repo = multi_ram_repo(tmp_path / "cli-overflow")
    arguments = [
        "keil",
        "convert",
        "--project",
        str(repo),
        "--uvprojx",
        "missing.uvprojx",
        "--target-name",
        TARGET,
        "--memory-layout",
        '{"flash":' + "9" * 5000 + "}",
        "--json",
    ]
    assert cli_main(arguments) != 0
    failure = json.loads(capsys.readouterr().out)
    assert failure["code"] == "MEMORY_LAYOUT_INVALID"
    assert failure["details"]["field"] == "memoryLayout"
    assert failure["details"]["rule"] == "json"
    assert "remediation" in failure["details"]


def test_cli_rejects_unknown_incomplete_and_nonstring_roles_before_inspection(
    tmp_path, capsys
):
    repo = multi_ram_repo(tmp_path / "cli-invalid")
    cases = [
        ({**ALL_MAIN.to_dict(), "extra": "IRAM1"}, "memoryLayout.extra", "unknownKey"),
        (
            {key: value for key, value in ALL_MAIN.to_dict().items() if key != "bss"},
            "memoryLayout.bss",
            "required",
        ),
        ({**ALL_MAIN.to_dict(), "flash": 7}, "memoryLayout.flash", "type"),
    ]
    for payload, field, rule in cases:
        arguments = [
            "keil",
            "convert",
            "--project",
            str(repo),
            "--uvprojx",
            "missing.uvprojx",
            "--target-name",
            TARGET,
            "--memory-layout",
            json.dumps(payload),
            "--json",
        ]
        assert cli_main(arguments) != 0
        failure = json.loads(capsys.readouterr().out)
        assert failure["code"] == "MEMORY_LAYOUT_INVALID"
        assert failure["details"]["field"] == field
        assert failure["details"]["rule"] == rule


def test_cli_repeated_memory_layout_argument_fails_as_grammar(tmp_path, capsys):
    repo = multi_ram_repo(tmp_path / "cli-repeat")
    arguments = [
        "keil",
        "convert",
        "--project",
        str(repo),
        "--uvprojx",
        UVPROJX,
        "--target-name",
        TARGET,
        "--memory-layout",
        json.dumps(ALL_MAIN.to_dict()),
        "--memory-layout",
        json.dumps(ALL_MAIN.to_dict()),
        "--json",
    ]
    assert cli_main(arguments) == 2
    assert capsys.readouterr().out == ""


def test_cli_apply_requires_the_same_layout_choice(tmp_path, capsys):
    repo = multi_ram_repo(tmp_path / "cli-apply")
    assert _convert(repo, json.dumps(SPLIT.to_dict()), "--dry-run") == 0
    planned = json.loads(capsys.readouterr().out)
    plan_id = planned["data"]["plan_id"]

    # Omission is a different reviewed request.
    assert _convert(repo, None, "--apply", "--plan-id", plan_id, "--authorized") != 0
    omitted = json.loads(capsys.readouterr().out)
    assert omitted["code"] == "PLAN_CHANGED"

    # A valid but different mapping is also a different choice.
    assert (
        _convert(
            repo,
            json.dumps(ALL_MAIN.to_dict()),
            "--apply",
            "--plan-id",
            plan_id,
            "--authorized",
        )
        != 0
    )
    changed = json.loads(capsys.readouterr().out)
    assert changed["code"] == "PLAN_CHANGED"

    assert (
        _convert(
            repo,
            json.dumps(SPLIT.to_dict()),
            "--apply",
            "--plan-id",
            plan_id,
            "--authorized",
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    manifest = json.loads((repo / ".stm32-project.json").read_text("utf-8"))
    assert manifest["memory"]["layout"] == SPLIT.to_dict()


def test_registered_mcp_tools_bind_the_public_camel_case_memory_layout(tmp_path):
    repo = multi_ram_repo(tmp_path / "mcp")
    server = mcp_mod.create_server(repo, tmp_path / "data", "session-memory-layout")

    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for tool_name in ("stm32_keil_preflight", "stm32_keil_convert"):
        properties = tools[tool_name].inputSchema["properties"]
        assert "memoryLayout" in properties
        assert "memory_layout" not in properties

    def call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        _, structured = asyncio.run(server.call_tool(tool_name, arguments))
        assert structured is not None
        return structured

    selection = {
        "uvprojx": UVPROJX,
        "targetName": TARGET,
        "startupStrategy": "generate-cmsis-gcc",
        "startupSource": STARTUP_SOURCE,
    }
    required = call("stm32_keil_preflight", selection)
    assert required["ok"] is True
    assert required["data"]["analysis"]["memoryLayout"]["status"] == (
        "requires-selection"
    )

    planned = call(
        "stm32_keil_convert", {**selection, "memoryLayout": SPLIT.to_dict()}
    )
    assert planned["ok"] is True
    assert planned["data"]["memory_layout"]["status"] == "explicit"
    assert planned["data"]["memory_layout"]["layout"] == SPLIT.to_dict()
    plan_id = planned["data"]["plan_id"]

    omitted = call(
        "stm32_keil_convert",
        {**selection, "planId": plan_id, "authorized": True},
    )
    assert omitted["ok"] is False
    assert omitted["code"] == "PLAN_CHANGED"

    edited = call(
        "stm32_keil_convert",
        {
            **selection,
            "memoryLayout": ALL_MAIN.to_dict(),
            "planId": plan_id,
            "authorized": True,
        },
    )
    assert edited["ok"] is False
    assert edited["code"] == "PLAN_CHANGED"
    assert not (repo / ".stm32-project.json").exists()

    applied = call(
        "stm32_keil_convert",
        {
            **selection,
            "memoryLayout": SPLIT.to_dict(),
            "planId": plan_id,
            "authorized": True,
        },
    )
    assert applied["ok"] is True
    manifest = json.loads((repo / ".stm32-project.json").read_text("utf-8"))
    assert manifest["memory"]["layout"] == SPLIT.to_dict()


def test_registered_mcp_invalid_layout_is_a_structured_failure(tmp_path):
    repo = multi_ram_repo(tmp_path / "mcp-invalid")
    server = mcp_mod.create_server(
        repo, tmp_path / "data", "session-invalid-layout"
    )
    _, structured = asyncio.run(
        server.call_tool(
            "stm32_keil_preflight",
            {
                "uvprojx": UVPROJX,
                "targetName": TARGET,
                "memoryLayout": {**ALL_MAIN.to_dict(), "extra": "IRAM1"},
            },
        )
    )
    assert structured is not None
    assert structured["ok"] is False
    assert structured["code"] == "MEMORY_LAYOUT_INVALID"
    assert structured["details"]["field"] == "memoryLayout.extra"
    assert structured["details"]["rule"] == "unknownKey"
    assert "remediation" in structured["details"]
