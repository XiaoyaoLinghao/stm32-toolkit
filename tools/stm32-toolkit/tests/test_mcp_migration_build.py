"""MCP migration/build tools, schemas, roots guard, and the end-to-end gate
(STM32TK-0306).

The four new tools are permanently bound to ``ServerRuntime.project_root``;
every request wrapper runs the existing client-roots guard before adapter
work.  The end-to-end test copies the committed Keil fixture, makes it
convertible (removes the blocker pragmas and the assembly source), and runs
inspect -> conversion plan/apply -> configuration plan/apply -> fake build,
linking plan IDs, the conversion report, the managed manifest, the build
result, the identity, hashes, and Git HEAD.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.context import build_project_context
from stm32_toolkit.mcp_server import ServerRuntime, create_server, main
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
)

from test_build_runner import install_fake_cmake, prepare_project
from test_mcp_roots import _RootSession, _context
from test_migration_apply import git_init

FIXTURES = Path(__file__).parent / "fixtures"
GITIGNORE = "build/\n.stm32-toolkit/build.lock\n__pycache__/\n*.pyc\n"

WRAPPERS = {
    "stm32_keil_inspect": mcp_mod.tool_keil_inspect_for_request,
    "stm32_keil_convert": mcp_mod.tool_keil_convert_for_request,
    "stm32_project_configure": mcp_mod.tool_project_configure_for_request,
    "stm32_build": mcp_mod.tool_build_for_request,
}
BUILD_ARGUMENTS = {"stm32_build": {"preset": "arm-debug"}}


COMMON_C = (
    "/* common.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void systick_isr(void)\n"
    "{\n"
    "    __nop();\n"
    "    __wfi();\n"
    "}\n"
    "\n"
    '__asm("nop");\n'
    "\n"
    '__attribute__((section(".common.data"))) int shared_value;\n'
    "__attribute__((at(0x20000000))) int pinned_value;\n"
    "\n"
    "int common_work(void) { return 0; }\n"
)

MAIN_C = (
    "/* main.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void early_init(void) { __nop(); }\n"
    "\n"
    "int main(void) { return 0; }\n"
)


def _keil_runtime(tmp_path: Path) -> ServerRuntime:
    from test_migration_apply import build_repo

    project = build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        gitignore=GITIGNORE,
    )
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


async def _call(server, name: str, arguments: dict) -> dict[str, object]:
    _content, structured = await server.call_tool(name, arguments)
    return structured


def convertible_fixture_copy(tmp_path: Path) -> Path:
    """Copy the committed naturally-convertible Keil fixture.

    Only the copy and Git init happen here: no uvprojx/source/scatter/
    include/FPU content is rewritten before the first public workflow call.
    """
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "keil-convertible", root)
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    git_init(root)
    return root


# ---------------------------------------------------------------------------
# registry and schemas
# ---------------------------------------------------------------------------


def _registry_server(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    return create_server(project, tmp_path / "plugin-data", "session-a")


def test_server_registers_exactly_seven_project_bound_tools(tmp_path: Path):
    server = _registry_server(tmp_path)
    tools = asyncio.run(server.list_tools())

    assert server.name == "STM32 Toolkit"
    assert "permanently bound" in server.instructions
    assert "explicitly authorized" in server.instructions
    assert "only read-only foundation tools" not in server.instructions
    assert {tool.name for tool in tools} == {
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
        "stm32_keil_inspect",
        "stm32_keil_convert",
        "stm32_project_configure",
        "stm32_build",
    }


def test_new_tool_schemas_expose_only_declared_properties(tmp_path: Path):
    server = _registry_server(tmp_path)
    tools = asyncio.run(server.list_tools())
    schemas = {tool.name: tool.inputSchema for tool in tools}

    inspect = schemas["stm32_keil_inspect"]
    assert set(inspect["properties"]) == {"uvprojx", "targetName", "includeBaseline"}
    assert set(inspect.get("required", [])) == set()
    assert "string" in str(inspect["properties"]["uvprojx"])
    assert "string" in str(inspect["properties"]["targetName"])
    assert inspect["properties"]["includeBaseline"]["type"] == "boolean"
    assert inspect["properties"]["includeBaseline"]["default"] is True

    convert = schemas["stm32_keil_convert"]
    assert set(convert["properties"]) == {"uvprojx", "targetName", "planId", "authorized"}
    assert set(convert.get("required", [])) == set()
    assert "string" in str(convert["properties"]["planId"])
    assert convert["properties"]["authorized"]["type"] == "boolean"
    assert convert["properties"]["authorized"]["default"] is False

    configure = schemas["stm32_project_configure"]
    assert set(configure["properties"]) == {"planId", "authorized"}
    assert set(configure.get("required", [])) == set()
    assert "string" in str(configure["properties"]["planId"])
    assert configure["properties"]["authorized"]["type"] == "boolean"
    assert configure["properties"]["authorized"]["default"] is False

    build = schemas["stm32_build"]
    assert set(build["properties"]) == {"preset", "clean", "timeoutSeconds", "authorized"}
    assert build["required"] == ["preset"]
    assert build["properties"]["preset"]["enum"] == ["arm-debug", "arm-release"]
    assert build["properties"]["preset"]["type"] == "string"
    assert build["properties"]["clean"]["type"] == "boolean"
    assert build["properties"]["clean"]["default"] is False
    assert build["properties"]["timeoutSeconds"]["type"] == "integer"
    assert build["properties"]["timeoutSeconds"]["default"] == 300
    assert build["properties"]["timeoutSeconds"]["minimum"] == 1
    assert build["properties"]["timeoutSeconds"]["maximum"] == 3600
    assert build["properties"]["authorized"]["type"] == "boolean"
    assert build["properties"]["authorized"]["default"] is False

    for name in (
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
    ):
        assert schemas[name].get("properties", {}) == {}
        assert schemas[name].get("required", []) == []


def test_no_tool_accepts_a_root_command_or_environment_parameter(tmp_path: Path):
    server = _registry_server(tmp_path)
    tools = asyncio.run(server.list_tools())

    forbidden = {
        "projectRoot",
        "project_root",
        "dataRoot",
        "data_root",
        "command",
        "environment",
        "sessionId",
        "session_id",
        "argv",
    }
    for tool in tools:
        assert not (set(tool.inputSchema.get("properties", {})) & forbidden)


# ---------------------------------------------------------------------------
# direct helpers and in-memory FastMCP two-phase flow
# ---------------------------------------------------------------------------


def test_direct_helpers_return_operation_result_envelopes(tmp_path: Path):
    runtime = _keil_runtime(tmp_path)

    assert mcp_mod.tool_keil_inspect(runtime)["operation"] == "keil-inspect"
    assert (
        mcp_mod.tool_keil_convert(runtime)["operation"] == "keil-conversion-plan"
    )
    assert (
        mcp_mod.tool_project_configure(runtime)["operation"]
        == "project-configuration-plan"
    )
    assert mcp_mod.tool_build(
        runtime, preset="arm-debug", authorized=False
    )["operation"] == "build"


def test_in_memory_convert_requires_plan_id_and_authorization(tmp_path: Path):
    """Regression: MCP convert is a two-phase plan/apply tool that fails closed."""
    runtime = _keil_runtime(tmp_path)
    server = create_server(
        runtime.project_root, tmp_path / "plugin-data", "session-a"
    )

    plan = asyncio.run(_call(server, "stm32_keil_convert", {"authorized": False}))
    assert plan["ok"] is True
    assert plan["operation"] == "keil-conversion-plan"
    plan_id = plan["data"]["plan_id"]
    assert len(plan_id) == 64

    without_auth = asyncio.run(
        _call(server, "stm32_keil_convert", {"planId": plan_id})
    )
    assert without_auth["ok"] is False
    assert without_auth["code"] == "AUTHORIZATION_REQUIRED"
    assert without_auth["operation"] == "keil-conversion-apply"

    stale = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {"planId": "0" * 64, "authorized": True},
        )
    )
    assert stale["ok"] is False
    assert stale["code"] == "PLAN_CHANGED"

    applied = asyncio.run(
        _call(
            server,
            "stm32_keil_convert",
            {"planId": plan_id, "authorized": True},
        )
    )
    assert applied["ok"] is True
    assert applied["operation"] == "keil-conversion-apply"
    assert (runtime.project_root / ".stm32-project.json").is_file()


def test_in_memory_configure_and_build_fail_closed(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    server = create_server(root, tmp_path / "plugin-data", "session-a")

    no_auth = asyncio.run(
        _call(server, "stm32_build", {"preset": "arm-debug"})
    )
    assert no_auth["ok"] is False
    assert no_auth["code"] == "AUTHORIZATION_REQUIRED"
    assert no_auth["operation"] == "build"
    assert not hit_file.exists() or hit_file.read_text(encoding="utf-8") == ""

    # The tool schema rejects an out-of-enum preset before adapter work.
    with pytest.raises(Exception):
        asyncio.run(
            _call(
                server,
                "stm32_build",
                {"preset": "arm-fast", "authorized": True},
            )
        )
    # The direct helper enforces the same workflow validation.
    bad_preset = mcp_mod.tool_build(
        ServerRuntime.create(root, tmp_path / "plugin-data", "session-a"),
        preset="arm-fast",
        authorized=True,
    )
    assert bad_preset["ok"] is False
    assert bad_preset["code"] == "WORKFLOW_INPUT_INVALID"
    assert bad_preset["details"] == {
        "field": "preset",
        "rule": "value",
        "allowed": "arm-debug|arm-release",
    }

    built = asyncio.run(
        _call(
            server,
            "stm32_build",
            {"preset": "arm-debug", "authorized": True},
        )
    )
    assert built["ok"] is True
    assert built["operation"] == "build"

    plan = asyncio.run(
        _call(server, "stm32_project_configure", {"authorized": False})
    )
    assert plan["ok"] is True
    assert plan["operation"] == "project-configuration-plan"


# ---------------------------------------------------------------------------
# roots guard for every new tool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "arguments", "operation"),
    [
        ("stm32_keil_inspect", {}, "keil-inspect"),
        ("stm32_keil_convert", {}, "keil-conversion-plan"),
        ("stm32_project_configure", {}, "project-configuration-plan"),
        ("stm32_build", {"preset": "arm-debug"}, "build"),
    ],
)
def test_every_new_tool_rejects_multiple_client_roots(
    tmp_path: Path, tool: str, arguments: dict, operation: str
):
    runtime = _keil_runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[runtime.project_root, other]])

    result = asyncio.run(WRAPPERS[tool](runtime, _context(session), **arguments))

    assert result["ok"] is False
    assert result["operation"] == operation
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_every_new_tool_rejects_a_mismatched_single_root(tmp_path: Path):
    runtime = _keil_runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()

    for tool in (
        "stm32_keil_inspect",
        "stm32_keil_convert",
        "stm32_project_configure",
        "stm32_build",
    ):
        session = _RootSession([[other]])
        result = asyncio.run(WRAPPERS[tool](runtime, _context(session), **BUILD_ARGUMENTS.get(tool, {})))
        assert result["ok"] is False
        assert result["code"] == "UNSUPPORTED_MULTIROOT"


def test_every_new_tool_handles_roots_unavailable(tmp_path: Path):
    runtime = _keil_runtime(tmp_path)

    for tool in (
        "stm32_keil_inspect",
        "stm32_keil_convert",
        "stm32_project_configure",
        "stm32_build",
    ):
        session = _RootSession([[]], error=RuntimeError("roots broken"))
        result = asyncio.run(WRAPPERS[tool](runtime, _context(session), **BUILD_ARGUMENTS.get(tool, {})))
        assert result["ok"] is False
        assert result["code"] == "MCP_ROOTS_UNAVAILABLE"


# ---------------------------------------------------------------------------
# stdio startup
# ---------------------------------------------------------------------------


def test_main_runs_the_extended_server_over_stdio(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    received: dict[str, object] = {}

    class FakeServer:
        def run(self, *, transport: str) -> None:
            received["transport"] = transport

    def fake_create_server(
        project_root: Path, data_root: Path, session_id: str | None
    ) -> FakeServer:
        received["project_root"] = project_root
        received["data_root"] = data_root
        received["session_id"] = session_id
        return FakeServer()

    monkeypatch.setattr("stm32_toolkit.mcp_server.create_server", fake_create_server)

    assert main([
        "--project-root", str(project),
        "--data-root", str(tmp_path / "plugin-data"),
        "--session-id", "session-a",
    ]) == 0

    assert received["transport"] == "stdio"


# ---------------------------------------------------------------------------
# end-to-end gate
# ---------------------------------------------------------------------------


def test_end_to_end_fixture_inspect_convert_configure_build(tmp_path: Path, monkeypatch):
    """Copy of the committed convertible fixture: inspect -> plan/apply ->
    configure -> build, entirely through public workflows without any
    fixture surgery or manual manifest edits."""
    root = convertible_fixture_copy(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)

    # inspect
    runtime = ServerRuntime.create(root, tmp_path / "plugin-data", "session-a")
    inspection = mcp_mod.tool_keil_inspect(runtime)
    assert inspection["ok"] is True
    assert inspection["operation"] == "keil-inspect"
    assert inspection["data"]["inspection"]["device"] == "STM32F429ZGTx"

    # conversion plan
    plan = convert_keil_workflow(root).to_dict()
    assert plan["ok"] is True
    assert plan["operation"] == "keil-conversion-plan"
    assert plan["data"]["blockers"] == []
    plan_id = plan["data"]["plan_id"]

    # conversion apply
    applied = convert_keil_workflow(root, plan_id=plan_id, authorized=True).to_dict()
    assert applied["ok"] is True
    assert applied["operation"] == "keil-conversion-apply"
    report_path = root / "artifacts" / "migration" / "conversion-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["planId"] == plan_id
    assert report["gitHead"]
    assert any(
        section["address"] == 0x20000000 for section in report["fixedSections"]
    )
    manifest_path = root / ".stm32-project.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == 2
    # The generated manifest is used exactly as produced: the debug spec
    # stays empty and build-only configuration must still succeed.
    assert manifest["debug"] == {}

    # configuration plan/apply with the untouched generated manifest
    configure_plan = configure_project_workflow(root).to_dict()
    assert configure_plan["ok"] is True
    assert configure_plan["operation"] == "project-configuration-plan"
    assert configure_plan["data"]["blockers"] == []
    configure_id = configure_plan["data"]["plan_id"]
    configured = configure_project_workflow(
        root, plan_id=configure_id, authorized=True
    ).to_dict()
    assert configured["ok"] is True
    assert configured["operation"] == "project-configuration-apply"
    generated = root / ".stm32-toolkit" / "generated-files.json"
    assert generated.is_file()
    generated_payload = json.loads(generated.read_text(encoding="utf-8"))
    assert generated_payload["toolVersion"] == "0.3.0"
    tasks = json.loads((root / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    assert [task["label"] for task in tasks["tasks"]] == [
        "STM32 Toolkit: Build Debug",
        "STM32 Toolkit: Build Release",
    ]
    for task in tasks["tasks"]:
        assert task["args"][:2] == ["build", "--preset"]
        assert task["args"][2] in ("arm-debug", "arm-release")
        assert "--project" in task["args"]
        assert "${workspaceFolder}" in task["args"]
    # Empty debug generates a deterministic launch config that claims no
    # usable hardware debugging: no cortex-debug configuration at all.
    launch = json.loads((root / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"] == []

    # fake build through the workflow
    built = build_firmware_workflow(root, preset="arm-debug", authorized=True).to_dict()
    assert built["ok"] is True
    assert built["operation"] == "build"
    assert built["data"]["identity"]["preset"] == "arm-debug"
    assert built["data"]["identity"]["gitHead"] == report["gitHead"]

    build_result = json.loads(
        (root / "artifacts" / "migration" / "build-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert build_result["status"] == "success"
    identity_doc = json.loads(
        (root / "build" / "arm-debug" / "firmware-identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert identity_doc["buildId"] == build_result["buildId"]
    assert identity_doc["gitHead"] == report["gitHead"]
    assert identity_doc["preset"] == "arm-debug"
    elf = (root / "build" / "arm-debug" / "legacy.elf").read_bytes()
    assert identity_doc["elfSha256"] == hashlib.sha256(elf).hexdigest()
    assert {entry["path"] for entry in build_result["artifacts"]} >= {
        "build/arm-debug/legacy.elf",
        "build/arm-debug/firmware-identity.json",
        "artifacts/migration/build-result.json",
    }
    assert hit_file.read_text(encoding="utf-8") != ""

    # context agrees: build ready, hardware capabilities still false
    context = build_project_context(
        root, tmp_path / "plugin-data", "session-a"
    ).to_dict()
    assert context["ok"] is True
    assert context["data"]["build"]["managedManifestValid"] is True
    assert context["data"]["build"]["managedFilesMissing"] == []
    assert context["data"]["build"]["managedFilesDrifted"] == []
    assert context["data"]["capabilities"]["build"] is True
    for key in ("flash", "hostTest", "targetTest", "monitor", "breakpointDebug"):
        assert context["data"]["capabilities"][key] is False
