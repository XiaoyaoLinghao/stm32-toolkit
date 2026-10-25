"""Registered MCP/CLI routes and strict protocol schema copies."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

import pytest

import stm32_toolkit.cli as cli
import stm32_toolkit.mcp_server as mcp_mod
import stm32_toolkit.probe.protocol as protocol
from stm32_toolkit import __version__
from stm32_toolkit.mcp_server import ServerRuntime, create_server
from stm32_toolkit.result import OperationResult

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_SCHEMA = REPO_ROOT / "schemas" / "probe-protocol.schema.json"
PACKAGED_SCHEMA = (
    REPO_ROOT
    / "tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json"
)
BASE = 0x0800_0000
REGIONS = [{"start": 0x0800_0000, "length": 0x1_0000}]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    return ServerRuntime.create(project, tmp_path / "data", "session-a")


def _server(tmp_path: Path):
    runtime = _runtime(tmp_path)
    return runtime, create_server(
        runtime.project_root, runtime.data_root, runtime.session_id
    )


def _schemas(server: object) -> dict[str, dict[str, object]]:
    return {
        tool.name: tool.inputSchema
        for tool in asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    }


def _resolve(schema: dict[str, object], node: dict[str, object]) -> dict[str, object]:
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        return schema["$defs"][reference.rsplit("/", 1)[-1]]  # type: ignore[index]
    return node


def test_registered_firmware_tools_expose_closed_source_only_shapes(
    tmp_path: Path,
) -> None:
    _runtime_value, server = _server(tmp_path)
    schemas = _schemas(server)

    assert set(schemas["stm32_firmware_import"]["properties"]) == {
        "firmwarePath",
        "expectedSha256",
        "format",
        "target",
        "flashRegions",
        "baseAddress",
        "planId",
        "authorized",
    }
    assert set(schemas["stm32_firmware_admit"]["properties"]) == {
        "importId",
        "expectedSha256",
    }
    assert set(schemas["stm32_flash_imported"]["properties"]) == {
        "probeId",
        "importId",
        "expectedSha256",
        "authorized",
        "frequencyHz",
    }
    import_schema = schemas["stm32_firmware_import"]
    regions = import_schema["properties"]["flashRegions"]
    assert regions["minItems"] == 1
    assert regions["maxItems"] == 32
    region_item = _resolve(import_schema, regions["items"])
    assert region_item["additionalProperties"] is False
    assert set(region_item["properties"]) == {"start", "length"}
    forbidden = {
        "elfPath",
        "projectRoot",
        "dataRoot",
        "sessionId",
        "backend",
        "endpoint",
        "token",
        "workspace",
        "lease",
        "svd",
        "address",
        "argv",
    }
    for name in (
        "stm32_firmware_import",
        "stm32_firmware_admit",
        "stm32_flash_imported",
    ):
        assert not (set(schemas[name]["properties"]) & forbidden)


def test_registered_import_tools_reject_coerced_or_extra_inputs(
    tmp_path: Path,
) -> None:
    runtime, server = _server(tmp_path)
    payload = b"coercion"
    (runtime.project_root / "fw.bin").write_bytes(payload)
    base_arguments = {
        "firmwarePath": "fw.bin",
        "expectedSha256": _sha(payload),
        "format": "bin",
        "target": "stm32f407vg",
        "flashRegions": REGIONS,
        "baseAddress": BASE,
    }

    for mutation in (
        {"authorized": "true"},
        {"authorized": 1},
        {"flashRegions": [{"start": True, "length": 16}]},
        {"flashRegions": [{"start": BASE, "length": 16, "extra": 1}]},
    ):
        with pytest.raises(Exception):
            asyncio.run(
                server.call_tool(
                    "stm32_firmware_import", {**base_arguments, **mutation}
                )
            )
    assert not (tmp_path / "data" / "projects").exists()


def test_registered_mcp_plan_apply_admit_on_unmanaged_fixture(tmp_path: Path) -> None:
    runtime, server = _server(tmp_path)
    payload = b"registered-mcp"
    (runtime.project_root / "fw.bin").write_bytes(payload)
    arguments = {
        "firmwarePath": "fw.bin",
        "expectedSha256": _sha(payload),
        "format": "bin",
        "target": "stm32f407vg",
        "flashRegions": REGIONS,
        "baseAddress": BASE,
    }
    assert not (runtime.project_root / ".stm32-project.json").exists()

    _content, plan = asyncio.run(
        server.call_tool("stm32_firmware_import", arguments)
    )
    assert plan["ok"] is True, plan
    assert plan["data"]["mode"] == "firmware-import-plan"
    assert "hardware" not in plan["data"]

    _content, applied = asyncio.run(
        server.call_tool(
            "stm32_firmware_import",
            {
                **arguments,
                "planId": plan["data"]["planId"],
                "authorized": True,
            },
        )
    )
    assert applied["ok"] is True, applied
    assert applied["data"]["created"] is True
    assert applied["data"]["hardware"]["authorized"] is False

    _content, admitted = asyncio.run(
        server.call_tool(
            "stm32_firmware_admit",
            {
                "importId": applied["data"]["importId"],
                "expectedSha256": _sha(payload),
            },
        )
    )
    assert admitted["ok"] is True, admitted
    assert admitted["data"]["offlineReady"] is True
    assert admitted["data"]["hardwareVerified"] is False
    assert admitted["data"]["sourceSha256"] != admitted["data"]["imageSha256"]
    assert admitted["data"]["target"] == "stm32f407vg"
    assert not (runtime.project_root / ".stm32-project.json").exists()


def test_mcp_roots_guard_runs_before_offline_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime(tmp_path)
    calls: list[str] = []

    async def roots_unavailable(*_args: object) -> dict[str, object]:
        calls.append("roots")
        return OperationResult.failure(
            "stm32_firmware_import",
            "MCP_ROOTS_UNAVAILABLE",
            "MCP client roots are unavailable",
            {},
        ).to_dict()

    def forbidden(_request: object) -> OperationResult[object]:
        raise AssertionError("workflow must not run after root refusal")

    monkeypatch.setattr(mcp_mod, "_client_roots_failure", roots_unavailable)
    monkeypatch.setattr(mcp_mod, "firmware_import_workflow", forbidden)

    result = asyncio.run(
        mcp_mod.tool_firmware_import_for_request(
            runtime,
            None,
            "fw.bin",
            "a" * 64,
            "bin",
            "stm32f407vg",
            [mcp_mod.FirmwareFlashRegion(start=BASE, length=16)],
            BASE,
            None,
            False,
        )
    )
    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert calls == ["roots"]


def _cli_import_arguments(
    project: Path, data_root: Path, payload: bytes, *, mode: str, plan_id: str | None = None
) -> list[str]:
    arguments = [
        "firmware",
        "import",
        "--project-root",
        str(project),
        "--data-root",
        str(data_root),
        "--session-id",
        "session-a",
        "--firmware-path",
        "fw.bin",
        "--expected-sha256",
        _sha(payload),
        "--format",
        "bin",
        "--target",
        "stm32f407vg",
        "--flash-regions",
        json.dumps(REGIONS),
        "--base-address",
        str(BASE),
        mode,
        "--json",
    ]
    if plan_id is not None:
        arguments.extend(["--plan-id", plan_id])
    if mode == "--apply":
        arguments.append("--authorized")
    return arguments


def test_cli_import_plan_apply_and_admit_are_real_argv_routes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    payload = b"cli-routed"
    (project / "fw.bin").write_bytes(payload)

    assert cli.main(_cli_import_arguments(project, data_root, payload, mode="--dry-run")) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["ok"] is True, plan
    assert plan["data"]["mode"] == "firmware-import-plan"
    assert not data_root.exists()

    assert (
        cli.main(
            _cli_import_arguments(
                project,
                data_root,
                payload,
                mode="--apply",
                plan_id=plan["data"]["planId"],
            )
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["ok"] is True, applied
    assert applied["data"]["created"] is True

    assert (
        cli.main(
            [
                "firmware",
                "admit",
                "--project-root",
                str(project),
                "--data-root",
                str(data_root),
                "--session-id",
                "session-a",
                "--import-id",
                applied["data"]["importId"],
                "--expected-sha256",
                _sha(payload),
                "--json",
            ]
        )
        == 0
    )
    admitted = json.loads(capsys.readouterr().out)
    assert admitted["data"]["offlineReady"] is True
    assert admitted["data"]["hardwareVerified"] is False


def test_cli_import_rejects_authorized_without_apply_and_bad_region_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    payload = b"cli-rejected"
    (project / "fw.bin").write_bytes(payload)

    unauthorized = _cli_import_arguments(
        project, data_root, payload, mode="--dry-run"
    )
    unauthorized.insert(-1, "--authorized")
    assert cli.main(unauthorized) == 2
    assert "invalid arguments" in capsys.readouterr().err

    bad_regions = _cli_import_arguments(
        project, data_root, payload, mode="--dry-run"
    )
    bad_regions[bad_regions.index("--flash-regions") + 1] = '[{"start": true, "length": 16}]'
    assert cli.main(bad_regions) == 2
    assert "invalid arguments" in capsys.readouterr().err
    assert not data_root.exists()


def test_cli_flash_imported_routes_only_documented_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    captured: dict[str, object] = {}

    async def accepted(request: object) -> OperationResult[object]:
        captured["request"] = request
        return OperationResult.success("stm32_flash_imported", {"routed": True})

    monkeypatch.setattr(cli, "flash_imported_workflow", accepted)

    assert (
        cli.main(
            [
                "flash-imported",
                "--project-root",
                str(project),
                "--data-root",
                str(tmp_path / "data"),
                "--session-id",
                "session-a",
                "--probe",
                "probe-a",
                "--import-id",
                "a" * 64,
                "--expected-sha256",
                "b" * 64,
                "--authorized",
                "--json",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["data"] == {"routed": True}
    request = captured["request"]
    assert type(request).__name__ == "FlashImportedWorkflowRequest"
    assert request.project_root == project
    assert request.probe_id == "probe-a"
    assert request.import_id == "a" * 64
    assert request.authorized is True


def _fresh_cli(
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "stm32_toolkit.cli", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=120,
    )


def test_fresh_process_cli_plan_apply_admit_and_malformed_input(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data_root = tmp_path / "data"
    payload = b"fresh-process"
    (project / "fw.bin").write_bytes(payload)

    planned = _fresh_cli(
        _cli_import_arguments(project, data_root, payload, mode="--dry-run")
    )
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    assert plan["ok"] is True, plan
    assert plan["data"]["mode"] == "firmware-import-plan"
    assert not data_root.exists()

    applied = _fresh_cli(
        _cli_import_arguments(
            project,
            data_root,
            payload,
            mode="--apply",
            plan_id=plan["data"]["planId"],
        )
    )
    assert applied.returncode == 0, applied.stderr
    applied_data = json.loads(applied.stdout)
    assert applied_data["data"]["created"] is True

    admitted = _fresh_cli(
        [
            "firmware",
            "admit",
            "--project-root",
            str(project),
            "--data-root",
            str(data_root),
            "--session-id",
            "session-a",
            "--import-id",
            applied_data["data"]["importId"],
            "--expected-sha256",
            _sha(payload),
            "--json",
        ]
    )
    assert admitted.returncode == 0, admitted.stderr
    admitted_data = json.loads(admitted.stdout)
    assert admitted_data["data"]["offlineReady"] is True
    assert admitted_data["data"]["hardwareVerified"] is False

    malformed = _fresh_cli(
        [
            "firmware",
            "import",
            "--project-root",
            str(project),
            "--data-root",
            str(tmp_path / "data2"),
            "--session-id",
            "session-a",
            "--firmware-path",
            "fw.bin",
            "--expected-sha256",
            _sha(payload),
            "--format",
            "bin",
            "--target",
            "stm32f407vg",
            "--flash-regions",
            "not-json",
            "--base-address",
            str(BASE),
            "--dry-run",
            "--json",
        ]
    )
    assert malformed.returncode == 2
    assert "invalid arguments" in malformed.stderr
    assert not (tmp_path / "data2").exists()


def test_both_protocol_schema_copies_define_the_imported_program_contract() -> None:
    assert ROOT_SCHEMA.read_bytes() == PACKAGED_SCHEMA.read_bytes()
    schema = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
    assert "flash.program.imported" in schema["properties"]["operation"]["enum"]
    branches = [
        branch
        for branch in schema["allOf"]
        if branch.get("if", {}).get("properties", {}).get("operation", {}).get("const")
        == "flash.program.imported"
    ]
    assert len(branches) == 1
    then = branches[0]["then"]
    assert then["properties"]["operationLevel"] == {"const": "modify"}
    data = then["properties"]["data"]
    assert data["additionalProperties"] is False
    assert set(data["required"]) == {"elfPath", "elfSha256", "elfSize"}
    assert data["properties"]["elfPath"]["enum"] == ["image.elf"]


def _request(
    operation: str, level: str, data: Mapping[str, object], timeout: int = 300_000
) -> dict[str, object]:
    return {
        "protocol": "stm32-toolkit-probe/2",
        "toolkitVersion": __version__,
        "requestId": "request-imported",
        "workspaceId": "workspace-a",
        "sessionId": "session-a",
        "leaseId": "lease-a",
        "operationLevel": level,
        "operation": operation,
        "timeoutMs": timeout,
        "data": dict(data),
    }


def _decode(payload: Mapping[str, object]):
    return protocol.decode_request(
        json.dumps(payload).encode("utf-8"), __version__
    )


def test_protocol_decodes_only_the_exact_imported_program_request() -> None:
    data = {"elfPath": "image.elf", "elfSha256": "a" * 64, "elfSize": 8}
    decoded = _decode(_request("flash.program.imported", "modify", data))
    assert decoded.operation == "flash.program.imported"
    assert decoded.operation_level.value == "modify"

    rejected = (
        _request("flash.program.imported", "observe", data),
        _request(
            "flash.program.imported",
            "modify",
            {**data, "elfPath": "other.elf"},
        ),
        _request("flash.program.imported", "modify", {**data, "extra": 1}),
        _request(
            "flash.program.imported",
            "modify",
            {**data, "elfSize": True},
        ),
    )
    for payload in rejected:
        with pytest.raises(protocol.ProbeProtocolError):
            _decode(payload)

