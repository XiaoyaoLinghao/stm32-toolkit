"""Public WFI normal-return option route (M3b1).

These tests exercise the real public adapters only: repeatable CLI
``--wfi-return PATH:FUNCTION`` parsing and JSON output, the synchronous and
request-bound MCP wrappers, the actual registered ``@mcp.tool`` schemas and
calls, and workflow preflight -> PLAN -> APPLY.  Every project is a disposable
synthetic non-Git fixture below pytest's temporary directory; no compiler,
probe, network, hardware, or real user project is used.

The raw public form is a bounded list of exact ``{path, function}`` objects;
the accepted internal form remains the immutable ``WfiReturn`` tuple.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.migration.model import MigrationPlanError, WfiReturn
from stm32_toolkit.migration.source_intent import (
    MAX_WFI_RETURNS,
    WFI_NORMAL_BODY,
    WFI_RETURN_RULE_ID,
    normalize_wfi_return_options,
)
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES
from stm32_toolkit.workflows import (
    convert_keil_workflow,
    preflight_keil_workflow,
)

from test_migration_delivery import REPORT_PATH, output_parent, tree_digest
from test_migration_plan import FRAMEWORK_INCLUDE, build_repo

WFI_ONLY = "__asm void WFI_SET(void) { WFI; }\n"
#: Valid legacy explicit-return grammar (multiline, no ARMCC semicolons): this
#: wrapper keeps its historical supported translation and is never the
#: missing-return source-intent candidate.
WFI_EXPLICIT_RETURN = (
    "__asm void WFI_SET(void)\n"
    "{\n"
    "    WFI\n"
    "    BX LR\n"
    "}\n"
)
EXPECTED_WFI_AFTER = (
    "void WFI_SET(void)\n"
    "{\n"
    f"    {WFI_NORMAL_BODY}\n"
    "}\n"
)
WFI_A = "__asm void WFI_A(void) { WFI; }\n"
WFI_B = "__asm void WFI_B(void) { WFI; }\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def option(
    path: str = "Common/common.c", function: str = "WFI_SET"
) -> list[dict[str, str]]:
    return [{"path": path, "function": function}]


def single_repo(
    tmp_path: Path, *, name: str = "wfi-public", source: str = WFI_ONLY
) -> Path:
    return build_repo(
        tmp_path,
        name=name,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": source,
        },
        commit=False,
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Common", (("common.c", "1", "Common/common.c"),)),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
    )


def two_wfi_repo(tmp_path: Path, *, name: str = "wfi-public-two") -> Path:
    return build_repo(
        tmp_path,
        name=name,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/a.c": WFI_A,
            "Common/b.c": WFI_B,
        },
        commit=False,
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                (
                    "Common",
                    (("a.c", "1", "Common/a.c"), ("b.c", "1", "Common/b.c")),
                ),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
    )


def destination(tmp_path: Path, name: str = "public-output") -> Path:
    """An absent destination in a sibling tree, never inside the source."""
    return output_parent(tmp_path, name) / "project"


def convert_cli(repo: Path, dest: Path, extra: list[str], mode: str = "dry-run"):
    return cli_main(
        [
            "keil",
            "convert",
            "--project",
            str(repo),
            "--destination",
            str(dest),
            f"--{mode}",
            *extra,
            "--json",
        ]
    )


async def _call(server, name: str, arguments: dict) -> dict[str, object]:
    _content, structured = await server.call_tool(name, arguments)
    assert structured is not None
    return structured


# ---------------------------------------------------------------------------
# raw public normalizer: exact keys/types, no coercion, core validation reuse
# ---------------------------------------------------------------------------


def test_raw_option_normalizer_accepts_none_and_exact_objects() -> None:
    assert normalize_wfi_return_options(None) == ()
    assert normalize_wfi_return_options([]) == ()

    normalized = normalize_wfi_return_options(
        [
            {"path": "Common/z.c", "function": "z"},
            {"path": "Common/a.c", "function": "b"},
            {"path": "Common/a.c", "function": "a"},
        ]
    )
    assert normalized == (
        WfiReturn("Common/a.c", "a"),
        WfiReturn("Common/a.c", "b"),
        WfiReturn("Common/z.c", "z"),
    )
    # The result is the accepted immutable internal form.
    assert type(normalized) is tuple
    assert all(type(choice) is WfiReturn for choice in normalized)


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        (("Common/common.c", "WFI_SET"), "type"),
        ({"path": "Common/common.c", "function": "WFI_SET"}, "type"),
        ("Common/common.c:WFI_SET", "type"),
        ([("Common/common.c", "WFI_SET")], "type"),
        ([["Common/common.c", "WFI_SET"]], "type"),
        (
            [{"path": "Common/common.c", "function": "WFI_SET", "x": 1}],
            "unknownKey",
        ),
        ([{"path": "Common/common.c"}], "required"),
        ([{"function": "WFI_SET"}], "required"),
        ([{"path": 1, "function": "WFI_SET"}], "type"),
        ([{"path": "Common/common.c", "function": None}], "type"),
        ([{"path": "../outside.c", "function": "WFI_SET"}], "path"),
        ([{"path": "C:/outside.c", "function": "WFI_SET"}], "path"),
        ([{"path": "Common\\common.c", "function": "WFI_SET"}], "path"),
        ([{"path": "Common/common.h", "function": "WFI_SET"}], "path"),
        ([{"path": "Common/common.c", "function": "bad-name"}], "function"),
        ([{"path": "Common/common.c", "function": "1bad"}], "function"),
        ([{"path": "Common/common.c", "function": "a" * 129}], "function"),
        (
            [
                {"path": "Common/common.c", "function": "WFI_SET"},
                {"path": "Common/common.c", "function": "WFI_SET"},
            ],
            "duplicate",
        ),
    ],
)
def test_raw_option_normalizer_rejects_malformed_requests(
    value: object, rule: str
) -> None:
    with pytest.raises(MigrationPlanError) as caught:
        normalize_wfi_return_options(value)
    assert caught.value.code == "WFI_RETURNS_INVALID"
    assert caught.value.details["field"] == "wfiReturns"
    assert caught.value.details["rule"] == rule


def test_raw_option_normalizer_bounds_count_and_keeps_drive_path_intact() -> None:
    too_many = [
        {"path": f"Common/f{index}.c", "function": f"f{index}"}
        for index in range(MAX_WFI_RETURNS + 1)
    ]
    with pytest.raises(MigrationPlanError) as caught:
        normalize_wfi_return_options(too_many)
    assert caught.value.details["rule"] == "limit"

    with pytest.raises(MigrationPlanError) as drive:
        normalize_wfi_return_options(
            option(path="C:/outside/common.c")
        )
    assert drive.value.details["rule"] == "path"
    # The drive path is rejected exactly as supplied, never rewritten into a
    # project-relative path.
    assert drive.value.details["path"] == "C:/outside/common.c"


# ---------------------------------------------------------------------------
# real CLI parsing, JSON output and actionable malformed values
# ---------------------------------------------------------------------------


def test_cli_preflight_parses_repeatable_wfi_returns(
    tmp_path: Path, capsys
) -> None:
    repo = two_wfi_repo(tmp_path)

    assert (
        cli_main(
            [
                "keil",
                "preflight",
                "--project",
                str(repo),
                "--wfi-return",
                "Common/b.c:WFI_B",
                "--wfi-return",
                "Common/a.c:WFI_A",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    direct = preflight_keil_workflow(
        repo,
        wfi_returns=[
            {"path": "Common/b.c", "function": "WFI_B"},
            {"path": "Common/a.c", "function": "WFI_A"},
        ],
    ).to_dict()

    assert payload["operation"] == "keil-preflight"
    assert payload["ok"] is True
    assert payload["data"] == direct["data"]
    assert payload["data"]["analysis"]["blockers"] == []
    # The normalizer orders the same logical choices deterministically.
    assert [
        (entry["path"], entry["function"])
        for entry in payload["data"]["analysis"]["wfiReturns"]
    ] == [("Common/a.c", "WFI_A"), ("Common/b.c", "WFI_B")]


@pytest.mark.parametrize(
    "value",
    ["Common/common.c", "Common/common.c:", ":WFI_SET", "", ":"],
)
def test_cli_malformed_wfi_return_is_actionable(
    tmp_path: Path, capsys, value: str
) -> None:
    repo = single_repo(tmp_path, name="syntax")

    assert (
        cli_main(
            [
                "keil",
                "preflight",
                "--project",
                str(repo),
                "--wfi-return",
                value,
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["operation"] == "keil-preflight"
    assert payload["code"] == "WFI_RETURNS_INVALID"
    assert payload["details"]["field"] == "wfiReturns"
    assert payload["details"]["rule"] == "syntax"
    assert payload["details"]["example"] == "Common/common.c:WFI_SET"
    assert "PATH:FUNCTION" in payload["message"]


def test_cli_drive_path_is_refused_as_a_path_not_relativized(
    tmp_path: Path, capsys
) -> None:
    repo = single_repo(tmp_path, name="drive-path")

    assert (
        cli_main(
            [
                "keil",
                "preflight",
                "--project",
                str(repo),
                "--wfi-return",
                "C:/outside/common.c:WFI_SET",
                "--json",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "WFI_RETURNS_INVALID"
    assert payload["details"]["rule"] == "path"
    assert payload["details"]["path"] == "C:/outside/common.c"


# ---------------------------------------------------------------------------
# workflow preflight -> PLAN -> APPLY with the exact public option
# ---------------------------------------------------------------------------


def test_workflow_preflight_plan_apply_binds_exact_option_and_hashes(
    tmp_path: Path,
) -> None:
    repo = single_repo(tmp_path, name="workflow")
    original = (repo / "Common" / "common.c").read_bytes()
    before_tree = tree_digest(repo)
    dest = destination(tmp_path, "workflow-output")
    choices = option()

    preflight = preflight_keil_workflow(repo, wfi_returns=choices)
    assert preflight.ok is True, preflight.to_dict()
    data = preflight.to_dict()["data"]
    assert data["analysis"]["blockers"] == []
    assert data["planReadiness"]["status"] == "ready-for-plan"
    expected_after = EXPECTED_WFI_AFTER.encode("utf-8")
    assert data["analysis"]["wfiReturns"] == [
        {
            "path": "Common/common.c",
            "function": "WFI_SET",
            "sourceSha256": sha256(original),
            "convertedSha256": sha256(expected_after),
            "requestedBehavior": "normal-return",
            "binaryEquivalent": False,
        }
    ]
    changes = {
        change["path"]: change for change in data["analysis"]["sourceChanges"]
    }
    assert changes["Common/common.c"]["ruleIds"] == [WFI_RETURN_RULE_ID]

    plan = convert_keil_workflow(repo, destination=dest, wfi_returns=choices)
    assert plan.ok is True, plan.to_dict()
    preview = plan.to_dict()["data"]
    assert plan.operation == "keil-conversion-plan"
    assert preview["options"]["wfiReturns"] == [
        {"path": "Common/common.c", "function": "WFI_SET"}
    ]
    patch = next(
        item
        for item in preview["sourcePatches"]
        if item["path"] == "Common/common.c"
    )
    assert patch["rule_ids"] == [WFI_RETURN_RULE_ID]
    assert patch["before_sha256"] == sha256(original)
    assert patch["after_sha256"] == sha256(expected_after)
    output = next(
        item
        for item in preview["outputs"]
        if item["path"] == "Common/common.c"
    )
    assert output["sha256"] == sha256(expected_after)
    assert output["kind"] == "replaced"
    assert not dest.exists()

    applied = convert_keil_workflow(
        repo,
        destination=dest,
        plan_id=preview["planId"],
        authorized=True,
        wfi_returns=choices,
    )
    assert applied.ok is True, applied.to_dict()
    assert applied.operation == "keil-conversion-apply"
    assert applied.to_dict()["data"]["outputRoot"] == str(dest)
    assert (dest / "Common" / "common.c").read_bytes() == expected_after
    # The source is read-only throughout planning and apply.
    assert (repo / "Common" / "common.c").read_bytes() == original
    assert tree_digest(repo) == before_tree

    report = json.loads((dest / REPORT_PATH).read_text(encoding="utf-8"))
    assert report["wfiReturns"] == [
        {
            "path": "Common/common.c",
            "function": "WFI_SET",
            "sourceSha256": sha256(original),
            "convertedSha256": sha256(expected_after),
            "requestedBehavior": "normal-return",
            "binaryEquivalent": False,
        }
    ]
    assert report["sourceSnapshotSha256"] == (
        applied.to_dict()["data"]["sourceSnapshotSha256"]
    )


def test_workflow_apply_reuses_the_reviewed_choice_in_any_raw_order(
    tmp_path: Path,
) -> None:
    repo = two_wfi_repo(tmp_path, name="reordered")
    dest = destination(tmp_path, "reordered-output")
    both = [
        {"path": "Common/a.c", "function": "WFI_A"},
        {"path": "Common/b.c", "function": "WFI_B"},
    ]

    plan = convert_keil_workflow(repo, destination=dest, wfi_returns=both)
    assert plan.ok is True, plan.to_dict()
    plan_id = plan.to_dict()["data"]["planId"]

    applied = convert_keil_workflow(
        repo,
        destination=dest,
        plan_id=plan_id,
        authorized=True,
        wfi_returns=list(reversed(both)),
    )
    assert applied.ok is True, applied.to_dict()
    assert applied.operation == "keil-conversion-apply"
    assert b"void WFI_A(void)" in (dest / "Common" / "a.c").read_bytes()
    assert b"void WFI_B(void)" in (dest / "Common" / "b.c").read_bytes()


def test_workflow_refuses_omitted_changed_and_invalid_selections(
    tmp_path: Path,
) -> None:
    repo = single_repo(tmp_path, name="refusal")
    before_tree = tree_digest(repo)
    dest = destination(tmp_path, "refusal-output")
    plan = convert_keil_workflow(repo, destination=dest, wfi_returns=option())
    assert plan.ok is True, plan.to_dict()
    plan_id = plan.to_dict()["data"]["planId"]

    # Omitting the reviewed choice leaves the technical blocker in place; the
    # established technical-blocker precedence wins over staleness.
    omitted = convert_keil_workflow(
        repo, destination=dest, plan_id=plan_id, authorized=True
    )
    assert omitted.ok is False
    assert omitted.code == "DELIVERY_BLOCKED"
    assert "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED" in (
        omitted.details["blockerCodes"]
    )
    assert not dest.exists()

    # A changed but syntactically valid choice is unused and refused before
    # plan identity.
    changed = convert_keil_workflow(
        repo,
        destination=dest,
        plan_id=plan_id,
        authorized=True,
        wfi_returns=option(function="OTHER"),
    )
    assert changed.ok is False
    assert changed.code == "WFI_RETURN_UNUSED"
    assert not dest.exists()

    unknown = convert_keil_workflow(
        repo,
        destination=dest,
        plan_id=plan_id,
        authorized=True,
        wfi_returns=[
            {"path": "Common/common.c", "function": "WFI_SET", "extra": 1}
        ],
    )
    assert unknown.ok is False
    assert unknown.code == "WFI_RETURNS_INVALID"
    assert unknown.details["rule"] == "unknownKey"
    assert not dest.exists()

    # Raw transport shapes fail in the adapter before any plan/destination
    # work; a tuple is never silently accepted as the public list form.
    for raw in (
        ("Common/common.c", "WFI_SET"),
        [("Common/common.c", "WFI_SET")],
        "Common/common.c:WFI_SET",
    ):
        invalid = convert_keil_workflow(
            repo, destination=dest, plan_id=plan_id, authorized=True,
            wfi_returns=raw,
        )
        assert invalid.ok is False
        assert invalid.code == "WFI_RETURNS_INVALID"
        assert invalid.details["rule"] == "type"
        assert not dest.exists()

    assert tree_digest(repo) == before_tree


def test_cli_convert_plan_and_apply_carry_the_option(
    tmp_path: Path, capsys
) -> None:
    repo = single_repo(tmp_path, name="cli-convert")
    original = (repo / "Common" / "common.c").read_bytes()
    dest = destination(tmp_path, "cli-convert-output")
    flag = ["--wfi-return", "Common/common.c:WFI_SET"]

    assert convert_cli(repo, dest, flag) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["operation"] == "keil-conversion-plan"
    assert plan["ok"] is True
    assert plan["data"]["options"]["wfiReturns"] == [
        {"path": "Common/common.c", "function": "WFI_SET"}
    ]
    plan_id = plan["data"]["planId"]

    # Omitting the reviewed selection at apply time re-plans to the blocked
    # state and never publishes the reviewed plan.
    assert (
        convert_cli(
            repo, dest, ["--plan-id", plan_id, "--authorized"], mode="apply"
        )
        == 2
    )
    omitted = json.loads(capsys.readouterr().out)
    assert omitted["code"] == "DELIVERY_BLOCKED"
    assert not dest.exists()

    assert (
        convert_cli(
            repo,
            dest,
            ["--plan-id", plan_id, *flag, "--authorized"],
            mode="apply",
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["operation"] == "keil-conversion-apply"
    assert applied["ok"] is True
    assert (dest / "Common" / "common.c").read_bytes() == (
        EXPECTED_WFI_AFTER.encode("utf-8")
    )
    assert (repo / "Common" / "common.c").read_bytes() == original


def test_no_option_compatibility_and_explicit_return_control(
    tmp_path: Path,
) -> None:
    # Valid multiline legacy explicit-return grammar: the historical supported
    # translation needs no new option and carries no wfiReturns key.
    repo = single_repo(
        tmp_path, name="explicit-return", source=WFI_EXPLICIT_RETURN
    )
    original = (repo / "Common" / "common.c").read_bytes()
    dest = destination(tmp_path, "control-output")

    preflight = preflight_keil_workflow(repo)
    assert preflight.ok is True, preflight.to_dict()
    preflight_data = preflight.to_dict()["data"]
    assert preflight_data["analysis"]["blockers"] == []
    assert "wfiReturns" not in json.dumps(preflight_data)

    plan = convert_keil_workflow(repo, destination=dest)
    assert plan.ok is True, plan.to_dict()
    preview = plan.to_dict()["data"]
    assert set(preview["options"]) == {
        "startupOptions",
        "memoryLayout",
        "extraRegions",
    }
    assert "wfiReturns" not in json.dumps(preview)
    applied = convert_keil_workflow(
        repo,
        destination=dest,
        plan_id=preview["planId"],
        authorized=True,
    )
    assert applied.ok is True, applied.to_dict()
    assert (repo / "Common" / "common.c").read_bytes() == original
    report = json.loads((dest / REPORT_PATH).read_text(encoding="utf-8"))
    assert "wfiReturns" not in report

    # The same wrapper is never eligible for the missing-return choice; the
    # refusal comes from the adapter with no destination effect.
    other = destination(tmp_path, "control-refusal-output")
    refused = convert_keil_workflow(
        repo, destination=other, wfi_returns=option()
    )
    assert refused.ok is False
    assert refused.code == "WFI_RETURN_AMBIGUOUS"
    assert refused.details["rule"] == "explicitReturn"
    assert not other.exists()


# ---------------------------------------------------------------------------
# actual registered MCP tools: schema, calls, request-bound wrapper
# ---------------------------------------------------------------------------


def test_registered_mcp_schema_and_calls_expose_wfi_returns(
    tmp_path: Path,
) -> None:
    repo = single_repo(tmp_path, name="mcp-public")
    original = (repo / "Common" / "common.c").read_bytes()
    runtime = ServerRuntime.create(repo, tmp_path / "plugin-data", "session-a")
    server = create_server(repo, tmp_path / "plugin-data", "session-public")
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    assert set(MCP_TOOL_NAMES.values()) == set(tools)
    for tool_name in ("stm32_keil_preflight", "stm32_keil_convert"):
        properties = tools[tool_name].inputSchema["properties"]
        assert "array" in str(properties["wfiReturns"])
        assert "object" in str(properties["wfiReturns"])
        assert tools[tool_name].inputSchema.get("required", []) == []

    choices = [{"path": "Common/common.c", "function": "WFI_SET"}]
    preflight = asyncio.run(
        _call(server, "stm32_keil_preflight", {"wfiReturns": choices})
    )
    assert preflight["ok"] is True, preflight
    assert preflight["operation"] == "keil-preflight"
    assert [
        (entry["path"], entry["function"])
        for entry in preflight["data"]["analysis"]["wfiReturns"]
    ] == [("Common/common.c", "WFI_SET")]

    # The synchronous and request-bound adapters carry the same raw value.
    sync = mcp_mod.tool_keil_preflight(runtime, wfi_returns=choices)
    bound = asyncio.run(
        mcp_mod.tool_keil_preflight_for_request(
            runtime, None, wfi_returns=choices
        )
    )
    assert sync["data"] == preflight["data"] == bound["data"]

    bound_dest = destination(tmp_path, "mcp-bound-output")
    bound_plan = asyncio.run(
        mcp_mod.tool_keil_convert_for_request(
            runtime,
            None,
            destination=str(bound_dest),
            wfi_returns=choices,
        )
    )
    assert bound_plan["ok"] is True, bound_plan
    assert bound_plan["data"]["options"]["wfiReturns"] == choices
    assert not bound_dest.exists()

    dest = destination(tmp_path, "mcp-output")
    plan = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {"destination": str(dest), "wfiReturns": choices},
        )
    )
    assert plan["ok"] is True, plan
    assert plan["data"]["options"]["wfiReturns"] == choices

    applied = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {
                "destination": str(dest),
                "planId": plan["data"]["planId"],
                "authorized": True,
                "wfiReturns": choices,
            },
        )
    )
    assert applied["ok"] is True, applied
    assert applied["operation"] == "keil-conversion-apply"
    assert (dest / "Common" / "common.c").read_bytes() == (
        EXPECTED_WFI_AFTER.encode("utf-8")
    )
    assert (repo / "Common" / "common.c").read_bytes() == original

    # Unknown/raw option content is refused by the shared validator before the
    # destination is created.
    invalid_dest = destination(tmp_path, "mcp-invalid-output")
    unknown = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {
                "destination": str(invalid_dest),
                "wfiReturns": [
                    {
                        "path": "Common/common.c",
                        "function": "WFI_SET",
                        "extra": True,
                    }
                ],
            },
        )
    )
    assert unknown["ok"] is False
    assert unknown["code"] == "WFI_RETURNS_INVALID"
    assert unknown["details"]["rule"] == "unknownKey"
    assert not invalid_dest.exists()

    non_string_value = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {
                "destination": str(invalid_dest),
                "wfiReturns": [
                    {"path": "Common/common.c", "function": 7}
                ],
            },
        )
    )
    assert non_string_value["ok"] is False
    assert non_string_value["code"] == "WFI_RETURNS_INVALID"
    assert non_string_value["details"]["rule"] == "type"
    assert not invalid_dest.exists()
