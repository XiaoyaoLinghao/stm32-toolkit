from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit import cli
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.protocol import calculate_case_inventory_digest


PROTOCOL = "stm32-target-frame/2"
SESSION_ID = "vs10a-public"
PROBE_ID = "probe-v2"
CASES = ("suite.boot", "suite.sensor")
CASE_INVENTORY_DIGEST = calculate_case_inventory_digest(CASES)
INVENTORY_DIGEST = "1" * 64
ACTION_DIGEST = "2" * 64
PROBE_SERIAL_HASH = "3" * 64
FULL_IDENTITY = {
    "workspace_id": "4" * 64,
    "project_id": "12345678-1234-5678-1234-567812345678",
    "session_id": SESSION_ID,
    "build_id": "5" * 64,
    "elf_sha256": "6" * 64,
    "target_device": "STM32F429ZGTx",
    "input_snapshot_sha256": "7" * 64,
    "git_commit": "8" * 40,
    "git_dirty": False,
}


def _write_v2_project(project: Path) -> None:
    project.mkdir()
    (project / ".stm32-project.json").write_text(
        json.dumps(
            {"testing": {"target": {"protocol": PROTOCOL}}},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


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
    project: Path, data_root: Path, action_digest: str = ACTION_DIGEST
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


class _FakeTargetSession:
    """Equivalent isolated target sessions used only at the public adapter seam."""

    def __init__(self, project_root: Path, data_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.data_root = data_root.resolve()
        self.calls: list[tuple[str, str]] = []

    def _assert_bound_v2_context(self, context: object) -> None:
        assert Path(context.project_root).resolve() == self.project_root
        assert Path(context.data_root).resolve() == self.data_root
        assert context.session_id == SESSION_ID
        manifest = json.loads(
            (self.project_root / ".stm32-project.json").read_text(encoding="utf-8")
        )
        assert manifest["testing"]["target"]["protocol"] == PROTOCOL

    def _data(self, *, action_digest: str | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "protocol": PROTOCOL,
            "identity": FULL_IDENTITY,
            "inventory_digest": INVENTORY_DIGEST,
            "case_inventory_digest": CASE_INVENTORY_DIGEST,
            "case_ids": list(CASES),
            "probe_serial_hash": PROBE_SERIAL_HASH,
        }
        if action_digest is not None:
            data["authorized_action_digest"] = action_digest
        return data

    async def prepare(
        self, context: object, *, probe_id: str, case_ids: tuple[str, ...]
    ) -> OperationResult[dict[str, object]]:
        self._assert_bound_v2_context(context)
        assert probe_id == PROBE_ID
        assert case_ids == CASES
        self.calls.append(("prepare", probe_id))
        return OperationResult.success(
            "test.target.prepare", self._data(action_digest=ACTION_DIGEST)
        )

    async def execute(
        self, context: object, *, probe_id: str, authorized_action_digest: str
    ) -> OperationResult[dict[str, object]]:
        self._assert_bound_v2_context(context)
        assert probe_id == PROBE_ID
        assert authorized_action_digest == ACTION_DIGEST
        self.calls.append(("execute", authorized_action_digest))
        return OperationResult.success(
            "test.target.execute",
            {
                **self._data(action_digest=authorized_action_digest),
                "run": {"state": "passed", "execution_source": "physical"},
                "physical_transport_evidence": True,
            },
        )


def _cli_result(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
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


def test_cli_and_mcp_v2_target_prepare_execute_have_identical_public_semantics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_project = tmp_path / "cli-project"
    cli_data = tmp_path / "cli-data"
    mcp_project = tmp_path / "mcp-project"
    mcp_data = tmp_path / "mcp-data"
    _write_v2_project(cli_project)
    _write_v2_project(mcp_project)

    cli_session = _FakeTargetSession(cli_project, cli_data)
    mcp_session = _FakeTargetSession(mcp_project, mcp_data)
    monkeypatch.setattr(cli, "target_test_prepare", cli_session.prepare)
    monkeypatch.setattr(cli, "target_test_execute", cli_session.execute)
    monkeypatch.setattr(mcp_mod, "target_test_prepare", mcp_session.prepare)
    monkeypatch.setattr(mcp_mod, "target_test_execute", mcp_session.execute)

    cli_prepare = _cli_result(_prepare_argv(cli_project, cli_data), capsys)
    mcp_prepare = asyncio.run(
        _mcp_call(
            mcp_project,
            mcp_data,
            MCP_TOOL_NAMES["test_target_prepare"],
            {"probeId": PROBE_ID, "caseIds": list(CASES)},
        )
    )
    assert cli_prepare == mcp_prepare
    assert cli_prepare["operation"] == "test.target.prepare"
    assert cli_prepare["code"] == "OK"
    assert cli_prepare["data"]["protocol"] == PROTOCOL
    assert cli_prepare["data"]["identity"] == FULL_IDENTITY
    assert cli_prepare["data"]["case_inventory_digest"] == CASE_INVENTORY_DIGEST

    cli_execute = _cli_result(
        _execute_argv(cli_project, cli_data), capsys
    )
    mcp_execute = asyncio.run(
        _mcp_call(
            mcp_project,
            mcp_data,
            MCP_TOOL_NAMES["test_target_execute"],
            {
                "probeId": PROBE_ID,
                "authorizedActionDigest": ACTION_DIGEST,
            },
        )
    )
    assert cli_execute == mcp_execute
    assert cli_execute["operation"] == "test.target.execute"
    assert cli_execute["code"] == "OK"
    assert cli_execute["data"]["protocol"] == PROTOCOL
    assert cli_execute["data"]["identity"] == FULL_IDENTITY
    assert cli_execute["data"]["case_inventory_digest"] == CASE_INVENTORY_DIGEST
    assert cli_session.calls == [("prepare", PROBE_ID), ("execute", ACTION_DIGEST)]
    assert mcp_session.calls == [("prepare", PROBE_ID), ("execute", ACTION_DIGEST)]


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
    base = _prepare_argv(project, tmp_path / "data")
    for option in ("--identity", "--elf", "--target", "--address"):
        assert cli.main([*base, option, "caller-controlled"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert calls == []


def test_mcp_target_tools_expose_only_declared_project_probe_contract(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    tools = asyncio.run(
        create_server(project, tmp_path / "data", SESSION_ID).list_tools()
    )
    schemas = {tool.name: tool.inputSchema for tool in tools}

    assert set(schemas[MCP_TOOL_NAMES["test_target_prepare"]]["properties"]) == {
        "probeId",
        "caseIds",
    }
    assert set(schemas[MCP_TOOL_NAMES["test_target_execute"]]["properties"]) == {
        "probeId",
        "authorizedActionDigest",
    }
    forbidden = {
        "projectRoot",
        "dataRoot",
        "sessionId",
        "identity",
        "buildId",
        "elf",
        "elfPath",
        "target",
        "svd",
        "address",
        "size",
        "transport",
        "lease",
    }
    for name in (
        MCP_TOOL_NAMES["test_target_prepare"],
        MCP_TOOL_NAMES["test_target_execute"],
    ):
        assert not forbidden.intersection(schemas[name]["properties"])
