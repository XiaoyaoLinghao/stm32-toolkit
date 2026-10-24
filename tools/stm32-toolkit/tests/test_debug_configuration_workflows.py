"""PY-OCD-DEBUG-CONFIG public-route tests: workflow, CLI, MCP, context, hardware.

Every project is an authored synthetic Schema v2/v3 tree below ``tmp_path``.
No PyOCD import, probe, network, hardware, original project or installed
runtime is touched.  Probe discovery uses an in-memory backend fake only.
These tests are the author's slice evidence; the primary conversation agent
runs them independently.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from collections.abc import Mapping
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.context import (
    _firmware_routes,
    _hardware_capability_details,
    build_project_context,
)
from stm32_toolkit.debug_configuration import describe_debug_configuration
from stm32_toolkit.hardware_workflows import (
    FlashWorkflowRequest,
    HardwareWorkflowSeams,
    ProbeListWorkflowRequest,
    _prepare,
    _WorkflowFailure,
    probe_list_workflow,
)
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.probe.backend import ProbeDescriptor
from stm32_toolkit.workflows import (
    configure_project_workflow,
    preflight_keil_workflow,
)

from test_debug_configuration import (
    PAIR,
    content_snapshot,
    no_debug_payload,
    schema3_payload,
    source_path,
)
from test_generation import write_project
from test_mcp_roots import _RootSession, _context
from test_migration_plan import build_repo

DEBUG_INVALID = "DEBUG_CONFIGURATION_INVALID"
HARDWARE_INVALID = "HARDWARE_INPUT_INVALID"


def _root(tmp_path: Path, payload: dict | None = None) -> Path:
    return write_project(
        tmp_path / "project",
        no_debug_payload() if payload is None else payload,
    )


def _flash_request(root: Path, data_root: Path) -> FlashWorkflowRequest:
    return FlashWorkflowRequest(
        project_root=root,
        data_root=data_root,
        session_id="session-a",
        probe_id="probe-a",
        expected_build_id="1" * 64,
        expected_elf_sha256="2" * 64,
        authorized=False,
    )


def _diagnostic_codes(details: object) -> list[str]:
    # OperationResult freezes nested mappings, so accept any Mapping.
    assert isinstance(details, Mapping)
    diagnostics = details["diagnostics"]
    assert isinstance(diagnostics, (list, tuple))
    return [str(entry["code"]) for entry in diagnostics]


# ---------------------------------------------------------------------------
# workflow PLAN/APPLY round trips
# ---------------------------------------------------------------------------


def test_workflow_paired_plan_and_apply_round_trip(tmp_path):
    root = _root(tmp_path)
    before = content_snapshot(root)

    plan = configure_project_workflow(
        root, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert plan.ok is True
    assert plan.operation == "project-configuration-plan"
    data = plan.data
    assert data["debug_configuration"] == {
        "backend": PAIR[0],
        "target": PAIR[1],
    }
    edit = data["manifest_edit"]
    assert edit["path"] == ".stm32-project.json"
    assert edit["status"] == "update"
    assert "before_bytes" not in edit and "after_bytes" not in edit
    assert set(edit) == {
        "path",
        "status",
        "before_sha256",
        "after_sha256",
        "before_size",
        "after_size",
        "unified_diff",
    }
    assert edit["before_sha256"] != edit["after_sha256"]
    assert '"backend": "pyocd"' in edit["unified_diff"]
    assert content_snapshot(root) == before

    applied = configure_project_workflow(
        root,
        plan_id=data["plan_id"],
        authorized=True,
        debug_backend=PAIR[0],
        debug_target=PAIR[1],
    )
    assert applied.ok is True
    assert applied.operation == "project-configuration-apply"
    applied_data = applied.data
    assert applied_data["manifestEditPath"] == ".stm32-project.json"
    assert applied_data["manifestEditStatus"] == "update"
    assert source_path(root).read_bytes() != before[".stm32-project.json"][2]
    assert json.loads(source_path(root).read_text("utf-8"))["debug"] == {
        "backend": PAIR[0],
        "target": PAIR[1],
    }

    # A repeat plan with the same pair is a byte-preserving no-op.
    again = configure_project_workflow(
        root, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert again.ok is True
    assert again.data["manifest_edit"]["status"] == "unchanged"
    assert again.data["manifest_edit"]["unified_diff"] == ""
    assert (
        again.data["manifest_edit"]["before_sha256"]
        == again.data["manifest_edit"]["after_sha256"]
    )


def test_workflow_pair_edit_preserves_schema3_svd_fields(tmp_path):
    payload = schema3_payload()
    root = _root(tmp_path, payload)
    model_before = json.loads(source_path(root).read_text("utf-8"))

    plan = configure_project_workflow(
        root, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert plan.ok is True
    after = json.loads(source_path(root).read_text("utf-8"))
    assert after == model_before  # PLAN writes nothing
    applied = configure_project_workflow(
        root,
        plan_id=plan.data["plan_id"],
        authorized=True,
        debug_backend=PAIR[0],
        debug_target=PAIR[1],
    )
    assert applied.ok is True
    written = json.loads(source_path(root).read_text("utf-8"))
    assert written["debug"]["backend"] == PAIR[0]
    assert written["debug"]["target"] == PAIR[1]
    assert written["debug"]["svd"] == model_before["debug"]["svd"]
    assert written["debug"]["svdDevice"] == model_before["debug"]["svdDevice"]
    assert (
        written["debug"]["readableRegions"]
        == model_before["debug"]["readableRegions"]
    )
    for key in ("schemaVersion", "logicalProjectId", "memory", "generation"):
        assert written[key] == model_before[key]


def test_workflow_no_option_route_keeps_the_historical_shape(tmp_path):
    root = _root(tmp_path)
    before = content_snapshot(root)

    plan = configure_project_workflow(root)
    explicit_none = configure_project_workflow(
        root, debug_backend=None, debug_target=None
    )
    assert plan.ok is True and explicit_none.ok is True
    data = plan.data
    assert "debug_configuration" not in data
    assert "manifest_edit" not in data
    assert data["plan_id"] == explicit_none.data["plan_id"]
    assert content_snapshot(root) == before

    applied = configure_project_workflow(
        root, plan_id=data["plan_id"], authorized=True
    )
    assert applied.ok is True
    assert applied.operation == "project-configuration-apply"
    assert json.loads(source_path(root).read_text("utf-8"))["debug"] == {}


@pytest.mark.parametrize(
    ("backend", "target", "codes", "missing", "field", "rule"),
    [
        (
            None,
            PAIR[1],
            ["DEBUG_BACKEND_MISSING"],
            ["debug.backend"],
            "debug.backend",
            "missing",
        ),
        (
            PAIR[0],
            None,
            ["DEBUG_TARGET_MISSING"],
            ["debug.target"],
            "debug.target",
            "missing",
        ),
        (
            None,
            None,
            ["DEBUG_BACKEND_MISSING", "DEBUG_TARGET_MISSING"],
            ["debug.backend", "debug.target"],
            "debug.backend",
            "missing",
        ),
        (
            "openocd",
            PAIR[1],
            ["DEBUG_BACKEND_UNSUPPORTED"],
            [],
            "debug.backend",
            "unsupported",
        ),
        (
            PAIR[0],
            " stm32f407vg",
            ["DEBUG_TARGET_MALFORMED"],
            [],
            "debug.target",
            "pattern",
        ),
        (PAIR[0], 7, ["DEBUG_TARGET_MALFORMED"], [], "debug.target", "type"),
        (7, PAIR[1], ["DEBUG_BACKEND_UNSUPPORTED"], [], "debug.backend", "type"),
        (
            PAIR[0],
            "",
            ["DEBUG_TARGET_MALFORMED"],
            [],
            "debug.target",
            "empty",
        ),
    ],
)
def test_workflow_invalid_pair_returns_complete_diagnostics_without_writes(
    tmp_path, backend, target, codes, missing, field, rule
):
    root = _root(tmp_path)
    before = content_snapshot(root)

    result = configure_project_workflow(
        root, debug_backend=backend, debug_target=target
    )

    assert result.ok is False
    assert result.code == DEBUG_INVALID
    details = result.details
    assert _diagnostic_codes(details) == codes
    assert list(details["missingFields"]) == missing
    assert details["field"] == field
    assert details["rule"] == rule
    for entry in details["diagnostics"]:
        assert set(entry) == {"code", "field", "rule", "message", "remediation"}
        assert "stm32-toolkit project configure" in entry["remediation"]
        assert "stm32_project_configure" in entry["remediation"]
    assert content_snapshot(root) == before


def test_workflow_apply_refuses_changed_omitted_or_invalid_pair_without_writes(
    tmp_path,
):
    root = _root(tmp_path)
    plan = configure_project_workflow(
        root, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    plan_id = plan.data["plan_id"]
    before = content_snapshot(root)

    changed = configure_project_workflow(
        root,
        plan_id=plan_id,
        authorized=True,
        debug_backend=PAIR[0],
        debug_target="stm32f411xe",
    )
    assert changed.ok is False and changed.code == "PLAN_CHANGED"

    omitted = configure_project_workflow(
        root, plan_id=plan_id, authorized=True
    )
    assert omitted.ok is False and omitted.code == "PLAN_CHANGED"

    # An invalid pair is reported by the shared validator before any stale
    # comparison and still writes nothing.
    invalid = configure_project_workflow(
        root,
        plan_id="0" * 64,
        authorized=True,
        debug_backend="openocd",
        debug_target=PAIR[1],
    )
    assert invalid.ok is False and invalid.code == DEBUG_INVALID
    assert _diagnostic_codes(invalid.details) == ["DEBUG_BACKEND_UNSUPPORTED"]
    assert content_snapshot(root) == before


def test_workflow_paired_apply_requires_exact_boolean_authorization(tmp_path):
    root = _root(tmp_path)
    sequence_id = configure_project_workflow(
        root, debug_backend=PAIR[0], debug_target=PAIR[1]
    ).data["plan_id"]
    before = content_snapshot(root)

    for authorized in (False, "true", 1, 0, None, [], {}):
        result = configure_project_workflow(
            root,
            plan_id=sequence_id,
            authorized=authorized,
            debug_backend=PAIR[0],
            debug_target=PAIR[1],
        )
        assert result.ok is False
        assert result.code == "AUTHORIZATION_REQUIRED"
        assert result.operation == "project-configuration-apply"

    missing = configure_project_workflow(
        root,
        authorized=True,
        debug_backend=PAIR[0],
        debug_target=PAIR[1],
    )
    assert missing.ok is False and missing.code == "AUTHORIZATION_REQUIRED"
    assert dict(missing.details) == {"field": "planId", "rule": "required"}
    assert content_snapshot(root) == before


# ---------------------------------------------------------------------------
# CLI PLAN/APPLY and emitted remediation
# ---------------------------------------------------------------------------


def test_cli_paired_plan_and_apply_round_trip(tmp_path, capsys):
    root = _root(tmp_path)
    before = content_snapshot(root)

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--dry-run",
                "--json",
                "--debug-backend",
                PAIR[0],
                "--debug-target",
                PAIR[1],
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["operation"] == "project-configuration-plan"
    assert payload["data"]["debug_configuration"] == {
        "backend": PAIR[0],
        "target": PAIR[1],
    }
    assert payload["data"]["manifest_edit"]["status"] == "update"
    plan_id = payload["data"]["plan_id"]
    assert content_snapshot(root) == before

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--apply",
                "--json",
                "--debug-backend",
                PAIR[0],
                "--debug-target",
                PAIR[1],
                "--plan-id",
                plan_id,
                "--authorized",
            ]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True
    assert applied["operation"] == "project-configuration-apply"
    assert applied["data"]["manifestEditStatus"] == "update"
    assert json.loads(source_path(root).read_text("utf-8"))["debug"] == {
        "backend": PAIR[0],
        "target": PAIR[1],
    }


def test_cli_invalid_pair_returns_structured_failure_without_writes(
    tmp_path, capsys
):
    root = _root(tmp_path)
    before = content_snapshot(root)

    assert (
        cli_main(
            [
                "project",
                "configure",
                "--project",
                str(root),
                "--dry-run",
                "--json",
                "--debug-backend",
                "openocd",
                "--debug-target",
                PAIR[1],
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == DEBUG_INVALID
    assert _diagnostic_codes(payload["details"]) == ["DEBUG_BACKEND_UNSUPPORTED"]
    assert content_snapshot(root) == before


def test_emitted_remediation_plan_command_runs_read_only(tmp_path, capsys):
    """Run the exact prompt string Toolkit emits, not a hardcoded copy."""
    root = _root(tmp_path)
    before = content_snapshot(root)

    status = describe_debug_configuration(None, None)
    remediation = status.diagnostics[0].remediation
    start = remediation.index("`stm32-toolkit project configure")
    end = remediation.index("`", start + 1)
    argv = shlex.split(remediation[start + 1 : end])
    assert argv[0] == "stm32-toolkit"
    argv = [
        value.replace("<project>", str(root)).replace(
            "<pyocd-target>", PAIR[1]
        )
        for value in argv
    ]
    assert all("<" not in value for value in argv)
    assert "--dry-run" in argv and "--json" in argv

    assert cli_main(argv[1:]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["operation"] == "project-configuration-plan"
    assert payload["data"]["debug_configuration"] == {
        "backend": PAIR[0],
        "target": PAIR[1],
    }
    assert content_snapshot(root) == before

    # The emitted APPLY prompt is complete too.
    assert (
        "--apply --json --plan-id <data.plan_id> --authorized"
        in status.next_steps[0]
    )
    assert "stm32_configure_project" not in status.next_steps[0]
    assert "stm32-toolkit configure " not in status.next_steps[0]


def test_guidance_documents_use_the_same_runnable_pair_commands():
    repo = Path(__file__).resolve().parents[3]
    user_guide = repo / "docs" / "user-guide.md"
    documents = (
        user_guide,
        repo / "skills" / "configure-stm32-project" / "SKILL.md",
        repo / "skills" / "migrate-keil" / "SKILL.md",
    )
    command_tokens = (
        "stm32-toolkit project configure",
        "--debug-backend pyocd",
        "--debug-target",
        "--dry-run --json",
        "--apply --json",
        "--plan-id",
        "--authorized",
        "stm32_project_configure",
        "debugBackend",
        "debugTarget",
        "diagnostics",
        "manifest_edit",
        "readableRegions",
    )
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for token in command_tokens:
            assert token in text, f"{document.name} lacks {token!r}"
        assert "stm32_configure_project" not in text
        assert "stm32-toolkit configure " not in text
    guide = user_guide.read_text(encoding="utf-8")
    for token in ("targetSupport", "hardwareVerified", "not-checked"):
        assert token in guide


# ---------------------------------------------------------------------------
# MCP wrappers, registered raw values, and roots boundary
# ---------------------------------------------------------------------------


def test_mcp_wrapper_paired_plan_and_apply_round_trip(tmp_path):
    root = _root(tmp_path)
    before = content_snapshot(root)
    runtime = ServerRuntime.create(root, tmp_path / "data", "session-a")

    assert "debug_configuration" not in mcp_mod.tool_project_configure(runtime)[
        "data"
    ]
    plan = mcp_mod.tool_project_configure_for_request
    planned = asyncio.run(
        plan(
            runtime,
            None,
            debug_backend=PAIR[0],
            debug_target=PAIR[1],
        )
    )
    assert planned["ok"] is True
    assert planned["operation"] == "project-configuration-plan"
    assert planned["data"]["manifest_edit"]["status"] == "update"
    assert content_snapshot(root) == before

    applied = mcp_mod.tool_project_configure(
        runtime,
        planned["data"]["plan_id"],
        True,
        PAIR[0],
        PAIR[1],
    )
    assert applied["ok"] is True
    assert applied["operation"] == "project-configuration-apply"
    assert applied["data"]["manifestEditStatus"] == "update"


def test_registered_mcp_handler_preserves_raw_values_without_coercion(tmp_path):
    root = _root(tmp_path)
    before = content_snapshot(root)
    server = create_server(root, tmp_path / "data", "session-a")

    async def call(arguments: dict[str, object]) -> dict[str, object]:
        _content, structured = await server.call_tool(
            "stm32_project_configure", arguments
        )
        return structured

    # Non-string scalars, containers and booleans must reach the shared
    # validator unchanged and be refused, never stringified or truncated.
    for raw in (7, True, ["pyocd"], {"backend": "pyocd"}, 0, 1.5):
        result = asyncio.run(
            call({"debugBackend": raw, "debugTarget": raw, "authorized": False})
        )
        assert result["ok"] is False
        assert result["code"] == DEBUG_INVALID
        assert _diagnostic_codes(result["details"]) == [
            "DEBUG_BACKEND_UNSUPPORTED",
            "DEBUG_TARGET_MALFORMED",
        ]

    partial = asyncio.run(
        call({"debugBackend": PAIR[0], "authorized": False})
    )
    assert partial["code"] == DEBUG_INVALID
    assert _diagnostic_codes(partial["details"]) == ["DEBUG_TARGET_MISSING"]

    empty = asyncio.run(
        call({"debugBackend": "", "debugTarget": " ", "authorized": False})
    )
    assert empty["code"] == DEBUG_INVALID
    assert _diagnostic_codes(empty["details"]) == [
        "DEBUG_BACKEND_UNSUPPORTED",
        "DEBUG_TARGET_MALFORMED",
    ]
    assert content_snapshot(root) == before

    planned = asyncio.run(
        call({"debugBackend": PAIR[0], "debugTarget": PAIR[1]})
    )
    assert planned["ok"] is True
    applied = asyncio.run(
        call(
            {
                "debugBackend": PAIR[0],
                "debugTarget": PAIR[1],
                "planId": planned["data"]["plan_id"],
                "authorized": True,
            }
        )
    )
    assert applied["ok"] is True
    assert applied["operation"] == "project-configuration-apply"


def test_mcp_pair_request_keeps_the_client_roots_boundary(tmp_path):
    root = _root(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    runtime = ServerRuntime.create(root, tmp_path / "data", "session-a")
    session = _RootSession([[root, other]])

    result = asyncio.run(
        mcp_mod.tool_project_configure_for_request(
            runtime,
            _context(session),
            debug_backend=PAIR[0],
            debug_target=PAIR[1],
        )
    )

    assert result["ok"] is False
    assert result["operation"] == "project-configuration-plan"
    assert result["code"] == "UNSUPPORTED_MULTIROOT"


def test_registered_mcp_schema_keeps_debug_values_unconstrained(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    server = create_server(project, tmp_path / "data", "session-a")
    schemas = {
        tool.name: tool.inputSchema
        for tool in asyncio.run(server.list_tools())
    }
    configure = schemas["stm32_project_configure"]
    assert set(configure["properties"]) == {
        "planId",
        "authorized",
        "debugBackend",
        "debugTarget",
    }
    for field in ("debugBackend", "debugTarget"):
        entry = configure["properties"][field]
        assert entry.get("type") != "string"
        assert "enum" not in entry and "const" not in entry


# ---------------------------------------------------------------------------
# configured project context
# ---------------------------------------------------------------------------


def test_context_absent_debug_blocks_hardware_but_keeps_build_and_configure(
    tmp_path,
):
    root = _root(tmp_path)
    plan = configure_project_workflow(root).data
    assert (
        configure_project_workflow(
            root, plan_id=plan["plan_id"], authorized=True
        ).ok
        is True
    )

    result = build_project_context(root, tmp_path / "data")
    assert result.ok is True
    data = result.data
    debug = data["debugConfiguration"]
    assert debug["status"] == "needs-user-input"
    assert debug["backend"] is None and debug["target"] is None
    assert debug["missingFields"] == ["debug.backend", "debug.target"]
    assert _diagnostic_codes(debug) == [
        "DEBUG_BACKEND_MISSING",
        "DEBUG_TARGET_MISSING",
    ]
    assert debug["targetSupport"] == "not-checked"
    assert debug["hardwareVerified"] is False
    assert debug["nextSteps"]
    for name in ("flash", "targetTest", "monitor", "breakpointDebug"):
        detail = data["capabilityDetails"][name]
        assert detail["status"] == "blocked"
        assert "debug.backend (missing)" in detail["reason"]
        assert "debug.target (missing)" in detail["reason"]
        assert "stm32-toolkit project configure" in " ".join(
            detail["nextSteps"]
        )
        assert data["capabilities"][name] is False
    assert data["capabilityDetails"]["build"]["status"] == "available"
    assert data["capabilityDetails"]["configure"]["status"] == "available"
    routes = data["firmwareRoutes"]
    assert routes["imported"]["status"] == "not-evaluated"


def test_context_configured_pair_is_metadata_only(tmp_path):
    root = _root(tmp_path, schema3_payload())

    result = build_project_context(root, tmp_path / "data")
    assert result.ok is True
    data = result.data
    debug = data["debugConfiguration"]
    assert debug["status"] == "configured"
    assert debug["backend"] is None and debug["target"] is None
    # schema3_payload has an SVD but no explicit pair; the read-only status
    # must report the missing pair without inventing one.
    assert debug["missingFields"] == ["debug.backend", "debug.target"]

    configured_root = write_project(
        tmp_path / "configured", no_debug_payload(debug={"backend": "pyocd", "target": PAIR[1]})
    )
    configured = build_project_context(configured_root, tmp_path / "data-2")
    assert configured.ok is True
    configured_debug = configured.data["debugConfiguration"]
    assert configured_debug["status"] == "configured"
    assert configured_debug["backend"] == PAIR[0]
    assert configured_debug["target"] == PAIR[1]
    assert configured_debug["missingFields"] == []
    assert configured_debug["diagnostics"] == []
    assert configured_debug["targetSupport"] == "not-checked"
    assert configured_debug["hardwareVerified"] is False
    for name in ("flash", "targetTest", "monitor", "breakpointDebug"):
        assert configured.data["capabilityDetails"][name]["status"] == (
            "not-evaluated"
        )
        assert configured.data["capabilities"][name] is False


def test_context_invalid_pair_reports_all_reasons(tmp_path):
    payload = no_debug_payload(debug={"backend": "openocd", "target": 7})
    root = _root(tmp_path, payload)

    result = build_project_context(root, tmp_path / "data")
    assert result.ok is True
    debug = result.data["debugConfiguration"]
    assert debug["status"] == "needs-user-input"
    assert _diagnostic_codes(debug) == [
        "DEBUG_BACKEND_UNSUPPORTED",
        "DEBUG_TARGET_MALFORMED",
    ]
    detail = result.data["capabilityDetails"]["flash"]
    assert detail["status"] == "blocked"
    assert "debug.backend (unsupported)" in detail["reason"]
    assert "debug.target (type)" in detail["reason"]


def test_context_snapshot_reason_is_retained_with_the_debug_block():
    status = describe_debug_configuration(None, None)

    details = _hardware_capability_details(
        snapshot_fresh=True, debug_status=status
    )

    flash = details["flash"]
    assert flash["status"] == "blocked"
    for text in (
        "FIRMWARE_PROVENANCE_UNSUPPORTED",
        "debug.backend (missing)",
        "debug.target (missing)",
    ):
        assert text in flash["reason"]
    joined = " ".join(flash["nextSteps"])
    assert "restore a Git repository" in joined
    assert "stm32-toolkit project configure" in joined
    for name in ("targetTest", "monitor", "breakpointDebug"):
        assert "FIRMWARE_PROVENANCE_UNSUPPORTED" in details[name]["reason"]
        assert "debug.backend (missing)" in details[name]["reason"]
    routes = _firmware_routes(flash)
    assert routes["imported"]["status"] == "not-evaluated"


def test_unconfigured_context_has_no_debug_configuration(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    result = build_project_context(empty, tmp_path / "data")
    assert result.ok is True
    assert "debugConfiguration" not in result.data
    hardware = result.data["capabilityDetails"]["flash"]
    assert hardware["status"] == "not-evaluated"


# ---------------------------------------------------------------------------
# Keil preflight: non-blocking post-migration description
# ---------------------------------------------------------------------------


def test_preflight_debug_configuration_is_nonblocking_post_migration(tmp_path):
    root = build_repo(tmp_path, commit=False)

    result = preflight_keil_workflow(root)

    assert result.ok is True
    data = result.data
    debug = data["debugConfiguration"]
    assert debug["phase"] == "post-migration"
    assert debug["blocking"] is False
    assert debug["status"] == "needs-user-input"
    assert debug["backend"] is None and debug["target"] is None
    assert debug["missingFields"] == ["debug.backend", "debug.target"]
    assert _diagnostic_codes(debug) == [
        "DEBUG_BACKEND_MISSING",
        "DEBUG_TARGET_MISSING",
    ]
    assert debug["targetSupport"] == "not-checked"
    assert debug["hardwareVerified"] is False
    joined = " ".join(debug["nextSteps"])
    assert (
        "stm32-toolkit project configure --project <project> "
        "--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json"
    ) in joined
    assert "stm32_project_configure" in joined
    # The description adds no technical blocker, prerequisite or plan ID.
    assert all(
        not str(blocker.get("code", "")).startswith("DEBUG")
        for blocker in data["analysis"]["blockers"]
    )
    readiness = json.dumps(result.to_dict()["data"]["planReadiness"])
    assert "debugConfiguration" not in readiness
    assert "stm32-toolkit project configure" not in readiness
    assert data["planReadiness"]["planId"] is None
    assert data["applyReadiness"]["ready"] is False


# ---------------------------------------------------------------------------
# hardware workflow diagnostics (offline; no backend is constructed)
# ---------------------------------------------------------------------------


def test_hardware_missing_both_reports_full_diagnostics_and_old_first_rule(
    tmp_path,
):
    root = _root(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    request = _flash_request(root, data_root)

    with pytest.raises(_WorkflowFailure) as info:
        _prepare(
            request,
            FlashWorkflowRequest,
            require_probe=True,
            require_pins=True,
        )

    error = info.value
    assert error.code == HARDWARE_INVALID
    details = error.details
    assert details["field"] == "debug.backend"
    assert details["rule"] == "pyocdRequired"
    assert list(details["missingFields"]) == ["debug.backend", "debug.target"]
    assert _diagnostic_codes(details) == [
        "DEBUG_BACKEND_MISSING",
        "DEBUG_TARGET_MISSING",
    ]
    guidance = details["guidance"]
    assert (
        "stm32-toolkit project configure --project <project> "
        "--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json"
    ) in guidance
    assert "stm32_project_configure" in guidance


def test_hardware_malformed_target_reports_complete_diagnostics(tmp_path):
    root = _root(tmp_path, no_debug_payload(debug={"backend": "pyocd", "target": 7}))
    data_root = tmp_path / "data"
    data_root.mkdir()
    request = _flash_request(root, data_root)

    with pytest.raises(_WorkflowFailure) as info:
        _prepare(
            request,
            FlashWorkflowRequest,
            require_probe=True,
            require_pins=True,
        )

    error = info.value
    assert error.code == HARDWARE_INVALID
    assert error.details["field"] == "debug.target"
    assert error.details["rule"] == "identifierRequired"
    assert list(error.details["missingFields"]) == []
    assert _diagnostic_codes(error.details) == ["DEBUG_TARGET_MALFORMED"]
    assert "debug.target" in error.details["guidance"]


def test_hardware_svd_gate_stays_separate_from_the_debug_pair(tmp_path):
    root = _root(
        tmp_path,
        no_debug_payload(debug={"backend": "pyocd", "target": PAIR[1]}),
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    request = _flash_request(root, data_root)

    with pytest.raises(_WorkflowFailure) as info:
        _prepare(
            request,
            FlashWorkflowRequest,
            require_probe=True,
            require_pins=True,
            require_svd=True,
        )

    error = info.value
    assert error.code == "SVD_SELECTION_REQUIRED"
    assert error.details["field"] == "debug.svd"
    assert error.details["rule"] == "required"


# ---------------------------------------------------------------------------
# independent probe discovery (in-memory backend only)
# ---------------------------------------------------------------------------


def test_probe_discovery_is_independent_of_the_debug_configuration(tmp_path):
    root = _root(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    events: list[str] = []

    class _DiscoveryBackend:
        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            events.append("backend.list")
            return (ProbeDescriptor("probe-a", "Arm", "CMSIS-DAP", None),)

        def close(self) -> None:
            events.append("backend.close")

    seams = HardwareWorkflowSeams(
        _test_backend_factory=lambda: _DiscoveryBackend()
    )
    request = ProbeListWorkflowRequest(root, data_root, "session-a")

    result = asyncio.run(probe_list_workflow(request, _seams=seams))

    assert result.ok is True
    assert events == ["backend.list", "backend.close"]
    data = result.data
    assert data["probes"][0]["probeId"] == "probe-a"
    assert data["discovery"]["status"] == "project-bound"
    # Discovery did not require or invent a debug pair.
    assert json.loads(source_path(root).read_text("utf-8"))["debug"] == {}
