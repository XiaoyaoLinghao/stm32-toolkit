from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import stm32_toolkit.mcp_server as mcp_mod
import stm32_toolkit.testing_workflows as workflows
from stm32_toolkit import cli
from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import (
    TestRunManifest as _TestRunManifest,
    calculate_inventory_digest,
)
from stm32_toolkit.testing.protocol import calculate_case_inventory_digest
from stm32_toolkit.testing.target import TargetTestRunner
from test_physical_target_workflows import (
    CASES,
    RAW_PROBE,
    _Board,
    _SourceChangeBackend,
    _fixed_identity,
    _fixed_project,
    _fixed_v2_stream,
)


PROTOCOL = "stm32-target-frame/2"
SESSION_ID = "vs10a-public"
PROBE_ID = RAW_PROBE


def _context_args(project: Path, data_root: Path) -> list[str]:
    return [
        "--project",
        str(project),
        "--data-root",
        str(data_root),
        "--session-id",
        SESSION_ID,
        "--json",
    ]


def _prepare_argv(project: Path, data_root: Path) -> list[str]:
    argv = [
        "test",
        "target",
        "prepare",
        "--probe-id",
        PROBE_ID,
    ]
    for case_id in CASES:
        argv.extend(["--case-id", case_id])
    return [*argv, *_context_args(project, data_root)]


def _execute_argv(
    project: Path, data_root: Path, action_digest: str
) -> list[str]:
    return [
        "test",
        "target",
        "execute",
        "--probe-id",
        PROBE_ID,
        "--authorized-action-digest",
        action_digest,
        *_context_args(project, data_root),
    ]


@dataclass
class _PublicPhysicalSession:
    project: Path
    data_root: Path
    build: Mapping[str, object]
    workspace: WorkspacePaths
    identity: EvidenceIdentity
    inventory_digest: str
    case_inventory_digest: str
    flash_segment: bytes
    board: _Board
    events: list[tuple[object, ...]]

    def backend_factory(self) -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=self.board,
            physical_identity={
                "board_id": str(self.build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(self.build["targetDevice"]),
                "probe_serial_hash": sha256(PROBE_ID.encode("utf-8")).hexdigest(),
            },
            stream=_fixed_v2_stream(),
            flash_segment=self.flash_segment,
            events=self.events,
        )


def _make_physical_session(tmp_path: Path) -> _PublicPhysicalSession:
    project_root = tmp_path / "project"
    project_root.mkdir()
    project, build = _fixed_project(project_root, protocol=PROTOCOL)
    data_root = tmp_path / "data"
    workspace = WorkspacePaths.from_roots(
        data_root,
        project,
        build["logicalProjectId"],
        SESSION_ID,
    )
    identity = _fixed_identity(build, workspace)
    return _PublicPhysicalSession(
        project=project,
        data_root=data_root,
        build=build,
        workspace=workspace,
        identity=identity,
        inventory_digest=calculate_inventory_digest(
            "target", identity, CASES
        ),
        case_inventory_digest=calculate_case_inventory_digest(CASES),
        flash_segment=(
            project / "build" / "arm-debug" / "firmware.elf"
        ).read_bytes()[84:404],
        board=_Board(),
        events=[],
    )


def _install_public_physical_seam(
    monkeypatch: pytest.MonkeyPatch,
    session: _PublicPhysicalSession,
) -> None:
    real_supervisor = workflows._target_supervisor

    def target_supervisor(
        context: workflows.TestingWorkflowContext,
        state: object,
        *,
        probe_id: str,
        level: object,
        support: Mapping[str, object],
        seams: workflows.TargetWorkflowSeams,
    ) -> object:
        assert seams._test_backend_factory is None
        return real_supervisor(
            context,
            state,
            probe_id=probe_id,
            level=level,
            support=support,
            seams=workflows.TargetWorkflowSeams(
                _test_backend_factory=session.backend_factory
            ),
        )

    monkeypatch.setattr(workflows, "_target_supervisor", target_supervisor)

    real_publish = workflows.TestRunPublisher.publish_target_physical

    def record_publish(
        publisher: workflows.TestRunPublisher,
        manifest: object,
        run_envelope: object,
    ) -> object:
        session.events.append(("publish",))
        return real_publish(publisher, manifest, run_envelope)

    monkeypatch.setattr(
        workflows.TestRunPublisher,
        "publish_target_physical",
        record_publish,
    )


def _cli_result(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    assert cli.main(argv) == 0
    return json.loads(capsys.readouterr().out)


async def _mcp_call(
    project: Path,
    data_root: Path,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    server = create_server(project, data_root, SESSION_ID)
    _content, result = await server.call_tool(tool_name, arguments)
    return result


def _run_cli(
    session: _PublicPhysicalSession,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict[str, object], dict[str, object], tuple[object, ...]]:
    prepared = _cli_result(
        _prepare_argv(session.project, session.data_root),
        capsys,
    )
    assert prepared["ok"] is True
    assert prepared["operation"] == "test.target.prepare"
    action_digest = str(prepared["data"]["authorized_action_digest"])
    executed = _cli_result(
        _execute_argv(session.project, session.data_root, action_digest),
        capsys,
    )
    assert executed["ok"] is True
    return prepared, executed, tuple(session.events)


def _run_mcp(
    session: _PublicPhysicalSession,
) -> tuple[dict[str, object], dict[str, object], tuple[object, ...]]:
    prepared = asyncio.run(
        _mcp_call(
            session.project,
            session.data_root,
            MCP_TOOL_NAMES["test_target_prepare"],
            {"probeId": PROBE_ID, "caseIds": list(CASES)},
        )
    )
    assert prepared["ok"] is True
    action_digest = str(prepared["data"]["authorized_action_digest"])
    executed = asyncio.run(
        _mcp_call(
            session.project,
            session.data_root,
            MCP_TOOL_NAMES["test_target_execute"],
            {
                "probeId": PROBE_ID,
                "authorizedActionDigest": action_digest,
            },
        )
    )
    assert executed["ok"] is True
    return prepared, executed, tuple(session.events)


def _reset_session(session: _PublicPhysicalSession) -> None:
    session.board = _Board()
    session.events.clear()


def _prepared_record(
    session: _PublicPhysicalSession,
    action_digest: str,
) -> Mapping[str, object]:
    runner = TargetTestRunner(
        session.workspace.session_root / "target-authorizations",
        object(),
        object(),
        lambda _name: object(),
        owns_probe=False,
    )
    return runner.load_prepared(action_digest).binding


def _manifest_from_result(
    session: _PublicPhysicalSession,
    result: Mapping[str, object],
) -> TestRunManifest:
    artifact = result["data"]["test_manifest"]
    artifact_path = session.workspace.workspace_root / "evidence" / str(
        artifact["relative_path"]
    )
    manifest = _TestRunManifest.from_dict(
        json.loads(artifact_path.read_text(encoding="utf-8"))
    )
    assert manifest.raw_events is not None
    return manifest


def _assert_public_semantics(
    session: _PublicPhysicalSession,
    prepared: Mapping[str, object],
    executed: Mapping[str, object],
) -> None:
    assert prepared["operation"] == "test.target.prepare"
    assert prepared["code"] == "OK"
    assert executed["operation"] == "test.target.execute"
    assert executed["code"] == "OK"

    prepare_data = prepared["data"]
    assert prepare_data["protocol"] == PROTOCOL
    assert prepare_data["case_ids"] == list(CASES)
    assert prepare_data["case_inventory_digest"] == session.case_inventory_digest
    assert prepare_data["inventory_digest"] == session.inventory_digest
    assert prepare_data["probe_serial_hash"] == sha256(
        PROBE_ID.encode("utf-8")
    ).hexdigest()
    action_digest = str(prepare_data["authorized_action_digest"])
    assert len(action_digest) == 64
    assert all(character in "0123456789abcdef" for character in action_digest)

    binding = _prepared_record(session, action_digest)
    assert binding["protocol"] == PROTOCOL
    assert binding["case_inventory_digest"] == session.case_inventory_digest
    assert binding["inventory_digest"] == session.inventory_digest
    assert binding["workspace_id"] == session.identity.workspace_id
    assert binding["project_id"] == session.identity.project_id
    assert binding["session_id"] == session.identity.session_id
    assert binding["revision"] == session.identity.git_commit
    assert binding["elf_sha256"] == session.identity.elf_sha256
    assert binding["build_id"] == session.identity.build_id
    assert binding["target"]["target_id"] == session.identity.target_device

    execute_data = executed["data"]
    assert execute_data["execution_source"] == "physical"
    assert execute_data["physical_transport_evidence"] is True
    assert execute_data["origin_workspace_id"] == session.identity.workspace_id
    assert execute_data["import_workspace_id"] == session.identity.workspace_id
    assert execute_data["run"]["state"] == "passed"

    manifest = _manifest_from_result(session, executed)
    assert manifest.identity == session.identity
    assert manifest.mode == "target"
    assert manifest.cases
    assert tuple(case.case_id for case in manifest.cases) == CASES
    raw_path = (
        session.workspace.workspace_root
        / "evidence"
        / manifest.raw_events.relative_path
    )
    assert raw_path.is_file()
    assert sha256(raw_path.read_bytes()).hexdigest() == manifest.raw_events.sha256


def _assert_physical_order(events: tuple[object, ...]) -> tuple[str, ...]:
    flash = next(index for index, event in enumerate(events) if event[:2] == ("flash", "modify"))
    readback = next(
        index
        for index, event in enumerate(events)
        if event[:2] == ("flash.readback", "modify")
    )
    postflash_identity = next(
        index
        for index, event in enumerate(events)
        if index > flash and event == ("identity", "modify")
    )
    transport_open = next(
        index for index, event in enumerate(events) if event[0] == "transport.open"
    )
    transport_identity = next(
        index
        for index, event in enumerate(events)
        if event[:2] == ("transport.identity", "modify")
    )
    transport_read = next(
        index for index, event in enumerate(events) if event[0] == "transport.read"
    )
    publish = next(
        index for index, event in enumerate(events) if event == ("publish",)
    )
    assert flash < readback < postflash_identity < transport_open
    assert transport_open < transport_identity < transport_read < publish
    return tuple(str(event[0]) for event in events)


def test_cli_and_registered_mcp_tools_run_real_v2_target_workflows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _make_physical_session(tmp_path)
    _install_public_physical_seam(monkeypatch, session)

    cli_prepared, cli_executed, cli_events = _run_cli(session, capsys)
    _assert_public_semantics(session, cli_prepared, cli_executed)
    cli_event_names = _assert_physical_order(cli_events)

    _reset_session(session)
    mcp_prepared, mcp_executed, mcp_events = _run_mcp(session)
    _assert_public_semantics(session, mcp_prepared, mcp_executed)
    mcp_event_names = _assert_physical_order(mcp_events)

    assert cli_prepared["operation"] == mcp_prepared["operation"]
    assert cli_prepared["code"] == mcp_prepared["code"] == "OK"
    assert set(cli_prepared["data"]) == set(mcp_prepared["data"])
    assert cli_prepared["data"]["protocol"] == mcp_prepared["data"]["protocol"] == PROTOCOL
    assert cli_prepared["data"]["case_inventory_digest"] == mcp_prepared["data"]["case_inventory_digest"]
    assert cli_prepared["data"]["inventory_digest"] == mcp_prepared["data"]["inventory_digest"]
    assert cli_executed["operation"] == mcp_executed["operation"]
    assert cli_executed["code"] == mcp_executed["code"] == "OK"
    assert set(cli_executed["data"]) == set(mcp_executed["data"])
    assert cli_executed["data"]["run"]["state"] == mcp_executed["data"]["run"]["state"] == "passed"
    assert cli_executed["data"]["execution_source"] == mcp_executed["data"]["execution_source"] == "physical"
    assert cli_executed["data"]["physical_transport_evidence"] is True
    assert mcp_executed["data"]["physical_transport_evidence"] is True
    assert cli_event_names == mcp_event_names


def test_mcp_inventory_is_exactly_the_frozen_48_names(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    tools = asyncio.run(
        create_server(project, tmp_path / "data", SESSION_ID).list_tools()
    )

    names = {tool.name for tool in tools}
    assert len(names) == 48
    assert names == set(MCP_TOOL_NAMES.values())
    assert len(MCP_TOOL_NAMES) == 48


def test_cli_target_entry_point_rejects_identity_elf_target_and_address_injection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[object] = []

    async def forbidden(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return OperationResult.success("unexpected", {})

    monkeypatch.setattr(cli, "target_test_prepare", forbidden)
    monkeypatch.setattr(cli, "target_test_execute", forbidden)

    prepare_base = _prepare_argv(project, tmp_path / "data")
    execute_base = _execute_argv(project, tmp_path / "data", "a" * 64)
    for base in (prepare_base, execute_base):
        for option in ("--identity", "--elf", "--target", "--address"):
            assert cli.main([*base, option, "caller-controlled"]) == 2
            captured = capsys.readouterr()
            assert captured.out == ""
            assert calls == []


def test_mcp_target_tools_close_schema_and_reject_forbidden_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    server = create_server(project, data_root, SESSION_ID)
    tools = asyncio.run(server.list_tools())
    schemas = {tool.name: tool.inputSchema for tool in tools}

    prepare_name = MCP_TOOL_NAMES["test_target_prepare"]
    execute_name = MCP_TOOL_NAMES["test_target_execute"]
    assert schemas[prepare_name]["additionalProperties"] is False
    assert schemas[execute_name]["additionalProperties"] is False
    assert set(schemas[prepare_name]["properties"]) == {"probeId", "caseIds"}
    assert set(schemas[execute_name]["properties"]) == {
        "probeId",
        "authorizedActionDigest",
    }

    calls: list[object] = []

    async def forbidden(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return OperationResult.success("unexpected", {})

    monkeypatch.setattr(mcp_mod, "target_test_prepare", forbidden)
    monkeypatch.setattr(mcp_mod, "target_test_execute", forbidden)

    with pytest.raises(ToolError):
        asyncio.run(
            server.call_tool(
                prepare_name,
                {
                    "probeId": PROBE_ID,
                    "caseIds": list(CASES),
                    "target": "caller-controlled",
                },
            )
        )
    with pytest.raises(ToolError):
        asyncio.run(
            server.call_tool(
                execute_name,
                {
                    "probeId": PROBE_ID,
                    "authorizedActionDigest": "a" * 64,
                    "address": 0x20000000,
                },
            )
        )
    assert calls == []
